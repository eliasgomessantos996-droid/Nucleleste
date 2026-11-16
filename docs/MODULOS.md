# Módulos

Convenção: cada módulo lista arquivos, responsabilidades, entradas/saídas, dependências e comportamentos relevantes. Cobertura atual: **bloco 1**.

---
## Bloco 1 — Base, acesso e rastreabilidade

### 1.1 Persistência e esquema — `app/db.py`
- **Faz:** define o esquema inteiro (`SCHEMA`), evolui bancos antigos (`COLUNAS_NOVAS` + `migrar`), semeia dados mínimos (`inicializar`), abre conexões (`conectar`, `get_db`, `close_db`), leitura/escrita da tabela `config` (`config_get`, `config_set`), relógio do sistema (`agora()`).
- **Constantes de negócio embutidas:** `EXAMES_PADRAO` (exames e fichas impressas por exame, copiados do VBA original segundo o comentário), `DOCUMENTOS_OUTROS`, `CONVENIOS_CAIXA`, `CONFIG_PADRAO`.
- **Efeitos colaterais:** a cada partida pode alterar o banco (ver DADOS_E_INTEGRACOES §2). `get_db` liga o rastreio do "desfazer" em POSTs.
- **Dependentes:** praticamente todos os módulos. Importa de volta `desfazer`, `exames_cores`, `fichas_plano`, `migracoes`, `anexos` (importações tardias dentro das funções para evitar ciclos).

### 1.2 Migrações — `app/migracoes.py`
Ver DADOS_E_INTEGRACOES §4. Tem CLI própria (`python -m app.migracoes`). Erro específico: `ErroMigracao`. `copia_do_banco` usa a API de backup do SQLite e grava em `<pasta do banco>/backups/<PREFIXO>_<data>.db`.

### 1.3 Autenticação — `app/auth.py` (blueprint `auth`)
Rotas: `/login`, `/logout` (POST), `/minha-senha`, `/meu-tema` (POST; tema, brilho, cor do calendário do próprio usuário), `/sessao/batida` e `/sessao/saida` (presença). `registrar_acesso` grava em `acessos` com IP (`request.remote_addr`). Regras em REGRAS_DE_NEGOCIO §1.

### 1.4 Presença — `app/presenca.py`
Tabela `presenca` (usuário + aba). Cada aba bate a cada 20 s (`BATIDA_S`); online = alguma batida nos últimos 90 s (`ONLINE_S`). `sair` apaga abas e atualiza `usuarios.visto_em`. `situacao(db)` devolve `{id: {online, visto}}`; **a NucleAI (`sistema=3`) é sempre online**. Aba válida: só `[A-Za-z0-9_-]`, até 40 caracteres.

### 1.5 Permissões e menu — `app/modulos.py`
Catálogo de 37 módulos, perfis, ícones, `MENU`, `ABAS` (botões internos por tela), `modulos_do_usuario`, `modulo_do_endpoint`, `montar_menu`, `montar_abas`, `telas()` (usada pelos favoritos). Regras em REGRAS_DE_NEGOCIO §2.

### 1.6 Auditoria e desfazer — `app/auditoria.py`, `app/desfazer.py`, `app/views_registros.py` (blueprint `reg`)
- Tela `/registros` (módulo `registros`): filtros por período (padrão últimos 7 dias), usuário, módulo, texto; até 1500 linhas; totais por usuário e módulo (top 8).
- `POST /registros/<id>/desfazer`: só administrador ou módulo `gerencia`. Recusa se não há payload, se já foi desfeita ou se os dados mudaram depois. A execução real é `agenda.aplicar_desfazer` (**a lógica geral de desfazer mora em `agenda.py`**, que aceita tabelas do próprio `TABELAS_DESFAZER` ou elegíveis pelo `desfazer.tabela_permitida`); confere que o estado atual das linhas é igual ao "depois" gravado, restaura o "antes" (UPDATE ou INSERT) e apaga linhas que não existiam antes. Também trata `apagar_agendas` (desfazer criação de agendas, só se não há paciente marcado).
- Marca `desfeito_em/desfeito_por` na linha original.

### 1.7 Usuários e administração — `app/views_admin.py` (blueprint `admin`, parte "usuários e perfis")
- Criar/editar (`/usuarios/novo`, `/usuarios/<id>`): admin (perfil Usuário ou Administrador), módulos marcados, permissões do mapa de laudos (`laudos.perm_do_form`). Nome do usuário em maiúsculas (`util.maiusculas`), não editável depois. Senha mínima 3. Não pode retirar o próprio admin. Usuário não-admin precisa de ≥ 1 módulo.
- Redefinir senha (`/usuarios/<id>/senha`): **não marca `trocar_senha`** e não confere se o id existe (UPDATE em zero linhas passaria silenciosamente). Alterna ativo/inativo (`/situacao`; não pode desativar a si mesmo).
- Arquivar/desarquivar/desligar (`app/usuarios_arquivo.py`): arquivar = `ativo=0` + `arquivado_em`; recusa a si mesmo, usuários internos (`sistema`) e **o último administrador ativo**. Desligar funcionário = inativar `bh_employees`, preencher `end_date` (se vazio) e `archived_at`, depois arquivar. Desarquivar volta à lista mas **continua desativado**; limpa `archived_at` do funcionário.
- A lista de usuários oculta os internos (`sistema=0`) e mostra último login, nº de ações e presença.
- Demais seções de `views_admin.py` (backup, pastas, WhatsApp, configurações) → bloco 9.
- `acessos` (`/acessos`): últimos 1000 eventos; exige o módulo `acessos`.

### 1.8 Cache curto — `app/cache_curto.py`
Cache em memória por processo, `obter(chave, calcular, segundos=30)`: cálculo único com espera (até 120 s) para pedidos simultâneos; limite de 300 chaves (zera tudo ao exceder). Surgiu do teste de sobrecarga (comentário). Usado por dashboard e KPIs (a confirmar nos blocos 8).

### 1.9 Utilitários — `app/util.py`
Datas (`para_data`, `data_iso`, `data_br`, `data_extenso`), idade, CPF (`cpf_valido`, `cpf_formatado`), telefone (`telefone_padrao`, `telefone_valido`, `telefone_formatado`), `maiusculas`, `para_valor` (texto→número), `moeda`, `valor_extenso` (por extenso). Detalhes das regras de CPF/telefone serão lidos junto com o cadastro de clientes (bloco 2).

---
## Bloco 2 — Núcleo clínico

### 2.1 Cadastros — `app/views_cadastros.py` (blueprint `cad`)
- **Clientes** (`/clientes`, `/clientes/novo`, `/clientes/<id>`, `/clientes/<id>/excluir`): busca por código/CPF (se só dígitos) ou por nome/nome da mãe (todos os termos, `LIKE`); 50 por página. O formulário normaliza (`_ler_form_cliente`): textos em maiúsculas, CPF `000.000.000-00`, telefone `(XX)9XXXX-XXXX`, data ISO, sexo = 1ª letra. Vincula `convenio_id` pelo nome (`_convenio_id`). Ao criar pode seguir para "atender" (`atend.novo?cliente=`). A edição mostra atendimentos (por `cliente_id` **ou** mesmo CPF) e doses. Vindo da agenda, pré-preenche nome, contato e convênio por querystring.
- **Convênios** (`/convenios`): nome único (maiúsculas), `gera_caixa`, `ativo`; ao renomear, atualiza `clientes.convenio` dos clientes ligados. Valor por exame em `convenio_valores` (campos `valor_<id do exame>`; vazio ou negativo apaga; "1.250" é lido como milhar). Mantém, por compatibilidade, as colunas antigas `valor_mibi/ossea/tgi/paratgi/galio` em sincronia (`_COLUNAS_ANTIGAS`). Exclusão só se nenhum cliente usa o convênio (senão manda desativar); apaga os valores junto.
- **Médicos** (`/medicos`): nome em maiúsculas e CRM; impede duplicado **apenas ao criar** (a edição pode gerar duplicata; a lista sinaliza `dup`); exclusão sem verificar uso.
- **Exames e fichas** (`/exames`, `/exames/novo`, `/exames/<id>`): nome único, título impresso, lista ordenada de documentos `[[slug, cópias]]`, questionário, `pede_medicamentos`, ativo, ordem. Não há rota de exclusão de exame (só desativar).
- **Fichas personalizadas** (`/exames/fichas*`): texto livre até 20 000 caracteres com marcação própria (ver 2.3); prévia por POST; excluir.

