# Regras de negócio

Estado: **bloco 1 (acesso, permissões, auditoria, desfazer)**. Regras clínicas, de agenda e financeiras serão acrescentadas nos blocos 2–8.

## 1. Autenticação [FATO] (`app/auth.py`, `app/__init__.py`)
- Login em `POST /login`: o nome digitado é convertido para MAIÚSCULAS e comparado em `usuarios.usuario`. Mensagens distintas para usuário inexistente, desativado e senha incorreta. Só "senha incorreta" é registrada em `acessos`; login bem-sucedido grava "Logado" com o user-agent.
- Não há contador de tentativas nem bloqueio temporário no código de `auth.py` (verificado por leitura; reconfirmar na Fase 5).
- Senhas: hash do Werkzeug (`generate_password_hash`). Troca em `/minha-senha`: exige a atual, mínimo **3 caracteres**, confirmação igual; zera `trocar_senha`.
- Redirecionamento pós-login só aceita caminho local (`/…` e não `//…`).
- Sessão: cookie do Flask, `SameSite=Lax`, não permanente (fechar o navegador encerra), `PERMANENT_SESSION_LIFETIME` 12 h declarado, mas sem limite por inatividade (comentário em `create_app`). `session['ultima']` é gravado no login; seu uso será verificado (`static/js/sessao.js`, `presenca.py`).
- Primeiro acesso: se `usuarios` está vazia cria `ADMIN`/`admin`. O instalador e a CLI definem a senha do ADMIN (`cli.py admin-senha`, bloco 9).
- Senha provisória (`usuarios.trocar_senha=1`, usada nos acessos criados para funcionários, senha padrão `123` em `bh/portal.py`): todo endpoint exceto `static`, `auth.*` e `atu.*` redireciona para `/minha-senha`; menu e abas ficam vazios.
- Usuários lembrados (1.5.8): só depois de um login bem-sucedido o servidor grava o cookie `nuc_usuarios` (até 8 logins, o mais recente primeiro, 365 dias, `HttpOnly`, `SameSite=Lax`); nunca guarda senha nem nome digitado errado. A tela de login mostra só os nomes do cookie que ainda são usuários ativos, preenche o primeiro e sugere os outros (`datalist`).
- CSRF: token de sessão `session['csrf']`, exigido em todo POST (campo `_csrf` ou cabeçalho `X-CSRF-Token`). Exceções: `atu.iniciar` (instalador, sem sessão) e `pesq.publica` (pesquisa pública).

## 2. Permissões por módulo [FATO] (`app/modulos.py`)
- Existem **37 módulos** (`MODULOS`). Administrador (`usuarios.admin=1`) recebe todos. Usuário comum: JSON em `usuarios.modulos` ∩ módulos válidos; JSON inválido → nenhum módulo; **NULL → `LEGADO`** (todos exceto: exames, exames_lanc, faturamento, faturamento_dash, registros, acessos, backup, configuracoes, agenda_relatorios, agenda_financeiro, agenda_faltas, resgate_relatorio, arquivo_documentos, gerencia, agenda_leitura, e qualquer `bh_*` ou `blind_*`).
- `bh_gestao` implica `bh_consulta`.
- Perfis prontos (`PRESETS`): recepcao, agenda, estagiario (atendimentos + agenda_leitura), financeiro, documentos_gerencia, tecnologo, banco_horas, blindagens, tudo, nenhum. São só atalhos de marcação na tela de usuários; o que vale é a lista gravada.
- Endpoint → módulo (`modulo_do_endpoint`): decisão por prefixo do nome do endpoint. Regras notáveis:
  - `ajuda.comandos`, `laudo.prazo/limpar/entregues/retificar`, `admin.mensagens_whats`, `admin.backup_restaurar*`, `admin.backup_pasta*`, `saude.*` → módulo `gerencia`.
  - `nucleai.*`, `admin.usuario*`, `lanc.importar` → só administrador (`'__admin__'`).
  - `agenda.pagina/dia/mes/imprimir` → `agenda` **ou** `agenda_leitura`; demais `agenda.*` → `agenda`; `agenda.financeiro*`, `agenda.faltas*`, `agenda.resgates*`, `agenda.relatorio*` têm módulo próprio.
  - `bh.*` → `bh_portal`, `bh_dp`, `bh_gestao` (lista `BH_GESTAO`), `bh_mensagens/bh_portal` ou `bh_consulta`.
  - `atu.avisar` → `backup` ou `gerencia`. `admin.backup*` → `backup` ou `gerencia`.
  - Sem regra (`None`) = livre para qualquer usuário logado: login, `inicio.painel`, `inicio.api*`, `ajuda.*` (exceto comandos), `fav.*`, `nov.*`, `pesq.*`, `atu.pendente/estado/iniciar`, e **qualquer endpoint que não case com nenhum prefixo** (a função termina com `return None`). Implicação a verificar: endpoints novos sem prefixo conhecido ficam abertos (`chat.*` não casa com nenhuma regra e, portanto, é livre para qualquer logado; se isso é intencional é [?], ver bloco 6).
