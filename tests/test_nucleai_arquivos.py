"""Testes da ETAPA 5: envio de arquivos à NucleAI (.xlsx, .xls, .csv, .txt), validação por conteúdo,
isolamento por conversa/usuário, limpeza ao apagar conversa, arquivo_ler, arquivo_agrupar e fluxo com ilustrar + Excel."""
import io
import json
import sqlite3
import struct
import unittest

from openpyxl import Workbook, load_workbook

from app import ajuda, anexos, chat
from app import nucleai_arquivos as arq
from app import nucleai_conhecimento as conh
from app import nucleai_ferramentas as ferr
from app import nucleai_ia as ia
from app import nucleai_motor as motor
from tests.test_nucleai_motor import MotorBase, OpenRouter


def _fazer_xlsx(linhas, aba='MIBIs'):
    wb = Workbook()
    ws = wb.active
    ws.title = aba
    for row in linhas:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


def _fazer_xls(linhas, titulo='Planilha'):
    """Gera um .xls BIFF5 válido em memória (sem depender de xlwt)."""
    def record(code, content):
        return struct.pack('<HH', code, len(content)) + content

    def bof(kind):
        return record(0x0809, struct.pack('<HHHH', 0x0500, kind, 0x096C, 0x07C9))

    nome = titulo.encode('cp1252')
    prefix = bof(0x0005) + record(0x0042, struct.pack('<H', 1252))
    boundsheet_dummy = record(0x0085, struct.pack('<IBBB', 0, 0, 0, len(nome)) + nome)
    globals_len = len(prefix + boundsheet_dummy + record(0x000A, b''))
    globals_stream = prefix + record(0x0085, struct.pack('<IBBB', globals_len, 0, 0, len(nome)) + nome) + record(0x000A, b'')
    ncols = max((len(r) for r in linhas), default=1)
    sheet = bof(0x0010) + record(0x0200, struct.pack('<HHHHH', 0, len(linhas), 0, ncols, 0))
    for r_idx, row in enumerate(linhas):
        for c_idx, val in enumerate(row):
            if isinstance(val, (int, float)):
                sheet += record(0x0203, struct.pack('<HHHd', r_idx, c_idx, 0, float(val)))
            else:
                enc = str(val).encode('cp1252')
                sheet += record(0x0204, struct.pack('<HHHH', r_idx, c_idx, 0, len(enc)) + enc)
    return globals_stream + sheet + record(0x000A, b'')


