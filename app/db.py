"""Acesso ao banco SQLite: conexão por requisição, esquema e dados iniciais."""
import json
import os
import secrets
import sqlite3
from datetime import datetime

from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
    senha_hash TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    admin INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT,
    modulos TEXT,
    criado_por TEXT
);
CREATE TABLE IF NOT EXISTS faturas (
    id INTEGER PRIMARY KEY,
    convenio TEXT NOT NULL,
    referencia TEXT NOT NULL,
    nota_fiscal TEXT,
    valor_bruto REAL NOT NULL DEFAULT 0,
    tributos REAL NOT NULL DEFAULT 0,
    valor_liquido REAL NOT NULL DEFAULT 0,
    previsao TEXT,
    status TEXT NOT NULL DEFAULT 'ABERTO',
    data_recebimento TEXT,
    valor_recebido REAL,
    banco_recebimento TEXT,
    obs TEXT,
    usuario TEXT,
    quitado_por TEXT,
    atualizado_por TEXT,
    criado_em TEXT,
    atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_faturas_ref ON faturas(referencia);
CREATE INDEX IF NOT EXISTS ix_faturas_conv ON faturas(convenio);
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY,
    data_hora TEXT NOT NULL,
    usuario TEXT,
    modulo TEXT,
    acao TEXT,
    detalhe TEXT,
    rota TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_data ON auditoria(data_hora);
CREATE INDEX IF NOT EXISTS ix_audit_usuario ON auditoria(usuario);
CREATE TABLE IF NOT EXISTS acessos (
    id INTEGER PRIMARY KEY,
    data_hora TEXT NOT NULL,
    usuario TEXT,
    evento TEXT,
    computador TEXT,
    detalhe TEXT
);
CREATE TABLE IF NOT EXISTS convenios (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
    gera_caixa INTEGER NOT NULL DEFAULT 0,
    valor_mibi REAL, valor_ossea REAL, valor_tgi REAL, valor_paratgi REAL, valor_galio REAL,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS medicos (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    crm TEXT
);
CREATE TABLE IF NOT EXISTS exames (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
    titulo_ficha TEXT,
    documentos TEXT NOT NULL DEFAULT '[]',
    questionario TEXT,
    pede_medicamentos INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    ordem INTEGER NOT NULL DEFAULT 100
);
-- valor que cada convênio paga por exame (1.5.0). Só existe linha quando o valor foi preenchido; todo exame cadastrado
-- aparece para todo convênio (inclusive os novos), então não é preciso "vincular" nada.
CREATE TABLE IF NOT EXISTS convenio_valores (
    convenio_id INTEGER NOT NULL,
    exame_id INTEGER NOT NULL,
    valor REAL NOT NULL,
    PRIMARY KEY (convenio_id, exame_id)
);
CREATE INDEX IF NOT EXISTS ix_conv_valores_exame ON convenio_valores(exame_id);
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    cpf TEXT,
    cep TEXT, rua TEXT, numero TEXT, complemento TEXT, bairro TEXT, cidade TEXT, uf TEXT,
    contato TEXT,
    convenio_id INTEGER,
    convenio TEXT,
    nome_mae TEXT,
    data_nasc TEXT,
    cartao_convenio TEXT,
    profissao TEXT,
    criado_em TEXT,
    atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_clientes_nome ON clientes(nome);
CREATE INDEX IF NOT EXISTS ix_clientes_cpf ON clientes(cpf);
CREATE TABLE IF NOT EXISTS atendimentos (
    id INTEGER PRIMARY KEY,
    cliente_id INTEGER,
    cliente_nome TEXT,
    cpf TEXT,
    medico TEXT,
    data TEXT,
    exame TEXT,
    convenio TEXT,
    medicamentos TEXT,
    exame_anterior TEXT,
    respostas TEXT,
    usuario TEXT,
    criado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_atend_cliente ON atendimentos(cliente_id);
CREATE INDEX IF NOT EXISTS ix_atend_data ON atendimentos(data);
CREATE TABLE IF NOT EXISTS guias (
    id INTEGER PRIMARY KEY,
    atendimento_id INTEGER,
    paciente TEXT,
    convenio TEXT,
    data TEXT,
    exame TEXT,
    horario TEXT,
    usuario TEXT
);
CREATE INDEX IF NOT EXISTS ix_guias_data ON guias(data);
CREATE TABLE IF NOT EXISTS caixa (
    id INTEGER PRIMARY KEY,
    atendimento_id INTEGER,
    data TEXT,
    cliente TEXT,
    cpf TEXT,
    procedimento TEXT,
    convenio TEXT,
    status TEXT NOT NULL DEFAULT 'ABERTO',
    usuario TEXT,
    nota_fiscal TEXT,
    valor REAL,
    forma_pagamento TEXT,
    obs TEXT
);
CREATE INDEX IF NOT EXISTS ix_caixa_data ON caixa(data);
CREATE TABLE IF NOT EXISTS doses (
    id INTEGER PRIMARY KEY,
    cliente_id INTEGER,
    paciente TEXT,
    data_nasc TEXT,
    contato TEXT,
    cpf TEXT,
    idade TEXT,
    medicamento TEXT,
    mci TEXT,
    preparo TEXT,
    dieta TEXT,
    susp_medicacao TEXT,
    data_dose TEXT,
    medico TEXT,
    status TEXT NOT NULL DEFAULT 'AGENDADO',
    obs TEXT,
    usuario TEXT,
    criado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_doses_data ON doses(data_dose);
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY,
    descricao TEXT NOT NULL,
    categoria TEXT,
    vencimento TEXT,
    valor REAL,
    obs TEXT,
    status TEXT NOT NULL DEFAULT 'ABERTO',
    banco_pagamento TEXT,
    forma_pagamento TEXT,
    fornecedor TEXT,
    nota_fiscal TEXT,
    data_pagamento TEXT,
    usuario TEXT
);
-- Contas recorrentes: geram uma conta em aberto por mês no dia escolhido (AUTOINCREMENT: o id nunca é reaproveitado)
CREATE TABLE IF NOT EXISTS contas_recorrentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT NOT NULL,
    categoria TEXT,
    valor REAL NOT NULL,
    dia_vencimento INTEGER NOT NULL CHECK (dia_vencimento BETWEEN 1 AND 31),
    fornecedor TEXT,
    fornecedor_id INTEGER,
    obs TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    mes_inicio TEXT NOT NULL,
    criado_em TEXT,
    criado_por TEXT
);
-- Lotes de pagamento: as contas marcadas em /contas viram um lote ligado a um banco
CREATE TABLE IF NOT EXISTS contas_lotes (id INTEGER PRIMARY KEY, banco TEXT NOT NULL, criado_em TEXT NOT NULL, criado_por TEXT, obs TEXT, status TEXT NOT NULL DEFAULT 'ABERTO', concluido_em TEXT);
-- Itens do lote: situacao 'EM PAGAMENTO', 'PAGA' ou 'DEVOLVIDA'
CREATE TABLE IF NOT EXISTS contas_lote_itens (id INTEGER PRIMARY KEY, lote_id INTEGER NOT NULL, conta_id INTEGER NOT NULL, situacao TEXT NOT NULL DEFAULT 'EM PAGAMENTO', atualizado_em TEXT, atualizado_por TEXT, UNIQUE(lote_id, conta_id));
-- Fornecedores do contas a pagar (cadastro manual ou pela consulta do CNPJ); o CNPJ é opcional, mas único quando informado
CREATE TABLE IF NOT EXISTS fornecedores (
    id INTEGER PRIMARY KEY,
    cnpj TEXT,
    nome TEXT NOT NULL,
    fantasia TEXT,
    telefone TEXT,
    email TEXT,
    endereco TEXT,
    cidade TEXT,
    uf TEXT,
    contato TEXT,
    obs TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT,
    criado_por TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_fornecedores_cnpj ON fornecedores(cnpj) WHERE cnpj IS NOT NULL;
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

-- Controle de realização de exames (planilha EXAMES.xlsx): uma linha por exame realizado
CREATE TABLE IF NOT EXISTS exame_cores (
    id INTEGER PRIMARY KEY,
    chave TEXT NOT NULL UNIQUE,
    rotulo TEXT NOT NULL,
    cor TEXT NOT NULL,
    padroes TEXT NOT NULL DEFAULT '',
    ordem INTEGER NOT NULL DEFAULT 100,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS realizacoes (
    id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    numero INTEGER,
    codigo TEXT,
    cliente_id INTEGER,
    paciente TEXT NOT NULL,
    sexo TEXT,
    data_nasc TEXT,
    idade TEXT,
    peso REAL,
    altura REAL,
    convenio TEXT,
    medico_id INTEGER,
    medico TEXT,
    cid TEXT,
    radio TEXT,
    eluicao TEXT,
    farmaco TEXT,
    lote TEXT,
    ativ_prescrita TEXT,
    ativ_administrada TEXT,
    exame TEXT,
    hora_injecao TEXT,
    hora_exame TEXT,
    responsavel TEXT,
    obs TEXT,
    cor_planilha TEXT,
    origem TEXT,
    atendimento_id INTEGER,
    criado_por TEXT,
    criado_em TEXT,
    atualizado_por TEXT,
    atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_realiz_data ON realizacoes(data);
CREATE INDEX IF NOT EXISTS ix_realiz_paciente ON realizacoes(paciente);
CREATE INDEX IF NOT EXISTS ix_realiz_cliente ON realizacoes(cliente_id);

-- Fichas personalizadas: documentos criados pela própria clínica e impressos junto com o atendimento
CREATE TABLE IF NOT EXISTS fichas_extras (
    id INTEGER PRIMARY KEY,
    titulo TEXT NOT NULL,
    conteudo TEXT NOT NULL DEFAULT '',
    cabecalho INTEGER NOT NULL DEFAULT 1,
    ativa INTEGER NOT NULL DEFAULT 1,
    criado_por TEXT,
    criado_em TEXT,
    atualizado_por TEXT,
    atualizado_em TEXT
);

-- Banco de Horas (módulo vindo do programa autônomo; mesmas colunas, tabelas com prefixo bh_)
CREATE TABLE IF NOT EXISTS bh_employees (
    id INTEGER PRIMARY KEY, clock_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
    start_date TEXT NOT NULL, end_date TEXT,
    opening_balance_minutes INTEGER NOT NULL DEFAULT 0,
    opening_balance_date TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    is_intern INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bh_schedules (
    id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES bh_employees(id),
    effective_date TEXT NOT NULL, weekdays_json TEXT NOT NULL,
    required_break_minutes INTEGER NOT NULL DEFAULT 0,
    two_punch_policy TEXT NOT NULL DEFAULT 'review',
    deduct_break_minutes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, actor TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    UNIQUE(employee_id,effective_date)
);
CREATE TABLE IF NOT EXISTS bh_imports (
    id INTEGER PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT UNIQUE NOT NULL,
    period_start TEXT NOT NULL, period_end TEXT NOT NULL,
    created_at TEXT NOT NULL, actor TEXT NOT NULL,
    file_bytes BLOB NOT NULL, counters_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bh_import_rows (
    id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES bh_imports(id),
    clock_id TEXT NOT NULL, imported_name TEXT NOT NULL, date TEXT NOT NULL,
    punches_json TEXT NOT NULL, raw_text TEXT NOT NULL,
    parse_error TEXT NOT NULL DEFAULT '',
    accepted INTEGER NOT NULL DEFAULT 1, is_conflict INTEGER NOT NULL DEFAULT 0,
    UNIQUE(import_id,clock_id,date)
);
CREATE UNIQUE INDEX IF NOT EXISTS bh_canonical_attendance ON bh_import_rows(clock_id,date) WHERE accepted = 1;
CREATE INDEX IF NOT EXISTS bh_attendance_clock_date ON bh_import_rows(clock_id,date);
CREATE TABLE IF NOT EXISTS bh_corrections (
    id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES bh_employees(id),
    date TEXT NOT NULL, punches_json TEXT NOT NULL, kind TEXT NOT NULL,
    reason TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS bh_correction_dates ON bh_corrections(employee_id,date,id);
CREATE TABLE IF NOT EXISTS bh_ocorrencias (
    id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES bh_employees(id),
    data TEXT NOT NULL, tipo TEXT NOT NULL, horarios_json TEXT NOT NULL DEFAULT '[]',
    observacao TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDENTE',
    criado_por TEXT NOT NULL, criado_em TEXT NOT NULL,
    tratado_por TEXT, tratado_em TEXT, parecer TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS bh_ocorrencias_pendentes ON bh_ocorrencias(status,employee_id,data);
CREATE TABLE IF NOT EXISTS bh_adjustments (
    id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES bh_employees(id),
    date TEXT NOT NULL, minutes INTEGER NOT NULL, reason TEXT NOT NULL,
    actor TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS bh_adjustment_dates ON bh_adjustments(employee_id,date);
CREATE TABLE IF NOT EXISTS bh_audit_log (
    id INTEGER PRIMARY KEY, occurred_at TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id INTEGER,
    employee_id INTEGER REFERENCES bh_employees(id), reason TEXT NOT NULL DEFAULT '',
    before_json TEXT, after_json TEXT
);
CREATE TABLE IF NOT EXISTS bh_report_snapshots (
    id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES bh_employees(id),
    month TEXT NOT NULL, version INTEGER NOT NULL, issued_at TEXT NOT NULL,
    content_hash TEXT NOT NULL, snapshot_json TEXT NOT NULL, pdf_bytes BLOB NOT NULL,
    UNIQUE(employee_id,month,version)
);
CREATE TABLE IF NOT EXISTS bh_roster_days (
    employee_id INTEGER NOT NULL REFERENCES bh_employees(id), date TEXT NOT NULL,
    kind TEXT NOT NULL, start_time TEXT NOT NULL DEFAULT '', end_time TEXT NOT NULL DEFAULT '',
    break_minutes INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(employee_id,date)
);
CREATE TABLE IF NOT EXISTS bh_employee_documents (
    id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES bh_employees(id),
    category TEXT NOT NULL, title TEXT NOT NULL, month TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL, content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL, content BLOB NOT NULL, note TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT NOT NULL, actor TEXT NOT NULL,
    archived_at TEXT, archived_by TEXT, archive_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS bh_employee_documents_lookup ON bh_employee_documents(employee_id,category);
CREATE TABLE IF NOT EXISTS bh_messages (
    id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES bh_employees(id),
    sender_user_id INTEGER NOT NULL REFERENCES usuarios(id), sender_role TEXT NOT NULL,
    sender_label TEXT NOT NULL, sender_name TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS bh_messages_thread ON bh_messages(employee_id,id);
CREATE TABLE IF NOT EXISTS bh_message_threads (
    employee_id INTEGER PRIMARY KEY REFERENCES bh_employees(id),
    staff_read_id INTEGER NOT NULL DEFAULT 0, employee_read_id INTEGER NOT NULL DEFAULT 0
);

-- Mensagens livres: qualquer usuário conversa com qualquer outro (estilo WhatsApp). Fica gravada até ser lida.
CREATE TABLE IF NOT EXISTS chat_mensagens (
    id INTEGER PRIMARY KEY,
    de_id INTEGER NOT NULL REFERENCES usuarios(id),
    para_id INTEGER NOT NULL REFERENCES usuarios(id),
    corpo TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    lida_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_chat_para ON chat_mensagens(para_id, lida_em);
CREATE INDEX IF NOT EXISTS ix_chat_par ON chat_mensagens(de_id, para_id, id);

CREATE TABLE IF NOT EXISTS chat_canais (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    nome TEXT NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_canal_membros (
    canal_id INTEGER NOT NULL REFERENCES chat_canais(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    PRIMARY KEY (canal_id, usuario_id)
);

-- Suporte ao desenvolvedor: formulários de sugestão e de correção de bug enviados pelos usuários, e a pasta dos aceitos
CREATE TABLE IF NOT EXISTS suporte_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,                      -- SUGESTAO ou BUG
    titulo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    tela TEXT,
    passos TEXT,                             -- bug: como acontece
    gravidade TEXT,                          -- bug: IMPEDE, ATRAPALHA ou PEQUENO
    usuario_id INTEGER,
    usuario TEXT,
    criado_em TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'NOVA',     -- NOVA, ACEITA (na pasta), RECUSADA ou APLICADA (já entrou numa atualização)
    decidido_por TEXT,
    decidido_em TEXT,
    texto_atualizacao TEXT,                  -- texto mais didático escrito na pasta, para o relatório da atualização
    versao TEXT,
    aplicada_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_suporte_status ON suporte_itens(status, tipo);
CREATE INDEX IF NOT EXISTS ix_suporte_usuario ON suporte_itens(usuario_id, tipo);

-- Agenda de exames (independente do cadastro de pacientes): uma agenda = um exame em um dia, com suas linhas de horário
CREATE TABLE IF NOT EXISTS agenda_exames (
    id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    exame TEXT NOT NULL,
    inicio TEXT NOT NULL,
    intervalo INTEGER NOT NULL,
    vagas INTEGER NOT NULL DEFAULT 1,
    criado_por TEXT,
    criado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_agenda_data ON agenda_exames(data);
-- ordem escolhida pela recepção para as agendas de cada exame (botões ↑ ↓ na tela da agenda); exame sem linha usa a ordem de criação
CREATE TABLE IF NOT EXISTS agenda_ordem_exames (
    exame TEXT PRIMARY KEY,
    posicao INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS agenda_horarios (
    id INTEGER PRIMARY KEY,
    agenda_id INTEGER NOT NULL REFERENCES agenda_exames(id) ON DELETE CASCADE,
    hora TEXT NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0,
    paciente TEXT NOT NULL DEFAULT '',
    convenio TEXT NOT NULL DEFAULT '',
    contato TEXT NOT NULL DEFAULT '',
    senha TEXT NOT NULL DEFAULT '',
    observacao TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'AGENDADO',
    remarcado_para TEXT,
    atualizado_por TEXT,
    atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_agenda_hor_agenda ON agenda_horarios(agenda_id);
-- registro de cada alteração feita numa linha da agenda (quem, quando, o quê, valor antes e depois)
CREATE TABLE IF NOT EXISTS agenda_log (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    usuario TEXT,
    horario_id INTEGER,
    agenda_id INTEGER,
    data TEXT,
    hora TEXT,
    paciente TEXT,
    acao TEXT NOT NULL,
    campo TEXT,
    antes TEXT,
    depois TEXT
);
CREATE INDEX IF NOT EXISTS ix_agenda_log_hor ON agenda_log(horario_id);
CREATE INDEX IF NOT EXISTS ix_agenda_log_data ON agenda_log(data);
CREATE TABLE IF NOT EXISTS agenda_espera (
    id INTEGER PRIMARY KEY,
    exame TEXT NOT NULL DEFAULT '',
    nome TEXT NOT NULL,
    convenio TEXT NOT NULL DEFAULT '',
    contato TEXT NOT NULL DEFAULT '',
    observacao TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'AGUARDANDO',
    criado_por TEXT,
    criado_em TEXT,
    encaixado_em TEXT
);
CREATE TABLE IF NOT EXISTS agenda_bloqueios (
    data TEXT PRIMARY KEY,
    motivo TEXT NOT NULL DEFAULT '',
    criado_por TEXT,
    criado_em TEXT
);
CREATE TABLE IF NOT EXISTS agenda_modelos (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
    exame TEXT NOT NULL,
    inicio TEXT NOT NULL,
    intervalo INTEGER NOT NULL,
    qtd INTEGER NOT NULL,
    vagas INTEGER NOT NULL DEFAULT 1
);

-- Presença: uma linha por aba aberta; a pessoa conta como online enquanto a aba bate (ver presenca.py)
CREATE TABLE IF NOT EXISTS presenca (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    aba TEXT NOT NULL,
    visto REAL NOT NULL,
    PRIMARY KEY (usuario_id, aba)
);
CREATE INDEX IF NOT EXISTS ix_presenca_visto ON presenca(visto);

-- Controle de blindagens (geradores de tecnécio): cadastro, validade e devolução
CREATE TABLE IF NOT EXISTS blindagem_devolucoes (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    valor_unitario REAL
);
CREATE TABLE IF NOT EXISTS blindagens (
    id INTEGER PRIMARY KEY,
    lote TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nota_fiscal TEXT NOT NULL,
    serie TEXT NOT NULL,
    data_nota TEXT NOT NULL,
    cfop TEXT NOT NULL,
    validade TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'VÁLIDO',
    devolucao_id INTEGER REFERENCES blindagem_devolucoes(id),
    criado_por TEXT,
    criado_em TEXT,
    atualizado_por TEXT,
    atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_blind_status ON blindagens(status);
CREATE INDEX IF NOT EXISTS ix_blind_validade ON blindagens(validade);
-- Módulo Documentos: contratos e documentos de fiscalização (com vencimento). O arquivo fica no próprio banco.
CREATE TABLE IF NOT EXISTS arquivos_docs (
    id INTEGER PRIMARY KEY,
    tipo TEXT NOT NULL,
    nome TEXT NOT NULL,
    vencimento TEXT,
    arquivo_nome TEXT NOT NULL,
    content_type TEXT NOT NULL,
    tamanho INTEGER NOT NULL DEFAULT 0,
    conteudo BLOB NOT NULL,
    criado_por TEXT,
    criado_em TEXT,
    atualizado_por TEXT,
    atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_arquivos_tipo ON arquivos_docs(tipo, vencimento);
-- Movimento de caixa: uma sessão (abertura e fechamento) por usuário e por dia.
CREATE TABLE IF NOT EXISTS caixa_sessoes (
    id INTEGER PRIMARY KEY,
    usuario TEXT NOT NULL,
    data TEXT NOT NULL,
    fundo REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ABERTO',
    aberto_em TEXT,
    fechado_em TEXT,
    fechado_por TEXT,
    alertado_em TEXT,
    obs TEXT,
    UNIQUE (usuario, data)
);
CREATE INDEX IF NOT EXISTS ix_caixa_sessoes_status ON caixa_sessoes(status);
-- Avisos de atualização disparados pela gestão (prazo para salvar o trabalho antes de o programa ser encerrado).
-- NucleAI: conteúdo da ajuda editado ou criado pela administração (a base original fica no código).
-- EDITADA troca o texto de uma área existente; NOVA é uma área (ou módulo/tema) criada pela administração.
CREATE TABLE IF NOT EXISTS ajuda_conteudo (
    id INTEGER PRIMARY KEY,
    tema TEXT NOT NULL,
    modulo TEXT NOT NULL,
    area TEXT NOT NULL,
    texto TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL,
    chave_acesso TEXT,
    atualizado_em TEXT,
    atualizado_por TEXT,
    UNIQUE (tema, modulo, area)
);
-- NucleAI: o chat é apagado, mas a essência (dúvida, quem chamou, se resolveu, nota) fica e alimenta o painel e os relatórios.
CREATE TABLE IF NOT EXISTS ajuda_registros (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    usuario_id INTEGER,
    usuario TEXT,
    tema TEXT,
    modulo TEXT,
    area TEXT,
    origem TEXT NOT NULL DEFAULT 'LISTA',
    duvida TEXT,
    resultado TEXT,
    nota INTEGER,
    chamou_gerencia INTEGER NOT NULL DEFAULT 0,
    respondido_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_ajuda_registros_data ON ajuda_registros (criado_em);
-- Dúvidas escritas que a NucleAI não entendeu: mostram o que falta na base de ajuda.
CREATE TABLE IF NOT EXISTS ajuda_nao_entendidas (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    usuario_id INTEGER,
    usuario TEXT,
    texto TEXT
);
-- Pedidos de ajuda enviados à gerência pela NucleAI.
CREATE TABLE IF NOT EXISTS ajuda_chamados (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    usuario_id INTEGER NOT NULL,
    usuario TEXT,
    registro_id INTEGER,
    tema TEXT,
    modulo TEXT,
    area TEXT,
    duvida TEXT,
    status TEXT NOT NULL DEFAULT 'ABERTO',
    atendido_por TEXT,
    atendido_por_id INTEGER,
    atendido_em TEXT,
    confirmou TEXT,
    confirmado_em TEXT,
    gerencia_online INTEGER NOT NULL DEFAULT 0,
    avisados INTEGER NOT NULL DEFAULT 0
);
-- Conversa de ajuda com a NucleAI (temporária): onde o usuário está na árvore tema -> módulo -> área.
CREATE TABLE IF NOT EXISTS ajuda_sessoes (
    usuario_id INTEGER PRIMARY KEY,
    estado TEXT NOT NULL,
    tema INTEGER,
    modulo INTEGER,
    area INTEGER,
    gerencia_chamada INTEGER NOT NULL DEFAULT 0,
    atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS atualizacao_avisos (
    id INTEGER PRIMARY KEY,
    criado_em TEXT,
    criado_por TEXT,
    prazo_min INTEGER,
    ate TEXT,
    destinatarios INTEGER
);
-- Um aviso por documento, por data de vencimento e por fase (60, 30, 15, 7, 1 e 0 dias, ou VENCIDO).
CREATE TABLE IF NOT EXISTS docs_avisos (
    documento_id INTEGER NOT NULL,
    vencimento TEXT NOT NULL,
    fase TEXT NOT NULL,
    enviado_em TEXT,
    PRIMARY KEY (documento_id, vencimento, fase)
);
-- índices acrescentados na 1.5.0 depois do teste de sobrecarga (2 a 20 milhões de linhas)
CREATE INDEX IF NOT EXISTS ix_atend_cli_data ON atendimentos(cliente_id, data);
-- cobre as contagens e os rankings do dashboard (exame, convênio, médico, usuário, paciente) sem ler a tabela
CREATE INDEX IF NOT EXISTS ix_atend_painel ON atendimentos(data, exame, convenio, medico, usuario, cliente_id);
CREATE INDEX IF NOT EXISTS ix_atend_exame ON atendimentos(exame);
CREATE INDEX IF NOT EXISTS ix_atend_usuario ON atendimentos(usuario);
CREATE INDEX IF NOT EXISTS ix_audit_modulo ON auditoria(modulo);
CREATE INDEX IF NOT EXISTS ix_contas_status_venc ON contas(status, vencimento);
CREATE INDEX IF NOT EXISTS ix_caixa_status ON caixa(status);
CREATE INDEX IF NOT EXISTS ix_chat_para_id ON chat_mensagens(para_id, id);
CREATE INDEX IF NOT EXISTS ix_acessos_data ON acessos(data_hora);
-- Lembretes em checklist (app/lembretes.py): o lembrete é do dono, ou "para todos" (criado pela gestão); cada usuário guarda as suas marcações
CREATE TABLE IF NOT EXISTS lembretes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    titulo TEXT NOT NULL,
    para_todos INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    data_inicio TEXT NOT NULL,
    reset_diario INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT
);
CREATE TABLE IF NOT EXISTS lembrete_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lembrete_id INTEGER NOT NULL REFERENCES lembretes(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL,
    texto TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lembrete_itens ON lembrete_itens(lembrete_id, ordem);
CREATE TABLE IF NOT EXISTS lembrete_marcas (
    lembrete_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    marcado_em TEXT,
    data TEXT NOT NULL,
    PRIMARY KEY (item_id, usuario_id)
);
-- NucleAI (IA online, Gemini): nível de acesso de cada usuário (0 a 4; 0 = sem acesso).
CREATE TABLE IF NOT EXISTS nucleai_llm_nivel (
    usuario_id INTEGER PRIMARY KEY,
    nivel INTEGER NOT NULL DEFAULT 0,
    atualizado_em TEXT,
    atualizado_por TEXT
);
-- Contagem diária de perguntas e tokens por usuário (limite diário pelo nível).
CREATE TABLE IF NOT EXISTS nucleai_llm_uso (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL,
    dia TEXT NOT NULL,
    qtd INTEGER NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0,
    UNIQUE (usuario_id, dia)
);
-- Registro de cada resposta: modo 'IA' (Gemini), 'REGRAS' (resposta automática por queda/cota) ou 'EVENTO' (liberação/desativação).
CREATE TABLE IF NOT EXISTS nucleai_llm_log (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    usuario_id INTEGER,
    usuario TEXT,
    treinador TEXT,
    pergunta TEXT,
    resposta TEXT,
    ferramentas TEXT,
    tokens INTEGER NOT NULL DEFAULT 0,
    modo TEXT NOT NULL DEFAULT 'IA',
    nota INTEGER,
    autoavaliacao TEXT
);
CREATE INDEX IF NOT EXISTS ix_nucleai_llm_log_data ON nucleai_llm_log (criado_em);
-- Gasto de tokens da NucleAI: registro por pedido para acompanhamento e gráficos da gerência.
CREATE TABLE IF NOT EXISTS nucleai_tokens (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    usuario_id INTEGER,
    usuario TEXT NOT NULL,
    modelo TEXT NOT NULL,
    tokens_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_saida INTEGER NOT NULL DEFAULT 0,
    tokens_total INTEGER NOT NULL DEFAULT 0,
    tempo_ms INTEGER NOT NULL DEFAULT 0,
    teste INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_nucleai_tokens_data ON nucleai_tokens (criado_em);
CREATE INDEX IF NOT EXISTS ix_nucleai_tokens_usuario ON nucleai_tokens (usuario);
CREATE INDEX IF NOT EXISTS ix_nucleai_tokens_modelo ON nucleai_tokens (modelo);
-- Treinadores: personalidade da IA (formalidade, tamanho e força de 1 a 5).
CREATE TABLE IF NOT EXISTS nucleai_treinadores (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE,
    tratamento TEXT,
    tom TEXT,
    formalidade INTEGER NOT NULL DEFAULT 3,
    tamanho INTEGER NOT NULL DEFAULT 3,
    forca INTEGER NOT NULL DEFAULT 3,
    criado_em TEXT,
    atualizado_em TEXT
);
-- Memória da IA (GEMINI.md e TREINAMENTO.txt): o banco é a fonte (entra no backup e passa pelas atualizações);
-- uma cópia em arquivo fica na pasta de dados para leitura e edição manual.
CREATE TABLE IF NOT EXISTS nucleai_memoria (
    arquivo TEXT PRIMARY KEY,
    conteudo TEXT NOT NULL DEFAULT '',
    atualizado_em TEXT,
    atualizado_por TEXT
);
-- Cada versão anterior da memória (para ver o histórico e reverter).
CREATE TABLE IF NOT EXISTS nucleai_memoria_versoes (
    id INTEGER PRIMARY KEY,
    arquivo TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    por TEXT,
    motivo TEXT
);
-- Estado da IA na conversa de cada usuário: modo 'IA' ou 'REGRAS' (sem internet) e a ação esperando o Sim/Não.
CREATE TABLE IF NOT EXISTS nucleai_llm_sessao (
    usuario_id INTEGER PRIMARY KEY,
    modo TEXT NOT NULL DEFAULT 'IA',
    pendente TEXT,
    atualizado_em TEXT
);
-- Conversa do chat de treinamento (aba IA online): fica guardada para revisão.
CREATE TABLE IF NOT EXISTS nucleai_treino_msgs (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    usuario_id INTEGER,
    treinador TEXT,
    papel TEXT NOT NULL,
    texto TEXT NOT NULL DEFAULT '',
    cartao TEXT
);
CREATE INDEX IF NOT EXISTS ix_nucleai_treino_msgs ON nucleai_treino_msgs (usuario_id, id);
-- Blocos visuais gerados pela ferramenta `ilustrar` da NucleAI (um id por bloco, permite substituição e decisão travada).
CREATE TABLE IF NOT EXISTS nucleai_ilustracoes (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    usuario_id INTEGER NOT NULL,
    treino INTEGER NOT NULL DEFAULT 0,
    tipo TEXT NOT NULL,
    titulo TEXT NOT NULL DEFAULT '',
    dados TEXT NOT NULL,
    substitui_id INTEGER,
    substituido_por INTEGER,
    decisao_resp TEXT,
    decisao_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_nucleai_ilustracoes ON nucleai_ilustracoes (usuario_id, treino, id);
-- pedidos de exame emitidos; o prontuário do paciente vai listar. O campo exames guarda um exame por linha.
CREATE TABLE IF NOT EXISTS pedidos_exame (
    id INTEGER PRIMARY KEY, cliente_id INTEGER, paciente TEXT NOT NULL, exames TEXT NOT NULL, data TEXT NOT NULL,
    medico TEXT, especialidade TEXT, registro TEXT, convenio TEXT, hipotese TEXT, observacoes TEXT, usuario TEXT, criado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_pedidos_exame_cliente ON pedidos_exame(cliente_id);
-- tabelas de preços dos exames (particular e outras). `codigo` é o código TUSS/CBHPM também usado nas guias SP/SADT;
-- `vigencia` é a data ISO de início da tabela
CREATE TABLE IF NOT EXISTS tabelas_preco (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, vigencia TEXT, obs TEXT, ativa INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT, criado_por TEXT, atualizado_em TEXT, atualizado_por TEXT
);
CREATE TABLE IF NOT EXISTS tabela_preco_itens (
    id INTEGER PRIMARY KEY, tabela_id INTEGER NOT NULL, exame_id INTEGER, codigo TEXT, descricao TEXT NOT NULL, valor REAL,
    obs TEXT, ordem INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_tabela_preco_itens ON tabela_preco_itens(tabela_id);
-- guias de convênio digitadas (SP/SADT Unimed e pedido IPSEMG). modelo = 'unimed_sadt' ou 'ipsemg_pedido'.
-- Os campos ficam em JSON em `dados`: chave = número do campo do formulário (ex.: "10"; "25_1" = linha 1 do campo 25).
CREATE TABLE IF NOT EXISTS guias_convenio (
    id INTEGER PRIMARY KEY, modelo TEXT NOT NULL, cliente_id INTEGER, atendimento_id INTEGER, paciente TEXT,
    dados TEXT NOT NULL DEFAULT '{}', usuario TEXT, criado_em TEXT, atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_guias_convenio_cliente ON guias_convenio(cliente_id);
-- prontuário do paciente: um por cliente, com número de 6 dígitos gerado na criação
CREATE TABLE IF NOT EXISTS prontuarios (id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL UNIQUE, numero TEXT NOT NULL UNIQUE, criado_em TEXT, criado_por TEXT);
-- documentos do prontuário (SBAR e os próximos modelos). situacao: PENDENTE (criado, ainda não aberto), RASCUNHO (salvo
-- parcialmente) ou CONCLUIDO (assinado no papel e fechado, só leitura). dados = JSON com os campos do modelo.
CREATE TABLE IF NOT EXISTS prontuario_docs (id INTEGER PRIMARY KEY, prontuario_id INTEGER NOT NULL, cliente_id INTEGER NOT NULL,
    atendimento_id INTEGER, tipo TEXT NOT NULL, titulo TEXT, dados TEXT NOT NULL DEFAULT '{}', situacao TEXT NOT NULL DEFAULT 'PENDENTE',
    profissional_nome TEXT, profissional_conselho TEXT, profissional_registro TEXT, criado_em TEXT, criado_por TEXT, atualizado_em TEXT, atualizado_por TEXT,
    concluido_em TEXT, concluido_por TEXT);
CREATE INDEX IF NOT EXISTS ix_prontuario_docs_cliente ON prontuario_docs(cliente_id);
CREATE INDEX IF NOT EXISTS ix_prontuario_docs_atend ON prontuario_docs(atendimento_id);
CREATE INDEX IF NOT EXISTS ix_prontuario_docs_situacao ON prontuario_docs(situacao);
-- Estoque de materiais e medicamentos (independente da enfermagem). saldo é o saldo atual; cada movimento guarda o saldo_apos.
CREATE TABLE IF NOT EXISTS est_itens (
    id INTEGER PRIMARY KEY,
    codigo TEXT,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'MATERIAL',
    unidade TEXT,
    local TEXT,
    estoque_minimo REAL NOT NULL DEFAULT 0,
    saldo REAL NOT NULL DEFAULT 0,
    ultimo_valor REAL,
    ultima_compra TEXT,
    alerta_enviado INTEGER NOT NULL DEFAULT 0,
    obs TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT,
    criado_por TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_est_itens_nome ON est_itens(tipo, nome COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS est_movimentos (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES est_itens(id),
    data_hora TEXT NOT NULL,
    tipo TEXT NOT NULL,
    sentido INTEGER NOT NULL,
    qtd REAL NOT NULL,
    valor_unitario REAL,
    fornecedor_id INTEGER,
    fornecedor_nome TEXT,
    documento TEXT,
    lote TEXT,
    validade TEXT,
    data_documento TEXT,
    motivo TEXT,
    obs TEXT,
    usuario TEXT,
    saldo_apos REAL,
    pedido_id INTEGER
);
CREATE INDEX IF NOT EXISTS ix_est_mov_item ON est_movimentos(item_id, data_hora);
CREATE INDEX IF NOT EXISTS ix_est_mov_data ON est_movimentos(data_hora);
-- Pedidos de compra do estoque: cabeçalho (RASCUNHO, ENVIADO, RECEBIDO ou CANCELADO) e itens com o recebido de cada um.
CREATE TABLE IF NOT EXISTS est_pedidos (
    id INTEGER PRIMARY KEY,
    numero TEXT NOT NULL UNIQUE,
    data TEXT NOT NULL,
    fornecedor_id INTEGER,
    fornecedor_nome TEXT,
    status TEXT NOT NULL DEFAULT 'RASCUNHO',
    condicoes TEXT,
    observacao TEXT,
    solicitante TEXT,
    criado_por TEXT,
    criado_em TEXT,
    enviado_em TEXT,
    recebido_em TEXT,
    cancelado_em TEXT
);
CREATE TABLE IF NOT EXISTS est_pedido_itens (
    id INTEGER PRIMARY KEY,
    pedido_id INTEGER NOT NULL REFERENCES est_pedidos(id),
    item_id INTEGER NOT NULL REFERENCES est_itens(id),
    qtd REAL NOT NULL,
    valor_unitario REAL,
    qtd_recebida REAL NOT NULL DEFAULT 0,
    obs TEXT
);
CREATE INDEX IF NOT EXISTS ix_est_ped_itens ON est_pedido_itens(pedido_id);
-- Integração Medcloud (app/medcloud.py): acesso do paciente ao portal (senha cifrada) e fila do robô por atendimento
CREATE TABLE IF NOT EXISTS medcloud_acessos (
    cliente_id INTEGER PRIMARY KEY,
    usuario TEXT NOT NULL,
    senha TEXT NOT NULL,
    qr TEXT,
    criado_em TEXT,
    atendimento_id INTEGER
);
CREATE TABLE IF NOT EXISTS medcloud_fila (
    id INTEGER PRIMARY KEY,
    atendimento_id INTEGER NOT NULL UNIQUE,
    cliente_id INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDENTE',
    tentativas INTEGER NOT NULL DEFAULT 0,
    erro TEXT,
    criado_em TEXT,
    atualizado_em TEXT
);
-- Arquivos (anexos e laudos) a enviar ao estudo na Medcloud (app/medcloud_envios.py). Enquanto esperam o robô o conteúdo fica no
-- anexos.db (anexo_id); sem anexos.db (banco em memória) fica na coluna conteudo. Depois de enviado (estado OK) o conteúdo é
-- apagado: a Medcloud é quem guarda o arquivo.
CREATE TABLE IF NOT EXISTS medcloud_envios (
    id INTEGER PRIMARY KEY,
    atendimento_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    arquivo_nome TEXT NOT NULL,
    content_type TEXT,
    tamanho INTEGER,
    sha256 TEXT,
    anexo_id INTEGER,
    conteudo BLOB,
    estado TEXT NOT NULL DEFAULT 'PENDENTE',
    tentativas INTEGER NOT NULL DEFAULT 0,
    erro TEXT,
    fase TEXT,
    criado_por TEXT,
    criado_em TEXT,
    atualizado_em TEXT,
    enviado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_medcloud_envios_estado ON medcloud_envios(estado);
CREATE INDEX IF NOT EXISTS ix_medcloud_envios_atend ON medcloud_envios(atendimento_id);
"""

# Documentos impressos por exame, como no VBA original (LANCAMENTO2 / FICHAGERAL /
# FICHALINFONODO). Cada item: [slug_da_ficha, cópias].
EXAMES_PADRAO = [
    # nome, título na ficha, documentos, questionário, pede medicamentos em uso
    ('MIBI', 'MIBI', [['ficha_mibi', 1], ['pnt_mibi', 1], ['termo_haroldo', 1], ['dr_haroldo', 1],
                      ['sae_mibi', 1], ['escore_news', 2]], None, 1),
    ('ÓSSEA', 'ÓSSEA', [['pnt_ossea', 1], ['ficha_geral', 1], ['sae_geral', 1]], None, 0),
    ('RENAL', 'RENAL', [['pnt_renal', 1], ['ficha_geral', 1], ['sae_geral', 1]], None, 0),
    ('DMSA', 'DMSA', [['pnt_renal', 1], ['ficha_geral', 1], ['sae_geral', 1]], None, 0),
    ('DTPA', 'DTPA', [['pnt_renal', 1], ['ficha_geral', 1], ['sae_geral', 1]], None, 0),
    ('PULMONAR', 'PULMONAR', [['pnt_pulmonar', 1], ['ficha_geral', 1], ['sae_geral', 1],
                              ['escore_news', 2]], None, 0),
    ('LINFONODO', 'LINFONODO', [['pnt_linfonodo', 1], ['ficha_geral', 1], ['etiqueta_cliente', 1],
                                ['sae_geral', 1]], 'linfonodo', 0),
    ('IODO', 'DOSE IODO', [['ficha_geral', 1], ['sae_geral', 1]], None, 0),
    ('GALIO', 'GÁLIO', [['pnt_galio', 1], ['ficha_geral', 1], ['sae_geral', 1]], None, 0),
    ('PCI', 'DOSE PCI', [['ficha_geral', 1], ['etiqueta_cliente', 1], ['sae_geral', 1]], None, 0),
    ('SPECT', 'SPECT', [['pnt_spect', 1], ['ficha_geral', 1], ['sae_geral', 1]], None, 0),
    ('TGI', 'TIREOIDE', [['pnt_tgi', 1], ['ficha_geral', 1], ['sae_geral', 1]], None, 0),
    ('PARATGI', 'PARATIREOIDE', [['pnt_paratgi', 1], ['ficha_geral', 1], ['sae_geral', 1]], None, 0),
]
# Exames digitados livremente ("Lançar outros") usam este conjunto.
DOCUMENTOS_OUTROS = [['ficha_geral', 1], ['sae_geral', 1], ['etiqueta_cliente', 1]]

# Convênios cujo atendimento vai para o caixa (os demais geram protocolo de guia).
CONVENIOS_CAIXA = ('PARTICULAR', 'SMS', 'MAIS MED')

CONFIG_PADRAO = {
    # integração Medcloud: função desligada até a gerência ativar; login e senha (cifrada) são gravados pela tela
    'medcloud_ativo': '0',
    'medcloud_url': 'https://medcloud.co',
    'agenda_aviso_mibi': '1',
    'clinica_nome': 'CENTRO DE MEDICINA NUCLEAR DO LESTE MINEIRO LTDA',
    'clinica_cidade': 'Governador Valadares - MG',
    'clinica_cnpj': '73.964.983/0001-50',
    'clinica_endereco': '',
    'clinica_telefone': '',
    'blindagem_valor_unitario': '405,80',
    'pastas': json.dumps([
        {'nome': 'Laudos assinados', 'caminho': r'Z:\RECEPÇÃO\LAUDOS\LAUDOS ASSINADOS'},
        {'nome': 'Laudos anteriores', 'caminho': r'Z:\RECEPÇÃO\LAUDOS'},
        {'nome': 'Pasta das fichas (PDF)', 'caminho': r'Z:\RECEPÇÃO\SISTEMA\PDF'},
        {'nome': 'Pasta JPEG', 'caminho': r'Z:\JPG\JPG'},
        {'nome': 'Modelo de fotos (Word)', 'caminho': r'\\Servidor\d\RECEPÇÃO\SISTEMA\MODELOFOTO.doc'},
    ], ensure_ascii=False),
}


def caminho_banco():
    return current_app.config['DATABASE']


def conectar(path):
    con = sqlite3.connect(path, timeout=30, detect_types=0)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout=30000')
    # bancos grandes: cache de 16 MB por conexão e tabelas temporárias em memória. (Sem mmap: no Windows o arquivo mapeado
    # impede trocar o banco na restauração do backup.)
    con.execute('PRAGMA cache_size=-16000')
    con.execute('PRAGMA temp_store=MEMORY')
    return con


def get_db():
    if 'db' not in g:
        g.db = conectar(caminho_banco())
        from . import desfazer
        if desfazer.deve_rastrear():   # POST: anota as mudanças linha a linha para o botão "Desfazer" do registro de atividades
            desfazer.instalar(g.db)
    return g.db


def close_db(_exc=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def agora():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# Colunas acrescentadas depois da primeira versão (bancos antigos recebem via ALTER TABLE).
COLUNAS_NOVAS = {
    'usuarios': [('modulos', 'TEXT'), ('criado_por', 'TEXT'), ('bh_funcionario_id', 'INTEGER'),
                 ('sessao_id', 'TEXT'),
                 ('trocar_senha', 'INTEGER NOT NULL DEFAULT 0'), ('visto_em', 'TEXT'),
                 # usuário interno que envia os avisos do sistema (não entra; só a gerência vê as mensagens dele)
                 ('sistema', 'INTEGER NOT NULL DEFAULT 0'),
                 ('tema', "TEXT NOT NULL DEFAULT 'verde'"),
                 # painel de favoritos do usuário (JSON: modo grade/lista e a ordem dos módulos)
                 ('favoritos', 'TEXT'),
                 # brilho do sistema: 'claro' ou 'escuro' (a cor é o tema; o brilho diz se o fundo é claro ou fechado)
                 ('brilho', "TEXT NOT NULL DEFAULT 'claro'"),
                 # cor de fundo do calendário da agenda, escolhida pelo próprio usuário ('' = cor padrão do sistema)
                 ('cor_calendario', "TEXT NOT NULL DEFAULT ''"),
                 # mapa de laudos: JSON {"ver": [situações], "mover": [situações de onde pode avançar]}; NULL = acesso completo
                 ('laudo_perm', 'TEXT'),
                 # 1 depois que o usuário concluiu ou dispensou o tutorial da NucleAI
                 ('tutorial_visto', 'INTEGER NOT NULL DEFAULT 0'),
                 # perfil arquivado (data): sai da lista de usuários, mas continua disponível em "Ver arquivados"
                 ('arquivado_em', 'TEXT')],
    # bh_employees.archived_at: funcionário desligado e arquivado (sai da lista, histórico do ponto continua)
    'bh_employees': [('archived_at', 'TEXT')],
    'clientes': [('criado_por', 'TEXT'), ('atualizado_por', 'TEXT'), ('sexo', 'TEXT')],
    # previsão de entrega do laudo (data ISO), calculada ao lançar o atendimento com o prazo definido pela gerência
    'atendimentos': [('previsao_laudo', 'TEXT'),
                     # paciente interno do hospital e de onde veio (hospital / setor / leito): gera o SBAR pendente no prontuário
                     ('interno', 'INTEGER NOT NULL DEFAULT 0'), ('interno_local', 'TEXT')],
    'convenios': [('usuario', 'TEXT'), ('medcloud', 'INTEGER NOT NULL DEFAULT 0')],
    # fase: etapa em que o robô está (a tela de carregamento mostra); estudo: ID do estudo criado na Medcloud
    # compartilhado: vínculo do estudo com o acesso do paciente (NULL = não se aplica; PENDENTE, PROCESSANDO, OK ou ERRO), feito em
    # segundo plano depois que o estudo existe; comp_tentativas/comp_erro: tentativas e último erro desse vínculo
    # acesso_*: usuário, senha (cifrada) e QR deste atendimento (cada atendimento novo cadastra o paciente de novo e fica com a
    # senha da hora; a ficha antiga mantém a senha antiga). acesso_modo='proprio' marca pedidos do fluxo novo (NULL = pedido antigo,
    # que usava o acesso do cliente)
    'medcloud_fila': [('fase', 'TEXT'), ('estudo', 'TEXT'), ('compartilhado', 'TEXT'),
                      ('comp_tentativas', 'INTEGER NOT NULL DEFAULT 0'), ('comp_erro', 'TEXT'),
                      ('acesso_usuario', 'TEXT'), ('acesso_senha', 'TEXT'), ('acesso_qr', 'TEXT'), ('acesso_modo', 'TEXT'),
                      # pendências do estudo criado: anexos e laudos que a equipe marca como enviados/entregues (1 = resolvido)
                      ('anexos_ok', 'INTEGER NOT NULL DEFAULT 0'), ('anexos_ok_por', 'TEXT'), ('anexos_ok_em', 'TEXT'),
                      ('laudos_ok', 'INTEGER NOT NULL DEFAULT 0'), ('laudos_ok_por', 'TEXT'), ('laudos_ok_em', 'TEXT')],
    # arquivo enviado à Medcloud sai do anexos.db (local_apagado_em); para baixar de novo o robô busca na Medcloud
    # (download_estado: PEDIDO > PRONTO ou ERRO; download_erro: motivo)
    'medcloud_envios': [('local_apagado_em', 'TEXT'), ('download_estado', 'TEXT'), ('download_erro', 'TEXT')],
    'medicos': [('usuario', 'TEXT')],
    # fornecedor_id liga a conta ao cadastro de fornecedores; parcela_n/parcela_total/parcela_grupo identificam compras parceladas (1/3)
    'contas': [('quitado_por', 'TEXT'), ('fornecedor_id', 'INTEGER'), ('parcela_n', 'INTEGER'), ('parcela_total', 'INTEGER'),
               ('parcela_grupo', 'TEXT'),
               # lote de pagamento em que a conta está agora (NULL = lista normal de contas em aberto)
               ('lote_id', 'INTEGER'),
               # conta gerada por uma conta recorrente e o mês de referência ('AAAA-MM'); a conta nasce sem lote
               ('recorrente_id', 'INTEGER'), ('recorrente_mes', 'TEXT')],
    # movimento de caixa: recebimento (quitação), forma, troco e sessão em que foi recebido
    'caixa_sessoes': [('lembrado_em', 'TEXT')],
    # mapa de laudos: situação de cada exame realizado (NULL = lançado antes do acompanhamento)
    'realizacoes': [('laudo_situacao', 'TEXT'), ('laudo_atualizado_em', 'TEXT'), ('laudo_liberado_em', 'TEXT'),
                    ('laudo_liberado_por', 'TEXT'), ('laudo_entregue_em', 'TEXT'), ('laudo_entregue_por', 'TEXT'),
                    # laudo entregue "limpo" do mapa (vai para Laudos entregues) e retificação do laudo (indicador da ONA)
                    ('laudo_arquivado_em', 'TEXT'), ('laudo_arquivado_por', 'TEXT'),
                    ('laudo_retificado_em', 'TEXT'), ('laudo_retificado_por', 'TEXT'), ('laudo_retificado_motivo', 'TEXT')],
    # mensagens do sistema que se apagam sozinhas (laudos liberados: 3 dias); laudo_id liga o aviso ao exame no mapa
    # tipo ATUALIZACAO: o único aviso do AVISOS DO SISTEMA que os funcionários veem
    # responde_id: mensagem citada; acao/chamado_id/acao_resp: botões dos pedidos de ajuda à gerência
    # anexo_id/anexo_tipo/anexo_nome: imagem enviada pelo chat (o conteúdo fica no anexos.db e some em 24 h)
    'chat_mensagens': [('expira_em', 'TEXT'), ('laudo_id', 'INTEGER'), ('tipo', 'TEXT'), ('responde_id', 'INTEGER'),
                       ('acao', 'TEXT'), ('chamado_id', 'INTEGER'), ('acao_resp', 'TEXT'), ('acao_url', 'TEXT'),
                       ('anexo_id', 'INTEGER'), ('anexo_tipo', 'TEXT'), ('anexo_nome', 'TEXT'), ('cartao', 'TEXT')],
    # tema da sugestão/bug e os dados do envio (dispositivo, navegador, IP...) em JSON, para conferir com os erros que o sistema registra
    'suporte_itens': [('tema', 'TEXT'), ('meta', 'TEXT')],
    'ajuda_sessoes': [('candidatos', 'TEXT'), ('registro_id', 'INTEGER'), ('duvida', 'TEXT'), ('origem', 'TEXT'),
                      ('seguinte', 'TEXT')],
    # faturamento em três momentos (faturado → nota fiscal emitida → recebido, com glosa) e o PDF do protocolo (no anexos.db)
    'faturas': [('protocolo', 'TEXT'), ('qtd_guias', 'INTEGER'), ('nf_emitida_em', 'TEXT'), ('nf_emitida_por', 'TEXT'),
                ('bruto_recebido', 'REAL'), ('tributos_recebidos', 'REAL'), ('glosa', 'REAL'), ('anexo_id', 'INTEGER'),
                ('protocolo_nome', 'TEXT'), ('protocolo_tamanho', 'INTEGER'), ('protocolo_em', 'TEXT'), ('protocolo_por', 'TEXT')],
    'caixa': [('editado_por', 'TEXT'), ('sessao_id', 'INTEGER'), ('valor_recebido', 'REAL'), ('troco', 'REAL'),
              ('pago_em', 'TEXT'), ('recebido_por', 'TEXT'),
              # pagamento dividido em duas formas: a segunda forma e quanto foi pago nela (o resto é da primeira)
              ('forma_pagamento2', 'TEXT'), ('valor_pagamento2', 'REAL')],
    'blindagens': [('devolvida_em', 'TEXT'), ('devolvida_por', 'TEXT')],
    'agenda_exames': [('observacao', "TEXT NOT NULL DEFAULT ''"),
                      # agenda criada com reserva de horários para o UNACON (mostra os botões de reservar/liberar)
                      ('reserva_unacon', 'INTEGER NOT NULL DEFAULT 0'),
                      # convênio escolhido para a reserva ao criar a agenda ('' = sem reserva)
                      ('reserva_convenio', 'TEXT'),
                      # exame cadastrado ao qual a agenda está vinculada (o nome da agenda é só um nome); não muda depois de criada
                      ('exame_id', 'INTEGER'),
                      # título da 6ª coluna da grade (MIBI: Etapa; demais exames: Exame; antigas: o padrão) e o valor que já vem em cada linha nova
                      ('coluna_titulo', 'TEXT'), ('senha_padrao', 'TEXT')],
    'agenda_modelos': [('exame_id', 'INTEGER')],
    # quem resgatou a falta (reagendado ou desistiu) e quando
    # reservado_unacon: horário guardado para o convênio UNACON (não aparece como livre para os demais)
    'agenda_horarios': [('chegou', 'INTEGER NOT NULL DEFAULT 0'), ('chegou_por', 'TEXT'), ('chegou_em', 'TEXT'), ('resgatado_por', 'TEXT'), ('resgatado_em', 'TEXT'), ('reservado_unacon', 'INTEGER NOT NULL DEFAULT 0'),
                        # convênio para o qual o horário está reservado (reservado_unacon=1 significa "reservado", para qualquer convênio)
                        ('reservado_convenio', 'TEXT'), ('idade', "TEXT NOT NULL DEFAULT ''")],
    # desfazer: como voltar atrás na ação registrada (JSON); desfeito_*: quando e por quem foi desfeita
    'auditoria': [('desfazer', 'TEXT'), ('desfeito_em', 'TEXT'), ('desfeito_por', 'TEXT'), ('usuario_id', 'INTEGER')],
    # anexo_id: linha do anexos.db onde está o arquivo (NULL = ainda guardado na coluna antiga)
    'arquivos_docs': [('anexo_id', 'INTEGER'), ('sha256', 'TEXT')],
    'bh_employee_documents': [('anexo_id', 'INTEGER')],
    'prontuario_docs': [('profissional_conselho', 'TEXT')],
    'pedidos_exame': [('convenio', 'TEXT'), ('hipotese', 'TEXT'), ('observacoes', 'TEXT')],
    'nucleai_llm_log': [('modelo', 'TEXT'), ('tokens_entrada', 'INTEGER NOT NULL DEFAULT 0'),
                        ('tokens_saida', 'INTEGER NOT NULL DEFAULT 0'),
                        ('tempo_ms', 'INTEGER NOT NULL DEFAULT 0'),
                        ('teste', 'INTEGER NOT NULL DEFAULT 0')],
}
SISTEMA_USUARIO = 'AVISOS DO SISTEMA'


def migrar(con):
    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = {r[1] for r in con.execute('PRAGMA table_info(%s)' % tabela)}
        for nome, tipo in colunas:
            if nome not in existentes:
                con.execute('ALTER TABLE %s ADD COLUMN %s %s' % (tabela, nome, tipo))
    con.execute('''CREATE TABLE IF NOT EXISTS nucleai_tokens (
        id INTEGER PRIMARY KEY,
        criado_em TEXT NOT NULL,
        usuario_id INTEGER,
        usuario TEXT NOT NULL,
        modelo TEXT NOT NULL,
        tokens_entrada INTEGER NOT NULL DEFAULT 0,
        tokens_saida INTEGER NOT NULL DEFAULT 0,
        tokens_total INTEGER NOT NULL DEFAULT 0,
        tempo_ms INTEGER NOT NULL DEFAULT 0,
        teste INTEGER NOT NULL DEFAULT 0
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS ix_nucleai_tokens_data ON nucleai_tokens (criado_em)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_nucleai_tokens_usuario ON nucleai_tokens (usuario)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_nucleai_tokens_modelo ON nucleai_tokens (modelo)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_contas_fornecedor ON contas(fornecedor_id)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_contas_parcela_grupo ON contas(parcela_grupo)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_contas_lote ON contas(lote_id)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_lote_itens_lote ON contas_lote_itens(lote_id)')
    # uma conta por recorrência e mês de referência ('AAAA-MM'): editar o vencimento não faz o gerador criar outra
    con.execute("UPDATE contas SET recorrente_mes=substr(vencimento,1,7) WHERE recorrente_id IS NOT NULL AND recorrente_mes IS NULL")
    con.execute('DROP INDEX IF EXISTS ix_contas_recorrente_venc')
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_contas_recorrente_mes ON contas(recorrente_id, recorrente_mes) '
                'WHERE recorrente_id IS NOT NULL')
    # cada funcionário do Banco de Horas tem no máximo um acesso
    con.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_usuarios_bh_func ON usuarios(bh_funcionario_id) '
                'WHERE bh_funcionario_id IS NOT NULL')


def inicializar(path):
    """Cria as tabelas e os dados mínimos (exames, configuração, usuário admin)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = conectar(path)
    con.executescript(SCHEMA)
    migrar(con)
    for ordem, (nome, titulo, docs, quest, med) in enumerate(EXAMES_PADRAO):
        con.execute(
            'INSERT OR IGNORE INTO exames (nome, titulo_ficha, documentos, questionario, pede_medicamentos, ordem) '
            'VALUES (?,?,?,?,?,?)', (nome, titulo, json.dumps(docs), quest, med, ordem))
    # 1.5.0: os cinco valores antigos (MIBI, Óssea, TGI, Paratgi, Gálio) passam para a tabela de valores por exame (uma vez)
    if not con.execute("SELECT 1 FROM config WHERE chave='convenio_valores_migrados'").fetchone():
        for coluna, exame in (('valor_mibi', 'MIBI'), ('valor_ossea', 'ÓSSEA'), ('valor_tgi', 'TGI'),
                              ('valor_paratgi', 'PARATGI'), ('valor_galio', 'GALIO')):
            con.execute('INSERT OR IGNORE INTO convenio_valores (convenio_id, exame_id, valor) '
                        'SELECT c.id, e.id, c.%s FROM convenios c JOIN exames e ON e.nome=? COLLATE NOCASE '
                        'WHERE c.%s IS NOT NULL' % (coluna, coluna), (exame,))
        con.execute("INSERT INTO config (chave, valor) VALUES ('convenio_valores_migrados', '1')")
    from .exames_cores import CATEGORIAS_PADRAO
    if con.execute('SELECT COUNT(*) FROM exame_cores').fetchone()[0] == 0:
        for ordem, (chave, rotulo, cor, padroes) in enumerate(CATEGORIAS_PADRAO, 1):
            con.execute('INSERT OR IGNORE INTO exame_cores (chave, rotulo, cor, padroes, ordem) VALUES (?,?,?,?,?)',
                        (chave, rotulo, cor, padroes, ordem * 10))
    for chave, valor in CONFIG_PADRAO.items():
        con.execute('INSERT OR IGNORE INTO config (chave, valor) VALUES (?,?)', (chave, valor))
    # reservas feitas quando só existia o UNACON passam a ter o convênio gravado (idempotente)
    con.execute("UPDATE agenda_horarios SET reservado_convenio='UNACON' WHERE reservado_unacon=1 AND COALESCE(reservado_convenio,'')=''")
    con.execute("UPDATE agenda_exames SET reserva_convenio='UNACON' WHERE reserva_unacon=1 AND COALESCE(reserva_convenio,'')=''")
    con.execute("UPDATE agenda_horarios SET status='RETORNO' WHERE status='REMARCOU'")   # Remarcou virou Retorno (cor do Veio)
    from . import agenda as _agenda
    _agenda.vincular_antigas(con)   # agendas de antes do vínculo recebem o exame cadastrado que corresponde ao nome (idempotente)
    from . import fichas_plano
    fichas_plano.garantir(con)   # fichas "Plano terapêutico MDN" (uma vez)
    # o Gálio passa a imprimir o PNT próprio (antes usava o da Óssea); uma vez, só se ainda estiver com o padrão antigo
    if not con.execute("SELECT 1 FROM config WHERE chave='galio_pnt_v1'").fetchone():
        gal = con.execute("SELECT id, documentos FROM exames WHERE nome='GALIO' COLLATE NOCASE").fetchone()
        if gal and '"pnt_ossea"' in (gal['documentos'] or ''):
            con.execute('UPDATE exames SET documentos=? WHERE id=?', (gal['documentos'].replace('"pnt_ossea"', '"pnt_galio"'), gal['id']))
        con.execute("INSERT INTO config (chave, valor) VALUES ('galio_pnt_v1', '1')")
    if con.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0] == 0:
        # Primeiro acesso sem dados migrados: usuário admin/admin (trocar a senha!).
        con.execute('INSERT INTO usuarios (usuario, senha_hash, admin, criado_em) VALUES (?,?,1,?)',
                    ('ADMIN', generate_password_hash('admin'), agora()))
    # contato do sistema: quem envia os avisos de vencimento. A senha é aleatória e ninguém a conhece, então não entra.
    if not con.execute('SELECT 1 FROM usuarios WHERE sistema=1').fetchone():
        con.execute('INSERT INTO usuarios (usuario, senha_hash, admin, ativo, modulos, sistema, criado_em) VALUES (?,?,0,1,?,1,?)',
                    (SISTEMA_USUARIO, generate_password_hash(secrets.token_hex(32)), '[]', agora()))
    # contato LAUDOS DO SISTEMA: avisa todos os funcionários quando um laudo é liberado (sistema = 2)
    if not con.execute('SELECT 1 FROM usuarios WHERE sistema=2').fetchone():
        con.execute('INSERT INTO usuarios (usuario, senha_hash, admin, ativo, modulos, sistema, criado_em) VALUES (?,?,0,1,?,2,?)',
                    ('LAUDOS DO SISTEMA', generate_password_hash(secrets.token_hex(32)), '[]', agora()))
    # NucleAI: assistente de ajuda (sistema = 3); aparece nas Mensagens só durante uma conversa de ajuda
    if not con.execute('SELECT 1 FROM usuarios WHERE sistema=3').fetchone():
        con.execute('INSERT INTO usuarios (usuario, senha_hash, admin, ativo, modulos, sistema, criado_em) VALUES (?,?,0,1,?,3,?)',
                    ('NucleAI', generate_password_hash(secrets.token_hex(32)), '[]', agora()))
    if not con.execute('SELECT 1 FROM usuarios WHERE sistema=4').fetchone():
        con.execute('INSERT INTO usuarios (usuario, senha_hash, admin, ativo, modulos, sistema, criado_em) VALUES (?,?,0,1,?,4,?)',
                    ('Agenda', generate_password_hash(secrets.token_hex(32)), '[]', agora()))
    # faturamento (uma vez): a situação ABERTO vira FATURADO (sem nota) ou NF_EMITIDA (com nota); recebimentos antigos ganham o bruto recebido e a glosa
    if not con.execute("SELECT 1 FROM config WHERE chave='faturas_status_v2'").fetchone():
        con.execute("UPDATE faturas SET status=CASE WHEN COALESCE(TRIM(nota_fiscal),'')<>'' THEN 'NF_EMITIDA' ELSE 'FATURADO' END WHERE status='ABERTO'")
        con.execute("UPDATE faturas SET nf_emitida_em=substr(COALESCE(criado_em, referencia),1,10) WHERE status='NF_EMITIDA' AND nf_emitida_em IS NULL")
        con.execute("UPDATE faturas SET bruto_recebido=ROUND(COALESCE(valor_recebido, valor_liquido) + COALESCE(tributos,0), 2), tributos_recebidos=COALESCE(tributos,0), "
                    "glosa=ROUND(valor_bruto - (COALESCE(valor_recebido, valor_liquido) + COALESCE(tributos,0)), 2) WHERE status='RECEBIDO' AND bruto_recebido IS NULL")
        con.execute("INSERT INTO config (chave, valor) VALUES ('faturas_status_v2', '1')")
    from . import suporte
    suporte.garantir(con)   # perfil "SUPORTE DO DESENVOLVEDOR" (senha provisória 123, troca no primeiro acesso)
    # avisos de atualização enviados antes da marcação: passam a ser visíveis aos funcionários (idempotente)
    con.execute("UPDATE chat_mensagens SET tipo='ATUALIZACAO' WHERE tipo IS NULL AND corpo LIKE 'Aviso de atualização:%' "
                "AND de_id IN (SELECT id FROM usuarios WHERE sistema=1)")
    con.commit()
    from .migracoes import zerar_movimento_antigo  # 1.4.4: começar o movimento de caixa do zero (uma única vez)
    zerar_movimento_antigo(con, path)
    # anexos em banco separado (1.4.7): cria o anexos.db e leva para lá os arquivos que ainda estão no banco principal.
    # Se a migração falhar, nada é apagado e o sistema segue lendo os anexos de onde estão.
    from . import anexos
    from .migracoes import migrar_anexos
    anexos.garantir(anexos.caminho_ao_lado(path))
    try:
        migrar_anexos(con, path)
    except Exception:
        con.rollback()
    con.close()


def config_get(chave, padrao=None):
    row = get_db().execute('SELECT valor FROM config WHERE chave=?', (chave,)).fetchone()
    return row['valor'] if row else padrao


def config_set(chave, valor):
    db = get_db()
    db.execute('INSERT INTO config (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor',
               (chave, valor))
    db.commit()