- O cumprimento é feito em `before_request` (não por decorador): bloqueio com mensagem "Você não tem acesso a este módulo." e retorno ao painel.
- Painéis do Início (1.5.8): `config.dashboard_paineis_ocultos` (lista JSON) esconde painéis do dashboard para usuários comuns, que também não recebem os dados deles; administrador e módulo `gerencia` sempre veem tudo. A escolha é global, em `dash.paineis` (módulo `gerencia`).
- Funcionário (`bh_funcionario_id` preenchido, não admin, com `bh_portal`) acessando `inicio.*` é enviado a `bh.portal_home`.

## 3. Auditoria [FATO] (`app/auditoria.py`)
- `after_request` grava em `auditoria` **somente POSTs de usuário logado** que terminaram com redirecionamento 301/302/303, ou 200 quando o endpoint está em `RESPONDE_200` (impressões e ações JSON da agenda). Não grava login/logout nem ação cuja resposta acrescentou mensagem flash de categoria `erro`.
- Texto da ação vem de `ACOES[endpoint]`; endpoints ausentes viram "Ação em <endpoint>". `agenda.campo` (edição de célula) propositalmente não é registrado.
- Detalhe: campos selecionados do formulário (`CAMPOS_RESUMO`, máx. 60 caracteres cada, nunca campos com "senha" no nome), parâmetros da rota e destino do redirecionamento, truncado em 400.
- Falhas na gravação são engolidas (`except Exception: pass`): a auditoria nunca derruba a resposta.

## 4. Desfazer geral [FATO] (`app/desfazer.py`)
- Em todo POST (exceto prefixos `auth. chat. ajuda. atu. fav. nucleai. nov. agenda.campo pesq. lanc.importar bh.importacao admin.backup`), `get_db` instala gatilhos **TEMP** em cada tabela elegível que registram antes/depois de cada linha na tabela temporária `_mud`.
- Elegível: tabela com PK única inteira chamada `id`, sem coluna BLOB, ≤ 60 colunas, fora de `auditoria, acessos, usuarios, config` e dos prefixos `chat_ ajuda_ nucleai sqlite_ anexos _`.
- Ao fim, `coletar` transforma as mudanças em JSON gravado em `auditoria.desfazer`. Limites: > 400 linhas alteradas ou > 600 000 bytes → a ação fica sem botão. O botão só funciona se as linhas ainda estiverem como a ação as deixou (verificação em `views_registros`, bloco 8).
- Ações da agenda montam o próprio desfazer (`g.desfazer`).
- Falha ao instalar gatilhos apenas deixa a ação sem desfazer.

## 5. Convenções transversais [FATO]
- Convênios que vão para o caixa em vez de gerar guia: constante `db.CONVENIOS_CAIXA = ('PARTICULAR','SMS','MAIS MED')` (e coluna `convenios.gera_caixa`; relação entre as duas a esclarecer no bloco 2).
- Backup automático (1.5.8, `backup_pacote.backup_automatico`): todos os dias, dentro da janela `backup_auto_inicio`–`backup_auto_fim` (padrão 08:00–18:00, limites inclusos), um backup por janela fixa de `backup_auto_minutos` (15, 30, 60, 120, 180 ou 240; padrão 30) contada a partir do início. A reserva da janela fica em `backup_auto_ultimo_em` (servidor e bandeja disputam; só um faz). Cada novo automático apaga o automático anterior do mesmo dia (`backup_auto_arquivo`), então fica um arquivo por dia com o horário no nome; manuais nunca são apagados. O laço de `avisos` acorda a cada 60 s para o backup.
- Pastas externas do backup (1.5.8): até 5 em `backup_pastas_destino` (a antiga `backup_pasta_destino` é migrada uma vez), cada uma com estado próprio em `backup_pastas_estado`. A cópia é independente por pasta; os automáticos substituídos (`backup_auto_substituidos`, até 200) são apagados em cada pasta e só saem da lista quando todas as pastas estavam acessíveis e nenhuma tem mais o arquivo.
- Erro 500 é gravado em `auditoria` (módulo "Sistema", ação "Erro interno") e aparece na Saúde do sistema.

