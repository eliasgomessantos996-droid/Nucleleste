"""Gera um banco de TESTE com volume enorme de dados sintéticos, para o teste de sobrecarga.

Nunca usa dados reais (LGPD) e nunca toca na instalação real: recusa qualquer pasta dentro de C:\\ProgramData\\Nucleleste ou a
pasta dados/ do projeto. Insere direto no SQLite (sem passar por HTTP), em lotes, com datas espalhadas em 5 anos e
distribuições parecidas com as reais (poucos exames concentram a maior parte do volume, faltas variam por convênio).

Uso:
    python ferramentas/gerar_carga.py --pasta %TEMP%\\nucleleste_carga --escala M
Escalas (linhas no total, aproximado): S = 100 mil · M = 2 milhões · L = 20 milhões · XL = 50 milhões.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

ESCALAS = {'S': 100_000, 'M': 2_000_000, 'L': 20_000_000, 'XL': 50_000_000}
# fatia de cada tabela no total de linhas
FATIAS = {'clientes': .10, 'atendimentos': .18, 'realizacoes': .18, 'agenda_horarios': .25, 'auditoria': .15, 'chat_mensagens': .06,
          'caixa': .04, 'acessos': .02, 'contas': .01, 'faturas': .003, 'cq_ocorrencias': .004, 'cq_pesquisas': .003}
BYTES_POR_LINHA = 230          # estimativa conservadora (dados + índices), conferida na escala M
FOLGA_DISCO = 8 * 1024 ** 3    # deixa pelo menos 8 GB livres no disco

NOMES = ('MARIA', 'JOSE', 'ANA', 'JOAO', 'ANTONIO', 'FRANCISCA', 'CARLOS', 'PAULO', 'LUCAS', 'ADRIANA', 'JULIANA', 'MARCOS', 'PATRICIA',
         'ALINE', 'SANDRA', 'RAFAEL', 'BRUNO', 'CAMILA', 'FERNANDA', 'PEDRO', 'LUIZ', 'RITA', 'SEBASTIAO', 'TEREZA', 'RAIMUNDO')
SOBRENOMES = ('SILVA', 'SANTOS', 'OLIVEIRA', 'SOUZA', 'RODRIGUES', 'FERREIRA', 'ALVES', 'PEREIRA', 'LIMA', 'GOMES', 'COSTA', 'RIBEIRO',
              'MARTINS', 'CARVALHO', 'ALMEIDA', 'LOPES', 'SOARES', 'FERNANDES', 'VIEIRA', 'BARBOSA', 'ROCHA', 'DIAS', 'NASCIMENTO')
EXAMES = (('CINTILOGRAFIA ÓSSEA', 30), ('CINTILOGRAFIA MIOCÁRDICA (MIBI)', 25), ('PET-CT', 15), ('CINTILOGRAFIA DE TIREOIDE', 10),
          ('CINTILOGRAFIA RENAL (DMSA)', 6), ('PESQUISA DE CORPO INTEIRO', 5), ('CINTILOGRAFIA PULMONAR', 4), ('ESVAZIAMENTO GÁSTRICO', 2),
          ('CINTILOGRAFIA DE PARATIREOIDES', 2), ('LINFOCINTILOGRAFIA', 1))
CONVENIOS = (('SUS', 30, .16), ('UNIMED', 25, .09), ('BRADESCO SAÚDE', 12, .07), ('PARTICULAR', 10, .04), ('CASSI', 8, .08),
             ('GEAP', 7, .11), ('SULAMÉRICA', 5, .06), ('UNACON', 3, .13))
MEDICOS = tuple('DR(A). %s %s' % (n, s) for n, s in zip(NOMES[::2], SOBRENOMES[::2]))
CIDADES = ('VITÓRIA DA CONQUISTA', 'ITAPETINGA', 'BRUMADO', 'JEQUIÉ', 'GUANAMBI', 'POÇÕES', 'BARRA DO CHOÇA', 'ANAGÉ')
USUARIOS_CARGA = 600
SENHA_CARGA = 'carga123'
ACOES = ('Salvou atendimento', 'Mudou o status na agenda', 'Editou cliente', 'Lançou exame realizado', 'Recebeu pagamento', 'Gerou relatório')
MODULOS = ('Atendimentos', 'Agenda de exames', 'Clientes', 'Lançamento de exames', 'Caixa', 'Relatórios')


def proteger(pasta):
    alvo = os.path.normcase(os.path.abspath(pasta))
    proibidas = [os.path.normcase(os.path.abspath(p)) for p in (r'C:\ProgramData\Nucleleste', os.path.join(RAIZ, 'dados'))]
    for p in proibidas:
        if alvo == p or alvo.startswith(p + os.sep):
            raise SystemExit('Recusado: %s é a instalação real ou os dados do projeto. Use uma pasta só de teste.' % pasta)


def escolher(itens):
    """random.choices pré-calculado: lista de (valor, peso)."""
    valores = [v for v, *_ in itens]
    pesos = [p for _v, p, *_ in itens]
    return lambda k=1: random.choices(valores, pesos, k=k)


def lotes(gerador, tamanho=50_000):
    lote = []
    for linha in gerador:
        lote.append(linha)
        if len(lote) >= tamanho:
            yield lote
            lote = []
    if lote:
        yield lote


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pasta', required=True)
    ap.add_argument('--escala', choices=ESCALAS, default='S')
    ap.add_argument('--semente', type=int, default=2026)
    ap.add_argument('--limpar', action='store_true', help='apaga a pasta de teste antes de gerar')
    a = ap.parse_args()
    proteger(a.pasta)
    total = ESCALAS[a.escala]
    os.makedirs(a.pasta, exist_ok=True)
    livre = shutil.disk_usage(a.pasta).free
    estimado = total * BYTES_POR_LINHA
    if livre - estimado < FOLGA_DISCO:
        raise SystemExit('Espaço insuficiente: precisa de ~%.1f GB e o disco tem %.1f GB livres (folga mínima de %d GB).'
                         % (estimado / 1024 ** 3, livre / 1024 ** 3, FOLGA_DISCO // 1024 ** 3))
    banco = os.path.join(a.pasta, 'sistema.db')
    if a.limpar:
        for nome in ('sistema.db', 'sistema.db-wal', 'sistema.db-shm', 'anexos.db', 'anexos.db-wal', 'anexos.db-shm'):
            if os.path.exists(os.path.join(a.pasta, nome)):
                os.remove(os.path.join(a.pasta, nome))
    from app import db as dbmod
    from app import qualidade
    from werkzeug.security import generate_password_hash
    dbmod.inicializar(banco)
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    qualidade.garantir(con)
    con.execute('PRAGMA journal_mode=OFF')
    con.execute('PRAGMA synchronous=OFF')
    con.execute('PRAGMA cache_size=-400000')
    random.seed(a.semente)
    n = {t: max(10, int(total * f)) for t, f in FATIAS.items()}
    hoje = date.today()
    inicio = hoje - timedelta(days=5 * 365)
    dias = (hoje - inicio).days
    exame = escolher(EXAMES)
    conv = escolher(CONVENIOS)
    falta_conv = {c: t for c, _p, t in CONVENIOS}
    t0 = time.time()

    def dia_aleatorio():
        return inicio + timedelta(days=random.randrange(dias))

    def nome():
        return '%s %s %s' % (random.choice(NOMES), random.choice(SOBRENOMES), random.choice(SOBRENOMES))

    def relatar(tabela, qtd):
        print('  %-18s %12s linhas  (%.0f s)' % (tabela, format(qtd, ',').replace(',', '.'), time.time() - t0), flush=True)

    # usuários do teste de carga (a mesma senha para todos; o hash é calculado uma vez)
    hash_carga = generate_password_hash(SENHA_CARGA)
    todos = json.dumps(['dashboard', 'atendimentos', 'agenda', 'clientes', 'caixa', 'movimento_caixa', 'exames_lanc', 'laudos', 'ona',
                        'qualidade_gestao', 'qualidade_fornecedores', 'registros', 'contas', 'faturamento'])
    con.executemany('INSERT OR IGNORE INTO usuarios (usuario, senha_hash, admin, ativo, modulos, criado_em) VALUES (?,?,?,?,?,?)',
                    [('CARGA%03d' % i, hash_carga, 1 if i < 5 else 0, 1, todos, dbmod.agora()) for i in range(USUARIOS_CARGA)])
    con.commit()
    uids = [r[0] for r in con.execute("SELECT id FROM usuarios WHERE usuario LIKE 'CARGA%'")]
    relatar('usuarios', len(uids))

    # clientes
    def g_cli():
        for i in range(n['clientes']):
            c = conv()[0]
            yield (nome(), '%011d' % random.randrange(10 ** 11), '45%06d' % random.randrange(10 ** 6), 'RUA %s' % random.choice(SOBRENOMES),
                   str(random.randrange(1, 2000)), random.choice(CIDADES), 'BA', '77 9%08d' % random.randrange(10 ** 8), c,
                   nome(), (hoje - timedelta(days=random.randrange(365 * 5, 365 * 95))).isoformat(), random.choice('MF'), dbmod.agora())
    for lote in lotes(g_cli()):
        con.executemany('INSERT INTO clientes (nome, cpf, cep, rua, numero, cidade, uf, contato, convenio, nome_mae, data_nasc, sexo, criado_em) '
                        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', lote)
    con.commit()
    max_cli = con.execute('SELECT MAX(id) FROM clientes').fetchone()[0]
    relatar('clientes', n['clientes'])

    # atendimentos e exames realizados (com laudo)
    def g_at():
        for i in range(n['atendimentos']):
            d = dia_aleatorio().isoformat()
            yield (random.randrange(1, max_cli + 1), nome(), random.choice(MEDICOS), d, exame()[0], conv()[0],
                   'CARGA%03d' % random.randrange(USUARIOS_CARGA), d + ' 08:00:00')
    for lote in lotes(g_at()):
        con.executemany('INSERT INTO atendimentos (cliente_id, cliente_nome, medico, data, exame, convenio, usuario, criado_em) '
                        'VALUES (?,?,?,?,?,?,?,?)', lote)
    con.commit()
    relatar('atendimentos', n['atendimentos'])

    def g_real():
        for i in range(n['realizacoes']):
            d = dia_aleatorio()
            hora = '%02d:%02d' % (random.randrange(7, 17), random.choice((0, 20, 40)))
            ini = datetime.fromisoformat('%s %s:00' % (d.isoformat(), hora))
            lib = ini + timedelta(hours=random.choice((2, 4, 8, 12, 18, 20, 23, 26, 30, 48, 72)))
            ent = lib + timedelta(hours=random.randrange(1, 96))
            presc = random.choice((10, 15, 20, 25, 30))
            adm = presc * random.uniform(.85, 1.12)
            liberado = lib < datetime.now()
            yield (d.isoformat(), random.randrange(1, max_cli + 1), nome(), random.choice('MF'),
                   (d - timedelta(days=random.randrange(365 * 5, 365 * 95))).isoformat(), conv()[0], random.choice(MEDICOS), exame()[0],
                   '%d mCi' % presc, ('%.1f mCi' % adm).replace('.', ','), hora, hora,
                   lib.strftime('%Y-%m-%d %H:%M:%S') if liberado else None, ent.strftime('%Y-%m-%d %H:%M:%S') if liberado else None,
                   'LIBERADO' if liberado else 'LAUDANDO', ini.strftime('%Y-%m-%d %H:%M:%S'), ini.strftime('%Y-%m-%d %H:%M:%S'))
    for lote in lotes(g_real()):
        con.executemany('INSERT INTO realizacoes (data, cliente_id, paciente, sexo, data_nasc, convenio, medico, exame, ativ_prescrita, '
                        'ativ_administrada, hora_injecao, hora_exame, laudo_liberado_em, laudo_entregue_em, laudo_situacao, criado_em, atualizado_em) '
                        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', lote)
    con.commit()
    relatar('realizacoes', n['realizacoes'])

    # agenda: uma agenda por exame por dia útil, com os horários distribuídos
    nomes_exame = [e for e, _ in EXAMES]
    agendas = []
    d = inicio
    while d <= hoje + timedelta(days=60):
        if d.weekday() < 5:
            for ex in nomes_exame:
                agendas.append((d.isoformat(), ex, '07:00', 20, 1, 'carga', dbmod.agora()))
        d += timedelta(days=1)
    con.executemany('INSERT INTO agenda_exames (data, exame, inicio, intervalo, vagas, criado_por, criado_em) VALUES (?,?,?,?,?,?,?)', agendas)
    con.commit()
    ag_ids = [(r[0], r[1]) for r in con.execute('SELECT id, data FROM agenda_exames')]
    relatar('agenda_exames', len(ag_ids))

    def g_hor():
        por_agenda = max(1, n['agenda_horarios'] // len(ag_ids))
        sobra = n['agenda_horarios'] - por_agenda * len(ag_ids)
        hoje_iso = hoje.isoformat()
        for k, (aid, dia) in enumerate(ag_ids):
            qtd = por_agenda + (1 if k < sobra else 0)
            for i in range(qtd):
                c = conv()[0]
                if dia > hoje_iso:
                    st = 'AGENDADO'
                else:
                    r = random.random()
                    taxa = falta_conv[c]
                    st = 'FALTOU' if r < taxa else 'REMARCOU' if r < taxa + .03 else 'RESGATADO' if r < taxa + .05 else 'VEIO'
                livre = random.random() < .08
                yield (aid, '%02d:%02d' % (7 + (i * 20) // 60 % 12, (i * 20) % 60), i, '' if livre else nome(), '' if livre else c,
                       '' if livre else '77 9%08d' % random.randrange(10 ** 8), 'AGENDADO' if livre else st)
    for lote in lotes(g_hor()):
        con.executemany('INSERT INTO agenda_horarios (agenda_id, hora, ordem, paciente, convenio, contato, status) VALUES (?,?,?,?,?,?,?)', lote)
    con.commit()
    relatar('agenda_horarios', n['agenda_horarios'])

    # registro de atividades e acessos
    def g_aud():
        for i in range(n['auditoria']):
            dt = datetime.combine(dia_aleatorio(), datetime.min.time()) + timedelta(seconds=random.randrange(8 * 3600, 18 * 3600))
            k = random.randrange(len(ACOES))
            yield (dt.strftime('%Y-%m-%d %H:%M:%S'), 'CARGA%03d' % random.randrange(USUARIOS_CARGA), MODULOS[k], ACOES[k],
                   'registro sintético %d' % i, '/carga', '10.0.0.%d' % random.randrange(2, 250))
    for lote in lotes(g_aud()):
        con.executemany('INSERT INTO auditoria (data_hora, usuario, modulo, acao, detalhe, rota, ip) VALUES (?,?,?,?,?,?,?)', lote)
    con.commit()
    relatar('auditoria', n['auditoria'])

    def g_ace():
        for i in range(n['acessos']):
            dt = datetime.combine(dia_aleatorio(), datetime.min.time()) + timedelta(seconds=random.randrange(7 * 3600, 19 * 3600))
            yield (dt.strftime('%Y-%m-%d %H:%M:%S'), 'CARGA%03d' % random.randrange(USUARIOS_CARGA), random.choice(('Entrou', 'Saiu')),
                   'PC-%02d' % random.randrange(30), '')
    for lote in lotes(g_ace()):
        con.executemany('INSERT INTO acessos (data_hora, usuario, evento, computador, detalhe) VALUES (?,?,?,?,?)', lote)
    con.commit()
    relatar('acessos', n['acessos'])

    # mensagens entre os usuários de carga
    def g_chat():
        for i in range(n['chat_mensagens']):
            a_, b_ = random.sample(uids, 2)
            dt = datetime.combine(dia_aleatorio(), datetime.min.time()) + timedelta(seconds=random.randrange(8 * 3600, 18 * 3600))
            ts = dt.strftime('%Y-%m-%d %H:%M:%S')
            yield (a_, b_, 'Mensagem de teste %d sobre o paciente das %02dh' % (i, dt.hour), ts, ts if random.random() < .97 else None)
    for lote in lotes(g_chat()):
        con.executemany('INSERT INTO chat_mensagens (de_id, para_id, corpo, criado_em, lida_em) VALUES (?,?,?,?,?)', lote)
    con.commit()
    relatar('chat_mensagens', n['chat_mensagens'])

    def g_caixa():
        for i in range(n['caixa']):
            d = dia_aleatorio().isoformat()
            yield (d, nome(), exame()[0], 'PARTICULAR', random.choice(('PAGO', 'PAGO', 'PAGO', 'ABERTO')), 'CARGA%03d' % random.randrange(USUARIOS_CARGA),
                   str(1000 + i), random.choice((450.0, 950.0, 1290.0, 1295.0, 3200.0)), random.choice(('DINHEIRO', 'PIX')))
    for lote in lotes(g_caixa()):
        con.executemany('INSERT INTO caixa (data, cliente, procedimento, convenio, status, usuario, nota_fiscal, valor, forma_pagamento) '
                        'VALUES (?,?,?,?,?,?,?,?,?)', lote)
    con.commit()
    relatar('caixa', n['caixa'])

    # fornecedores, contas, faturas, ocorrências, pesquisas e avaliações de fornecedor
    con.executemany('INSERT INTO fornecedores (cnpj, nome, ativo, criado_em, criado_por) VALUES (?,?,1,?,?)',
                    [('%014d' % (10 ** 13 + i), 'FORNECEDOR SINTÉTICO %04d LTDA' % i, dbmod.agora(), 'carga') for i in range(800)])
    fids = [r[0] for r in con.execute('SELECT id FROM fornecedores')]

    def g_contas():
        for i in range(n['contas']):
            v = dia_aleatorio()
            pago = v < hoje and random.random() < .93
            yield ('COMPRA %d' % i, random.choice(('Material de escritório', 'Radiofármacos', 'Manutenção', 'Serviços')), v.isoformat(),
                   round(random.uniform(50, 25000), 2), 'PAGO' if pago else 'ABERTO', random.choice(fids),
                   (v + timedelta(days=random.choice((-2, 0, 0, 0, 1, 5)))).isoformat() if pago else None)
    for lote in lotes(g_contas()):
        con.executemany('INSERT INTO contas (descricao, categoria, vencimento, valor, status, fornecedor_id, data_pagamento) VALUES (?,?,?,?,?,?,?)', lote)

    def g_fat():
        for i in range(n['faturas']):
            p = dia_aleatorio()
            liq = round(random.uniform(5000, 300000), 2)
            rec = p < hoje - timedelta(days=30)
            yield (conv()[0], p.strftime('%m/%Y'), liq, liq, p.isoformat(), 'RECEBIDO' if rec else 'ABERTO',
                   (p + timedelta(days=random.choice((0, 3, 10, 40)))).isoformat() if rec else None,
                   round(liq * random.uniform(.9, 1.0), 2) if rec else None, dbmod.agora())
    for lote in lotes(g_fat()):
        con.executemany('INSERT INTO faturas (convenio, referencia, valor_bruto, valor_liquido, previsao, status, data_recebimento, valor_recebido, '
                        'criado_em) VALUES (?,?,?,?,?,?,?,?,?)', lote)
    from app.qualidade import GRAVIDADES, TIPOS_OCORRENCIA

    def g_oc():
        for i in range(n['cq_ocorrencias']):
            yield (dia_aleatorio().isoformat(), random.choice(TIPOS_OCORRENCIA), random.choice(('Recepção', 'Exames', 'Laudo', 'Faturamento')),
                   exame()[0], conv()[0], 'Ocorrência sintética %d' % i, random.choice(GRAVIDADES), 'ENCERRADA', 'carga', dbmod.agora())
    for lote in lotes(g_oc()):
        con.executemany('INSERT INTO cq_ocorrencias (data, tipo, setor, exame, convenio, descricao, gravidade, status, criado_por, criado_em) '
                        'VALUES (?,?,?,?,?,?,?,?,?,?)', lote)

    def g_pq():
        for i in range(n['cq_pesquisas']):
            yield (dia_aleatorio().isoformat(), random.choice((10, 10, 10, 9, 9, 8, 7, 6, 3)), exame()[0], '', 'carga', dbmod.agora())
    for lote in lotes(g_pq()):
        con.executemany('INSERT INTO cq_pesquisas (data, nota, exame, comentario, criado_por, criado_em) VALUES (?,?,?,?,?,?)', lote)
    con.commit()
    relatar('financeiro/qualidade', n['contas'] + n['faturas'] + n['cq_ocorrencias'] + n['cq_pesquisas'])

    con.execute('PRAGMA journal_mode=WAL')
    con.execute('ANALYZE')
    con.commit()
    con.close()
    tamanho = sum(os.path.getsize(os.path.join(a.pasta, f)) for f in os.listdir(a.pasta) if f.startswith('sistema.db'))
    linhas = sum(n.values()) + len(ag_ids)
    resumo = {'escala': a.escala, 'linhas': linhas, 'por_tabela': n, 'segundos': round(time.time() - t0, 1),
              'tamanho_mb': round(tamanho / 1024 ** 2, 1), 'bytes_por_linha': round(tamanho / max(1, linhas), 1),
              'usuarios': 'CARGA000 a CARGA%03d (senha %s)' % (USUARIOS_CARGA - 1, SENHA_CARGA)}
    with open(os.path.join(a.pasta, 'carga_resumo.json'), 'w', encoding='utf-8') as fh:
        json.dump(resumo, fh, ensure_ascii=False, indent=1)
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
