"""Módulos do sistema, permissões por usuário, menu e mapa endpoint -> módulo."""
import json

# (chave, nome, grupo, descrição curta)
MODULOS = [
    ('dashboard', 'Dashboard', 'Visão geral', 'Indicadores e gráficos de atendimentos'),
    ('atendimentos', 'Atendimentos', 'Lançamentos', 'Lançar atendimentos, imprimir/reimprimir fichas'),
    ('prontuario', 'Prontuário do paciente', 'Lançamentos', 'Prontuário com número, histórico de atendimentos, SBAR e documentos clínicos'),
    ('medicamentos', 'Medicamentos', 'Lançamentos', 'Agenda de doses de iodo, gálio e PCI'),
    ('exames_lanc', 'Lançamento de exames', 'Lançamentos', 'Controle de realização dos exames (rádio-fármaco, lote, atividade) como na planilha EXAMES'),
    ('guias', 'Protocolo de guias', 'Lançamentos', 'Guias de convênio do período'),
    ('caixa', 'Caixa', 'Lançamentos', 'Recebimentos de particular, SMS e Mais Med'),
    ('movimento_caixa', 'Movimento de caixa', 'Lançamentos', 'Abertura e fechamento diário do caixa, recebimentos com quitação, troco e relatório para assinatura'),
    ('caixa_diario', 'Caixa diário da empresa', 'Financeiro', 'Controle de caixa da empresa com as contas BB, Unicred, Caixa e dinheiro, saldos em cadeia e planilha do dia'),
    ('laudos', 'Mapa de laudos', 'Lançamentos', 'Acompanhar cada exame: processando imagem, laudando e liberado para entrega'),
    ('ona', 'Relatório ONA', 'Qualidade', 'Indicadores de qualidade no formato da ONA: identificação, registro, prazo de laudo e comparecimento'),
    ('qualidade_gestao', 'Gestão da qualidade', 'Qualidade', 'Indicadores, robô do PDCA, Pareto, Ishikawa, 5 Porquês, GUT, risco, 5W2H, SWOT, fluxogramas, protocolos (POPs), organograma, ocorrências e modelos prontos'),
    ('qualidade_fornecedores', 'Avaliação de fornecedores', 'Qualidade', 'Avaliação periódica dos fornecedores com critérios e relatório para a ONA'),
    ('clientes', 'Clientes', 'Cadastros', 'Cadastro e consulta de clientes'),
    ('convenios', 'Convênios', 'Cadastros', 'Cadastro de convênios e valores'),
    ('medicos', 'Médicos', 'Cadastros', 'Médicos solicitantes'),
    ('exames', 'Exames e fichas', 'Cadastros', 'Quais fichas cada exame imprime'),
    ('contas', 'Contas a pagar', 'Financeiro', 'Despesas, vencimentos e quitação'),
    ('tabela_precos', 'Tabela de preços', 'Financeiro', 'Preços dos exames por tabela (particular e outras), reajuste, PDF e impressão'),
    ('faturamento', 'Faturamento', 'Financeiro', 'Notas fiscais, tributos, líquido e recebimentos'),
    ('faturamento_dash', 'Faturamento: relatórios', 'Financeiro', 'Dashboard financeiro por convênio'),
    ('relatorios', 'Relatórios de atendimentos', 'Financeiro', 'Atendimentos por exame, convênio, médico...'),
    ('documentos', 'Atestados e declarações', 'Outros', 'Atestado, declarações e recibo'),
    ('pastas', 'Pastas', 'Outros', 'Atalhos das pastas da rede'),
    ('bh_consulta', 'Banco de Horas: consulta', 'Banco de Horas', 'Saldos, extratos, relatórios, escala e histórico (somente ver)'),
    ('bh_gestao', 'Banco de Horas: gestão', 'Banco de Horas', 'Cadastrar funcionários e jornadas, importar o ponto, corrigir dias, ajustar saldos, emitir relatórios e editar a escala'),
    ('bh_dp', 'Departamento Pessoal', 'Banco de Horas', 'Pasta de documentos e folhas de ponto assinadas dos funcionários'),
    ('bh_mensagens', 'Mensagens com funcionários (antigo)', 'Banco de Horas', 'Substituído pelas mensagens livres, que todos os usuários já têm'),
    ('bh_portal', 'Minha área (funcionário)', 'Banco de Horas', 'O funcionário vê só o próprio banco de horas e a situação dos documentos'),
    ('agenda', 'Agenda de exames', 'Agenda', 'Marcar pacientes por exame e dia, controlar presença, lista de espera e impressão da agenda'),
    ('agenda_leitura', 'Agenda: só consulta e impressão', 'Agenda', 'Ver a agenda e imprimir o dia, sem poder alterar nada (perfil de estagiário)'),
    ('agenda_relatorios', 'Relatórios da agenda', 'Agenda', 'Quantos pacientes vieram, faltaram ou remarcaram, por período, exame e convênio'),
    ('agenda_financeiro', 'Financeiro da Agenda', 'Financeiro', 'Faturamento e repasse médico por convênio e tipo de exame (pacientes atendidos: veio ou retorno)'),
    ('agenda_faltas', 'Faltas e reagendamento', 'Agenda', 'Pacientes que faltaram, por exame e período, com contato direto para convidar a reagendar'),
    ('resgate_relatorio', 'Relatório de resgate', 'Financeiro', 'Quantos pacientes que faltaram cada usuário resgatou (reagendados e desistências)'),
    ('arquivo_documentos', 'Documentos', 'Documentos', 'Upload de contratos e de documentos de fiscalização, com nome e data de vencimento'),
    ('gerencia', 'Gerência (avisos de vencimento)', 'Documentos', 'Recebe, no contato do sistema, os avisos de documentos de fiscalização que vão vencer'),
    ('blind_cadastro', 'Cadastro de blindagem', 'Controle de Blindagens', 'Cadastrar blindagens (lote, nota fiscal, série, CFOP e validade) e acompanhar o status'),
    ('blind_devolucao', 'Solicitar devolução', 'Controle de Blindagens', 'Solicitar a devolução das blindagens vencidas e gerar a planilha e os documentos de transporte'),
    ('blind_devolvida', 'Confirmar devolução', 'Controle de Blindagens', 'Registrar a data em que cada blindagem com devolução solicitada foi devolvida (status DEVOLVIDA)'),
    ('suporte_dev', 'Suporte ao desenvolvedor: formulários e pasta', 'Administração', 'Ver os formulários enviados (sugestões e correções de bugs), aceitar ou recusar e gerar o relatório da próxima atualização (perfil do desenvolvedor)'),
    ('enfermagem', 'Enfermagem e Segurança', 'Enfermagem e Segurança', 'Carrinho de emergência, medicamentos, equipamentos, esterilização e radioproteção da enfermagem. Só vale depois que a assinatura do profissional for importada'),
    ('estoque', 'Estoque de materiais e medicamentos', 'Estoque', 'Cadastro de materiais e medicamentos, entradas e baixas, ajuste de inventário, histórico de compras e estoque mínimo (avisa a gerência)'),
    ('usuarios_gerir', 'Gerenciar usuários', 'Administração', 'Criar e editar usuários comuns (nunca a gestão nem o desenvolvedor) e entregar só os módulos que a própria pessoa tem. Só a gestão libera'),
    ('registros', 'Registros de atividades', 'Administração', 'Quem fez o quê e quando (auditoria)'),
    ('acessos', 'Log de acessos', 'Administração', 'Entradas e saídas do sistema'),
    ('backup', 'Backup', 'Administração', 'Cópias de segurança do banco'),
    ('configuracoes', 'Dados da clínica', 'Administração', 'Nome, cidade e CNPJ dos documentos'),
]
CHAVES = [m[0] for m in MODULOS]
NOMES = {m[0]: m[1] for m in MODULOS}