---
## Bloco 2 — Núcleo clínico

## 6. Clientes [FATO] (`views_cadastros._validar_cliente`, `util.py`)
- Obrigatórios: nome, data de nascimento válida, sexo M/F, CPF. Contato é opcional, mas se informado precisa ter 10 ou 11 dígitos (aceita prefixo 55 com 13 dígitos).
- CPF: 11 dígitos, não todos iguais, dois dígitos verificadores (`util.cpf_valido`). Duplicidade de CPF é barrada entre clientes (mensagem com nome e código). **Exceção:** na edição, se o CPF não mudou, um CPF inválido é aceito (`atual['cpf'] == f['cpf']`).
- Não há unicidade por nome. Cliente com atendimento ou dose no histórico (`cliente_id`) não pode ser excluído; os atendimentos antigos também são associados por CPF na tela de edição e ao decidir "exame anterior".
- Histórico do paciente (1.5.8, `cad.cliente_historico`): lista os `atendimentos` do cliente (por `cliente_id` e, sem cliente, pelo mesmo CPF), com data, exame e médico solicitante, filtro de período e PDF.
- Telefone vira `(XX)9XXXX-XXXX` (11 dígitos) ou `(XX)XXXX-XXXX` (10). Textos sem número são mantidos.
- `util.para_valor`: se há vírgula, o ponto é milhar e a vírgula é decimal; **sem vírgula, o ponto é decimal** ("1.234" vira 1,234). A tela de convênios compensa com regex de milhar; telas que usam `para_valor` direto não têm essa proteção (verificar em financeiro/caixa).

## 7. Atendimento [FATO] (`views_atendimentos.novo`)
- Validações: cliente existente; exame e médico informados (maiúsculas); data válida; **medicamentos em uso obrigatórios** quando `exames.pede_medicamentos=1` (nos exames padrão, só MIBI); se o cliente tem atendimento anterior (por `cliente_id` ou CPF), é obrigatório informar o último exame (`NÃO INFORMADO` vira vazio); se o exame tem questionário e não está em modo manual, todas as perguntas precisam de SIM/NÃO.
- Convênio: o informado (maiúsculas) ou, se vazio, o do cliente.
- Persistência: grava `atendimentos` com `previsao_laudo` = `prazo_laudo.previsao(data)`; cadastra o médico se não existir; **se `convenios.gera_caixa=1` cria linha em `caixa` (ABERTO); senão cria linha em `guias`**. Convênio sem linha em `convenios` cai em guia. A constante `db.CONVENIOS_CAIXA` não é usada em nenhum ponto (busca em `app/*.py`).
- Respostas: guarda `r<i>` SIM/NÃO e `o<i>` somente quando a resposta é SIM; modo manual guarda apenas `{"manual":1}`.
- Exclusão (só administrador) apaga guia, caixa e atendimento; não mexe em `realizacoes` ligadas (`atendimento_id`) nem em `doses`.

## 8. Fichas impressas [FATO]
- Cada exame define fichas e cópias (na URL, 1 a 10; valor inválido = 1). Sem configuração ou lista vazia: `DOCUMENTOS_OUTROS` (ficha geral, SAE geral, etiqueta do cliente). Itens que deixaram de existir (`valido`) são descartados em silêncio.
- Padrões de fábrica (`db.EXAMES_PADRAO`): MIBI = ficha MIBI + PNT MIBI + termo + declaração Dr. Haroldo + SAE MIBI + 2× escore NEWS; PULMONAR inclui 2× escore NEWS; LINFONODO inclui etiqueta do cliente e questionário `linfonodo`. A intenção clínica de cada documento é [?].

## 9. Doses [FATO] (`views_medicamentos.py`)
Medicamentos aceitos: IODO, GÁLIO, PCI. "SEM PREPARO" é gravado como texto nas colunas de dieta e suspensão. O preparo de 15 ou 30 dias escolhe a ficha de orientação.

