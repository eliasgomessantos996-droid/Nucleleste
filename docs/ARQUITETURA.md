# Arquitetura (Fase 1: inventário)

## 1. Tecnologias [FATO]
- Python; dependências em `requirements.txt`: `flask>=3.0`, `waitress>=3.0`, `xlrd>=2.0.1` (ponto `.xls`), `reportlab>=4.0` (PDF), `openpyxl>=3.1` (Excel).
- Banco: SQLite, arquivo `sistema.db` (a `LEIA-ME.md` fala em modo WAL; presença de `-wal`/`-shm` em `dados/` confirma). Anexos em um segundo banco `anexos.db` (`app/anexos.py`).
- Front-end: templates Jinja (`app/templates`, 90 itens + `fichas/` com 24) e JavaScript/CSS puros em `app/static/{js,css}`; sem framework.
- Instalação: Inno Setup (`instalador/nucleleste.iss`), `build.ps1`, tarefa do Windows (`instalar_servico.ps1`, `remover_servico.ps1`), bandeja `tray.pyw` (ctypes).
- Não é repositório Git; não existe `docs/` anterior. Há `LEIA-ME.md` (191 linhas) e `PROJETO_1.5.0.md` (plano/estado da 1.5.0).

## 2. Estrutura de diretórios
| Caminho | Responsabilidade aparente |
|---|---|
| `servidor.py` | entrada web: `create_app(avisos_automaticos=True)`; `--dev` usa servidor do Flask em 127.0.0.1, senão Waitress em 0.0.0.0 com 48 threads |
| `tray.pyw` | entrada Windows: ícone na bandeja; `--servidor` sobe só o servidor (usado pela tarefa agendada); lê pasta de dados de `NUCLELESTE_DADOS` ou `local_dados.txt` |
| `app/__init__.py` | fábrica `create_app`, configuração, ciclo before/after request, registro de 29 blueprints |
| `app/db.py` | esquema (~50 tabelas), migrações por `ALTER TABLE`, usuário `ADMIN` inicial |
| `app/migracoes.py` | tabela `migracoes_aplicadas` (migrações versionadas) |
| `app/modulos.py` | 37 módulos de permissão, perfis (`PRESETS`), menu, abas, mapa endpoint→módulo |
| `app/views_*.py` | rotas (Blueprints), uma por área |
| `app/*.py` (demais) | regra de negócio e geração de documentos (`*_docs.py` = PDF/Excel) |
| `app/bh/` | Banco de Horas (incorporado de outro programa): `core, documents, messages, migracao, pdf, planning, portal, search` |
| `app/ajuda*.py`, `nucleai_comandos.py`, `views_nucleai.py` | assistente NucleAI (sem IA externa) |
| `app/qualidade*.py`, `pesquisa*.py`, `ona*.py` | qualidade, PDCA, pesquisa de satisfação, relatório ONA |
| `ferramentas/` | conversão de fichas, importação do sistema antigo, carga/estresse |
| `tests/` | 42 arquivos `test_*.py` (unittest) |
| `instalador/` | build do Setup; `build/` e `cache/` são artefatos (ignorar), `saida/` guarda `.exe` |
| `dados/` | **dados reais locais** (banco, chave secreta, backups). Não abrir nem alterar |
| `__pycache__/`, `instalador/build/`, `instalador/cache/` | gerados; fora da investigação |
| `SERSELIASAPPDATAocaltempdbg_nai.txt` | arquivo solto na raiz, nome malformado, parece depuração [?] (ver pendências) |

## 3. Pontos de entrada [FATO]
1. `servidor.py` (web). 2. `tray.pyw` (bandeja/serviço). 3. `app/cli.py` (`backup`, `admin-senha`, `importar-db`, `importar-exames`, `importar-bh`, `config`). 4. `INICIAR.bat`, `MIGRAR_DADOS.bat`, `.cmd` em `instalador/`. 5. `ferramentas/*.py` (utilitários isolados).