# Quem já existia antes da criação dos perfis mantém o que tinha: tudo, menos o que era só do administrador.
LEGADO = [k for k in CHAVES if k not in ('exames', 'exames_lanc', 'faturamento', 'faturamento_dash', 'registros', 'acessos', 'backup', 'configuracoes',
                                         'agenda_relatorios', 'agenda_financeiro', 'agenda_faltas', 'resgate_relatorio',
                                         'arquivo_documentos', 'gerencia', 'agenda_leitura', 'suporte_dev', 'enfermagem', 'usuarios_gerir',
                                         'prontuario', 'estoque')
          and not k.startswith('bh_') and not k.startswith('blind_')]

PRESETS = {
    'recepcao': ('Recepção', ['dashboard', 'atendimentos', 'medicamentos', 'guias', 'caixa', 'movimento_caixa', 'clientes', 'convenios', 'medicos',
                              'documentos', 'pastas', 'agenda']),
    'agenda': ('Agenda de exames', ['dashboard', 'agenda']),
    # estagiário: lança atendimentos (fichas) e só consulta/imprime a agenda, sem alterar
    'estagiario': ('Estagiário (lança fichas e vê a agenda)', ['atendimentos', 'agenda_leitura']),
    'financeiro': ('Financeiro', ['dashboard', 'caixa', 'contas', 'faturamento', 'faturamento_dash', 'relatorios', 'convenios',
                                  'agenda_financeiro', 'tabela_precos']),
    'documentos_gerencia': ('Gerência (documentos e avisos)', ['dashboard', 'arquivo_documentos', 'gerencia']),
    'tecnologo': ('Técnico (exames realizados)', ['dashboard', 'atendimentos', 'exames_lanc', 'clientes', 'medicos', 'prontuario']),
    'banco_horas': ('Banco de Horas (equipe)', ['bh_consulta', 'bh_gestao', 'bh_dp']),
    'blindagens': ('Controle de blindagens', ['dashboard', 'blind_cadastro', 'blind_devolucao', 'blind_devolvida']),
    'tudo': ('Todos os módulos', [k for k in CHAVES if k not in ('suporte_dev', 'enfermagem', 'usuarios_gerir')]),   # a caixa do desenvolvedor não vai no "todos
    'nenhum': ('Limpar', []),
}

