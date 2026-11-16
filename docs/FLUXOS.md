# Fluxos de ponta a ponta

Estado: fluxos 1 a 3 (bloco 2). Cada passo cita o arquivo/símbolo. Não há fluxos hipotéticos aqui.

## 1. Lançar um atendimento na recepção [FATO]
Entrada: `GET/POST /atendimentos/novo` (`views_atendimentos.novo`, módulo `atendimentos`).
1. `before_request` (login, CSRF, módulo `atendimentos`) → ver ARQUITETURA §5.
2. GET: carrega exames ativos, convênios ativos e médicos; monta `exames_json` (questionário e "pede medicamentos" por exame) para o JavaScript do formulário; `?cliente=<id>` pré-seleciona o cliente.
3. POST: normaliza campos, lê o cliente e o exame, consulta se existe atendimento anterior (cliente_id ou CPF), lê as respostas do questionário (`_respostas_do_form`).
4. Valida (REGRAS §7). Havendo erro, reapresenta o formulário com mensagens flash.
5. Sem erro: calcula `previsao_laudo` (`prazo_laudo.previsao`), insere em `atendimentos`, cadastra o médico se for novo e insere **uma** linha em `caixa` (convênio com `gera_caixa=1`) **ou** em `guias`. `db.commit()`.
6. Resposta: flash informando o destino (caixa ou protocolo de guias) e a previsão do laudo; redireciona para `/atendimentos/<id>/imprimir?novo=1`.
7. Impressão: `fichas.documentos_do_exame` define as fichas; `fichas.dados_atendimento` preenche os campos; `impressao.html` renderiza (cópias por ficha na URL `?d=slug:cópias`). Fichas personalizadas passam por `renderizar_texto`.
8. `after_request`: registra "Lançou atendimento" na `auditoria` com o desfazer geral (linhas de `atendimentos`, `caixa` ou `guias`, `medicos`).
Efeitos colaterais: pode criar médico; não cria `realizacoes` (isso é outro passo manual, fluxo 2).

## 2. Do atendimento ao exame realizado e ao laudo entregue [FATO]
1. **Lançar exame realizado**: `/exames-realizados/novo?atendimento=<id>` ou aba "do dia" (`views_exames.do_dia`). Copia data, cliente, nascimento, convênio, médico e exame do atendimento como rascunho (`_rascunho_do_atendimento`); o técnico completa rádio, fármaco, lote, atividades, horas. Insere em `realizacoes` com `laudo_situacao='PROCESSANDO'` e `atendimento_id` (se informado e livre).
   - Atalho em lote: `/exames-realizados/atendimentos-do-dia` cria linhas em branco **sem** `laudo_situacao` (ficam fora do mapa).
2. **Mapa de laudos** (`/laudos`): usuário com permissão move o cartão com `POST /laudos/<id>/situacao` → `laudos.mudar`. Em `LIBERADO` (primeira liberação) cria uma mensagem de chat em nome de `LAUDOS DO SISTEMA` para cada usuário ativo (não interno), com `expira_em` = agora + 3 dias e `laudo_id`.
3. **Entrega**: a mensagem tem um botão que chama `POST /laudos/<id>/entregar` → `laudos.entregar` → `mudar(..., 'ENTREGUE')`; redireciona ao mapa destacando o laudo.
4. **Limpeza**: `POST /laudos/limpar` arquiva entregues; ficam em `/laudos/entregues`, onde podem ser retificados.
5. **Rotina de fundo**: `avisos.iniciar` (laço a cada 600 s) chama `laudos.apagar_expiradas` e apaga as mensagens vencidas (exceto as com imagem, tratadas por `chat.apagar_imagens_expiradas`).
Dependências entre passos: não há vínculo obrigatório entre atendimento e exame realizado (o vínculo `atendimento_id` é opcional); a coerência depende da recepção/técnico.

## 3. Ciclo de vida de uma blindagem [FATO]
1. Cadastro (`blind.novo`): validação (REGRAS §12) → `blindagens` com status `VÁLIDO` → `atualizar_status`.
2. Qualquer abertura de tela do módulo chama `atualizar_status` (não há rotina de fundo para isso): vira `VENCIDO` quando `validade < hoje`.
3. Solicitação (`blind.devolucao`): marca blindagens vencidas como `DEVOLUÇÃO SOLICITADA`, grava `blindagem_devolucoes` (valor unitário vigente) e libera planilha PDF/XLSX e documentos de transporte (`blindagem_docs`), por `did`.
4. Confirmação (`blind.devolvidas`): informa a data de devolução e muda para `DEVOLVIDA` (`devolvida_em/por`).
Estados e transições não saem desse circuito automático: o único retorno automático é `VENCIDO → VÁLIDO` ao corrigir a validade.


