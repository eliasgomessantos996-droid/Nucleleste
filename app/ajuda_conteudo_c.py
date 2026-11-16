"""Base de ajuda da NucleAI, parte 3: Documentos, Qualidade, Blindagens, Outros, Banco de Horas e Configuração."""


def L(*linhas):
    return '\n'.join(linhas)


TEMAS_C = [
    ('Documentos', [
        ('Documentos', [
            ('Enviar um contrato ou documento', L(
                '1. Abra "Documentos" e clique em "Documentos e contratos".',
                '2. Digite o "Nome do documento" e escolha o "Arquivo".',
                '3. Clique em "Enviar". O documento fica guardado: use Abrir ou Baixar na lista para vê-lo depois.')),
            ('Documento de fiscalização', L(
                '1. Clique em "Documentos de fiscalização".',
                '2. Informe o "Nome do documento", o "Vencimento" e o "Arquivo".',
                '3. Clique em "Enviar". O sistema passa a vigiar o vencimento. Para trocar os dados, use Editar; para remover, Excluir.')),
            ('Avisos de vencimento', L(
                'Os avisos saem automaticamente 60, 30, 15, 7 e 1 dia antes, no dia do vencimento e quando vence (VENCIDO).',
                'Chegam pelo contato AVISOS DO SISTEMA, visível só para a gerência.')),
        ]),
    ]),
    ('Qualidade', [
        ('Relatório ONA', [
            ('Gerar o relatório', L(
                '1. Escolha as datas De e Até.',
                '2. Clique em Gerar.',
                'A tela mostra os indicadores com numerador, denominador e percentual, e também a produção por exame, convênio e sexo.')),
            ('Entender os indicadores', L(
                '• Identificação do paciente e registro completo do exame.',
                '• Cadastro com CPF e cadastro com sexo informado.',
                '• Laudo entregue no prazo (24 horas depois do exame).',
                '• Comparecimento na agenda.',
                'Para melhorar os números, mantenha os cadastros completos e atualize o Mapa de laudos.')),
            ('PDF e Excel', L(
                'Use os botões PDF e Excel no alto da tela para guardar o relatório do período.')),
        ]),
        ('Central da qualidade', [
            ('Para que serve', L(
                'É a porta de entrada das ferramentas de gestão: mostra os indicadores críticos, as sugestões do robô, os problemas em '
                'tratamento e as ações atrasadas, e leva a cada ferramenta.')),
            ('Modelos prontos e PDF com assinatura', L(
                'Cada aba tem uma galeria de modelos prontos para medicina nuclear (problemas, riscos, SWOT, fluxogramas, organogramas, protocolos, critérios e perguntas).',
                'Aplique com um clique e altere só os dados importantes. Todo PDF traz a análise e o quadro de assinatura e validação, para apresentar a auditorias e órgãos.')),
        ]),
        ('Indicadores (KPI)', [
            ('Ler o painel', L(
                '1. Escolha o período (De e Até) e clique em Atualizar.',
                '2. Cada cartão mostra o valor, a meta e a situação: verde na meta, amarelo atenção, vermelho crítico.',
                '3. A linha mostra os últimos seis meses; a linha tracejada é a meta.',
                'Os números vêm da agenda, dos exames realizados, dos laudos, do faturamento, das contas, das blindagens e das ocorrências.')),
            ('Mudar as metas', L(
                'Abra "Metas dos indicadores", digite o novo alvo de cada um e clique em Gravar metas.')),
        ]),
        ('Robô do PDCA', [
            ('Rodar a análise', L(
                '1. Escolha o período e clique em "Analisar agora".',
                '2. O robô confere cada indicador com a meta e com o período anterior, procura onde o problema se concentra '
                '(exame, convênio, dia, motivo) e calcula a prioridade GUT.',
                '3. Cada problema encontrado vira um rascunho com PDCA, Ishikawa, 5 Porquês e plano 5W2H.',
                'Ele também roda sozinho uma vez por dia e avisa a gerência quando aparece problema novo.')),
            ('Aceitar ou descartar', L(
                'Abra a sugestão, ajuste o que quiser e clique em Aceitar: o problema passa para o Ciclo PDCA.',
                'Descartar faz o robô não sugerir o mesmo problema pelos próximos 30 dias.')),
        ]),
        ('Ciclo PDCA', [
            ('Abrir um problema', L(
                '1. Em "Abrir um problema", escreva o título e a descrição.',
                '2. Dê as notas de Gravidade, Urgência e Tendência (1 a 5).',
                '3. Clique em "Abrir problema" e preencha as fases: Planejar, Fazer, Checar e Agir.')),
            ('Imprimir o PDCA completo', L(
                'Dentro do problema, use "PDF completo": sai o PDCA, a GUT, o Ishikawa, os 5 Porquês e o plano 5W2H.')),            ('Começar por um modelo pronto', L(
                'No alto da tela, abra "Modelos prontos de análise de problemas" e clique em "Usar este modelo".',
                'O problema já entra com as causas do Ishikawa, os cinco porquês, a GUT e o plano 5W2H de medicina nuclear; ajuste só o que for do seu serviço.')),
        ]),
        ('Gráfico de Pareto', [
            ('Gerar o Pareto', L(
                '1. Escolha a fonte dos dados (faltas por exame, convênio, dia ou motivo, ocorrências, laudos fora do prazo, glosa).',
                '2. Escolha o período e clique em Gerar.',
                'As barras ficam em ordem e a linha mostra o acumulado; os itens até 80% (classe A) são os que mais pesam.')),
            ('Classificar o motivo das faltas', L(
                'Escolha a fonte "Faltas por motivo": a tela lista as faltas sem motivo; escolha o motivo de cada uma e confirme no botão ao lado.')),
        ]),
        ('Diagrama de Ishikawa', [
            ('Montar a espinha de peixe', L(
                '1. Escolha o problema.',
                '2. Escolha a categoria (Método, Máquina, Mão de obra, Material, Meio ambiente, Medição), escreva a causa e clique em Incluir causa.',
                'Marque "principal" nas causas mais prováveis: aparecem em vermelho com estrela.')),
        ]),
        ('Cinco porquês', [
            ('Chegar à causa raiz', L(
                '1. Escolha o problema.',
                '2. Responda "por quê?" cinco vezes, sempre sobre a resposta anterior.',
                '3. Escreva a causa raiz e salve: ela vai para o campo de causa do PDCA.')),
        ]),
        ('Matriz GUT', [
            ('Priorizar os problemas', L(
                'Cada problema recebe Gravidade, Urgência e Tendência de 1 a 5; a prioridade é a multiplicação (até 125).',
                'Mude as notas na própria linha e confirme no botão ao lado: a lista se reordena.')),
        ]),
        ('Matriz de risco', [
            ('Cadastrar um risco', L(
                '1. Em "Novo risco", descreva o risco, a causa e a consequência.',
                '2. Dê a probabilidade e o impacto de 1 a 5 e escolha a resposta (mitigar, evitar, transferir ou aceitar).',
                '3. Informe a ação, o responsável e o prazo e salve. O risco aparece na célula colorida da matriz.')),
        ]),
        ('Plano de ação 5W2H', [
            ('Incluir uma ação', L(
                'Preencha o quê, por quê, onde, quando, quem, como e o valor previsto, escolha a situação e clique em Incluir ação.',
                'Ações com prazo vencido e ainda abertas ficam em vermelho. Use PDF ou Excel para imprimir o plano.')),
        ]),
        ('Matriz SWOT', [
            ('Fazer uma análise', L(
                '1. Em "Nova análise SWOT", dê um título e clique em Criar.',
                '2. Inclua itens nos quatro quadrantes com peso de 1 a 5.',
                'A tela sugere cruzamentos: usar forças nas oportunidades, reduzir ameaças, corrigir fraquezas.')),
        ]),
        ('Fluxograma de processos', [
            ('Desenhar um processo', L(
                '1. Dê o nome e escolha começar em branco ou por um modelo pronto.',
                '2. Use os botões para incluir etapas, decisões, documentos e raias; arraste para posicionar.',
                '3. Clique em Ligar, depois na etapa de origem e na de destino.',
                'As alterações são salvas sozinhas. Use "Cores por" para colorir por tipo, setor ou situação de implantação.')),
            ('Aprovar e imprimir', L(
                'Aprovar versão congela o desenho; uma alteração depois disso abre a próxima versão.',
                'Use Imprimir (folha deitada), baixe em PNG ou SVG, ou use PDF/Baixar: o PDF sai com o desenho, a análise e o quadro de assinaturas.')),
            ('Fluxogramas prontos', L(
                'Abra "Fluxogramas prontos" no alto da tela e escolha um modelo (agendamento, administração da dose, derramamento, rejeitos, faturamento...).',
                'O desenho abre no editor com as raias por setor; mude os nomes e as etapas e aprove a versão.')),
        ]),
        ('Perfil epidemiológico', [
            ('Ler o perfil dos pacientes', L(
                '1. Escolha o período (De e Até) e clique em Atualizar.',
                '2. A tela mostra a pirâmide etária, o sexo, as faixas de idade, a procedência (cidade e bairro), os exames, os convênios, os médicos, os diagnósticos e a evolução por mês.',
                'Use PDF ou Baixar para o documento da ONA, com a análise e os campos de assinatura. Os dados vêm dos exames realizados e do cadastro dos clientes.')),
        ]),
        ('Protocolos (POPs)', [
            ('Criar um protocolo a partir de um modelo', L(
                '1. Abra "Protocolos prontos para medicina nuclear" e clique em "Criar este protocolo" (ou em "Criar todos os protocolos").',
                '2. Ajuste objetivo, responsáveis, passo a passo, registros e referências ao seu serviço e salve.',
                '3. Clique em Aprovar: fica registrado quem aprovou, a data e a validade (1 ano).')),
            ('PDF com assinatura', L(
                'O botão PDF (abrir) ou Baixar gera o protocolo completo com o fluxograma e o quadro de validação (nome, data e assinatura).',
                'A lista mestra reúne todos os protocolos. Alterar um protocolo aprovado abre a versão seguinte em rascunho.')),
        ]),
        ('Organograma', [
            ('Montar o organograma', L(
                '1. Inclua a função mais alta da empresa (por exemplo, Diretoria), sem superior.',
                '2. Inclua as outras funções escolhendo o superior, o setor, a pessoa e a cor da área.',
                'Clique em uma caixa do desenho para editar. Use Imprimir ou PNG.')),
        ]),
        ('Ocorrências e satisfação', [
            ('Registrar uma ocorrência', L(
                '1. Escolha a data, o tipo (não conformidade, evento adverso, reclamação, retrabalho...) e a gravidade.',
                '2. Descreva o que aconteceu, sem o nome do paciente, e a ação imediata.',
                '3. Salve. Use "→ PDCA" para abrir um problema a partir da ocorrência.')),
            ('Lançar a pesquisa de satisfação', L(
                'Em "Pesquisa de satisfação", informe a nota de 0 a 10 dada pelo paciente e o comentário, e clique em Registrar.')),
        ]),
        ('Pesquisa de satisfação (QR Code)', [
            ('Divulgar a pesquisa aos clientes', L(
                'Na tela aparece o QR Code da pesquisa. Imprima o cartaz ou envie o link pelo WhatsApp.',
                'O cliente precisa estar conectado à rede interna da clínica (o Wi-Fi) para abrir o formulário.')),
            ('Editar as perguntas', L(
                'Altere o texto de cada pergunta, exclua as que não quiser ou inclua novas, até o máximo de 15. Cada pergunta tem um tipo: escala (Ótimo, Bom, Ruim ou Péssimo), Sim ou Não (por exemplo, segurança do paciente) ou nota de 0 a 10 (recomendação, NPS).',
                'Todo formulário tem ainda um campo de elogio e outro de sugestão, e o nome e o telefone são opcionais. O cliente também pode informar o exame, se foi por convênio ou particular e se é paciente ou acompanhante.')),
            ('Ver as respostas e os indicadores', L(
                'Em "Respostas" aparece cada pesquisa recebida, com o resultado por pergunta, o percentual de satisfação (Ótimo e Bom), a segurança do paciente (Sim ou Não), o índice de recomendação (NPS) e a satisfação por exame.',
                'O relatório para a ONA sai em PDF e Excel, com as respostas do QR Code e as impressas marcadas como Impresso.')),
            ('Questionário impresso', L(
                '1. Em "Pesquisa de satisfação (QR Code)", clique em "Imprimir questionário" e imprima as folhas.',
                '2. Entregue ao cliente que não quiser responder pelo celular.',
                '3. Com a folha preenchida, clique em "Lançar questionário impresso", informe a data e marque as mesmas respostas. Pergunta sem marcação fica como "Em branco".',
                '4. A resposta entra nos indicadores e no relatório da ONA marcada como "Impresso".')),
        ]),
        ('Avaliação de fornecedores', [
            ('Avaliar um fornecedor', L(
                '1. Clique em Avaliar no fornecedor.',
                '2. Dê a nota de 1 a 5 em cada critério; o resultado parcial aparece na hora.',
                '3. Se não for aprovado, descreva a ação. Grave a avaliação.',
                'Aprovado a partir de 80% da nota máxima; aprovado com restrições de 60% a 79%; reprovado abaixo de 60%.')),
            ('Relatório para a ONA', L(
                'Use "Relatório PDF" ou Excel no alto da tela: sai a situação de cada fornecedor e as avaliações do período.',
                'Em Critérios, ajuste a lista e os pesos conforme o manual da ONA.')),
        ]),
    ]),
    ('Enfermagem e Segurança', [
        ('Painel da enfermagem', [
            ('Ver a situação das áreas', L(
                'Cada cartão mostra uma área (carrinho, medicamentos, equipamentos, esterilização, radioproteção): verde em dia, vermelho com problema.',
                'A gestão define o titular e o substituto de cada área; os avisos de vencimento vão para eles e, se ficar vencido por 3 dias, também para a gerência.')),
        ]),
        ('Carrinho de emergência', [
            ('Cadastrar e conferir', L(
                '1. Cadastre o carrinho e inclua os itens com quantidade, mínimo, lote e validade.',
                '2. Em Conferência, marque o checklist, confira as quantidades e informe o lacre quebrado e o novo lacre (obrigatório após o uso).',
                '3. A ficha abre pronta para imprimir, com a assinatura de quem conferiu. O carrinho fica vermelho se algo estiver vencido ou abaixo do mínimo.')),
        ]),
        ('Medicamentos e insumos', [
            ('Controlar o estoque', L(
                'Use "Incluir os de medicina nuclear" para cadastrar adenosina, dipiridamol, dobutamina e os demais; depois informe lote, validade e quantidade.',
                'Ao usar um item, a baixa é feita e ele entra na lista de reposição. A temperatura da geladeira é registrada todo dia e fica vermelha fora do limite.')),
        ]),
        ('Equipamentos médicos', [
            ('Teste diário e manutenção', L(
                'Cadastre cada equipamento. O cardioversor exige o teste diário (descarga, bateria, pás e fita), que gera a ficha assinada.',
                'Informe a última e a próxima manutenção e anexe o laudo em PDF. Se o teste não for feito até o horário limite, o responsável recebe um aviso.')),
        ]),
        ('Esterilização', [
            ('Registrar pacotes', L(
                'Registre cada pacote ou lote de autoclave com os indicadores químico e biológico; a validade padrão é de 30 dias.',
                'Imprima a etiqueta com QR para colar no pacote e marque como usado quando acabar.')),
        ]),
        ('Radioproteção da enfermagem', [
            ('Monitor, kit e ocorrências', L(
                'Registre o teste diário do monitor de contaminação, confira o kit de derramamento e anote extravasamentos e reações adversas.',
                'A ocorrência pode ir também para as Ocorrências da Qualidade, sem nome de paciente.')),
        ]),
        ('Profissionais e assinaturas', [
            ('Liberar o módulo', L(
                'Na tela de permissões, ao marcar o módulo para um profissional e salvar, o sistema pede a assinatura (PNG ou JPG) e os dados do conselho profissional.',
                'Se a gestão cancelar, nada é salvo. A assinatura só sai nas fichas que o próprio profissional conferiu.')),
        ]),
    ]),
    ('Estoque', [
        ('Itens', [
            ('Cadastrar um item do estoque', L(
                '1. Clique em "+ Novo item" na tela Estoque.',
                '2. Escolha o tipo (material ou medicamento), informe o nome e a unidade (UN, CX, AMP...).',
                '3. Em "Estoque mínimo", digite a quantidade que não pode faltar. Se já houver saldo, use "Saldo inicial".')),
            ('Dar entrada de mercadoria recebida', L(
                '1. Na linha do item, clique em "Entrada".',
                '2. Informe a quantidade e o valor unitário. Escolha o fornecedor cadastrado ou digite o nome.',
                'Com nota fiscal, lote e validade preenchidos, o histórico do item fica completo. O último valor é atualizado.')),
            ('Dar baixa manual e ajuste de inventário', L(
                '1. Na linha do item, clique em "Saída" e informe a quantidade e o motivo: Uso, Perda, Vencido, Doação ou Outro.',
                'O sistema não deixa o saldo ficar negativo.',
                '2. Para conferir o estoque físico, clique em "Ajuste" e informe a contagem e o motivo.')),
            ('Estoque mínimo e aviso à gerência', L(
                'Quando o saldo chega ao mínimo, a gerência recebe um aviso no contato do sistema, uma vez só.',
                'Depois que o item é reposto acima do mínimo, um novo aviso sai na próxima queda.',
                'Itens abaixo do mínimo aparecem no topo da tela Estoque.')),
        ]),
        ('Movimentações', [
            ('Ver as movimentações e o histórico', L(
                'Em "Movimentações" você filtra por período, item e tipo, e vê o total de entradas e saídas.',
                'Em "Histórico", na linha do item, aparecem os últimos valores pagos e todas as movimentações dele.')),
        ]),
        ('Pedidos', [
            ('Criar e enviar um pedido', L(
                '1. Abra a tela de pedidos do Estoque e clique em "+ Novo pedido". Escolha o fornecedor e as condições de pagamento.',
                '2. Clique em "Adicionar item" e escolha cada item. O valor previsto vem do último valor pago.',
                '3. Clique em "Salvar" para guardar o rascunho. Quando o pedido sair, use "Marcar como enviado".')),
            ('Sugerir pelo mínimo e registrar o recebimento', L(
                'Use "Sugerir itens abaixo do mínimo" para trazer os itens que precisam de reposição, já com a quantidade sugerida.',
                'Ao chegar a entrega, clique em "Registrar recebimento", confira as quantidades e os valores pagos e informe a nota fiscal.',
                'Cada linha recebida dá entrada no estoque. O pedido vira recebido quando tudo chegou; senão fica com recebimento parcial.')),
        ]),
        ('Relatórios do estoque', [
            ('Ver a posição e os relatórios do estoque', L(
                'Em "Relatórios do estoque" você vê o valor em estoque de cada item, os itens abaixo do mínimo, a movimentação do período e as validades a vencer.',
                'Escolha De, Até e o tipo (material ou medicamento) e clique em "Filtrar". "PDF" abre o relatório e "Excel" baixa a planilha.')),
        ]),
        ('Escrituração', [
            ('Ver o livro de movimentação de cada item', L(
                'Em "Escrituração" aparecem, por item, o saldo inicial do período, cada movimento em ordem e o saldo final.',
                'Cada seção mostra se o saldo confere. O PDF e o Excel trazem o termo de abertura, o quadro de validação e as assinaturas.')),
        ]),
        ('Preços dos materiais', [
            ('Estudo de preços dos itens', L(
                'Em "Preços" você vê o último valor pago, a data e o fornecedor da última entrada, o menor, a média e o maior valor de cada item.',
                'Clique no nome do item para ver o quadro por fornecedor, o fornecedor mais barato e o histórico de preços com o gráfico.')),
        ]),
    ]),
    ('Controle de Blindagens', [
        ('Cadastro de blindagem', [
            ('Consultar as blindagens', L(
                'A lista mostra as blindagens cadastradas e o status de cada uma.',
                'O status muda para VENCIDO sozinho quando a validade passa.')),
            ('Os status', L(
                '• VÁLIDO: dentro da validade.',
                '• VENCIDO: validade passou.',
                '• DEVOLUÇÃO SOLICITADA: já pedida em "Solicitar devolução".',
                '• DEVOLVIDA: confirmada em "Confirmar devolução".')),
        ]),
        ('Novo cadastro', [
            ('Cadastrar uma blindagem', L(
                'Preencha todos os campos obrigatórios: Lote, Nota fiscal, Série, Data da nota, CFOP e Validade.',
                'Ao salvar, a blindagem é cadastrada com o status VÁLIDO.')),
        ]),
        ('Solicitar devolução', [
            ('Marcar as vencidas', L(
                '1. Marque as blindagens vencidas que serão devolvidas.',
                '2. Clique para solicitar a devolução.',
                'O status delas passa para DEVOLUÇÃO SOLICITADA.')),
            ('Planilha e documentos de transporte', L(
                'Depois da solicitação, o sistema gera a planilha e os documentos de transporte.',
                'Imprima e envie junto com as blindagens.')),
        ]),
        ('Confirmar devolução', [
            ('Registrar a data da devolução', L(
                '1. Localize a blindagem com devolução solicitada.',
                '2. Informe a data em que foi devolvida e confirme.',
                'Só você decide: o sistema não muda o status sozinho. Depois da confirmação, o status vira DEVOLVIDA.')),
        ]),
    ]),
    ('Outros', [
        ('Atestados e declarações', [
            ('Escolher o documento', L(
                'Escolha entre atestado, declarações e recibo. Todos têm o mesmo layout da planilha antiga.',
                'Também há o pedido de exame, as guias SP/SADT Unimed e o pedido IPSEMG (veja as áreas abaixo).')),
            ('Preencher e imprimir', L(
                '1. Em "Buscar cliente", escolha a pessoa para preencher o nome automaticamente (ou digite os dados).',
                '2. Complete os campos do documento.',
                '3. Gere e imprima. Os dados da clínica (nome, cidade e CNPJ) vêm de "Dados da clínica".')),
            ('Pedido de exame', L(
                '1. Escolha o paciente pelo seletor.',
                '2. Adicione os exames: um por linha, ou pesquise o exame e clique em "Adicionar".',
                '3. Confira a data. Médico, especialidade e CRM já vêm do último pedido.',
                '4. Clique em "Gerar e imprimir".',
                'Os pedidos feitos ficam na lista dos últimos pedidos, para reimprimir.')),
            ('Guia SP/SADT Unimed', L(
                '1. Clique em "Nova guia SP/SADT Unimed" na lista de guias digitadas.',
                '2. Preencha os campos numerados, como no impresso TISS. Escolha o paciente e a carteirinha pelo seletor ou pelo prontuário.',
                '3. Busque o procedimento pela tabela de preços. Os totais são calculados sozinhos.',
                '4. Os dados da clínica ficam lembrados para a próxima guia.',
                '5. Clique em "Salvar e imprimir". Para PDF, use Imprimir e escolha Salvar como PDF.')),
            ('Pedido IPSEMG', L(
                'Clique em "Novo pedido IPSEMG" na lista de guias digitadas.',
                'É o Pedido para Diagnóstico e Tratamento. Preencha os campos de 1 a 21 e clique em "Salvar e imprimir".')),
            ('Guias digitadas', L(
                'A lista mostra as guias e pedidos já digitados.',
                '1. Clique no item para reabrir e corrigir.',
                '2. Para reimprimir, abra o item e use "Salvar e imprimir".',
                '3. Para excluir, use o botão "Excluir" na linha e confirme.')),
        ]),
        ('Pastas', [
            ('Abrir uma pasta da rede', L(
                'A tela tem atalhos para as pastas da rede (laudos, fotos, PDFs).',
                'O botão "Abrir" abre a pasta no Explorador de Arquivos deste computador.')),
            ('Se a pasta não abrir', L(
                'Confira se você está no computador da recepção e se a pasta de rede está acessível.',
                'Se continuar sem abrir, avise a administração.')),
        ]),
    ]),
    ('Banco de Horas', [
        ('Painel de saldos', [
            ('Ler os saldos', L(
                'O painel mostra o saldo de cada funcionário e as pendências do período.',
                'Abra o extrato para conferir as batidas.')),
            ('Corrigir um lançamento', L(
                '1. Abra o extrato do funcionário e escolha o mês.',
                '2. Altere batidas e classificações, sempre com uma justificativa.',
                '3. O saldo do dia e dos meses seguintes é recalculado sozinho.')),
            ('Ajuste de saldo e relatório mensal', L(
                'Ajuste: registre compensações e acertos que não são batidas de ponto.',
                'Relatório mensal: confira os dados e emita o PDF para assinatura. Cada versão emitida fica preservada.')),
        ]),
        ('Funcionários do ponto', [
            ('Cadastrar um funcionário', L(
                '1. Clique para cadastrar.',
                '2. Informe o nome e o Número I igual ao do relógio de ponto.',
                '3. Salve.')),
            ('Jornada de trabalho', L(
                'Cadastre uma vigência para cada mudança de jornada, com as horas de trabalho por dia.',
                'Funcionários inativos mantêm saldos e histórico.')),
            ('Acesso do funcionário', L(
                'Crie o acesso para o funcionário ver o próprio banco de horas em "Minha área".',
                'Ele vê só o dele e os documentos que estão no sistema (sem abrir os arquivos).')),
        ]),
        ('Importar ponto', [
            ('Importar a planilha mensal', L(
                '1. Selecione o arquivo mensal do relógio de ponto (formato XLS).',
                '2. Envie. O original é preservado para consulta.')),
            ('Conferir a importação', L(
                'No histórico de importações, abra a importação para ver o período e os funcionários identificados.',
                'A associação usa o Número I. Funcionários sem cadastro precisam ser cadastrados.')),
        ]),
        ('Escala mensal', [
            ('Planejar o mês', L(
                'A escala mostra a equipe cadastrada, incluindo estagiários, mês a mês.')),
            ('Alterar um dia', L(
                'Quem tem acesso de gestão clica em um dia para preencher o formulário de alteração.',
                'Quem só consulta vê os horários completos abaixo.')),
        ]),
        ('Departamento Pessoal', [
            ('Abrir a pasta do funcionário', L(
                'A lista mostra uma pasta por funcionário. A coluna Pendências mostra os documentos básicos que faltam anexar.')),
            ('Anexar um documento', L(
                '1. Abra a pasta do funcionário.',
                '2. Escolha o tipo e o arquivo (PDF, PNG, JPEG ou WEBP, dentro do limite de tamanho).',
                '3. Para folha de ponto assinada, escolha também o mês.',
                '4. Envie.')),
            ('Folhas de ponto assinadas', L(
                'As cópias assinadas dos relatórios mensais ficam na pasta do funcionário. Abra ou imprima quando precisar.',
                'Documentos arquivados podem ser restaurados com justificativa.')),
        ]),
        ('Histórico do ponto', [
            ('Consultar as alterações', L(
                'Mostra quem alterou os dados do Banco de Horas, quando e por qual motivo, com os valores antigos e novos.',
                'O registro geral de todo o sistema fica em "Registros de atividades".')),
        ]),
        ('Minha área', [
            ('Meu saldo e meus lançamentos', L(
                'Aqui você vê o seu saldo do banco de horas e, mês a mês, as horas previstas, trabalhadas e o saldo de cada dia.',
                'Ajustes feitos pela gerência aparecem em uma lista separada.')),
            ('Meus documentos e dúvidas', L(
                'Você vê apenas a situação dos seus documentos: os arquivos ficam com o Departamento Pessoal.',
                'Em caso de dúvida, use as mensagens e fale com a gerência.')),
        ]),
    ]),
    ('Configuração', [
        ('Minha conta', [
            ('Trocar a sua senha', L(
                '1. Abra "Minha conta" (tema Configuração).',
                '2. Digite a "Senha atual", a "Nova senha" e a confirmação da nova senha.',
                '3. Clique em "Salvar". Use a nova senha no próximo acesso.')),
            ('Escolher o tema e o brilho', L(
                'Em "Minha conta", a seção Aparência tem duas escolhas, que valem em qualquer computador onde você entrar:',
                '• Tema: a cor do sistema (Verde, Azul, Vinho, Roxo, Terracota, Grafite, Oceano ou Índigo). Ela muda a barra lateral, a barra do topo, os botões, as tabelas e o átomo.',
                '• Brilho: o fundo pode ser suave, como um roxo pastel, ou escuro e fechado, para quem prefere trabalhar com o sistema escuro.',
                'Dá para combinar qualquer cor com qualquer brilho. A mudança aparece na hora.')),
            ('Ver o log de atualizações', L(
                'Em "Minha conta", clique em "Log de atualizações" e, na versão desejada, em "Abrir log da atualização": o sistema gera um PDF com saudação, introdução, sumário e todas as novidades daquela versão.')),
            ('Senha provisória', L(
                'Quem recebe um acesso novo entra com uma senha provisória e precisa definir a senha dele antes de usar o sistema.')),
        ]),
        ('Usuários e perfis', [
            ('Quem pode editar quem', L(
                'A ordem é Desenvolvedor, Gestão e Usuários. Cada nível edita os que estão abaixo; o perfil acima aparece como "Protegido".',
                'Para um usuário comum editar outros usuários, a gestão marca o módulo "Gerenciar usuários" no perfil dele. Ele só mexe em usuários comuns e só libera módulos que ele mesmo tem.')),
            ('Criar um usuário', L(
                '1. Clique em novo usuário.',
                '2. Informe o nome de usuário e a senha provisória.',
                '3. Escolha os módulos que ele poderá usar e salve.')),
            ('Escolher os módulos de cada pessoa', L(
                'Marque só o que a pessoa precisa. Módulos desmarcados somem do menu e ficam bloqueados.',
                'Os perfis prontos (Recepção, Agenda, Financeiro, Técnico, Estagiário e outros) marcam vários módulos de uma vez.',
                'O perfil Estagiário lança fichas (atendimentos) e só consulta e imprime a agenda, sem poder alterar nada.',
                'Em Perfil, escolha Usuário (funcionário normal, só com os módulos marcados) ou Administrador (acessa tudo).',
                'Funcionários cadastrados no Banco de Horas recebem acesso automático: o login é o primeiro nome e a senha padrão é 123; o sistema só libera depois que ele trocar a senha.',
                'Administradores veem tudo. Libere para a gerência o módulo "Gerência" para receber os avisos de vencimento.')),
        ]),
        ('Comandos da NucleAI', [
            ('Pedir uma tarefa à NucleAI', L(
                'No chat da NucleAI escreva o que quer, por exemplo: "imprimir a agenda do dia". Ela pergunta se pode fazer (Sim ou Não) e só então faz.',
                'Escreva "comandos" para ver o que você pode pedir. Perguntas começadas por "como", "onde" ou "qual" continuam sendo dúvidas de ajuda.')),
            ('Escolher quem pode usar cada comando', L(
                'Em Administração > Comandos da NucleAI, cada comando tem um risco: baixo (a maioria pode), médio (só quem a gerência escolher) e alto (só a gerência).',
                'Para cada comando escolha Todos, Só os escolhidos (marque as pessoas) ou Ninguém, e clique em Salvar.')),
        ]),
        ('Gasto de tokens (NucleAI)', [
            ('Consultar o uso da IA', L(
                'A tela mostra o consumo de tokens da NucleAI no período escolhido, com totais e gráficos por modelo, usuário, dia e horário.',
                'Use os filtros para analisar períodos e identificar quais modelos e usuários concentram o consumo. Os dados vêm dos pedidos registrados pela IA online.')),
        ]),
        ('NucleAI: IA online', [
            ('Configurar a chave e os modelos', L(
                'Na seção Configurações, a gerência pode informar ou apagar a chave OpenRouter. A chave digitada não é exibida novamente.',
                'Mantenha os modelos ativos na ordem desejada: use as setas para priorizar, ative ou desative cada opção e acrescente modelos pelo identificador OpenRouter.',
                'Se um modelo não responder, a NucleAI tenta os próximos modelos ativos. Use Testar conexão para conferir a configuração.')),
            ('Revisar trocas de modelo', L(
                'A lista de trocas mostra quando e por que a NucleAI mudou de modelo. Filtre por período, modelo ou classificação.',
                'A gerência classifica cada troca como Natural ou Estranha para acompanhar o comportamento. O arquivo de trocas faz parte dos backups.')),
            ('Saúde da NucleAI e tokens', L(
                'A área Saúde resume o funcionamento recente da IA e os sinais de erro ou pausa.',
                'Em Gasto de tokens, escolha o período e consulte os gráficos e totais por modelo, usuário, dia e horário. Use esses dados para acompanhar o consumo.')),
            ('Memória compartilhada como manual', L(
                'A memória reúne orientações que a NucleAI consulta durante as conversas. Selecione o arquivo, edite o texto e salve para compartilhar a orientação com os usuários.',
                'As versões anteriores podem ser consultadas e restauradas pela própria tela. Use a memória para instruções gerais, sem incluir senhas ou chaves.')),
            ('Conversas de teste e treinamento', L(
                'Inicie uma nova conversa de teste para separar ensaios do chat de treinamento. Os treinadores de teste aparecem com nome Teste#XXXX.',
                'Use essas conversas para simular pedidos e revisar respostas antes de liberar mudanças para os usuários. A memória compartilhada funciona como manual de referência.')),
            ('Ilustrar resultados no chat', L(
                'Peça à NucleAI para ilustrar os dados de uma consulta. Ela pode montar uma planilha, gráfico, cartões de informação ou cartão de decisão.',
                'A ilustração segue o acesso do usuário à tela de origem. Quando disponível, use o botão de planilha para baixar os dados.')),
            ('Consultar e remarcar a agenda', L(
                'Peça uma consulta da agenda ou sugira uma remarcação informando paciente, exame e data desejada.',
                'Confira os horários oferecidos. A NucleAI pede confirmação antes de alterar a agenda e segue a permissão da pessoa para a tela.',
                'A alteração fica no Registro de atividades identificada como “Feito com auxílio da NucleAI”. A gerência pode desfazer pela tela de registros.')),
            ('Ler arquivos e preparar relatórios', L(
                'Envie um arquivo compatível no chat e peça à NucleAI para ler ou resumir o conteúdo e preparar um relatório.',
                'Confira as informações geradas antes de usá-las. Arquivos ilegíveis ou fora do formato aceito precisam ser enviados novamente em formato compatível.')),
            ('Treinar a IA no chat Treinador', L(
                'Em Configuração > NucleAI: IA online, a gerência conversa com a NucleAI com inteligência artificial antes de liberá-la para o time.',
                'Escreva como se fosse um usuário e corrija quando ela errar: o que ela aprende fica guardado no TREINAMENTO.txt.',
                'Comandos: /chanceperfil [Nome#0001] troca de treinador; /configperfil mostra e muda o perfil; /limpar apaga a conversa de treino.')),
            ('Liberar ou desativar a IA para o time', L(
                'Quando a gerência decidir que ela está pronta, clique em Liberar, e digite o código mostrado na página para confirmar.',
                'Se notar um comportamento estranho, clique em Desativar: todos voltam à NucleAI automática na hora. Depois, use Voltar ao treino.')),
            ('Escolher o nível de IA de cada usuário', L(
                'Na mesma tela, em Nível de IA de cada usuário, escolha Desligado, Leve, Médio, Alto ou Max para cada pessoa e clique em Salvar níveis.',
                'Leve tira dúvidas; Médio também puxa informações; Alto faz simulações e alterações simples; Max faz tudo. A IA nunca dá acesso a um módulo que a pessoa não tem.')),
        ]),
        ('Saúde do sistema', [
            ('O que a tela mostra', L(
                'Versão do sistema, espaço livre no disco, último backup, tamanho do banco, caixas abertos, vencimentos pendentes e os últimos erros.',
                'É visível para a administração e a gerência.')),
            ('Quando agir', L(
                '• Disco com pouco espaço: libere espaço no computador-base.',
                '• Último backup antigo: faça um backup em "Backup".',
                '• Erros repetidos: avise o suporte com o horário e a tela em que ocorreram.')),
        ]),
        ('Registros de atividades', [
            ('Pesquisar quem fez o quê', L(
                'Todo lançamento, alteração, exclusão, quitação e geração de documento fica gravado com o usuário.',
                'Use os filtros de período, usuário ou texto para localizar uma ação.')),
        ]),
        ('Log de acessos', [
            ('Ver entradas e saídas', L(
                'Mostra os últimos 1000 registros de entrada e saída do sistema, com usuário e horário.')),
        ]),
        ('Backup', [
            ('Fazer uma cópia de segurança', L(
                '1. Abra "Backup".',
                '2. Clique em "Fazer backup agora". Na lista, "Baixar" guarda uma cópia no seu computador.',
                'Cada backup é um arquivo .zip com os dois bancos (sistema.db e anexos.db, onde ficam os PDFs e demais anexos) e um LEIA-ME.txt com o passo a passo para restaurar.',
                'As cópias ficam na pasta de backups mostrada na tela. O sistema também guarda uma cópia antes de cada atualização.',
                'O backup automático (administração e gerência) tem uma janela de horário (Das e Até) e uma frequência (de 15 min a 4 h). Durante a janela, ele faz um backup a cada intervalo; cada backup gera um arquivo novo (o nome traz a data e o horário). Backups com mais de 7 dias são apagados sozinhos, na pasta local e nas pastas de cópia; os 3 mais recentes sempre ficam.',
                'Guarde também uma cópia fora do computador (pendrive, outro computador ou nuvem).')),
            ('Enviar cópias para outras pastas (Drive, pendrive ou rede; só administração e gerência)', L(
                '1. Em "Backup", no quadro "Cópia em outras pastas", digite o caminho completo da pasta (exemplo: G:\\Meu Drive\\Backups ou \\\\servidor\\backups) e clique em "Adicionar pasta".',
                '2. Dá para ter até 5 pastas. Cada uma mostra a sua situação: "Em dia", "Atrasada" ou o erro. Para tirar uma, clique em "Remover"; os arquivos que já estão nela não são apagados.',
                'Os backups são copiados para todas as pastas. O servidor não enxerga o Google Drive nem as unidades do usuário; a cópia para essas pastas é feita pelo ícone da bandeja no computador onde elas existem.',
                'Se uma pasta ficar indisponível (pendrive tirado, rede fora), as outras continuam recebendo as cópias e só a pasta com problema mostra o erro.')),
            ('Restaurar os dados (só administração e gerência)', L(
                'Quem tem só o módulo Backup faz e baixa cópias, mas não vê a restauração. Ela é só para a administração e a gerência.',
                '1. Em "Backup", clique em "Restaurar o último backup" ou em "Restaurar" na linha do arquivo desejado.',
                '2. Confira o arquivo, a data e o conteúdo (sistema + anexos) na tela de confirmação.',
                '3. Digite o código de verificação de 6 números mostrado na tela. Ele vale 5 minutos e só serve uma vez.',
                'Antes de trocar os dados, o sistema guarda o estado atual em uma cópia ANTES-DE-RESTAURAR. Os dois bancos são restaurados juntos; se a segunda parte falhar, a primeira é desfeita.',
                'Arquivos antigos (.db, só do sistema) também podem ser restaurados: nesse caso os anexos atuais são mantidos.')),
            ('Buscar o arquivo em pendrive, disco ou pasta de rede', L(
                'Use quando a cópia está fora da pasta do sistema (só administração e gerência).',
                '1. Em "Backup", clique em "Buscar em outra pasta".',
                '2. Informe o caminho completo da pasta, no computador onde o sistema está instalado (exemplo: E:\\Copias), e clique em "Buscar".',
                '3. Escolha um arquivo da lista, ou use "Restaurar o mais recente desta pasta".',
                '4. Confira os dados e digite o código de verificação, como em qualquer restauração.',
                'A busca é só de leitura e lista apenas arquivos válidos. O sistema lembra a última pasta usada e registra quem buscou e o que restaurou.')),
            ('Avisar os usuários antes de atualizar', L(
                '1. Em "Avisar usuários", informe o prazo em minutos.',
                '2. Clique em "Avisar usuários": todos recebem a mensagem do AVISOS DO SISTEMA e uma faixa de contagem aparece na tela.',
                'Ao fim do prazo o sistema é atualizado e uma tela de espera aparece sozinha.')),
        ]),
        ('Dados da clínica', [
            ('Pasta dos laudos em Word', L(
                'Em "Dados da clínica", preencha "Pasta dos laudos em Word" com o caminho da pasta onde ficam os laudos (exemplo: Z:\\RECEPÇÃO\\LAUDOS).',
                'Em "Lançar atendimento", cada exame anterior do paciente ganha o botão "Abrir laudo (Word)". O sistema procura nessa pasta (e nas subpastas) o arquivo com o nome do paciente, entendendo nomes como "3F RAD - MARIA SILVA.docx" ou "08.03.2023 MARIA SILVA.docx".',
                'Se houver um só arquivo certo, ele abre direto; se houver vários, aparece uma lista para escolher.')),
            ('Informar os dados da clínica', L(
                'Preencha nome, cidade e CNPJ.',
                'Esses dados aparecem em declarações, atestados e recibos e no cabeçalho dos relatórios. Salve ao final.')),
        ]),
        ('Painéis do Início', [
            ('Escolher os painéis do Início', L(
                'Só administração e gerência podem usar esta tela. Em "Configuração > Painéis do Início", marque os painéis que os usuários comuns devem ver e desmarque os que devem ficar ocultos.',
                'Clique em "Salvar". A mensagem "Painéis do Início atualizados." confirma a gravação.',
                'A escolha vale para todos os usuários comuns. Administração e gerência sempre veem todos os painéis.')),
        ]),
        ('Mensagens do WhatsApp', [
            ('Editar os textos enviados', L(
                'Em "Mensagens do WhatsApp" (só a gerência vê esta tela), altere o texto de cada tipo: lembrete do exame, quem faltou (resgate) e convite para reagendar.',
                'Use as marcas entre chaves para o sistema preencher os dados: {saudacao} (Olá, Maria), {nome}, {exame}, {data} e {hora}.',
                'Deixe o campo como estava para voltar ao texto padrão, ou use "Restaurar texto padrão" para todos.')),
        ]),
        ('Medcloud (portal do paciente)', [
            ('Ligar a integração e escolher os convênios', L(
                'Só administração e gerência veem esta tela, em "Configuração > Administração > Medcloud (portal do paciente)".',
                '1. Marque "Função ativada", informe o usuário e a senha da Medcloud e clique em "Testar conexão" (só faz o login, não cadastra ninguém).',
                '2. Marque os convênios que vão para a Medcloud: só os atendimentos desses convênios geram acesso e estudo.',
                '3. Clique em "Salvar". Para trocar o login ou a senha quando mudarem no portal, informe os novos aqui; senha em branco mantém a atual e ela nunca é mostrada de volta.')),
            ('Definir o horário de funcionamento', L(
                'Marque "Funcionar só neste horário", informe "Liga às" e "Desliga às" (exemplo: 05:50 e 19:00) e escolha os dias da semana.',
                'No início do horário o robô abre o navegador e entra na Medcloud sozinho; no fim ele fecha. Atendimentos lançados fora do horário saem sem Medcloud.',
                'Sem a caixa marcada, a função vale o dia todo.')),
            ('O que acontece ao lançar um atendimento', L(
                'O robô cria o acesso do paciente (cadastro sem e-mail, com o CPF ou, sem CPF, o celular) e um estudo novo para o atendimento: modalidade NM, com o nome do exame e a data do atendimento. A cada atendimento novo o robô pega o protocolo da hora (a senha de um acesso antigo pode ter mudado): se o paciente já existe na Medcloud, ele aperta "Reenviar novos dados de login", que gera uma senha nova para o mesmo usuário; se não existe, cadastra. A ficha do atendimento novo traz essa senha. A ficha antiga continua com a senha que foi impressa nela (que pode não valer mais).',
                'Uma tela de carregamento mostra a etapa do robô. As fichas abrem quando o estudo é criado e o protocolo de acesso (usuário, senha e QR Code) sai no final delas.')),
            ('Vínculo do estudo com o paciente (segundo plano)', L(
                'Na Medcloud o estudo e o acesso do paciente são coisas separadas. Por isso, logo depois de criar o estudo (e com a ficha já liberada), o robô compartilha o estudo com o paciente, escolhendo o nome e o ID de acesso dele. Isso acontece em segundo plano e não trava o lançamento.',
                'Se der erro, a tabela "Últimos pedidos do robô" mostra "estudo não vinculado ao paciente" e o motivo, com o botão "Tentar de novo". Enquanto não vincular, o exame não aparece no portal do paciente.')),
            ('Reimprimir uma ficha', L(
                'Reimprimir um atendimento já lançado NÃO cria estudo e não mostra a tela de carregamento: a ficha abre direto, com o protocolo de acesso que o paciente já tem no final.',
                'O estudo só é gerado quando o atendimento é lançado (atendimento novo).')),
            ('Quando o estudo não é criado', L(
                'A tela mostra a mensagem de erro e a ficha não abre sozinha. Escolha: "Tentar de novo" (o protocolo sai junto com o estudo) ou "Imprimir sem o estudo", que imprime as fichas com o protocolo de acesso, mas sem o exame no portal do paciente.',
                'Se o acesso do paciente também não foi criado, a opção vira "Imprimir sem o estudo e sem o protocolo". Em "Medcloud (portal do paciente)" fica a lista dos últimos pedidos, com "Tentar de novo" nos que falharam.')),
        ]),
    ]),
]