# Ícone de cada tela do menu: o NOME do desenho no sprite static/img/icones.svg (Lucide, ISC; traço fino, currentColor).
# Usado na barra lateral, na barra do topo e nos favoritos. Para trocar um desenho, use outro nome do sprite.
ICONES = {
    'inicio.painel': 'house', 'nucleai.painel': 'bot', 'nucleaiia.pagina': 'atom', 'nucleaiia.tokens': 'chart-column', 'chat.conversa': 'message-square', 'dash.dashboard': 'layout-dashboard', 'dash.paineis': 'layout-dashboard', 'fav.painel': 'star', 'lem.painel': 'list-checks',
    'pront.indice': 'heart-pulse', 'atend.novo': 'clipboard-plus', 'atend.lista': 'clipboard-list','atend.caixa': 'wallet', 'mov.pagina': 'receipt', 'cxd.pagina': 'banknote', 'laudo.quadro': 'kanban',
    'atend.guias': 'files', 'lanc.editar': 'pen-line', 'lanc.lista': 'radiation', 'med.editar': 'pill', 'med.lista': 'syringe',
    'agenda.pagina': 'calendar-days', 'agenda.relatorio': 'chart-column', 'agenda.faltas': 'calendar-x', 'agenda.financeiro': 'badge-dollar-sign', 'agenda.reservas_pagina': 'files',
    'cad.clientes': 'users', 'cad.convenios': 'handshake', 'cad.medicos': 'stethoscope', 'cad.exames': 'flask-conical', 'lanc.cores': 'palette',
    'fat.lista': 'calculator', 'fat.emissao': 'file-text', 'fat.recebidas': 'badge-dollar-sign', 'fin.contas': 'credit-card', 'fat.dashboard': 'trending-up', 'fin.relatorios': 'file-chart-column', 'agenda.resgates': 'repeat',
    'preco.lista': 'badge-dollar-sign', 'preco.consulta': 'calculator',
    'arq.lista': 'folder-open', 'ona.pagina': 'award', 'qual.central': 'layout-grid', 'qual.kpi': 'gauge', 'qual.robo_pagina': 'bot', 'qual.pdca': 'refresh-cw',
    'qual.pareto': 'chart-column', 'qual.ishikawa': 'git-branch', 'qual.porques': 'circle-help', 'qual.gut': 'calculator',
    'qual.riscos': 'triangle-alert', 'qual.plano': 'list-checks', 'qual.swot': 'grid-2x2', 'qual.fluxos': 'workflow',
    'enf.painel': 'layout-grid', 'enf.carrinho': 'heart-pulse', 'enf.medicamentos': 'pill', 'enf.equipamentos': 'gauge', 'enf.esterilizacao': 'flask-conical',
    'enf.radioprotecao': 'radiation', 'enf.profissionais': 'badge-check',
    'est.itens': 'clipboard-list', 'est.movimentos': 'scroll-text', 'est.pedidos': 'clipboard-check',
    'est.relatorios': 'file-chart-column', 'est.escrituracao': 'file-text', 'est.precos': 'calculator',
    'qual.protocolos': 'scroll-text', 'qual.epidemio': 'users', 'qual.organograma': 'network', 'qual.ocorrencias': 'clipboard-list', 'qual.forn': 'handshake',
    'blind.lista': 'shield', 'blind.novo': 'shield-plus', 'blind.devolucao': 'undo-2', 'blind.devolvidas': 'shield-check',
    'doc.indice': 'file-text', 'admin.pastas': 'folder-tree',
    'bh.painel': 'timer', 'bh.funcionarios': 'contact', 'bh.importacoes': 'file-down', 'bh.escala': 'calendar-range', 'bh.dp_indice': 'folder-archive',
    'bh.historico': 'history', 'bh.portal_home': 'user-round',
    'auth.minha_senha': 'user-cog', 'admin.usuarios': 'users', 'saude.pagina': 'heart-pulse', 'reg.registros': 'scroll-text', 'admin.acessos': 'log-in',
    'admin.backup': 'database-backup', 'admin.configuracoes': 'settings', 'admin.mensagens_whats': 'message-square', 'medc.pagina': 'user-round', 'mpend.lista': 'cloud-upload',
    'adm.painel': 'settings', 'bh.adm': 'contact',
    'qual.satisf': 'message-square', 'ajuda.comandos': 'bot', 'sup.sugestao': 'lightbulb', 'sup.bug': 'bug', 'sup.recebidos': 'inbox', 'sup.pasta': 'clipboard-check', 'sup.dados': 'database-backup',
}
# ícone de cada tema (grupo) do menu
TEMA_ICONES = {
    'Lançamentos': 'notebook-pen', 'Agenda': 'calendar', 'Cadastros': 'book-user', 'Financeiro': 'banknote', 'Documentos': 'files',
    'Qualidade': 'badge-check', 'Enfermagem e Segurança': 'heart-pulse', 'Estoque': 'folder-archive', 'Controle de Blindagens': 'shield-half', 'Outros': 'layout-grid', 'Banco de Horas': 'clock', 'Configuração': 'settings-2',
}
ICONE_PADRAO = 'layout-grid'
# todos os desenhos do sprite: o seletor de símbolos dos favoritos oferece exatamente estes
NOMES_ICONES = sorted(set(ICONES.values()) | set(TEMA_ICONES.values()) | {'atom'})
ICONES_SUGERIDOS = NOMES_ICONES