---
## 4. Agenda: marcação, comparecimento, falta e resgate [FATO]
1. **Criar agenda** (`POST /agenda/criar`): dia, exame, início, intervalo, quantidade ou término, vagas por horário, repetição semanal (até 26), reserva opcional para um convênio. Valida e gera as linhas; dia bloqueado recusa; dias bloqueados nas repetições são pulados.
2. **Marcar paciente**: o usuário digita na grade; cada célula salva ao sair (`POST /agenda/horario/<id>/campo` com o valor anterior). Conflito → 409 e a tela mostra o valor atual. Se duplicar nome no dia, só **avisa**; depois do salvamento, `avisar_duplicados` manda pergunta Sim/Não à equipe da agenda.
3. **Atualização ao vivo**: a tela consulta `/agenda/dia/<data>` a cada 5 s e só redesenha se nada estiver sendo digitado.
4. **Dia do exame**: mudar o status para `VEIO` (se o paciente não é cliente, a tela oferece cadastrar com os dados da linha). Contam para o repasse médico.
5. **Falta**: status `FALTOU` libera o botão de WhatsApp (abre o aplicativo do computador por `whatsapp://` e, sem resposta em 1,5 s, o WhatsApp Web, com o texto de `mensagens_whats`). O sistema não envia sozinho.
6. **Resgate**: em "Faltas e reagendamento", o usuário marca `Reagendado` (escolhe novo dia/horário; o paciente é copiado e a origem fica `RESGATADO` com `resgatado_por`) ou `Desistiu`. Alimenta o relatório de resgates e o indicador de qualidade.
7. **Lista de espera**: incluir, encaixar em horário livre (respeitando reserva de convênio) ou excluir.
8. **Reserva para convênio**: planilha Excel em branco com o código de cada vaga → convênio preenche → importação confere data/hora/exame e só preenche vaga vazia.
9. **Desfazer**: cada ação grava uma fotografia no registro de atividades; "Desfazer" só funciona se as linhas continuam como a ação as deixou.

## 5. Balcão: do lançamento ao fechamento do caixa [FATO]
1. Atendimento de convênio com `gera_caixa=1` cria linha em `caixa` (`ABERTO`, com `usuario` = quem lançou) (§1).
2. O usuário abre **seu caixa do dia** (`/movimento-caixa/abrir`, fundo de troco). Se tem caixa de outra data aberto, o sistema recusa e avisa.
3. **Receber** (`/receber/<id>`): só quem lançou; forma DINHEIRO ou PIX; nota fiscal obrigatória; em dinheiro, informa o valor entregue e o troco é calculado. Vira `PAGO` ligado à sessão. Dá para imprimir a **quitação**.
4. Corrigir enquanto aberto (próprio usuário); depois de fechado, só gerência/administração. Reabrir caixa: só gerência (avisa o dono).
5. **Fechar** (`/fechar`): gera o relatório PDF para assinatura (dinheiro com troco e PIX separados; esperado em dinheiro = fundo + líquido).
6. **Rotina de fundo** (a cada 10 min): alerta o dono de caixa de dia anterior aberto e, após 17 h, lembra de fechar. A tela "Saúde" marca vermelho caixa antigo aberto.

## 6. Banco de Horas: do relógio ao relatório assinado [FATO]
1. RH cadastra o funcionário (Número I do relógio, vínculo, saldo inicial) e a jornada com vigência; o sistema cria acesso automático (login = 1º nome, senha provisória) para o portal.
2. Mensalmente importa-se o `.XLS` do relógio; mesmo arquivo (SHA-256) não repete; dia já aceito com batidas diferentes vira conflito, preservando o original.
3. O painel mostra saldos e **pendências** (dia sem batida, batidas ímpares, importações divergentes, sem jornada).
4. RH resolve cada pendência por **correção de dia** (batidas ou classificação, com justificativa) ou **ajuste de saldo**.
5. Sem pendências, emite o **relatório PDF** (versão e hash); o funcionário e a gerência assinam e a folha assinada é arquivada no Departamento Pessoal (categoria `folha_ponto`, por mês).
6. O funcionário acompanha o próprio saldo e a situação dos documentos em "Minha área" e conversa com a equipe pelas mensagens do BH.

