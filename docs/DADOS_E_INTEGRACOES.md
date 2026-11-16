# Dados e integrações

Estado: **bloco 1 (esquema base e persistência)**. Tabelas dos blocos seguintes estão listadas com o arquivo dono, mas ainda não detalhadas.

## 1. Persistência [FATO]
- **Banco principal** `sistema.db` (SQLite). Conexão por requisição em `app/db.py: get_db()` (guardada em `flask.g`, fechada em `close_db`). Pragmas em `conectar()`: `journal_mode=WAL`, `busy_timeout=30000`, `cache_size=-16000` (16 MB), `temp_store=MEMORY`; sem mmap de propósito (no Windows impede trocar o arquivo na restauração de backup).
- **Banco de anexos** `anexos.db`, ao lado do principal (`anexos.caminho_ao_lado`). Recebe os arquivos que antes ficavam em BLOB (`arquivos_docs.conteudo`, `bh_employee_documents.content`) e as imagens do chat (24 h). Ver `app/anexos.py` (bloco 6).
- **Pasta de dados**: `config.json`/`NUCLELESTE_DADOS`; contém `sistema.db(-wal,-shm)`, `chave_secreta.txt` (chave de sessão do Flask, 64 hex), `backups/`. Em produção: `C:\ProgramData\Nucleleste` (declarado em `LEIA-ME.md`; não verificado aqui).
- **Datas** são texto ISO (`YYYY-MM-DD`, `agora()` = `YYYY-MM-DD HH:MM:SS`, hora local sem fuso). Valores monetários são `REAL`.

## 2. Inicialização e evolução do esquema [FATO] (`db.inicializar`, `db.migrar`)
Ordem em cada partida do servidor (`create_app` → `inicializar`):
1. `executescript(SCHEMA)` (todos os `CREATE TABLE/INDEX IF NOT EXISTS`).
2. `migrar`: para cada tabela em `COLUNAS_NOVAS`, `ALTER TABLE ADD COLUMN` das colunas ausentes (é assim que bancos antigos evoluem); recria índices `ix_contas_fornecedor`, `ix_contas_parcela_grupo`, `ix_usuarios_bh_func` (único parcial: 1 acesso por funcionário do BH).
3. Semeia: `EXAMES_PADRAO` (13 exames com fichas), `exame_cores` (de `exames_cores.CATEGORIAS_PADRAO`, se vazia), `CONFIG_PADRAO` (nome, cidade, CNPJ da clínica, valor unitário da blindagem, atalhos de pastas), fichas "Plano terapêutico MDN" (`fichas_plano.garantir`).
4. Migração única 1.5.0: copia `convenios.valor_mibi/ossea/tgi/paratgi/galio` para `convenio_valores` (marca a execução em `config.convenio_valores_migrados`).
5. Normaliza reservas antigas do UNACON para `reservado_convenio/reserva_convenio='UNACON'`.
6. Usuários: se não há nenhum, cria `ADMIN` com senha `admin` (comentário no código manda trocar); garante os 3 usuários internos (coluna `usuarios.sistema`: 1 = AVISOS DO SISTEMA, 2 = LAUDOS DO SISTEMA, 3 = NucleAI) com senha aleatória que ninguém conhece.
7. Marca como `ATUALIZACAO` mensagens antigas "Aviso de atualização:%" dos avisos do sistema.
8. `migracoes.zerar_movimento_antigo` e `migracoes.migrar_anexos` (ver §4) — **executam automaticamente, em toda partida, até estarem registradas** em `migracoes_aplicadas`.