# Menu lateral: (grupo, [(módulo, rótulo, endpoint, prefixos de endpoint que marcam o item como ativo)])
MENU = [
    # ordem por relevância de uso no dia a dia: o que a recepção abre o tempo todo fica no topo
    (None, [(None, 'Início', 'inicio.painel', ('inicio.',)), ('__admin__', 'NucleAI', 'nucleai.painel', ('nucleai.',)),
            (None, 'Suporte ao desenvolvedor', 'sup.sugestao', ()),
            (None, 'Mensagens', 'chat.conversa', ('chat.',)), ('dashboard', 'Dashboard', 'dash.dashboard', ('dash.',)),
            (None, 'Meus favoritos', 'fav.painel', ('fav.',)), (None, 'Lembretes', 'lem.painel', ('lem.',))]),
    ('Agenda', [
        (('agenda', 'agenda_leitura'), 'Agenda de exames', 'agenda.pagina', ('agenda.',)),
    ]),
    ('Lançamentos', [
        ('atendimentos', 'Atendimentos', 'atend.lista', ('atend.lista', 'atend.imprimir', 'atend.excluir', 'atend.novo')),
        ('prontuario', 'Prontuário do paciente', 'pront.indice', ('pront.',)),
        ('laudos','Mapa de laudos', 'laudo.quadro', ('laudo.',)),
        (('atendimentos', 'laudos'), 'Pendências Medcloud', 'mpend.lista', ('mpend.',)),
        ('guias', 'Protocolo de guias', 'atend.guias', ('atend.guia',)),
        ('exames_lanc', 'Exames realizados', 'lanc.lista', ('lanc.lista', 'lanc.editar', 'lanc.imprimir', 'lanc.exportar', 'lanc.excluir', 'lanc.atend', 'lanc.sugestao', 'lanc.do_dia')),
        ('medicamentos', 'Agenda de medicamentos', 'med.lista', ('med.lista', 'med.imprimir', 'med.status', 'med.editar')),
    ]),
    ('Cadastros', [
        ('clientes', 'Clientes', 'cad.clientes', ('cad.cliente',)),
        ('convenios', 'Convênios', 'cad.convenios', ('cad.convenio',)),
        ('medicos', 'Médicos', 'cad.medicos', ('cad.medico',)),
        ('exames', 'Exames e fichas', 'cad.exames', ('cad.exame', 'lanc.cores')),
    ]),
    ('Financeiro', [
        ('caixa', 'Caixa', 'atend.caixa', ('atend.caixa',)),
        ('movimento_caixa', 'Movimento de caixa', 'mov.pagina', ('mov.',)),
        ('caixa_diario', 'Caixa diário da empresa', 'cxd.pagina', ('cxd.',)),
        ('faturamento', 'Faturamento', 'fat.lista', ()),
        ('contas', 'Contas a pagar', 'fin.contas', ('fin.conta',)),
        ('tabela_precos', 'Tabela de preços', 'preco.lista', ('preco.',)),
        ('faturamento_dash', 'Faturamento: relatórios', 'fat.dashboard', ('fat.dashboard',)),
        ('relatorios', 'Relatórios de atendimentos', 'fin.relatorios', ('fin.relatorios',)),
        ('resgate_relatorio', 'Relatório de resgate', 'agenda.resgates', ('agenda.resgates',)),
    ]),
    ('Estoque', [
        ('estoque', 'Estoque', 'est.itens', ('est.',)),
    ]),
    ('Documentos', [
        ('arquivo_documentos', 'Documentos', 'arq.lista', ('arq.',)),
    ]),
    ('Qualidade', [
        ('qualidade_gestao', 'Qualidade', 'qual.central', ()),
    ]),
    ('Enfermagem e Segurança', [
        ('enfermagem', 'Enfermagem e Segurança', 'enf.painel', ()),
    ]),
    ('Controle de Blindagens', [
        ('blind_cadastro', 'Cadastro de blindagem', 'blind.lista', ('blind.',)),
    ]),
    ('Outros', [
        ('documentos', 'Atestados e declarações', 'doc.indice', ('doc.',)),
        ('pastas', 'Pastas', 'admin.pastas', ('admin.pastas',)),
    ]),
    ('Banco de Horas', [
        ('bh_consulta', 'Painel de saldos', 'bh.painel', ('bh.painel', 'bh.extrato', 'bh.correcao', 'bh.ajuste', 'bh.relatorio', 'bh.pesquisa')),
        ('bh_consulta', 'Escala mensal', 'bh.escala', ('bh.escala',)),
        ('bh_dp', 'Departamento Pessoal', 'bh.dp_indice', ('bh.dp_',)),
        ('bh_consulta', 'Administração do ponto', 'bh.adm', ()),
        ('bh_portal', 'Minha área', 'bh.portal_home', ('bh.portal_home',)),
    ]),
    ('Configuração', [
        (None, 'Minha conta', 'auth.minha_senha', ('auth.minha_senha', 'nov.')),
        (None, 'Administração', 'adm.painel', ()),
    ]),
]

