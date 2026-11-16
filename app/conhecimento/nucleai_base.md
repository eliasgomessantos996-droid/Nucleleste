# Pacote de conhecimento da NucleAI (versão 1, gerado a partir do código e da pasta docs/)

## A clínica
Centro de Medicina Nuclear do Leste Mineiro (Nucleleste), em Governador Valadares (MG): diagnóstico por imagem em
medicina nuclear. O paciente recebe um radiofármaco (ex.: tecnécio-99m), as imagens são feitas e um médico nuclear
emite o laudo. Exames comuns: MIBI (miocárdio: Estresse, Repouso, Protocolo), Óssea, Renal/DMSA/DTPA, Pulmonar,
Linfonodo sentinela, SPECT cerebral, TGI (tireoide), PARATGI (paratireoide), Gálio. Doses de iodo, gálio e PCI são
agendadas à parte, com preparo (dieta e suspensão de medicação).

## O sistema
Sistema web interno: um PC servidor e os demais PCs pelo navegador, com login e senha. Cada usuário só vê os módulos
liberados no seu perfil (recepção, técnico, financeiro, gerência, administração, banco de horas, estagiário, funcionário).
Tudo o que se grava fica no Registro de atividades (quem fez, quando e o quê) e muitas ações têm o botão Desfazer.

## A jornada de um exame
1. Agenda: horários por exame e dia, reserva de vagas para convênio, lista de espera, MIBI com Estresse/Repouso.
   Status de cada paciente: Agendado, Veio, Faltou, Retorno, Resgatado (falta reagendada), Desistiu.
2. Confirmação e faltas: textos de WhatsApp prontos; a falta pode ser resgatada (reagendada) e o resgate conta para o usuário.
3. Chegada: a recepção cadastra o cliente (nome, CPF, nascimento, sexo e convênio obrigatórios) e lança o Atendimento (exame,
   convênio, médico, medicamentos e questionário da ficha PNT). As fichas são impressas com a previsão do laudo.
4. Cobrança: convênios marcados "vai para o caixa" (Particular, SMS, Mais Med) geram lançamento no Caixa; os outros, guia no Protocolo de guias.
5. Exames realizados: o técnico registra radiofármaco, lote, atividades e horas; o exame entra no Mapa de laudos.
6. Laudo: Processando imagem → Laudando → Liberado → Entregue.
7. Faturamento: notas por convênio, tributos, recebimento, glosa e prazo médio.

## Dinheiro
Convênios (faturamento) e particular (caixa do balcão, dinheiro ou PIX). Contas a pagar com fornecedores e parcelas.
Caixa diário da empresa com quatro contas (Banco do Brasil, Unicred, Caixa Econômica, dinheiro). Repasse médico pela
agenda (quem veio × valor do convênio × percentual).

## Qualidade e conformidade
Relatório ONA (identificação, registro, prazo de laudo, comparecimento) e Gestão da qualidade (indicadores, PDCA,
Pareto, Ishikawa, 5 Porquês, GUT, riscos, 5W2H, SWOT, fluxogramas, POPs, organograma, ocorrências, satisfação,
avaliação de fornecedores). Blindagens dos geradores de tecnécio têm validade e devolução com documentos da CNEN.
Documentos de fiscalização avisam o vencimento em 60, 30, 15, 7, 1 e 0 dias. Backup em .zip com restauração protegida por código.

## Pessoal
Banco de horas pelo relógio de ponto, escala, documentos do departamento pessoal e "Minha área" do funcionário.

## Comunicação
Mensagens entre usuários (com imagens que somem em 24 h), avisos do sistema, contato Agenda, laudos liberados e a
própria NucleAI. A NucleAI pode chamar a gerência quando não resolver.

## Glossário
Atendimento: registro da recepção (gera guia ou caixa e imprime fichas). Exame realizado: registro técnico.
Guia: protocolo de convênio. PNT: ficha com questionário por exame. SAE: ficha de enfermagem. NEWS: escore clínico.
UNACON: serviço para o qual se reservam horários. Resgate: falta reagendada. Glosa: diferença entre faturado e recebido.
ONA: Organização Nacional de Acreditação. CNEN: Comissão Nacional de Energia Nuclear.

## O que o sistema não faz
Não envia WhatsApp nem e-mail automaticamente, não se integra a equipamentos de imagem/PACS, não emite NF-e nem TISS,
não controla estoque de radiofármacos nem dosimetria.