## 10. Prazo e previsão do laudo [FATO] (`prazo_laudo.py`)
- Configuração em `config`: `laudo_prazo_tipo` (`horas`|`dias`|`uteis`), `laudo_prazo_valor` (padrão 24 horas corridas; limites 1–720 horas, 1–60 dias), `laudo_prazo_carnaval`, `laudo_prazo_corpus`, `laudo_feriados_extras`. Alterar exige `gerencia` ou admin (`pode_prazo` na tela; a rota `/laudos/prazo` é protegida pelo mapa endpoint→módulo, que a manda para `laudos`, ver pendência 15).
- Feriados: fixos nacionais (1/1, 21/4, 1/5, 7/9, 12/10, 2/11, 15/11, 20/11, 25/12), Sexta-feira Santa, 30/1 (aniversário de Governador Valadares) e 13/6 (Santo Antônio); Carnaval (segunda e terça) e Corpus Christi só se marcados; datas extras `dd/mm` ou `dd/mm/aaaa`.
- Cálculo: **horas** = início + N horas, e se cair em dia não útil vai para 23:59:59 do próximo dia útil; **dias** = data + N dias, ajustada ao próximo dia útil, até 23:59:59; **úteis** = soma N dias úteis. A previsão do atendimento parte das 00:00 do dia do atendimento. Atendimentos anteriores à coluna `previsao_laudo` são recalculados com o prazo vigente ao imprimir. `dia_util` = segunda a sexta e não feriado.

## 11. Mapa de laudos — transições [FATO] (`laudos.mudar`, `pode_mudar`)
- Acesso completo (admin, módulo `gerencia`, ou `laudo_perm` nulo/inválido): qualquer mudança de situação. Restrito (`laudo_perm` = {ver, mover}): só avança **uma** etapa a partir de situação listada em `mover`, e pode "mudar para a mesma situação" (corrigir a data) se enxerga aquela situação. `ENTREGUE` não tem próxima etapa, portanto não entra em `mover`.
- Primeira liberação (`LIBERADO`, ou `ENTREGUE` direto): grava `laudo_liberado_em/por`; o aviso a todos só sai quando a nova situação é `LIBERADO` (entrega direta não avisa).
- Voltar a uma etapa anterior à liberação zera liberação e entrega. Sair de `ENTREGUE` remove o arquivamento; ir de `ENTREGUE` para `LIBERADO` limpa a entrega.
- Data de liberação informada manualmente: não pode ser futura (tolerância de 1 min) nem anterior ao dia do exame.
- "Limpar" arquiva entregues do período; retificar só vale para laudo `ENTREGUE`, com motivo de até 300 caracteres.
- Mensagens de liberação expiram em 3 dias (`DIAS_MENSAGEM`) e saem por `apagar_expiradas` (quem a chama: bloco 6).

## 12. Blindagens [FATO] (`blindagens.py`)
- Obrigatórios: lote (letras e números, até 30, maiúsculas, **único**), nota fiscal (≤ 20), série (≤ 10), data da nota, CFOP (4 dígitos), validade (não anterior à data da nota).
- Status: `VÁLIDO`, `VENCIDO`, `DEVOLUÇÃO SOLICITADA`, `DEVOLVIDA`. `atualizar_status` converte VÁLIDO→VENCIDO quando `validade < hoje` e VENCIDO→VÁLIDO quando `validade >= hoje` (corrigir a validade restaura). A blindagem é válida **até o próprio dia da validade**. Os status de devolução não mudam sozinhos e travam edição e exclusão (`TRAVADAS`).
- Solicitar devolução: exige ≥ 1 blindagem, todas existentes e **VENCIDAS**; cria a solicitação com o valor unitário vigente (`config.blindagem_valor_unitario`, padrão "405,80") e marca todas como DEVOLUÇÃO SOLICITADA.
- Confirmar devolução: exige data, não futura e não anterior à data da solicitação; só para blindagens em DEVOLUÇÃO SOLICITADA.



