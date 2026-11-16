"""Frases de exemplo (como o usuário realmente pergunta) para a busca da NucleAI achar a área certa.
Chave: (módulo, área), com os mesmos títulos da base de ajuda; um teste confere que nenhuma chave ficou sem área."""

ALIASES = {
    ('Início', 'Usar o menu lateral'): [
        'como pesquisar uma tela no menu', 'não acho a tela', 'onde fica o menu', 'trocar a cor do sistema', 'mudar o tema de cor',
        'sair do sistema', 'como faço logoff', 'esconder grupo do menu'],
    ('Início', 'O que aparece na tela inicial'): ['voltar para a tela inicial', 'onde fica o início', 'tela principal'],
    ('Mensagens', 'Enviar e receber mensagens'): [
        'como mandar mensagem para um colega', 'enviar recado', 'falar com a gerência', 'conversar com alguém', 'chat da equipe'],
    ('Mensagens', 'Contatos do sistema'): [
        'o que é avisos do sistema', 'por que não consigo responder o avisos do sistema', 'quem é laudos do sistema',
        'não posso responder mensagem do sistema'],
    ('Mensagens', 'Avisos na tela'): ['aviso de mensagem nova', 'ativar notificação do navegador', 'não aparece aviso de mensagem'],
    ('Dashboard', 'Ler os indicadores'): ['ver gráficos', 'quantos atendimentos hoje', 'indicadores do mês'],
    ('Dashboard', 'Alertas e pendências'): ['contas vencidas no painel', 'doses atrasadas', 'alertas do dashboard'],

    ('Lançar atendimento', 'Passo a passo do lançamento'): [
        'como lançar um atendimento', 'lançar exame do paciente', 'registrar atendimento', 'novo atendimento', 'atender um paciente',
        'gerar a guia do paciente', 'lançar atendimento de convênio', 'como faço o lançamento'],
    ('Lançar atendimento', 'O cliente ainda não está cadastrado'): [
        'paciente novo não aparece na pesquisa', 'cliente não encontrado', 'não acho o paciente para lançar', 'paciente sem cadastro'],
    ('Lançar atendimento', 'Quais fichas são impressas'): [
        'quais fichas saem', 'ficha que imprime no atendimento', 'imprimir ficha do exame', 'ficha geral sae etiqueta'],
    ('Atendimentos', 'Pesquisar e filtrar'): [
        'ver atendimentos de um dia', 'procurar um atendimento antigo', 'lista de atendimentos', 'buscar atendimento por convênio'],
    ('Atendimentos', 'Reimprimir as fichas'): [
        'imprimir de novo a ficha', 'perdi a ficha do paciente', 'reimprimir ficha', 'segunda via da ficha'],
    ('Atendimentos', 'Excluir um atendimento'): [
        'lancei errado e quero apagar', 'excluir atendimento', 'apagar um atendimento', 'remover lançamento errado'],
    ('Caixa', 'Ver o que está a receber'): ['pagamentos pendentes do particular', 'lista do caixa', 'quem ainda não pagou'],
    ('Caixa', 'Informar o pagamento'): [
        'registrar pagamento do particular', 'dar baixa no pagamento', 'informar a forma de pagamento', 'colocar nota fiscal do pagamento'],
    ('Movimento de caixa', 'Abrir o caixa do dia'): [
        'como abrir o caixa', 'abrir caixa de manhã', 'começar o dia no caixa', 'fundo de troco', 'não consigo lançar caixa aberto de outro dia'],
    ('Movimento de caixa', 'Receber um pagamento e imprimir a quitação'): [
        'receber pagamento do paciente', 'cobrar o paciente', 'imprimir o comprovante de pagamento', 'quitação do paciente',
        'pagou no pix', 'pagou em dinheiro e preciso dar troco', 'número da nota fiscal obrigatório', 'recibo de pagamento'],
    ('Movimento de caixa', 'Fechar o caixa e assinar o relatório'): [
        'como fechar o caixa', 'fechar o caixa no fim do dia', 'fechamento de caixa', 'relatório do caixa para assinar',
        'esqueci de fechar o caixa', 'aviso de caixa aberto'],
    ('Movimento de caixa', 'Corrigir um recebimento'): [
        'errei o valor do recebimento', 'corrigir pagamento lançado errado', 'alterar recebimento de caixa fechado', 'trocar a forma de pagamento'],
    ('Mapa de laudos', 'Entender as colunas'): [
        'o que significa processando imagem', 'etapas do laudo', 'colunas do mapa de laudos', 'onde vejo os laudos pendentes'],
    ('Mapa de laudos', 'Mudar a situação de um laudo'): [
        'liberar um laudo', 'laudo ficou pronto', 'passar para laudando', 'mudar o status do laudo', 'avisar que o laudo está liberado'],
    ('Mapa de laudos', 'Marcar como entregue pela mensagem'): [
        'entreguei o laudo ao paciente', 'marcar laudo como entregue', 'botão da mensagem do laudo', 'paciente retirou o laudo'],
    ('Protocolo de guias', 'O que são as guias'): ['de onde vêm as guias', 'guia de convênio', 'por que não gerou guia'],
    ('Protocolo de guias', 'Consultar e conferir'): ['ver as guias do mês', 'protocolo de guia por período', 'conferir guias do convênio'],
    ('Lançar exame realizado', 'Dados do paciente'): ['lançar exame realizado paciente', 'peso e altura do paciente', 'cid do exame'],
    ('Lançar exame realizado', 'Dados do exame e do radiofármaco'): [
        'lote do radiofármaco', 'atividade administrada', 'hora da injeção', 'eluição do gerador', 'registrar rádio e fármaco'],
    ('Lançar exame realizado', 'O que acontece ao salvar'): ['por que o exame foi para o mapa de laudos', 'exame entra em processando'],
    ('Exames realizados', 'Consultar e filtrar'): ['ver exames realizados do dia', 'planilha de exames', 'filtrar exame por tipo'],
    ('Exames realizados', 'Imprimir e exportar'): ['exportar exames realizados', 'baixar exames para excel', 'imprimir lista de exames'],
    ('Agendar medicamento', 'Preencher o agendamento'): [
        'agendar dose de iodo', 'marcar dose de gálio', 'agendar pci', 'dieta do iodo', 'suspensão da medicação'],
    ('Agendar medicamento', 'Ficha e orientações'): ['orientações de preparo do iodo', 'ficha de agendamento da dose', 'preparo de 15 ou 30 dias'],
    ('Agenda de medicamentos', 'Consultar as doses'): ['ver doses agendadas', 'lista de doses de iodo'],
    ('Agenda de medicamentos', 'Mudar o status e imprimir'): ['dose foi aplicada', 'mudar status da dose', 'imprimir lista de doses'],

    ('Agenda de exames', 'Criar a agenda do dia'): [
        'como criar a agenda', 'abrir agenda de um exame', 'agenda do dia', 'bloquear um dia na agenda', 'dia sem atendimento', 'feriado na agenda'],
    ('Agenda de exames', 'Preencher a grade de pacientes'): [
        'marcar paciente na agenda', 'agendar paciente', 'colocar paciente no horário', 'copiar agenda para outro dia', 'copiar linha da agenda',
        'observação em vermelho', 'colocar convênio na agenda', 'telefone do paciente na agenda'],
    ('Agenda de exames', 'Status do paciente'): [
        'paciente veio', 'paciente faltou', 'marcar presença', 'marcar falta', 'paciente remarcou', 'mudar status do paciente na agenda'],
    ('Agenda de exames', 'MIBI, lista de espera e impressão'): [
        'senha de autorização do mibi', 'mibi estresse ou repouso', 'protocolo do mibi', 'lista de espera da agenda', 'imprimir a agenda',
        'encaixar paciente na lista de espera'],
    ('Relatórios da agenda', 'Gerar o relatório'): [
        'quantos pacientes faltaram', 'taxa de falta', 'relatório de presença', 'quantos vieram no mês', 'relatório da agenda por convênio'],
    ('Relatórios da agenda', 'Salvar em PDF ou Excel'): ['exportar relatório da agenda', 'baixar agenda em excel'],
    ('Faltas e reagendamento', 'Chamar quem faltou'): [
        'chamar paciente que faltou no whatsapp', 'mensagem para quem faltou', 'convidar a remarcar', 'entrar em contato com quem faltou', 'resgatar paciente'],
    ('Faltas e reagendamento', 'Marcar Reagendado ou Desistiu'): [
        'paciente que faltou quer remarcar', 'reagendar paciente', 'paciente desistiu do exame', 'copiar paciente para outro dia', 'marcar reagendado'],
    ('Financeiro da Agenda', 'Como o valor é calculado'): [
        'repasse do médico', 'quanto repassar ao médico', 'percentual do médico', 'valor do convênio por exame', 'financeiro da agenda'],
    ('Financeiro da Agenda', 'Conferir e exportar'): ['exportar repasse médico', 'relatório de repasse'],

    ('Clientes', 'Cadastrar um novo cliente'): [
        'cadastrar paciente', 'novo cliente', 'cadastro de paciente novo', 'campos obrigatórios do cliente', 'cpf do paciente', 'sexo do paciente',
        'incluir paciente no sistema'],
    ('Clientes', 'Telefone no padrão'): [
        'telefone não é aceito', 'formato do telefone', 'ddd do telefone', 'celular do paciente', 'telefone inválido'],
    ('Clientes', 'Pesquisar e corrigir um cadastro'): [
        'achar um paciente', 'corrigir cadastro do cliente', 'alterar dados do paciente', 'mudar o convênio do paciente', 'procurar cliente pelo cpf'],
    ('Convênios', 'Cadastrar convênio e valores'): ['cadastrar convênio novo', 'valores do convênio', 'preço do mibi por convênio', 'tabela de valores'],
    ('Convênios', 'Convênios que vão para o caixa'): [
        'convênio particular', 'por que não gera guia', 'convênio vai para o caixa', 'sms e mais med', 'pago na clínica'],
    ('Médicos', 'Cadastrar um médico'): ['cadastrar médico solicitante', 'crm do médico', 'novo médico'],
    ('Médicos', 'Cadastro automático'): ['médico digitado no atendimento', 'médico duplicado', 'corrigir nome do médico'],
    ('Exames e fichas', 'Escolher as fichas de cada exame'): [
        'quais fichas imprimem em cada exame', 'mudar ficha do exame', 'ordem de impressão das fichas', 'cadastrar um exame novo'],
    ('Exames e fichas', 'Fichas personalizadas'): [
        'criar um termo próprio', 'criar ficha personalizada', 'ficha com nome do paciente automático', 'documento da clínica personalizado'],
    ('Cores dos exames', 'Ajustar cores e palavras'): ['mudar a cor de um exame', 'cores da planilha', 'tipo do exame colorido'],
    ('Cores dos exames', 'Importar a planilha de exames'): ['importar planilha exames', 'trazer exames da planilha antiga'],

    ('Faturamento', 'Registrar uma fatura'): [
        'lançar nota fiscal', 'registrar fatura do convênio', 'cadastrar nota fiscal', 'valor bruto e líquido', 'tributos da nota'],
    ('Faturamento', 'Quitar e reabrir'): [
        'convênio pagou a fatura', 'convênio pagou a nota fiscal', 'convênio pagou a nota', 'receber do convênio', 'recebimento do convênio',
        'dar baixa na fatura', 'quitar fatura', 'reabrir fatura quitada', 'glosa'],
    ('Faturamento', 'Acompanhar atrasos'): ['faturas atrasadas', 'convênio que não pagou', 'previsão de recebimento vencida'],
    ('Contas a pagar', 'Cadastrar uma conta'): ['lançar despesa', 'cadastrar conta a pagar', 'novo boleto', 'conta do fornecedor'],
    ('Contas a pagar', 'Quitar uma conta'): ['paguei a conta', 'dar baixa em conta', 'quitar conta a pagar', 'banco do pagamento'],
    ('Contas a pagar', 'Vencimentos e alertas'): ['contas que vencem', 'conta vencida', 'contas em aberto'],
    ('Contas a pagar', 'Gerar lote de pagamento'): ['gerar lote de pagamento', 'mandar contas para o banco', 'quitar lote'],
    ('Contas a pagar', 'Quitar ou devolver as contas do lote'): ['quitar as contas do lote', 'devolver conta do lote', 'imprimir lote de pagamento'],
    ('Tabela de preços', 'Criar uma tabela de preços'): ['nova tabela de preços', 'criar tabela de preço', 'preço dos exames'],
    ('Tabela de preços', 'Ferramentas: exames, convênio e reajuste'): ['reajustar preços', 'aumentar preço dos exames', 'copiar valores do convênio'],
    ('Faturamento: relatórios', 'Escolher período e convênio'): ['relatório financeiro por convênio', 'quanto faturou no mês', 'dashboard financeiro'],
    ('Faturamento: relatórios', 'Ler o painel financeiro'): ['recebido e a receber', 'faturamento por convênio', 'prazo médio de recebimento'],
    ('Relatórios de atendimentos', 'Escolher o agrupamento'): [
        'relatório de atendimentos por exame', 'atendimentos por médico', 'atendimentos por usuário', 'atendimentos por convênio'],
    ('Relatórios de atendimentos', 'Salvar ou imprimir'): ['imprimir relatório de atendimentos', 'exportar relatório'],
    ('Relatório de resgate', 'O que o relatório mostra'): ['quantos pacientes resgatei', 'relatório de resgate por usuário', 'resgate de faltas'],
    ('Relatório de resgate', 'PDF e Excel'): ['exportar resgate'],

    ('Documentos', 'Enviar um contrato ou documento'): [
        'guardar um contrato', 'anexar documento', 'upload de documento', 'enviar arquivo', 'subir um pdf'],
    ('Documentos', 'Documento de fiscalização'): [
        'alvará', 'licença sanitária', 'documento com vencimento', 'documento da vigilância', 'cadastrar licença'],
    ('Documentos', 'Avisos de vencimento'): [
        'aviso de documento vencendo', 'quando avisa o vencimento', 'documento vencido', 'quem recebe os avisos de vencimento'],
    ('Relatório ONA', 'Gerar o relatório'): ['relatório da ona', 'indicadores de qualidade', 'acreditação ona'],
    ('Relatório ONA', 'Entender os indicadores'): ['o que é identificação do paciente', 'prazo do laudo 24 horas', 'indicadores ona'],
    ('Relatório ONA', 'PDF e Excel'): ['exportar relatório ona'],
    ('Cadastro de blindagem', 'Consultar as blindagens'): ['ver blindagens vencidas', 'lista de blindagens', 'validade da blindagem'],
    ('Cadastro de blindagem', 'Os status'): ['o que é devolução solicitada', 'status da blindagem', 'blindagem vencida'],
    ('Novo cadastro', 'Cadastrar uma blindagem'): [
        'cadastrar blindagem nova', 'lote e nota fiscal da blindagem', 'cfop da blindagem', 'chegou uma blindagem'],
    ('Solicitar devolução', 'Marcar as vencidas'): ['devolver blindagem vencida', 'solicitar devolução de blindagem', 'blindagens para devolver'],
    ('Solicitar devolução', 'Planilha e documentos de transporte'): ['documento de transporte da blindagem', 'planilha de devolução'],
    ('Confirmar devolução', 'Registrar a data da devolução'): ['blindagem foi devolvida', 'confirmar que devolveu', 'data da devolução'],
    ('Prontuário do paciente', 'Abrir o prontuário'): ['abrir prontuário', 'prontuário do paciente', 'número do prontuário'],
    ('Prontuário do paciente', 'SAE de enfermagem digital'): ['fazer a sae', 'sae digital', 'sistematização de enfermagem'],
    ('Prontuário do paciente', 'Plano terapêutico (PNT) digital'): ['responder o pnt', 'questionário pnt', 'ficha pnt preenchida'],
    ('Prontuário do paciente', 'Preencher o SBAR'):['preencher sbar', 'passagem de plantão', 'concluir sbar'],
    ('Atestados e declarações', 'Pedido de exame'): ['pedido de exame', 'imprimir pedido de exame', 'gerar pedido de exame'],
    ('Atestados e declarações', 'Guia SP/SADT Unimed'): ['guia sp sadt', 'guia unimed', 'guia tiss'],
    ('Atestados e declarações', 'Escolher o documento'):['fazer um atestado', 'declaração de comparecimento', 'recibo avulso'],
    ('Atestados e declarações', 'Preencher e imprimir'): ['imprimir atestado', 'imprimir declaração', 'imprimir recibo', 'paciente pediu declaração'],
    ('Pastas', 'Abrir uma pasta da rede'): ['abrir pasta de laudos', 'pasta de fotos', 'atalho da pasta da rede'],
    ('Pastas', 'Se a pasta não abrir'): ['pasta não abre', 'botão abrir não funciona'],

    ('Painel de saldos', 'Ler os saldos'): ['saldo de horas do funcionário', 'banco de horas', 'ver saldos da equipe'],
    ('Painel de saldos', 'Corrigir um lançamento'): ['corrigir batida de ponto', 'ajustar horário do ponto', 'abonar falta', 'corrigir dia do ponto'],
    ('Painel de saldos', 'Ajuste de saldo e relatório mensal'): ['compensação de horas', 'relatório mensal do ponto', 'pdf do ponto para assinar'],
    ('Funcionários do ponto', 'Cadastrar um funcionário'): ['cadastrar funcionário no ponto', 'número i do relógio', 'novo funcionário'],
    ('Funcionários do ponto', 'Jornada de trabalho'): ['mudar jornada do funcionário', 'jornada de 44 horas', 'horas por dia'],
    ('Funcionários do ponto', 'Acesso do funcionário'): ['dar acesso ao funcionário', 'criar login do funcionário', 'minha área do funcionário'],
    ('Importar ponto', 'Importar a planilha mensal'): ['importar o ponto', 'planilha do relógio de ponto', 'subir arquivo xls do ponto'],
    ('Importar ponto', 'Conferir a importação'): ['funcionário não identificado na importação', 'histórico de importações'],
    ('Escala mensal', 'Planejar o mês'): ['escala de trabalho', 'escala do mês', 'escala dos estagiários'],
    ('Escala mensal', 'Alterar um dia'): ['mudar a escala de um dia', 'trocar plantão', 'alterar escala'],
    ('Departamento Pessoal', 'Abrir a pasta do funcionário'): ['documentos do funcionário', 'pendências de documentos'],
    ('Departamento Pessoal', 'Anexar um documento'): ['anexar documento do funcionário', 'guardar rg do funcionário'],
    ('Departamento Pessoal', 'Folhas de ponto assinadas'): ['guardar folha de ponto assinada', 'folha assinada do funcionário'],
    ('Histórico do ponto', 'Consultar as alterações'): ['quem alterou o ponto', 'histórico de alterações do ponto'],
    ('Minha área', 'Meu saldo e meus lançamentos'): ['ver meu banco de horas', 'meu saldo de horas', 'meus horários'],
    ('Minha área', 'Meus documentos e dúvidas'): ['meus documentos no dp', 'falar com a gerência sobre meu ponto'],

    ('Minha conta', 'Escolher o tema e o brilho'): [
        'mudar a cor do sistema', 'trocar o tema', 'modo escuro', 'sistema escuro', 'deixar o sistema escuro', 'mudar o tema de cor'],
    ('Minha conta', 'Ver o log de atualizações'): ['o que mudou na versão', 'novidades da atualização', 'log de atualizações', 'abrir pdf das atualizações'],
    ('Minha conta', 'Trocar a sua senha'): [
        'trocar a senha', 'mudar minha senha', 'alterar senha', 'esqueci a minha senha', 'senha errada', 'não consigo entrar'],
    ('Minha conta', 'Senha provisória'): ['senha provisória', 'primeiro acesso', 'pediu para trocar a senha', 'senha nova do acesso'],
    ('Usuários e perfis', 'Criar um usuário'): [
        'criar usuário novo', 'cadastrar acesso para funcionário', 'dar acesso ao sistema', 'novo login', 'esqueci a senha de um usuário'],
    ('Usuários e perfis', 'Escolher os módulos de cada pessoa'): [
        'liberar módulo para um usuário', 'usuário não vê uma tela', 'não tenho acesso a uma tela', 'permissões do usuário', 'perfil de acesso',
        'tirar acesso de alguém', 'liberar a gerência'],
    ('Saúde do sistema', 'O que a tela mostra'): ['como está o sistema', 'espaço no disco', 'últimos erros do sistema', 'versão do sistema'],
    ('Saúde do sistema', 'Quando agir'): ['disco cheio', 'sistema com erro', 'o sistema deu erro'],
    ('Registros de atividades', 'Pesquisar quem fez o quê'): [
        'quem apagou', 'quem apagou um atendimento', 'quem excluiu um atendimento', 'quem apagou um cadastro', 'quem alterou',
        'auditoria', 'histórico de ações', 'quem mexeu nesse cadastro', 'quem fez essa alteração'],
    ('NucleAI', 'Painel de estatísticas'): ['estatísticas da nucleai', 'quantas dúvidas a nucleai atendeu', 'nota da nucleai', 'painel da nucleai'],
    ('NucleAI', 'Editar e criar conteúdo da ajuda'): [
        'editar o texto da ajuda', 'criar uma ajuda nova', 'corrigir instruções da nucleai', 'adicionar área de ajuda'],
    ('NucleAI', 'Configurações da NucleAI'): [
        'quem recebe o chamado da nucleai', 'desligar a nucleai', 'tempo da conversa da nucleai', 'configurar a nucleai'],
    ('NucleAI', 'Chamados à gerência'): [
        'pedido de ajuda da nucleai', 'falar com o usuário que pediu ajuda', 'chamados da nucleai', 'botão falar com o usuário'],
    ('Log de acessos', 'Ver entradas e saídas'): ['quem entrou no sistema', 'horário de login', 'acessos dos usuários'],
    ('Backup', 'Fazer uma cópia de segurança'): ['fazer backup', 'como faço backup', 'como fazer backup', 'cópia de segurança', 'baixar o backup',
                                                  'guardar o banco de dados', 'backup em zip'],
    ('Backup', 'Restaurar os dados (só administração e gerência)'): [
        'restaurar os dados', 'voltar o sistema para a cópia de ontem', 'recuperar os dados apagados', 'código de verificação da restauração',
        'desfazer tudo e voltar atrás'],
    ('Backup', 'Buscar o arquivo em pendrive, disco ou pasta de rede'): [
        'restaurar do pendrive', 'buscar em outra pasta', 'cópia em pasta de rede', 'restaurar o mais recente da pasta'],
    ('Dados da clínica', 'Pasta dos laudos em Word'): [
        'pasta dos laudos', 'abrir laudo em word', 'botão abrir laudo', 'onde o sistema procura o laudo do paciente', 'configurar a pasta de laudos'],
    ('Meus favoritos', 'Montar o painel de favoritos'): [
        'favoritos', 'atalhos dos módulos que mais uso', 'personalizar o painel de atalhos', 'widgets', 'mudar a ordem dos atalhos'],
    ('Backup', 'Avisar os usuários antes de atualizar'): [
        'avisar que vai atualizar', 'aviso de atualização', 'o sistema vai ser atualizado', 'atualizar o sistema'],
    ('Dados da clínica', 'Informar os dados da clínica'): ['nome da clínica nos documentos', 'cnpj da clínica', 'cidade nos relatórios'],
    ('Painéis do Início', 'Escolher os painéis do Início'): [
        'esconder painel do início', 'ocultar painéis do dashboard', 'o que o usuário vê no início', 'painéis do dashboard'],
}