## 3. Tabelas definidas em `app/db.py`
| Domínio | Tabelas | Observações |
|---|---|---|
| Acesso | `usuarios`, `acessos` (login/logout/senha incorreta), `auditoria`, `presenca` | `usuarios.usuario` único sem distinção de maiúsculas; `modulos` = JSON de chaves (NULL = perfil legado); colunas extras: `bh_funcionario_id, trocar_senha, sistema, tema, brilho, cor_calendario, favoritos, laudo_perm, tutorial_visto, arquivado_em, visto_em` |
| Cadastros | `clientes`, `convenios`, `convenio_valores`, `medicos`, `exames`, `fichas_extras`, `config` | `exames.documentos` = JSON `[[slug_ficha, cópias]]`; `exames.questionario` p.ex. `linfonodo`; `convenios.gera_caixa` (ver pendência 7) |
| Atendimento | `atendimentos`, `guias`, `caixa`, `doses` | `atendimentos.respostas` e `medicamentos` guardam texto/JSON; `previsao_laudo` calculada ao lançar |
| Exames realizados | `realizacoes`, `exame_cores` | 40+ colunas; `laudo_situacao` e carimbos de liberação/entrega/arquivo/retificação alimentam o mapa de laudos |
| Agenda | `agenda_exames` (uma agenda = exame + dia), `agenda_horarios` (linhas), `agenda_espera`, `agenda_bloqueios`, `agenda_modelos`, `agenda_ordem_exames` | `agenda_horarios` tem `ON DELETE CASCADE`; `status` padrão `AGENDADO`; reservas por convênio em `reservado_unacon/reservado_convenio` |
| Financeiro | `contas` (parcelamento: `parcela_n/total/grupo`), `fornecedores` (CNPJ único quando informado), `faturas` | |
| Caixa | `caixa`, `caixa_sessoes` (único por usuário+dia) | `cxd_*` (caixa diário da empresa) são criadas em `caixa_diario.py` |
| Banco de Horas | `bh_employees, bh_schedules, bh_imports, bh_import_rows, bh_corrections, bh_adjustments, bh_audit_log, bh_report_snapshots, bh_roster_days, bh_employee_documents, bh_messages, bh_message_threads` | nomes em inglês (vieram de outro programa); índice único parcial `bh_canonical_attendance` garante 1 batida aceita por (relógio, dia) |
| Comunicação | `chat_mensagens`, `atualizacao_avisos`, `docs_avisos` | `docs_avisos` PK (documento, vencimento, fase) evita avisar duas vezes |
| Documentos/blindagens | `arquivos_docs`, `blindagens` (lote único), `blindagem_devolucoes` | |
| NucleAI | `ajuda_conteudo, ajuda_registros, ajuda_nao_entendidas, ajuda_chamados, ajuda_sessoes` | |

Tabelas criadas fora de `db.py` (a detalhar): `anexos` (`anexos.py`), `cxd_inicio/cxd_lancamentos/cxd_retidas` (`caixa_diario.py`), `migracoes_aplicadas` (`migracoes.py`), `nucleai_cmd_*` (`nucleai_comandos.py`), `cq_*` (19 tabelas de qualidade/pesquisa em `qualidade.py` e `pesquisa.py`).

## 4. Migrações de dados (`app/migracoes.py`) [FATO]
- Controle: tabela `migracoes_aplicadas(nome, aplicada_em, detalhe)`.
- **Automáticas na partida**: `zerar_movimento_v1` (`zerar_movimento_caixa_v1`): apaga `caixa_sessoes` e `caixa` com `status='PAGO'` **uma única vez** (pedido da versão 1.4.4), após copiar o banco para `backups/ANTES_ZERAR_CAIXA_*.db`. `anexos_externos_v1`: move BLOBs para `anexos.db` conferindo tamanho e SHA-256 antes de esvaziar a coluna; falha deixa o arquivo onde estava; faz `VACUUM` depois; cópia prévia `ANTES_ANEXOS_*`.
- **Manuais** (`python -m app.migracoes relatorio|aplicar --confirmo`): `telefones_padrao_v1` (padroniza `contato` em agenda_horarios, agenda_espera, clientes) e `sexo_clientes_v1` (preenche `clientes.sexo` pelo último exame realizado).

## 5. Integrações externas [FATO]
- **BrasilAPI** e **ReceitaWS**: consulta de CNPJ em `app/fornecedores.py:17-18` (única integração de rede encontrada até agora).
- Relógio de ponto: arquivo `.xls` importado por upload (`xlrd`), não é integração viva (bloco 5).
- Protocolo do Windows `nucleleste-pasta:` para abrir pastas da rede (declarado em `LEIA-ME.md`; a verificar nos blocos 8–9).


---
## Inventário complementar de tabelas e integrações (blocos 3 a 9) [FATO: lido nos módulos citados]

