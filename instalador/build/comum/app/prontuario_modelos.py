"""Modelos de documentos clínicos do prontuário (motor genérico).

Cada tipo de documento é uma entrada em MODELOS. As funções deste arquivo cuidam dos valores iniciais, da leitura do
formulário, dos cálculos, dos obrigatórios e do texto para impressão. Para acrescentar um documento, basta uma entrada.

Campo (dict):
  chave       nome do campo no formulário e no JSON gravado
  rotulo      texto ao lado do campo
  tipo        texto, area, simnao, simnao_na, escolha, multipla, numero, hora, data, sinais ou calculado
  opcoes      lista de opções (escolha, simnao, simnao_na, multipla)
  sugestoes   frases prontas que aparecem como botões clicáveis
  obrig       True quando o campo é obrigatório para concluir
  largura     colunas da grade (3, 4, 6 ou 12)
  ajuda       texto curto opcional
  inicial     nome de um valor do contexto do atendimento (exame, medicamentos, exame_anterior, alergias, hospital_setor...)
  cond        (chave, valor): o campo só aparece (e é lido) quando a outra resposta tem esse valor
  calc        campo 'calculado': o valor sai de MODELOS[tipo]['calcular'] (no servidor, ao salvar, e ao vivo no JS)

Seção (dict): id, titulo, subtitulo, letra (S, B, A, R ou vazio), campos, assinatura (rótulo da linha de assinatura
ao fim da seção; a impressão desenha a linha).

Modelo (dict): titulo, sigla, descricao, secoes (ou 'montar': função que devolve as seções a partir de dados),
'iniciais' (função contexto -> dados iniciais extras), 'calcular' (função dados -> valores calculados),
'assinaturas' (rótulos das linhas finais; padrão ['Profissional responsável']; [] = nenhuma).

Sinais vitais (tipo 'sinais') são guardados em sub-chaves: <chave>_pa, <chave>_fc, <chave>_fr, <chave>_spo2, <chave>_temp, <chave>_dor.
Chaves que começam com '_' (ex.: _pnt_slug) são internas e não aparecem na tela.
"""

# sub-campos dos sinais vitais: (sufixo, rótulo, unidade)
SINAIS_SUB = [('pa', 'PA', 'mmHg'), ('fc', 'FC', 'bpm'), ('fr', 'FR', 'irpm'), ('spo2', 'SpO2', '%'),
              ('temp', 'Temp.', '°C'), ('dor', 'Dor 0-10', '')]

OPCOES_SIMNAO = ['Sim', 'Não']
OPCOES_SIMNAO_NA = ['Sim', 'Não', 'Não se aplica']
OPCOES_PNT = ['SIM', 'NÃO']   # as respostas do questionário PNT são gravadas assim (mesmo formato do atendimento)
TIPOS_ESCOLHA = ('escolha', 'simnao', 'simnao_na')
ASSINATURA_PADRAO = ['Profissional responsável']
CONSELHOS_PROFISSIONAL = ['COREN', 'CRM', 'CRBM', 'CONTER/CRTRs']

PRESCRICAO_MIBI = [
    ('prescr_1', 'Caixa 1: Tc-99m', '35 MCI TC99 + SESTAMIBI'),
    ('prescr_2', 'Caixa 2: Persantin', 'PERSANTIN 40 mg diluído em 12 ml de ABD'),
    ('prescr_3', 'Caixa 3: Aminofilina', 'AMINOFILINA 120 mg diluída em 5 ml de ABD'),
    ('prescr_4', 'Caixa 4: Heparina', 'HEPARINA 0,1 ml (5.000 UI/ml) diluída em 5 ml de ABD'),
]