### 2.2 Atendimentos, guias e caixa — `app/views_atendimentos.py` (blueprint `atend`)
- `/atendimentos/novo`: lança o atendimento (fluxo em FLUXOS.md §1). `/atendimentos`: lista filtrada (período padrão = mês corrente até hoje, máx. 2000). `/atendimentos/<id>/imprimir`: monta as fichas. `/atendimentos/<id>/excluir` (**só administrador**) apaga também guia e caixa vinculados. `/atendimentos/previsao`: JSON da previsão de laudo. `/atendimentos/laudo/<cliente>`: procura o laudo em Word na pasta `config.laudos_pasta_word` (ver 2.6).
- **Guias** (`/guias`): protocolo dos convênios que não vão ao caixa; só permite editar o horário ou remover a guia.
- **Caixa** (`/caixa`, `/caixa/<id>`): lista os lançamentos do período; quem não é privilegiado só vê os que ele mesmo lançou; salvar valor/forma/NF/status/obs sujeito às regras de `movimento` (bloco 4). Status `ABERTO|PAGO|CANCELADO`; formas: DINHEIRO, PIX, CARTÃO DE DÉBITO, CARTÃO DE CRÉDITO, TRANSFERÊNCIA, CONVÊNIO/FATURA.

### 2.3 Fichas — `app/fichas.py`, `app/fichas_plano.py`, `app/templates/fichas/`
- Catálogo em `templates/fichas/_manifesto.json` (`catalogo()`). `FICHAS_ATENDIMENTO` lista as 16 que entram no atendimento. Fichas personalizadas têm slug `x<id>`.
- `QUESTIONARIOS`: perguntas SIM/NÃO por ficha PNT (linfonodo, mibi, óssea, renal, pulmonar, spect, tgi, paratgi), com justificativa opcional quando SIM. O questionário de um exame é o da **primeira ficha PNT** da sua lista (`questionario_do_exame`).
- `dados_atendimento` monta os campos: dados do cliente (`dados_cliente`), do atendimento e até 9 respostas `r1..r9`/`o1..o9`. Se `respostas.manual`, a ficha sai em branco.
- `renderizar_texto`: converte o texto das fichas personalizadas em HTML escapado; marcações `# `, `## `, `---`, `**negrito**`, `[ ]/[x]`, `{campo}` (campos de `CAMPOS_FICHA`).
- `fichas_plano.garantir` (chamada por `db.inicializar`): cria uma vez as fichas "Plano terapêutico MDN" (Anexo 01 do POP MDN 24, uma por exame) como fichas personalizadas; controle por `config.fichas_plano_v1`. O conteúdo clínico dos modelos **não foi lido**.

### 2.4 Medicamentos (doses) — `app/views_medicamentos.py` (blueprint `med`)
Doses de IODO, GÁLIO e PCI. Exige médico, medicamento válido, data da dose, e datas de dieta e de suspensão da medicação (ou "SEM PREPARO", que preenche as duas). Copia dados do cliente para a dose (snapshot). Status `AGENDADO|CONCLUIDO|CANCELADO`. Impressão: ficha de agendamento + `iodo_15dias` (preparo 15 DIAS) ou `iodo_30dias` (30 DIAS). Cadastra médico novo automaticamente.

### 2.5 Exames realizados — `app/views_exames.py` (blueprint `lanc`, prefixo `/exames-realizados`), `app/exames_cores.py`, `app/exames_import.py`
- Reproduz a planilha EXAMES.xlsx: 1 linha por exame realizado (`realizacoes`). Lista filtrável (mês, período, texto, convênio, médico, tipo), até 1500 linhas; impressão (até 5000); exportação CSV (UTF-8 com BOM, `;`, até 100 000).
- `exames_cores.Classificador`: classifica o texto do exame em categorias por palavras-chave (tabela `exame_cores`; a primeira que combina vence) e devolve cor e rótulo; `cor_planilha` guarda a cor da planilha importada.
- Novo/edição: paciente e exame obrigatórios, data ISO válida, horas `HH:MM`, peso/altura numéricos. Gera `numero` sequencial por mês e sugere `codigo` = último código numérico + 1 (`_proximos`). **Todo exame novo lançado pelo formulário entra no mapa de laudos como `PROCESSANDO`.** Pode nascer de um atendimento (`atendimento_id`, no máximo um exame por atendimento).
- `/sugestao`: devolve rádio/eluição/fármaco/lote/atividades/responsável do último exame do mesmo tipo com fármaco preenchido.
- `/atendimentos-do-dia` (POST): cria em lote exames em branco a partir dos atendimentos do dia ainda não vinculados; **esse caminho não define `laudo_situacao`**, então tais exames não entram no mapa de laudos (pendência 14).
- `/importar` (xlsx/xlsm): `exames_import.importar_xlsx`, colunas localizadas pelo cabeçalho de cada aba (uma aba por mês). Restrita ao administrador em `modulos.py`.

### 2.6 Mapa de laudos — `app/laudos.py`, `app/views_laudos.py` (blueprint `laudo`, `/laudos`), `app/prazo_laudo.py`, `app/laudos_word.py`
- Estados em ordem: `PROCESSANDO → LAUDANDO → LIBERADO → ENTREGUE`. O quadro lista, por período (padrão últimos 7 dias), só exames com `laudo_situacao` e sem arquivamento.
- `mudar` aplica as transições e carimbos; `avisar_liberacao` envia mensagem do usuário `LAUDOS DO SISTEMA` a todos os ativos não internos, com expiração em 3 dias (`apagar_expiradas`). Regras em REGRAS_DE_NEGOCIO §11.
- `/laudos/entregues`, `/limpar` (arquiva entregues do período), `/retificar` (marca laudo entregue como retificado → indicador da ONA), `/prazo` (ver §10).
- `laudos_word.py`: separa data/código/nome nos nomes de arquivo, pontua o nome do paciente e só abre arquivo dentro da pasta (`caminho_seguro`).

### 2.7 Blindagens — `app/blindagens.py`, `app/views_blindagens.py` (blueprint `blind`), `app/blindagem_docs.py`
Cadastro de geradores de tecnécio; atualização automática VÁLIDO/VENCIDO; solicitação de devolução (cria `blindagem_devolucoes` e liga as blindagens); confirmação da devolução (data); PDFs e planilha: planilha da devolução (PDF e XLSX), declaração para transporte, declaração do expedidor, etiquetas ONU 2910, etiqueta do destinatário e "material radioativo" (reproduzem os modelos Word da clínica; `gerar_documentos`). Regras em REGRAS_DE_NEGOCIO §12. O texto interno dos PDFs (conteúdo regulatório) **não foi lido**.


---
## Blocos 3 a 10 — mapa por rotas e assinaturas (SUBSTITUÍDO pelas seções 'aprofundado' abaixo; mantido como visão rápida)

Nível desta varredura: rotas (`@bp.route`) e funções públicas, lidos por busca. **As regras internas de cada módulo não foram lidas**, salvo onde indicado. Cada item abaixo é mapeamento, não verificação de comportamento.

### 3. Agenda — `agenda.py`, `views_agenda.py` (blueprint de agenda)
- Rotas: visão por dia/mês, horários livres, criar/excluir agendamento, reservar horário, bloquear/desbloquear, copiar, editar campos e status do horário, mover exame, remarcar/reagendar, lista de espera (incluir, excluir, encaixar), impressão diária (PDF), relatório, resgates, faltas, financeiro (PDF/XLSX) e reservas (planilha e importação).
- `agenda_reservas.py`: reservas importadas por planilha. Desfazer geral da agenda em `views_registros.aplicar_desfazer` (pendência 13).
- Pendente: regras de conflito de horário, transições de status, cálculo financeiro.

