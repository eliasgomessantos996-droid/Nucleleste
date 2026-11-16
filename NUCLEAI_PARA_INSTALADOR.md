# NucleAI com IA real (OpenRouter) — incluir no próximo instalador

Feito em 15/11/2026 pela sessão "Leia e entenda o sistema", via `/altroute` (AntiGravity + Codex), numa cópia de trabalho (`..\SistemaNucleleste-ia`) e depois juntado aqui no `SistemaNucleleste`.
A versão continua **1.6.0** (não foi alterada).

## Pedido
Na próxima geração do instalador (`instalador\build.ps1`), incluir estas mudanças junto com as da integração Medcloud.
Os arquivos já estão no lugar certo nesta pasta; o `build.ps1` copia `app\` inteiro, então basta gerar o Setup a partir do estado atual.
**Antes de gerar:** confira se `instalador\build\comum\app\` não está com cópia antiga (ela foi gerada às 16:13, antes da junção da NucleAI) e rode os testes da seção "Como conferir".
Não é preciso dependência nova: tudo usa só a biblioteca padrão do Python, mais flask, openpyxl e xlrd, que já estão no `requirements.txt`.

## O que mudou
1. **Provedor OpenRouter** (`app/llm.py`). Substitui a API do Gemini. A gerência digita a chave na tela "NucleAI: IA online". Ela é gravada em `<pasta de dados>\nucleai\openrouter_chave.txt` e nunca é exibida (sem arquivo, vale a variável `NUCLELESTE_OPENROUTER_CHAVE`). Há uma lista ordenada de modelos (`config.nucleai_llm_modelos`). Se um modelo estoura a cota (429/402), dá erro de servidor ou passa de 12 s, a IA troca para o próximo. Quem estourou a cota fica 15 min em pausa.
2. **Log de trocas** (`app/nucleai_trocas.py`). Gravado em `<pasta de dados>\nucleai\trocas.jsonl`. Tela da gerência para marcar cada troca como Natural ou Estranha. **O backup (`backup_pacote.py`) passou a incluir `nucleai_trocas.jsonl`** como terceiro arquivo do zip e a restaurá-lo; backups antigos continuam válidos.
3. **Ferramenta Ilustrar** (`app/nucleai_ilustrar.py`, tabela `nucleai_ilustracoes`). Planilha ordenável com download em Excel, gráfico SVG, cartões de informação, decisão Sim/Não e permissão. Só o bot publica esses blocos.
4. **Agenda pela IA** (`nucleai_ferramentas.py`). Consulta e remarcação com confirmação, propondo o horário mais próximo (tolerância de 60 min, configurável). A permissão é conferida pela tela do usuário. A auditoria registra o próprio usuário com a marca "Feito com auxílio da NucleAI" (nova coluna `auditoria.usuario_id`), e a gerência pode desfazer em Registros de atividades.
5. **Leitura de arquivos** (`app/nucleai_arquivos.py`). Aceita xlsx, xls, csv e txt de até 5 MB e monta relatórios agrupados. PDF é recusado, porque exigiria pacote novo.
6. **Fake Chat** com usuários `Teste#XXXX` e memória compartilhada com seções fixas (Quem sou, Ferramentas, Como agir, Preferências), enviada a qualquer modelo.
7. **Saúde da NucleAI** (liga e desliga para os usuários) e **gráficos de tokens** (`app/nucleai_tokens.py`, tabela `nucleai_tokens`, tela `nucleaiia.tokens`, nova entrada no menu "Gasto de tokens (NucleAI)").
8. Ajuda acrescentada para "Financeiro › Consulta rápida" e para as telas novas. Registro em `app/novidades.py` (versão 1.6.0).

## Arquivos
- **Novos:** `app/nucleai_arquivos.py`, `app/nucleai_ilustrar.py`, `app/nucleai_tokens.py`, `app/nucleai_trocas.py`, `app/templates/nucleai_tokens.html` e os testes `tests/test_nucleai_{agenda_ia,arquivos,ilustrar,memoria_manual,openrouter,tokens,trocas}.py`.
- **Alterados:** `app/llm.py`, `app/nucleai_{conhecimento,ferramentas,ia,memoria,motor}.py`, `app/ajuda.py`, `app/ajuda_conteudo_b.py`, `app/ajuda_conteudo_c.py`, `app/backup_pacote.py`, `app/chat.py`, `app/views_chat.py`, `app/views_nucleai_ia.py`, `app/views_registros.py`, os templates `chat.html`, `nucleai_ia.html` e `registros.html`, `static/css/{chat,nucleai_ia}.css`, `static/js/{chat,nucleai_cartoes,nucleai_treino}.js`, `docs/MODULOS.md` e os testes `test_llm`, `test_nucleai`, `test_nucleai_ia`, `test_nucleai_motor` e `test_menu`.
- **Juntados à mão com o trabalho do Medcloud** (os trechos do Medcloud foram mantidos): `app/db.py` (tabelas `nucleai_tokens` e `nucleai_ilustracoes`, colunas novas em `auditoria` e `nucleai_llm_log`), `app/modulos.py` (menu e permissões de `nucleaiia.tokens` e `chat.ilustracao_excel`), `app/novidades.py`, `docs/ALTERACOES.md`, `tests/test_menu.py` e `tests/test_nucleai.py` (contagem de telas: 101 = Medcloud + Gasto de tokens).
- **Não mexidos pela NucleAI:** `app/__init__.py`, `views_atendimentos.py`, `impressao.html` e tudo do Medcloud.
- Cópia de segurança dos arquivos deste projeto antes da junção: `C:\Users\elias\OneDrive\Desktop\Sistema\SistemaNucleleste-ia\_logs\original-antes-nucleai\`.

## Como conferir
```powershell
$env:TEMP="<pasta gravável>"; $env:TMP=$env:TEMP
python -m unittest tests.test_nucleai tests.test_llm tests.test_nucleai_ia tests.test_nucleai_motor tests.test_nucleai_openrouter tests.test_nucleai_trocas tests.test_nucleai_ilustrar tests.test_nucleai_agenda_ia tests.test_nucleai_arquivos tests.test_nucleai_memoria_manual tests.test_nucleai_tokens tests.test_menu tests.test_medcloud
```
Resultado na cópia de trabalho, antes da junção: **462 testes, OK**.
Resultado aqui, depois da junção (28 módulos: os acima mais agenda, chat, backup, ajuda, registro, modulos e atendimento): **496 testes, 1 falha**.
A falha é `test_nucleai.test_todo_o_menu_tem_ajuda`: "tela sem ajuda: Configuração › Medcloud (portal do paciente)".
Ela vem da integração Medcloud: a tela nova do menu ainda não tem texto de ajuda em `app/ajuda_conteudo*.py`. **Acrescentar essa ajuda antes de gerar o instalador** e rodar o teste de novo.

## Não verificado
- As telas no navegador e no tema escuro (Ilustrar, trocas, Saúde, tokens, Fake Chat).
- Uma chamada real ao OpenRouter (precisa da chave).
- O Setup instalado: o instalador ainda não foi gerado com estas mudanças.
- Instalação real em `C:\ProgramData\Nucleleste`: **não tocada**.