# Telas que viram botões (abas) dentro de outra. O item do menu lateral (a chave) abre a primeira aba permitida, e a barra de
# botões aparece no topo de todas as telas do grupo. Cada aba continua exigindo o seu próprio módulo: quem não tem a permissão
# não vê o botão (e, se não tiver nenhuma das abas, o item some do menu). Aba: (módulo, rótulo, endpoint, prefixos de endpoint).
ABAS = {
    'qual.central': [
        ('qualidade_gestao', 'Central da qualidade', 'qual.central', ('qual.central',)),
        ('qualidade_gestao', 'Indicadores (KPI)', 'qual.kpi', ('qual.kpi',)),
        ('qualidade_gestao', 'Robô do PDCA', 'qual.robo_pagina', ('qual.robo',)),
        ('qualidade_gestao', 'Ciclo PDCA', 'qual.pdca', ('qual.pdca', 'qual.problema', 'qual.causa')),
        ('qualidade_gestao', 'Gráfico de Pareto', 'qual.pareto', ('qual.pareto', 'qual.falta')),
        ('qualidade_gestao', 'Diagrama de Ishikawa', 'qual.ishikawa', ('qual.ishikawa',)),
        ('qualidade_gestao', 'Cinco porquês', 'qual.porques', ('qual.porques',)),
        ('qualidade_gestao', 'Matriz GUT', 'qual.gut', ('qual.gut',)),
        ('qualidade_gestao', 'Matriz de risco', 'qual.riscos', ('qual.risco',)),
        ('qualidade_gestao', 'Plano de ação 5W2H', 'qual.plano', ('qual.plano', 'qual.acao')),
        ('qualidade_gestao', 'Matriz SWOT', 'qual.swot', ('qual.swot',)),
        ('qualidade_gestao', 'Fluxograma de processos', 'qual.fluxos', ('qual.fluxo',)),
        ('qualidade_gestao', 'Perfil epidemiológico', 'qual.epidemio', ('qual.epidemio',)),
        ('qualidade_gestao', 'Protocolos (POPs)', 'qual.protocolos', ('qual.protocolo',)),
        ('qualidade_gestao', 'Organograma', 'qual.organograma', ('qual.organograma', 'qual.org_')),
        ('qualidade_gestao', 'Ocorrências e satisfação', 'qual.ocorrencias', ('qual.ocorrencia', 'qual.pesquisa')),
        ('qualidade_gestao', 'Pesquisa de satisfação (QR Code)', 'qual.satisf', ('qual.satisf',)),
        ('qualidade_fornecedores', 'Avaliação de fornecedores', 'qual.forn', ('qual.forn',)),
        ('ona', 'Relatório ONA', 'ona.pagina', ('ona.',)),
    ],
    'enf.painel': [
        ('enfermagem', 'Painel da enfermagem', 'enf.painel', ('enf.painel', 'enf.responsaveis')),
        ('enfermagem', 'Carrinho de emergência', 'enf.carrinho', ('enf.carrinho',)),
        ('enfermagem', 'Medicamentos e insumos', 'enf.medicamentos', ('enf.medicamento', 'enf.reposicao', 'enf.temperatura')),
        ('enfermagem', 'Equipamentos médicos', 'enf.equipamentos', ('enf.equipamento', 'enf.teste')),
        ('enfermagem', 'Esterilização', 'enf.esterilizacao', ('enf.pacote', 'enf.esteriliza')),
        ('enfermagem', 'Radioproteção da enfermagem', 'enf.radioprotecao', ('enf.rp', 'enf.radioprotecao')),
        ('enfermagem', 'Profissionais e assinaturas', 'enf.profissionais', ('enf.profissionais', 'enf.assinatura')),
    ],
    'est.itens': [
        ('estoque', 'Itens', 'est.itens', ('est.itens', 'est.item_', 'est.entrada', 'est.saida', 'est.ajuste', 'est.historico')),
        ('estoque', 'Movimentações', 'est.movimentos', ('est.movimentos',)),
        ('estoque', 'Pedidos', 'est.pedidos', ('est.pedido',)),
        ('estoque', 'Relatórios do estoque', 'est.relatorios', ('est.relatorios',)),
        ('estoque', 'Escrituração', 'est.escrituracao', ('est.escrituracao',)),
        ('estoque', 'Preços dos materiais', 'est.precos', ('est.precos',)),
    ],
    'atend.lista': [
        ('atendimentos', 'Atendimentos', 'atend.lista', ('atend.lista', 'atend.imprimir', 'atend.excluir')),
        ('atendimentos', 'Lançar atendimento', 'atend.novo', ('atend.novo',)),
    ],
    'lanc.lista': [
        ('exames_lanc', 'Exames realizados', 'lanc.lista', ('lanc.lista', 'lanc.imprimir', 'lanc.exportar', 'lanc.excluir', 'lanc.atend', 'lanc.sugestao', 'lanc.do_dia')),
        ('exames_lanc', 'Lançar exame realizado', 'lanc.editar', ('lanc.editar',)),
    ],
    'med.lista': [
        ('medicamentos', 'Agenda de medicamentos', 'med.lista', ('med.lista', 'med.imprimir', 'med.status')),
        ('medicamentos', 'Agendar medicamento', 'med.editar', ('med.editar',)),
    ],
    'agenda.pagina': [
        (('agenda', 'agenda_leitura'), 'Agenda de exames', 'agenda.pagina', ('agenda.',)),
        ('agenda_relatorios', 'Relatórios da agenda', 'agenda.relatorio', ('agenda.relatorio',)),
        ('agenda_faltas', 'Faltas e reagendamento', 'agenda.faltas', ('agenda.faltas',)),
        ('agenda_financeiro', 'Financeiro da Agenda', 'agenda.financeiro', ('agenda.financeiro',)),
        ('agenda', 'Reservas do convênio', 'agenda.reservas_pagina', ('agenda.reservas',)),
    ],
    # faturamento em três momentos: cadastro da fatura, emissão da nota fiscal e recebimento (com a glosa)
    'fat.lista': [
        ('faturamento', 'Faturamento', 'fat.lista', ('fat.lista', 'fat.editar', 'fat.excluir', 'fat.protocolo', 'fat.resumo')),
        ('faturamento', 'Emissão da nota fiscal', 'fat.emissao', ('fat.emissao', 'fat.emitir', 'fat.desfazer_emissao')),
        ('faturamento', 'Recebidas', 'fat.recebidas', ('fat.recebidas', 'fat.quitar', 'fat.reabrir')),
    ],
    'preco.lista': [
        ('tabela_precos', 'Tabela de preços', 'preco.lista', ('preco.lista', 'preco.editar', 'preco.acao', 'preco.pdf')),
        ('tabela_precos', 'Consulta rápida', 'preco.consulta', ('preco.consulta',)),
    ],
    'cad.exames': [
        ('exames', 'Exames e fichas', 'cad.exames', ('cad.exame',)),
        ('exames', 'Cores dos exames', 'lanc.cores', ('lanc.cores',)),
    ],
    'blind.lista': [
        ('blind_cadastro', 'Cadastro de blindagem', 'blind.lista', ('blind.lista', 'blind.editar', 'blind.excluir')),
        ('blind_cadastro', 'Novo cadastro', 'blind.novo', ('blind.novo',)),
        ('blind_devolucao', 'Solicitar devolução', 'blind.devolucao', ('blind.devolucao', 'blind.planilha', 'blind.documento')),
        ('blind_devolvida', 'Confirmar devolução', 'blind.devolvidas', ('blind.devolvidas',)),
    ],
    'bh.adm': [
        ('bh_consulta', 'Funcionários do ponto', 'bh.funcionarios', ('bh.funcionario', 'bh.portal_acesso')),
        ('bh_consulta', 'Importar ponto', 'bh.importacoes', ('bh.importac',)),
        ('bh_consulta', 'Histórico do ponto', 'bh.historico', ('bh.historico',)),
    ],
    'sup.sugestao': [
        (None, 'Sugestão', 'sup.sugestao', ('sup.sugestao',)),
        (None, 'Correção de bug', 'sup.bug', ('sup.bug',)),
        ('suporte_dev', 'Formulários recebidos', 'sup.recebidos', ('sup.recebidos', 'sup.decidir')),
        ('suporte_dev', 'Pasta de aceitos', 'sup.pasta', ('sup.pasta', 'sup.texto', 'sup.situacao', 'sup.aplicar', 'sup.relatorio')),
        ('suporte_dev', 'Dados protegidos', 'sup.dados', ('sup.dados',)),
    ],
    'adm.painel': [
        ('usuarios_gerir', 'Usuários e perfis', 'admin.usuarios', ('admin.usuario',)),
        ('gerencia', 'Saúde do sistema', 'saude.pagina', ('saude.',)),
        ('registros', 'Registros de atividades', 'reg.registros', ('reg.',)),
        ('acessos', 'Log de acessos', 'admin.acessos', ('admin.acessos',)),
        ('backup', 'Backup', 'admin.backup', ('admin.backup',)),
        ('configuracoes', 'Dados da clínica', 'admin.configuracoes', ('admin.configuracoes',)),
        ('gerencia', 'Mensagens do WhatsApp', 'admin.mensagens_whats', ('admin.mensagens_whats',)),
        ('gerencia', 'Medcloud (portal do paciente)', 'medc.pagina', ('medc.',)),
        ('gerencia', 'Comandos da NucleAI', 'ajuda.comandos', ('ajuda.comandos',)),
        ('gerencia', 'NucleAI: IA online', 'nucleaiia.pagina', ('nucleaiia.pagina',)),
        ('gerencia', 'Gasto de tokens (NucleAI)', 'nucleaiia.tokens', ('nucleaiia.tokens',)),
        ('gerencia', 'Painéis do Início', 'dash.paineis', ('dash.paineis',)),
    ],
}