### 4. Dinheiro — `movimento.py`, `views_movimento.py`, `caixa_diario.py`, `views_caixa_diario.py`, `financeiro`, `views_financeiro.py`, `fornecedores.py`, `views_faturamento.py`
- **Caixa do dia (movimento)**: formas de recebimento `DINHEIRO` e `PIX`. Sessão por usuário: abrir (com fundo), fechar, reabrir (privilegiado). Recebimento, edição, exclusão individual ou em lote, quitação e relatório PDF da sessão. Lembrete de caixa aberto a partir das 17h (`HORA_LEMBRETE`), via `alertar_caixas_abertos`.
- **Caixa diário**: tipos RECEITA/DESPESA, contas com cor (`CONTAS`), saldos por dia, "retidas" (lista própria), relatório XLSX. Pendência herdada 4 (regras de conta e taxa de PIX) segue em aberto.
- **Contas a pagar (`financeiro`)**: contas com parcelas (`MAX_PARCELAS = 60`), quitar/reabrir/excluir, impressão, relatório por fornecedor (PDF/XLSX).
- **Fornecedores**: consulta de CNPJ em `FONTES` (BrasilAPI e ReceitaWS, `TIMEOUT_S = 8`) com validação de dígitos verificadores; cadastro; geração de parcelas (`planejar_parcelas`, divisão do valor e datas por mês). Consulta externa só preenche o formulário; não grava sozinha (ver `consultar_cnpj`, a confirmar).
- **Faturamento**: lista, nova/edição, quitar, reabrir, excluir e dashboard.

### 5. Banco de Horas — `app/bh/*`, `views_bh.py`
- Módulo incorporado de outro programa. Núcleo em `bh/core.py` (funcionários, jornada, importação de planilha `.xls` por `import_xls`, correções de dia `correct_day`, ajustes `add_adjustment`, cálculo diário `_calculate_day`, relatório mensal `monthly_report`, resumo `summary`). Tipos de dia: `normal, falta, abono, folga, feriado`.
- **Portal do funcionário** (`bh/portal.py`): conta criada com senha padrão `SENHA_PADRÃO = '123'` e troca obrigatória no primeiro login; mínimo de 6 caracteres. Ver pendência 16.
- Documentos pessoais (`bh/documents.py`): até 15 MB; 6 categorias obrigatórias (identidade, CPF, CTPS, comprovante, contrato, admissional); arquivar/restaurar; hash SHA-256 por arquivo.
- Escala mensal (`bh/planning.py`): tipos trabalho/férias/folga/feriado com códigos T, FE, FO, FD; PDF da escala.
- Mensagens internas (`bh/messages.py`): até 2000 caracteres, 10 por minuto, 200 na conversa.
- Busca global (`bh/search.py`) limitada aos módulos do usuário.
- Migração de banco antigo (`bh/migracao.py`): copia tabelas listadas em `TABELAS`. Ver pendência 12.

### 6. Comunicação — `chat.py`, `views_chat.py`, `presenca.py`, `avisos.py`, `mensagens_whats.py`, `views_admin.py` (mensagens WhatsApp)
- **Chat interno**: mensagens até 2000 caracteres, 40 por minuto (`MAX_POR_MINUTO`), conversa de 300, imagem até 5 MB, imagem apagada após 24 h (`apagar_imagens_expiradas`), busca com normalização de acentos (`_dobrar`), indicador de digitação (6 s).
- **Presença**: batida a cada 20 s por aba, online por 90 s, até 40 abas por usuário (`presenca.py`).
- **Avisos (`avisos.py`)**: fases de aviso em dias restantes `(0, 1, 7, 15, 30, 60)`. Laço de fundo a cada 600 s (FLUXOS §2).
- **Mensagens de WhatsApp (`mensagens_whats.py`)**: modelos de texto com variáveis (`VARIAVEIS`), limite de 1000 caracteres, tipos em `TIPOS`, restaurar padrão. Só monta o texto; não envia (verificar em `views_admin`).

### 7. NucleAI e ajuda — `nucleai_comandos.py` (693 linhas), `views_nucleai.py`, `ajuda.py`, `views_ajuda.py`
- Assistente local por palavras-chave (sem IA externa). Catálogo `COMANDOS` com cerca de 40 comandos (agenda, caixa, laudos, doses, financeiro, KPI, satisfação, backup, usuários).
- Níveis de risco: `BAIXO`, `MEDIO`, `ALTO`, com modo `todos | escolhidos | ninguem` (padrão por risco em `MODO_PADRAO`).
- Comandos de risco pedem confirmação; o pedido perde a validade após `VALIDADE_MIN = 30` (unidade presumida em minutos [HIPÓTESE]). Não verificado se as ações executam pelas mesmas rotas do sistema.
- Chamados de ajuda com resposta do administrador; tutorial (`tutorial-visto`); impressão de ajuda.
- Novidades por versão: `views_novidades.py` serve `<versão>.pdf`.

### 8. Qualidade, pesquisa, ONA e dashboard — `views_qualidade.py` (69 rotas, maior blueprint), `pesquisa*.py`, `ona*.py`, `views_dashboard.py`, `views_saude.py`
- Qualidade: indicadores com metas, robô de análise (aceitar/descartar sugestão), PDCA com 5 porquês, GUT, causas (Ishikawa), ações, Pareto, plano de ação, riscos, SWOT, fluxogramas com aprovação, organograma, ocorrências, avaliação de fornecedores (critérios e PDF), relatório de satisfação com QR code e cartaz.
- Pesquisa pública (`/pesquisa`, sem login) e revisão das respostas.
- ONA: relatório PDF/XLSX com indicador de laudos retificados (ver REGRAS §11).
- Dashboard e saúde do sistema: rotas de visualização; regras de cálculo não lidas.

### 9. Operação — `views_atualizacao.py`, `backup_pacote.py`, `views_admin.py` (backup e restauração), `cli.py`, `tray.pyw`, `ferramentas/`, `instalador/`
- Atualização: tela de espera 503 (ver ARQUITETURA §5); iniciar atualização; avisos aos usuários.
- Backup: gerar, baixar, restaurar de arquivo ou de pasta (`restaurar-pasta`). Restauração é operação de alto risco (pendência 12).
- Configuração de pastas e geração de `.reg` para o computador (`configurar-computador.reg`).
- CLI (`cli.py`): `backup`, `admin-senha`, `importar-db`, `importar-exames`, `importar-bh`, `config`. `admin-senha` redefine senha de administrador pela linha de comando.
- `ferramentas/`: conversão de fichas, importação do sistema antigo, carga e estresse. Não rodados.
- Instalador: `instalador/nucleleste.iss` (Inno Setup), `build.ps1`, tarefa agendada (`instalar_servico.ps1`).

### 10. Testes — `tests/` (42 arquivos `test_*.py`, unittest)
- Mapeamento por módulo ainda não feito. Execução só em banco temporário (ver ARQUITETURA §7.10). Ver TESTES_E_COMPORTAMENTOS.md quando criado.



---
## Bloco 3 (aprofundado) — Agenda de exames [FATO: lido `agenda.py`, `views_agenda.py`, `agenda_reservas.py`]

**Ideia central:** a agenda é uma "planilha por dia". Em cada dia há uma *agenda por exame* (`agenda_exames`) com linhas de horário (`agenda_horarios`). Linha sem paciente = horário livre. A agenda **não tem vínculo com `clientes`**: guarda nome, convênio e contato digitados (docstring de `agenda.py`). A única ligação é o nome: `views_agenda.status` consulta `clientes` pelo nome em maiúsculas para avisar se o paciente já é cadastrado.