---
## §13. Agenda [FATO] (`agenda.py`)
- **Status:** `AGENDADO, VEIO, FALTOU, REMARCOU, RESGATADO (rótulo "Reagendado"), DESISTIU`. Só se muda status de linha com paciente.
- **Resgate:** conta como resgate só quando o status anterior era `FALTOU` e o novo é `RESGATADO` ou `DESISTIU`; grava `resgatado_por/em`. O relatório de resgates conta por usuário.
- **Limites:** 200 horários por agenda na criação; 600 linhas por agenda; 1 a 10 pacientes por horário; até 26 repetições semanais; intervalo de 1 a 240 minutos; lembrete (observação) de até 200 caracteres; campos da célula com limites (paciente 120, convênio 60, contato 80, senha 40, observação 300).
- **Horário:** aceita `8:30`, `08h30`, `0830`, `8.30`; não passa da meia-noite (`gerar_horas`). Se informar término e não a quantidade, calcula `(fim - início) // intervalo`.
- **Bloqueio de dia:** só se o dia ainda não tem agenda; dia bloqueado não aceita criar nem copiar para ele. Ao repetir semanalmente, dias bloqueados são pulados e listados.
- **MIBI:** no exame cujo nome contém `MIBI` ou `MIOCARD`, a "senha" vira escolha `Estresse|Repouso|Protocolo`. Protocolo pinta a linha de verde enquanto agendado (comentário em `agenda.py`).
- **Contato:** vários contatos separados por `/` ou `;` viram `a / b`; sem número, o texto é mantido; WhatsApp usa só o primeiro número válido e remove `55` quando tem 13 dígitos.
- **Convênio da linha:** deve existir em `convenios` ativo (sem diferenciar maiúsculas); senão erro. Digitar o convênio da reserva marca a linha como reservada; digitar outro convênio num horário reservado vazio é bloqueado (mande "Liberar reserva"); em linha com paciente, corrige e libera a reserva.
- **Duplicidade ao salvar:** `_duplicado` só **avisa** (mesmo nome, mesmo dia e exame); não impede.
- **Remarcar × Copiar:** remarcar move o paciente (origem vira `REMARCOU` ou `RESGATADO`, com texto do novo horário); copiar mantém a origem (para ida e retorno). Destino ocupado é recusado; destino reservado exige o mesmo convênio.
- **Status da linha remarcada:** fica travado; só administrador e gerência podem alterá-lo (o novo status limpa o `remarcado_para`, sem mexer na nova marcação). Remarcar de novo a mesma linha continua proibido para todos.
- **Retorno no relatório da agenda:** o status `RETORNO` conta também em `VEIO` e na taxa de falta (tela, PDF, Excel e ONA, que usam `agenda.relatorio`). Desde a 1.5.8 o financeiro também conta o `RETORNO` (ver Financeiro abaixo). Quem foi remarcado e veio na nova marcação conta uma vez só: a presença fica na nova data, e a origem segue só em Retornos (ligação pelo texto de `remarcado_para` e pelo nome do paciente; outra etapa do MIBI não entra nessa regra).
- **Copiar dia:** pula agendas que já existem no destino (mesmo exame e início); com pacientes, não copia quem está `REMARCOU`; reservas livres seguem para o destino.
- **Exclusão de agenda:** só administrador ou gerência; pede confirmação se houver paciente.
- **Resumo do dia (balões):** mostra só chegaram, atendidos (`VEIO` + `RETORNO` da própria grade), faltaram e reagendados, mais os livres; retorno e desistiu não têm balão próprio (1.5.8).
- **Reagendamento no histórico:** a linha não mostra mais "resgatou: X"; o histórico da linha registra a ação `Reagendado por <login>` (em `remarcar` com origem `RESGATADO` e em `definir_status` quando é resgate para `RESGATADO`). `resgatado_por/em` continuam gravados para o relatório de resgates (1.5.8).
- **Financeiro (repasse):** conta quem tem status `VEIO` ou `RETORNO` (1.5.8); o `RETORNO` remarcado cujo paciente veio na nova data é descartado (`_marcar_veio_na_nova_data`), para não cobrar duas vezes; a coluna Nº é renumerada de 1 a N no fim, depois de filtros, união do MIBI e descartes; valor = `convenio_valores` do convênio e do tipo de exame (fallback nas colunas antigas `valor_mibi` etc.); repasse = valor × pct/100 com 2 casas; pct de 0 a 100. Quem não tem valor aparece como `sem_valor`. O filtro por dias da semana (ex.: só terças e sextas) vale para tela, PDF e Excel; as caixinhas Repouso/Estresse/Protocolo marcam as etapas dos exames MIBI, e o PDF cabe em uma única folha A4.
- **Associação nome do exame → tipo cadastrado** (`exame_do_nome`): nome igual → sinônimos (PARATGI/PARATIR, MIBI/MIOCARD, OSSEA, GALIO, TGI) → maior nome cadastrado como palavra inteira.
- **Taxas:** `taxa_falta = FALTOU / (VEIO + FALTOU)`; vazio se a base for zero.
- **Permissão:** sem o módulo `agenda`, a tela abre em modo somente leitura (`somente_leitura` em `views_agenda.pagina`); as rotas POST usam só `login_obrigatorio` e dependem do mapa `modulo_do_endpoint` (ver pendência 8).