def modulos_do_usuario(u):
    """Conjunto de módulos liberados. Administrador vê todos; NULL = perfil legado."""
    if u is None:
        return set()
    if u['admin']:
        return set(CHAVES)
    bruto = u['modulos']
    if bruto is None:
        return set(LEGADO)
    try:
        mods = set(json.loads(bruto)) & set(CHAVES)
    except (ValueError, TypeError):
        return set()
    if 'bh_gestao' in mods:  # quem gerencia o banco de horas também consulta
        mods.add('bh_consulta')
    return mods


# endpoints do Banco de Horas que alteram dados (exigem "gestão"); os demais bh.* só consultam
BH_GESTAO = {'funcionario_novo', 'funcionario_editar', 'funcionario_jornada', 'importacao_enviar', 'correcao', 'ajuste',
             'relatorio_pdf', 'escala_salvar', 'portal_acesso_criar', 'portal_acesso_atualizar', 'ocorrencia_tratar'}


def _modulo_bh(ep):
    nome = ep[3:]
    if nome in {'portal_home', 'portal_ocorrencia'}:
        return 'bh_portal'
    if nome.startswith('mensagens') or nome.startswith('msg'):
        return ('bh_mensagens', 'bh_portal')  # equipe ou funcionário
    if nome.startswith('dp_'):
        return 'bh_dp'
    if nome in BH_GESTAO:
        return 'bh_gestao'
    return 'bh_consulta'


# telas da agenda que só leem (o estagiário, com "Agenda: só consulta e impressão", usa só estas)
AGENDA_SO_LEITURA = {'agenda.pagina', 'agenda.dia', 'agenda.mes', 'agenda.imprimir'}


