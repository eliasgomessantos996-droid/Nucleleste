# Interface (observada em execução de teste)

Observado em 19/10/2026 numa cópia local do código (pasta temporária), com banco novo e vazio, na porta 8099. A instalação real e `dados/` não foram usados. Nenhum dado real foi visto nem gravado. [FATO: telas abertas no navegador]

## Entrada
- Tela de login (`/login`) com logo da clínica, campos Usuário e Senha. Usuário é convertido para maiúsculas (ADMIN no primeiro acesso).
- Após o login, aparece um tutorial da NucleAI (21 passos, pode ser pulado).

## Estrutura da tela
- Barra lateral esquerda com grupos: RECEPÇÃO, LANÇAMENTOS, AGENDA, CADASTROS, FINANCEIRO, DOCUMENTOS, QUALIDADE, CONTROLE DE PONTO (Banco de Horas), CONFIGURAÇÃO. Itens só aparecem conforme os módulos do usuário.
- Topo: NucleAI, Mensagens (com contador), Dashboard, Meus favoritos, Minha conta, Rever tutorial.
- Cabeçalho de cada tela: nome do grupo, título e uma frase explicando a função; data do dia no canto.
- Tela inicial (`/`): cartões de atalho (Lançar atendimento, Novo cliente, Agendar medicamento, Protocolo de guias, Caixa, Faturamento) e painéis de hoje: atendimentos do dia, clientes, caixas em aberto, contas a pagar, doses dos próximos 7 dias, contas vencendo em 7 dias.

## Telas conferidas (sem alterar nada)
| Tela | Caminho | O que mostra |
|---|---|---|
| Lançar atendimento | `/atendimentos/novo` | cliente, exame, data (com previsão automática do laudo), convênio, médico, medicamentos em uso, exames anteriores |
| Mapa de laudos | `/laudos` | prazo padrão de 24 horas; colunas Processando imagem, Laudando, Liberado para entrega, Entregue; botões Limpar entregues e Laudos entregues |
| Agenda de exames | `/agenda` | calendário mensal, criar agenda por exame, copiar dia, bloquear dia, lista de espera, legenda de status (Agendado, Veio, Faltou, Remarcou, Reagendado, Desistiu, Protocolo MIBI, Reservado para convênio, Horário livre) |
| Movimento de caixa | `/movimento-caixa` | abrir caixa com fundo de troco, a receber, recebimentos lançados (visão da gerência) |
| Exames e fichas | `/exames` | tabela de exame → fichas impressas e extras; botão Editar por linha |
| Usuários e perfis | `/usuarios` | lista com perfil, módulos liberados, último acesso, registros por usuário; Editar perfil e Redefinir senha |

## Observações de uso [FATO da tela]
- Textos explicativos em quase todas as telas dizem quem pode fazer cada ação (ex.: gerência exclui lançamento de caixa, com registro na auditoria).
- O aviso de laudo liberado vai para o contato "LAUDOS DO SISTEMA" e some em 3 dias (confirma REGRAS §11).
- Previsão de laudo mostrada ao vivo: 24 horas corridas a partir da data do atendimento (confirma REGRAS §10).
- Não foram abertas telas de impressão, relatórios em PDF, Banco de Horas nem chat com dados. Não testado: fluxos de gravação e impressão.

## Fluxos testados em cópia local com banco falso (19/10/2026)
Dados fictícios: "PACIENTE TESTE FICTICIO", CPF de exemplo, médico fictício. Nada real.
1. **Cadastro de cliente** (`/clientes/novo`): salvou como cliente 1 e o CPF exibido em impressão ficou formatado. [FATO]
2. **Lançar atendimento** (`/atendimentos/novo?cliente=1`): exame MIBI com as 8 perguntas respondidas NÃO e medicamentos "NENHUM (TESTE)" foi salvo. O sistema pediu as respostas do questionário e mostrou a previsão de laudo (24 horas). [FATO]
3. **Destino do lançamento**: sem convênio cadastrado, o atendimento foi para **Protocolo de guias** (1 guia), não para o caixa. Caixa do período ficou vazio. Confirma REGRAS §7 e FLUXOS §1. [FATO]
4. **Impressão das fichas** (`/atendimentos/1/imprimir`): a página montou as fichas do MIBI (Ficha MIBI, PNT, termo, orientação, SAE, NEWS) e a lista de fichas marcáveis. Dados do paciente preenchidos (idade 46 anos, contato formatado). A saída em PDF pelo navegador não foi verificada visualmente. [FATO parcial]
5. **Mapa de laudos**: continuou com 0 exames. Confirma FLUXOS §2: o atendimento não cria exame realizado. [FATO]

Não testado: impressão do PDF final, relatórios, Banco de Horas, chat, qualidade e recebimento no caixa (pois o atendimento foi para guia).
