"""Log de atualizações: o que mudou em cada versão do sistema, e o PDF (estilo caderno de escola: saudação, introdução,
sumário e as atualizações numeradas) que o botão "Abrir log da atualização" gera.

Para registrar uma versão nova, acrescente uma entrada em VERSOES (a mais recente primeiro).
Cada atualização é (categoria, título, descrição, [passos ou dicas de uso]).
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

NOVO, MELHORIA, SEGURANCA = 'Novidade', 'Melhoria', 'Segurança'

VERSOES = [
    {'versao': '1.6.0', 'data': '2026-11-15', 'titulo': 'Prontuário, consulta de preços, pedido de exame e destaque de paciente interno', 'itens': [
        (MELHORIA, 'Sistema reorganizado para o celular',
         'No celular e no tablet pequeno, todas as telas ganharam um layout próprio: topo fixo com o nome da tela e botão do menu, menu em gaveta (abre pelo botão ou arrastando da borda '
         'esquerda e fecha tocando fora), cabeçalho mais compacto, campos e botões maiores para o toque (sem o zoom automático do iPhone), filtros em colunas, janelas que sobem de baixo, '
         'barra de botões do módulo que rola de lado e tabelas que viram cartões, com o nome de cada coluna ao lado do valor. Na Agenda, o calendário e as ações ficam numa gaveta '
         'e a grade do dia aparece logo no começo. No computador nada mudou.',
         ['Abra o sistema pelo navegador do celular, no mesmo endereço do computador.',
          'Toque em ☰ no canto superior esquerdo (ou arraste da borda esquerda) para abrir o menu.',
          'Na Agenda, toque na barra com a data para trocar o dia no calendário.']),
        (NOVO, 'Acesso do paciente ao portal Medcloud, impresso com as fichas',
         'Ao lançar um atendimento de um convênio marcado pela gerência, um robô entra na Medcloud, cria o acesso do paciente (cadastro sem e-mail, '
         'usando o CPF, ou o celular quando não há CPF) e, a cada atendimento, o robô também cria um estudo novo para o paciente (modalidade NM, com o nome do exame e a data do atendimento), mesmo que ele já esteja cadastrado. O usuário, a senha e o QR Code só saem em uma página no final das fichas se o estudo for criado. Cada atendimento novo pega o protocolo da hora: se o paciente já existe na Medcloud, o robô aperta "Reenviar novos dados de login" (mesmo usuário, senha nova); se não existe, cadastra. A ficha traz essa senha; o acesso fica salvo no próprio atendimento, então a ficha antiga mantém a senha antiga e '
         'a reimpressão traz sempre a senha daquele atendimento, sem criar estudo nem passar pela tela de carregamento: o estudo só é gerado no lançamento de um atendimento novo. '
         'Depois que o estudo é criado e a ficha já saiu, o robô ainda vincula o estudo ao acesso do paciente (Compartilhar > paciente > Confirmar e enviar) em segundo plano, sem travar o sistema; '
         'se isso falhar, a tela da gerência mostra o erro e permite tentar de novo. A gerência liga e desliga a função, escolhe os convênios e troca o login e a senha da Medcloud em '
         'Administração > Medcloud, que também permite definir um horário de funcionamento (ex.: liga às 05:50 e desliga às 19:00, nos dias marcados). Ao lançar o atendimento, uma tela de carregamento mostra a etapa do robô e só abre as fichas quando o protocolo chega; se a Medcloud falhar ou demorar, as fichas imprimem normalmente e o pedido pode ser repetido.',
         ['Gerência: abra Administração > Medcloud, informe o login e a senha, marque os convênios e ative a função.',
          'Lance o atendimento normalmente; na impressão, o protocolo aparece no final assim que o robô terminar.']),
        (NOVO, 'Pendências Medcloud: anexos e laudos dos estudos',
         'Todo atendimento que gerou um estudo na Medcloud entra na nova tela Lançamentos > Pendências Medcloud com duas pendências: anexos e laudos. '
         'Em cada paciente você clica em "Enviar anexo" ou "Enviar laudo", escolhe o arquivo no computador e o robô leva ao estudo na Medcloud em segundo plano '
         '(Anexos > Anexar novos arquivos > "Anexar arquivo como anexo"; o paciente vê no portal). Enviar o arquivo não tira a pendência: quem confere é a equipe, '
         'que marca "anexos enviados" e "laudos entregues" separadamente (cada paciente tem quantidades diferentes). Qualquer usuário com acesso a Atendimentos ou Laudos '
         'pode enviar e marcar. A lista de Atendimentos mostra "Medcloud: pendente anexos e/ou laudos".',
         ['Abra Lançamentos > Pendências Medcloud.', 'Na linha do paciente, clique em "Enviar anexo" ou "Enviar laudo" e escolha o arquivo.',
          'Quando conferir que está tudo certo, clique em "Marcar anexos enviados" / "Marcar laudos entregues".']),
        (MELHORIA, 'Anexos enviados à Medcloud não ficam mais no banco de anexos; laudos entregues atualizam o mapa de laudos',
         'Depois que o robô leva um anexo ou laudo ao estudo, o arquivo é apagado do banco de anexos do sistema: a Medcloud é quem guarda, então o anexos.db não cresce '
         'com esses arquivos. O nome, o tamanho e a situação continuam na tela. Ao clicar no nome de um arquivo já enviado, o robô busca o arquivo de volta na Medcloud '
         '(pode levar alguns segundos e exige a integração ligada e dentro do horário). Os arquivos que já estavam guardados podem ser liberados pelo administrador no botão '
         '"Liberar espaço" da tela Pendências Medcloud. Também: ao marcar "laudos entregues" na pendência, os exames desse atendimento no mapa de laudos passam para "Entregue".',
         ['Administrador: abra Lançamentos > Pendências Medcloud e, se aparecer o aviso de arquivos já enviados, clique em "Liberar espaço".',
          'Para baixar um arquivo enviado, clique no nome dele e aguarde o robô buscar na Medcloud.']),
        (MELHORIA, 'Páginas mais rápidas: arquivos de estilo e script ficam guardados no navegador',
         'Cada página carregava cerca de 70 arquivos (estilos, scripts e ícones) e o servidor passava toda requisição desses arquivos pelo login e pelo banco, '
         'além de o navegador pedir todos de novo a cada página. Agora os arquivos fixos não passam mais pelo banco, o navegador os guarda (com versão no endereço, então '
         'uma atualização do sistema os renova sozinha) e as páginas são comprimidas na rede. Páginas abrem mais rápido, principalmente com vários computadores ligados.',
         ['Não é preciso fazer nada: a primeira página depois da atualização baixa os arquivos uma vez e as seguintes abrem mais rápido.']),
        (MELHORIA, 'NucleAI: mensagens com negrito, itálico, listas, destaques coloridos e tabelas',
         'As respostas da NucleAI deixaram de mostrar asteriscos soltos: agora o chat desenha a formatação. Dois asteriscos deixam em **negrito**, dois sublinhados em __itálico__, '
         'e há também ~~riscado~~, ++sublinhado++, `código`, títulos (# e ##), listas com "-" e numeradas, citações com ">", divisor "---" e destaques coloridos '
         '("> [!aviso]", "[!dica]", "[!ok]", "[!erro]", "[!info]"). A NucleAI foi ensinada a usar essas marcas e a escolher o bloco visual certo: planilha para listas longas, gráfico para comparações, '
         'cartão de informações para fichas, cartão de decisão Sim/Não antes de alterar algo e cartão de permissão para acessos. Só as mensagens da NucleAI são formatadas: o que as pessoas digitam no chat continua texto puro, '
         'e a prévia da lista de conversas não mostra as marcas.',
         ['Peça à NucleAI uma lista, um resumo ou uma comparação: ela já responde com a formatação.', 'No Fake Chat (aba IA online) você vê o mesmo resultado.']),
        (MELHORIA, 'NucleAI: não inventa mais agendas, contas e números; admite quando não consegue consultar',
         'A NucleAI às vezes respondia sobre agenda, contas, gráficos e indicadores sem consultar o sistema, com números inventados, e copiava marcas internas do histórico '
         '("[ilustração #2…]", "o gráfico está acima") sem ter gerado nada. Agora, se ela responde com dados sem ter chamado uma ferramenta que os traga, o sistema a corrige uma vez '
         'e, se ela insistir, mostra uma resposta honesta em vez do número inventado ("não consegui consultar isso no sistema agora"). Ainda não existe ferramenta para contas a pagar: '
         'a NucleAI passa a dizer isso e a oferecer abrir a tela. O texto enviado à IA também ficou mais enxuto (a lista de ferramentas não é mais repetida no manual) '
         'e ganhou duas regras novas sobre dados do sistema e marcas internas.',
         ['Se uma conversa de teste já tem respostas inventadas, use /limpar no Fake Chat: o histórico também influencia as respostas seguintes.']),
        (MELHORIA, 'Folha do protocolo Medcloud personalizada, com linha para a data de entrega do laudo',
         'A última folha das fichas, com o usuário e a senha do portal Medcloud, ganhou o visual da clínica: logo, dados da Nucleleste (CNPJ, endereço e telefone, quando cadastrados), '
         'dados do paciente e do exame, usuário e senha em destaque, QR Code, passo a passo do acesso e uma linha em branco "Data de entrega do laudo" (dia / mês / ano), '
         'para a recepção preencher à mão na hora de entregar a folha ao paciente.',
         ['Imprima as fichas do atendimento: a folha do protocolo é a última.', 'Escreva à mão a data de entrega do laudo na linha em branco.']),
        (MELHORIA, 'Convênio obrigatório no cadastro do paciente e no lançamento do atendimento',
         'O convênio passou a ser obrigatório: sem ele o cliente não é cadastrado nem alterado, e o atendimento não é lançado '
         '(é o critério para o lançamento na Medcloud). No atendimento, vale o convênio escolhido ali ou, se o campo ficar em branco, o do cadastro do paciente; '
         'se nenhum dos dois existir, o sistema pede para informar. Pacientes antigos sem convênio podem ser atendidos escolhendo o convênio no próprio lançamento.',
         ['No cadastro do paciente, escolha o convênio (campo marcado como obrigatório).',
          'Ao lançar o atendimento, deixe "(convênio do cadastro)" ou escolha outro convênio para aquele atendimento.']),
        (MELHORIA, 'NucleAI: motivo real do limite da IA, sem travar todos os modelos por uma falha',
         'Ao atingir o limite da OpenRouter, a NucleAI agora lê o motivo informado por ela e age de acordo: nos modelos gratuitos (:free) o limite é da conta toda '
         '(20 pedidos por minuto e 50 por dia, até a conta ter comprado US$ 10 em créditos), então o sistema para de percorrer os outros modelos gratuitos — cada tentativa também gastaria o limite — '
         'e avisa o motivo e quando volta a tentar. Se o limite for só de um modelo/provedor, a pausa começa em 1 minuto e dobra a cada falha seguida, até o teto de "Pausa por cota" (antes eram sempre 15 minutos). '
         'Modelo que não existe mais ou não aceita ferramentas (erro 404) é pulado em vez de derrubar a conversa. A aba IA online mostra o último limite informado e o Fake Chat exibe o motivo exato.',
         ['Abra Administração > NucleAI IA > Modelos OpenRouter para ver o último limite informado e quais modelos estão em pausa.',
          'Para mais folga, ative ao menos um modelo pago na lista de modelos.']),
        (MELHORIA, 'Nome da mãe, idade e conselho profissional no prontuário',
         'O SBAR e os demais documentos do prontuário (na tela e na impressão) agora mostram o nome da mãe e a idade do paciente. '
         'Ao preencher o profissional, é possível escolher o conselho: COREN, CRM, CRBM ou CONTER/CRTRs, que sai na linha de assinatura impressa.',
         ['Abra o paciente em Prontuário e entre no SBAR.', 'Em Profissional, escolha o conselho e digite o número do registro.',
          'Ao imprimir, o conselho escolhido aparece na linha de assinatura.']),
        (NOVO, 'Consulta rápida de valores dos exames',
         'Na tela Tabela de preços, o botão Consulta rápida abre uma busca instantânea: digite parte do nome ou o código do exame e veja o valor em cada convênio '
         '(SMS, Particular e MAISMED). Onde o convênio não tem preço para o exame, aparece um traço.',
         ['Abra Tabela de preços e clique em Consulta rápida.', 'Digite parte do nome ou o código do exame; a lista filtra enquanto você digita.']),
        (MELHORIA, 'Pedido de exame redesenhado',
         'O pedido de exame impresso ganhou cabeçalho com a identidade da clínica, dados do paciente e exames em blocos bem distribuídos e o campo de assinatura '
         'fixo no rodapé. No formulário, os últimos valores lançados (médico, registro, convênio, indicação) ficam salvos neste computador, como o usuário na tela de login.',
         ['Abra Documentos e escolha Pedido de exame.', 'Os últimos dados do médico, registro e convênio já vêm preenchidos; confira e emita.']),
        (MELHORIA, 'Selo INTERNO nas fichas impressas',
         'Na Ficha MIBI e na Ficha Geral, quando o paciente do atendimento é marcado como interno, aparece no canto superior um selo grande escrito INTERNO, '
         'com o hospital/setor/leito ao lado, sem atrapalhar os demais dados da ficha.',
         ['Ao lançar o atendimento, marque Paciente interno do hospital e informe o local.', 'Imprima a Ficha MIBI ou a Ficha Geral: o selo INTERNO sai no topo.']),
        (MELHORIA, 'NucleAI: modelos OpenRouter, trocas e acompanhamento de uso',
         'A gerência pode configurar uma chave OpenRouter digitada na tela, ordenar e ativar modelos; se um modelo falhar, a NucleAI tenta o próximo. '
         'As trocas ficam registradas em arquivo, podem ser classificadas como Naturais ou Estranhas e entram no backup. A tela de IA online também mostra a saúde da NucleAI e gráficos de uso e tokens.',
         ['Gerência > NucleAI: IA online > Configurações para chave e modelos.',
          'Na mesma tela, filtre e classifique as trocas e consulte Saúde da NucleAI e Gasto de tokens.']),
        (NOVO, 'NucleAI: ilustrações, agenda e leitura de arquivos',
         'A ferramenta Ilustrar apresenta dados em planilha, gráfico, cartões de informação ou decisão, respeitando a permissão de cada tela. '
         'A NucleAI também consulta a agenda e pode propor remarcações com confirmação; as alterações ficam na auditoria como “Feito com auxílio da NucleAI” e podem ser desfeitas pela gerência. '
         'Ela lê arquivos enviados e prepara relatórios. Testes no chat usam nomes Teste#XXXX, e a memória compartilhada serve como manual.',
         ['No chat, peça uma ilustração, uma consulta ou remarcação da agenda, ou envie um arquivo para leitura.',
          'A gerência acompanha a auditoria e pode desfazer uma alteração auxiliada pela NucleAI.',
          'Na aba IA online, use conversas Teste#XXXX e a memória compartilhada para orientar a NucleAI.']),
    ]},
    {'versao': '1.5.9', 'data': '2026-11-13', 'titulo': 'NucleAI com inteligência artificial (em treinamento)', 'itens': [
        (NOVO, 'NucleAI com inteligência artificial (em treinamento)',
         'A NucleAI ganhou uma versão com inteligência artificial (Google Gemini). Ela entende perguntas escritas com as suas palavras, mostra resultados no próprio chat '
         '(lista da agenda, gráficos, projeções de pacientes e de faltas, acessos de um usuário) com botão para abrir a tela, e faz alterações simples, '
         'sempre pedindo um Sim antes e deixando tudo no Registro de atividades, marcado como feito pelo chat e com o botão Desfazer. '
         'Por enquanto ela está em treinamento: só a gerência conversa com ela, no chat Treinador da aba IA online. Quando a gerência decidir, ela é liberada '
         'para o time com um código de confirmação, e cada usuário usa conforme o nível (Leve, Médio, Alto ou Max). Sem internet, a NucleAI automática '
         'continua respondendo e a IA volta sozinha quando a conexão voltar. O que ela aprende (GEMINI.md e TREINAMENTO.txt) fica guardado e passa por todas as atualizações.',
         ['Gerência > NucleAI: IA online: chat Treinador, níveis, memória, configurações, Liberar e Desativar.',
          'No chat Treinador: /chanceperfil [Nome#0001] troca de treinador; /configperfil mostra e muda o perfil.']),
        (MELHORIA, 'Idade do paciente na agenda',
         'A agenda ganhou a coluna Idade, um campo pequeno ao lado do nome. Ela acompanha o paciente ao remarcar, recortar e copiar, e vai preenchida para o cadastro de cliente aberto pela agenda (que avisa se a data de nascimento der outra idade). O botão Ocultar idade/Mostrar idade, na barra das colunas, esconde ou mostra a coluna; a escolha fica guardada no computador.',
         ['Agenda > barra das colunas > Ocultar idade / Mostrar idade.']),
        (MELHORIA, 'Backup automático: um arquivo novo a cada vez e limpeza de 7 dias',
         'Cada backup automático agora gera um arquivo novo, em vez de substituir o anterior do mesmo dia. Para não acumular, os backups com mais de 7 dias são apagados sozinhos na pasta do computador e em cada pasta de cópia (Google Drive, rede, pendrive). Os 3 backups mais recentes nunca são apagados. As pastas de cópia recebem todos os backups dos últimos 7 dias.',
         ['Configuração > Backup > Backup automático.']),
        (NOVO, 'Contas a pagar: lotes de pagamento',
         'Ao marcar contas e escolher o banco, o sistema cria um lote de pagamento numerado e imprime a lista. As contas do lote saem da lista normal e ficam em "Em pagamento". Quando o lote volta do banco, dá para quitar todas de uma vez ou só as que foram pagas, e devolver as que não foram para a lista normal. O lote guarda o histórico de cada conta (paga ou devolvida) e pode ser impresso de novo.',
         ['Financeiro > Contas a pagar: marque as contas, escolha o banco e clique em Gerar lote de pagamento e imprimir.',
          'Financeiro > Contas a pagar > Lotes de pagamento: abra o lote para quitar ou devolver as contas.']),
        (NOVO, 'Pedido de exame',
         'Em Atestados e declarações há o Pedido de exame, no mesmo modelo do pedido médico em Word: paciente, um exame por linha, data e o médico com especialidade e CRM. O médico, a especialidade e o CRM do último pedido já vêm preenchidos, e os pedidos ficam guardados para reimprimir.',
         ['Outros > Atestados e declarações > Pedido de exame.']),
        (MELHORIA, 'Número das linhas preenchidas na impressão da agenda',
         'A impressão da agenda do dia ganhou a coluna Nº, antes do horário. Ela numera só as linhas com paciente (1, 2, 3...), recomeçando em cada exame, para conferir de relance quantos pacientes estão marcados.',
         ['Agenda > Imprimir.']),
        (NOVO, 'Tabela de preços dos exames',
         'Novo módulo no Financeiro para montar tabelas de preços (por exemplo, Particular 2026): código TUSS, exame, valor e observação. Dá para trazer todos os exames cadastrados, copiar os valores de um convênio, reajustar tudo por porcentagem com arredondamento e duplicar a tabela para a próxima vigência. A tabela sai em PDF com a logo da clínica, para imprimir ou enviar.',
         ['Financeiro > Tabela de preços: Nova tabela, preencha e salve.', 'Na tabela aberta: Ferramentas (exames cadastrados, copiar de convênio, reajuste) e Abrir PDF para imprimir.']),
        (NOVO, 'Guias SP/SADT da Unimed e pedido do IPSEMG',
         'Em Atestados e declarações dá para digitar a guia SP/SADT no padrão TISS da Unimed e o Pedido para Diagnóstico e Tratamento do IPSEMG, no mesmo layout dos impressos. O paciente, a carteirinha, o médico solicitante e o exame vêm do cadastro e do atendimento; os dados da clínica (registro ANS, código na operadora, CNES, prestador) ficam guardados para as próximas guias. As guias ficam salvas para reimprimir e saem em PDF pelo botão Imprimir (Salvar como PDF).',
         ['Outros > Atestados e declarações > Guia SP/SADT Unimed ou Pedido IPSEMG.', 'Outros > Atestados e declarações > Guias digitadas: reimprimir ou excluir.']),
        (NOVO, 'Prontuário do paciente com SBAR digital',
         'Cada paciente atendido ganha um prontuário com número próprio e o histórico de todos os atendimentos, exames realizados, doses, pedidos de exame e documentos. Ao lançar o atendimento, marque Paciente interno do hospital e informe de onde ele veio: o SBAR fica pendente no prontuário para a equipe preencher depois do exame. O SBAR tem as quatro etapas (Situação, Breve histórico, Avaliação e Recomendação), com sugestões prontas para clicar, e sai impresso com a logo da clínica e a linha para a assinatura do profissional. Também dá para imprimir o modelo em branco para preencher à mão.',
         ['Lançamentos > Lançar atendimento: marque Paciente interno do hospital.', 'Lançamentos > Prontuário do paciente: documentos pendentes, busca do paciente e Novo documento.', 'O acesso é liberado pelo administrador no módulo Prontuário do paciente.']),
        (MELHORIA, 'Apostila do sistema no Log de atualizações',
         'A apostila saiu da tela de entrada e agora fica em Minha conta > Log de atualizações, só para quem entrou no sistema. Ela é refeita sozinha a cada atualização e ganhou o capítulo Novidades desta versão, com o que mudou.',
         ['Minha conta > Log de atualizações > Abrir apostila (PDF).']),
        (MELHORIA, 'Agenda do dia impressa só com os pacientes marcados',
         'O PDF da agenda do dia não imprime mais os horários vazios: saem só as linhas com paciente, numeradas, e o exame sem ninguém marcado mostra "Nenhum paciente marcado". Com menos linhas, a letra fica maior e tudo continua cabendo em uma página. No cabeçalho, um quadro de resumo mostra o total de pacientes, a quantidade por exame e a quantidade por convênio.',
         ['Agenda de exames > Imprimir o dia.']),
        (NOVO, 'Campanhas de saúde do mês',
         'O sistema se veste com a campanha de saúde de cada mês, como Janeiro Branco, Outubro Rosa e Novembro Azul: aparece o laço na cor da campanha no menu, na tela de entrada e no Início, com uma mensagem de conscientização e os exames da clínica ligados ao tema. A troca é automática no primeiro dia do mês. As cores do sistema continuam as mesmas. A gerência pode desligar.',
         ['Gerência > Painéis do Início > Campanhas de saúde do mês.']),
        (NOVO, 'Prontuário: SAE, plano terapêutico, ficha MIBI, NEWS e outros documentos digitais',
         'Além do SBAR, o prontuário tem a SAE de enfermagem (as três etapas, cada uma com a linha de assinatura), o plano terapêutico (PNT) com o questionário digital do exame, a ficha MIBI, o escore NEWS com a pontuação e o risco calculados sozinhos, o registro de administração do radiofármaco, a anamnese, a evolução e o checklist de segurança do paciente. As fichas impressas continuam como antes: dá para preencher à mão ou no sistema. O PNT preenchido no prontuário também preenche a ficha PNT impressa do atendimento. Cada atendimento mostra botões para criar os documentos sugeridos para o exame.',
         ['Lançamentos > Prontuário do paciente > atendimento > botões dos documentos sugeridos.']),
        (MELHORIA, 'O sistema abre direto na agenda',
         'Ao entrar no sistema, ou ao abrir o endereço dele no navegador, quem tem acesso à agenda já cai na agenda de exames. Quem não usa a agenda continua começando pelo Início. O Início segue no menu, como antes.',
         ['Menu > Início, para ver o painel inicial.']),
        (NOVO, 'Lembretes em checklist de volta',
         'Os lembretes em checklist voltaram ao sistema. Crie lembretes com uma lista de itens, cada um com uma caixinha; eles aparecem ao entrar no sistema até você desativá-los. A gestão pode criar lembretes para todos, e as marcações são de cada pessoa.',
         ['Menu > Lembretes.']),
        (NOVO, 'Contas a pagar recorrentes de volta',
         'As contas recorrentes voltaram. Ao cadastrar uma conta, marque "Conta recorrente" e escolha o dia do vencimento: todo mês a conta entra em aberto nesse dia, sem precisar lançar de novo. A tela Contas recorrentes permite editar, pausar, reativar e excluir o cadastro; as contas já lançadas continuam na lista e podem entrar nos lotes de pagamento normalmente.',
         ['Contas a pagar > Contas recorrentes.']),
        (NOVO, 'Estoque de materiais e medicamentos de volta',
         'O estoque voltou ao sistema: cadastro de materiais e medicamentos, entradas e saídas, pedidos aos fornecedores com recebimento, preços dos materiais, histórico e relatórios em PDF.',
         ['Menu > Estoque.']),
    ]},
    {'versao': '1.5.8','data': '2026-11-12', 'titulo': 'Apostila do sistema em PDF e outras melhorias', 'itens': [
        (NOVO, 'Apostila do sistema em PDF na tela de login',
         'Na tela de entrada há o link "Apostila do sistema (PDF)". Ele abre uma apostila completa, com capa, sumário com páginas e um capítulo para cada área do menu, com o passo a passo de todas as funcionalidades. Não é preciso entrar no sistema para abrir. Quando a administração edita a ajuda da NucleAI, a apostila acompanha.',
         ['Tela de entrada > Apostila do sistema (PDF).']),
        (MELHORIA, 'Pesquisa de satisfação no padrão da ONA',
         'As perguntas foram trocadas por 13 perguntas que cobrem o que a ONA avalia: agendamento, recepção, tempo de espera, orientações sobre o preparo e a radiação, privacidade, cuidado da equipe, limpeza, conforto, entrega do laudo e avaliação geral. '
         'Há também duas perguntas de Sim ou Não sobre segurança do paciente (confirmação do nome e da data de nascimento e orientações depois do exame) e uma nota de 0 a 10 de recomendação (NPS). '
         'O cliente pode informar o exame, se foi por convênio ou particular e se é paciente ou acompanhante. As respostas antigas continuam guardadas.',
         ['Qualidade > Pesquisa de satisfação (QR Code): escolha o tipo de cada pergunta.',
          'Respostas e indicadores: veja a segurança do paciente, o índice de recomendação e a satisfação por exame.']),
        (NOVO, 'Questionário de satisfação impresso',
         'Para o cliente que não quer responder pelo celular, a pesquisa pode ser impressa em uma folha A4 e depois lançada no sistema pela recepção. As respostas lançadas entram nos indicadores e no relatório da ONA marcadas como Impresso.',
         ['Qualidade > Pesquisa de satisfação (QR Code) > Imprimir questionário.',
          'Qualidade > Pesquisa de satisfação (QR Code) > Lançar questionário impresso.']),
        (MELHORIA, 'Financeiro da agenda: Veio e Retorno, com a numeração real',
         'O financeiro da agenda passa a contar quem está com status Veio ou Retorno. Quem foi remarcado e veio na nova data conta uma vez só, na nova data. '
         'A coluna Nº é a contagem das linhas que estão no relatório (1, 2, 3...), sem buracos quando alguma linha da agenda foi excluída, na tela, no PDF e no Excel.',
         ['Agenda > Financeiro da agenda.']),
        (MELHORIA, 'Agenda: resumo do dia mais simples',
         'Os balões do resumo mostram só chegaram, atendidos, faltaram e reagendados, além dos horários livres. "Atendidos" soma quem veio e quem está como Retorno; o balão de retornos e o de desistências saíram.',
         ['Agenda de exames > balões do resumo de cada exame.']),
        (MELHORIA, 'Reagendamento registrado no histórico da linha',
         'A linha reagendada não mostra mais o texto "resgatou". Quem reagendou fica no histórico da linha, como "Reagendado por" seguido do login. Nos relatórios, a coluna passou a se chamar "Quando reagendou".',
         ['Agenda de exames > botão de histórico da linha.']),
        (MELHORIA, 'Agenda: escolha do exame com destaque',
         'A caixa que escolhe qual exame aparecer na grade ganhou título, ícone e uma dica curta: escolha um exame para ver só a grade dele, ou Todos para o dia inteiro.',
         ['Agenda de exames > caixa Exame, acima da grade.']),
        (NOVO, 'Backup automático ao longo do dia',
         'O backup automático agora roda dentro de um horário (por exemplo, das 08:00 às 18:00) e na frequência escolhida (15 min, 30 min, 1 h, 2 h, 3 h ou 4 h). '
         'No mesmo dia ele não cria um arquivo novo a cada vez: substitui o anterior, e o nome do arquivo traz o horário. No dia seguinte começa um arquivo novo. Os backups feitos à mão não são apagados.',
         ['Configuração > Backup > Backup automático: marque Ligado, escolha Das, Até e a Frequência e salve.']),
        (NOVO, 'Backup em mais de uma pasta ao mesmo tempo',
         'É possível escolher até 5 pastas de destino (por exemplo, Google Drive, pendrive e pasta de rede). Os backups são copiados para todas, e cada pasta mostra se está em dia ou o erro da última tentativa. '
         'O servidor não enxerga o Google Drive nem as unidades do usuário: a cópia para essas pastas é feita pelo ícone da bandeja no computador onde elas existem.',
         ['Configuração > Backup > Adicionar pasta.', 'Para tirar uma pasta da lista, use Remover na linha dela.']),
        (NOVO, 'Histórico do paciente',
         'Cada cliente tem um relatório com todos os atendimentos: data, exame e médico solicitante, com filtro de período e PDF para imprimir.',
         ['Cadastros > Clientes > botão Histórico na linha do cliente ou no cadastro.']),
        (NOVO, 'Painéis do Início escolhidos pela gerência',
         'A gerência escolhe quais painéis do Início os usuários veem (números do período, gráficos, alertas, últimos atendimentos e próximas doses). A escolha vale para todos os usuários; administrador e gerência sempre veem tudo.',
         ['Configuração > Painéis do Início: marque o que deve aparecer e salve.']),
        (MELHORIA, 'Login lembra o usuário',
         'A tela de entrada já vem com o último usuário que entrou naquele computador e sugere os outros que já entraram nele. Só entram nomes de usuários válidos, depois de um login certo. A senha nunca é guardada.',
         ['Tela de entrada > campo Usuário: comece a digitar ou escolha da lista.']),
        (MELHORIA, 'Perfil epidemiológico mais completo',
         'O perfil dos pacientes (tela e dossiê da ONA) ganhou diagnósticos por capítulo da CID-10, IMC dos adultos (com peso e altura do exame), idade média por exame, exames por sexo e procedência: mesma cidade da clínica ou outras cidades. '
         'O sexo continua obrigatório no cadastro do cliente.',
         ['Qualidade > Perfil epidemiológico.', 'Relatório ONA > PDF do dossiê, seção 5.']),
    ]},
    {'versao': '1.5.7','data': '2026-11-03', 'titulo': 'Agenda: status do remarcado para a gerência e retorno no relatório', 'itens': [
        (MELHORIA, 'Agenda: gerência pode alterar o status de quem foi remarcado',
         'A linha remarcada para outra data, antes travada para todos, agora pode ter o status alterado pelo administrador e pela gerência. '
         'Para os demais usuários continua travada. A nova marcação não é alterada automaticamente.',
         ['Agenda de exames > coluna Status da linha remarcada.']),
        (MELHORIA, 'Relatório da agenda: retorno conta como veio',
         'Na tela, no PDF e no Excel, quem está com status Retorno passa a contar em Vieram e na taxa de falta. A coluna Retornos continua mostrando quantos são. Quem foi remarcado e veio na nova data conta uma vez só, na nova data.',
         ['Agenda de exames > Relatórios.']),
        (MELHORIA, 'Recibo com a logo da Nucleleste',
         'O modelo do recibo agora sai com a logo da Nucleleste nas duas vias, no lugar da imagem antiga, que trazia outra logo, endereço e telefones.',
         ['Atestados e declarações > Recibo.']),
    ]},
    {'versao': '1.5.4', 'data': '2026-10-25', 'titulo': 'Financeiro da agenda: impressão em uma folha e dias alternados', 'itens': [
        (MELHORIA, 'Financeiro da agenda: relatório em uma única folha A4',
         'O PDF do financeiro da agenda ficou compacto e cabe em uma única folha A4, com as tabelas por convênio e por paciente. '
         'O botão Imprimir gera a versão pronta para papel.',
         []),
        (NOVO, 'Financeiro da agenda: filtro por dias da semana',
         'É possível mostrar só alguns dias da semana do período (ex.: só terças e sextas) na tela, no PDF e no Excel.',
         ['Agenda de exames > Financeiro > Dias da semana.']),
        (NOVO, 'Financeiro da agenda: caixinhas de etapa do MIBI',
         'Para os exames MIBI, as etapas Repouso, Estresse e Protocolo aparecem em caixinhas marcadas na tela, no PDF e no Excel.',
         ['Agenda de exames > Financeiro.']),
    ]},
    {'versao': '1.5.3','data': '2026-10-25', 'titulo': 'Agenda compacta, escala com horários e ocorrência de ponto', 'itens': [
        (MELHORIA, 'Agenda compacta e menu de áreas',
         'Os atalhos das áreas ficam em um menu com ícones e navegação pelo teclado. A formatação pode ser mostrada ou ocultada, com a escolha lembrada neste navegador. '
         'Os cabeçalhos ocupam menos altura e, no computador, os painéis da agenda usam o espaço disponível na tela, com rolagem interna dos horários.',
         ['Agenda de exames > Áreas da agenda / Mostrar formatação.']),
        (MELHORIA, 'Previsão do laudo junto aos dados do exame',
         'Nas fichas Geral e MIBI, a previsão de entrega fica na linha após o exame, dentro do corpo da ficha, sem aumentar sua altura. '
         'Nas fichas personalizadas, acompanha o campo do exame ou os dados do paciente.', []),
        (SEGURANCA, 'Sessão única por usuário',
         'Ao entrar em outro computador ou navegador, o acesso anterior é encerrado com um aviso claro. As consultas automáticas também levam a pessoa de volta ao login.',
         ['Entre novamente no computador em que deseja continuar trabalhando.']),
        (NOVO, 'Contato Agenda: avisos de agendamento de MIBI',
         'Os usuários que veem os avisos da gerência recebem paciente, data, horário e etapa pelo contato Agenda nas Mensagens. O aviso vem ativado e pode ser desligado nas Configurações. Falhas no aviso são registradas e preservam o agendamento.',
         ['Mensagens > Agenda.', 'Configurações > Avisar agendamentos de MIBI.']),
        (NOVO, 'Grupos de transmissão da gestão',
         'A gestão pode criar grupos, editar seus membros e excluí-los nas Mensagens, escolhendo pessoas com acesso à Agenda. Um envio entrega mensagens individuais da gestão; as respostas ficam na conversa de cada pessoa.',
         ['Mensagens > Grupos de transmissão > Criar grupo.', 'Escolha um grupo e use Enviar para todos.']),
        (SEGURANCA, 'Ponto: lançamentos do funcionário respeitam o vínculo',
         'A Minha área e as consultas e cópias de relatórios acessíveis ao funcionário ocultam os dias fora do vínculo no servidor. '
         'Dias anteriores ao saldo inicial, mas dentro do vínculo, continuam disponíveis. A gerência mantém a consulta completa.',
         ['Banco de Horas > Minha área > Lançamentos do mês.']),
        (MELHORIA, 'Escala com entrada, saída, intervalo e carga diária',
         'A escala mostra os horários e a carga líquida de cada dia, descontando o intervalo já cadastrado. '
         'O PDF recebeu cabeçalho com a logo da clínica, tabelas com linhas alternadas, legenda e total planejado por colaborador.',
         ['Banco de Horas > Escala mensal > Baixar escala em PDF.']),
        (NOVO, 'Ocorrência de ponto com acompanhamento e análise da gerência',
         'O funcionário informa esquecimentos de batida, batidas erradas e outros problemas pela Minha área e acompanha o status. '
         'As pendências aparecem no painel e no extrato para aprovação, correção ou recusa com justificativa e auditoria. '
         'Ocorrências pendentes impedem a emissão definitiva do relatório de ponto.',
         ['Minha área > Ocorrência de ponto.', 'Banco de Horas > Painel de saldos > Ocorrências de ponto pendentes.']),
    ]},
    {'versao': '1.5.2', 'data': '2026-10-21', 'titulo': 'Dossiê ONA completo em PDF', 'itens': [
        (MELHORIA, 'Agenda: 6ª coluna personalizável (Etapa no MIBI, Exame nos demais) e coluna Observação/Senha',
         'A coluna que se chamava "Senha de autorização" agora muda conforme a agenda. Ao criar uma agenda de MIBI, aparece a escolha da etapa (Repouso ou Estresse): a coluna passa a se chamar "Etapa" e a escolha já vem preenchida em todas as linhas, '
         'e em cada linha ainda dá para trocar para Estresse, Repouso ou Protocolo. Nos outros exames o título vem como "Exame" (pode ser alterado ao criar) e o exame vinculado à agenda já vem em todas as linhas, editável. '
         'Linhas acrescentadas depois e agendas copiadas para outro dia seguem o mesmo padrão (no MIBI a etapa se inverte na cópia). A coluna Observação passou a se chamar "Observação/Senha", pois a senha da operadora agora é anotada nela.',
         ['Agenda de exames > Criar agenda > Etapa do MIBI / Título da 6ª coluna.']),
        (MELHORIA, 'Agenda: o status Remarcou virou Retorno, na cor do Veio',
         'No exame de duas etapas (MIBI), o paciente que vem num dia e volta em outro não tinha faltado, mas aparecia como "Remarcou", parecendo ausência. O status agora se chama "Retorno" e fica na cor do Veio. '
         'Ao escolher Retorno (ou o botão de seta da linha), o sistema pergunta o dia e o horário do retorno, marca o paciente lá e ele aparece no outro dia; a linha de origem continua como Retorno e fica travada para outras pessoas. '
         'Quem estava como Remarcou passou a Retorno. Nos relatórios, nos balões e no PDF da agenda a contagem virou "retornos", e Repouso e Estresse do mesmo paciente continuam contando como um exame só.',
         ['Agenda de exames > status Retorno.']),
        (NOVO, 'Dossiê ONA: relatório completo em PDF, com capa, sumário e contracapa',
         'Ao pedir o PDF do Relatório ONA, o sistema agora gera um documento profissional com a capa e a logo da clínica, o sumário (o índice, com a página de cada assunto), '
         'uma seção para cada tema e a contracapa. Reúne os indicadores ONA, a produção de exames, o perfil epidemiológico dos pacientes, a agenda e o comparecimento, '
         'os indicadores da qualidade com metas, a satisfação do cliente, a gestão da qualidade (problemas, ações, riscos e ocorrências) e a segurança do paciente (enfermagem). '
         'Cada gráfico traz um quadro "Como ler este gráfico" que explica o que ele representa, e cada seção termina com uma "Leitura rápida". '
         'No fim há o quadro de validação para as assinaturas. O visual segue as cores do sistema, no mesmo estilo do registro de atualizações, e o PDF tem marcadores para navegar pelo painel do leitor. '
         'O resumo de uma página continua disponível como "PDF resumido".',
         ['Relatório ONA > PDF completo.', 'Relatório ONA > PDF resumido.']),
    ]},
    {'versao': '1.5.1', 'data': '2026-10-20', 'titulo': 'Enfermagem e Segurança, Qualidade com modelos prontos, Suporte renovado, Faturamento em etapas e backup automático', 'itens': [
        (NOVO, 'Enfermagem e Segurança: carrinho, medicamentos, equipamentos, esterilização e radioproteção',
         'Novo módulo para os profissionais de enfermagem, com cinco áreas e um painel que mostra em vermelho o que precisa de atenção. Carrinho de emergência: itens com quantidade mínima, '
         'lote e validade, número do lacre (o quebrado e o novo) e conferência diária, semanal ou após o uso em formato de checklist; a ficha sai pronta para imprimir. '
         'Medicamentos e insumos: adenosina, dipiridamol, dobutamina, regadenoson, aminofilina, atropina, nitroglicerina, glicose, soro e adrenalina já podem ser incluídos de uma vez, '
         'com baixa no uso e lista de reposição, e a temperatura da geladeira é registrada todo dia com limite configurável. Equipamentos: teste diário do cardioversor (carga, bateria, '
         'pás e fita), manutenção e calibração com o laudo em PDF, e aviso se o teste não for feito até o horário escolhido. Esterilização: cada pacote ou lote de autoclave com '
         'indicadores químico e biológico e etiqueta com QR. Radioproteção: teste do monitor de contaminação, kit de derramamento e registro de extravasamentos e reações adversas. '
         'Cada área tem um responsável titular e um substituto, que recebem os avisos de validade (60, 30, 15, 7, 1 e 0 dias e vencido) no contato AVISOS DO SISTEMA; se o item ficar '
         'vencido por 3 dias sem providência, o aviso também chega à gerência. A assinatura do profissional sai sobre a linha, com nome, cargo e conselho, só nas fichas que ele mesmo '
         'registrou, e cada impressão fica no registro de atividades.',
         ['Menu > Enfermagem e Segurança.', 'Administração > Usuários: ao marcar o módulo para um profissional, o sistema pede a assinatura, o cargo e o conselho antes de salvar.',
          'A permissão só vale depois que a assinatura for importada; cancelar não salva nada.']),
        (NOVO, 'Suporte ao desenvolvedor: não aceitar abre a conversa com cartão em cápsulas, temas e relatório de pendências',
         'Ao clicar em "Não aceitar", o desenvolvedor vai direto para a conversa com quem enviou, nas Mensagens, onde o sistema coloca um cartão especial em cápsulas com o que a pessoa '
         'escreveu entre aspas, o nome, a data e o tema. Esse cartão só o sistema cria, então ninguém consegue imitá-lo escrevendo texto; depois dele o desenvolvedor explica o motivo '
         'normalmente. As sugestões e os bugs agora têm tema (Segurança, Organização, Desempenho e outros) e o envio guarda os dados do aparelho, do navegador, do endereço e das últimas '
         'ações da pessoa, para conferir com os erros que o sistema registra. Na Pasta de aceitos, o relatório em PDF das pendências saiu reformulado, com capa, sumário, contracapa e os itens '
         'separados por tema, com os bugs antes das sugestões.',
         ['Suporte ao desenvolvedor > Formulários recebidos > Não aceitar.', 'Suporte ao desenvolvedor > Pasta de aceitos > Relatório em PDF.']),
        (NOVO, 'Agenda: pendência da segunda etapa do MIBI e aviso na observação',
         'Quem tem só o Repouso ou só o Estresse marcado passa a constar como pendente no relatório da agenda, com a etapa que falta, o contato e um botão para abrir a agenda; quando a segunda etapa é marcada, o paciente '
         'aparece como concluído. Ao remarcar uma etapa, a observação do novo horário mostra quando é a outra etapa (ou que ainda não foi agendada) e continua editável.', ['Agenda de exames > Relatórios > Exames de duas etapas.']),
        (MELHORIA, 'Agenda: MIBI em duas etapas conta um exame só no relatório por período',
         'Quando o mesmo paciente aparece no Repouso e no Estresse (até 30 dias de diferença), o relatório da agenda por período conta um único exame; o Protocolo continua sendo um exame por si. '
         'O relatório diário e o resumo de cada dia seguem mostrando cada linha da agenda, e o financeiro da agenda continua separando Estresse e Repouso.', ['Agenda de exames > Relatórios.']),
        (MELHORIA, 'Agenda: número em coluna própria, copiar com pergunta, larguras padrão e celular reorganizado',
         'O número das linhas ganhou uma coluna só dele, que não atrapalha mais o horário, com botões Nº− e Nº+ para aumentar ou diminuir o tamanho. '
         'Em "Copiar para outro dia" o sistema pergunta se deseja apagar a data atual e colar na nova: Sim apaga o dia copiado e leva os dados para a nova data; Não grava nas duas datas. '
         'Na agenda MIBI, os pacientes copiados trocam Repouso por Estresse e Estresse por Repouso. '
         'O novo botão "Tornar padrão" guarda a largura das colunas que você ajustou: a agenda volta assim sempre que for aberta; sem clicar, a mudança vale só até recarregar ("Largura original" desfaz). '
         'Quem foi remarcado para outra data fica com o status travado para qualquer usuário; só a nova marcação muda de status. '
         'No celular cada horário virou um cartão com os campos empilhados e legíveis, no lugar das colunas estreitas.',
         ['Agenda de exames > Número: Nº− / Nº+.', 'Agenda de exames > Copiar para outro dia.', 'Agenda de exames > Colunas: Tornar padrão.']),
        (NOVO, 'Financeiro da agenda por etapa do MIBI',
         'Ao escolher o exame MIBI no Financeiro da agenda aparecem as opções Estresse, Repouso e Protocolo (pode marcar várias). O relatório, o PDF e o Excel trazem só as etapas marcadas, entre as datas escolhidas.',
         ['Agenda de exames > Financeiro da agenda > Etapas do MIBI.']),
        (NOVO, 'Resumo semanal das contas a vencer, toda segunda-feira, pelas Mensagens',
         'Toda segunda-feira o sistema envia, pelo contato "AVISOS DO SISTEMA" na aba Mensagens, a lista das contas em aberto que vencem nos próximos 7 dias, com data, descrição, fornecedor, valor e o total. '
         'Recebem os usuários com o módulo Contas a pagar. O aviso sai uma vez por semana, na primeira conferência da segunda-feira; sem contas no período, a mensagem avisa que não há nenhuma.', ['Mensagens > AVISOS DO SISTEMA.']),
        (NOVO, 'Balão "chegou" na agenda',
         'Quando a caixa Chegou de uma linha é marcada, o resumo da agenda ganha um balão igual aos de "vieram" e "faltaram": "1 chegou" para um paciente e "2 chegaram" (e assim por diante) para mais de um.', ['Agenda de exames > balões do resumo.']),
        (NOVO, 'Agenda: caixa "Chegou", histórico de cada linha e atualização compartilhada',
         'Ao lado do número de cada linha há uma caixinha "Chegou" (sem aumentar a coluna). Marcada, ela vale para todos os usuários, aparece no balão do resumo ("N chegaram") e entra na contagem do Relatório da agenda, '
         'no painel e nas tabelas. Cada alteração feita numa linha (campos, status, chegada, remarcação, cópia, recorte e retirada) fica registrada com quem fez e quando, e o novo botão de relógio mostra o histórico da linha. '
         'A tela da agenda já se atualiza sozinha a cada poucos segundos, então todos veem as mudanças dos colegas quase na hora.', ['Agenda de exames > caixa ao lado do número da linha.', 'Agenda de exames > botão de histórico da linha.']),
        (MELHORIA, 'Agenda: nome editável nas mensagens, observação em destaque e novo tom do Faltou',
         'O nome da agenda pode ser alterado no botão Renomear de cada agenda (o exame cadastrado vinculado não muda) e é o nome que entra no texto das mensagens de WhatsApp, em {exame} ou {agenda}. '
         'A observação que aparece ao lado da data ficou maior, em vermelho forte e com um leve pulsar. A cor do Faltou passou para um tom coral, bem diferente do rosa das vagas reservadas para convênio (UNACON), '
         'nas linhas, no status, no resumo e na impressão.', ['Agenda de exames > Renomear.', 'Administração > Mensagens do WhatsApp > {agenda}.']),
        (MELHORIA, 'Agenda vinculada a um exame cadastrado; relatórios e financeiro por exame, com painel de todos os exames',
         'Ao criar a agenda é obrigatório escolher o exame cadastrado ao qual ela fica vinculada (ele não muda depois); o campo de texto passou a ser só o nome da agenda. '
         'O relatório da agenda e o financeiro da agenda usam o exame vinculado (e o cadastro de convênios pelo mesmo exame), não mais o nome da agenda; a lista de exames mostra só os exames cadastrados. '
         'Os dados continuam vindo da agenda: o financeiro considera só quem está com status Veio. No MIBI, Repouso e Estresse do mesmo paciente contam como um exame só e o Protocolo como um MIBI completo; '
         'marcando as etapas Estresse, Repouso e Protocolo no financeiro, cada etapa é vista separada. O relatório ganhou um painel de todos os exames no período '
         '(por exame: agendados, vieram até o momento, faltaram e remarcaram; convênios, vieram por dia e horários de maior movimento), que não muda com o filtro.',
         ['Agenda de exames > Criar agenda > Exame vinculado.', 'Agenda de exames > Relatórios da agenda.', 'Agenda de exames > Financeiro da Agenda.']),
        (MELHORIA, 'Correção: pesquisa de cliente, médico e CPF no lançamento para quem tem conta do ponto',
         'Quem tinha o acesso criado pelo Banco de Horas (Minha área) e também módulos da recepção não via as opções de clientes cadastrados ao pesquisar no lançamento do atendimento: '
         'o sistema desviava as buscas para a tela inicial e a lista chegava vazia. Agora só a tela inicial é desviada para a Minha área; a pesquisa de cliente, a de médico e a conferência de CPF respondem normalmente.', ['Lançamentos > Lançar atendimento > Pesquisar cliente.']),
        (NOVO, 'Atalho "Agenda" no topo do menu',
         'Quem tem acesso à agenda ganhou, no alto do menu lateral, o botão "Agenda", que abre a Agenda de exames em um clique.', ['Menu lateral > botão AGENDA.']),
        (NOVO, 'Agenda: botão Recortar (tesoura) e tamanho dos números do calendário',
         'O botão com o boneco, que cadastrava o cliente a partir da linha, foi trocado por uma tesourinha: Recortar tira o paciente do horário, deixando-o livre, e leva o paciente com todos os dados para outro dia e horário escolhidos. '
         'Os botões Nº− e Nº+ agora ficam dentro do calendário e aumentam ou diminuem os números dos dias do calendário (não mais a coluna de contagem das linhas, que voltou ao tamanho fixo).',
         ['Agenda de exames > tesoura na linha do paciente.', 'Agenda de exames > calendário > Números do calendário.']),
        (MELHORIA, 'Gestão e desenvolvedor podem trocar o login dos usuários',
         'Em Usuários e perfis > Editar perfil, a gestão e o desenvolvedor podem alterar o login (nome de usuário usado para entrar), inclusive dos funcionários cadastrados no ponto. '
         'O nome da pessoa não muda e a senha continua a mesma; o novo login não pode repetir outro e o caixa aberto acompanha a troca. Os registros antigos de atividades e acessos mantêm o login que a pessoa tinha na hora. '
         'A gestão não troca o login do desenvolvedor, e usuários comuns com o módulo Gerenciar usuários não trocam login.', ['Usuários e perfis > Editar perfil > Nome de usuário.']),
        (NOVO, 'Hierarquia de perfis: Desenvolvedor > Gestão > Outros usuários',
         'O perfil DESENVOLVEDOR passou a ficar acima da gestão: ele edita a gestão e os demais usuários. A gestão edita os outros usuários, mas não consegue alterar, trocar a senha, '
         'desativar nem arquivar o desenvolvedor, e também não libera o módulo do suporte. Os usuários comuns só editam outros usuários se a gestão liberar o novo módulo "Gerenciar usuários"; '
         'mesmo assim só mexem em usuários comuns, só entregam módulos que eles próprios têm e não criam administradores. Perfis acima do seu nível aparecem como "Protegido" na lista.',
         ['Usuários e perfis > coluna Perfil (Desenvolvedor, Gestão, Usuário).', 'Editar perfil > módulo "Gerenciar usuários".']),
        (NOVO, 'Perfil epidemiológico dos pacientes atendidos (ONA)',
         'Nova aba na Qualidade com o perfil dos pacientes atendidos no período, calculado com os exames realizados e o cadastro dos clientes: pirâmide etária, sexo, faixas de idade, idade média e mediana, procedência (cidade e bairro), exames, convênios, médicos solicitantes, diagnósticos (CID), evolução mensal e por dia da semana, mais a qualidade do preenchimento dos dados. Tem gráficos na tela e PDF com a análise e os campos de assinatura e validação.',
         ['Qualidade > Perfil epidemiológico.']),
        (MELHORIA, 'Agenda: contador de linhas e resumo em destaque',
         'Cada linha da agenda ganhou um número antes do horário, que se refaz sozinho quando uma linha é excluída. O resumo de cada exame (por exemplo 23/26 marcados, vieram, faltaram, remarcaram e livres) ficou com letra maior e a contagem de marcados em vermelho.', []),
        (MELHORIA, 'Agenda mais compacta: escolha do exame ao lado da data',
         'O título da agenda ficou menor e o exame mostrado agora se escolhe numa lista ao lado da data, no lugar dos botões que ficavam abaixo de "Criar agenda"; a legenda subiu e a tela ganhou espaço. '
         'No menu, Agenda passou a ser o primeiro tema, antes de Lançamentos.', ['Agenda de exames > lista de exames ao lado da data.']),
        (NOVO, 'Desenvolvedor: aba Dados protegidos',
         'O perfil DESENVOLVEDOR ganhou a aba "Dados protegidos", que lista as respostas da pesquisa de satisfação e permite excluí-las. A exclusão não aparece no registro de atividades.', []),
        (MELHORIA, 'Agenda sem sobreposição e legível no tema escuro',
         'O calendário da agenda não cobre mais o painel branco e os horários e textos da grade ficaram legíveis no tema escuro.', []),
        (NOVO, 'Qualidade: modelos prontos para medicina nuclear, protocolos (POPs) e PDF com assinatura e validação',
         'Todas as abas da Qualidade ganharam uma galeria de modelos prontos para o centro de medicina nuclear: 18 problemas já analisados (com causas por 6M do Ishikawa, '
         'cinco porquês, prioridade GUT e plano 5W2H), conjuntos de ações 5W2H, matrizes de risco, análises SWOT, 17 fluxogramas com raias por setor, 3 organogramas, '
         'registros de ocorrência, critérios de avaliação de fornecedores e conjuntos de perguntas da pesquisa de satisfação. Você aplica com um clique e altera só os dados '
         'importantes. Há também a nova aba "Protocolos (POPs)", com 21 protocolos prontos (identificação e triagem, radiofármacos, derramamento, rejeitos, faturamento, '
         'entre outros), versão, aprovação e lista mestra. Todas as ferramentas geram PDF (abrir ou baixar) com a análise e o quadro de validação, com nome, cargo e registro, '
         'data e assinatura, para apresentar a auditorias e órgãos de fiscalização; Ishikawa, cinco porquês, fluxograma, organograma e protocolos agora também têm PDF. '
         'Os modelos são pontos de partida: o responsável técnico e o supervisor de proteção radiológica devem revisar e conferir a legislação vigente.',
         ['Qualidade > qualquer aba > Modelos prontos > Usar este modelo.', 'Qualidade > Protocolos (POPs) > Criar este protocolo > Aprovar > PDF para assinatura.',
          'Botões PDF e Baixar em cada ferramenta.']),
        (NOVO, 'Suporte ao desenvolvedor: sugestões e correções de bugs',
         'Novo item no menu, logo abaixo de Início, com duas abas para todos os usuários: "Sugestão" e "Correção de bug". Cada uma é um formulário; o que a pessoa '
         'enviou aparece em "Seus envios" com a situação (enviado, aceito ou não aceito). O perfil DESENVOLVEDOR (senha provisória 123, troca no primeiro acesso) e o '
         'administrador ganham duas abas a mais: "Formulários recebidos", com as correções de bugs acima das sugestões e botões grandes de aceitar ou não aceitar, e '
         '"Pasta de aceitos", onde o texto de cada item pode ser reescrito de forma didática e onde sai o relatório em PDF do que entra na próxima atualização '
         '(abre dentro do sistema ou baixa).',
         ['Suporte ao desenvolvedor > Sugestão ou Correção de bug. Desenvolvedor: Formulários recebidos e Pasta de aceitos.']),
        (NOVO, 'Faturamento em três etapas: faturado, nota fiscal emitida e recebido (com glosa)',
         'O Faturamento ganhou abas. Em "Faturamento" a fatura é cadastrada com convênio, data de referência, valor faturado, protocolo e quantidade de guias; a nota fiscal '
         'deixou de ser obrigatória e a fatura fica "Faturado (sem nota)". Em "Emissão da nota fiscal" você informa o número e a data da nota e a situação muda para "Nota fiscal emitida". '
         'Em "Recebidas" lança o que foi pago (bruto recebido, tributos opcionais e líquido) e o sistema compara com o faturado: a diferença é a glosa, em reais e em porcentagem. '
         'O PDF do protocolo pode ser importado em cada fatura, aberto dentro do sistema sem baixar e baixado depois; há também o resumo da fatura em PDF. '
         'As faturas antigas continuam: as abertas viraram "Faturado" ou "Nota fiscal emitida" conforme tinham nota.',
         ['Faturamento > Faturamento, Emissão da nota fiscal e Recebidas.']),
        (NOVO, 'Backup automático e cópia na nuvem (Google Drive, rede ou pendrive)',
         'Em Backup, a administração e a gerência ligam o backup automático e escolhem de quantos em quantos dias (todos os dias, a cada 5, a cada 15...) e em que horário. '
         'O padrão é todos os dias às 18:30; o botão "Fazer backup agora" continua valendo. O backup é sempre gravado neste computador, junto do banco; se houver uma '
         'pasta de cópia (por exemplo, a do Google Drive no Explorador de Arquivos), os backups mais recentes também vão para ela, feitos pela bandeja do Windows, '
         'que enxerga as unidades do usuário. A tela mostra se a cópia está em dia e quando será o próximo backup.',
         ['Backup > Cópia em outra pasta e Backup automático.']),
        (MELHORIA, 'Movimento de caixa mostra só os seus lançamentos do dia',
         'A tela passa a listar por padrão só o que você lançou e só do dia de hoje, com campo de data para ver outro dia (ou todas as datas). '
         'A administração e a gerência marcam "lançamentos de todos os usuários" para conferir os de outras pessoas. '
         'O relatório de fechamento de um caixa só abre para o dono dele e para a gestão.', []),
        (NOVO, 'Recebimento em duas formas de pagamento',
         'Ao receber, marque "Dividir em duas formas de pagamento" para registrar parte em dinheiro e parte em PIX num só recebimento. '
         'O troco é calculado sobre a parte em dinheiro, o relatório de fechamento soma cada parte no seu lugar e a quitação mostra as duas formas.', []),
        (MELHORIA, 'Reservas do convênio: uma planilha por dia, em .zip, e importação na agenda',
         'As planilhas de reserva saem uma por dia reservado, com os campos da agenda (nome, contato, senha e observação). Num período maior vem um .zip '
         'com todas e um relatório em PDF com as datas e a quantidade de vagas. Na agenda do dia, os botões de baixar e importar a planilha só aparecem '
         'quando há vaga reservada em branco. As planilhas não ficam guardadas no sistema.',
         ['Agenda > Reservas do convênio, ou os botões "Planilha das reservas do dia" e "Importar planilha preenchida" na agenda do dia.']),
        (NOVO, 'PNT do Gálio com questionário próprio',
         'O Gálio deixou de usar o PNT da Óssea e ganhou o seu, com as perguntas do plano terapêutico (próteses e metais, biópsia ou cirurgia de melanoma, '
         'tratamento de tumores, alergia, gravidez e individualidade). Na instalação existente, o exame GALIO é ajustado uma única vez, se ainda estiver com o padrão antigo.', []),
        (MELHORIA, 'Impressão das fichas com o quadro de escolha recolhido',
         'O quadro que personaliza quais fichas (e quantas cópias) imprimir agora fica fechado e abre com um clique em "Personalizar as fichas a imprimir".', []),
        (MELHORIA, 'Idade do paciente em Exames realizados',
         'Quando o exame não tem nascimento nem idade digitada, o sistema busca a data de nascimento no cadastro do paciente (pelo vínculo ou, sem vínculo, '
         'pelo nome quando só há um cadastro com aquele nome) e mostra a idade na lista, na impressão e na exportação.', []),
    ]},
    {'versao': '1.5.0', 'data': '2026-10-18', 'titulo': 'Gestão da Qualidade completa, robô do PDCA, imagens no chat e sistema mais rápido', 'itens': [
        (NOVO, 'Imagens no chat (somem em 24 horas)',
         'Nas Mensagens dá para enviar uma imagem (JPG, PNG, GIF ou WebP, até 5 MB) pelo botão de imagem ou colando com Ctrl+V. '
         'Só quem enviou e quem recebeu conseguem abrir. Depois de 24 horas a imagem é apagada sozinha; o texto da mensagem continua.', []),
        (NOVO, 'Central da qualidade e indicadores (KPI)',
         'Novo grupo de telas na Qualidade. Os indicadores são calculados com os dados do sistema (comparecimento, faltas, prazo do laudo, '
         'identificação, desvio de atividade, glosa, vencimentos, ocorrências, satisfação, fornecedores), com meta, situação e os últimos seis meses.',
         ['Qualidade > Indicadores (KPI). As metas são definidas pela gerência na própria tela.']),
        (NOVO, 'Robô do PDCA',
         'Analisa os indicadores, encontra o que está fora da meta ou piorando, procura onde o problema se concentra (Pareto) e monta o plano '
         'completo como rascunho: PDCA, Ishikawa, 5 Porquês e 5W2H, com a prioridade GUT. Roda sozinho uma vez por dia e avisa a gerência.',
         ['Qualidade > Robô do PDCA > Analisar agora. Aceite, edite ou descarte cada sugestão.']),
        (NOVO, 'Ferramentas de análise',
         'Ciclo PDCA, Gráfico de Pareto, Diagrama de Ishikawa (6M), Cinco porquês, Matriz GUT, Matriz de risco, Plano de ação 5W2H e Matriz '
         'SWOT, ligados entre si e com impressão, PDF e Excel.', []),
        (NOVO, 'Fluxograma de processos e organograma',
         'Editor de fluxograma com etapas, decisões, documentos, raias por setor, cores por tipo, setor ou situação de implantação, versão e '
         'aprovação, modelos prontos e exportação em PNG e SVG. Organograma montado sozinho a partir dos cargos, com cores por área.', []),
        (NOVO, 'Ocorrências, satisfação e avaliação de fornecedores (ONA)',
         'Registro de não conformidades, eventos, reclamações e retrabalho; pesquisa de satisfação (nota 0 a 10); avaliação periódica dos '
         'fornecedores por critérios com peso, classificação e relatório para a ONA.', []),
        (NOVO, 'Pesquisa de satisfação do cliente com QR Code',
         'Na Qualidade há uma pesquisa com até 10 perguntas de múltipla escolha (Ótimo, Bom, Ruim e Péssimo), mais campos de elogio e de sugestão '
         'e nome e telefone opcionais. O sistema gera o QR Code: o cliente que está na clínica, conectado ao Wi-Fi, lê com o celular e responde. '
         'A página só abre dentro da rede interna. O QR Code pode ser impresso em um cartaz ou o link enviado pelo WhatsApp. As perguntas já vêm '
         'sugeridas e podem ser editadas, excluídas e incluídas (no máximo 10). Cada resposta fica guardada para a gerência marcar como avaliada, '
         'e os resultados viram indicadores (percentual de Ótimo e Bom por pergunta, nota média, elogios e sugestões) e o relatório de satisfação '
         'da ONA em PDF e Excel. A nota também alimenta o indicador "Satisfação do paciente" do painel da qualidade.',
         ['Qualidade > Pesquisa de satisfação (QR Code): edite as perguntas, imprima o cartaz ou envie pelo WhatsApp.',
          'Qualidade > Pesquisa de satisfação (QR Code) > Respostas e indicadores: veja cada resposta e baixe o relatório da ONA.',
          'O endereço do QR Code usa o IP desta máquina; se ele mudar, informe o endereço fixo ou o nome da máquina na própria tela.']),
        (NOVO, 'NucleAI cumpre pedidos escritos (37 comandos)',
         'Além de tirar dúvidas, a NucleAI agora faz tarefas pedidas no chat, como "imprimir a agenda do dia", "quantos atendimentos hoje", '
         '"buscar cliente Maria", "fazer backup" ou "reabrir o caixa de Maria". Antes de fazer qualquer coisa ela pergunta Sim ou Não (por botão ou '
         'escrevendo); consultas só de leitura respondem direto. Escreva "comandos" para ver o que você pode pedir. Cada comando tem um risco: baixo '
         '(a maioria das pessoas pode), médio (só quem a gerência escolher) e alto (só a gerência: backup, reabrir caixa, desfazer a última ação e telas '
         'de administração). A gerência decide quem usa cada comando, e pode desligar qualquer um. Perguntas começadas por "como", "onde" ou "qual" '
         'continuam sendo dúvidas de ajuda. Cada comando executado fica no registro de atividades.',
         ['Administração > Comandos da NucleAI: escolha Todos, Só os escolhidos (marque as pessoas) ou Ninguém para cada comando.']),
        (NOVO, 'Desfazer em qualquer ação do registro de atividades e reabrir caixa',
         'O botão Desfazer do registro de atividades passou a valer para todas as ações que alteram dados (lançar, alterar, excluir, quitar, '
         'fechar o caixa e muitas outras), e não só para a agenda. Ele só desfaz se os dados continuam como a ação os deixou; senão avisa o motivo. '
         'Para quando alguém fecha o caixa sem querer, há também o botão Reabrir caixa dentro do Movimento de caixa, só para a gerência; o dono '
         'recebe um aviso. Contas de usuário, mensagens e o próprio registro ficam de fora do desfazer.',
         ['Administração > Registros de atividades > Desfazer na linha da ação.', 'Lançamentos > Movimento de caixa > Caixas > Reabrir caixa (gerência).']),
        (MELHORIA, 'Qualidade reunida em um módulo só',
         'Relatório ONA, Central da qualidade, Indicadores (KPI), Robô do PDCA, Ciclo PDCA, Pareto, Ishikawa, Cinco porquês, Matriz GUT, Matriz de risco, '
         'Plano 5W2H, Matriz SWOT, Fluxograma, Organograma, Ocorrências e satisfação, Pesquisa de satisfação e Avaliação de fornecedores viraram botões '
         'dentro do módulo Qualidade, que agora ocupa um só item da barra lateral. Cada botão continua respeitando as permissões do usuário.', []),
        (MELHORIA, 'Menu lateral mais enxuto: telas viraram botões',
         'Para facilitar a navegação, várias telas saíram da barra lateral e viraram botões no topo da tela principal do módulo: '
         'Lançar atendimento (em Atendimentos), Lançar exame realizado (em Exames realizados), Agendar medicamento (em Agenda de '
         'medicamentos), Relatórios da agenda, Faltas e reagendamento e Financeiro da Agenda (na Agenda de exames), Cores dos exames '
         '(em Exames e fichas) e Novo cadastro, Solicitar devolução e Confirmar devolução (em Cadastro de blindagem). '
         'Em Configuração, Usuários e perfis, Saúde do sistema, Registros de atividades, Log de acessos, Backup e Dados da clínica '
         'agora ficam num só módulo, Administração, com um botão para cada tela. No Banco de Horas, Funcionários do ponto, Importar ponto '
         'e Histórico do ponto passaram para Administração do ponto. As permissões continuam as mesmas: quem não tem acesso a uma tela '
         'não vê o botão, e o módulo só aparece no menu para quem tem acesso a pelo menos uma das telas. A pesquisa do menu continua '
         'achando as telas que viraram botões, e os favoritos antigos continuam funcionando.', []),
        (SEGURANCA, 'Caixa: cada pessoa recebe só o que lançou',
         'No Movimento de caixa, os atendimentos a receber só aparecem para quem os lançou, e só essa pessoa consegue receber o valor '
         '(com o caixa dela aberto, como antes). A administração e a gerência continuam vendo todos os lançamentos para conferir e '
         'excluir, mas também só recebem os próprios. A tela Caixa também mostra e altera só os lançamentos de quem os fez.', []),
        (NOVO, 'Valor de todos os exames em cada convênio',
         'No cadastro de convênios, todo convênio agora pode ter o valor de qualquer exame da clínica (RENAL, DMSA, DTPA, PULMONAR, SPECT '
         'etc., não só MIBI, Óssea, TGI, Paratgi e Gálio). Dentro do convênio basta escolher o exame na caixa de seleção, digitar o valor '
         'e trocar de exame (ou teclar Enter para ir ao próximo). Exame novo cadastrado aparece sozinho em todos os convênios, inclusive '
         'nos que forem criados depois. Os valores que já estavam cadastrados foram mantidos, e o Financeiro da agenda passou a usar '
         'o valor do exame em qualquer convênio.',
         ['Cadastros > Convênios > Editar > "Valor de cada exame". Deixe em branco o que o convênio não paga.']),
        (MELHORIA, 'Financeiro da agenda por exame',
         'O relatório de repasse médico ganhou o campo Exame: escolha, por exemplo, MIBI e o relatório (tela, PDF e Excel) traz só aquele '
         'exame, já que o repasse é feito um exame por vez. Com "Todos os exames" o relatório continua somando tudo.',
         ['Agenda > Financeiro da agenda > escolha o exame, o período e o percentual > Gerar relatório.']),
        (MELHORIA, 'Questionário da ficha: "Preencher manual" de verdade',
         'Ao clicar em Preencher manual, as perguntas somem da tela, qualquer resposta já marcada é apagada e nada é gravado; a ficha sai '
         'em branco para ser preenchida à mão. Também foi corrigido o layout das respostas SIM/NÃO na ficha impressa (MIBI e demais PNTs), '
         'que quebravam no meio, como em "( X" e ") SIM".', []),
        (MELHORIA, 'Resgate só quando o paciente sai de Faltou',
         'Passar um paciente de Agendado para Reagendado continua mostrando o novo dia na linha, mas não conta como resgate: ele não entra no '
         'relatório de resgates nem no indicador de faltas resgatadas. O resgate (e a desistência tratada) só vale quando o paciente sai do status Faltou.', []),
        (NOVO, 'Agenda: planilha das vagas reservadas para o convênio (gerar e importar)',
         'No botão Reservas do convênio, dentro da Agenda, você escolhe o convênio e o período e baixa uma planilha em branco (Excel) com as vagas '
         'reservadas para ele: data, hora, exame e convênio já preenchidos, e espaço para nome e contato do paciente. O convênio preenche e devolve; '
         'ao importar, o sistema encontra cada vaga pelo código e preenche nome e contato na agenda. Vaga já preenchida não é alterada e as linhas '
         'que não conferem aparecem num relatório do resultado.',
         ['Agenda de exames > Reservas do convênio > 1. Gerar a planilha / 2. Importar a planilha preenchida.']),
        (NOVO, 'Agenda: cadastrar cliente pela linha e aviso de duplicidade',
         'Cada linha da agenda tem o botão 👤 (antes do ＋) que abre o cadastro de cliente já com o nome, o contato e o convênio da linha; se o '
         'paciente ainda está Agendado, o sistema pergunta se quer marcar também como Veio. Ao mudar o status para Veio de um paciente que não '
         'está cadastrado, um pop-up pergunta se quer cadastrá-lo, levando os dados. Quando o mesmo nome ou o mesmo telefone aparece duas vezes na '
         'agenda do mesmo dia, o AVISOS DO SISTEMA manda um alerta com os botões Sim e Não: o Sim abre a agenda do dia destacando as linhas do caso.',
         ['Agenda > botão 👤 no fim da linha do paciente.']),
        (MELHORIA, 'Blindagens fora dos indicadores da ONA',
         'O vencimento das blindagens deixou de contar como problema nos indicadores e no robô do PDCA, porque elas só podem ser devolvidas '
         'depois de vencerem.', []),
        (NOVO, 'Tutorial animado da NucleAI',
         'No primeiro acesso, a NucleAI abre um passeio animado pelo sistema: a tela escurece, só o botão da vez fica aceso e piscando, e ela '
         'anda até ele, aponta, pulsa, abre e fecha a boca enquanto fala e dança com os olhos. O roteiro é montado só com as telas que o usuário '
         'pode usar e a ordem muda conforme o jeito de trabalhar: quem cuida do financeiro começa por ele; a recepção, por lançamentos e agenda. '
         'Dá para avançar com o botão, com as setas do teclado ou pular a qualquer momento.',
         ['Para rever quando quiser: Minha conta > Rever o tutorial, ou o botão "Rever o tutorial" no rodapé do menu.']),
        (NOVO, 'Prazo de entrega do laudo configurável e previsão no atendimento',
         'A gerência define o prazo padrão de entrega dos laudos (antes fixo em 24 horas): horas corridas, dias corridos ou dias úteis, por exemplo '
         '7 dias ou 6 dias úteis. Ao lançar o atendimento, o sistema calcula a previsão de entrega pulando sábados, domingos e feriados de '
         'Governador Valadares (nacionais, Sexta-feira Santa, aniversário da cidade em 30/01 e Santo Antônio em 13/06; Carnaval, Corpus Christi '
         'e outros dias sem expediente a gerência marca). A data aparece na tela, é gravada no atendimento, sai impressa em todas as fichas com o '
         'título "Previsão de entrega do laudo" e mostra no Mapa de laudos quando o exame está atrasado. O indicador de laudo no prazo da ONA usa o '
         'mesmo prazo.',
         ['Lançamentos > Mapa de laudos > Alterar prazo (gerência).', 'A lista de feriados deve ser conferida com a prefeitura; datas extras entram em "Outros dias sem expediente".']),
        (NOVO, 'Convênio e médico solicitante já preenchidos',
         'Ao escolher o cliente no Lançar atendimento, o convênio do atendimento já vem com o convênio cadastrado dele (dá para trocar). No Lançar exame '
         'realizado, ao escolher o paciente, o médico solicitante vem do atendimento mais recente.', []),
        (NOVO, 'Atendimentos do dia em Exames realizados',
         'Nova aba com os atendimentos lançados na recepção no dia, do mais recente ao mais antigo. Um clique em "Lançar exame" abre o lançamento já '
         'com paciente, convênio, médico e exame preenchidos (rascunho), mas o exame continua sendo um registro separado do atendimento. O que já '
         'foi lançado aparece marcado e não duplica.',
         ['Lançamentos > Exames realizados > aba Atendimentos do dia.']),
        (NOVO, 'Mapa de laudos: acesso por usuário e data real de liberação',
         'No perfil do usuário, a gerência escolhe quais situações do Mapa de laudos cada pessoa vê e de quais ela pode passar para a próxima etapa '
         '(por exemplo, só ver "Processando imagem" e passar para "Laudando", ou só "Liberado" para "Entregue"). Quem tem acesso restrito só avança '
         'uma etapa por vez. Ao liberar ou entregar, dá para informar a data e hora em que o laudo foi realmente liberado, para um esquecimento de '
         'marcação não aparecer como laudo atrasado na ONA (não pode ser futura nem anterior ao exame).',
         ['Administração > Usuários e perfis > Editar perfil > Mapa de laudos.']),
        (NOVO, 'Laudos entregues, limpar o mapa e retificação de laudo',
         'Ao lado de "Alterar prazo", o botão "Limpar entregues do período" tira do Mapa de laudos os laudos entregues, sem apagar nada: eles seguem na '
         'nova página Laudos entregues, que a gerência consulta com filtro de período e paciente. Nos laudos entregues há o botão Retificar laudo '
         '(com o motivo), que gera o indicador "Laudos retificados" no relatório ONA.',
         ['Lançamentos > Mapa de laudos > Limpar entregues do período / Laudos entregues.']),
        (NOVO, 'Arquivar perfil e desligar funcionário',
         'Em Usuários e perfis há o botão Arquivar: o perfil sai da lista e fica sem acesso, mas continua disponível em "Ver arquivados" (dá para '
         'desarquivar). Para quem é funcionário do Banco de Horas, o botão Desligar funcionário arquiva o perfil e encerra o cadastro do ponto '
         '(inativo, com a data do desligamento), que sai da lista de funcionários e fica em "Ver arquivados". O histórico do ponto é mantido.',
         ['Administração > Usuários e perfis > Arquivar ou Desligar funcionário. Banco de Horas > Funcionários > Ver arquivados.']),
        (NOVO, 'Questionário das fichas PNT no atendimento',
         'Ao lançar o atendimento, o exame que tem ficha PNT mostra o questionário dela (MIBI, óssea, renal, pulmonar, SPECT, TGI, paratireoide, '
         'linfonodo). As respostas SIM/NÃO saem impressas na ficha, e a justificativa só aparece (e só é gravada) quando a resposta é SIM. '
         'O botão Preencher manual libera o atendimento sem responder.', []),
        (MELHORIA, 'Agenda: grade mais escura, vários contatos e WhatsApp pelo aplicativo',
         'As linhas da grade da agenda ficaram mais escuras e fáceis de acompanhar. A coluna Contato aceita mais de um número, com uma setinha para '
         'alternar entre eles. O botão 💬 abre a conversa no WhatsApp instalado no computador e, se ele não responder, no WhatsApp Web, já com a '
         'mensagem pronta, que começa com "Enviado por" e o primeiro nome de quem enviou.', []),
        (NOVO, 'Mensagens do WhatsApp editáveis pela gerência',
         'Os textos de lembrete, falta (resgate) e reagendamento passaram a ser editados pela gerência, com marcas que o sistema preenche com o nome, '
         'exame, data e hora do paciente. Há botão para restaurar o texto padrão.',
         ['Administração > Mensagens do WhatsApp.']),
        (MELHORIA, 'Pesquisa de satisfação: logo animada, agradecimento e aviso de cada avaliação',
         'A página do cliente ganhou a logo animada do login e uma tela de agradecimento que se fecha sozinha. Cada avaliação respondida avisa a '
         'gerência pelas Mensagens, com os botões Sim e Não: o Sim abre direto a avaliação (o comentário do cliente não aparece no aviso).', []),
        (MELHORIA, 'Sistema mais rápido com muitos dados',
         'Depois de um teste de sobrecarga com 2 e 20 milhões de registros, o dashboard, o registro de atividades, a lista de atendimentos e '
         'os indicadores ficaram muito mais rápidos (novos índices, contas feitas no banco e cálculo único quando várias pessoas abrem a '
         'mesma tela). O banco também foi testado contra queda no meio das gravações.', []),
    ]},
    {'versao': '1.4.9', 'data': '2026-10-17', 'titulo': 'Agenda mais clara, ordem dos exames e cor do calendário', 'itens': [
        (NOVO, 'Caixa diário da empresa (novo módulo, menu Financeiro)',
         'Controle do caixa da empresa no formato da planilha MOVIMENTO DE CAIXA: quatro contas (Banco do Brasil, Unicred, Caixa Econômica e '
         'movimento de caixa), cada uma com o saldo do dia anterior. Os lançamentos são editáveis e os saldos dos dias seguintes são recalculados.',
         ['Financeiro > Caixa diário da empresa > Saldos iniciais (uma vez), depois Lançar entradas e saídas.']),
        (MELHORIA, 'Modo escuro: linhas destacadas legíveis',
         'Ao passar o mouse sobre uma linha de tabela (por exemplo, o registro de atividades) ou ao marcar uma linha, o fundo fica escuro e o texto '
         'claro, para dar para ler. Na agenda, a cor do status (por exemplo, azul para Veio) preenche a linha inteira, inclusive nome, contato, senha e observação.', []),
        (NOVO, 'Retiradas retidas e planilha do dia em Excel',
         'As retiradas retidas temporariamente ficam fora das contas, e o total final desconta o valor delas. O botão "Baixar planilha do dia" '
         'gera o Excel formatado para imprimir (A4, títulos, bordas, valores em R$), com as cores de cada conta e o mesmo cálculo da planilha original.', []),
        (MELHORIA, 'Ordem dos exames na agenda',
         'Na lista de agendas do dia, o botão "Ordenar" mostra as setas ↑ ↓ em cada exame. Suba ou desça o exame que quiser; a ordem vale para todos os dias.',
         ['Agenda > escolha o dia > botão Ordenar.']),
        (NOVO, 'Cor de fundo do calendário',
         'O calendário da agenda pode ter a cor de fundo escolhida por cada pessoa. A escolha fica no perfil e vale em qualquer computador.',
         ['Agenda > abaixo do calendário, escolha a cor. "Cor padrão" volta ao normal.']),
        (MELHORIA, 'Agenda com fundo branco no tema escuro',
         'No brilho escuro a grade da agenda continua com fundo branco, para as cores de status aparecerem como no claro.', []),
        (MELHORIA, 'Visual mais sóbrio',
         'Cores chapadas, sem brilho seguindo o mouse e sem enfeites grandes de fundo. As animações continuam.', []),
        (MELHORIA, 'Contador de status no singular',
         'Quando há só um paciente, o resumo mostra "1 veio" (e "1 faltou", "1 remarcou" etc.). A partir de dois, volta ao plural.', []),
        (MELHORIA, 'Chat mais ágil',
         'As mensagens chegam na hora sem o servidor consultar o banco a cada instante, o que deixa as telas mais rápidas quando há várias abas abertas.', []),
    ]},
    {'versao': '1.4.8', 'data': '2026-10-17', 'titulo': 'Logo do login com cara de cada tema e átomo animado', 'itens': [
        (NOVO, 'Logo da tela de login sem fundo, para cada tema',
         'A logo da clínica agora aparece sem o fundo branco e com uma versão para cada cor de tema. No tema claro as letras '
         'pegam a cor principal do tema; no tema escuro ganham a cor clara e um contorno, para ficarem em destaque em qualquer cor escolhida.',
         ['A logo acompanha o tema que você escolheu na tela de entrada.']),
        (NOVO, 'Átomo animado na tela de entrada',
         'O átomo acima de "NUCLELESTE" agora gira: os elétrons percorrem as órbitas e o núcleo pulsa de leve. Ele também segue a cor do tema. '
         'Quem tem "reduzir movimento" ativado no computador vê o átomo parado.', []),
    ]},
    {'versao': '1.4.7', 'data': '2026-10-16', 'titulo': 'Anexos em banco próprio, backup em .zip, visual novo e agenda mais flexível', 'itens': [
        (SEGURANCA, 'Anexos em um segundo banco (anexos.db)',
         'Os PDFs, Word, Excel e imagens dos módulos Documentos e Departamento Pessoal agora ficam em um banco separado. O banco principal e os '
         'backups deixam de crescer com os arquivos. Os anexos antigos são levados para lá automaticamente na primeira abertura, com cópia de '
         'segurança e conferência do SHA-256 de cada arquivo.', ['Nada muda para quem usa: enviar, abrir, baixar e excluir continuam iguais.']),
        (SEGURANCA, 'Backup em .zip com os dois bancos',
         'O botão "Fazer backup agora" gera um único arquivo .zip com o sistema, os anexos e um LEIA-ME.txt com o passo a passo para restaurar. '
         'Os backups antigos (.db) continuam aparecendo e podendo ser restaurados.', []),
        (SEGURANCA, 'Restaurar backup, inclusive de outra pasta (só administração e gerência)',
         'A restauração reconhece o .zip pelo conteúdo, restaura os dois bancos juntos e guarda antes uma cópia do estado atual. Dá para buscar backups '
         'em pendrive, outro disco ou pasta de rede. Toda restauração exige um código de verificação digitado.',
         ['Backup > Restaurar o último backup, ou Backup > Buscar em outra pasta.']),
        (NOVO, 'Fichas "Plano terapêutico MDN"',
         'Oito fichas (Cisternocintilografia, Dacriocintilografia, Esvaziamento gástrico, Gálio, Glândulas salivares, MIBG, Refluxo e Samário) '
         'entram como opção ao cadastrar um exame e saem preenchidas com os dados do paciente.', []),
        (NOVO, 'Abrir o laudo em Word do paciente',
         'Em Lançar atendimento, cada exame anterior ganha o botão "Abrir laudo (Word)". O sistema procura, na pasta definida pela gestão, o '
         'arquivo com o nome do paciente, entendendo nomes como "3F RAD - MARIA SILVA.docx" e "08.03.2023 MARIA SILVA.docx".',
         ['A gestão define a pasta em Configuração > Dados da clínica.']),
        (NOVO, 'Reservar horários para um convênio ao criar a agenda',
         'Na janela de criar agenda, a aba "Reservar horários para um convênio" abre os campos: convênio, a partir de que horário, quantos '
         'horários e de quantos em quantos. Os horários reservados ficam rosa e só aparecem como livres para pacientes daquele convênio.', []),
        (MELHORIA, 'Agenda com colunas ajustáveis, como no Excel',
         'Arraste a borda do título de qualquer coluna para mudar a largura; o ajuste vale para todas as agendas e fica salvo. A coluna das ações '
         '(depois do status) pode ser ocultada e mostrada quando for preciso.', []),
        (MELHORIA, 'Barra lateral nova',
         'Mais arredondada, com ícone em cada módulo, linhas separando temas e módulos, setas maiores para ocultar e mostrar e animações suaves.', []),
        (MELHORIA, 'Caixa e Movimento de caixa no tema Financeiro',
         'Os dois módulos saíram de Lançamentos e foram para Financeiro.', []),
        (NOVO, 'Excluir vários lançamentos do movimento de caixa',
         'Cada lançamento ganhou um checkbox, com "marcar todos", "Excluir selecionados" e "Excluir todos" (administração e gerência).', []),
        (MELHORIA, 'Favoritos mais bonitos e personalizáveis',
         'Os atalhos viraram widgets com ícone, cor e animação. Dá para trocar o símbolo de cada um, reordenar e alternar entre grade e lista.', []),
        (MELHORIA, 'Ícones novos, em traço fino, em todo o menu',
         'Os emojis da barra lateral, da barra do topo e dos favoritos foram trocados por ícones próprios de traço fino (biblioteca aberta Lucide, '
         'guardada dentro do sistema, sem depender da internet). Cada tela e cada tema do menu tem o seu desenho, que acompanha a cor do tema '
         'e funciona nos modos claro e escuro. Nos favoritos, o seletor oferece os mesmos ícones.', ['Favoritos > Personalizar > botão da paleta no atalho.']),
        (MELHORIA, 'Correção: funcionário com módulos de recepção não fica mais preso em redirecionamentos',
         'Quem tem cadastro no Banco de Horas e também módulos de recepção (sem o módulo Minha área) passou a abrir a tela inicial normal depois de '
         'trocar a senha, em vez de dar "redirecionamento em excesso".', []),
        (NOVO, 'Acesso automático para funcionários do Banco de Horas',
         'Ao cadastrar um funcionário no Banco de Horas, o sistema cria o usuário com o primeiro nome como login (se já existir, junta o último nome) '
         'e a senha padrão 123. No primeiro login o sistema fica travado: nenhuma tela abre até o funcionário definir a própria senha.',
         ['Estagiários e cadastros inativos não recebem acesso automático.']),
        (NOVO, 'Perfil Usuário ou Administrador e o perfil de Estagiário',
         'Ao criar um usuário, o perfil agora é Usuário (funcionário normal, só com os módulos marcados) ou Administrador. Nos módulos liberados há o '
         'botão "Estagiário": lança fichas (atendimentos) e só consulta e imprime a agenda, sem poder alterar nada.',
         ['Usuários e perfis > Novo usuário > botão Estagiário.']),
        (NOVO, 'Minha conta: senha, tema e brilho no mesmo lugar',
         'A página Minha conta (tema Configuração) reúne a troca de senha, a escolha do tema (a cor) e o brilho (claro ou escuro), além do log de atualizações. '
         'Qualquer cor combina com qualquer brilho e a escolha vale em qualquer computador.', ['Configuração > Minha conta > Aparência.']),
        (MELHORIA, 'Visual novo em todo o sistema, que muda com o tema',
         'A cor escolhida no rodapé do menu agora vale para tudo: barra lateral, barra do topo, página central, botões, tabelas, cartões, '
         'degradês e o átomo giratório. Há dois temas novos (Oceano e Índigo), cada um com versão clara e escura. Uma luz acompanha o mouse na barra lateral, na barra do topo, '
         'nos cartões e nos botões, e tudo foi feito de forma leve.', ['Troque em Minha conta > Aparência.']),
        (NOVO, 'Datas de cada parcela editáveis (Contas a pagar)',
         'Ao lançar uma compra parcelada, cada parcela mostra o seu vencimento com calendário. As datas começam mensais, mas qualquer uma '
         'pode ser mudada à mão, em qualquer intervalo.', ['Marque "Compra parcelada" e ajuste as datas na grade "Vencimento de cada parcela".']),
        (NOVO, 'Log de atualizações',
         'Em Minha conta, o botão "Log de atualizações" abre a lista de versões e gera este PDF com as novidades de cada uma.', []),
    ]},
    {'versao': '1.4.6', 'data': '2026-10-16', 'titulo': 'Reserva UNACON, desfazer ações, favoritos e formatação da agenda', 'itens': [
        (NOVO, 'Reserva de horários para o UNACON',
         'Horários reservados ficam rosa e só aparecem como livres para o UNACON. Marcar o convênio UNACON reserva o horário.', []),
        (SEGURANCA, 'Excluir agenda só para administração e gerência', 'O botão de excluir agenda deixou de aparecer para os demais perfis.', []),
        (NOVO, 'Botão Desfazer nos Registros de atividades',
         'Ações da agenda (criar e excluir agenda, status, remarcar, lista de espera, reservas) podem ser desfeitas, se os dados não mudaram depois.', []),
        (NOVO, 'Meus favoritos', 'Painel de atalhos por usuário, em grade ou lista, com os módulos na ordem que cada pessoa quiser.', []),
        (MELHORIA, 'Ocultar e mostrar a barra lateral', 'A tela aberta passa a ocupar o espaço da barra lateral.', []),
        (MELHORIA, 'Formatação do texto da agenda', 'Aumentar e diminuir a letra, negrito, itálico, sublinhado e maiúsculas.', []),
    ]},
    {'versao': '1.4.5', 'data': '2026-10-16', 'titulo': 'Restauração de backup e menu recolhido', 'itens': [
        (SEGURANCA, 'Restaurar backup pelo sistema',
         'Botão para restaurar o último backup (ou um específico), com código de verificação digitado e cópia automática do estado atual.', []),
        (MELHORIA, 'Menu com os temas recolhidos ao entrar', 'A cada login os módulos aparecem ocultos dentro de cada tema, para abrir só o que precisa.', []),
        (MELHORIA, 'Agenda: botões acima da legenda', 'A legenda e os botões abaixo do calendário trocaram de lugar.', []),
    ]},
    {'versao': '1.4.4', 'data': '2026-10-16', 'titulo': 'Fornecedores, compra parcelada e agenda do dia em uma página', 'itens': [
        (NOVO, 'Fornecedores e compra parcelada',
         'Cadastro manual ou pelo CNPJ, vínculo com a conta a pagar e relatório Contas por fornecedor (PDF e Excel). Cada parcela vira uma conta 1/3, 2/3, 3/3.', []),
        (MELHORIA, 'Imprimir o dia da agenda', 'Pergunta se é todos os exames ou só um; o relatório sai sempre em uma página.', []),
        (MELHORIA, 'Movimento de caixa', 'A gerência exclui lançamentos (com registro na auditoria); o movimento antigo foi zerado uma única vez, com cópia do banco antes.', []),
    ]},
]

INTRODUCAO = ('Este documento reúne, em linguagem simples, tudo o que mudou nesta versão do sistema Nucleleste: o que é novo, o que ficou melhor e o '
              'que ficou mais seguro. Cada item explica para que serve e, quando é útil, onde encontrar. Se algo não ficar claro, a NucleAI '
              '(o botão redondo no canto da tela) pode ajudar, ou fale com a gerência.')


def versoes():
    return [{'versao': v['versao'], 'data': v['data'], 'titulo': v['titulo'], 'qtd': len(v['itens'])} for v in VERSOES]


def obter(versao):
    return next((v for v in VERSOES if v['versao'] == versao), None)


def _data_extenso(iso):
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    d = datetime.strptime(iso, '%Y-%m-%d')
    return '%d de %s de %d' % (d.day, meses[d.month - 1], d.year)


def _saudacao(agora=None):
    h = (agora or datetime.now()).hour
    return 'Bom dia' if h < 12 else ('Boa tarde' if h < 18 else 'Boa noite')


class _Doc(BaseDocTemplate):
    def __init__(self, buf, **kw):
        super().__init__(buf, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2.6 * cm, bottomMargin=2.2 * cm, **kw)
        quadro = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='corpo')
        self.addPageTemplates([PageTemplate(id='capa', frames=[quadro], onPage=self._capa),
                               PageTemplate(id='miolo', frames=[quadro], onPage=self._miolo)])
        self.rotulo = ''
        self.clinica = ''

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name == 'Secao':
            self.notify('TOCEntry', (0, f.getPlainText(), self.page))

    def _capa(self, c, doc):
        c.saveState()
        c.setFillColor(colors.HexColor('#255f39'))
        c.rect(0, A4[1] - 7.5 * cm, A4[0], 7.5 * cm, stroke=0, fill=1)
        c.setFillColor(colors.HexColor('#2f9e6a'))
        c.circle(A4[0] - 2.5 * cm, A4[1] - 1.5 * cm, 3.2 * cm, stroke=0, fill=1)
        c.setStrokeColor(colors.white)
        c.setLineWidth(1.2)
        for ang in (0, 60, 120):   # átomo
            c.saveState()
            c.translate(3.6 * cm, A4[1] - 3.7 * cm)
            c.rotate(ang)
            c.ellipse(-1.7 * cm, -0.55 * cm, 1.7 * cm, 0.55 * cm, stroke=1, fill=0)
            c.restoreState()
        c.setFillColor(colors.HexColor('#ffd54a'))
        c.circle(3.6 * cm, A4[1] - 3.7 * cm, 0.22 * cm, stroke=0, fill=1)
        c.restoreState()

    def _miolo(self, c, doc):
        c.saveState()
        c.setFillColor(colors.HexColor('#255f39'))
        c.rect(0, A4[1] - 1.5 * cm, A4[0], 1.5 * cm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 10)
        c.drawString(2.2 * cm, A4[1] - 0.95 * cm, getattr(self, 'cab', 'NUCLELESTE · Registro de atualizações'))
        c.drawRightString(A4[0] - 2.2 * cm, A4[1] - 0.95 * cm, self.rotulo)
        c.setStrokeColor(colors.HexColor('#cdd6d1'))
        for k in range(1, 4):   # linhas de caderno, bem discretas, no rodapé
            c.line(2.2 * cm, 1.3 * cm - k * 0.0, A4[0] - 2.2 * cm, 1.3 * cm)
        c.setFillColor(colors.HexColor('#5d6b64'))
        c.setFont('Helvetica', 8.5)
        c.drawString(2.2 * cm, 0.8 * cm, self.clinica)
        c.drawRightString(A4[0] - 2.2 * cm, 0.8 * cm, 'Página %d' % doc.page)
        c.restoreState()


def pdf_versao(versao, clinica='', usuario='', agora=None):
    """PDF do log da versão (capa com saudação, introdução, sumário e as atualizações numeradas). None se a versão não existe."""
    v = obter(versao)
    if not v:
        return None
    ss = getSampleStyleSheet()
    verde = colors.HexColor('#255f39')
    est = {
        'titulo': ParagraphStyle('Titulo', parent=ss['Title'], fontSize=30, leading=34, textColor=colors.white, alignment=0),
        'versao': ParagraphStyle('Versao', parent=ss['Normal'], fontSize=15, leading=19, textColor=colors.HexColor('#ffd54a')),
        'h1': ParagraphStyle('Cap', parent=ss['Heading1'], fontSize=18, textColor=verde, spaceBefore=14, spaceAfter=8),
        'secao': ParagraphStyle('Secao', parent=ss['Heading2'], fontSize=13.5, textColor=verde, spaceBefore=12, spaceAfter=4, leading=17),
        'corpo': ParagraphStyle('Corpo', parent=ss['BodyText'], fontSize=11, leading=16),
        'item': ParagraphStyle('Item', parent=ss['BodyText'], fontSize=10.5, leading=15, leftIndent=14, bulletIndent=2),
        'peq': ParagraphStyle('Peq', parent=ss['BodyText'], fontSize=9, textColor=colors.HexColor('#5d6b64')),
        'cent': ParagraphStyle('Cent', parent=ss['BodyText'], fontSize=12, alignment=TA_CENTER, leading=17),
    }
    buf = io.BytesIO()
    doc = _Doc(buf, title='Registro de atualizações - versão %s' % versao, author='Nucleleste')
    doc.rotulo = 'Versão %s' % versao
    doc.clinica = clinica or 'Nucleleste'
    historia = [Spacer(1, 1.2 * cm), Paragraph('Registro de<br/>atualizações', est['titulo']), Spacer(1, 4),
                Paragraph('Versão %s · %s' % (versao, _data_extenso(v['data'])), est['versao']), Spacer(1, 3.6 * cm)]
    nome = (usuario or '').title()
    historia += [Paragraph('%s%s!' % (_saudacao(agora), (', ' + nome) if nome else ''), est['h1']),
                 Paragraph('Seja bem-vindo(a) à versão <b>%s</b> do sistema Nucleleste. %s' % (versao, v['titulo']) + '.', est['corpo']),
                 Spacer(1, 0.5 * cm), Paragraph('Introdução', est['h1']), Paragraph(INTRODUCAO, est['corpo']), Spacer(1, 0.5 * cm)]
    resumo = [['Versão', versao], ['Data', _data_extenso(v['data'])], ['Atualizações', str(len(v['itens']))]]
    tabela = Table(resumo, colWidths=[4 * cm, 10 * cm])
    tabela.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), .6, colors.HexColor('#cdd6d1')), ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f2ec')),
                                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('TEXTCOLOR', (0, 0), (0, -1), verde),
                                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    historia += [tabela, PageBreak()]
    # sumário
    sumario = TableOfContents()
    sumario.levelStyles = [ParagraphStyle('S0', fontSize=11.5, leading=20, leftIndent=8, firstLineIndent=-8)]
    sumario.dotsMinLevel = 0
    historia += [Paragraph('Sumário', est['h1']), sumario, PageBreak()]
    # atualizações
    historia.append(Paragraph('Atualizações desta versão', est['h1']))
    cores = {NOVO: '#2f7a49', MELHORIA: '#1f4e79', SEGURANCA: '#8a4b2a'}
    for n, (cat, titulo, texto, dicas) in enumerate(v['itens'], 1):
        bloco = [Paragraph('%d. %s' % (n, titulo), est['secao']),
                 Paragraph('<font color="%s"><b>%s</b></font>' % (cores.get(cat, '#255f39'), cat.upper()), est['peq']),
                 Spacer(1, 2), Paragraph(texto, est['corpo'])]
        for d in dicas:
            bloco.append(Paragraph(d, est['item'], bulletText='•'))
        historia.append(KeepTogether(bloco))
    historia += [Spacer(1, 0.8 * cm), Paragraph('Encerramento', est['h1']),
                 Paragraph('Obrigado por usar o Nucleleste. Sugestões e dúvidas são sempre bem-vindas: fale com a gerência ou com a NucleAI.', est['corpo']),
                 Spacer(1, 0.6 * cm), Paragraph('Gerado em %s' % (agora or datetime.now()).strftime('%d/%m/%Y %H:%M'), est['peq'])]
    # a capa usa o modelo "capa"; depois da primeira página troca para o modelo "miolo"
    from reportlab.platypus import NextPageTemplate
    historia.insert(0, NextPageTemplate('miolo'))
    doc.multiBuild(historia)
    return buf.getvalue()