## 4. Configuração [FATO] (`carregar_config`, `app/__init__.py:17`)
Ordem: `config.json` da raiz (`porta`, `pasta_dados`) → variável `NUCLELESTE_DADOS` substitui a pasta → `config.json` dentro da pasta de dados só pode mudar `porta` → `NUCLELESTE_PORTA` vence. A chave de sessão é gerada e guardada em `chave_secreta.txt` na pasta de dados (`_chave_secreta`). Outras variáveis: `NUCLELESTE_TAREFA` (nome da tarefa do Windows).

## 5. Ciclo de cada requisição [FATO] (`create_app`, `app/__init__.py:95`)
1. `before_request`: (a) tela de espera 503 após atualização (`atualizacao.espera_restante`); (b) carrega usuário ativo da sessão; (c) gera token CSRF e exige em todo POST, exceto `atu.iniciar` e `pesq.publica`; (d) calcula módulos (`modulos.modulos_do_usuario`); (e) força troca de senha se `trocar_senha`; (f) bloqueia endpoint sem módulo (`modulos.modulo_do_endpoint`; `'__admin__'` = só admin; tupla = qualquer um); (g) funcionário com `bh_funcionario_id` e módulo `bh_portal` vai para `bh.portal_home`.
2. `after_request`: `auditoria.depois_da_requisicao`.
3. `context_processor`: injeta menu, abas, tema, estado da NucleAI, tutorial, contador do chat.
4. Erro 500 grava em `auditoria` ("Erro interno"); 400 mostra mensagem simples.
5. Se `avisos_automaticos`: `avisos.iniciar` dispara laço periódico a cada 600 s (conferido em visos.iniciar; o docstring antigo dizia hora em hora).

## 6. Mapa de módulos (blueprints registrados)
auth, inicio, cadastros, atendimentos, medicamentos, financeiro, documentos, admin, dashboard, faturamento, registros, bh, exames (`lanc`), chat, blindagens, agenda, arquivos, movimento, atualizacao (`atu`), saude, laudos, ona, ajuda, nucleai, favoritos, novidades, caixa_diario, qualidade, pesquisa.
Tamanho relativo (rotas por arquivo): qualidade 69, agenda 36, bh 33, admin 18, financeiro 18, cadastros 16, nucleai 11, exames 11, movimento 11, blindagens 11, atendimentos 10.
Maiores arquivos de lógica: `agenda.py` (1038 linhas), `qualidade.py` (859), `ajuda.py` (850), `db.py` (831), `nucleai_comandos.py` (693), `bh/core.py` (669).

Dependências: bibliotecas externas apenas as 5 de `requirements.txt` (confirmado pelos imports de `app/*.py`); integrações de rede citadas em `LEIA-ME.md`: BrasilAPI e ReceitaWS (CNPJ, `fornecedores.py`) [FATO: `app/fornecedores.py:17-18`].

## 7. Plano de investigação (ordem por dependência e risco)
1. **Base:** `db.py`, `migracoes.py`, `util.py`, `auth.py`, `modulos.py`, `auditoria.py`, `cache_curto.py` → DADOS_E_INTEGRACOES, REGRAS (permissões).
2. **Núcleo clínico:** cadastros → atendimentos → `fichas*.py` → medicamentos → exames realizados → laudos → blindagens.
3. **Agenda:** `agenda.py`, `views_agenda.py`, `agenda_reservas.py`, relatórios/financeiro/faltas/resgate.
4. **Dinheiro:** movimento, caixa, caixa_diario, financeiro, fornecedores, faturamento.
5. **Banco de Horas:** `app/bh/*`, `views_bh.py`, `usuarios_arquivo.py`.
6. **Comunicação:** chat, presença, avisos, mensagens_whats, anexos.
7. **NucleAI e ajuda:** `ajuda*.py`, `nucleai_comandos.py`, tutorial, novidades.
8. **Qualidade:** `qualidade*.py`, `pesquisa*.py`, `ona*.py`, `prazo_laudo.py`, dashboard.
9. **Operação:** atualização, backup (`backup_pacote.py`), saúde, `cli.py`, `tray.pyw`, instalador, `ferramentas/`.
10. **Testes:** mapear `tests/` por módulo e executar somente em ambiente isolado (banco temporário), registrando o resultado.