**Tabelas usadas:** `agenda_exames` (data, exame, inicio, intervalo, vagas, observacao, reserva_unacon, reserva_convenio), `agenda_horarios` (hora, ordem, paciente, convenio, contato, senha, observacao, status, remarcado_para, resgatado_por/em, reservado_unacon, reservado_convenio, atualizado_por/em), `agenda_bloqueios`, `agenda_modelos`, `agenda_espera`, `agenda_ordem_exames`.

**Interface técnica:** todas as ações são POST que respondem JSON (`_resposta`): sucesso `ok`, erro 400 com `erro`, confirmação 409 com `confirmar`, conflito 409 com `conflito/atual/por`. A grade grava ao sair de cada célula (texto da própria tela).

**Edição concorrente:** `salvar_campo` recebe `antes` (valor que a tela exibia). Se o banco já tem outro valor, levanta `ErroConflito` e nada é gravado.

**Desfazer:** cada ação reversível guarda em `g.desfazer` fotografia (antes/depois) das linhas mexidas; `aplicar_desfazer` só reverte se as linhas continuam como a ação as deixou. Criar agendas e copiar sem pacientes usam `apagar_agendas` (recusa se já houver paciente).

**Reserva para convênio:** coluna `reserva_unacon`/`reservado_unacon` e `reserva_convenio`/`reservado_convenio`. O nome "UNACON" é herdado (a sigla designa unidade oncológica; no código vale para qualquer convênio escolhido). Horário reservado só aceita paciente do mesmo convênio (`_checar_reserva`). A planilha de reservas (`agenda_reservas.py`) sai em branco com o código da vaga; o convênio preenche; `importar` só preenche vagas ainda vazias e confere data, hora e exame.

**Lista de espera:** `agenda_espera` com status AGUARDANDO/ENCAIXADO. Encaixar usa um horário livre do dia.

**Relatórios:** `relatorio` (marcados/vieram/faltaram/remarcaram, taxas), `faltas` (com link WhatsApp `wa`), `resgates` (por usuário), `financeiro` (repasse médico, com filtro por dias da semana e caixinhas Repouso/Estresse/Protocolo do MIBI; PDF em uma única folha A4), reservas. PDFs/XLSX em `agenda_docs.py`, `agenda_rel_docs.py`, `agenda_fin_docs.py` (modelo comum de `relatorio_base.py`).

**Aviso de duplicidade:** após salvar paciente ou contato, `avisar_duplicados` manda pergunta (Sim/Não) pelo contato AVISOS DO SISTEMA a quem usa a agenda; falha aqui nunca impede o salvamento.


---
## Bloco 4 (aprofundado) — Dinheiro [FATO: lidos `movimento.py`, `views_movimento.py`, `caixa_diario.py`, `views_caixa_diario.py`, `fornecedores.py`, `views_financeiro.py`, `views_faturamento.py`]

Há **quatro controles financeiros independentes**, sem ligação automática entre si:
1. **Movimento de caixa** (`movimento*.py`, tabelas `caixa` + `caixa_sessoes`): recebimento do balcão, por usuário e por dia.
2. **Caixa diário da empresa** (`caixa_diario.py`, tabelas `cxd_*`): reprodução da planilha de saldo em 4 contas.
3. **Contas a pagar** (`views_financeiro.py` + `fornecedores.py`, tabelas `contas`, `fornecedores`).
4. **Faturamento** (`views_faturamento.py`, tabela `faturas`): notas emitidas a convênios e particular, com tributos e recebimento.

### 4.1 Movimento de caixa
- Cada usuário tem **uma sessão por dia** (`caixa_sessoes`: usuario, data, fundo, status ABERTO/FECHADO, aberto/fechado em, `alertado_em`, `lembrado_em`).
- Lançamentos nascem em `caixa` (status ABERTO) quando o atendimento é de convênio com `gera_caixa=1` (ver REGRAS §7). Receber converte para `PAGO` e grava forma, nota fiscal, valor recebido, troco, `sessao_id`, `pago_em`, `recebido_por`.
- Formas: apenas `DINHEIRO` e `PIX` (`FORMAS`). Note que a tela `/caixa` oferece mais formas (ver bloco 2); o movimento restringe a duas.
- Avisos: pelo contato do sistema, a quem deixou caixa de outro dia aberto (1 por dia) e lembrete às 17h (`HORA_LEMBRETE`), disparados pela rotina de `avisos.py`.
- Relatório para assinatura: dinheiro (devido, recebido, troco, líquido) e PIX separados; `esperado_dinheiro = fundo + líquido`.
- Recibo avulso de quitação: `/movimento-caixa/quitacao/<id>`.

### 4.2 Caixa diário
- Contas: `BB` (Banco do Brasil), `UNICRED`, `CAIXA` (Caixa Econômica) e `DINHEIRO`. Cores iguais às da planilha original.
- Saldo do dia = saldo anterior + receitas − despesas, **recalculado em cadeia** a partir de uma data-base (`cxd_inicio`, única linha com `id=1`). Retiradas retidas (`cxd_retidas`) não entram nas contas; `total_final = saldo_total − retidas`.
- As tabelas são criadas por `garantir(db)` a cada abertura de tela (`CREATE TABLE IF NOT EXISTS`).
- Relatório do dia em XLSX (A4, assinaturas "Gerente Administrativo" e "Sócio-Administrador").

### 4.3 Contas a pagar e fornecedores
- 30 categorias fixas (`CATEGORIAS`, inclui receitas, o que mistura receita e despesa na mesma lista) e 4 bancos (`BANCOS`: BANCO DO BRASIL, UNICRED, DINHEIRO, CAIXA).
- Parcelamento: 2 a 60 parcelas, valor total dividido (centavos exatos, diferença na última) ou valor por parcela; vencimento mensal ou datas manuais. Todas ligadas por `parcela_grupo`. "Excluir parcelas em aberto" apaga só as ABERTO do grupo.
- Fornecedor: CNPJ opcional, mas se informado deve ser válido e único; consulta externa (BrasilAPI, depois ReceitaWS; timeout 8 s) preenche o formulário sem gravar. Alterar o nome do fornecedor atualiza o nome nas contas; excluir o fornecedor mantém as contas sem vínculo.
- Quitar exige banco da lista; grava `data_pagamento` (padrão hoje), forma e quem quitou.

### 4.4 Faturamento
- Fatura: convênio (ou PARTICULAR), data de referência, nota fiscal, valor bruto, tributos, **líquido = bruto − tributos**, previsão de recebimento, status ABERTO/RECEBIDO.
- Quitar: data, valor recebido (padrão = líquido) e banco; a diferença positiva é anotada como glosa/ajuste.
- Dashboard: recebido × a receber, glosa, prazo médio (recebimento − referência), taxa de recebimento, evolução mensal, envelhecimento (0–30, 31–60, 61–90, 90+ dias desde a referência) e percentual de tributos por convênio (top 10 + "Outros").


---
## Bloco 5 (aprofundado) — Banco de Horas [FATO: lidos `bh/core.py`, `bh/portal.py`, `bh/planning.py`, `bh/messages.py`, `bh/documents.py`, `bh/migracao.py`, `views_bh.py`]

**Origem:** porte do programa autônomo "Banco de Horas" para dentro do sistema; mesmas regras de cálculo, agora sobre tabelas `bh_*` (docstring de `bh/core.py`). O código do módulo está em inglês; as telas, em português.

**Entidades:** `bh_employees` (Número I do relógio, nome, vínculo, saldo inicial, estagiário), `bh_schedules` (jornada com vigência), `bh_imports` / `bh_import_rows` (planilha do relógio, com o arquivo original), `bh_corrections` (correção de dia), `bh_adjustments` (ajuste de saldo), `bh_audit_log`, `bh_report_snapshots` (PDF emitido, por versão), `bh_roster_days` (escala), `bh_employee_documents`, `bh_messages` e `bh_message_threads`.

**Princípios do desenho (do docstring e do código):**
- Durações são **minutos inteiros com sinal**.
- A planilha é associada ao funcionário pelo **Número I**, nunca pelo nome.
- Importações são **imutáveis**: o primeiro registro aceito de cada (Número I, dia) prevalece; uma nova importação diferente cria *conflito* e preserva o original.
- Dia incerto **não gera débito nem crédito** (fica pendente).
- Tudo é auditado em `bh_audit_log` com antes/depois e justificativa.

