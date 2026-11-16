"""Base de ajuda da NucleAI, parte 1: Início e mensagens, e Lançamentos.

Estrutura: tema = (título, [módulo]); módulo = (título, [(área, instruções)]).
Os títulos de tema e de módulo seguem o menu lateral (um teste confere que nenhuma tela ficou sem ajuda).
"""


def L(*linhas):
    return '\n'.join(linhas)


TEMAS_A = [
    ('Início e mensagens', [
        ('Início', [
            ('O que aparece na tela inicial', L(
                'A tela Início mostra o seu nome, a data de hoje e os atalhos dos módulos que você pode usar.',
                '1. Para voltar a ela de qualquer tela, clique em "Início" no topo do menu lateral.',
                '2. Os módulos que não aparecem no menu não estão liberados para o seu perfil. Peça à gerência ou à administração, que liberam em "Usuários e perfis".')),
            ('Usar o menu lateral', L(
                '1. A caixa de pesquisa no topo do menu filtra as telas enquanto você digita. Aperte a tecla / para ir direto a ela.',
                '2. Clique no nome de um tema (Lançamentos, Agenda, Cadastros...) para recolher ou abrir o grupo. A cada login os temas começam recolhidos; abra só o que precisar.',
                '2.1. O botão « junto ao menu oculta a barra lateral e a tela ocupa o espaço dela. Clique em » para mostrar de novo.',
                '3. No rodapé do menu, o seletor "Tema" troca a cor do sistema. A cor fica salva no seu perfil e vale em qualquer computador.',
                '4. "Sair (logoff)" encerra o seu acesso. Fechar o navegador também encerra.')),
        ]),
        ('Mensagens', [
            ('Enviar e receber mensagens', L(
                '1. Abra "Mensagens" no menu e clique no nome da pessoa na lista.',
                '2. Escreva no campo de baixo. Enter envia; Shift+Enter quebra a linha.',
                '3. Os dois tracinhos ao lado da hora mostram que a pessoa leu.',
                '4. Se a pessoa estiver ausente, ela vê a mensagem assim que abrir o sistema.')),
            ('Contatos do sistema', L(
                'Alguns contatos são automáticos e só enviam avisos (você não consegue responder a eles):',
                '• AVISOS DO SISTEMA: avisos de atualização do sistema (a gerência recebe também os de vencimento de documentos e de caixa).',
                '• LAUDOS DO SISTEMA: avisa todos quando um laudo é liberado. A mensagem tem o botão "Marcar como entregue e ver no mapa" e some sozinha depois de 3 dias.',
                '• NucleAI: sou eu! Apareço aqui quando você clica no botão redondo no canto da tela.')),
            ('Avisos na tela', L(
                'Quando chega uma mensagem nova, aparece um aviso no canto da tela, em qualquer página, e o número no item "Mensagens" do menu.',
                'Para receber avisos do navegador mesmo com a aba escondida, clique em "Ativar avisos do navegador" no alto da tela de Mensagens (aparece quando o navegador permite).')),
        ]),
        ('Sugestão', [
            ('Mandar uma sugestão', L(
                '1. Abra "Suporte ao desenvolvedor", logo abaixo de "Início" no menu, e escolha a aba "Sugestão".',
                '2. Preencha o título, diga em qual tela (se souber) e descreva a ideia.',
                '3. Clique em "Enviar sugestão". Ela aparece em "Seus envios", com a situação: Enviado, Aceito ou Não aceito.',
                'O desenvolvedor lê todas as sugestões e escolhe quais entram na próxima atualização.')),
        ]),
        ('Correção de bug', [
            ('Relatar um problema', L(
                '1. Em "Suporte ao desenvolvedor", escolha a aba "Correção de bug".',
                '2. Preencha o título, a tela, o que aconteceu e, se souber, o passo a passo. Marque o quanto isso atrapalha.',
                '3. Clique em "Enviar correção de bug".',
                'As correções de bugs ficam acima das sugestões para o desenvolvedor e aparecem com aviso em vermelho.')),
        ]),
        ('Formulários recebidos', [
            ('Aceitar ou não aceitar (perfil do desenvolvedor)', L(
                '1. Em "Suporte ao desenvolvedor", abra a aba "Formulários recebidos". Só o perfil DESENVOLVEDOR e a administração a veem.',
                '2. As correções de bugs aparecem primeiro, depois as sugestões. Leia e use os botões grandes: "Sim, aceitar" ou "Não aceitar".',
                '3. O aceito vai para a "Pasta de aceitos". O recusado fica em "Não aceitos", onde dá para aceitar depois ou devolver para análise.',
                'O número vermelho no item do menu mostra quantos formulários esperam decisão.')),
        ]),
        ('Pasta de aceitos', [
            ('Preparar a próxima atualização', L(
                '1. Em "Suporte ao desenvolvedor", abra a aba "Pasta de aceitos".',
                '2. Em cada item, reescreva o "Texto para a atualização" de forma mais didática e clique em "Salvar texto".',
                '3. Clique em "Abrir relatório (PDF)" para ver, dentro do sistema, tudo o que precisa entrar na próxima atualização, ou em "Baixar".',
                '4. Depois de lançar a atualização, use "Marcar todos como aplicados" (ou item por item). Eles saem da lista e vão para "Já aplicados".')),
        ]),
        ('Dados protegidos', [
            ('Excluir respostas da pesquisa', L(
                'Só o desenvolvedor vê esta aba. Ela lista as respostas da pesquisa de satisfação; marque as que quiser e clique em Excluir.',
                'A exclusão é definitiva e não aparece no registro de atividades.')),
        ]),
        ('Dashboard', [
            ('Ler os indicadores', L(
                'O Dashboard reúne gráficos e números dos atendimentos.',
                '1. Use os filtros de período no alto para mudar o que é contado.',
                '2. Passe o mouse sobre os gráficos para ver os valores exatos.',
                '3. Os números dos cartões contam sozinhos ao abrir a tela.')),
            ('Alertas e pendências', L(
                'Os cartões de alerta mostram o que precisa de atenção: contas vencidas, contas a vencer em 7 dias, total de contas em aberto e doses agendadas que já passaram.',
                'Clique no cartão para ir à tela correspondente e resolver a pendência.')),
        ]),
        ('Meus favoritos', [
            ('Montar o painel de favoritos', L(
                'Cada usuário tem o seu painel de atalhos, que só ele vê e que vale em qualquer computador.',
                '1. Abra "Meus favoritos" no menu e clique em "Personalizar".',
                '2. Na lista à direita, marque os módulos que você mais usa. Cada um vira um atalho (widget) na tela.',
                '3. Arraste os atalhos para mudar a posição, ou use os botões ◀ ▶. O botão ⇔ alarga o atalho e a bolinha troca a cor.',
                '4. "Grade" mostra os atalhos lado a lado; "Lista" mostra um embaixo do outro. Clique em "Concluir" quando terminar. Tudo é salvo na hora.')),
        ]),
        ('Lembretes', [
            ('Criar um lembrete em checklist', L(
                'O lembrete é uma lista de itens, cada um com uma caixinha. Ele aparece toda vez que você entra no sistema, até você desativá-lo.',
                '1. Abra "Lembretes" no menu e clique em "Novo lembrete".',
                '2. Informe o título, escreva um item por linha (até 30) e escolha a data de início. Antes dela, o lembrete não aparece.',
                '3. Marque "Zerar as marcações todo dia" para as caixinhas voltarem desmarcadas a cada dia. Clique em "Salvar".')),
            ('Marcar e desativar o lembrete', L(
                '1. Ao entrar no sistema, a janela mostra os seus lembretes. Marque as caixinhas: a marcação é gravada na hora.',
                '2. "Fechar" esconde a janela só por este acesso; ela volta no próximo login.',
                '3. "Desativar este lembrete" pede confirmação e o tira da lista. Para reativar, abra "Lembretes" e use "Ativar".')),
        ]),
        ('NucleAI', [
            ('Painel de estatísticas', L(
                'O Painel mostra, no período escolhido, quantas consultas a NucleAI atendeu, quantas foram resolvidas, a nota média e os chamados à gerência.',
                'Veja também os temas mais consultados, as áreas em que mais usuários dizem "não ajudou" e as dúvidas escritas que a NucleAI não entendeu.',
                'Use as áreas com mais "não ajudou" e as dúvidas não entendidas para decidir o que reescrever em "Conteúdo".')),
            ('Editar e criar conteúdo da ajuda', L(
                '1. Abra a aba "Conteúdo".',
                '2. Para corrigir um texto, clique em Editar na área, altere e salve. "Restaurar original" volta ao texto que veio com o sistema.',
                '3. Para criar uma área nova (ou um módulo ou tema novo), use o formulário "Nova área". Escolha, se quiser, o módulo de permissão exigido: só quem o tem verá o conteúdo.',
                'As mudanças valem na hora para todos os usuários.')),
            ('Configurações da NucleAI', L(
                'Na aba "Configurações" você escolhe: quem recebe os chamados de ajuda; o tempo para apagar conversas abandonadas; o tempo da despedida; e se a NucleAI está ligada ou desligada.',
                'Se ninguém da lista estiver online quando um usuário pedir ajuda, a NucleAI avisa que a gerência responderá assim que possível.')),
            ('Chamados à gerência', L(
                'A aba "Chamados" lista os pedidos de ajuda enviados à gerência: quem pediu, a área, a dúvida, se a pessoa confirmou o assunto e o andamento.',
                'Na mensagem da NucleAI, o botão "Falar com o usuário" abre a conversa com uma pergunta pronta. Quando a pessoa confirma, a NucleAI envia um resumo detalhado da área para você ajudá-la.')),
        ]),
    ]),
    ('Lançamentos', [
        ('Lançar atendimento', [
            ('Passo a passo do lançamento', L(
                '1. Em "Pesquisar cliente", digite o nome, o código ou o CPF e escolha o cliente.',
                '2. Escolha o Exame e a Data.',
                '3. Confira o "Convênio deste atendimento" (vem do cadastro do cliente, mas pode ser trocado só para este atendimento).',
                '4. Informe o Médico solicitante e, se houver, os Medicamentos em uso.',
                '5. Salve. Convênios geram o protocolo de guia; Particular, SMS e Mais Med geram o lançamento no Caixa. As fichas do exame ficam prontas para imprimir.')),
            ('O cliente ainda não está cadastrado', L(
                '1. Abra "Clientes" (tema Cadastros) e clique em novo cliente.',
                '2. Preencha pelo menos nome, CPF, data de nascimento, sexo e convênio (obrigatórios). O telefone é padronizado sozinho.',
                '3. Salve e volte a "Lançar atendimento": o cliente já aparece na pesquisa.')),
            ('Quais fichas são impressas', L(
                'Cada exame imprime as fichas definidas em "Exames e fichas" (tema Cadastros).',
                'Exames digitados que não estão nessa lista imprimem Ficha Geral, SAE e Etiqueta.',
                'Para mudar quais fichas saem, peça a quem tem acesso a "Exames e fichas".')),
            ('Paciente interno do hospital', L(
                '1. Marque a caixa de paciente interno do hospital.',
                '2. Informe o hospital, o setor e o leito.',
                'O SBAR fica pendente no prontuário do paciente.',
                'Todo paciente atendido ganha um número de prontuário, que aparece na mensagem de sucesso.')),
        ]),
        ('Atendimentos', [
            ('Pesquisar e filtrar', L(
                'A lista mostra os atendimentos do filtro (até os 2000 mais recentes).',
                '1. Use os filtros de período, exame, convênio ou texto no alto.',
                '2. Clique em Filtrar. O total aparece abaixo do título.')),
            ('Reimprimir as fichas', L(
                '1. Localize o atendimento na lista.',
                '2. Use o botão de impressão da linha para abrir as fichas.',
                '3. Para trocar quais fichas e quantas cópias imprimir, abra o quadro "Personalizar as fichas a imprimir" (ele fica fechado) e clique em "Atualizar".',
                '4. Imprima pelo navegador (Ctrl+P).')),
            ('Excluir um atendimento', L(
                'Use o botão de exclusão da linha e confirme.',
                'Toda exclusão fica registrada em "Registros de atividades" (quem excluiu e quando). Em caso de dúvida antes de excluir, fale com a gerência.')),
        ]),
        ('Prontuário do paciente', [
            ('Abrir o prontuário', L(
                '1. Abra "Prontuário do paciente" no menu e pesquise por nome, CPF, código ou número do prontuário.',
                '2. Também dá para abrir pelo botão "Prontuário" no cadastro do cliente e na lista de atendimentos.')),
            ('Documentos pendentes', L(
                'A tela inicial do prontuário lista os documentos ainda não concluídos.',
                'Clique em "Abrir" na linha do documento para continuar o preenchimento.')),
            ('Preencher o SBAR', L(
                'O SBAR tem quatro etapas: S, B, A e R.',
                '1. Preencha cada etapa. Clique nas sugestões para preenchê-la mais rápido.',
                '2. Use "Preencher com o padrão" para usar o texto padrão da etapa.',
                '3. Clique em "Salvar rascunho" para guardar sem concluir.',
                '4. Para concluir, informe o nome e o registro do profissional (COREN ou CRM) e clique em "Concluir e imprimir".',
                'Um documento concluído fica só para leitura. A administração pode reabrir para correção.')),
            ('Imprimir e assinar', L(
                'A impressão sai com a logo da clínica e a linha para assinatura.',
                '1. Clique em "Imprimir" no documento.',
                '2. Para preencher à mão, use "Imprimir em branco".',
                'Para guardar em PDF, escolha Salvar como PDF na janela de impressão.')),
            ('Novo documento e histórico', L(
                '1. No prontuário do paciente, escolha o "Tipo de documento" e, se quiser, o atendimento.',
                '2. Clique em "Novo documento".',
                '3. A linha do tempo mostra atendimentos, documentos, exames realizados, doses, pedidos e guias.',
                '4. Para levar o histórico completo, clique em "Imprimir histórico".')),
            ('Documentos sugeridos do atendimento', L(
                'Cada atendimento mostra botões "+ SAE", "+ PNT", "+ MIBI", "+ NEWS" e "+ RADIO", conforme o exame.',
                'Clique no botão para criar o documento já ligado ao atendimento. Ele some depois de criado.',
                'Para qualquer outro tipo, use "+ Documento" no atendimento e escolha o tipo.')),
            ('SAE de enfermagem digital', L(
                'A SAE tem três etapas: Histórico, Durante o exame e Pós-exame.',
                'Cada etapa tem a sua linha de assinatura na impressão.',
                'A ficha SAE impressa continua disponível para quem preferir preencher à mão.')),
            ('Plano terapêutico (PNT) digital', L(
                '1. Responda Sim ou Não em cada pergunta do exame.',
                '2. Quando a resposta for Sim, escreva a justificativa.',
                '3. Ao salvar, a ficha PNT impressa do atendimento sai preenchida: use o botão "Imprimir na ficha original".',
                'No MIBI, as caixas da prescrição médica também aparecem no questionário.')),
            ('Ficha MIBI, NEWS e radiofármaco', L(
                'No escore de cálcio, o total (DA + CX + CD) é calculado sozinho.',
                'No NEWS, a pontuação e o risco são calculados sozinhos a partir dos sinais.',
                'O registro do radiofármaco já vem preenchido com o que foi lançado em "Exames realizados" no mesmo dia.')),
            ('Anamnese, evolução e checklist de segurança', L(
                'A anamnese registra a queixa, os antecedentes, os medicamentos e as alergias do paciente.',
                'A evolução registra o que aconteceu com o paciente, por qualquer categoria da equipe.',
                'O checklist de segurança confere identificação, alergias, preparo e orientações antes e depois do exame.')),
        ]),
        ('Mapa de laudos', [
            ('Entender as colunas', L(
                'Cada exame lançado entra em "Processando imagem". Depois segue para:',
                '• Laudando',
                '• Liberado para entrega',
                '• Entregue',
                'Exames lançados antes do acompanhamento não aparecem no mapa.')),
            ('Mudar a situação de um laudo', L(
                '1. Escolha o período no alto e clique em Mostrar.',
                '2. No cartão do exame, escolha a nova situação na lista.',
                '3. Clique em Mudar.',
                'Ao passar para "Liberado para entrega", todos os funcionários recebem o aviso do LAUDOS DO SISTEMA.')),
            ('Marcar como entregue pela mensagem', L(
                '1. Abra a mensagem de laudo liberado no contato LAUDOS DO SISTEMA.',
                '2. Clique em "Marcar como entregue e ver no mapa".',
                '3. O sistema marca como Entregue, leva você ao laudo na página e faz o cartão piscar em verde.',
                'Se escolher errado, mude a situação de volta no próprio cartão.')),
        ]),
        ('Pendências Medcloud', [
            ('O que aparece aqui', L(
                'Todo atendimento que gerou um estudo na Medcloud entra nesta tela com duas pendências: anexos e laudos.',
                'Cada paciente tem uma quantidade diferente de anexos e de laudos, então a equipe é quem diz quando terminou.',
                'A tela mostra se falta só o anexo, só o laudo ou os dois. A lista de Atendimentos também avisa "Medcloud: pendente".')),
            ('Enviar um anexo ou um laudo', L(
                '1. Na linha do paciente, clique em "Enviar anexo" ou "Enviar laudo".',
                '2. Escolha o arquivo no computador (pode escolher vários). Aceita PDF, Word, Excel, TXT, JPG e PNG, até 25 MB cada.',
                '3. O robô leva o arquivo ao estudo na Medcloud em segundo plano ("Anexar arquivo como anexo": o paciente vê no portal). A situação aparece ao lado do nome do arquivo.',
                'Se der erro, use "Tentar de novo" ou retire o arquivo da fila no X. Com o robô desligado, o arquivo espera na fila.')),
            ('Marcar como enviado ou entregue', L(
                'Mandar o arquivo não tira a pendência. Quando conferir que está tudo certo, clique em "Marcar anexos enviados" ou "Marcar laudos entregues".',
                'Qualquer usuário com acesso a esta tela pode marcar. Se marcou sem querer, use "Reabrir".',
                'Quando os anexos e os laudos estão resolvidos, o paciente sai da lista de pendências (continua em "Todos os estudos").')),
        ]),
        ('Protocolo de guias', [
            ('O que são as guias', L(
                'As guias de convênio são geradas sozinhas pelos atendimentos de convênio. Você não digita guias.',
                'Convênios marcados "vai para o caixa" não geram guia.')),
            ('Consultar e conferir', L(
                '1. Escolha o período.',
                '2. Confira o total de guias mostrado no alto.',
                '3. Use a lista para conferir paciente, exame e convênio antes de enviar ao convênio.')),
        ]),
        ('Lançar exame realizado', [
            ('Dados do paciente', L(
                '1. Em "Pesquisar paciente cadastrado", digite nome, código ou CPF e escolha: nome, nascimento e convênio são preenchidos.',
                '2. Complete, se quiser: idade, peso (kg), altura (m), médico solicitante e CID.')),
            ('Dados do exame e do radiofármaco', L(
                'Informe a data do exame, o exame, o código (registro) e os campos do radiofármaco: Rádio, Eluição, Fármaco, Lote, atividade prescrita e administrada, hora da injeção e hora do exame.',
                'Preencha o Responsável e a Observação, e salve.')),
            ('O que acontece ao salvar', L(
                'O exame entra em "Processando imagem" no Mapa de laudos.',
                'Quando o laudo for liberado, todos os funcionários recebem o aviso.',
                'O sexo do paciente agora vem do cadastro do cliente, não é digitado aqui.')),
        ]),
        ('Exames realizados', [
            ('Consultar e filtrar', L(
                'A tela mostra o controle de realização dos exames do período.',
                '1. Escolha o período e os filtros.',
                '2. Veja o total de exames no alto da tela.')),
            ('Imprimir e exportar', L(
                'Use os botões de impressão e exportação da tela para gerar a lista do período (como na planilha antiga).',
                'A idade do paciente vem da data de nascimento do exame; se a linha não tem nascimento nem idade, o sistema busca no cadastro do paciente (pelo vínculo ou pelo nome, quando só há um cadastro com aquele nome).',
                'Para corrigir um exame, abra a linha e edite.')),
        ]),
        ('Agendar medicamento', [
            ('Preencher o agendamento', L(
                '1. Pesquise o cliente por nome, código ou CPF.',
                '2. Escolha o Medicamento (Iodo, Gálio ou PCI) e o Preparo.',
                '3. Informe a Dose (mCi), a Data da dose e o Médico solicitante.',
                '4. Informe o início da dieta e a suspensão da medicação, e a observação se houver.')),
            ('Ficha e orientações', L(
                'Ao salvar, a ficha de agendamento e as orientações de preparo do iodo (15 ou 30 dias) ficam prontas para imprimir.',
                'Entregue as orientações ao paciente.')),
        ]),
        ('Agenda de medicamentos', [
            ('Consultar as doses', L(
                'A tela lista as doses de Iodo, Gálio e PCI agendadas.',
                'Use os filtros para achar por período, medicamento ou paciente.')),
            ('Mudar o status e imprimir', L(
                'Use as ações da linha para atualizar o status da dose e para imprimir a ficha.',
                'Doses agendadas que já passaram aparecem como alerta no Dashboard.')),
        ]),
    ]),
]