def modulo_do_endpoint(ep):
    """Módulo exigido por um endpoint. None = livre (login, painel, APIs); '__admin__' = só administrador.
    Uma tupla significa "qualquer um destes módulos"."""
    if ep in ('chat.canal_salvar', 'chat.canal_excluir', 'chat.canal_enviar', 'chat.ilustracao_excel'):
        return None   # canais exigem Gestão na própria rota; ilustração valida o destinatário na própria rota
    if ep == 'ajuda.comandos':
        return 'gerencia'   # quem pode pedir o quê à NucleAI: administração e gerência
    if ep and ep.startswith('bh.'):
        return _modulo_bh(ep)
    if ep in ('laudo.prazo', 'laudo.limpar', 'laudo.entregues', 'laudo.retificar'):
        return 'gerencia'   # prazo, limpeza do mapa, laudos entregues e retificação: só administração e gerência
    if ep and ep.startswith('sup.'):
        # enviar sugestão e correção de bug é de todos; ver os formulários, decidir e a pasta são do perfil do desenvolvedor (e do administrador)
        return None if ep.startswith(('sup.sugestao', 'sup.bug')) else 'suporte_dev'
    if ep == 'admin.mensagens_whats':
        return 'gerencia'   # textos do WhatsApp da agenda: só administração e gerência
    if ep and ep.startswith('medc.'):
        return 'gerencia'   # login, convênios e fila do robô da Medcloud: só administração e gerência
    if ep and ep.startswith('mpend.'):
        return ('atendimentos', 'laudos')   # pendências de anexos e laudos dos estudos: quem lança atendimentos ou cuida de laudos
    if ep and ep.startswith('pesq.'):
        return None   # pesquisa de satisfação do cliente: página pública (só dentro da rede, a própria rota confere)
    if ep and ep.startswith('arq.'):
        return 'arquivo_documentos'
    if ep and ep.startswith('agenda.'):
        if ep.startswith('agenda.financeiro'):
            return 'agenda_financeiro'
        if ep.startswith('agenda.faltas'):
            return 'agenda_faltas'
        if ep.startswith('agenda.resgates'):
            return 'resgate_relatorio'
        if ep in AGENDA_SO_LEITURA:
            return ('agenda', 'agenda_leitura')   # ver e imprimir: também o perfil só de consulta
        return 'agenda_relatorios' if ep.startswith('agenda.relatorio') else 'agenda'
    if ep and ep.startswith('blind.'):
        if ep.startswith('blind.devolvidas'):
            return 'blind_devolvida'
        return 'blind_devolucao' if ep.startswith(('blind.devolucao', 'blind.planilha', 'blind.documento')) else 'blind_cadastro'
    if ep and ep.startswith('lanc.'):
        if ep == 'lanc.cores':
            return 'exames'
        return '__admin__' if ep == 'lanc.importar' else 'exames_lanc'
    if not ep or ep == 'static' or ep.startswith('auth.') or ep == 'inicio.painel' or ep.startswith('inicio.api') \
            or ep.startswith('ajuda.') or ep.startswith(('fav.', 'nov.', 'lem.')):
        return None
    if ep == 'dash.paineis':
        return 'gerencia'
    if ep.startswith('dash.'):
        return 'dashboard'
    if ep.startswith('atend.guia'):
        return 'guias'
    if ep.startswith('atend.caixa'):
        return 'caixa'
    if ep.startswith('nucleaiia.'):
        return 'gerencia'   # IA online (treino, níveis, memória, liberar, trocas): administração e gerência
    if ep.startswith('nucleai.'):
        return '__admin__'  # painel, conteúdo, configurações e chamados da NucleAI: só administração
    if ep.startswith('mov.'):
        return 'movimento_caixa'
    if ep.startswith('cxd.'):
        return 'caixa_diario'
    if ep.startswith('laudo.'):
        return 'laudos'
    if ep.startswith('ona.'):
        return 'ona'
    if ep.startswith('enf.'):
        return 'enfermagem'
    if ep.startswith('est.'):
        return 'estoque'
    if ep.startswith('qual.forn'):
        return 'qualidade_fornecedores'
    if ep.startswith('qual.'):
        return 'qualidade_gestao'
    if ep in ('atu.pendente', 'atu.estado', 'atu.iniciar'):
        return None  # instalador e tela de espera: sem login (a própria rota restringe o acesso)
    if ep == 'atu.avisar':
        return ('backup', 'gerencia')
    if ep and ep.startswith('saude.'):
        return 'gerencia'  # saúde do sistema: administração e gerência
    if ep.startswith('atend.'):
        return 'atendimentos'
    if ep.startswith('med.'):
        return 'medicamentos'
    if ep.startswith('cad.cliente'):
        return 'clientes'
    if ep.startswith('cad.convenio'):
        return 'convenios'
    if ep.startswith('cad.medico'):
        return 'medicos'
    if ep.startswith('cad.exame'):
        return 'exames'
    if ep.startswith('fin.conta'):
        return 'contas'
    if ep.startswith('fin.relatorios'):
        return 'relatorios'
    if ep == 'fat.dashboard':
        return 'faturamento_dash'
    if ep.startswith('fat.'):
        return 'faturamento'
    if ep.startswith('doc.'):
        return 'documentos'
    if ep.startswith('admin.pastas'):
        return 'pastas'
    if ep.startswith(('admin.backup_restaurar', 'admin.backup_pasta', 'admin.backup_destino', 'admin.backup_automatico')):
        return 'gerencia'   # restaurar backup (inclusive buscar em outra pasta): só administração e gerência
    if ep.startswith('admin.backup'):
        return ('backup', 'gerencia')   # fazer/baixar backup: módulo Backup (a gerência também, pelo botão da Saúde do sistema)
    if ep == 'admin.acessos':
        return 'acessos'
    if ep == 'admin.configuracoes':
        return 'configuracoes'
    if ep.startswith('reg.'):
        return 'registros'
    if ep.startswith('admin.usuario'):
        return 'usuarios_gerir'
    if ep and ep.startswith('preco.'):
        return 'tabela_precos'
    if ep and ep.startswith('pront.'):
        return 'prontuario'
    return None