**Fluxo:** cadastrar funcionário → definir jornada (com vigência) → importar planilha `.XLS` do relógio → conferir pendências (dia a dia) → corrigir dia ou ajustar saldo (com justificativa) → emitir relatório mensal em PDF para assinatura (versionado).

**Telas (`views_bh.py`, blueprint `bh`, `/banco-horas`):** painel de saldos do mês, pesquisa, funcionários (lista, ficha, jornada, acesso), importações, extrato mensal, correção de dia, ajuste, relatório (HTML e PDF), histórico, escala (e PDF), Departamento Pessoal (documentos), mensagens e "Minha área" do funcionário.

**Erros:** todo `ValueError` é capturado por `@bp.errorhandler(ValueError)`: mostra a mensagem, devolve o formulário preenchido (sem campos de senha) pela sessão (`bh_form`) e redireciona de volta.

**Acesso do funcionário (`bh/portal.py`):** conta na própria tabela `usuarios` (coluna `bh_funcionario_id`) com módulo único `bh_portal`, sempre com `trocar_senha=1`. Ao cadastrar um funcionário (não estagiário e ativo), o sistema cria **automaticamente** o acesso: login = primeiro nome sem acento (ou `primeiro.ultimo`, ou com número), senha **`123`**.

**Importação de dados antigos (`bh/migracao.py`, CLI `importar-bh`):** só roda se `bh_employees` e `bh_imports` estiverem vazias; mapeia perfis (manager → consulta, gestão, dp, mensagens; viewer → consulta; employee → portal); usuário já existente mantém-se como está. Abre a origem em modo somente leitura.


---
## Bloco 6 (aprofundado) — Comunicação, avisos e anexos [FATO: lidos `chat.py`, `views_chat.py`, `avisos.py`, `anexos.py`, `mensagens_whats.py`, `arquivos.py`, `views_arquivos.py`, `atualizacao.py`, `views_atualizacao.py`, `bh/pdf.py`, `bh/search.py`]

### 6.1 Chat interno (`chat.py`, `views_chat.py`, `/mensagens`)
- Qualquer usuário ativo conversa com qualquer outro. Mensagens ficam gravadas em `chat_mensagens` até serem lidas.
- **Contatos especiais** (coluna `usuarios.sistema`): `1` = AVISOS DO SISTEMA, `2` = LAUDOS DO SISTEMA (ambos só leitura), `3` = NucleAI (só responde dentro de uma conversa de ajuda iniciada pelo botão). Funcionários só veem, do contato de avisos, as mensagens do tipo `ATUALIZACAO`; avisos de vencimento e de caixa são da gerência (`_visivel`).
- **Tempo real por espera longa:** `GET /mensagens/novas?espera=N` segura a resposta até N segundos (máx. 15) esperando novidade. Há no máximo 24 esperas simultâneas no servidor e 3 por usuário; passando disso, a consulta responde na hora e o navegador espaça as consultas. Cada espera ocupa uma thread do servidor (Waitress, 48 threads) [HIPÓTESE sobre capacidade: ver pendência 29].
- **Imagens:** JPEG, PNG, GIF ou WEBP (detectadas pelo conteúdo), até 5 MB, guardadas em `anexos.db` e **apagadas 24 h depois** (a mensagem fica, marcada `APAGADA`). Só quem enviou ou recebeu vê a imagem.
- **Limites:** 2000 caracteres; 40 mensagens por minuto por usuário; 300 mensagens por conversa na tela; "digitando…" só em memória (6 s); busca na conversa sem acento (até 60 resultados nas últimas 5000).
- **Mensagens com ação:** `AVALIACAO_VER` e `AGENDA_VER` permitem Sim/Não uma única vez e devolvem a URL de destino.

### 6.2 Avisos e rotina de fundo (`avisos.py`)
- Documentos de fiscalização têm aviso por fase (60, 30, 15, 7, 1 e 0 dias antes, e vencido); cada fase sai **uma vez** por data de vencimento (`docs_avisos`), para a gerência.
- **Laço em segundo plano** (`avisos.iniciar`): espera 30 s e, a cada **600 s**, executa em ordem: `verificar` (inclui alerta de caixa de outro dia aberto) → `movimento.lembrar_fechamento` → `chat.apagar_imagens_expiradas` → `qualidade_robo.rotina_diaria` → `laudos.apagar_expiradas`. Qualquer exceção é engolida e tenta de novo na rodada seguinte.
- Abrir a tela de Documentos também executa `avisos.verificar` (efeito colateral em GET).

### 6.3 Anexos (`anexos.py`)
- Segundo banco SQLite `anexos.db` ao lado do `sistema.db`, tabela `anexos` (origem, origem_id, sha256, tamanho, conteudo, criado_em). O principal guarda só metadados e `anexo_id`. Gravação: conteúdo primeiro, metadado depois; se o metadado falha, o conteúdo é apagado. Sem arquivo em disco (banco em memória), o conteúdo fica no próprio banco.

### 6.4 Documentos (`arquivos.py`, `/documentos-arquivo`)
- Dois tipos: `CONTRATO` e `FISCALIZACAO` (este exige vencimento). Aceita PDF, Word, Excel, JPG e PNG **pela extensão** (não pelo conteúdo, ao contrário do DP e do chat), até 20 MB. Situação: VENCIDO, PROXIMO (≤ 30 dias) ou EM DIA. Excluir apaga o metadado, os avisos e depois o conteúdo.

### 6.5 Mensagens de WhatsApp (`mensagens_whats.py`)
- Três modelos editáveis pela gerência (`lembrete`, `falta`, `reagendamento`), em `config.whats_mensagens` (JSON), até 1000 caracteres, com `{saudacao} {nome} {exame} {data} {hora}`. O sistema **monta o texto**; o envio é por link `wa.me` aberto pelo usuário na tela de faltas (**não há envio automático no código lido**).

### 6.6 Aviso de atualização (`atualizacao.py`, `/atualizacao`)
- A gestão dispara um aviso com prazo de 1 a 60 minutos (padrão 10) a todos os usuários ativos, pelo contato AVISOS DO SISTEMA (tipo `ATUALIZACAO`).
- O instalador (no computador-base) consulta `/atualizacao/pendente` (sem login, **só 127.0.0.1/::1**) e chama `POST /atualizacao/iniciar` com o cabeçalho `X-Chave` igual à **chave secreta do servidor** (comparação em tempo constante, também só local) para pedir o aviso de 3 minutos.
- Marca `atualizando.txt` na pasta de dados faz o servidor novo exibir a **tela de espera** por até 60 s depois de iniciar (válida por no máximo 900 s).

### 6.7 Banco de Horas: PDF e pesquisa
- `bh/pdf.py`: relatório mensal A4 para assinatura (tabela Dia/Marcações/Prevista/Trabalhada/Saldo/Situação), marca d'água "RASCUNHO" se incompleto, resumo (saldo anterior, movimento, acumulado) e três assinaturas (Funcionário, Gerência, Administração); mostra batidas originais quando corrigidas.
- `bh/search.py`: busca por tela, funcionário (nome ou Número I, até 20) e importação, respeitando os módulos `bh_consulta`, `bh_gestao`, `bh_dp`.


---
## Bloco 7 (aprofundado) — NucleAI, ajuda, tutorial e personalização [FATO: lidos `ajuda.py`, `ajuda_busca.py`, `ajuda_admin.py`, `ajuda_stats.py`, `nucleai_comandos.py`, `views_nucleai.py`, `views_ajuda.py`, `tutorial.py`, `temas.py`, `views_favoritos.py`, `views_novidades.py`, `novidades.py` (início)]

### 7.1 O que é a NucleAI
Assistente com ajuda local e camada opcional de IA via OpenRouter. Aparece como um usuário especial (`usuarios.sistema=3`, nome `NucleAI`) nas Mensagens. Oferece **tirar dúvidas**, **cumprir pedidos** e, quando a IA está liberada, consultar dados e apresentar resultados no chat. A gerência configura chave e modelos, revisa trocas, saúde e consumo de tokens na tela IA online.