def _sbar():
    return {
        'titulo': 'SBAR — Comunicação e passagem de caso',
        'sigla': 'SBAR',
        'descricao': 'Relatório de passagem de caso da equipe técnica (medicina nuclear) para o paciente internado no hospital.',
        'assinaturas': ['Assinatura do profissional'],
        'secoes': [
            {'id': 'origem', 'titulo': 'Origem do paciente', 'subtitulo': 'Preencha ao receber o paciente do hospital.', 'letra': '',
             'campos': [
                 {'chave': 'hospital_setor', 'rotulo': 'Hospital / setor de origem', 'tipo': 'texto', 'largura': 6, 'inicial': 'hospital_setor',
                  'sugestoes': ['Hospital — enfermaria', 'UTI adulto', 'Pronto-socorro', 'Centro de oncologia']},
                 {'chave': 'leito', 'rotulo': 'Leito', 'tipo': 'texto', 'largura': 3},
                 {'chave': 'chegada_data', 'rotulo': 'Data de chegada', 'tipo': 'data', 'largura': 3},
                 {'chave': 'chegada_hora', 'rotulo': 'Hora de chegada', 'tipo': 'hora', 'largura': 3},
                 {'chave': 'saida_data', 'rotulo': 'Data de saída', 'tipo': 'data', 'largura': 3},
                 {'chave': 'saida_hora', 'rotulo': 'Hora de saída', 'tipo': 'hora', 'largura': 3},
                 {'chave': 'acompanhado', 'rotulo': 'Acompanhado por', 'tipo': 'texto', 'largura': 6,
                  'sugestoes': ['Técnico de enfermagem do hospital', 'Familiar', 'Maqueiro', 'Sem acompanhante']},
                 {'chave': 'transporte', 'rotulo': 'Meio de transporte', 'tipo': 'escolha', 'largura': 6,
                  'opcoes': ['Deambulando', 'Cadeira de rodas', 'Maca', 'Ambulância']},
             ]},
            {'id': 'S', 'titulo': 'Situação', 'subtitulo': 'Como o paciente está agora e por que veio.', 'letra': 'S',
             'campos': [
                 {'chave': 'exame', 'rotulo': 'Exame / procedimento realizado', 'tipo': 'texto', 'obrig': True, 'largura': 6, 'inicial': 'exame'},
                 {'chave': 'motivo', 'rotulo': 'Motivo da solicitação / hipótese diagnóstica', 'tipo': 'area', 'largura': 6,
                  'sugestoes': ['Pesquisa de isquemia miocárdica', 'Pesquisa de metástases ósseas', 'Avaliação de função renal',
                                'Pesquisa de tromboembolismo pulmonar', 'Pesquisa de sangramento digestivo', 'Estadiamento oncológico']},
                 {'chave': 'estado_geral', 'rotulo': 'Estado geral na chegada', 'tipo': 'area', 'obrig': True, 'largura': 12,
                  'sugestoes': ['Consciente, orientado, colaborativo', 'Hemodinamicamente estável', 'Eupneico em ar ambiente',
                                'Em uso de O2 por cateter nasal', 'Sonolento, responde a estímulos', 'Queixa de dor',
                                'Acamado, dependente para mobilização']},
                 {'chave': 'queixa', 'rotulo': 'Queixa atual', 'tipo': 'area', 'largura': 12,
                  'sugestoes': ['Sem queixas', 'Dor torácica', 'Dispneia', 'Náuseas']},
             ]},
            {'id': 'B', 'titulo': 'Breve histórico', 'subtitulo': 'Doenças, alergias, medicamentos e exames anteriores.', 'letra': 'B',
             'campos': [
                 {'chave': 'comorbidades', 'rotulo': 'Comorbidades', 'tipo': 'multipla', 'largura': 12,
                  'opcoes': ['Hipertensão', 'Diabetes', 'Cardiopatia', 'DPOC/asma', 'Doença renal crônica', 'Neoplasia', 'AVC prévio', 'Outras']},
                 {'chave': 'comorbidades_outras', 'rotulo': 'Outras comorbidades', 'tipo': 'texto', 'largura': 6},
                 {'chave': 'alergias', 'rotulo': 'Alergias', 'tipo': 'texto', 'largura': 6, 'inicial': 'alergias',
                  'sugestoes': ['Nega alergias', 'Dipirona', 'Iodo/contraste iodado', 'Látex']},
                 {'chave': 'medicamentos', 'rotulo': 'Medicamentos em uso', 'tipo': 'area', 'largura': 12, 'inicial': 'medicamentos'},
                 {'chave': 'dispositivos', 'rotulo': 'Dispositivos', 'tipo': 'multipla', 'largura': 12,
                  'opcoes': ['Acesso venoso periférico', 'Cateter central', 'Sonda vesical', 'Sonda nasoenteral', 'Dreno',
                             'Oxigênio', 'Monitor cardíaco', 'Nenhum']},
                 {'chave': 'isolamento', 'rotulo': 'Isolamento / precauções', 'tipo': 'escolha', 'largura': 6,
                  'opcoes': ['Nenhum', 'Contato', 'Gotículas', 'Aerossóis']},
                 {'chave': 'exames_anteriores', 'rotulo': 'Exames anteriores relevantes', 'tipo': 'area', 'largura': 12,
                  'inicial': 'exame_anterior'},
             ]},
            {'id': 'A', 'titulo': 'Avaliação', 'subtitulo': 'Sinais vitais, administração do radiofármaco e intercorrências.', 'letra': 'A',
             'campos': [
                 {'chave': 'sinais_chegada', 'rotulo': 'Sinais vitais na chegada', 'tipo': 'sinais', 'largura': 12},
                 {'chave': 'sinais_saida', 'rotulo': 'Sinais vitais na saída', 'tipo': 'sinais', 'largura': 12},
                 {'chave': 'consciencia', 'rotulo': 'Nível de consciência', 'tipo': 'escolha', 'largura': 6,
                  'opcoes': ['Alerta', 'Responde à voz', 'Responde à dor', 'Não responde']},
                 {'chave': 'radiofarmaco', 'rotulo': 'Radiofármaco administrado', 'tipo': 'texto', 'largura': 6,
                  'sugestoes': ['Tc-99m Sestamibi', 'Tc-99m MDP', 'Tc-99m DTPA', 'Tc-99m DMSA', 'Tc-99m MAA', 'Gálio-67', 'Iodo-131', 'F-18 FDG']},
                 {'chave': 'atividade', 'rotulo': 'Atividade administrada', 'tipo': 'texto', 'largura': 3, 'ajuda': 'Ex.: 25 mCi'},
                 {'chave': 'horario_admin', 'rotulo': 'Horário da administração', 'tipo': 'hora', 'largura': 3},
                 {'chave': 'via', 'rotulo': 'Via / local de punção', 'tipo': 'texto', 'largura': 6,
                  'sugestoes': ['Venosa — MSD', 'Venosa — MSE', 'Oral']},
                 {'chave': 'medic_exame', 'rotulo': 'Medicações durante o exame', 'tipo': 'area', 'largura': 12,
                  'sugestoes': ['Dipiridamol conforme prescrição', 'Aminofilina conforme prescrição', 'Furosemida conforme prescrição', 'Nenhuma']},
                 {'chave': 'intercorrencias', 'rotulo': 'Intercorrências', 'tipo': 'area', 'obrig': True, 'largura': 12,
                  'sugestoes': ['Sem intercorrências', 'Reação vasovagal, revertida', 'Náuseas, sem vômitos',
                                'Extravasamento no local da punção', 'Desconforto torácico com o estresse farmacológico, revertido']},
                 {'chave': 'riscos', 'rotulo': 'Riscos identificados', 'tipo': 'multipla', 'largura': 12,
                  'opcoes': ['Queda', 'Lesão por pressão', 'Flebite', 'Broncoaspiração', 'Nenhum']},
             ]},
            {'id': 'R', 'titulo': 'Recomendação', 'subtitulo': 'Cuidados e destino depois do exame.', 'letra': 'R',
             'campos': [
                 {'chave': 'cuidados', 'rotulo': 'Cuidados após o exame', 'tipo': 'area', 'obrig': True, 'largura': 12,
                  'sugestoes': ['Estimular a ingestão de água', 'Esvaziar a bexiga com frequência nas próximas 24 h',
                                'Manter distância de gestantes e crianças por 24 h',
                                'Descartar fraldas e urina conforme orientação de radioproteção',
                                'Retirar o acesso venoso no hospital', 'Liberado para dieta habitual']},
                 {'chave': 'pendencias', 'rotulo': 'Pendências / retorno', 'tipo': 'area', 'largura': 12,
                  'sugestoes': ['Retorno para imagens tardias às __:__', 'Nenhuma pendência', 'Aguardando laudo']},
                 {'chave': 'destino', 'rotulo': 'Destino do paciente', 'tipo': 'escolha', 'largura': 6,
                  'opcoes': ['Retorno ao setor de origem', 'Alta', 'Outro']},
                 {'chave': 'profissional_hospital', 'rotulo': 'Profissional do hospital que recebeu o paciente', 'tipo': 'texto', 'largura': 6},
                 {'chave': 'observacoes', 'rotulo': 'Observações', 'tipo': 'area', 'largura': 12},
             ]},
        ],
    }


