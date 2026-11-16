"""Base de ajuda da NucleAI, parte 2: Agenda, Cadastros e Financeiro."""


def L(*linhas):
    return '\n'.join(linhas)


TEMAS_B = [
    ('Agenda', [
        ('Agenda de exames', [
            ('Criar a agenda do dia', L(
                '1. Escolha o dia no calendário.',
                '2. Crie a agenda de cada exame que será feito naquele dia.',
                '3. Dias em que a clínica não atende podem ser bloqueados.',
                'Tudo é salvo ao sair de cada célula, não existe botão de salvar.')),
            ('Preencher a grade de pacientes', L(
                '1. Digite o nome, o contato e escolha o convênio na lista dos convênios cadastrados.',
                '2. O telefone é padronizado sozinho: (XX)9XXXX-XXXX.',
                '3. Use a observação para lembretes: ela aparece em vermelho e em caixa alta ao lado da data.',
                '4. Para copiar a agenda ou uma linha para outro dia, use os botões de copiar.')),
            ('Status do paciente', L(
                'Escolha o status na própria linha:',
                '• Agendado • Veio • Faltou • Retorno • Reagendado • Desistiu',
                'Retorno é para quem veio e volta em outro dia (por exemplo, a segunda etapa do MIBI): o sistema pergunta o dia e o horário, marca o paciente lá e deixa a linha atual na cor do Veio.',
                '"Veio" conta no financeiro da agenda. "Faltou" libera o 💬 para chamar o paciente pelo WhatsApp com uma mensagem acolhedora de resgate.')),
            ('MIBI, lista de espera e impressão', L(
                'MIBI: escolha Estresse, Repouso ou Protocolo e informe a senha de autorização. Protocolo pinta a linha de verde e a presença fica em azul.',
                'Lista de espera: anote quem aguarda vaga e encaixe quando abrir um horário.',
                'Imprimir: use o botão de impressão da agenda do dia.')),
            ('Imprimir a agenda do dia', L(
                '1. Abra a agenda do dia e clique em imprimir.',
                '2. O PDF sai só com os horários que têm paciente.',
                '3. No topo, um resumo mostra o total de pacientes, o total por exame e o total por convênio.')),
        ]),
        ('Relatórios da agenda', [
            ('Gerar o relatório', L(
                '1. Escolha o período e, se quiser, exame e convênio.',
                '2. Clique em gerar.',
                'O relatório mostra quantos pacientes vieram, faltaram ou marcaram retorno. A taxa de falta considera quem veio e quem faltou.')),
            ('Salvar em PDF ou Excel', L(
                'Use os botões PDF e Excel no alto do relatório.',
                'O PDF sai com cabeçalho da clínica e numeração de páginas; no Excel os números ficam como número, prontos para somar.')),
        ]),
        ('Reservas do convênio', [
            ('Gerar as planilhas em branco', L(
                '1. Em Agenda de exames, clique em "Reservas do convênio" (ou, num dia que tem vaga reservada, em "Planilha das reservas do dia").',
                '2. Escolha o convênio (ou todos) e o período e clique em "Baixar planilhas (Excel)".',
                '3. Um dia reservado gera uma planilha. Num período maior (por exemplo, um mês), vem um arquivo .zip com uma planilha para cada dia reservado e um relatório simples em PDF com as datas e a quantidade de vagas.',
                'Cada planilha traz data, hora, exame e convênio das vagas reservadas e espaço para nome, contato, senha e observação. Envie ao convênio. As planilhas não ficam guardadas no sistema.')),
            ('Importar a planilha preenchida', L(
                '1. Na agenda do dia (botão "Importar planilha preenchida", que só aparece quando há vaga reservada em branco) ou em "Reservas do convênio", escolha o arquivo devolvido.',
                '2. O sistema preenche nome, contato, senha e observação de cada vaga. Vagas já preenchidas não são alteradas.',
                'Linhas que não conferem aparecem no resultado, para você corrigir.')),
        ]),
        ('Faltas e reagendamento', [
            ('Chamar quem faltou', L(
                '1. Escolha o período e o exame.',
                '2. Clique em "💬 WhatsApp" na linha da pessoa: abre a conversa com uma mensagem acolhedora convidando a remarcar.',
                '3. Envie a mensagem no WhatsApp.')),
            ('Marcar Reagendado ou Desistiu', L(
                '1. Na linha do paciente, use a lista "Marcar…".',
                '2. Reagendado: escolha o novo dia e um horário livre e clique em "Reagendar para este horário". O paciente é copiado para lá com todas as informações.',
                '3. Desistiu: registra que a pessoa não quer mais fazer o exame.',
                'O histórico da linha registra "Reagendado por" com o login de quem reagendou.')),
        ]),
        ('Financeiro da Agenda', [
            ('Como o valor é calculado', L(
                'Contam só os pacientes com status "Veio" no período.',
                'O sistema usa o valor do convênio para o tipo de exame e calcula o repasse ao médico pelo percentual definido.')),
            ('Conferir e exportar', L(
                '1. Escolha o período e filtre por convênio ou médico, se precisar.',
                '2. Confira os totais.',
                '3. Gere o PDF ou o Excel pelos botões do alto.')),
        ]),
    ]),
    ('Cadastros', [
        ('Clientes', [
            ('Cadastrar um novo cliente', L(
                'Campos obrigatórios: Nome, CPF, Data de nascimento, Sexo (Feminino ou Masculino) e Convênio (é o critério para o lançamento na Medcloud).',
                'Complete se tiver: nome da mãe, profissão, endereço (CEP, rua, número, bairro, cidade, UF), contato e número do cartão do convênio ou SUS.',
                'Salve ao final.')),
            ('Telefone no padrão', L(
                'O contato é padronizado ao salvar: (XX)9XXXX-XXXX para celular e (XX)XXXX-XXXX para fixo.',
                'Digite com DDD. Telefone incompleto não é aceito: confira os números.')),
            ('Pesquisar e corrigir um cadastro', L(
                '1. Digite nome, código ou CPF na pesquisa.',
                '2. Abra o cliente e corrija o que precisar.',
                '3. Salve. O sistema registra quem cadastrou e quem alterou por último.')),
        ]),
        ('Convênios', [
            ('Cadastrar convênio e valores', L(
                '1. Clique para adicionar e digite o Nome.',
                '2. Informe os valores: MIBI, Óssea, TGI, Paratgi e Gálio.',
                '3. Salve. Os valores alimentam o financeiro da agenda e o faturamento.')),
            ('Convênios que vão para o caixa', L(
                'Convênios marcados "vai para o caixa" não geram protocolo de guia (ex.: PARTICULAR, SMS, MAIS MED).',
                'O pagamento deles é recebido em "Caixa" e "Movimento de caixa".')),
        ]),
        ('Médicos', [
            ('Cadastrar um médico', L(
                '1. Informe o Nome e o CRM.',
                '2. Salve. O médico passa a aparecer na lista dos lançamentos.')),
            ('Cadastro automático', L(
                'Médicos digitados no lançamento de atendimento entram aqui sozinhos.',
                'Use a pesquisa para conferir se o nome está correto e corrigir duplicidades.')),
        ]),
        ('Exames e fichas', [
            ('Escolher as fichas de cada exame', L(
                '1. Abra o exame (ou crie um novo).',
                '2. Marque as fichas que serão impressas ao lançar o exame.',
                '3. Use as setas para definir a ordem de impressão.',
                '4. Salve.')),
            ('Fichas personalizadas', L(
                'Crie documentos próprios da clínica: termos, orientações, declarações.',
                'Os campos entre chaves, como {nome}, são trocados pelos dados do paciente na hora de imprimir.',
                'As fichas criadas podem ser marcadas em qualquer exame.')),
        ]),
        ('Cores dos exames', [
            ('Ajustar cores e palavras', L(
                'Cada tipo de exame tem uma cor, como na planilha. Aqui você muda a cor e as palavras que identificam o tipo (ex.: LINF. SENT, LINFONODO e LINFO são o mesmo tipo).',
                'Salve para aplicar.')),
            ('Importar a planilha de exames', L(
                'A administração pode importar a planilha EXAMES.xlsx: traz os exames de todas as abas com a cor de cada tipo.',
                'Pacientes e médicos com o mesmo nome do cadastro ficam ligados a ele.')),
        ]),
    ]),
    ('Financeiro', [
        ('Caixa', [
            ('Ver o que está a receber', L(
                'A tela lista os atendimentos dos convênios que vão para o caixa (Particular, SMS, Mais Med).',
                'Use os filtros De, Até, Usuário e Status para achar o lançamento.')),
            ('Informar o pagamento', L(
                '1. Abra o lançamento.',
                '2. Informe o Valor (R$), o Status e a Forma de pagamento.',
                '3. Preencha a Nota fiscal e, se precisar, a Observação.',
                '4. Salve.')),
        ]),
        ('Movimento de caixa', [
            ('Abrir o caixa do dia', L(
                '1. Abra "Movimento de caixa" no início do dia.',
                '2. Informe o "Fundo de troco (R$)" e clique em "Abrir caixa".',
                'Só existe um caixa por usuário em cada dia. Se houver caixa de outro dia ainda aberto, feche-o antes: o sistema bloqueia novos lançamentos e avisa pelo AVISOS DO SISTEMA.')),
            ('Receber um pagamento e imprimir a quitação', L(
                '1. Na lista de pagamentos a receber, clique em "Receber" no lançamento.',
                '2. Escolha a Forma de pagamento: DINHEIRO ou PIX.',
                '3. Informe o "Número da nota fiscal emitida" (obrigatório).',
                '4. Em dinheiro, digite o "Valor entregue pelo cliente (R$)": o troco é calculado sozinho.',
                '5. Clique em "Confirmar recebimento" e abra a "Quitação" para imprimir o comprovante.',
                'Convênios marcados "Pago na clínica" também caem aqui.')),
            ('Pagamento em duas formas (dinheiro e PIX)', L(
                'Quando o cliente paga uma parte em dinheiro e outra em PIX, faça um só recebimento:',
                '1. Em "Receber", marque "Dividir em duas formas de pagamento".',
                '2. Informe quanto foi pago na segunda forma; o resto fica na primeira. Em dinheiro, digite o valor entregue só da parte em dinheiro: o troco é calculado sobre ela.',
                '3. Confirme. O relatório de fechamento soma cada parte no seu lugar (dinheiro e PIX) e a quitação mostra as duas formas.')),
            ('Ver só os seus lançamentos do dia', L(
                'A tela mostra por padrão só o que você lançou, no dia de hoje.',
                '1. Para ver outro dia, escolha a data em "Lançamentos do dia" e clique em "Mostrar". Marque "todas as datas" para ver tudo o que ainda está a receber.',
                '2. Administração e gerência podem marcar "lançamentos de todos os usuários" para conferir e excluir lançamentos de outras pessoas.',
                'O relatório de fechamento de um caixa só é aberto pelo dono dele e pela administração ou gerência.')),
            ('Fechar o caixa e assinar o relatório', L(
                '1. No fim do dia, confira os recebimentos.',
                '2. Clique em "Fechar caixa".',
                '3. Abra o "Relatório (PDF)": ele separa dinheiro (com troco) e PIX, para você assinar.',
                'O sistema avisa às 17h quem ainda está com o caixa aberto.')),
            ('Corrigir um recebimento', L(
                'Com o caixa aberto, você edita os seus recebimentos na própria tela.',
                'Depois de fechado, só administração e gerência conseguem corrigir. Se errou, peça a elas.')),
        ]),
        ('Faturamento', [
            ('Registrar uma fatura', L(
                '1. Em Faturamento, clique em "Nova fatura".',
                '2. Escolha o Convênio (ou particular) e a Data de referência.',
                '3. Informe o Valor faturado, o Protocolo do faturamento e a Quantidade de guias faturadas.',
                '4. A Nota fiscal é opcional: sem ela, a fatura fica como "Faturado (sem nota)". Se informar o número, ela já fica com a nota emitida.',
                '5. Se quiser, importe o PDF do protocolo e salve.')),
            ('Protocolo em PDF', L(
                'Na lista, o botão "Importar PDF" guarda o protocolo da fatura para consultas futuras (só PDF).',
                'Depois, "Ver PDF" abre o arquivo dentro do sistema, sem baixar; o botão ao lado baixa quando você quiser. Dá para trocar ou remover o PDF na tela do protocolo.',
                'O botão "PDF" da linha gera o resumo da fatura (dados, nota, recebimento e glosa).')),
            ('Quitar e reabrir', L(
                'O recebimento agora é lançado na aba "Recebidas" (veja a ajuda dela). Lá também dá para reabrir um recebimento feito por engano.',
                'Tudo fica registrado em "Registros de atividades".')),
            ('Acompanhar atrasos', L(
                'Faturas com previsão de recebimento já passada aparecem como atrasadas.',
                'Use os filtros por situação, convênio e período para cobrar o que está pendente.')),
        ]),
        ('Emissão da nota fiscal', [
            ('Emitir a nota fiscal', L(
                '1. Abra a aba "Emissão da nota fiscal": ela lista as faturas que ainda estão sem nota.',
                '2. Na linha da fatura, digite o número da nota, confira a data de emissão e clique em "Emitir".',
                '3. A situação muda para "Nota fiscal emitida" e a fatura vai para a aba "Recebidas".',
                'Digitou errado? Corrija o número na lista de notas emitidas, ou use "Desfazer" para a fatura voltar a "Faturado (sem nota)".')),
        ]),
        ('Recebidas', [
            ('Lançar o recebimento', L(
                '1. Abra a aba "Recebidas". Em "A receber" ficam as faturas com nota emitida.',
                '2. Clique em "Lançar recebimento", informe a data, o banco, o Bruto recebido e, se houver, marque "Informar tributos retidos" e digite os tributos.',
                '3. O Líquido recebido é calculado (bruto − tributos); se preferir, digite o líquido e o bruto é refeito.',
                '4. Confirme. A fatura passa para "Recebido" e entra na comparação abaixo.')),
            ('Entender a glosa', L(
                'A glosa é a diferença entre o bruto faturado e o bruto recebido: o que o convênio deixou de pagar.',
                'Na tabela "Recebidas", cada fatura mostra faturado, recebido (bruto), tributos, líquido recebido e a glosa em reais e em porcentagem. Vermelho = glosa; verde = sem glosa; azul = recebeu a mais.',
                'O Dashboard financeiro e os indicadores da Qualidade usam esses valores.')),
            ('Desfazer um recebimento', L(
                'Na linha da fatura recebida, clique em "Reabrir": o recebimento é desfeito e a fatura volta para "A receber".')),
        ]),
        ('Contas a pagar', [
            ('Cadastrar uma conta', L(
                'Informe Descrição, Categoria, Vencimento e Valor (R$).',
                'Complete com Nota fiscal, Fornecedor e Observação, e salve.')),
            ('Quitar uma conta', L(
                '1. Na lista de contas, clique em "Quitar" na linha da conta.',
                '2. Informe a data do pagamento, o banco e a forma de pagamento.',
                '3. O status muda para quitado e o total em aberto diminui.')),
            ('Gerar lote de pagamento', L(
                '1. Marque as contas na lista que serão pagas juntas.',
                '2. Escolha o "Banco do lote de pagamento".',
                '3. Clique em "Gerar lote de pagamento e imprimir".',
                'O lote recebe um número e a lista abre para impressão. As contas saem da lista normal e ficam no filtro "Em pagamento (em lote)".')),
            ('Quitar ou devolver as contas do lote', L(
                '1. Abra "Lotes de pagamento" e clique no lote.',
                '2. Clique em "Quitar todas as pendentes", ou marque as contas já pagas e clique em "Quitar marcadas".',
                '3. Informe a data, o banco e a forma de pagamento.',
                '4. Para as contas que não foram pagas, clique em "Devolver marcadas para a lista": elas voltam para a lista normal.',
                'O lote fica Concluído quando não sobra conta em pagamento. "Imprimir lista" imprime a lista do lote de novo.')),
            ('Conta recorrente mensal', L(
                'Marque "Conta recorrente" ao cadastrar a conta e escolha o dia do vencimento (1 a 31).',
                'Todo mês a conta entra em aberto nesse dia; em fevereiro, cai no último dia do mês.',
                'Pausar, reativar, editar ou excluir a recorrência fica em Contas a pagar > Contas recorrentes.')),
            ('Vencimentos e alertas', L(
                'O Dashboard mostra as contas vencidas, as que vencem em 7 dias e o total em aberto.',
                'Acompanhe por aqui para não perder prazos.')),
        ]),
        ('Consulta rápida', [
            ('Consultar os valores dos exames', L(
                '1. Abra "Tabela de preços" e clique em "Consulta rápida".',
                '2. Digite parte do nome do exame ou o código. A lista é filtrada enquanto você escreve.',
                '3. Confira os valores disponíveis por convênio; quando não houver preço, aparece um traço.')),
        ]),
        ('Tabela de preços', [
            ('Criar uma tabela de preços', L(
                '1. Abra "Tabela de preços" e clique em "Nova tabela".',
                '2. Informe o "Nome da tabela" e a "Vigência a partir de" (dd/mm/aaaa).',
                '3. Preencha a grade: código, exame, valor e observação. Use "+ Linha" para acrescentar exames.',
                '4. Clique em "Salvar". Valor em branco sai como "a consultar" no PDF.',
                'Para mudar preços sem perder os antigos, crie outra tabela com a nova vigência.')),
            ('Ferramentas: exames, convênio e reajuste', L(
                'As ferramentas aparecem depois de salvar a tabela. Elas gravam direto na tabela, então salve a grade antes.',
                '1. "Adicionar exames" acrescenta os exames ativos que ainda não estão na tabela, sem valor.',
                '2. "Copiar valores" traz os valores preenchidos de um convênio escolhido.',
                '3. "Reajustar" aplica uma porcentagem em todos os valores; use valor negativo para reduzir. Escolha o arredondamento antes de clicar.')),
            ('Imprimir ou salvar em PDF', L(
                'Na tela da tabela, clique em "Abrir PDF" para ver o arquivo ou em "Baixar PDF" para guardá-lo.',
                'Para imprimir, abra o PDF e use Imprimir do navegador. O campo "Observação" sai no fim do PDF.')),
            ('Duplicar para a próxima vigência', L(
                '1. Na tela da tabela, vá até a ferramenta "Duplicar para a próxima vigência".',
                '2. Informe o "Nome da nova tabela" e clique em "Duplicar".',
                '3. A cópia traz os mesmos exames e valores, sem vigência. Preencha a vigência e ajuste os preços que mudaram.',
                'A tabela antiga continua guardada, sem alterações.')),
        ]),
        ('Faturamento: relatórios', [
            ('Escolher período e convênio', L(
                '1. Escolha a data inicial e final.',
                '2. Escolha um convênio ou deixe todos.',
                '3. Clique em gerar.')),
            ('Ler o painel financeiro', L(
                'O painel mostra o valor faturado, os recebimentos e as faturas por convênio, usando a data de referência de cada fatura.',
                'Faturas atrasadas aparecem em destaque.')),
        ]),
        ('Relatórios de atendimentos', [
            ('Escolher o agrupamento', L(
                '1. Escolha o período.',
                '2. Escolha por onde agrupar: exame, convênio, médico ou usuário.',
                '3. Clique em gerar.')),
            ('Salvar ou imprimir', L(
                'Use os botões de impressão e exportação da tela para guardar o relatório.',
                'Os números são os mesmos da lista de atendimentos do período.')),
        ]),
        ('Relatório de resgate', [
            ('O que o relatório mostra', L(
                'Quantos pacientes que faltaram cada usuário resgatou no período: reagendados em outro dia e desistências.',
                'O resgate é registrado em "Faltas e reagendamento" ao marcar Reagendado ou Desistiu.')),
            ('PDF e Excel', L(
                'Escolha o período, gere e use os botões PDF ou Excel.',
                'Os dois seguem o mesmo cabeçalho e rodapé dos outros relatórios.')),
        ]),
        ('Caixa diário da empresa', [
            ('Informar os saldos iniciais', L(
                '1. Abra "Caixa diário da empresa" e clique em "Saldos iniciais".',
                '2. Informe a data-base e o saldo de cada conta (Banco do Brasil, Unicred, Caixa e Movimento de caixa) do fechamento da planilha anterior.',
                '3. Clique em "Gravar saldos iniciais". Isso só precisa ser feito uma vez.')),
            ('Lançar entradas e saídas do caixa', L(
                '1. Escolha o dia no campo "Dia" e clique em "Ver o dia".',
                '2. Em "Novo lançamento", escolha o tipo (dinheiro que entrou ou dinheiro que saiu), a descrição, o valor e a conta.',
                '3. A conta define onde o dinheiro entrou ou saiu: Banco do Brasil (amarelo), Unicred (verde), Caixa (azul) ou Movimento de caixa (cinza).',
                '4. Clique em "Lançar". O saldo de cada conta e o Saldo Total são recalculados.')),
            ('Corrigir um lançamento', L(
                '1. Na lista do dia, clique em "Editar" no lançamento.',
                '2. Altere o que precisar e clique em "Salvar alteração".',
                'Os saldos dos dias seguintes são recalculados sozinhos.')),
            ('Baixar a planilha do dia', L(
                '1. Escolha o dia e clique em "Baixar planilha do dia (Excel)".',
                'A planilha sai com as cores de cada conta e com o mesmo cálculo da planilha original.')),
        ]),
    ]),
]
