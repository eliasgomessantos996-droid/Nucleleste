# Testes e comportamentos comprovados (Fase 5)

## 1. Execução realizada
- **Quando e onde:** 19/10/2026, numa **cópia isolada** do código (pasta temporária da sessão, sem `dados/`, sem a instalação real), com ambiente virtual próprio. Cada teste cria seu **banco temporário** (`tempfile.TemporaryDirectory` + `create_app(<caminho>/t.db)`); nenhum teste lê `C:\ProgramData\Nucleleste`. Um teste de CLI define `NUCLELESTE_DADOS` apenas para uma pasta temporária (`test_anexos_backup.py:236`).
- **Como:** `python -m unittest -v` em **4 grupos paralelos** de módulos (a máquina tem 4 núcleos; o `PROJETO_1.5.0.md` também fala em 4 grupos).
- **Ambiente:** Python 3.14.4; Flask 3.1.3, Werkzeug 3.1.9, Jinja2 3.1.6, Waitress 3.0.2, xlrd 2.0.2, reportlab 5.0.1, openpyxl 3.1.5 (instalados de `requirements.txt` no ambiente virtual da cópia).
- **Resultado [FATO, saída dos 4 grupos]:**

| Grupo | Testes | Resultado | Tempo |
|---|---|---|---|
| 0 | 65 | OK | 117 s |
| 1 | 106 | OK | 170 s |
| 2 | 92 | OK | 130 s |
| 3 | 185 | OK (1 ignorado) | 285 s |
| **Total** | **448** | **0 falhas, 0 erros, 1 ignorado** | ~5 min em paralelo |

- **O teste ignorado** é `test_bh_core.test_uploaded_example_when_available`, que depende de uma planilha de exemplo que "só existe no ambiente de desenvolvimento".
- Observação: uma primeira execução em série, sem paralelismo, ficou muito lenta (106 testes em cerca de 25 minutos) e foi interrompida; o que vale é a execução paralela acima.
- **Limite:** o resultado vale para o código **desta cópia** (que reproduz o diretório do projeto no momento da cópia). Não foi executado contra o banco real, nem sob carga, nem em navegador.

## 2. O que os testes comprovam (mapa por módulo)
Contagem de métodos `test_*` por arquivo (busca no código) e o que cada conjunto cobre pelo nome dos testes:

| Área | Arquivo (nº de testes) | O que comprova |
|---|---|---|
| Agenda | `test_agenda.py` (17), `test_agenda_faltas.py` (7), `test_agenda_financeiro.py` (6), `test_agenda_reservas.py` (6), `test_agenda_cadastro_duplicidade.py` (10) | criação e validação de agendas, repetição semanal, bloqueio, modelos, conflito de edição, remarcar/copiar, MIBI (senha e protocolo), lista de espera, relatórios (tela, PDF, Excel), impressão, permissões e exigência de login; faltas e resgate; repasse; reservas; duplicidade por nome e telefone |
| Atendimento e fichas | `test_cadastro_cliente.py` (3), `test_questionario_pnt.py` (12), `test_prazo_laudo.py` (16), `test_144.py` (14) | cadastro, questionário PNT, previsão do laudo (Páscoa, feriados locais e móveis, dias úteis, 24 h), rascunho de exame a partir do atendimento, consulta de CNPJ |
| Laudos | `test_laudos.py` (5), `test_laudo_permissoes.py` (9), `test_laudos_entregues.py` (7) | mapa, aviso de liberação e expiração em 3 dias, contato do sistema somente leitura, permissões por situação, entregues e retificação |
| Dinheiro | `test_movimento.py` (6), `test_caixa_diario.py` (8), `test_parcelas_datas.py` (5), `test_fichas_plano_movimento.py` (12) | recebimento com troco e PIX, caixa de outra data bloqueia e avisa, fechamento e relatório, lembrete das 17 h, saldos em cadeia do caixa diário, parcelas com datas editáveis |
| Banco de Horas | `test_bh_core.py` (18), `test_bh_telas.py` (9), `test_bh_acesso_estagiario.py` (12) | regras do cálculo (folga automática, dia descoberto pendente, política de duas batidas, conflitos de importação, imutabilidade, transações atômicas), telas e acesso do funcionário e do estagiário |
| Comunicação | `test_chat_blindagens.py` (20), `test_chat_recursos.py` (29), `test_chat_imagens.py` (6), `test_avisos_visibilidade.py` (5), `test_mensagens_whats.py` (14) | conversa e não lidas, citação, busca, digitando, imagens e apagamento em 24 h, visibilidade dos avisos do sistema, textos de WhatsApp |
| Blindagens | dentro de `test_chat_blindagens.py` | cadastro, vencimento, devolução, documentos de transporte |
| NucleAI | `test_nucleai.py` (97), `test_tutorial.py` (11) | árvore de ajuda, busca por texto livre, fluxo de satisfação, chamados à gerência, 37 comandos, permissões e confirmação Sim/Não, tutorial |
| Qualidade | `test_qualidade.py` (18), `test_ona.py` (3), `test_v150_novidades.py` (18), `test_novidades.py` (5) | Pareto, GUT, risco, SWOT, indicadores, fluxograma (limpeza do que vem do navegador), organograma sem ciclos, fornecedores, robô (concentração, GUT, não duplica, aceitar/descartar, rotina diária), telas e exportações, permissões; relatório ONA; registro de versões |
| Operação | `test_anexos_backup.py` (33), `test_backup_restaurar.py` (6), `test_migracoes.py` (5), `test_atualizacao.py` (5), `test_entrega_e_atualizacao.py` (9), `test_saude.py` (9) | anexos em banco próprio, migração com conferência SHA-256, backup `.zip`, restauração (código, lista de outra pasta, falha na segunda parte volta a primeira, só administração/gerência), migrações de dados únicas, aviso de atualização e tela de espera, saúde do sistema |
| Usuários e interface | `test_menu.py` (6), `test_usuarios_arquivo.py` (6), `test_conta_aparencia.py` (5), `test_icones.py` (6), `test_unacon_desfazer_favoritos.py` (20), `test_documentos.py` (10) | ordem do menu e 71 telas, arquivar usuário, tema e brilho, ícones, reserva "UNACON", desfazer, favoritos, documentos |

Total por contagem de métodos: cerca de 520 ocorrências de `def test_` e `class` somadas pela busca; a execução contou **448 testes**.

## 3. O que não tem teste dedicado (por nome de arquivo) [HIPÓTESE: pode estar coberto de forma indireta]
`servidor.py`, `tray.pyw` e o instalador (`instalador/`); os scripts de `ferramentas/` (testados manualmente conforme `PROJETO_1.5.0.md`: carga e queda); o **comportamento do JavaScript no navegador** (testes inspecionam HTML e rotas, não executam o JS); a impressão real das fichas (o teste confere o HTML/PDF gerado, não a saída impressa); a consulta de CNPJ na rede (usa função de download substituída nos testes).

## 4. Comportamentos confirmados na execução manual (cópia local, banco falso)
Ver [INTERFACE.md](INTERFACE.md): cadastro de cliente, lançamento de atendimento MIBI e montagem das fichas funcionaram; o atendimento sem convênio foi para guia; o mapa de laudos permaneceu vazio, como documentado.

## 5. Avisos observados na execução
A suíte emitiu `ResourceWarning` sobre conexões e arquivos não fechados explicitamente (por exemplo, "Implicitly cleaning up HTTPError" no teste de CNPJ). Não causam falha; indicam recursos liberados só pelo coletor de lixo.