def _sae():
    """SAE de enfermagem: mesma estrutura da ficha impressa (sae_geral), uma linha de assinatura em cada etapa."""
    sim_nao_na = {'tipo': 'simnao_na', 'largura': 6}
    return {
        'titulo': 'SAE — Sistematização da Assistência de Enfermagem',
        'sigla': 'SAE',
        'descricao': 'Histórico, durante e pós-exame, com a assinatura do técnico ou enfermeiro em cada etapa.',
        'assinaturas': [],
        'secoes': [
            {'id': 'historico', 'titulo': 'Histórico', 'letra': '', 'assinatura': 'Técnico de Enfermagem/Enfermeiro',
             'campos': [
                 dict(sim_nao_na, chave='confirmou_identificacao', rotulo='1. Confirmou a identificação do cliente', tipo='simnao'),
                 dict(sim_nao_na, chave='acompanhante', rotulo='2. Presença de acompanhante', tipo='simnao'),
                 dict(sim_nao_na, chave='pertences', rotulo='3. Pertences entregues ao acompanhante'),
                 dict(sim_nao_na, chave='preparo', rotulo='4. Realizou o preparo corretamente'),
                 {'chave': 'alergia', 'rotulo': '5. Alergia a alguma medicação', 'tipo': 'escolha', 'largura': 6,
                  'opcoes': ['Sim', 'Não', 'Não sabe']},
                 {'chave': 'alergia_quais', 'rotulo': 'Quais', 'tipo': 'texto', 'largura': 6, 'inicial': 'alergias',
                  'sugestoes': ['Nega alergias', 'Dipirona', 'Iodo/contraste iodado', 'Látex']},
                 dict(sim_nao_na, chave='orientado', rotulo='6. Orientado sobre o procedimento', tipo='simnao'),
                 dict(sim_nao_na, chave='duvidas', rotulo='7. Perguntado se há dúvida', tipo='simnao'),
                 dict(sim_nao_na, chave='individualidade', rotulo='8. Individualidade (crenças, valores, religião)', tipo='simnao'),
                 {'chave': 'individualidade_qual', 'rotulo': 'Qual', 'tipo': 'texto', 'largura': 6},
             ]},
            {'id': 'durante', 'titulo': 'Durante o exame', 'letra': '', 'assinatura': 'Técnico de Enfermagem/Enfermeiro',
             'campos': [
                 {'chave': 'data_exame', 'rotulo': 'Data', 'tipo': 'data', 'largura': 4, 'inicial': 'data'},
                 {'chave': 'inicio_hora', 'rotulo': 'Início do procedimento (hora)', 'tipo': 'hora', 'largura': 4},
                 {'chave': 'monitorizacao', 'rotulo': '1. Monitorização', 'tipo': 'simnao', 'largura': 4},
                 {'chave': 'sinais_antes', 'rotulo': 'Sinais vitais antes do exame', 'tipo': 'sinais', 'largura': 12},
                 dict(sim_nao_na, chave='acesso_venoso', rotulo='2. Acesso venoso periférico'),
                 {'chave': 'medicacao', 'rotulo': '3. Medicação conforme prescrição: qual, hora e quem aplicou', 'tipo': 'area',
                  'largura': 12, 'sugestoes': ['Dipiridamol conforme prescrição', 'Aminofilina conforme prescrição', 'Nenhuma']},
                 {'chave': 'decubito', 'rotulo': '4. Decúbito', 'tipo': 'escolha', 'largura': 6, 'opcoes': ['Dorsal', 'Ventral']},
                 {'chave': 'termino_hora', 'rotulo': '5. Término do procedimento (hora)', 'tipo': 'hora', 'largura': 6},
                 {'chave': 'estado_liberado', 'rotulo': '6. Estado do paciente ao ser liberado', 'tipo': 'area', 'largura': 12,
                  'sugestoes': ['Consciente, orientado, sem queixas', 'Sem intercorrências', 'Queixa de náusea, em melhora',
                                'Acompanhado pelo familiar']},
             ]},
            {'id': 'pos', 'titulo': 'Pós-exame', 'letra': '', 'assinatura': 'Técnico de Enfermagem/Enfermeiro',
             'campos': [
                 {'chave': 'entrada_hora', 'rotulo': 'Horário de entrada', 'tipo': 'hora', 'largura': 4},
                 {'chave': 'monitorizacao_pos', 'rotulo': '1. Monitorização', 'tipo': 'simnao', 'largura': 4},
                 {'chave': 'sinais_pos', 'rotulo': 'Sinais vitais após o exame', 'tipo': 'sinais', 'largura': 12},
                 dict(sim_nao_na, chave='reacoes', rotulo='2. Sinais de reação alérgica, cefaleia, desconforto abdominal, náusea ou vômito', tipo='simnao'),
                 {'chave': 'reacoes_obs', 'rotulo': 'Registrar alterações', 'tipo': 'area', 'largura': 12},
                 dict(sim_nao_na, chave='consciencia_avaliada', rotulo='3. Nível de consciência e atividade motora avaliados', tipo='simnao'),
                 dict(sim_nao_na, chave='liberado_acompanhante', rotulo='4. Liberado com acompanhante', tipo='simnao'),
                 {'chave': 'intercorrencias', 'rotulo': '5. Intercorrências', 'tipo': 'area', 'largura': 12,
                  'sugestoes': ['Sem intercorrências', 'Reação vasovagal, revertida', 'Náuseas, sem vômitos']},
                 {'chave': 'orientacoes', 'rotulo': '6. Orientações compartilhadas', 'tipo': 'area', 'largura': 12,
                  'sugestoes': ['Orientada sobre radioproteção e gestantes/crianças por 24 h', 'Orientada a manter boa hidratação',
                                'Orientada a esvaziar a bexiga com frequência']},
                 {'chave': 'saida_hora', 'rotulo': 'Horário de saída', 'tipo': 'hora', 'largura': 4},
             ]},
        ],
    }