### 7.2 Ajuda
- **Base de conhecimento:** árvore tema → módulo → área → texto (`ajuda_conteudo_a/b/c.py`, montada por `ajuda_base.py`), na mesma ordem do menu. A administração pode **editar** textos, **criar** áreas/módulos/temas e **restaurar** o original (tabela `ajuda_conteudo`, estados `EDITADA` e `NOVA`; título até 70 caracteres, texto de 20 a 1800).
- **Permissão por módulo:** cada módulo da ajuda herda a chave de permissão do item do menu (`_montar_acesso`); o usuário só vê temas e módulos que pode usar.
- **Máquina de estados** (`ajuda_sessoes`): `TEMA → MODULO → AREA → SATISFEITO → NOTA`, com `ESCOLHA` (várias possibilidades), `POS` ("não ajudou": outra área, outro módulo, outro tema, chamar gerência, encerrar), `CMD` (aguardando Sim/Não de um pedido) e `ENCERRADO`.
- **Busca por texto livre** (`ajuda_busca.Indice`): normaliza (sem acento), remove palavras vazias, reduz a radicais, agrupa sinônimos em *conceitos* (imprimir/impressão, remarcar/reagendar/resgatar, convênio/plano etc.), corrige digitação por similaridade fonética (mesma letra inicial, parecença > 0,8) e pontua por BM25 com pesos (título da área 4, frases de exemplo 3, módulo 3, tema 1, texto 1). `decidir`: responde direto se a cobertura e a folga sobre o 2º lugar forem altas; mostra até 3 possibilidades se a cobertura ≥ 0,34; senão diz que não entendeu e registra em `ajuda_nao_entendidas`.
- **Registro:** o chat é temporário (apagado ao encerrar); fica em `ajuda_registros` a essência (quem, assunto, dúvida, origem LISTA/TEXTO, resultado, nota 1–5). Resultados: `RESOLVEU`, `RESOLVEU_E_NOVA`, `NAO_RESOLVEU`, `SEM_AVALIACAO`, `ABANDONOU`.
- **Limpeza** (`ajuda.limpar`, chamada ao listar contatos do chat): despedidas vencidas (padrão 60 s), conversas abandonadas (padrão 6 h; 1 a 72 h) e sessões encerradas sem mensagens.
- **Configuração** (tabela `config`): `nucleai_ativa`, `nucleai_abandono_h`, `nucleai_despedida_s`, `nucleai_destinatarios` (quem recebe os pedidos; vazio = toda a gerência).
- **Chamado à gerência:** cria `ajuda_chamados` e manda mensagem com botão "falar com o usuário" aos destinatários (válida 7 dias). A gerência abre a conversa com uma pergunta de confirmação (Sim/Não); se o usuário confirma, a NucleAI envia à gerência o passo a passo da área, uma descrição do módulo e quem tem acesso, um trecho relacionado do `LEIA-ME.md` e um roteiro de checagem (`CHECKLIST`). Status: `ABERTO → EM_ATENDIMENTO → RESOLVIDO`.

### 7.3 Comandos (`nucleai_comandos.py`)
- **37 comandos** (19 de baixo risco, 12 médio, 6 alto), cada um com palavras-chave por radical, palavras de exclusão (`nao`), módulo exigido e função de execução.
- Regras: comando que **faz** algo só executa após resposta **Sim** (pelo botão ou digitando); consulta só de leitura responde direto (`confirmar=False`). Perguntas iniciadas por *como, onde, qual, quais, quando, porque, quem, por que, o que, para que* continuam sendo dúvidas de ajuda.
- Permissão = módulo da tela + modo do comando: padrão baixo = todos; médio = só os escolhidos (e a gerência); alto = só a gerência (administrador ou módulo `gerencia`). A gerência pode mudar o modo de cada comando (alto só admite `gerencia` ou `ninguem`).
- Pedido pendente expira em `VALIDADE_MIN = 30` e a permissão é conferida **de novo** na hora do Sim.
- Execução grava no registro de atividades ("Comando da NucleAI: …"). Erros em um comando nunca derrubam o chat.
- **Comandos de alto risco:** fazer backup, reabrir caixa fechado (últimos 7 dias, por nome), desfazer a última ação registrada, saúde do sistema, registros de hoje, usuários e perfis (só administrador).
- **Comandos que alteram dados:** reabrir caixa, desfazer, encerrar/reabrir pesquisa de satisfação, backup (gera arquivo).
- `/ajuda/imprimir?u=` só aceita caminhos internos (`/...`, sem `//` e sem `:` antes de `?`).

### 7.4 Tutorial, temas, favoritos e log de versões
- **Tutorial** (`tutorial.py` + `static/js/tutorial.js`): roteiro personalizado pelos grupos do menu que o usuário enxerga; perfil principal (recepção, financeiro, gestão, pessoal) decide a ordem. `usuarios.tutorial_visto` impede repetir; pode rever em "Minha conta".
- **Temas** (`temas.py`): 8 cores (verde padrão, azul, vinho, roxo, terracota, grafite, oceano, índigo) e brilho claro/escuro, por usuário e válidos em qualquer computador; cor do calendário da agenda `#rrggbb`.
- **Favoritos** (`views_favoritos.py`): cada usuário monta o painel com até 40 atalhos dos módulos que pode abrir, modo grade ou lista, 1 ou 2 colunas, cor e ícone.
- **Log de atualizações** (`novidades.py`): lista de versões (a mais recente primeiro) com categorias Novidade, Melhoria e Segurança e PDF por versão. É a **fonte do histórico do produto** (ver NEGOCIO_E_PRODUTO.md).
- **IA online da NucleAI** (`views_nucleai_ia.py` e módulos `nucleai_*`): chave OpenRouter e lista ordenada de modelos com troca automática; arquivo de trocas classificado Natural/Estranha e incluído no backup; chat de treino/teste (`Teste#XXXX`), memória compartilhada como manual, leitura de arquivos e relatórios. A ferramenta Ilustrar gera planilha, gráfico, cartões informativos ou decisão, respeitando permissões. Consulta e remarcação de agenda pedem confirmação; alterações são auditadas como feitas com auxílio da NucleAI e podem ser desfeitas pela gerência. A tela apresenta saúde e gráficos de tokens. A ajuda administrativa está em `ajuda_conteudo_c.py`.


---
## Bloco 8 (aprofundado) — Qualidade, pesquisa, ONA, dashboard e saúde [FATO: lidos `qualidade.py`, `qualidade_dados.py`, `qualidade_robo.py`, `pesquisa.py`, `views_pesquisa.py`, `ona.py`, `views_dashboard.py`, `saude.py`, `views_saude.py`]

### 8.1 Gestão da Qualidade (`qualidade.py`, tabelas `cq_*`)
- As tabelas são criadas por `garantir(db)` (uma vez por banco e por processo); não mexe nas dos outros módulos.
- **Cadeia de trabalho** (docstring): Indicador → Problema → Causas (Ishikawa 6M, 5 Porquês) → Plano (5W2H) → PDCA.
- Entidades: problemas (`cq_problemas`: PDCA em 4 fases P/D/C/A, GUT, status `RASCUNHO|ABERTO|EM ANDAMENTO|CONCLUÍDO|DESCARTADO`), causas, porquês (5 níveis), ações 5W2H, riscos (matriz 5×5), SWOT (itens com peso e 4 estratégias cruzadas FO/FA/DO/DA), fluxogramas (`cq_processos`, desenho em JSON validado, até 400 etapas, versão e aprovação), organograma (hierarquia sem ciclos), ocorrências, motivos de falta, metas dos KPIs e avaliação de fornecedores.
- **GUT** = G × U × T (1 a 5 cada). **Risco** = probabilidade × impacto: ≥ 15 Crítico, ≥ 10 Alto, ≥ 5 Moderado, senão Baixo.
- **Fornecedores:** 6 critérios padrão com peso (qualidade 3, prazo 2, atendimento 1, preço 1, documentação e licenças 2, segurança e conformidade 2), nota 1–5; percentual = pontos/máximo; ≥ 80% APROVADO, ≥ 60% APROVADO COM RESTRIÇÕES, abaixo REPROVADO (exige ação descrita). Próxima avaliação: 12 meses se aprovado, 6 caso contrário.
- Editar um fluxograma já `APROVADO` cria nova versão e volta a `RASCUNHO`.
- Ocorrências: 8 tipos (inclui "Laudo retificado", "Retrabalho / repetição de exame", "Equipamento parado"), 3 gravidades; abrir problema a partir de uma ocorrência converte gravidade em G/U (2, 4 ou 5).
- Motivos de falta (9 opções) alimentam o Pareto por motivo.

