"""Backup em .zip com os dois bancos (sistema.db + anexos.db) e o LEIA-ME.txt, e tudo o que dá para fazer com ele:
reconhecer, listar (inclusive em outra pasta) e restaurar.

Regras de segurança:
- um .zip só vale se tiver, na raiz, `sistema.db` e `anexos.db` abríveis, íntegros (PRAGMA quick_check) e com as tabelas
  essenciais. O reconhecimento é pelo conteúdo, nunca pelo nome do arquivo;
- o zip nunca é extraído com os nomes que ele traz: só os dois membros esperados, lidos aos poucos para arquivos
  temporários de nomes fixos (sem path traversal) e com limite de tamanho (sem zip bomb);
- a busca em outra pasta só lê: não entra em subpastas, não segue links simbólicos e limita a quantidade de arquivos.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime, timedelta

from . import anexos

PREFIXO_SEGURANCA = 'ANTES-DE-RESTAURAR'
MEMBROS = ('sistema.db', 'anexos.db')
MAX_TOTAL_DESCOMPRIMIDO = 40 * 1024 ** 3       # 40 GB no total
MAX_RAZAO = 2000                               # taxa máxima de compressão aceita por arquivo do zip
MAX_ARQUIVOS_NA_PASTA = 300
TABELAS_ESSENCIAIS = {'usuarios', 'clientes', 'config'}


class ErroBackup(ValueError):
    """Backup inválido ou operação que não pôde ser feita (mensagem mostrada ao usuário)."""


def _copiar_banco(origem, destino):
    a, b = sqlite3.connect(origem), sqlite3.connect(destino)
    try:
        with b:
            a.backup(b)   # cópia consistente mesmo com o sistema em uso
    finally:
        a.close()
        b.close()


def _mb(caminho):
    return os.path.getsize(caminho) / 1048576


def _leia_me(versao, quando, tam_sistema, tam_anexos, nome_zip, tam_trocas=None):
    linha_trocas = ''
    if tam_trocas is not None:
        linha_trocas = '\n  nucleai_trocas.jsonl (%(tt).1f MB)  histórico de trocas de modelo da NucleAI IA.' % {'tt': tam_trocas}
    return '''BACKUP DO SISTEMA NUCLELESTE
============================

Arquivo: %(nome)s
Gerado em: %(quando)s
Versão do sistema: %(versao)s

O QUE HÁ NESTE ARQUIVO
  sistema.db  (%(ts).1f MB)  cadastros, atendimentos, financeiro, agenda, usuários, banco de horas e demais dados.
  anexos.db   (%(ta).1f MB)  os arquivos anexados (PDF, Word, Excel e imagens) dos módulos Documentos e Departamento Pessoal.%(trocas)s
  LEIA-ME.txt               este texto.

IMPORTANTE: OS DOIS BANCOS DEVEM SEMPRE SER RESTAURADOS JUNTOS.
O sistema.db guarda só a referência dos anexos; o conteúdo deles está no anexos.db.
Quando presente, o arquivo nucleai_trocas.jsonl contém o histórico de trocas de modelo da IA.

COMO RESTAURAR

1) Pelo próprio sistema (recomendado)
   - Entre como administrador ou gerência e abra Configuração > Backup.
   - Clique em "Restaurar o último backup" ou em "Restaurar" na linha deste arquivo.
   - Para um backup que está em um pendrive, outro disco ou pasta de rede, use "Buscar em outra pasta".
   - Confira os dados na tela e digite o código de verificação. O sistema guarda uma cópia do estado atual
     (ANTES-DE-RESTAURAR) antes de trocar os dados.

2) Manualmente (se o sistema não abre)
   - Feche o sistema (ícone da bandeja > Sair).
   - Abra este .zip e extraia sistema.db e anexos.db.
   - Se houver nucleai_trocas.jsonl, extraia-o para a pasta nucleai/trocas.jsonl.
   - Na pasta de dados (normalmente C:\\ProgramData\\Nucleleste), substitua os arquivos pelos extraídos.
     Apague também sistema.db-wal, sistema.db-shm, anexos.db-wal e anexos.db-shm, se existirem.
   - Abra o sistema de novo.

GUARDE UMA CÓPIA FORA DO COMPUTADOR
Copie os backups periodicamente para um pendrive, outro computador ou a nuvem. Se o computador for perdido,
os backups que estavam nele também se perdem.
''' % {'nome': nome_zip, 'quando': quando, 'versao': versao, 'ts': tam_sistema, 'ta': tam_anexos, 'trocas': linha_trocas}


# ------------------------------------------------------------------ onde ficam os backups
# O backup (.zip) é SEMPRE gravado numa pasta deste computador (`backups/`, ao lado do banco). A "pasta externa" (Google Drive,
# rede, pendrive) recebe uma CÓPIA dos backups dos últimos DIAS_RETENCAO dias. Backups BACKUP_ com mais de DIAS_RETENCAO dias
# são apagados, na pasta local e nas externas. Quem copia é o programa que enxerga a pasta: o servidor roda como
# conta SYSTEM, que não vê o Drive nem as unidades mapeadas do usuário; a bandeja do Windows roda na sessão do usuário e vê.
CHAVE_PASTAS = 'backup_pastas_destino'      # `config`: JSON com a lista de pastas externas (caminhos completos)
CHAVE_PASTA = 'backup_pasta_destino'        # formato antigo (uma pasta); é migrado para CHAVE_PASTAS e esvaziado
CHAVE_ESTADO = 'backup_pastas_estado'       # JSON {caminho: {ok_em, ultimo, erro, erro_em}}: situação de cada pasta
MAX_PASTAS = 5                              # quantas pastas externas podem ser configuradas
MAX_SUBSTITUIDOS = 200                      # tamanho máximo da lista de automáticos substituídos
CHAVE_AUTO = 'backup_auto'                  # '1' = backup automático ligado
CHAVE_AUTO_INICIO = 'backup_auto_inicio'    # HH:MM: começo da janela diária
CHAVE_AUTO_FIM = 'backup_auto_fim'          # HH:MM: fim da janela diária (inclusive)
CHAVE_AUTO_MINUTOS = 'backup_auto_minutos'  # intervalo entre backups dentro da janela
CHAVE_AUTO_ULTIMO = 'backup_auto_ultimo_em' # AAAA-MM-DD HH:MM:SS do último automático (também é a reserva)
CHAVE_AUTO_DATA = 'backup_auto_data'        # dia do último backup automático (a tela usa)
CHAVE_AUTO_ARQUIVO = 'backup_auto_arquivo'  # nome do último .zip automático
CHAVE_AUTO_SUBSTITUIDOS = 'backup_auto_substituidos'  # JSON: automáticos já substituídos que podem estar na pasta externa
INICIO_PADRAO = '08:00'
FIM_PADRAO = '18:00'
MINUTOS_PADRAO = 30
OPCOES_MINUTOS = (15, 30, 60, 120, 180, 240)   # intervalos aceitos
DIAS_RETENCAO = 7                           # backups BACKUP_ com mais de 7 dias são apagados (local e pastas externas)
MINIMO_GUARDADO = 3                         # os 3 mais recentes nunca são apagados por idade


def pasta_padrao(banco):
    return os.path.join(os.path.dirname(os.path.abspath(banco)), 'backups')


def _config_ler(con, chave, padrao=''):
    r = con.execute('SELECT valor FROM config WHERE chave=?', (chave,)).fetchone()
    return r[0] if r and r[0] is not None else padrao


def _config_gravar(con, chave, valor):
    con.execute('INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor', (chave, valor))


def _agora_texto():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def backups_locais(banco):
    """Nomes dos BACKUP_*.zip da pasta local, do mais novo para o mais antigo."""
    pasta = pasta_padrao(banco)
    itens = []
    try:
        for f in os.listdir(pasta):
            if f.startswith('BACKUP_') and f.lower().endswith('.zip'):
                try:
                    itens.append((os.path.getmtime(os.path.join(pasta, f)), f))
                except OSError:
                    continue
    except OSError:
        return []
    return [f for _, f in sorted(itens, reverse=True)]


def caminho_externo_valido(bruto):
    """(caminho normalizado, None) ou (None, mensagem). Só exige caminho completo: a pasta pode estar numa unidade que este
    programa não enxerga (Drive, rede, pendrive); quem copia é o que a enxerga."""
    bruto = (bruto or '').strip().strip('"')
    if not bruto or '\x00' in bruto:
        return None, 'Informe o caminho da pasta.'
    if not os.path.isabs(bruto):
        return None, 'Informe o caminho completo da pasta (exemplo: G:\\Meu Drive\\Backups ou \\\\servidor\\backups).'
    return os.path.normpath(bruto), None


def _normaliza(pasta):
    """Chave de comparação de pastas: sem diferenciar maiúsculas e com barras e separadores iguais."""
    return os.path.normcase(os.path.normpath(str(pasta).strip().strip('"')))


def _unicas(pastas):
    """Sem repetir (pela chave de `_normaliza`), na ordem, e no máximo MAX_PASTAS."""
    vistos, saida = set(), []
    for p in pastas:
        p = str(p or '').strip().strip('"')
        chave = _normaliza(p) if p else ''
        if chave and chave not in vistos:
            vistos.add(chave)
            saida.append(p)
    return saida[:MAX_PASTAS]


def _estado_lido(con):
    try:
        valor = json.loads(_config_ler(con, CHAVE_ESTADO, '{}') or '{}')
    except (TypeError, ValueError):
        return {}
    return valor if isinstance(valor, dict) else {}


def pastas_destino(con, migrar=False):
    """Pastas externas configuradas (sem repetir, até MAX_PASTAS). Se a lista estiver vazia e existir a pasta do formato antigo
    (CHAVE_PASTA), ela vira o primeiro item. Com `migrar=True` a migração é gravada uma vez e a chave antiga é esvaziada."""
    lista = _unicas(_lista_json(_config_ler(con, CHAVE_PASTAS)))
    antiga = (_config_ler(con, CHAVE_PASTA) or '').strip().strip('"')
    if antiga:
        if not lista:
            lista = _unicas([antiga])
        if migrar:
            _config_gravar(con, CHAVE_PASTAS, json.dumps(lista))
            _config_gravar(con, CHAVE_PASTA, '')
            con.commit()
    return lista


def lista_pastas(banco, migrar=False):
    """Pastas externas configuradas (ver `pastas_destino`). Lista vazia se não houver ou se o banco não abrir."""
    try:
        con = sqlite3.connect(os.path.abspath(banco), timeout=15)
    except sqlite3.Error:
        return []
    try:
        return pastas_destino(con, migrar)
    except sqlite3.Error:
        return []
    finally:
        con.close()


def salvar_pastas(banco, pastas):
    """Grava a lista de pastas externas (sem repetir, até MAX_PASTAS), tira a chave antiga e descarta a situação das pastas removidas."""
    lista = _unicas(pastas)
    con = sqlite3.connect(os.path.abspath(banco), timeout=15)
    try:
        estado = _estado_lido(con)
        _config_gravar(con, CHAVE_PASTAS, json.dumps(lista))
        _config_gravar(con, CHAVE_PASTA, '')
        _config_gravar(con, CHAVE_ESTADO, json.dumps({p: estado[p] for p in lista if p in estado}))
        con.commit()
    finally:
        con.close()
    return lista


def tem_substituidos_pendentes(banco):
    """Há automáticos substituídos que ainda podem estar em alguma pasta externa (a bandeja precisa sincronizar)."""
    try:
        con = sqlite3.connect('file:%s?mode=ro' % os.path.abspath(banco).replace('\\', '/').replace('?', '%3f').replace('#', '%23'), uri=True)
    except sqlite3.Error:
        return False
    try:
        return bool(_lista_json(_config_ler(con, CHAVE_AUTO_SUBSTITUIDOS)))
    except sqlite3.Error:
        return False
    finally:
        con.close()


def sincronizar_externa(banco, quem='', hoje=None):
    """Copia os backups dos últimos DIAS_RETENCAO dias (BACKUP_*.zip) para CADA pasta externa, de forma independente: uma pasta que
    falha não impede as outras. Também apaga de cada pasta os automáticos substituídos (lista antiga) e os BACKUP_ com mais de
    DIAS_RETENCAO dias. Devolve os nomes copiados (sem repetir), ou None se não há pasta ou se nenhuma pasta foi acessível agora.
    O erro de cada pasta fica em CHAVE_ESTADO, com o 'quem' (servidor ou bandeja)."""
    banco = os.path.abspath(banco)
    hoje = hoje or date.today()
    limite = hoje - timedelta(days=DIAS_RETENCAO)
    try:
        con = sqlite3.connect(banco, timeout=15)
    except sqlite3.Error:
        return None
    try:
        pastas = pastas_destino(con, migrar=True)
        if not pastas:
            return None
        origem = pasta_padrao(banco)
        recentes = []
        for nome in backups_locais(banco):
            data = _data_backup(os.path.join(origem, nome))
            if data is None or data >= limite:
                recentes.append(nome)
        substituidos = _lista_json(_config_ler(con, CHAVE_AUTO_SUBSTITUIDOS))
        estado = _estado_lido(con)
        copiados, acessiveis = [], []
        for pasta in pastas:
            info = dict(estado.get(pasta) or {})
            try:
                if not os.path.isabs(pasta):
                    raise OSError('o caminho precisa ser completo (exemplo: G:\\Meu Drive\\Backups)')
                os.makedirs(pasta, exist_ok=True)
                for nome in recentes:
                    fonte, destino = os.path.join(origem, nome), os.path.join(pasta, nome)
                    if os.path.exists(destino) and os.path.getsize(destino) == os.path.getsize(fonte):
                        continue
                    tmp = destino + '.parcial'
                    try:
                        shutil.copyfile(fonte, tmp)
                        os.replace(tmp, destino)
                    finally:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    if nome not in copiados:
                        copiados.append(nome)
                # automáticos substituídos no mesmo dia: saem desta pasta também (só esses nomes, nada mais)
                for velho in substituidos:
                    caminho_velho = os.path.join(pasta, os.path.basename(velho))
                    if velho.startswith('BACKUP_') and os.path.isfile(caminho_velho):
                        os.remove(caminho_velho)
                _apagar_antigos(pasta, hoje)
            except OSError as e:
                info.update(erro='%s: %s (%s)' % (quem or 'servidor', e.strerror or e, pasta), erro_em=_agora_texto())
                estado[pasta] = info
                continue
            locais = backups_locais(banco)
            info.update(ok_em=_agora_texto(), ultimo=locais[0] if locais else '', erro='', erro_em='')
            estado[pasta] = info
            acessiveis.append(pasta)
        # um nome só sai da lista quando TODAS as pastas estavam acessíveis nesta rodada e nenhuma tem mais o arquivo;
        # se alguma pasta deu erro, a lista fica como está para a próxima rodada (o limite de MAX_SUBSTITUIDOS continua valendo)
        if len(acessiveis) < len(pastas):
            restantes = list(substituidos)
        else:
            restantes = [n for n in substituidos if any(os.path.isfile(os.path.join(p, os.path.basename(n))) for p in acessiveis)]
        _config_gravar(con, CHAVE_AUTO_SUBSTITUIDOS, json.dumps(restantes[-MAX_SUBSTITUIDOS:]))
        _config_gravar(con, CHAVE_ESTADO, json.dumps({p: estado[p] for p in pastas if p in estado}))
        con.commit()
        return copiados if acessiveis else None
    finally:
        con.close()


def estado_externa(banco):
    """Situação de cada pasta externa para a tela: lista de {'pasta', 'ok_em', 'ultimo', 'em_dia', 'erro', 'erro_em'}
    (lista vazia = nenhuma pasta configurada)."""
    banco = os.path.abspath(banco)
    try:
        con = sqlite3.connect('file:%s?mode=ro' % banco.replace('\\', '/').replace('?', '%3f').replace('#', '%23'), uri=True)
    except sqlite3.Error:
        return []
    try:
        pastas = pastas_destino(con)
        estado = _estado_lido(con)
    except sqlite3.Error:
        return []
    finally:
        con.close()
    locais = backups_locais(banco)
    saida = []
    for p in pastas:
        e = estado.get(p) if isinstance(estado.get(p), dict) else {}
        ok_em, ultimo = e.get('ok_em', ''), e.get('ultimo', '')
        saida.append({'pasta': p, 'ok_em': ok_em, 'ultimo': ultimo, 'em_dia': bool(ok_em and ultimo and (not locais or ultimo == locais[0])),
                      'erro': e.get('erro', ''), 'erro_em': e.get('erro_em', '')})
    return saida


def _data_backup(caminho):
    """Dia do backup pelo nome; se o nome não tiver data, pela data de modificação do arquivo. None se não der para saber."""
    data = _data_do_nome(os.path.basename(caminho))
    if data is not None:
        return data
    try:
        return datetime.fromtimestamp(os.path.getmtime(caminho)).date()
    except OSError:
        return None


def _apagar_antigos(pasta, hoje, extensoes=('.zip',)):
    """Apaga da `pasta` os BACKUP_ com data anterior a `hoje - DIAS_RETENCAO`, mas nunca os MINIMO_GUARDADO mais recentes (por
    mtime). Só mexe em arquivos que começam com BACKUP_. Devolve quantos apagou (0 se a pasta não pode ser listada)."""
    limite = hoje - timedelta(days=DIAS_RETENCAO)
    try:
        itens = []
        for f in os.listdir(pasta):
            if f.startswith('BACKUP_') and f.lower().endswith(tuple(extensoes)):
                try:
                    itens.append((os.path.getmtime(os.path.join(pasta, f)), f))
                except OSError:
                    continue
    except OSError:
        return 0
    apagados = 0
    for _, f in sorted(itens, reverse=True)[MINIMO_GUARDADO:]:
        data = _data_backup(os.path.join(pasta, f))
        if data is None or data >= limite:
            continue
        try:
            os.remove(os.path.join(pasta, f))
            apagados += 1
        except OSError:
            pass
    return apagados


def reter_backups(banco, hoje=None):
    """Apaga da pasta local os BACKUP_ (.zip e .db antigos) com mais de DIAS_RETENCAO dias, mantendo sempre os MINIMO_GUARDADO
    mais recentes. Devolve quantos apagou."""
    return _apagar_antigos(pasta_padrao(banco), hoje or date.today(), ('.zip', '.db'))


def _hora_minuto(texto):
    try:
        h, m = str(texto or '').split(':')
        h, m = int(h), int(m)
        return (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None
    except ValueError:
        return None


def minutos_validos(valor):
    """Intervalo entre backups automáticos: um dos valores de OPCOES_MINUTOS, ou None se não for um deles."""
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return n if n in OPCOES_MINUTOS else None


def _data_do_nome(nome):
    """Dia do backup pelo nome BACKUP_dd-mm-aaaa_HH-MM-SS.zip (None se o nome não tem esse formato)."""
    nome = str(nome or '')
    if not nome.startswith('BACKUP_'):
        return None
    try:
        return datetime.strptime(nome[7:17], '%d-%m-%Y').date()
    except ValueError:
        return None


def _lista_json(texto):
    try:
        valor = json.loads(texto or '[]')
    except (TypeError, ValueError):
        return []
    return [str(x) for x in valor] if isinstance(valor, list) else []


def _ultimo_dt(texto):
    try:
        return datetime.strptime(str(texto or ''), '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def _ler_regras(con):
    """Regras da rotina automática lidas do banco. Valor inválido volta ao padrão; janela com início não menor que o fim volta ao padrão."""
    ini = _hora_minuto(_config_ler(con, CHAVE_AUTO_INICIO, INICIO_PADRAO)) or _hora_minuto(INICIO_PADRAO)
    fim = _hora_minuto(_config_ler(con, CHAVE_AUTO_FIM, FIM_PADRAO)) or _hora_minuto(FIM_PADRAO)
    if ini >= fim:
        ini, fim = _hora_minuto(INICIO_PADRAO), _hora_minuto(FIM_PADRAO)
    return {'ligado': _config_ler(con, CHAVE_AUTO, '1') == '1', 'inicio': ini, 'fim': fim,
            'minutos': minutos_validos(_config_ler(con, CHAVE_AUTO_MINUTOS, str(MINUTOS_PADRAO))) or MINUTOS_PADRAO}


def _dentro_da_janela(agora_dt, regras):
    return regras['inicio'] <= (agora_dt.hour, agora_dt.minute) <= regras['fim']


def _inicio_janela(agora_dt, regras):
    """Começo da janela fixa em que `agora_dt` cai: início + k * minutos (08:00, 08:30, ...). None se fora da janela diária.
    Assim o atraso de um backup não se acumula: cada janela começa no horário previsto."""
    if not _dentro_da_janela(agora_dt, regras):
        return None
    ini = agora_dt.replace(hour=regras['inicio'][0], minute=regras['inicio'][1], second=0, microsecond=0)
    k = int((agora_dt - ini).total_seconds() // 60) // regras['minutos']
    return ini + timedelta(minutes=k * regras['minutos'])


def _proximo(agora_dt, ultimo, regras):
    """Próximo horário previsto do backup automático (datetime): a janela atual, se ainda não houve backup nela, ou a próxima janela;
    depois do fim da janela diária, o início do dia seguinte."""
    ini = agora_dt.replace(hour=regras['inicio'][0], minute=regras['inicio'][1], second=0, microsecond=0)
    fim = agora_dt.replace(hour=regras['fim'][0], minute=regras['fim'][1], second=0, microsecond=0)
    janela = _inicio_janela(agora_dt, regras)
    if janela is None:
        return ini if agora_dt < ini else ini + timedelta(days=1)
    if ultimo is not None and ultimo >= janela:
        cand = janela + timedelta(minutes=regras['minutos'])
    else:
        cand = agora_dt
    return ini + timedelta(days=1) if cand > fim else cand


def agenda_automatica(banco, agora_dt):
    """Como está a rotina automática, para a tela: {'ligado','inicio','fim','minutos','ultimo','arquivo','proximo'}. `ultimo` e
    `proximo` são textos 'dd/mm/aaaa HH:MM' ('' quando não há); `proximo` fica vazio se a rotina estiver desligada."""
    banco = os.path.abspath(banco)
    saida = {'ligado': False, 'inicio': INICIO_PADRAO, 'fim': FIM_PADRAO, 'minutos': MINUTOS_PADRAO, 'ultimo': '', 'arquivo': '', 'proximo': ''}
    try:
        con = sqlite3.connect('file:%s?mode=ro' % banco.replace('\\', '/').replace('?', '%3f').replace('#', '%23'), uri=True)
    except sqlite3.Error:
        return saida
    try:
        regras = _ler_regras(con)
        ultimo = _ultimo_dt(_config_ler(con, CHAVE_AUTO_ULTIMO))
        arquivo = _config_ler(con, CHAVE_AUTO_ARQUIVO)
    except sqlite3.Error:
        return saida
    finally:
        con.close()
    saida.update(ligado=regras['ligado'], inicio='%02d:%02d' % regras['inicio'], fim='%02d:%02d' % regras['fim'], minutos=regras['minutos'],
                 arquivo=arquivo, ultimo=ultimo.strftime('%d/%m/%Y %H:%M') if ultimo else '')
    if regras['ligado']:
        saida['proximo'] = _proximo(agora_dt, ultimo, regras).strftime('%d/%m/%Y %H:%M')
    return saida


def backup_automatico(banco, agora_dt, versao=''):
    """Backup automático: de `minutos` em `minutos`, só dentro da janela `inicio`..`fim` (inclusive). Cada backup gera um arquivo
    novo (o nome traz a data e o horário); os com mais de DIAS_RETENCAO dias são apagados por reter_backups. O servidor e a bandeja rodam esta rotina; o horário
    do último backup é reservado no banco antes de começar, então só um dos dois faz. Devolve o caminho do zip ou None."""
    banco = os.path.abspath(banco)
    try:
        con = sqlite3.connect(banco, timeout=15)
    except sqlite3.Error:
        return None
    anterior = ''
    try:
        regras = _ler_regras(con)
        if not regras['ligado'] or not _dentro_da_janela(agora_dt, regras):
            return None
        hoje = agora_dt.date()
        con.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES (?, '')", (CHAVE_AUTO_ULTIMO,))
        anterior = _config_ler(con, CHAVE_AUTO_ULTIMO)
        ultimo = _ultimo_dt(anterior)
        janela = _inicio_janela(agora_dt, regras)   # já houve automático nesta janela fixa (08:00, 08:30...)? então não faz
        if ultimo is not None and janela is not None and ultimo >= janela:
            return None
        # reserva (só um processo consegue trocar o horário anterior pelo de agora)
        agora_texto = agora_dt.strftime('%Y-%m-%d %H:%M:%S')
        reservou = con.execute('UPDATE config SET valor=? WHERE chave=? AND valor=?', (agora_texto, CHAVE_AUTO_ULTIMO, anterior)).rowcount
        con.commit()
        if not reservou:
            return None
    except sqlite3.Error:
        return None
    finally:
        con.close()
    try:
        caminho = criar_zip(banco, 'BACKUP', versao, agora=agora_dt)
    except Exception:   # não deu: devolve o horário anterior para a próxima rodada tentar de novo
        try:
            con = sqlite3.connect(banco, timeout=15)
            con.execute('UPDATE config SET valor=? WHERE chave=?', (anterior, CHAVE_AUTO_ULTIMO))
            con.commit()
            con.close()
        except sqlite3.Error:
            pass
        return None
    nome = os.path.basename(caminho)
    try:
        con = sqlite3.connect(banco, timeout=15)
        try:
            _config_gravar(con, CHAVE_AUTO_ARQUIVO, nome)
            _config_gravar(con, CHAVE_AUTO_DATA, hoje.isoformat())
            con.commit()
        finally:
            con.close()
    except sqlite3.Error:
        pass   # o zip já está pronto; só o registro do nome falhou
    reter_backups(banco)
    return caminho


def criar_zip(banco, prefixo='BACKUP', versao='', pasta_destino=None, agora=None):
    """Gera `<prefixo>_dd-mm-aaaa_HH-MM-SS.zip` em `backups/` com os dois bancos e o LEIA-ME.txt. Devolve o caminho.
    `agora` define a data e a hora do nome (padrão: agora). Escreve em arquivo temporário e renomeia no fim: nunca deixa um zip incompleto."""
    banco = os.path.abspath(banco)   # o banco principal em uso (dentro do zip ele sempre se chama sistema.db)
    pasta_dados = os.path.dirname(banco)
    if not os.path.exists(banco):
        raise ErroBackup('Sem banco para copiar.')
    destino_dir = pasta_destino or os.path.join(pasta_dados, 'backups')
    os.makedirs(destino_dir, exist_ok=True)
    agora = agora or datetime.now()
    nome = '%s_%s.zip' % (prefixo, agora.strftime('%d-%m-%Y_%H-%M-%S'))
    final = os.path.join(destino_dir, nome)
    tmp = final + '.parcial'
    trabalho = tempfile.mkdtemp(prefix='bkp_', dir=destino_dir)
    try:
        cop_sistema, cop_anexos = os.path.join(trabalho, 'sistema.db'), os.path.join(trabalho, 'anexos.db')
        _copiar_banco(banco, cop_sistema)
        origem_anexos = anexos.caminho_ao_lado(banco)
        anexos.garantir(origem_anexos)
        _copiar_banco(origem_anexos, cop_anexos)
        origem_trocas = os.path.join(pasta_dados, 'nucleai', 'trocas.jsonl')
        tem_trocas = os.path.isfile(origem_trocas)
        cop_trocas = os.path.join(trabalho, 'nucleai_trocas.jsonl') if tem_trocas else None
        tam_trocas = None
        if tem_trocas:
            try:
                from . import nucleai_trocas
                with nucleai_trocas._lock:
                    shutil.copyfile(origem_trocas, cop_trocas)
                tam_trocas = _mb(cop_trocas)
            except Exception:
                tem_trocas = False
                cop_trocas = None
                tam_trocas = None
        texto = _leia_me(versao or '?', agora.strftime('%d/%m/%Y %H:%M:%S'), _mb(cop_sistema), _mb(cop_anexos), nome, tam_trocas)
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(cop_sistema, 'sistema.db')
            z.write(cop_anexos, 'anexos.db')
            if tem_trocas and cop_trocas and os.path.isfile(cop_trocas):
                z.write(cop_trocas, 'nucleai_trocas.jsonl')
            z.writestr('LEIA-ME.txt', texto.replace('\n', '\r\n'))
        os.replace(tmp, final)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    return final


# ------------------------------------------------------------------ reconhecer
def _sqlite_integro(caminho, exigir_tabelas):
    """O arquivo abre como SQLite, passa no quick_check e (se pedido) tem as tabelas essenciais."""
    try:
        con = sqlite3.connect('file:%s?mode=ro' % caminho.replace('\\', '/').replace('?', '%3f').replace('#', '%23'), uri=True)
        try:
            if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                return False
            tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            return exigir_tabelas <= tabelas
        finally:
            con.close()
    except sqlite3.Error:
        return False


def _membros_do_zip(caminho):
    """Confere só a estrutura do zip (sem extrair): os dois membros esperados, tamanhos e taxa de compressão sensatos."""
    try:
        with zipfile.ZipFile(caminho) as z:
            infos = {i.filename: i for i in z.infolist()}
            if len(infos) > 20 or not all(m in infos for m in MEMBROS):
                raise ErroBackup('Este .zip não é um backup do sistema (faltam sistema.db e anexos.db).')
            total = 0
            for m in MEMBROS:
                i = infos[m]
                total += i.file_size
                if i.file_size > 0 and i.compress_size > 0 and i.file_size / i.compress_size > MAX_RAZAO:
                    raise ErroBackup('O .zip tem uma taxa de compressão suspeita e foi recusado.')
            if total > MAX_TOTAL_DESCOMPRIMIDO:
                raise ErroBackup('O .zip é grande demais para ser um backup deste sistema.')
            for m in MEMBROS:   # os dois membros precisam começar como um banco SQLite
                with z.open(m) as f:
                    if f.read(16) != b'SQLite format 3\x00':
                        raise ErroBackup('O .zip tem o nome certo, mas %s não é um banco SQLite.' % m)
            return total
    except zipfile.BadZipFile:
        raise ErroBackup('Este arquivo não é um .zip válido.')


def eh_zip_de_backup(caminho):
    """Verificação rápida (só a estrutura) usada para listar. A validação completa é feita ao restaurar (`preparar`)."""
    try:
        _membros_do_zip(caminho)
        return True
    except (ErroBackup, OSError):
        return False


def preparar(caminho):
    """Valida o backup por inteiro e devolve {'tipo': 'zip'|'db', 'sistema': caminho, 'anexos': caminho|None, 'trocas': caminho|None, 'tmp': pasta}.
    Para .zip, extrai só os dois bancos (e trocas se houver) para uma pasta temporária (quem chama apaga `tmp` no fim). Levanta ErroBackup."""
    if not os.path.isfile(caminho):
        raise ErroBackup('O arquivo de backup não foi encontrado.')
    tmp = tempfile.mkdtemp(prefix='restaurar_')
    try:
        if caminho.lower().endswith('.zip'):
            _membros_do_zip(caminho)
            lidos = 0
            with zipfile.ZipFile(caminho) as z:
                for m in MEMBROS:
                    with z.open(m) as origem, open(os.path.join(tmp, m), 'wb') as destino:
                        while True:
                            bloco = origem.read(1024 * 1024)
                            if not bloco:
                                break
                            lidos += len(bloco)
                            if lidos > MAX_TOTAL_DESCOMPRIMIDO:
                                raise ErroBackup('O .zip é grande demais para ser um backup deste sistema.')
                            destino.write(bloco)
                trocas_extraido = None
                nomes_trocas = ('nucleai_trocas.jsonl', 'nucleai/trocas.jsonl', 'trocas.jsonl')
                nome_encontrado = next((n for n in nomes_trocas if n in z.namelist()), None)
                if nome_encontrado:
                    trocas_destino = os.path.join(tmp, 'nucleai_trocas.jsonl')
                    with z.open(nome_encontrado) as origem, open(trocas_destino, 'wb') as destino:
                        while True:
                            bloco = origem.read(1024 * 1024)
                            if not bloco:
                                break
                            lidos += len(bloco)
                            if lidos > MAX_TOTAL_DESCOMPRIMIDO:
                                raise ErroBackup('O .zip é grande demais para ser um backup deste sistema.')
                            destino.write(bloco)
                    trocas_extraido = trocas_destino
            sistema, anex = os.path.join(tmp, 'sistema.db'), os.path.join(tmp, 'anexos.db')
            if not _sqlite_integro(sistema, TABELAS_ESSENCIAIS):
                raise ErroBackup('O sistema.db do .zip não passou na verificação de integridade.')
            if not _sqlite_integro(anex, {'anexos'}):
                raise ErroBackup('O anexos.db do .zip não passou na verificação de integridade.')
            return {'tipo': 'zip', 'sistema': sistema, 'anexos': anex, 'trocas': trocas_extraido, 'tmp': tmp}
        if caminho.lower().endswith('.db'):
            if not _sqlite_integro(caminho, TABELAS_ESSENCIAIS):
                raise ErroBackup('Esse backup não passou na verificação de integridade.')
            return {'tipo': 'db', 'sistema': caminho, 'anexos': None, 'trocas': None, 'tmp': tmp}
        raise ErroBackup('Formato de backup não reconhecido (use .zip ou .db).')
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


# ------------------------------------------------------------------ listar
def info_arquivo(caminho):
    st = os.stat(caminho)
    zipado = caminho.lower().endswith('.zip')
    return {'nome': os.path.basename(caminho), 'tamanho': st.st_size, 'mtime': st.st_mtime,
            'data': datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M'),
            'tipo': 'zip' if zipado else 'db', 'com_anexos': zipado}


def listar_pasta(pasta, limite=MAX_ARQUIVOS_NA_PASTA):
    """Backups válidos diretamente na pasta (sem subpastas e sem links), do mais recente para o mais antigo."""
    itens = []
    with os.scandir(pasta) as it:
        for e in it:
            if len(itens) >= limite:
                break
            nome = e.name
            baixo = nome.lower()
            if not baixo.endswith(('.zip', '.db')) or baixo.endswith('_anexos.db'):
                continue
            try:
                if e.is_symlink() or not e.is_file(follow_symlinks=False):
                    continue
                if baixo.endswith('.zip') and not eh_zip_de_backup(e.path):
                    continue
                itens.append(info_arquivo(e.path))
            except OSError:
                continue
    return sorted(itens, key=lambda i: i['mtime'], reverse=True)


# ------------------------------------------------------------------ restaurar
def restaurar(banco, caminho, versao=''):
    """Restaura o backup (.zip: sistema + anexos juntos; .db antigo: só o sistema). Antes guarda o estado atual em um
    .zip ANTES-DE-RESTAURAR; se a segunda parte falhar, volta a primeira. Devolve {'seguranca', 'tipo', 'com_anexos'}."""
    pacote = preparar(caminho)
    try:
        banco = os.path.abspath(banco)
        pasta_dados = os.path.dirname(banco)
        banco_anexos = anexos.caminho_ao_lado(banco)
        caminho_trocas = os.path.join(pasta_dados, 'nucleai', 'trocas.jsonl')
        seguranca = criar_zip(banco, PREFIXO_SEGURANCA, versao)
        try:
            _copiar_banco(pacote['sistema'], banco)
            if pacote['anexos']:
                anexos.garantir(banco_anexos)
                _copiar_banco(pacote['anexos'], banco_anexos)
            if pacote.get('trocas') and os.path.isfile(pacote['trocas']):
                os.makedirs(os.path.dirname(caminho_trocas), exist_ok=True)
                from . import nucleai_trocas
                with nucleai_trocas._lock:
                    tmp_t = caminho_trocas + '.restaurando'
                    shutil.copyfile(pacote['trocas'], tmp_t)
                    os.replace(tmp_t, caminho_trocas)
        except Exception as erro:
            try:   # volta tudo ao que era
                volta = preparar(seguranca)
                try:
                    _copiar_banco(volta['sistema'], banco)
                    _copiar_banco(volta['anexos'], banco_anexos)
                    if volta.get('trocas') and os.path.isfile(volta['trocas']):
                        os.makedirs(os.path.dirname(caminho_trocas), exist_ok=True)
                        from . import nucleai_trocas
                        with nucleai_trocas._lock:
                            tmp_t = caminho_trocas + '.restaurando'
                            shutil.copyfile(volta['trocas'], tmp_t)
                            os.replace(tmp_t, caminho_trocas)
                finally:
                    shutil.rmtree(volta['tmp'], ignore_errors=True)
            except Exception:
                raise ErroBackup('A restauração falhou e não foi possível voltar ao estado anterior automaticamente. '
                                 'Use a cópia %s.' % os.path.basename(seguranca))
            raise ErroBackup('A restauração falhou (%s). O estado anterior foi mantido; cópia em %s.' % (erro, os.path.basename(seguranca)))
        return {'seguranca': os.path.basename(seguranca), 'tipo': pacote['tipo'], 'com_anexos': bool(pacote['anexos'])}
    finally:
        shutil.rmtree(pacote['tmp'], ignore_errors=True)