def _pnt_iniciais(ctx):
    """Perguntas (da ficha PNT do exame, ou as genéricas) e respostas do atendimento, para o questionário digital."""
    perguntas = ctx.get('_perguntas')
    if not perguntas:
        from . import fichas
        perguntas = [list(fichas.ALERGIA), list(fichas.GRAVIDEZ), list(fichas.INDIVIDUALIDADE)]
    slug = ctx.get('_slug') or ''
    resp = ctx.get('respostas') or {}
    dados = {'_pnt_slug': slug, '_pnt_perguntas': [list(p) for p in perguntas]}
    for i in range(1, len(perguntas) + 1):
        dados['r%d' % i] = resp.get('r%d' % i, '')
        dados['o%d' % i] = resp.get('o%d' % i, '')
    if slug == 'pnt_mibi':
        for chave, _rot, texto in PRESCRICAO_MIBI:
            dados[chave] = texto
    return dados


def _pnt_montar(dados):
    perguntas = dados.get('_pnt_perguntas') or []
    qs = []
    for i, (texto, rotulo) in enumerate(perguntas, 1):
        qs.append({'chave': 'r%d' % i, 'rotulo': '%d - %s' % (i, texto), 'tipo': 'simnao', 'opcoes': OPCOES_PNT, 'largura': 12})
        if rotulo:   # a justificativa só aparece quando a resposta é SIM
            qs.append({'chave': 'o%d' % i, 'rotulo': rotulo, 'tipo': 'texto', 'largura': 12, 'cond': ('r%d' % i, 'SIM')})
    secoes = [{'id': 'questionario', 'titulo': 'Questionário digital', 'letra': '',
               'subtitulo': 'Sim ou Não em cada pergunta. Quando a resposta é SIM, escreva a justificativa.',
               'campos': qs or [{'chave': '_sem', 'rotulo': 'Este exame não tem questionário.', 'tipo': 'texto', 'largura': 12}]}]
    if dados.get('_pnt_slug') == 'pnt_mibi':
        secoes.append({'id': 'prescricao', 'titulo': 'Prescrição médica', 'letra': '',
                       'subtitulo': 'Como na ficha impressa: cada caixa com o medicamento e a diluição.',
                       'campos': [{'chave': c, 'rotulo': r, 'tipo': 'area', 'largura': 12} for c, r, _t in PRESCRICAO_MIBI]})
    secoes.append({'id': 'evolucao', 'titulo': 'Evolução', 'letra': '', 'campos': [
        {'chave': 'evolucao', 'rotulo': 'Evolução', 'tipo': 'area', 'largura': 12,
         'sugestoes': ['Paciente sem queixas durante o exame', 'Tolerou bem o procedimento']}]})
    secoes.append({'id': 'observacoes', 'titulo': 'Observações', 'letra': '', 'campos': [
        {'chave': 'observacoes', 'rotulo': 'Observações', 'tipo': 'area', 'largura': 12}]})
    return secoes


def _pnt():
    return {
        'titulo': 'Plano terapêutico (PNT): questionário digital',
        'sigla': 'PNT',
        'descricao': 'Questionário digital da ficha PNT do exame. Gravado no atendimento, a ficha impressa sai preenchida.',
        'assinaturas': ['Assinatura do paciente ou responsável', 'Profissional responsável'],
        'iniciais': _pnt_iniciais,
        'montar': _pnt_montar,
    }