---
## §14. Dinheiro [FATO]
**Movimento de caixa** (`movimento.py`)
- Um usuário com caixa aberto de **outra data** não pode abrir o de hoje nem receber; precisa fechar o antigo (e recebe aviso). Caixa de hoje já aberto e fechado só reabre pela gerência/administração (`reabrir`), que avisa o dono.
- Receber: forma DINHEIRO ou PIX; nota fiscal obrigatória; valor > 0; em dinheiro, valor entregue ≥ valor, troco = entregue − valor. PIX não tem troco.
- **Só quem lançou o atendimento recebe** o valor (`pode_receber`; lançamento antigo sem dono qualquer um recebe). Administração e gerência veem todos os pendentes, mas só recebem os próprios.
- Editar recebimento: caixa aberto → o próprio dono ou privilegiado; caixa **fechado** → só privilegiado. Excluir lançamento (individual ou em lote) → só privilegiado, sem desfazer, com registro na auditoria.
- Privilegiado = administrador ou módulo `gerencia`.

**Caixa diário** (`caixa_diario.py`)
- Descrição em maiúsculas (até 200), valor > 0 com 2 casas, NF até 40, obs até 300. Lançar antes da data-base é recusado. Alterar um lançamento antigo muda os saldos dos dias seguintes (recálculo, nada é gravado como saldo).
- Não há nenhuma regra que impeça excluir ou editar lançamentos antigos; qualquer usuário com o módulo `caixa_diario` pode.

**Contas a pagar** (`views_financeiro.py`)
- Obrigatórios: descrição, categoria, valor, vencimento. Descrição em maiúsculas.
- `conta_reabrir` limpa banco e data de pagamento, mas **mantém** forma de pagamento e quem quitou (observação).
- `conta_excluir` e `conta_quitar` não pedem confirmação no servidor; a proteção é só a tela.

**Faturamento** (`views_faturamento.py`)
- Valor bruto > 0; tributos entre 0 e o bruto; referência e previsão devem ser datas válidas; convênio obrigatório (texto livre em maiúsculas, não precisa existir em `convenios`).
- Reabrir fatura limpa data, valor e banco do recebimento. Excluir não pede confirmação no servidor.
- Atrasadas = em aberto com previsão anterior a hoje.

**Relatórios de atendimentos** (`views_financeiro.relatorios`): agrupa `atendimentos` por exame, convênio, médico, usuário, dia ou mês; cruzamento exame × convênio; totais de `caixa` por status e `guias` por convênio no período.


---
## §15. Banco de Horas [FATO] (`bh/core.py`, `bh/portal.py`, `bh/planning.py`, `bh/documents.py`, `bh/messages.py`)

**Cadastro**
- Número I: obrigatório, até 64 caracteres, `[\w.-]+`, zeros à esquerda removidos quando só há dígitos; **único e imutável** (para mudar, cadastrar outro vínculo).
- Nome até 200. Admissão obrigatória; desligamento não anterior à admissão; data do saldo inicial dentro do vínculo; saldo inicial entre ±100.000.000 minutos.
- Estagiário: só aparece na escala; saldo inicial deve ser 0; sem correções, ajustes, relatório nem acesso. O tipo de vínculo **não muda** depois de haver ajuste ou relatório emitido.
- Alterar cadastro exige motivo (até 2000 caracteres). Mudança que deixaria correções, ajustes ou jornadas fora do vínculo é recusada.

