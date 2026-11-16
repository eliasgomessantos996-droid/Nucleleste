"""Módulo Enfermagem e Segurança: assinatura obrigatória para liberar o módulo, carrinho, medicamentos, equipamentos, esterilização, radioproteção,
fichas com assinatura e avisos ao responsável de cada área."""
import io
import json
from datetime import date, datetime, timedelta

from PIL import Image, ImageDraw

from app import db as dbmod
from app import enfermagem as enf
from tests.test_chat_blindagens import Base


def png_assinatura():
    img = Image.new('RGB', (240, 90), 'white')
    ImageDraw.Draw(img).line([(10, 70), (60, 20), (110, 60), (200, 15)], fill=(10, 10, 80), width=4)
    b = io.BytesIO()
    img.save(b, 'PNG')
    return b.getvalue()


class Enfermagem(Base):
    def con(self):
        return dbmod.conectar(self.app.config['DATABASE'])

    def linhas(self, sql, params=()):
        con = self.con()
        try:
            return [dict(r) for r in con.execute(sql, params)]
        finally:
            con.close()

    def uid(self, nome):
        return self.linhas('SELECT id FROM usuarios WHERE usuario=?', (nome,))[0]['id']

    def enviar_assinatura(self, c, uid, conteudo=None, **extra):
        dados = {'cargo': 'Enfermeira', 'conselho': 'COREN', 'numero': '123456', 'uf': 'SP', 'acao': 'trocar'}
        dados.update(extra)
        if conteudo is not None:
            dados['assinatura'] = (io.BytesIO(conteudo), 'assinatura.png')
        return self.post(c, '/enfermagem/assinatura/%d' % uid, dados, content_type='multipart/form-data')

    def profissional_pronta(self, nome='ENF_ANA'):
        """Usuário com o módulo e a assinatura já importada (pelo caminho normal da gestão)."""
        self.criar_usuario(nome, ['atendimentos'])
        adm = self.cliente()
        uid = self.uid(nome)
        r = self.post(adm, '/usuarios/%d' % uid, {'perfil': 'usuario', 'modulos': ['atendimentos', 'enfermagem']})
        self.assertEqual(r.status_code, 302)
        self.enviar_assinatura(adm, uid, png_assinatura())
        return uid

    # ------------------------------------------------------------ permissão e assinatura
    def test_liberar_exige_assinatura_e_cancelar_nao_salva_nada(self):
        self.criar_usuario('ENF_BIA', ['atendimentos'])
        uid = self.uid('ENF_BIA')
        adm = self.cliente()
        r = self.post(adm, '/usuarios/%d' % uid, {'perfil': 'usuario', 'modulos': ['atendimentos', 'enfermagem']})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/enfermagem/assinatura/%d' % uid, r.headers['Location'])
        self.assertEqual(json.loads(self.linhas('SELECT modulos FROM usuarios WHERE id=?', (uid,))[0]['modulos']), ['atendimentos'])   # nada salvo pela metade
        pagina = self.texto(adm.get(r.headers['Location']))
        self.assertIn('Nada foi salvo ainda', pagina)
        self.post(adm, '/enfermagem/assinatura/%d/cancelar' % uid)
        self.assertEqual(json.loads(self.linhas('SELECT modulos FROM usuarios WHERE id=?', (uid,))[0]['modulos']), ['atendimentos'])
        # sair da página sem importar (abrir a edição de novo) também descarta o pedido
        self.post(adm, '/usuarios/%d' % uid, {'perfil': 'usuario', 'modulos': ['atendimentos', 'enfermagem']})
        adm.get('/usuarios/%d' % uid)
        self.enviar_assinatura(adm, uid, png_assinatura())
        self.assertEqual(json.loads(self.linhas('SELECT modulos FROM usuarios WHERE id=?', (uid,))[0]['modulos']), ['atendimentos'])
        self.assertTrue(enf.assinatura_valida(self.con(), uid))

    def test_importar_assinatura_conclui_a_permissao_e_remove_o_fundo_branco(self):
        uid = self.profissional_pronta('ENF_CLA')
        self.assertIn('enfermagem', json.loads(self.linhas('SELECT modulos FROM usuarios WHERE id=?', (uid,))[0]['modulos']))
        c = self.cliente('ENF_CLA', 'senha123')
        self.assertEqual(c.get('/enfermagem').status_code, 200)
        png = c.get('/enfermagem/assinatura/%d.png' % uid).get_data()
        img = Image.open(io.BytesIO(png)).convert('RGBA')
        self.assertEqual(img.getpixel((0, 0))[3], 0)          # canto: fundo branco virou transparente
        self.assertLessEqual(img.width, 420)
        p = self.linhas('SELECT * FROM enf_profissionais WHERE usuario_id=?', (uid,))[0]
        self.assertEqual((p['cargo'], p['conselho'], p['numero'], p['uf']), ('Enfermeira', 'COREN', '123456', 'SP'))
        acoes = [a['acao'] for a in self.linhas("SELECT acao FROM auditoria WHERE modulo='Enfermagem'")]
        self.assertIn('Importou assinatura', acoes)
        self.assertIn('Liberou o módulo Enfermagem e Segurança', acoes)

    def test_trocar_e_manter_assinatura(self):
        uid = self.profissional_pronta('ENF_DAN')
        adm = self.cliente()
        antes = self.linhas('SELECT assinatura_id FROM enf_profissionais WHERE usuario_id=?', (uid,))[0]['assinatura_id']
        self.enviar_assinatura(adm, uid, None, acao='manter', numero='999999')
        meio = self.linhas('SELECT assinatura_id, numero FROM enf_profissionais WHERE usuario_id=?', (uid,))[0]
        self.assertEqual((meio['assinatura_id'], meio['numero']), (antes, '999999'))
        self.enviar_assinatura(adm, uid, png_assinatura())
        depois = self.linhas('SELECT assinatura_id FROM enf_profissionais WHERE usuario_id=?', (uid,))[0]['assinatura_id']
        self.assertNotEqual(depois, antes)
        self.assertIn('Trocou a assinatura', [a['acao'] for a in self.linhas("SELECT acao FROM auditoria WHERE modulo='Enfermagem'")])
        r = self.enviar_assinatura(adm, uid, b'nao e imagem')
        self.assertEqual(r.status_code, 200)               # erro: volta para a página com a mensagem

    def test_permissao_sem_assinatura_nao_vale(self):
        self.criar_usuario('ENF_EVA', ['enfermagem'])         # módulo no banco, mas sem assinatura
        c = self.cliente('ENF_EVA', 'senha123')
        self.assertIn(c.get('/enfermagem').status_code, (302, 403))
        self.assertNotIn('Enfermagem e Segurança', self.texto(c.get('/')))

    def test_usuario_novo_nao_nasce_com_o_modulo(self):
        adm = self.cliente()
        self.post(adm, '/usuarios/novo', {'usuario': 'ENF_NOVO', 'senha': 'abc123', 'perfil': 'usuario', 'modulos': ['atendimentos', 'enfermagem']})
        r = self.linhas("SELECT modulos FROM usuarios WHERE usuario='ENF_NOVO'")
        self.assertEqual(json.loads(r[0]['modulos']), ['atendimentos'])

    # ------------------------------------------------------------ carrinho
    def test_carrinho_vermelho_conferencia_lacre_e_ficha_assinada(self):
        uid = self.profissional_pronta('ENF_FLA')
        c = self.cliente('ENF_FLA', 'senha123')
        r = self.post(c, '/enfermagem/carrinho/novo', {'nome': 'Carrinho 1', 'local': 'Sala de estresse', 'lacre': 'L-100', 'periodicidade': 'DIARIA'})
        cid = int(r.headers['Location'].rsplit('/', 1)[1])
        ontem = (date.today() - timedelta(days=1)).isoformat()
        self.post(c, '/enfermagem/carrinho/%d/item' % cid, {'nome': 'Adrenalina', 'qtd': '5', 'qtd_min': '5', 'lote': 'A1', 'validade': (date.today() + timedelta(days=200)).isoformat()})
        self.assertIn('Completo', self.texto(c.get('/enfermagem/carrinho')))
        self.post(c, '/enfermagem/carrinho/%d/item' % cid, {'nome': 'Atropina', 'qtd': '1', 'qtd_min': '3', 'lote': 'B', 'validade': ontem})
        self.assertIn('enf-area vermelho', self.texto(c.get('/enfermagem/carrinho')))
        itens = self.linhas('SELECT * FROM enf_carrinho_itens WHERE carrinho_id=?', (cid,))
        # após o uso exige lacre quebrado e novo
        dados = {'tipo': 'APOS_USO', 'chk_0': '1', 'chk_1': '1'}
        for i in itens:
            dados['qtd_%d' % i['id']] = str(i['qtd'])
        r = self.post(c, '/enfermagem/carrinho/%d/conferir' % cid, dados, follow_redirects=True)
        self.assertIn('número do lacre', self.texto(r))
        dados.update({'lacre_quebrado': 'L-100', 'lacre_novo': 'L-101'})
        r = self.post(c, '/enfermagem/carrinho/%d/conferir' % cid, dados)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.linhas('SELECT lacre_atual FROM enf_carrinhos WHERE id=?', (cid,))[0]['lacre_atual'], 'L-101')
        conf = self.linhas('SELECT * FROM enf_conferencias WHERE carrinho_id=?', (cid,))[0]
        self.assertEqual((conf['lacre_quebrado'], conf['lacre_novo'], conf['profissional_id']), ('L-100', 'L-101', uid))
        self.assertGreaterEqual(conf['problemas'], 1)
        ficha = self.texto(c.get(r.headers['Location']))
        self.assertIn('/enfermagem/assinatura/%d.png' % uid, ficha)              # assinatura sobre a linha
        self.assertIn('Enfermeira', ficha)
        self.assertIn('COREN-SP 123456', ficha)
        self.assertIn('L-101', ficha)
        self.assertIn('Imprimiu ficha de conferência', [a['acao'] for a in self.linhas("SELECT acao FROM auditoria WHERE modulo='Enfermagem'")])

    def test_ficha_so_leva_a_assinatura_de_quem_registrou(self):
        self.profissional_pronta('ENF_GIO')
        self.criar_usuario('ENF_HEL', ['atendimentos'])
        adm = self.cliente()
        hel = self.uid('ENF_HEL')
        self.post(adm, '/usuarios/%d' % hel, {'perfil': 'usuario', 'modulos': ['atendimentos', 'enfermagem']})
        self.enviar_assinatura(adm, hel, png_assinatura(), cargo='Técnica de enfermagem', numero='555')
        gio = self.cliente('ENF_GIO', 'senha123')
        cid = int(self.post(gio, '/enfermagem/carrinho/novo', {'nome': 'C2'}).headers['Location'].rsplit('/', 1)[1])
        self.post(gio, '/enfermagem/carrinho/%d/item' % cid, {'nome': 'Soro', 'qtd': '2', 'qtd_min': '1'})
        r = self.post(gio, '/enfermagem/carrinho/%d/conferir' % cid, {'tipo': 'SEMANAL'})
        ficha_gio = self.texto(gio.get(r.headers['Location']))
        self.assertIn('/enfermagem/assinatura/%d.png' % self.uid('ENF_GIO'), ficha_gio)
        self.assertNotIn('/enfermagem/assinatura/%d.png' % hel, ficha_gio)
        self.assertNotIn('Técnica de enfermagem', ficha_gio)

    # ------------------------------------------------------------ medicamentos
    def test_medicamentos_uso_reposicao_e_temperatura(self):
        self.profissional_pronta('ENF_IVA')
        c = self.cliente('ENF_IVA', 'senha123')
        self.post(c, '/enfermagem/medicamentos/carregar')
        nomes = [m['nome'] for m in self.linhas('SELECT nome FROM enf_medicamentos')]
        for n in ('Adenosina', 'Dipiridamol', 'Dobutamina', 'Regadenoson', 'Aminofilina', 'Atropina', 'Nitroglicerina', 'Glicose', 'Soro fisiológico', 'Adrenalina'):
            self.assertIn(n, nomes)
        mid = self.linhas("SELECT id FROM enf_medicamentos WHERE nome='Adenosina'")[0]['id']
        self.post(c, '/enfermagem/medicamentos/salvar', {'id': str(mid), 'nome': 'Adenosina', 'local': 'Sala de estresse', 'lote': 'L9', 'qtd': '6', 'qtd_min': '5',
                                                       'validade': (date.today() + timedelta(days=100)).isoformat()})
        self.post(c, '/enfermagem/medicamentos/%d/usar' % mid, {'qtd': '2', 'motivo': 'Exame de estresse'})
        self.assertEqual(self.linhas('SELECT qtd FROM enf_medicamentos WHERE id=?', (mid,))[0]['qtd'], 4)
        rep = self.linhas("SELECT * FROM enf_reposicao WHERE medicamento_id=? AND status='PENDENTE'", (mid,))
        self.assertEqual((len(rep), rep[0]['qtd']), (1, 2))
        self.post(c, '/enfermagem/medicamentos/%d/usar' % mid, {'qtd': '1'})
        self.assertEqual(self.linhas("SELECT qtd FROM enf_reposicao WHERE medicamento_id=? AND status='PENDENTE'", (mid,))[0]['qtd'], 3)   # soma no mesmo pedido
        self.assertIn('Adenosina', self.texto(c.get('/enfermagem/medicamentos')))
        self.post(c, '/enfermagem/reposicao/%d/repor' % rep[0]['id'], {'qtd': '3', 'lote': 'L10'})
        self.assertEqual(self.linhas('SELECT qtd, lote FROM enf_medicamentos WHERE id=?', (mid,))[0]['qtd'], 6)
        r = self.post(c, '/enfermagem/medicamentos/%d/usar' % mid, {'qtd': '99'}, follow_redirects=True)
        self.assertIn('estoque', self.texto(r).lower())
        # temperatura: 2 a 8 °C por padrão
        self.post(c, '/enfermagem/temperatura', {'local': 'Geladeira', 'temperatura': '4,5'})
        self.post(c, '/enfermagem/temperatura', {'local': 'Geladeira', 'temperatura': '11'})
        t = self.linhas('SELECT temperatura, ok FROM enf_temperaturas ORDER BY id')
        self.assertEqual([(x['temperatura'], x['ok']) for x in t], [(4.5, 1), (11.0, 0)])
        self.assertIn('FORA do limite', self.texto(c.get('/enfermagem/medicamentos')))

    # ------------------------------------------------------------ equipamentos
    def test_equipamento_teste_diario_laudo_e_atraso(self):
        uid = self.profissional_pronta('ENF_JOS')
        c = self.cliente('ENF_JOS', 'senha123')
        laudo = (io.BytesIO(b'%PDF-1.4 laudo'), 'laudo.pdf')
        self.post(c, '/enfermagem/equipamentos/salvar', {'nome': 'Desfibrilador 1', 'tipo': 'Cardioversor/desfibrilador', 'patrimonio': 'P1',
                                                        'proxima_manutencao': (date.today() - timedelta(days=2)).isoformat(), 'laudo': laudo}, content_type='multipart/form-data')
        e = self.linhas("SELECT * FROM enf_equipamentos WHERE nome='Desfibrilador 1'")[0]
        self.assertEqual(e['teste_diario'], 1)
        self.assertEqual(c.get('/enfermagem/equipamentos/%d/laudo' % e['id']).get_data()[:5], b'%PDF-')
        eq = [x for x in enf.equipamentos(self.con(), datetime.combine(date.today(), datetime.strptime('23:00', '%H:%M').time())) if x['id'] == e['id']][0]
        self.assertTrue(eq['teste_atrasado'])
        self.assertEqual(eq['manutencao'], 'vencido')
        r = self.post(c, '/enfermagem/equipamentos/%d/teste' % e['id'], {'t_carga': '1', 't_bateria': '1', 't_pas': '1', 't_fita': '1'})
        ficha = self.texto(c.get(r.headers['Location']))
        self.assertIn('/enfermagem/assinatura/%d.png' % uid, ficha)
        self.assertIn('equipamento apto', ficha)
        r = self.post(c, '/enfermagem/equipamentos/%d/teste' % e['id'], {'t_carga': '1'})
        self.assertIn('FALHA no teste', self.texto(c.get(r.headers['Location'])))

    # ------------------------------------------------------------ esterilização e radioproteção
    def test_esterilizacao_etiqueta_e_radioprotecao(self):
        self.profissional_pronta('ENF_KAT')
        c = self.cliente('ENF_KAT', 'senha123')
        r = self.post(c, '/enfermagem/esterilizacao/novo', {'descricao': 'Kit de punção', 'autoclave': 'A1', 'ciclo': '12', 'quimico': 'CONFORME', 'biologico': 'AGUARDANDO'})
        pid = int(r.headers['Location'].split('/')[-2])
        p = self.linhas('SELECT * FROM enf_pacotes WHERE id=?', (pid,))[0]
        self.assertTrue(p['codigo'].startswith('EST-'))
        self.assertEqual((date.fromisoformat(p['validade']) - date.fromisoformat(p['data_esteril'])).days, 30)
        self.assertIn(p['codigo'], self.texto(c.get(r.headers['Location'])))
        self.assertIn(b'<svg', c.get('/enfermagem/esterilizacao/%d/qr.svg' % pid).get_data())
        self.post(c, '/enfermagem/esterilizacao/%d/biologico' % pid, {'resultado': 'NÃO CONFORME'})
        self.assertIn('enf-linha-vermelha', self.texto(c.get('/enfermagem/esterilizacao')))
        self.post(c, '/enfermagem/esterilizacao/%d/usado' % pid)
        self.assertNotIn(p['codigo'], self.texto(c.get('/enfermagem/esterilizacao')))
        # radioproteção: teste do monitor, kit e ocorrência (também na Qualidade)
        self.post(c, '/enfermagem/radioprotecao/teste', {'fundo': '0,1', 'fonte': '5', 'ok': '1'})
        self.assertEqual(len(self.linhas('SELECT * FROM enf_rp_testes')), 1)
        self.post(c, '/enfermagem/radioprotecao/ocorrencia', {'tipo': 'Extravasamento de radiofármaco', 'radiofarmaco': 'MIBI', 'local': 'braço direito', 'gravidade': 'Leve',
                                                              'conduta': 'Elevado o membro e avisado o médico', 'qualidade': '1'})
        oc = self.linhas('SELECT * FROM enf_ocorrencias')[0]
        self.assertTrue(oc['qualidade_id'])
        self.assertEqual(self.linhas('SELECT setor FROM cq_ocorrencias WHERE id=?', (oc['qualidade_id'],))[0]['setor'], 'Enfermagem')
        r = self.post(c, '/enfermagem/carrinho/novo', {'nome': 'Kit sala de dose', 'tipo': 'KIT'})
        self.assertEqual(self.linhas('SELECT tipo FROM enf_carrinhos WHERE nome=?', ('Kit sala de dose',))[0]['tipo'], 'KIT')
        self.assertIn('Kit sala de dose', self.texto(c.get('/enfermagem/radioprotecao')))

    # ------------------------------------------------------------ avisos
    def test_avisos_vao_ao_responsavel_e_sobem_para_a_gerencia(self):
        tit = self.profissional_pronta('ENF_LIA')
        sub = self.profissional_pronta('ENF_MAR')
        self.criar_usuario('GER_ENF', ['gerencia'])
        ger = self.uid('GER_ENF')
        adm = self.cliente()
        self.post(adm, '/enfermagem/responsaveis', {'titular_medicamentos': str(tit), 'substituto_medicamentos': str(sub)})
        con = self.con()
        hoje = date.today()
        con.execute("INSERT INTO enf_medicamentos (nome, local, qtd, qtd_min, validade) VALUES ('Adrenalina', 'Carrinho', 5, 1, ?)", ((hoje + timedelta(days=7)).isoformat(),))
        con.execute("INSERT INTO enf_medicamentos (nome, local, qtd, qtd_min, validade) VALUES ('Vencida X', 'Carrinho', 5, 1, ?)", ((hoje - timedelta(days=5)).isoformat(),))
        con.commit()
        antes = con.execute("SELECT COUNT(*) FROM chat_mensagens WHERE tipo='ENFERMAGEM'").fetchone()[0]
        n = enf.verificar_avisos(con, hoje, datetime(hoje.year, hoje.month, hoje.day, 7, 0))
        self.assertGreater(n, 0)
        para = {r['para_id'] for r in con.execute("SELECT para_id FROM chat_mensagens WHERE tipo='ENFERMAGEM' AND corpo LIKE '%Adrenalina%'")}
        self.assertEqual(para, {tit, sub})
        # o item vencido há 5 dias sobe para a gerência
        escala = [r['corpo'] for r in con.execute("SELECT corpo FROM chat_mensagens WHERE tipo='ENFERMAGEM' AND para_id=? AND corpo LIKE '%Vencida X%'", (ger,))]
        self.assertTrue(escala and 'aviso à gerência' in escala[0])
        # cada fase só é enviada uma vez
        self.assertEqual(enf.verificar_avisos(con, hoje, datetime(hoje.year, hoje.month, hoje.day, 7, 5)), 0)
        # o responsável enxerga o aviso na própria conversa (não fica restrito à gerência)
        c = self.cliente('ENF_LIA', 'senha123')
        sistema = self.linhas('SELECT id FROM usuarios WHERE sistema=1 AND usuario=?', (dbmod.SISTEMA_USUARIO,))[0]['id']
        self.assertIn('Adrenalina', self.texto(c.get('/mensagens?com=%d' % sistema)))
        con.close()

    def test_aviso_de_teste_diario_nao_feito(self):
        eid_user = self.profissional_pronta('ENF_NEL')
        con = self.con()
        con.execute("INSERT INTO enf_equipamentos (tipo, nome, teste_diario) VALUES ('Cardioversor/desfibrilador', 'Desf. A', 1)")
        con.commit()
        hoje = date.today()
        cedo = enf.verificar_avisos(con, hoje, datetime(hoje.year, hoje.month, hoje.day, 6, 0))
        tarde = enf.verificar_avisos(con, hoje, datetime(hoje.year, hoje.month, hoje.day, 10, 0))
        self.assertEqual(cedo, 0)
        self.assertGreater(tarde, 0)
        self.assertIn('teste diário de Desf. A', con.execute("SELECT corpo FROM chat_mensagens WHERE tipo='ENFERMAGEM' ORDER BY id DESC LIMIT 1").fetchone()[0])
        con.close()

    def test_telas_abrem_e_painel_resume(self):
        self.profissional_pronta('ENF_OTO')
        c = self.cliente('ENF_OTO', 'senha123')
        for url in ('/enfermagem', '/enfermagem/carrinho', '/enfermagem/medicamentos', '/enfermagem/equipamentos', '/enfermagem/esterilizacao', '/enfermagem/radioprotecao', '/enfermagem/profissionais'):
            self.assertEqual(c.get(url).status_code, 200, url)
        self.assertIn('Situação de hoje', self.texto(c.get('/enfermagem')))