def _ficha_mibi():
    return {
        'titulo': 'Ficha MIBI (digital)',
        'sigla': 'MIBI',
        'descricao': 'Dados da cintilografia do miocárdio: peso, injeção, escore de cálcio, fração de ejeção e medo ou fobia.',
        'calcular': lambda d: {'escore_total': _escore_total(d)},
        'secoes': [
            {'id': 'dados', 'titulo': 'Dados do exame', 'letra': '', 'campos': [
                {'chave': 'peso', 'rotulo': 'Peso (kg)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'altura', 'rotulo': 'Altura (cm)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'identidade', 'rotulo': 'Identidade', 'tipo': 'texto', 'largura': 6},
                {'chave': 'cartao_sus', 'rotulo': 'Cartão SUS', 'tipo': 'texto', 'largura': 6},
                {'chave': 'hora_injecao', 'rotulo': 'Hora da injeção', 'tipo': 'hora', 'largura': 3},
                {'chave': 'responsavel', 'rotulo': 'Responsável', 'tipo': 'texto', 'largura': 3},
                {'chave': 'previsao_imagem', 'rotulo': 'Previsão de imagem', 'tipo': 'texto', 'largura': 3},
                {'chave': 'lote', 'rotulo': 'Lote', 'tipo': 'texto', 'largura': 3},
                {'chave': 'injetado', 'rotulo': 'Injetado (atividade)', 'tipo': 'texto', 'largura': 3, 'ajuda': 'Ex.: 25 mCi'},
                {'chave': 'observacoes', 'rotulo': 'Observações', 'tipo': 'area', 'largura': 12},
            ]},
            {'id': 'escore', 'titulo': 'Escore de cálcio', 'letra': '', 'campos': [
                {'chave': 'realizar', 'rotulo': 'Realizar', 'tipo': 'simnao', 'largura': 3},
                {'chave': 'feito', 'rotulo': 'Feito', 'tipo': 'simnao', 'largura': 3},
                {'chave': 'processado', 'rotulo': 'Processado', 'tipo': 'simnao', 'largura': 3},
                {'chave': 'salvo', 'rotulo': 'Salvo', 'tipo': 'simnao', 'largura': 3},
                {'chave': 'da', 'rotulo': 'DA', 'tipo': 'numero', 'largura': 3},
                {'chave': 'cx', 'rotulo': 'CX', 'tipo': 'numero', 'largura': 3},
                {'chave': 'cd', 'rotulo': 'CD', 'tipo': 'numero', 'largura': 3},
                {'chave': 'escore_total', 'rotulo': 'Total do escore (DA + CX + CD)', 'tipo': 'calculado', 'calc': True, 'largura': 3},
            ]},
            {'id': 'fracao', 'titulo': 'Fração de ejeção', 'letra': '', 'campos': [
                {'chave': 'esforco', 'rotulo': 'Esforço (%)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'repouso', 'rotulo': 'Repouso (%)', 'tipo': 'numero', 'largura': 3},
            ]},
            {'id': 'medo', 'titulo': 'Medo ou fobia', 'letra': '', 'subtitulo': 'Marque Sim se o paciente referiu.', 'campos': [
                {'chave': 'medo_agulha', 'rotulo': 'Agulha', 'tipo': 'simnao', 'largura': 4},
                {'chave': 'medo_ambiente', 'rotulo': 'Ambiente fechado', 'tipo': 'simnao', 'largura': 4},
                {'chave': 'medo_jaleco', 'rotulo': 'Jaleco branco', 'tipo': 'simnao', 'largura': 4},
                {'chave': 'medo_medico', 'rotulo': 'Médico', 'tipo': 'simnao', 'largura': 4},
                {'chave': 'medo_aparelho', 'rotulo': 'Aparelho de exame', 'tipo': 'simnao', 'largura': 4},
            ]},
        ],
    }


def _escore_total(d):
    """DA + CX + CD quando os três são números; senão vazio."""
    try:
        return '%g' % sum(_num(d.get(k)) for k in ('da', 'cx', 'cd'))
    except TypeError:
        return ''


def _num(valor):
    """Número com vírgula decimal (ou None se vazio/inválido)."""
    texto = str(valor or '').strip().replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return None


def _pontos_news(d):
    """Pontuação de cada parâmetro do NEWS (tabela da ficha impressa). None se faltar algum valor obrigatório."""
    fr, spo2, temp, pas, fc = (_num(d.get(k)) for k in ('fr', 'spo2', 'temp', 'pas', 'fc'))
    if None in (fr, spo2, temp, pas, fc):
        return None
    if fr <= 8: p_fr = 3
    elif fr <= 11: p_fr = 1
    elif fr <= 20: p_fr = 0
    elif fr <= 24: p_fr = 2
    else: p_fr = 3
    if spo2 <= 91: p_spo2 = 3
    elif spo2 <= 93: p_spo2 = 2
    elif spo2 <= 95: p_spo2 = 1
    else: p_spo2 = 0
    p_o2 = 2 if d.get('o2') == 'Sim' else 0
    if temp <= 35.0: p_temp = 3
    elif temp <= 36.0: p_temp = 1
    elif temp <= 38.0: p_temp = 0
    elif temp <= 39.0: p_temp = 1
    else: p_temp = 2
    if pas <= 90: p_pas = 3
    elif pas <= 100: p_pas = 2
    elif pas <= 110: p_pas = 1
    elif pas <= 219: p_pas = 0
    else: p_pas = 3
    if fc <= 40: p_fc = 3
    elif fc <= 50: p_fc = 1
    elif fc <= 90: p_fc = 0
    elif fc <= 110: p_fc = 1
    elif fc <= 130: p_fc = 2
    else: p_fc = 3
    p_cons = 0 if d.get('consciencia') == 'Alerta' else 3
    return [p_fr, p_spo2, p_o2, p_temp, p_pas, p_fc, p_cons]


def _news_calcular(d):
    pontos = _pontos_news(d)
    if pontos is None:
        return {'pontuacao': '', 'risco': ''}
    total = sum(pontos)
    if total >= 7:
        risco = 'Alto'
    elif total >= 5:
        risco = 'Médio'
    elif 3 in pontos:
        risco = 'Baixo/médio: avaliar (3 em um parâmetro)'
    else:
        risco = 'Baixo'
    return {'pontuacao': str(total), 'risco': risco}


def _news():
    return {
        'titulo': 'Escore de alerta precoce (NEWS)',
        'sigla': 'NEWS',
        'descricao': 'Escore NEWS com a pontuação e o risco calculados pelo sistema.',
        'calcular': _news_calcular,
        'secoes': [
            {'id': 'sinais', 'titulo': 'Sinais', 'letra': '', 'subtitulo': 'Aceita vírgula nos decimais (ex.: 36,5).', 'campos': [
                {'chave': 'fr', 'rotulo': 'Frequência respiratória (irpm)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'spo2', 'rotulo': 'SpO2 (%)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'o2', 'rotulo': 'Oxigênio suplementar', 'tipo': 'simnao', 'largura': 3},
                {'chave': 'temp', 'rotulo': 'Temperatura (°C)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'pas', 'rotulo': 'PA sistólica (mmHg)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'fc', 'rotulo': 'Frequência cardíaca (bpm)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'consciencia', 'rotulo': 'Nível de consciência', 'tipo': 'escolha', 'largura': 6,
                 'opcoes': ['Alerta', 'Voz', 'Dor', 'Não responde']},
            ]},
            {'id': 'resultado', 'titulo': 'Resultado', 'letra': '', 'campos': [
                {'chave': 'pontuacao', 'rotulo': 'Pontuação total', 'tipo': 'calculado', 'calc': True, 'largura': 3},
                {'chave': 'risco', 'rotulo': 'Risco', 'tipo': 'calculado', 'calc': True, 'largura': 9},
                {'chave': 'conduta', 'rotulo': 'Conduta', 'tipo': 'area', 'largura': 12,
                 'sugestoes': ['Manter monitorização e reavaliar em 1 h', 'Comunicar a equipe médica', 'Sem conduta específica no momento']},
            ]},
        ],
    }


def _radiofarmaco():
    return {
        'titulo': 'Registro de administração do radiofármaco',
        'sigla': 'RADIO',
        'descricao': 'Radiofármaco, lote, atividade e a administração, com o extravasamento.',
        'secoes': [
            {'id': 'registro', 'titulo': 'Registro', 'letra': '', 'campos': [
                {'chave': 'radiofarmaco', 'rotulo': 'Radiofármaco', 'tipo': 'texto', 'largura': 6, 'inicial': 'radiofarmaco',
                 'sugestoes': ['Tc-99m Sestamibi', 'Tc-99m MDP', 'Tc-99m DTPA', 'Tc-99m DMSA', 'Tc-99m MAA', 'Gálio-67', 'Iodo-131', 'F-18 FDG']},
                {'chave': 'lote', 'rotulo': 'Lote', 'tipo': 'texto', 'largura': 3, 'inicial': 'lote'},
                {'chave': 'atividade_prescrita', 'rotulo': 'Atividade prescrita', 'tipo': 'texto', 'largura': 3, 'inicial': 'ativ_prescrita'},
                {'chave': 'atividade_administrada', 'rotulo': 'Atividade medida / administrada (mCi)', 'tipo': 'texto', 'largura': 3,
                 'inicial': 'ativ_administrada'},
                {'chave': 'hora_medicao', 'rotulo': 'Hora da medição', 'tipo': 'hora', 'largura': 3},
                {'chave': 'hora_administracao', 'rotulo': 'Hora da administração', 'tipo': 'hora', 'largura': 3},
                {'chave': 'via', 'rotulo': 'Via', 'tipo': 'texto', 'largura': 3, 'sugestoes': ['Venosa', 'Oral']},
                {'chave': 'local_puncao', 'rotulo': 'Local da punção', 'tipo': 'texto', 'largura': 3,
                 'sugestoes': ['Venosa — MSD', 'Venosa — MSE']},
                {'chave': 'extravasamento', 'rotulo': 'Extravasamento', 'tipo': 'simnao', 'largura': 3},
                {'chave': 'responsavel', 'rotulo': 'Responsável pela administração', 'tipo': 'texto', 'largura': 6},
                {'chave': 'observacoes', 'rotulo': 'Observações', 'tipo': 'area', 'largura': 12},
            ]},
        ],
    }


def _anamnese():
    return {
        'titulo': 'Anamnese / histórico clínico',
        'sigla': 'ANAM',
        'descricao': 'Queixa, história da doença, antecedentes, hábitos e medicamentos.',
        'secoes': [
            {'id': 'anamnese', 'titulo': 'Anamnese', 'letra': '', 'campos': [
                {'chave': 'queixa', 'rotulo': 'Queixa principal', 'tipo': 'area', 'largura': 12,
                 'sugestoes': ['Sem queixas', 'Dor torácica', 'Dispneia', 'Dor óssea']},
                {'chave': 'hda', 'rotulo': 'História da doença atual', 'tipo': 'area', 'largura': 12},
                {'chave': 'antecedentes', 'rotulo': 'Antecedentes pessoais', 'tipo': 'multipla', 'largura': 12,
                 'opcoes': ['Hipertensão', 'Diabetes', 'Cardiopatia', 'DPOC/asma', 'Doença renal crônica', 'Neoplasia', 'AVC prévio', 'Outros']},
                {'chave': 'cirurgias', 'rotulo': 'Cirurgias prévias', 'tipo': 'area', 'largura': 12, 'sugestoes': ['Nega cirurgias']},
                {'chave': 'medicamentos', 'rotulo': 'Medicamentos em uso', 'tipo': 'area', 'largura': 12, 'inicial': 'medicamentos'},
                {'chave': 'alergias', 'rotulo': 'Alergias', 'tipo': 'texto', 'largura': 6, 'inicial': 'alergias',
                 'sugestoes': ['Nega alergias', 'Dipirona', 'Iodo/contraste iodado', 'Látex']},
                {'chave': 'tabagismo', 'rotulo': 'Tabagismo', 'tipo': 'escolha', 'largura': 4, 'opcoes': ['Não', 'Ex-tabagista', 'Sim']},
                {'chave': 'etilismo', 'rotulo': 'Etilismo', 'tipo': 'escolha', 'largura': 4, 'opcoes': ['Não', 'Sim']},
                {'chave': 'atividade_fisica', 'rotulo': 'Atividade física', 'tipo': 'escolha', 'largura': 4, 'opcoes': ['Não', 'Sim']},
                {'chave': 'familiares', 'rotulo': 'Antecedentes familiares', 'tipo': 'multipla', 'largura': 12,
                 'opcoes': ['Câncer', 'Diabetes', 'Cardiopatia', 'Hipertensão', 'Doenças da tireoide', 'Outros']},
                {'chave': 'exames_anteriores', 'rotulo': 'Exames anteriores', 'tipo': 'area', 'largura': 12, 'inicial': 'exame_anterior'},
                {'chave': 'gestacao', 'rotulo': 'Gestação / amamentação', 'tipo': 'escolha', 'largura': 6,
                 'opcoes': ['Não se aplica', 'Não', 'Sim', 'Suspeita']},
                {'chave': 'peso', 'rotulo': 'Peso (kg)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'altura', 'rotulo': 'Altura (cm)', 'tipo': 'numero', 'largura': 3},
                {'chave': 'observacoes', 'rotulo': 'Observações', 'tipo': 'area', 'largura': 12},
            ]},
        ],
    }


def _evolucao():
    return {
        'titulo': 'Evolução',
        'sigla': 'EVOL',
        'descricao': 'Registro de evolução do paciente, por qualquer categoria da equipe.',
        'secoes': [
            {'id': 'evolucao', 'titulo': 'Evolução', 'letra': '', 'campos': [
                {'chave': 'data', 'rotulo': 'Data', 'tipo': 'data', 'largura': 3, 'inicial': 'data'},
                {'chave': 'hora', 'rotulo': 'Hora', 'tipo': 'hora', 'largura': 3},
                {'chave': 'categoria', 'rotulo': 'Categoria', 'tipo': 'escolha', 'largura': 6,
                 'opcoes': ['Enfermagem', 'Médica', 'Técnica em radiologia', 'Outra']},
                {'chave': 'sinais', 'rotulo': 'Sinais vitais', 'tipo': 'sinais', 'largura': 12},
                {'chave': 'evolucao', 'rotulo': 'Evolução', 'tipo': 'area', 'obrig': True, 'largura': 12,
                 'sugestoes': ['Paciente sem queixas', 'Tolerou bem o procedimento', 'Queixa de náusea, em melhora']},
                {'chave': 'conduta', 'rotulo': 'Conduta', 'tipo': 'area', 'largura': 12,
                 'sugestoes': ['Manter observação', 'Liberado conforme rotina', 'Comunicado à equipe médica']},
            ]},
        ],
    }


def _checklist():
    itens = [
        ('identificacao', '1. Identificação com dois identificadores (nome completo e data de nascimento)'),
        ('pulseira', '2. Pulseira de identificação (interno)'),
        ('alergias', '3. Alergias verificadas'),
        ('gestacao', '4. Gestação/amamentação verificada'),
        ('preparo', '5. Preparo e jejum conferidos'),
        ('medicacoes', '6. Medicações suspensas conforme orientação'),
        ('queda', '7. Risco de queda avaliado'),
        ('radioprotecao', '8. Orientações de radioproteção entregues'),
        ('acompanhante', '9. Acompanhante orientado'),
    ]
    return {
        'titulo': 'Checklist de segurança do paciente',
        'sigla': 'CHECK',
        'descricao': 'Itens de segurança conferidos antes e depois do exame.',
        'secoes': [
            {'id': 'checklist', 'titulo': 'Itens', 'letra': '',
             'campos': [{'chave': c, 'rotulo': r, 'tipo': 'simnao_na', 'largura': 12} for c, r in itens] +
                       [{'chave': 'observacoes', 'rotulo': 'Observações', 'tipo': 'area', 'largura': 12}]},
        ],
    }


# Modelos de documentos. Para um documento novo, acrescente uma entrada aqui.
MODELOS = {
    'sbar': _sbar(),
    'sae': _sae(),
    'pnt': _pnt(),
    'ficha_mibi': _ficha_mibi(),
    'news': _news(),
    'radiofarmaco': _radiofarmaco(),
    'anamnese': _anamnese(),
    'evolucao': _evolucao(),
    'checklist': _checklist(),
}


def obter(tipo):
    return MODELOS[tipo]


def tipos_disponiveis():
    """[(tipo, título)] para o seletor de novo documento."""
    return [(t, m['titulo']) for t, m in MODELOS.items()]


def secoes_de(tipo, dados=None):
    """Seções do documento. Modelos dinâmicos (PNT) montam as seções a partir dos dados guardados."""
    m = MODELOS[tipo]
    if 'montar' in m:
        return m['montar'](dados or {})
    return m['secoes']


def campos(tipo, dados=None):
    """Todos os campos do documento, na ordem das seções (lista achatada)."""
    return [c for s in secoes_de(tipo, dados) for c in s['campos']]


def rotulo_de(tipo, chave, dados=None):
    for c in campos(tipo, dados):
        if c['chave'] == chave:
            return c['rotulo']
    return chave


def assinaturas_de(tipo):
    return MODELOS[tipo].get('assinaturas', ASSINATURA_PADRAO)


def opcoes_de(campo):
    """Opções de um campo de escolha: as do próprio campo ou Sim/Não (e Sim/Não/Não se aplica)."""
    if campo.get('opcoes'):
        return campo['opcoes']
    return OPCOES_SIMNAO_NA if campo['tipo'] == 'simnao_na' else OPCOES_SIMNAO


def chaves_do_campo(campo):
    """Chaves gravadas no JSON para um campo (os sinais vitais gravam uma chave por medida)."""
    if campo['tipo'] == 'sinais':
        return [campo['chave'] + '_' + k for k, _, _ in SINAIS_SUB]
    return [campo['chave']]


def valores_iniciais(tipo, contexto=None):
    """Valores de um documento novo. 'iniciais' do modelo e campos com 'inicial' copiam o contexto do atendimento."""
    ctx = contexto or {}
    m = MODELOS[tipo]
    dados = dict(m['iniciais'](ctx)) if 'iniciais' in m else {}
    for c in campos(tipo, dados):
        if c['tipo'] == 'multipla':
            dados.setdefault(c['chave'], [])
        elif c['tipo'] == 'sinais':
            for k in chaves_do_campo(c):
                dados.setdefault(k, '')
        elif c['tipo'] == 'calculado':
            dados.setdefault(c['chave'], '')
        else:
            valor = (ctx.get(c['inicial']) or '') if c.get('inicial') else ''
            dados.setdefault(c['chave'], valor)
    return dados


def ler_form(tipo, form, base=None):
    """Lê do formulário os valores de todos os campos. `base` são os dados gravados (mantém as chaves internas '_...'
    e as perguntas de modelos dinâmicos). Campos calculados não vêm do formulário: saem de `calcular_campos`."""
    base = base or {}
    dados = {k: v for k, v in base.items() if k.startswith('_')}
    for c in campos(tipo, base):
        if c['tipo'] == 'multipla':
            dados[c['chave']] = [v for v in form.getlist(c['chave']) if v in (c.get('opcoes') or [])]
        elif c['tipo'] == 'sinais':
            for k in chaves_do_campo(c):
                dados[k] = (form.get(k) or '').strip()
        elif c['tipo'] == 'calculado':
            dados[c['chave']] = base.get(c['chave'], '')
        else:
            v = (form.get(c['chave']) or '').strip()
            if c['tipo'] in TIPOS_ESCOLHA and v not in opcoes_de(c):
                v = ''
            dados[c['chave']] = v
    for k in list(base):   # chaves das seções dinâmicas que não vieram do formulário continuam as mesmas
        if not k.startswith('_') and k not in dados:
            dados[k] = base[k]
    return dados


def calcular_campos(tipo, dados):
    """Atualiza os campos calculados do documento (ex.: pontuação do NEWS, total do escore de cálcio)."""
    m = MODELOS[tipo]
    if 'calcular' in m:
        dados.update(m['calcular'](dados))
    return dados


def _visivel(campo, dados):
    """Campo condicional: só conta quando a resposta da condição é o valor esperado."""
    if not campo.get('cond'):
        return True
    chave, valor = campo['cond']
    return (dados.get(chave) or '') == valor


def _vazio(campo, dados):
    if campo['tipo'] == 'multipla':
        return not dados.get(campo['chave'])
    if campo['tipo'] == 'sinais':
        return not any((dados.get(k) or '').strip() for k in chaves_do_campo(campo))
    return not (dados.get(campo['chave']) or '').strip()


def chaves_faltando(tipo, dados):
    """Chaves dos campos obrigatórios que estão vazios (usadas para destacar os campos na tela)."""
    return [c['chave'] for c in campos(tipo, dados) if c.get('obrig') and _visivel(c, dados) and _vazio(c, dados)]


def faltando(tipo, dados):
    """Rótulos dos campos obrigatórios que estão vazios."""
    return [rotulo_de(tipo, k, dados) for k in chaves_faltando(tipo, dados)]


def texto_impressao(campo, dados):
    """Texto de um campo para a folha impressa. Vazio = '' (a folha sai com linha para escrever à mão)."""
    if campo['tipo'] == 'sinais':
        partes = []
        for k, rot, unid in SINAIS_SUB:
            valor = (dados.get(campo['chave'] + '_' + k) or '').strip()
            if valor:
                partes.append('%s %s%s' % (rot, valor, (' ' + unid) if unid else ''))
        return '; '.join(partes)
    if campo['tipo'] == 'multipla':
        marcados = dados.get(campo['chave']) or []
        if not marcados:
            return ''
        return '   '.join(('( X ) ' if o in marcados else '(   ) ') + o for o in campo.get('opcoes') or [])
    valor = (dados.get(campo['chave']) or '').strip() if isinstance(dados.get(campo['chave']), str) else ''
    if campo['tipo'] in TIPOS_ESCOLHA:
        if not valor:
            return ''
        return '   '.join(('( X ) ' if o == valor else '(   ) ') + o for o in opcoes_de(campo))
    return valor
