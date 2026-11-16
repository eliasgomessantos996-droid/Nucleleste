"""
Importa os dados do sistema antigo (BD.mdb exportado em JSON + aba 'log' da planilha)
para o banco SQLite do novo sistema.

Uso:
    python ferramentas/importar_dados.py --dump dados/exportacao_mdb [--planilha "../VERSÃO 2.1 RECEPÇÃO1.xlsm"]
                                         [--banco dados/sistema.db] [--substituir]

Sem --substituir, o script se recusa a sobrescrever um banco que já tenha clientes.
Com --substituir, o banco atual é guardado em dados/backups antes de ser recriado.
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from werkzeug.security import generate_password_hash  # noqa: E402

from app import util  # noqa: E402
from app.db import CONVENIOS_CAIXA, SCHEMA, inicializar  # noqa: E402

avisos = []


def carregar(pasta, tabela):
    caminho = os.path.join(pasta, tabela + '.json')
    if not os.path.exists(caminho):
        avisos.append('Tabela %s não encontrada na exportação.' % tabela)
        return []
    with open(caminho, encoding='utf-8-sig') as fh:
        dados = json.load(fh)
    if isinstance(dados, dict):
        dados = [dados]
    return dados or []


def txt(v):
    if v is None:
        return None
    s = str(v).replace('\r', ' ').replace('\n', ' ').strip()
    s = re.sub(r'\s{2,}', ' ', s)
    return s or None


def data(v, campo='', ref=''):
    if v in (None, ''):
        return None
    d = util.para_data(v)
    if d:
        return d.isoformat()
    s = txt(v)
    if s and s.upper() != 'SEM PREPARO':
        avisos.append('Data não reconhecida em %s (%s): %r — mantida como texto.' % (campo, ref, s))
    return s


def ler_log_planilha(caminho):
    """Lê a aba 'log' da planilha (data, hora, evento, usuário, computador, usuário da máquina)."""
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
          'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    with zipfile.ZipFile(caminho) as zf:
        wb = ET.fromstring(zf.read('xl/workbook.xml'))
        rels = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
        alvo = {r.get('Id'): r.get('Target') for r in rels}
        arquivo = None
        for sh in wb.find('m:sheets', ns):
            if sh.get('name').lower() == 'log':
                arquivo = 'xl/' + alvo[sh.get('{%s}id' % ns['r'])]
        if not arquivo:
            return []
        compart = []
        if 'xl/sharedStrings.xml' in zf.namelist():
            for si in ET.fromstring(zf.read('xl/sharedStrings.xml')).findall('m:si', ns):
                compart.append(''.join(t.text or '' for t in si.iter('{%s}t' % ns['m'])))
        linhas = []
        for row in ET.fromstring(zf.read(arquivo)).iter('{%s}row' % ns['m']):
            vals = {}
            for c in row.findall('m:c', ns):
                col = re.match(r'[A-Z]+', c.get('r')).group(0)
                v = c.find('m:v', ns)
                if v is None:
                    is_ = c.find('m:is', ns)
                    vals[col] = ''.join(t.text or '' for t in is_.iter('{%s}t' % ns['m'])) if is_ is not None else None
                    continue
                if c.get('t') == 's':
                    vals[col] = compart[int(v.text)]
                elif c.get('t') == 'str':
                    vals[col] = v.text
                else:
                    try:
                        vals[col] = float(v.text)
                    except ValueError:
                        vals[col] = v.text
            linhas.append(vals)
    base = datetime(1899, 12, 30)
    saida = []
    for v in linhas:
        if not isinstance(v.get('A'), float):
            continue
        dia = v.get('B')
        if isinstance(dia, float):
            dia = (base + timedelta(days=dia)).date()
        else:
            dia = util.para_data(dia)
        hora = v.get('C')
        if isinstance(hora, float):
            seg = round((hora % 1) * 86400)
            hora = '%02d:%02d:%02d' % (seg // 3600, seg % 3600 // 60, seg % 60)
        if not dia:
            continue
        saida.append(('%s %s' % (dia.isoformat(), hora or '00:00:00'), txt(v.get('F')), txt(v.get('E')) or 'Logado',
                      txt(v.get('G')), txt(v.get('H'))))
    return saida


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dump', required=True, help='pasta com os JSON exportados do BD.mdb')
    ap.add_argument('--planilha', help='arquivo .xlsm (para importar o histórico de logins da aba "log")')
    ap.add_argument('--banco', default=os.path.join(RAIZ, 'dados', 'sistema.db'))
    ap.add_argument('--substituir', action='store_true', help='recria o banco mesmo que já tenha dados')
    a = ap.parse_args()

    if os.path.exists(a.banco):
        con = sqlite3.connect(a.banco)
        try:
            n = con.execute('SELECT COUNT(*) FROM clientes').fetchone()[0]
        except sqlite3.Error:
            n = 0
        con.close()
        if n and not a.substituir:
            print('O banco %s já tem %d clientes. Use --substituir para recriá-lo a partir do sistema antigo.' % (a.banco, n))
            sys.exit(2)
        pasta_bkp = os.path.join(os.path.dirname(a.banco), 'backups')
        os.makedirs(pasta_bkp, exist_ok=True)
        destino = os.path.join(pasta_bkp, 'ANTES_DA_IMPORTACAO_%s.db' % datetime.now().strftime('%d-%m-%Y_%H-%M-%S'))
        shutil.copy2(a.banco, destino)
        for suf in ('', '-wal', '-shm'):
            if os.path.exists(a.banco + suf):
                os.remove(a.banco + suf)
        print('Banco anterior guardado em', destino)

    os.makedirs(os.path.dirname(os.path.abspath(a.banco)), exist_ok=True)
    con = sqlite3.connect(a.banco)
    con.executescript(SCHEMA)
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cont = {}

    # Usuários (senhas passam a ser guardadas com hash)
    for u in carregar(a.dump, 'LOGIN'):
        nome = (txt(u.get('USUARIO')) or '').upper()
        if not nome:
            continue
        con.execute('INSERT OR IGNORE INTO usuarios (id, usuario, senha_hash, ativo, admin, criado_em) VALUES (?,?,?,?,?,?)',
                    (u.get('ID'), nome, generate_password_hash(str(u.get('SENHA') or '')),
                     0 if str(u.get('STATUS')) == '0' else 1, 1 if nome == 'SISTEMA' else 0, agora))
    cont['usuários'] = con.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0]

    # Convênios
    conv_id = {}
    conv_por_id_antigo = {}
    for c in carregar(a.dump, 'CADCONVENIO'):
        nome = (txt(c.get('BD_CONVENIO')) or '').upper()
        if not nome:
            continue
        con.execute('INSERT OR IGNORE INTO convenios (id, nome, gera_caixa, valor_mibi, valor_ossea, valor_tgi, '
                    'valor_paratgi, valor_galio) VALUES (?,?,?,?,?,?,?,?)',
                    (c['ID'], nome, 1 if nome in CONVENIOS_CAIXA else 0, c.get('MIBI'), c.get('OSSEA'), c.get('TGI'),
                     c.get('PARATGI'), c.get('GALIO')))
        conv_id[nome] = con.execute('SELECT id FROM convenios WHERE nome=?', (nome,)).fetchone()[0]
        conv_por_id_antigo[str(c['ID'])] = nome

    # Clientes
    clientes = {}
    for c in carregar(a.dump, 'CADCLIENTE'):
        nome = txt(c.get('BD_NOME'))
        if not nome:
            avisos.append('Cliente %s sem nome — ignorado.' % c.get('ID'))
            continue
        convenio = (txt(c.get('BD_CONVENIO')) or '').upper() or None
        if convenio and convenio not in conv_id:
            con.execute('INSERT OR IGNORE INTO convenios (nome, gera_caixa) VALUES (?,?)',
                        (convenio, 1 if convenio in CONVENIOS_CAIXA else 0))
            conv_id[convenio] = con.execute('SELECT id FROM convenios WHERE nome=?', (convenio,)).fetchone()[0]
            avisos.append('Convênio "%s" usado em clientes não existia no cadastro — criado.' % convenio)
        registro = (c['ID'], nome.upper(), txt(c.get('BD_CPF')), txt(c.get('BD_RUA')), txt(c.get('BD_NUMERO')),
                    txt(c.get('BD_COMPLEMENTO')), txt(c.get('BD_BAIRRO')), txt(c.get('BD_CIDADE')),
                    (txt(c.get('BD_UF')) or '').upper() or None, txt(c.get('BD_CONTATO')), conv_id.get(convenio), convenio,
                    txt(c.get('BD_NOMEMAE')), data(c.get('BD_DATANAC'), 'nascimento', 'cliente %s' % c['ID']),
                    txt(c.get('BD_CARTAOCONV')), txt(c.get('BD_PROFISSAO')), data(c.get('BD_DATACAD')), agora)
        con.execute('INSERT INTO clientes (id, nome, cpf, rua, numero, complemento, bairro, cidade, uf, contato, '
                    'convenio_id, convenio, nome_mae, data_nasc, cartao_convenio, profissao, criado_em, atualizado_em) '
                    'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', registro)
        clientes[c['ID']] = {'convenio': convenio, 'cpf': txt(c.get('BD_CPF')), 'nome': nome.upper()}
    cont['clientes'] = len(clientes)
    por_cpf = {}
    por_nome = {}
    for cid, c in clientes.items():
        if c['cpf']:
            por_cpf.setdefault(c['cpf'], cid)
        por_nome.setdefault(c['nome'], cid)

    # Médicos
    for m in carregar(a.dump, 'CADMEDICO'):
        nome = (txt(m.get('BD_MEDICO')) or '').upper()
        if nome:
            con.execute('INSERT INTO medicos (id, nome, crm) VALUES (?,?,?)', (m['ID'], nome, txt(m.get('BD_CRM'))))
    cont['médicos'] = con.execute('SELECT COUNT(*) FROM medicos').fetchone()[0]

    # Atendimentos (LANCAMENTO)
    n = 0
    for l in carregar(a.dump, 'LANCAMENTO'):
        idcli = txt(l.get('BD_IDCLI'))
        cid = int(idcli) if idcli and idcli.isdigit() else None
        if cid not in clientes:
            cid2 = por_cpf.get(txt(l.get('BD_CPF')))
            if cid is not None and not cid2:
                avisos.append('Atendimento %s: cliente %s não existe mais no cadastro (mantido com o nome).' % (l['ID'], idcli))
            cid = cid2 or cid
        idconv = (txt(l.get('ID_CONVENIO')) or '').split(' ')[0]
        convenio = conv_por_id_antigo.get(idconv) or (clientes.get(cid) or {}).get('convenio')
        con.execute('INSERT INTO atendimentos (id, cliente_id, cliente_nome, cpf, medico, data, exame, convenio, criado_em) '
                    'VALUES (?,?,?,?,?,?,?,?,?)',
                    (l['ID'], cid, (txt(l.get('BD_CLIENTE')) or '').upper(), txt(l.get('BD_CPF')),
                     (txt(l.get('BD_MEDICO')) or '').upper() or None, data(l.get('BD_DATA'), 'data do atendimento', l['ID']),
                     (txt(l.get('BD_EXAME')) or '').upper() or None, convenio, agora))
        n += 1
    cont['atendimentos'] = n

    # Protocolo de guias
    n = 0
    for gd in carregar(a.dump, 'PROTOCOLOGUIAS'):
        con.execute('INSERT INTO guias (id, paciente, convenio, data, exame, horario) VALUES (?,?,?,?,?,?)',
                    (gd['ID'], (txt(gd.get('PACIENTE')) or '').upper(), (txt(gd.get('CONVENIO')) or '').upper() or None,
                     data(gd.get('DATA'), 'data da guia', gd['ID']), (txt(gd.get('EXAME')) or '').upper() or None,
                     txt(gd.get('HORARIO'))))
        n += 1
    cont['guias'] = n

    # Caixa
    n = 0
    for c in carregar(a.dump, 'CAIXA'):
        con.execute('INSERT INTO caixa (id, data, cliente, cpf, procedimento, convenio, status, usuario, nota_fiscal) '
                    'VALUES (?,?,?,?,?,?,?,?,?)',
                    (c['ID'], data(c.get('BDDATA'), 'data do caixa', c['ID']), (txt(c.get('BDCLIENTE')) or '').upper(),
                     txt(c.get('BDCPF')), (txt(c.get('BDPROCEDIMENTO')) or '').upper(), (txt(c.get('BDCONVENIO')) or '').upper(),
                     (txt(c.get('BDSTATUS')) or 'ABERTO').upper(), txt(c.get('BDUSUARIO')), txt(c.get('NOTA_FISCAL'))))
        n += 1
    cont['caixa'] = n

    # Medicamentos (doses)
    n = 0
    for m in carregar(a.dump, 'MEDICAMENTOS'):
        pac = (txt(m.get('PACIENTE')) or '').upper()
        cpf = txt(m.get('CPF'))
        cid = por_cpf.get(cpf) or por_nome.get(pac)
        con.execute('INSERT INTO doses (id, cliente_id, paciente, data_nasc, contato, cpf, idade, medicamento, mci, preparo, '
                    'dieta, susp_medicacao, data_dose, status, obs, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (m['ID'], cid, pac, data(m.get('DATANASC'), 'nascimento (dose)', m['ID']), txt(m.get('CONTATO')), cpf,
                     txt(m.get('IDADE')), (txt(m.get('MEDICAMENTO')) or '').upper(), txt(m.get('MCI')), txt(m.get('PREPARO')),
                     data(m.get('DIETA'), 'dieta', m['ID']), data(m.get('SUSPMEDICACAO'), 'suspensão', m['ID']),
                     data(m.get('DATADOSE'), 'data da dose', m['ID']), (txt(m.get('STATUS')) or 'AGENDADO').upper(),
                     txt(m.get('OBS')), agora))
        n += 1
    cont['doses de medicamentos'] = n

    # Contas a pagar
    n = 0
    for c in carregar(a.dump, 'CONTASAPAGAR'):
        status = (txt(c.get('STATUS')) or 'ABERTO').upper()
        con.execute('INSERT INTO contas (id, descricao, categoria, vencimento, valor, obs, status, banco_pagamento, '
                    'forma_pagamento, fornecedor, nota_fiscal) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (c['ID'], (txt(c.get('DESCRIÇÃO')) or '').upper(), txt(c.get('CATEGORIA')),
                     data(c.get('VENCIMENTO'), 'vencimento', c['ID']), c.get('VALOR'), txt(c.get('OBS')), status,
                     txt(c.get('PGT BANCO')), txt(c.get('FORMAPGT')), txt(c.get('FORNECEDOR')), txt(c.get('NOTAFISCAL'))))
        n += 1
    cont['contas a pagar'] = n

    # Histórico de logins (aba "log" da planilha)
    if a.planilha:
        log = ler_log_planilha(a.planilha)
        con.executemany('INSERT INTO acessos (data_hora, usuario, evento, computador, detalhe) VALUES (?,?,?,?,?)', log)
        cont['acessos (log)'] = len(log)

    for tabela in ('BDLANÇAMENTO', 'CADCHECKLIST', 'CONV_EXAME_VALOR', 'ORÇAMENTO', 'PROTOCOLOGUIAS1', 'Cópia de CAIXA'):
        if carregar(a.dump, tabela):
            avisos.append('A tabela %s tem dados que não foram importados (não é usada pelo sistema).' % tabela)

    con.commit()
    con.close()
    inicializar(a.banco)  # exames padrão, configurações e usuário admin se não houver usuários

    print('\nImportação concluída em', a.banco)
    for k, v in cont.items():
        print('  %-22s %6d' % (k, v))
    avisos_filtrados = [x for x in avisos if 'não encontrada na exportação' not in x or 'LOGIN' in x or 'CADCLIENTE' in x]
    if avisos_filtrados:
        print('\nAvisos (%d):' % len(avisos_filtrados))
        for x in avisos_filtrados[:200]:
            print('  -', x)
        if len(avisos_filtrados) > 200:
            print('  ... e mais %d' % (len(avisos_filtrados) - 200))


if __name__ == '__main__':
    main()