class NucleaiArquivosTestes(MotorBase):
    def setUp(self):
        super().setUp()
        self.con.execute('DELETE FROM nucleai_ilustracoes')
        self.con.commit()
        ia.definir(self.con, 'nucleai_llm_chave', 'sk-teste')
        self.liberar((self.func, ferr.LEVE), (self.admin, ferr.MAX))
        self.bot = ajuda.bot_id(self.con)

    def _iniciar_nucleai(self, cli):
        r = self.post(cli, '/ajuda/iniciar', {})
        self.assertIn(r.status_code, (200, 302), self.texto(r))

    def _enviar_arquivo(self, cli, para, conteudo, nome, corpo=''):
        return self.post(
            cli,
            '/mensagens/enviar',
            {'para': str(para), 'corpo': corpo, 'arquivo': (io.BytesIO(conteudo), nome)},
            headers={'Accept': 'application/json'},
            content_type='multipart/form-data',
        )

    def _contar_anexos_ia(self):
        caminho = anexos.caminho_ao_lado(self.app.config['DATABASE'])
        con = sqlite3.connect(caminho)
        try:
            return con.execute("SELECT COUNT(*) FROM anexos WHERE origem=?", (arq.ORIGEM_ANEXO,)).fetchone()[0]
        finally:
            con.close()

    def test_xlsx_leitura_e_agrupamento_mibi(self):
        dados = _fazer_xlsx([
            ['Data', 'Paciente', 'Fase', 'Convênio', 'Resultado', 'Valor'],
            ['2026-10-05', 'Ana', 'Repouso', 'Unimed', 'Normal', 450.0],
            ['2026-10-12', 'Bruno', 'Estresse', 'Unimed', 'Isquemia', 550.0],
            ['2026-10-20', 'Carla', 'Repouso', 'Particular', 'Normal', 600.0],
            ['2026-11-03', 'Davi', 'Estresse', 'Particular', 'Normal', 700.0],
        ])
        cli = self.cliente('IA_REC', 'senha123')
        self._iniciar_nucleai(cli)
        antes = self._contar_anexos_ia()
        motor.BAIXAR = OpenRouter('Arquivo recebido. <<confianca:5>>')
        r = self._enviar_arquivo(cli, self.bot, dados, 'mibis.xlsx', corpo='Analise esta planilha')
        self.assertEqual(r.status_code, 200, self.texto(r))
        msg = r.get_json()['mensagem']
        self.assertIsNone(msg['imagem'])
        self.assertEqual(msg['arquivo']['nome'], 'mibis.xlsx')
        self.assertEqual(self._contar_anexos_ia(), antes + 1)

        ctx = ferr.contexto(self.con, self.func)
        res_ler = json.loads(ferr.chamar(ctx, 'arquivo_ler', {})['resumo'])
        self.assertEqual(res_ler['total_linhas'], 4)
        self.assertEqual([c['nome'] for c in res_ler['colunas']], ['Data', 'Paciente', 'Fase', 'Convênio', 'Resultado', 'Valor'])
        tipos = {c['nome']: c['tipo'] for c in res_ler['colunas']}
        self.assertEqual((tipos['Data'], tipos['Valor'], tipos['Fase']), ('data', 'numero', 'texto'))

        # Agrupar por Fase (contar, soma, média)
        res_fase = json.loads(ferr.chamar(ctx, 'arquivo_agrupar', {
            'agrupar_por': ['Fase'],
            'operacoes': [
                {'op': 'contar', 'rotulo': 'Qtd'},
                {'op': 'soma', 'coluna': 'Valor', 'rotulo': 'Total'},
                {'op': 'media', 'coluna': 'Valor', 'rotulo': 'Média'},
            ],
            'ordenar': 'grupo',
        })['resumo'])
        self.assertEqual(res_fase['colunas'], ['Fase', 'Qtd', 'Total', 'Média'])
        self.assertEqual(res_fase['linhas'], [
            ['Estresse', 2, 1250, 625],
            ['Repouso', 2, 1050, 525],
        ])

        # Agrupar por mês + filtro de data
        res_mes = json.loads(ferr.chamar(ctx, 'arquivo_agrupar', {
            'agrupar_por': ['Data'],
            'granularidade_data': 'mes',
            'filtros': [{'coluna': 'Data', 'op': 'data_entre', 'valor': '01/10/2026', 'valor_fim': '31/10/2026'}],
        })['resumo'])
        self.assertEqual(res_mes['total_filtrado'], 3)
        self.assertEqual(res_mes['linhas'], [['2026-10', 3]])

        # Filtros igual e contem
        res_conv = json.loads(ferr.chamar(ctx, 'arquivo_agrupar', {
            'agrupar_por': ['Convênio'],
            'filtros': [{'coluna': 'Resultado', 'op': 'contem', 'valor': 'norm'}],
        })['resumo'])
        self.assertEqual(res_conv['total_filtrado'], 3)

    def test_xls_csv_e_txt(self):
        cli = self.cliente('IA_REC', 'senha123')
        self._iniciar_nucleai(cli)
        motor.BAIXAR = OpenRouter('Ok. <<confianca:5>>', 'Ok. <<confianca:5>>', 'Ok. <<confianca:5>>')

        # 1) .xls
        xls_bytes = _fazer_xls([
            ['Fase', 'Valor'],
            ['Repouso', 300],
            ['Estresse', 500],
            ['Repouso', 400],
        ])
        r1 = self._enviar_arquivo(cli, self.bot, xls_bytes, 'mibi.xls', corpo='Veja xls')
        self.assertEqual(r1.status_code, 200, self.texto(r1))
        ctx = ferr.contexto(self.con, self.func)
        g1 = json.loads(ferr.chamar(ctx, 'arquivo_agrupar', {
            'anexo_id': r1.get_json()['mensagem']['id'],
            'agrupar_por': ['Fase'],
            'operacoes': [{'op': 'contar'}, {'op': 'soma', 'coluna': 'Valor'}],
        })['resumo'])
        self.assertEqual(g1['linhas'], [['Repouso', 2, 700], ['Estresse', 1, 500]])

        # 2) .csv com ponto e vírgula
        csv_bytes = 'Exame;Convênio;Valor\nMIBI;Unimed;450,50\nMIBI;SUS;200,00\n'.encode('utf-8')
        r2 = self._enviar_arquivo(cli, self.bot, csv_bytes, 'dados.csv', corpo='Veja csv')
        self.assertEqual(r2.status_code, 200, self.texto(r2))
        g2 = json.loads(ferr.chamar(ctx, 'arquivo_agrupar', {
            'anexo_id': r2.get_json()['mensagem']['id'],
            'agrupar_por': ['Convênio'],
            'operacoes': [{'op': 'soma', 'coluna': 'Valor', 'rotulo': 'Total'}],
        })['resumo'])
        self.assertEqual(g2['linhas'], [['Unimed', 450.5], ['SUS', 200]])

        # 3) .txt texto livre
        txt_bytes = 'Relatório diário da recepção.\nTudo em ordem.'.encode('utf-8')
        r3 = self._enviar_arquivo(cli, self.bot, txt_bytes, 'notas.txt', corpo='Veja txt')
        self.assertEqual(r3.status_code, 200, self.texto(r3))
        l3 = json.loads(ferr.chamar(ctx, 'arquivo_ler', {'anexo_id': r3.get_json()['mensagem']['id']})['resumo'])
        self.assertEqual(l3['tipo_conteudo'], 'texto')
        self.assertIn('Relatório diário', l3['amostra_texto'])

    def test_recusas_tamanho_tipo_falso_e_pdf(self):
        cli = self.cliente('IA_REC', 'senha123')
        self._iniciar_nucleai(cli)

        # > 5 MB
        grande = b'a,b\n' + b'1,2\n' * (arq.ARQUIVO_MAX // 4 + 100)
        r_big = self._enviar_arquivo(cli, self.bot, grande, 'grande.csv')
        self.assertEqual(r_big.status_code, 400)
        self.assertIn('5 MB', r_big.get_json()['erro'])

        # PDF recusado com mensagem clara
        r_pdf = self._enviar_arquivo(cli, self.bot, b'%PDF-1.4\n%conteudo', 'relatorio.pdf')
        self.assertEqual(r_pdf.status_code, 400)
        self.assertIn('PDF', r_pdf.get_json()['erro'])

        # Tipo falso: PNG renomeado para .xlsx e .csv
        png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
        self.assertEqual(self._enviar_arquivo(cli, self.bot, png, 'falso.xlsx').status_code, 400)
        self.assertEqual(self._enviar_arquivo(cli, self.bot, png, 'falso.csv').status_code, 400)

        # Tipo falso: texto CSV renomeado para .xlsx e .xls
        self.assertEqual(self._enviar_arquivo(cli, self.bot, b'a;b\n1;2\n', 'falso.xlsx').status_code, 400)
        self.assertEqual(self._enviar_arquivo(cli, self.bot, b'a;b\n1;2\n', 'falso.xls').status_code, 400)

        # Tipo falso: binário com NUL bytes renomeado para .txt
        self.assertEqual(self._enviar_arquivo(cli, self.bot, b'abc\x00def', 'falso.txt').status_code, 400)

        # Arquivo para usuário humano (não NucleAI) é recusado
        self.assertEqual(self._enviar_arquivo(cli, self.admin, b'a;b\n1;2\n', 'dados.csv').status_code, 400)

    def test_outro_usuario_nao_le_arquivo(self):
        cli_a = self.cliente('IA_REC', 'senha123')
        self._iniciar_nucleai(cli_a)
        motor.BAIXAR = OpenRouter('Recebi. <<confianca:5>>')
        r = self._enviar_arquivo(cli_a, self.bot, _fazer_xlsx([['Fase'], ['Repouso']]), 'segredo.xlsx')
        self.assertEqual(r.status_code, 200)
        msg_id = r.get_json()['mensagem']['id']

        cli_b = self.cliente('IA_ADM', 'senha123')
        self._iniciar_nucleai(cli_b)
        ctx_b = ferr.contexto(self.con, self.admin)
        res_ler = ferr.chamar(ctx_b, 'arquivo_ler', {'anexo_id': msg_id})
        self.assertTrue(res_ler['resumo'].startswith('ERRO:'))
        res_padrao = ferr.chamar(ctx_b, 'arquivo_ler', {})
        self.assertTrue(res_padrao['resumo'].startswith('ERRO:'))

    def test_apagar_conversa_apaga_arquivo(self):
        cli = self.cliente('IA_REC', 'senha123')
        self._iniciar_nucleai(cli)
        antes = self._contar_anexos_ia()
        motor.BAIXAR = OpenRouter('Recebi. <<confianca:5>>')
        r = self._enviar_arquivo(cli, self.bot, _fazer_xlsx([['Fase'], ['Repouso']]), 'mibi.xlsx')
        self.assertEqual(r.status_code, 200)
        msg_id = r.get_json()['mensagem']['id']
        anexo_id = self.con.execute('SELECT anexo_id FROM chat_mensagens WHERE id=?', (msg_id,)).fetchone()['anexo_id']
        caminho = anexos.caminho_ao_lado(self.app.config['DATABASE'])
        self.assertIsNotNone(anexos.ler(caminho, anexo_id))
        self.assertEqual(self._contar_anexos_ia(), antes + 1)

        # Encerrar a conversa apaga as mensagens e o blob em anexos.db
        ajuda._encerrar(self.con, self.func, 'Até logo!')
        self.con.commit()
        self.assertIsNone(anexos.ler(caminho, anexo_id))
        self.assertEqual(self._contar_anexos_ia(), antes)

    def test_fluxo_completo_llm_falso_com_ilustrar_e_excel(self):
        dados = _fazer_xlsx([
            ['Fase', 'Convênio'],
            ['Repouso', 'Unimed'],
            ['Repouso', 'Particular'],
            ['Estresse', 'Unimed'],
        ])
        cli = self.cliente('IA_REC', 'senha123')
        self._iniciar_nucleai(cli)

        motor.BAIXAR = OpenRouter(
            ('arquivo_ler', {}),
            ('arquivo_agrupar', {'agrupar_por': ['Fase'], 'operacoes': [{'op': 'contar', 'rotulo': 'Exames'}]}),
            ('ilustrar', {
                'tipo': 'planilha',
                'titulo': 'Relatório final de MIBIs por fase',
                'colunas': ['Fase', 'Exames'],
                'linhas': [['Repouso', 2], ['Estresse', 1]],
            }),
            ('ilustrar', {
                'tipo': 'grafico',
                'titulo': 'MIBIs por fase',
                'modo': 'barras',
                'rotulos': ['Repouso', 'Estresse'],
                'series': [{'nome': 'Exames', 'valores': [2, 1]}],
            }),
            'Segue o relatório final de MIBIs separado por fase, com planilha e gráfico. <<confianca:5>>',
        )

        r = self._enviar_arquivo(cli, self.bot, dados, 'mibis.xlsx', corpo='Me traga o relatório final de MIBIs nesta planilha')
        self.assertEqual(r.status_code, 200, self.texto(r))
        respostas = r.get_json()['respostas']
        cartoes = [m['cartao'] for m in respostas if m.get('cartao')]
        self.assertEqual(len(cartoes), 2)
        planilha = next(c for c in cartoes if c['subtipo'] == 'planilha')
        grafico = next(c for c in cartoes if c['subtipo'] == 'grafico')
        self.assertEqual(planilha['dados']['linhas'], [['Repouso', 2], ['Estresse', 1]])
        self.assertEqual(grafico['dados']['rotulos'], ['Repouso', 'Estresse'])

        # Download do Excel reaproveitando a ilustração da planilha
        dl = cli.get('/mensagens/ilustracao/%d/excel' % planilha['id'])
        self.assertEqual(dl.status_code, 200)
        wb = load_workbook(io.BytesIO(dl.data))
        ws = wb.active
        valores = [[ws.cell(row=i, column=j).value for j in range(1, 3)] for i in range(1, ws.max_row + 1)]
        wb.close()
        self.assertTrue(any(v == ['Repouso', 2] for v in valores))

    def test_conhecimento_e_limite_linhas(self):
        self.assertIn('arquivo_ler', conh.REGRAS)
        self.assertIn('arquivo_agrupar', conh.REGRAS)
        antigo = arq.MAX_LINHAS
        try:
            arq.MAX_LINHAS = 3
            csv_bytes = 'Col\n1\n2\n3\n4\n5\n'.encode('utf-8')
            res = arq.ler_tabela(csv_bytes, arq.MIME_CSV)
            self.assertEqual(len(res['linhas']), 3)
            self.assertTrue(res['truncado'])
        finally:
            arq.MAX_LINHAS = antigo


if __name__ == '__main__':
    unittest.main()