### Tabelas por módulo (sistema.db)
| Módulo | Tabelas |
|---|---|
| Agenda | `agenda_exames`, `agenda_horarios`, `agenda_bloqueios`, `agenda_modelos`, `agenda_espera`, `agenda_ordem_exames` |
| Caixa do balcão | `caixa` (por atendimento), `caixa_sessoes` (abertura/fechamento por usuário e dia) |
| Caixa diário da empresa | `cxd_inicio` (uma linha), `cxd_lancamentos`, `cxd_retidas` (criadas por `cxd.garantir`) |
| Contas e fornecedores | `contas` (com `parcela_n/total/grupo`), `fornecedores` |
| Faturamento | `faturas` |
| Banco de Horas | `bh_employees`, `bh_schedules`, `bh_imports`, `bh_import_rows`, `bh_corrections`, `bh_adjustments`, `bh_audit_log`, `bh_report_snapshots`, `bh_roster_days`, `bh_employee_documents`, `bh_messages`, `bh_message_threads` |
| Chat e avisos | `chat_mensagens` (inclui `acao`, `acao_url`, `acao_resp`, `chamado_id`, `laudo_id`, `expira_em`, `anexo_*`), `docs_avisos`, `atualizacao_avisos`, `presenca` (abas) |
| Documentos | `arquivos_docs` (metadados; conteúdo em `anexos.db`) |
| NucleAI | `ajuda_sessoes`, `ajuda_registros`, `ajuda_chamados`, `ajuda_nao_entendidas`, `ajuda_conteudo`, `nucleai_cmd_config`, `nucleai_cmd_acesso`, `nucleai_cmd_pendentes` |
| Qualidade | `cq_problemas`, `cq_causas`, `cq_porques`, `cq_acoes`, `cq_riscos`, `cq_swot_analises`, `cq_swot_itens`, `cq_processos`, `cq_organograma`, `cq_ocorrencias`, `cq_pesquisas`, `cq_falta_motivos`, `cq_kpi_metas`, `cq_forn_criterios`, `cq_forn_avaliacoes`, `cq_forn_notas`, `cq_robo_execucoes`, `cq_robo_descartes` |
| Pesquisa de satisfação | `cq_sat_perguntas`, `cq_sat_respostas`, `cq_sat_itens` |
| Núcleo | (ver bloco 1) `clientes`, `convenios`, `convenio_valores`, `medicos`, `exames`, `atendimentos`, `guias`, `doses`, `realizacoes`, `blindagens`, `blindagem_devolucoes`, `usuarios`, `auditoria`, `acessos`, `config`, `migracoes_aplicadas` |

### anexos.db
Tabela única `anexos` (origem, origem_id, sha256, tamanho, conteúdo, criado_em). Origens vistas: `arquivos_docs`, `bh_employee_documents`, `chat`. Modo WAL, `busy_timeout` 30 s.

### Chaves de `config` vistas neste conjunto
`clinica_nome`, `clinica_cidade`, `clinica_cnpj`, `laudos_pasta_word`, `whats_mensagens` (JSON), `pastas` (JSON), `backup_pasta_externa`, `blindagem_valor_unitario` (padrão "405,80"), `laudo_prazo_*`, `laudo_feriados_extras`, `nucleai_ativa`, `nucleai_abandono_h`, `nucleai_despedida_s`, `nucleai_destinatarios`, `pesquisa_ativa`, `pesquisa_endereco`, `pesquisa_perguntas_editadas`, `fichas_plano_v1`.

### Integrações e pontos de contato externos
| Com quê | Como | Observação |
|---|---|---|
| BrasilAPI / ReceitaWS | HTTPS GET do CNPJ (`fornecedores.consultar_cnpj`, timeout 8 s) | única chamada de rede para fora; envia só o CNPJ |
| WhatsApp | links `whatsapp://send` e `https://wa.me/<número>?text=` abertos no navegador do usuário | o sistema só monta o texto; o usuário envia |
| Relógio de ponto | importação manual do relatório `.XLS` (xlrd) | formato com aba "Registro de Presença" |
| Sistema antigo | `BD.mdb` (exportado em JSON) e planilha `VERSÃO 2.1 RECEPÇÃO1.xlsm` (aba `log`) via `ferramentas/importar_dados.py`; `EXAMES.xlsx` via `app.exames_import`; banco do programa Banco de Horas antigo via `bh/migracao.py` | importações pontuais, com backup antes |
| Laudos em Word | leitura da pasta configurada (rede), até 3 níveis, sem seguir links; abre só `.doc/.docx/.docm/.rtf` dentro da pasta | só leitura |
| Pastas de rede no Windows | protocolo `nucleleste-pasta:` registrado por arquivo `.reg` em cada PC | abre só pastas |
| Windows | tarefa agendada "Sistema Nucleleste (servidor)", mutex global, ícone de bandeja via `ctypes` | `tray.pyw` |
| Instalador | consulta `127.0.0.1/atualizacao/pendente` e `POST /atualizacao/iniciar` com a chave do servidor | só local |
| Rede interna | pesquisa pública `/pesquisa` por QR Code, aceita só IP privado | sem login |
| Ícones | biblioteca Lucide **embutida** (sem depender da internet) | ver `novidades.py` 1.4.7 |