## 7. Backup e restauração [FATO]
1. **Fazer**: tela de backup, bandeja, CLI ou comando da NucleAI geram `BACKUP_dd-mm-aaaa_HH-MM-SS.zip` com os dois bancos.
2. **Restaurar**: administração/gerência escolhe o arquivo (da pasta de backups ou de outra pasta); o sistema valida o conteúdo, mostra um **código de 6 dígitos** (5 min, uso único), exige digitá-lo, guarda `ANTES-DE-RESTAURAR_...zip`, troca os bancos e roda as migrações de esquema. Falha na segunda parte volta a primeira.
3. Depois, os usuários devem recarregar a página.

## 8. Atualização do sistema [FATO]
1. A gerência (ou o instalador, no PC-base) dispara o **aviso de atualização** (1–60 min; o instalador usa 3 min); todos recebem mensagem e uma faixa de contagem na tela (`atualizacao.js`, consulta `/atualizacao/estado` a cada 4 s).
2. Na hora H o instalador faz backup, encerra o servidor, troca o programa e escreve `atualizando.txt`; o servidor novo exibe **tela de espera** animada por até 60 s.
3. Quando o sistema volta, a página recarrega sozinha e mostra uma única mensagem de boas-vindas da versão.

## 9. Pedido de ajuda à NucleAI e chamado à gerência [FATO]
1. O usuário clica no botão redondo → `POST /ajuda/iniciar` cria a sessão e abre o chat com a NucleAI.
2. Escolhe tema → módulo → área, ou escreve a dúvida; recebe o passo a passo e responde "consegui te ajudar?" (1/2/3) e, opcionalmente, uma nota 1–5.
3. Se não ajudou, pode **chamar a gerência**: a NucleAI avisa os destinatários (`ajuda_chamados`, 7 dias) com botão "Falar com o usuário".
4. A gerência abre a conversa; a NucleAI pergunta ao usuário (Sim/Não) se o assunto é aquele; com Sim, envia à gerência um resumo com o passo a passo da área, quem acessa o módulo e um roteiro de checagem; a gerência marca `RESOLVIDO` no painel da NucleAI.
5. Ao encerrar, o chat é apagado; ficam só os registros estatísticos.
6. **Pedido de comando**: "imprimir a agenda do dia" → a NucleAI pergunta Sim/Não (botões ou texto) → confere a permissão de novo → executa e registra no registro de atividades.

## 10. Robô do PDCA e Qualidade [FATO]
1. Diariamente (laço de 10 min, uma vez por dia) o robô analisa os últimos 30 dias: compara cada indicador com a meta e com o período anterior, ignora bases pequenas (< 20), encontra concentração no Pareto e calcula a GUT.
2. Cria **rascunhos** de problema (PDCA + Ishikawa + 5 Porquês + 5W2H) e avisa a gerência.
3. A gerência **aceita** (vira `ABERTO`, entra no Ciclo PDCA), **edita** ou **descarta** (não volta por 30 dias).
4. O problema segue: ações 5W2H com prazo, fases P-D-C-A, evidência em números; relatório em PDF.

## 11. Pesquisa de satisfação [FATO]
1. A gerência edita as perguntas (até 10) e imprime o **cartaz com QR Code** (ou envia o link); o endereço usa o IP do servidor ou o definido pela gerência.
2. O cliente, **na rede interna**, abre `/pesquisa` pelo celular, responde Ótimo/Bom/Ruim/Péssimo a todas as perguntas e, se quiser, elogio/sugestão/nome/telefone.
3. O sistema grava a resposta, calcula a nota média (0–10), alimenta o indicador de satisfação e **avisa a gerência** (só a nota) com botões Sim/Não.
4. A gerência revisa as respostas, vê percentual de satisfação por pergunta e emite o relatório ONA (PDF/Excel).

## 12. Contas a pagar e faturamento [FATO]
1. **Conta comum**: descrição, categoria, vencimento, valor, fornecedor opcional. **Compra parcelada**: 2 a 60 parcelas, valor total dividido ou valor por parcela, datas mensais ou manuais; todas com `parcela_grupo`.
2. **Quitar** exige banco; **reabrir** limpa banco e data.
3. **Faturamento**: a fatura (convênio, referência, bruto, tributos → líquido, previsão) nasce `ABERTO`; ao quitar informa data, valor recebido (padrão = líquido) e banco; a diferença é a **glosa**. O dashboard mostra recebido × a receber, prazo médio e envelhecimento.
4. **Repasse médico** (Agenda > Financeiro): pacientes `VEIO` × valor do convênio por exame × percentual.