def telas():
    """Todas as telas do sistema: [(tema, módulo de permissão, rótulo, endpoint)]. Inclui as que viraram botões (abas)."""
    saida = []
    for grupo, itens in MENU:
        for mod, rotulo, ep, _pref in itens:
            if ep in ABAS:
                saida += [(grupo, a[0], a[1], a[2]) for a in ABAS[ep]]
            else:
                saida.append((grupo, mod, rotulo, ep))
    return saida


def _permitido(u, modulos, mod):
    if mod is None:
        return True
    if mod == '__admin__':
        return bool(u and u['admin'])
    return mod in modulos if isinstance(mod, str) else any(m in modulos for m in mod)


def _abas_visiveis(u, modulos, ep):
    return [a for a in ABAS.get(ep, ()) if _permitido(u, modulos, a[0])]


def _dono_do_endpoint(endpoint):
    """Qual item do menu (ou aba) é o dono do endpoint: o que tem o prefixo mais longo que combina. (chave do item, aba|None)."""
    if not endpoint:
        return None
    melhor, tam = None, 0
    for _grupo, itens in MENU:
        for _mod, _rotulo, ep, prefixos in itens:
            if ep in ABAS:
                for a in ABAS[ep]:
                    for p in a[3]:
                        if endpoint.startswith(p) and len(p) > tam:
                            melhor, tam = (ep, a[2]), len(p)
            for p in prefixos:
                if endpoint.startswith(p) and len(p) > tam:
                    melhor, tam = (ep, None), len(p)
    return melhor


def montar_menu(u, modulos, endpoint, incluir_abas=False):
    """Menu visível para o usuário, com o item ativo marcado. Com `incluir_abas`, cada aba vira um item próprio
    (usado pelos favoritos, que precisam enxergar todas as telas)."""
    from flask import url_for
    saida = []
    so_funcionario = bool(u and u['bh_funcionario_id'] and not u['admin'])
    dono = _dono_do_endpoint(endpoint)

    def item_de(rotulo, ep, grupo, ativo, url=None, extra=''):
        return {'rotulo': rotulo, 'url': url or url_for(ep), 'badge': None, 'ep': ep, 'grupo': grupo or 'Geral',
                'icone': ICONES.get(ep, ICONE_PADRAO), 'ativo': ativo, 'busca': extra}

    for grupo, itens in MENU:
        visiveis = []
        for mod, rotulo, ep, prefixos in itens:
            if so_funcionario and ep.startswith(('inicio.', 'fav.')):
                continue
            if mod == 'bh_portal' and not so_funcionario:
                continue
            if ep in ABAS:
                abas = _abas_visiveis(u, modulos, ep)
                if not abas:
                    continue
                if incluir_abas:
                    for a in abas:
                        visiveis.append(item_de(a[1], a[2], grupo, False))
                else:
                    extra = ' '.join(a[1] for a in abas)   # a pesquisa do menu também encontra as telas que viraram botões
                    if abas[0][2] != ep and ABAS[ep][0][2] == ep:
                        rotulo = abas[0][1]   # sem acesso à tela principal: o item leva o nome da tela a que a pessoa tem acesso
                    novo = item_de(rotulo, ep, grupo, bool(dono) and dono[0] == ep, url_for(abas[0][2]), extra)
                    if ep == 'sup.sugestao' and any(a[0] == 'suporte_dev' for a in abas):   # o desenvolvedor vê quantos formulários esperam decisão
                        from . import suporte
                        from .db import get_db
                        novo['selo'] = suporte.contar_novos(get_db()) or None
                    visiveis.append(novo)
                continue
            if not _permitido(u, modulos, mod):
                continue
            item = item_de(rotulo, ep, grupo, bool(dono) and dono[0] == ep and dono[1] is None)
            if ep == 'chat.conversa':
                from . import chat
                from .db import get_db
                item['badge'] = chat.nao_lidas_total(get_db(), u['id'])
            visiveis.append(item)
        if visiveis:
            saida.append((grupo, visiveis))
    return saida


def montar_abas(u, modulos, endpoint):
    """Barra de botões da tela atual: {'grupo', 'itens': [{rotulo, url, ativo, icone}], 'atual'} ou None quando a tela não
    faz parte de um grupo de abas (ou quando só há uma aba permitida, caso em que não há o que escolher)."""
    from flask import url_for
    dono = _dono_do_endpoint(endpoint)
    if not u or not dono or dono[0] not in ABAS:
        return None
    abas = _abas_visiveis(u, modulos, dono[0])
    if len(abas) < 2:
        return None
    grupo = next((g for g, itens in MENU for i in itens if i[2] == dono[0]), None)
    # tela que não é de nenhuma aba específica (ex.: página interna do grupo): o botão do item principal fica marcado
    alvo = dono[1] or abas[0][2]
    itens = [{'rotulo': a[1], 'url': url_for(a[2]), 'ativo': a[2] == alvo, 'icone': ICONES.get(a[2], ICONE_PADRAO), 'ep': a[2]} for a in abas]
    atual = next((i for i in itens if i['ativo']), None)
    return {'grupo': grupo or 'Geral', 'itens': itens, 'atual': atual}