**Jornada (`save_schedule`)**: vigência dentro do vínculo; minutos de cada dia da semana (0 a 1440); intervalo mínimo e descontado (0 a 1439); política para **duas batidas**: `review` (padrão, exige conferência), `continuous` (sem desconto) ou `deduct` (descontar intervalo fixo, que deve ser ≥ mínimo e > 0). A jornada vigente de um dia é a mais recente com vigência até aquele dia. (Na tela, `views_bh.funcionario_jornada` usa o **mesmo** valor de intervalo para mínimo e descontado.)

**Importação (`import_xls`)**: só `.XLS` (via `xlrd`), até 20 MB; mesmo arquivo (SHA-256) não é importado de novo; planilha precisa ter aba "Registro de Presença" com "Número I", "Nome" e dias em colunas; período até 62 dias. Cada célula de batidas aceita horários separados por espaço, vírgula ou ponto e vírgula; ordem errada ou repetida vira *erro de leitura* que exige revisão. Nome na planilha diferente do cadastro gera aviso, mas a associação vale pelo ID. Números I sem cadastro ficam listados como pendentes.

**Cálculo do dia (`_calculate_day`)** — ordem de decisão:
1. Fora do vínculo → `not_employed`. Antes do saldo inicial → sem cálculo.
2. Sem jornada vigente → pendente.
3. Folga ou feriado → esperado = 0.
4. Importações divergentes (`conflict`) não corrigidas depois → pendente.
5. Erro de leitura → revisão.
6. `falta` → saldo do dia = −esperado. `abono` → crédito = esperado, saldo 0.
7. Sem batidas e com jornada esperada → "classificar o dia" (pendente). Sem batidas e sem jornada → neutro.
8. Com batidas: número ímpar ou ordem errada → revisão; duas batidas seguem a política da jornada; quatro ou mais somam os pares e o intervalo (entre pares) deve atingir o mínimo.
9. Saldo do dia = trabalhado − esperado.

**Dia importado sem batidas** (linha existe na planilha, mas vazia, sem correção): `_day_data` o classifica como **folga automática** ("Folga (sem batidas)"), esperado 0. Dia **não importado** e sem correção com jornada esperada fica pendente. (Observação: um dia útil em branco na planilha não gera débito.)

**Saldo mensal (`monthly_report`)**: parte do saldo inicial na data de âncora, soma o resultado de todos os dias anteriores ao mês e os ajustes, e depois o movimento do mês. `complete` só é verdadeiro sem pendências no mês e nos anteriores e com o mês a partir do saldo inicial.

**Relatório para assinatura**: só emite se `complete`. Guarda uma foto (JSON + hash SHA-256). Se o conteúdo é idêntico ao da última versão, devolve o mesmo PDF; senão, nova versão (v1, v2...).

**Correção de dia**: batidas `HH:MM` estritas e crescentes (até 48), classificação em `normal|falta|abono|folga|feriado`; falta e abono integral não têm batidas; justificativa obrigatória; **a correção mais recente do dia prevalece** (não apaga as anteriores).

**Ajuste de saldo**: inteiro de minutos diferente de zero (±10.000.000), dentro do vínculo e a partir da data do saldo inicial; justificativa obrigatória.

**Escala (`planning.py`)**: padrão = segunda a sexta "trabalho" começando às 08:00, fim = 08:00 + jornada + intervalo; sábado e domingo "folga". Jornada ≤ 0 ou que passa de 24h → "pendente". Marcações manuais (até 366 dias) sobrepõem o padrão. PDF só sai sem pendências. Não altera ponto nem saldo.

**Mensagens**: cada funcionário tem uma conversa única compartilhada pela equipe com o módulo `bh_mensagens`; funcionário só vê a própria; equipe só envia a quem tem acesso ativo; 2000 caracteres e 10 por minuto por usuário; 200 mensagens por conversa; lidas por lado (`staff_read_id`, `employee_read_id`).

**Documentos (DP)**: 11 categorias; 6 obrigatórias conferidas no painel (identidade, CPF, CTPS, comprovante de residência, contrato, exame admissional). Aceita PDF, PNG, JPEG e WEBP, **detectados pelo conteúdo** (não pela extensão), até 15 MB; mesmo arquivo (SHA-256) ativo para o mesmo funcionário é recusado. Nunca se apaga: arquiva com justificativa e pode restaurar. O funcionário vê só quais tipos existem e os meses de folha de ponto, nunca título, nota nem arquivo. Conteúdo vai para `anexos.db`, com fallback para a coluna `content`.