### 8.2 Indicadores (`qualidade_dados.py`)
- 18 indicadores com meta, situação (`ok`, `atencao`, `critico`, `sem_dado`) e série de 6 meses, **calculados com os dados do próprio sistema** (agenda, exames realizados, laudos, faturas, contas, blindagens, documentos, chamados da NucleAI) e com os que a Qualidade coleta. Os relatórios de gestão trazem só números agregados, sem nome de paciente.
- Metas iniciais (`METAS_PADRAO`, editáveis pela gerência): comparecimento ≥ 85%, faltas ≤ 15%, laudos em 24 h ≥ 90%, tempo médio de laudo ≤ 24 h, laudos pendentes 0, identificação ≥ 98%, registro completo ≥ 95%, desvio de atividade ≤ 5%, glosa ≤ 3%, recebimento atrasado ≤ 10%, contas atrasadas 0, documentos vencidos 0, resposta a chamados ≤ 4 h, ocorrências graves 0, satisfação ≥ 9, fornecedores avaliados 100%, retrabalho ≤ 2%, resgate ≥ 50%.
- **Situação:** para "quanto maior melhor", ok se ≥ meta, atenção se ≥ 90% da meta; para "quanto menor melhor", ok se ≤ meta, atenção até meta + folga (20% ou 1).
- Definições relevantes: **laudo** = tempo entre o horário do exame e `laudo_liberado_em` (prazo fixo `PRAZO_LAUDO_H = 24`, **não** o prazo configurável de `prazo_laudo.py`); **desvio de atividade** = |administrada − prescrita| / prescrita > 10%; **resgate** = faltas reagendadas entre as tratadas; **glosa** = valor líquido − recebido nas faturas; **blindagens em devolução ou devolvidas não contam como vencidas**.
- Cálculo em SQL agregado, com cache de 60 s (`cache_curto`) invalidado por um novo horário de agenda ou exame realizado.
- **Pareto** (9 fontes: faltas por exame/convênio/motivo/dia da semana, ocorrências por tipo/setor, laudo fora do prazo por exame, glosa por convênio, volume de exames): classe A até 80% acumulado, B até 95%, C o resto.

### 8.3 Robô do PDCA (`qualidade_robo.py`)
- **Motor de regras**, sem IA externa ("totalmente previsível e testável"): compara cada indicador com a meta e com o período anterior de mesmo tamanho, ignora taxas com base menor que 20 casos, procura concentração no Pareto (item com ≥ 30%), calcula GUT (gravidade pelo desvio e risco ao paciente, urgência pela piora ≥ 20%, tendência pela persistência nos últimos 3 meses), monta um problema `RASCUNHO` com PDCA, Ishikawa, 5 Porquês e 5W2H a partir de `qualidade_modelos.BIBLIOTECA` e pergunta o que falta quando não há dado.
- A gerência aceita (vira `ABERTO`), edita ou descarta (não volta a ser sugerido por 30 dias).
- `rotina_diaria`: uma análise por dia (últimos 30 dias), chamada pelo laço de `avisos.py`; avisa a gerência quando surgem problemas novos.

### 8.4 Pesquisa de satisfação (`pesquisa.py`, `views_pesquisa.py`)
- Até 10 perguntas, opções Ótimo/Bom/Ruim/Péssimo (notas 10, 7, 3, 0); nota da resposta = média. Campos opcionais: nome, telefone, elogio, sugestão. QR Code em SVG gerado com `reportlab` (sem biblioteca extra).
- **Página pública** `/pesquisa` sem login, mas **só para IPs privados, locais ou link-local** (`ip_interno`); uma resposta por IP a cada 40 s e campo-armadilha `site` contra robôs. O endereço do QR Code é o IP da máquina na rede (ou o endereço fixo definido pela gerência).
- Cada resposta avisa a gerência (só a nota) com botões Sim/Não e entra também em `cq_pesquisas` com `criado_por='PESQUISA QR CODE'`, alimentando o indicador de satisfação.

### 8.5 Relatório ONA (`ona.py`)
- Sete indicadores com numerador, denominador e percentual no período: identificação do paciente, registro completo, cadastro com CPF, cadastro com sexo, **laudo no prazo (usa o prazo configurável de `prazo_laudo.py`)**, laudos retificados e comparecimento na agenda; mais produção por exame, convênio e sexo. O docstring avisa que a lista oficial de indicadores da ONA deve ser conferida com o manual vigente.

### 8.6 Dashboard (`views_dashboard.py`)
- Períodos: hoje, 7 d, 30 d, mês, mês anterior, ano, tudo e personalizado. KPIs de atendimentos, pacientes distintos, primeira vez, guias, média por dia; série diária (até 62 dias) ou mensal; 12 meses; rankings (exame, convênio, médico, usuário); dia da semana; faixa etária; alertas de contas e doses. Compara com o período anterior de mesma duração.
- **Otimizado para volume:** comentários citam teste com **3,6 milhões de atendimentos** (índice `ix_atend_cli_data`, rankings numa passada, cache de 30 s, ou 120 s para períodos longos).

### 8.7 Saúde do sistema (`saude.py`, `views_saude.py`)
- Nota 0–100 por média ponderada: disco 25, backup 25, banco 20, caixas 10, documentos 10, erros 10. Disco: precisa de ≥ 2 GB ou 20× (banco + backups); backup: ótimo ≤ 1 dia, ruim > 7 dias ou inexistente; banco: `PRAGMA quick_check`; caixas de dias anteriores abertos = crítico; documentos vencidos = crítico; erros internos (tabela `auditoria`, módulo "Sistema", ação "Erro interno") nas últimas 24 h e 7 dias.


---
## Bloco 9 (aprofundado) — Operação: backup, CLI, servidor e bandeja [FATO: lidos `backup_pacote.py`, `cli.py`, `views_admin.py` (backup, pastas, configurações), `servidor.py`, `tray.pyw`, `INICIAR.bat`, `PROJETO_1.5.0.md`]

### 9.1 Backup (`backup_pacote.py`, `views_admin.py`, `cli.py`)
- Formato: `.zip` com `sistema.db` + `anexos.db` + `LEIA-ME.txt` (cópia consistente pela API de backup do SQLite, mesmo com o sistema em uso). Gravação em arquivo temporário e renomeação ao final (nunca deixa zip incompleto). Backups antigos `.db` (só o sistema) ainda são aceitos.
- **Retenção:** o comando `backup` (CLI/bandeja) mantém só os **30** `BACKUP_*` mais recentes; os prefixos `ANTES-DE-RESTAURAR`, `ANTES_DA_IMPORTACAO`, `ANTES_DO_BANCO_DE_HORAS` e `ANTES_DOS_EXAMES` não são apagados automaticamente. O backup feito pela tela (`fazer_backup`) **não** aplica essa retenção. Não há agendamento automático de backup no código lido (só manual: tela, bandeja, comando da NucleAI ou CLI).
- **Reconhecimento por conteúdo:** o zip precisa ter os dois membros esperados (assinatura "SQLite format 3"), taxa de compressão ≤ 2000×, total ≤ 40 GB, no máximo 20 itens; extração só dos dois membros, em blocos, para pasta temporária (sem *path traversal* nem *zip bomb*); o banco extraído passa em `PRAGMA quick_check` e tem as tabelas `usuarios`, `clientes`, `config`.
- **Restauração** (só administração e gerência): duas etapas com **código de 6 dígitos** de uso único válido por 300 s; guarda antes um zip `ANTES-DE-RESTAURAR`; se a segunda parte falha, volta a primeira; depois roda `db.inicializar` para aplicar colunas novas de versões antigas. Busca em outra pasta: só lê, não entra em subpastas nem segue links, até 300 arquivos; só se restaura o que a busca listou (sessão, 600 s).
- Quem tem o módulo `backup` faz e baixa backups; restaurar é só administração/gerência.

