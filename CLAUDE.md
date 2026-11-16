# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Sistema web de recepção e gestão de uma clínica de medicina nuclear (Nucleleste). Flask + Waitress + SQLite, um servidor em um PC da clínica; os outros PCs usam o navegador (porta 8080). Idioma do código, templates e mensagens: português. Versão em `VERSION`; plano e estado da versão em andamento em `PROJETO_1.5.0.md`. A pasta `docs/` (começando por `docs/INDICE.md`) tem documentação técnica detalhada; consulte-a antes de reler código de um módulo.

## Regras fixas do projeto
- **Não mexer na instalação real** (`C:\ProgramData\Nucleleste`) nem rodar instalador sem aprovação. Ela já está em uso; o servidor roda como conta SYSTEM, que não enxerga Drive nem unidades do usuário.
- `dados/` desta pasta contém dados reais locais (banco, `chave_secreta.txt`, backups): não abrir, alterar nem copiar para testes.
- Não é repositório Git. Sem commit/push (nem existe repositório).
- Telas novas: ícones do sprite e desenhos SVG animados, sem emoji; conferir no tema escuro.
- Cada item novo é registrado no log de atualizações (`app/novidades.py`).

## Comandos
Há um venv fora do projeto em `%LOCALAPPDATA%\SistemaNucleleste\venv` (criado por `INICIAR.bat`). Dependências: `requirements.txt` (flask, waitress, xlrd, reportlab, openpyxl).

```powershell
python servidor.py --dev                  # desenvolvimento (Flask, 127.0.0.1, recarrega)
python servidor.py                        # produção (Waitress, 48 threads)
python -m app.cli backup                  # também: admin-senha, importar-db, config, importar-exames, importar-bh
python -m unittest tests.test_agenda -v   # um módulo de teste
python -m unittest tests.test_agenda.NomeDaClasse.test_nome -v   # um teste
```

Os testes são `unittest` (pytest também roda). Cada teste cria banco temporário via `create_app(<tmp>/t.db)`, sem tocar em `dados/`. A suíte completa (~520 testes) é lenta em série (mais de 13 min); a documentação a executa em 4 grupos paralelos de módulos. Não há lint configurado.

Para rodar o app sem tocar nos dados reais, aponte `NUCLELESTE_DADOS` para uma pasta vazia e `NUCLELESTE_PORTA` para outra porta (nunca 8080). Em ambientes com sandbox, defina também `TEMP`/`TMP` para uma pasta gravável, senão os testes falham com `PermissionError` em `_chave_secreta`.

`ferramentas/` tem gerador de dados sintéticos e testes de carga/queda (`gerar_carga.py`, `servidor_carga.py`, `carga_http.py`, `teste_queda.py`); nenhuma toca a instalação real.

## Arquitetura
- **Fábrica e ciclo da requisição:** `app/__init__.py` (`create_app`). Registra ~29 blueprints (`app/views_*.py`, um por área). `before_request` faz, em ordem: tela de espera 503 após atualização, carrega usuário da sessão, **CSRF obrigatório em todo POST** (exceções: `atu.iniciar` e `pesq.publica`), calcula módulos, força troca de senha e **bloqueia endpoints sem módulo** do usuário.
- **Permissões:** `app/modulos.py` mapeia endpoint → módulo (37 módulos, perfis em `PRESETS`). Endpoint novo precisa entrar nesse mapa, senão o acesso é bloqueado. `'__admin__'` = só administrador.
- **Configuração:** `config.json` da raiz (`porta`, `pasta_dados`) < variável `NUCLELESTE_DADOS` (substitui a pasta) < `config.json` dentro da pasta de dados (só muda `porta`) < `NUCLELESTE_PORTA`. A chave de sessão é gerada em `chave_secreta.txt` na pasta de dados.
- **Dados:** `app/db.py` define o esquema (~50 tabelas) e migrações por `ALTER TABLE`; `app/migracoes.py` guarda migrações únicas versionadas (`migracoes_aplicadas`). Dois bancos: `sistema.db` e `anexos.db` (conteúdo dos arquivos; `anexos.py`). **Backup e restauração tratam os dois juntos** (`backup_pacote.py`; restauração exige código de verificação e guarda `ANTES-DE-RESTAURAR_*.zip`).
- **Separação lógica/rota/documento:** regra de negócio em `app/<area>.py`, rotas em `views_<area>.py`, PDF/Excel em `*_docs.py` (reportlab/openpyxl). `app/bh/` é o Banco de Horas, incorporado de outro programa. `ajuda*.py` + `nucleai_comandos.py` formam a NucleAI (assistente por regras, sem IA externa).
- **Segundo plano:** com `avisos_automaticos=True` (servidor e bandeja), `avisos.iniciar` dispara um laço periódico (avisos de vencimento, limpeza de imagens do chat com 24 h, rotina do robô de qualidade). Os testes não ligam isso.
- **Entradas:** `servidor.py` (web), `tray.pyw` (ícone na bandeja; `--servidor` é usado pela tarefa agendada do Windows), `app/cli.py`, `instalador/` (Inno Setup; `build.ps1` gera o Setup, precisa do Inno Setup 6).
- **Front-end:** templates Jinja em `app/templates`, JS/CSS puros em `app/static`, sem framework.