### 9.2 Atalhos de pastas
- Em `Pastas`, a administração cadastra nome e caminho. Como o navegador não abre pastas do Windows, o sistema gera um `.reg` que registra no computador do usuário o protocolo `nucleleste-pasta:`; ele abre **somente pastas** (ou seleciona arquivo) em unidade mapeada (`X:\`) ou servidor de rede da lista, nunca executa arquivos.

### 9.3 Configurações da clínica
- `clinica_nome`, `clinica_cidade`, `clinica_cnpj` e `laudos_pasta_word` (pasta com os laudos em Word) em `config`; o nome da clínica vai nos cabeçalhos de PDF e relatórios.

### 9.4 CLI (`python -m app.cli`)
`backup`, `admin-senha ARQUIVO` (lê a senha do arquivo e **apaga** o arquivo; mínimo 3 caracteres; cria o ADMIN se não existir), `importar-db` (só se não houver clientes), `config PORTA`, `importar-exames`, `importar-bh`. `--dados PASTA` define a pasta de dados. Importações fazem backup antes.

### 9.5 Servidor e bandeja
- `servidor.py`: Waitress em `0.0.0.0` com **48 threads** (24 podem ficar seguradas pelas consultas do chat); `--dev` usa o servidor do Flask em `127.0.0.1` com recarga.
- `tray.pyw` (API do Windows via `ctypes`, sem biblioteca extra): `--servidor` sobe só o servidor como tarefa do Windows; sem argumento mostra o ícone da bandeja (e sobe o servidor se não houver tarefa). Mutex global evita duas cópias; menu com endereços de rede (copia ao clicar), abrir pastas do programa/dados/backups/log, backup agora, sobre e sair. Log em `<pasta de dados>/logs/` (rotaciona acima de 2 MB). Se a porta já está em uso por outro servidor do sistema, a bandeja vira só painel; se o servidor cair, a tarefa reinicia.
- `INICIAR.bat`: modo simples; cria um ambiente virtual em `%LOCALAPPDATA%\SistemaNucleleste\venv`, instala os requisitos e abre `http://localhost:8080` (porta fixa no arquivo, não lê `config.json`).

### 9.6 Plano e desempenho da 1.5.0 (`PROJETO_1.5.0.md`)
- Itens 1–8 "feitos e testados"; item 9 (login OAuth) fora da versão (depende de domínio com HTTPS). Instalação real ainda em 1.4.9, aguardando aprovação do usuário.
- **Regras fixas do projeto:** não mexer na instalação real (`C:\ProgramData\Nucleleste`) nem rodar instalador sem aprovação; sem commit/push sem pedido; mostrar resultado de testes sem afirmar o não verificado; se algo imprevisto for tocado, parar e perguntar.
- **Teste de sobrecarga** (dados sintéticos): 2 milhões de linhas e 50 usuários: 24,5 req/s, 0 erros após otimizações; 200 usuários: saturado (23 req/s, p50 5,2 s, 0 erros); queda no meio de ~340 gravações: banco íntegro. **Limite registrado:** um processo Python satura em ~25 req/s; acima de ~50 usuários simultâneos seria preciso outro modelo de servidor.


---
## Front-end (JavaScript e templates) [FATO: lidos `app.js`, `sessao.js`, `chat.js`, `agenda.js`, `bh.js`, `atualizacao.js`, `aguarde.js`, `faturamento.js`, `atendimento_form.html`]
- **Sem framework**: JavaScript puro, SVG para gráficos (`dashboard.js`, `faturamento.js`), `<dialog>` para janelas, `localStorage` para preferências por navegador (largura das colunas e formatação da agenda, sessão) e `sessionStorage` para o resumo de mensagens não lidas. Cabeçalho `X-CSRF-Token` em todo `fetch` POST; `X-Passivo: 1` marca consultas automáticas.
- **`app.js`**: maiúsculas automáticas (`data-maiusculas`), máscaras de CPF/CEP/telefone, confirmação (`data-confirmar`), seletor de cliente com busca por 2+ letras e atraso de 220 ms, **proteção contra clique duplo** em formulários POST (`data-enviado`) e a camada visual animada (hero, revelação em cascata, contagem de números).
- **`sessao.js`**: **não há limite de inatividade**; a sessão acaba ao fazer logoff ou ao fechar o navegador. Se o navegador reabre com sessão restaurada e a "batida" gravada no `localStorage` tem mais de 75 s, a sessão é encerrada. (Resolve a pendência 10.)
- **`chat.js`**: batida de presença a cada 20 s por aba (`/sessao/batida`), aviso `sendBeacon` ao sair; consulta "segurada" até 12 s (`ESPERA_S`, o servidor aceita até 15); avisos (toast, bipe, título piscando, notificação do navegador); cita mensagens, envia imagem por botão ou Ctrl+V (JPG/PNG/GIF/WebP até 5 MB) e busca na conversa; botões das mensagens de ação (laudo liberado → "Marcar como entregue", pedidos da NucleAI, avaliação, duplicidade de agenda).
- **`agenda.js`**: calendário, grade tipo planilha, colunas redimensionáveis (salvas no navegador), formatação do texto, reservas, remarcar/copiar/encaixar, WhatsApp, modo somente leitura (estagiário); atualiza a cada 5 s.
- **`bh.js`**: escala (clique no dia preenche o formulário), filtros de tabela, **jornadas sugeridas "44" (8 h de segunda a sexta + 4 h no sábado) e "20" (4 h de segunda a sexta)**, mensagens ao vivo do Banco de Horas por consulta curta (3 s na conversa, 15 s na lista).
- **`atualizacao.js` / `aguarde.js`**: faixa de aviso, tela de espera com 10 cenas animadas (tom bem-humorado sobre o dia a dia da clínica) e recarga automática.
- **`atendimento_form.html`**: o formulário central monta o questionário PNT a partir de `exames_json`; marca medicamentos como obrigatórios só quando o exame pede; "Não se aplica" e "Receita em anexo" preenchem o campo; mostra os exames anteriores do cliente com botão "Abrir laudo (Word)" e **obriga escolher o último exame** (ou "Não informar exame anterior"); a previsão do laudo vem de `/atendimentos/previsao`.
- **Templates**: 153 arquivos HTML (Jinja) e 18 scripts (~4 mil linhas), 2,3 mil linhas de CSS. Não foram lidos um a um os demais templates.

## Apostila (PDF)

- Código: `app/apostila.py`, função `gerar_pdf(db, versao, clinica)`, em reportlab, no visual do dossiê ONA.
- Rota pública `auth.apostila` (`/apostila.pdf`), sem login. Liberada pelo prefixo `auth.` em `modulos.modulo_do_endpoint`. Link na tela de entrada (`login.html`).
- Conteúdo: a árvore de ajuda efetiva, `ajuda.base(db)`: temas, módulos e áreas. Passos (`1.`, `2.1.`) viram blocos numerados; `•` vira marcador.
- Edições da administração na NucleAI entram na apostila, porque `base(db)` já devolve a versão editada.
- Cache em memória por (versão, nome da clínica, assinatura de `ajuda_conteudo`). Só refaz o PDF quando algo muda; um `threading.Lock` evita gerar duas vezes ao mesmo tempo.
- Textos da capa, de 'Como usar' e de 'Primeiros passos' ficam no próprio `apostila.py`.
