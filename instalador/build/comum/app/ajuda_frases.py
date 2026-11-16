"""Repertório de frases da NucleAI: cada situação tem várias versões, com estilos de abordagem diferentes
(animada, formal, poética, científica, esportiva...). A escolha é sorteada para a conversa não ficar repetitiva.

Regras que os testes conferem:
- SAUDACOES usam {nome};
- NAO_ENTENDI e NAO_ENTENDI_DUVIDA sempre dizem "não entendi";
- AGRADECIMENTOS sempre agradecem ("obrigada").
"""
import random

_sorteio = random.Random()


def escolher(frases, **dados):
    """Uma das frases, com os campos {nome} etc. preenchidos."""
    return _sorteio.choice(frases).format(**dados)


# ------------------------------------------------------------------ 20 saudações (a lista de temas vem logo depois)
SAUDACOES = [
    # animada
    'Olá, {nome}! 🎉🎉 Eu sou a NucleAI, a assistente do Nucleleste, e fico MUITO feliz em falar com você! '
    'Bora descobrir juntos o passo a passo do que você precisa? 💚',
    # formal
    'Olá, {nome}. Seja bem-vindo(a). Sou a NucleAI, assistente virtual do Nucleleste, e estou à disposição para '
    'orientá-lo(a) sobre o uso do sistema, com clareza e objetividade.',
    # descontraída
    'E aí, {nome}! 😄 Aqui é a NucleAI, a sua parceira de sistema. Dúvida bateu? Relaxa, eu te mostro o caminho sem complicação!',
    # poética
    'Olá, {nome}! ✨ Entre telas, botões e relatórios, sou a NucleAI: aquela que transforma dúvida em caminho. '
    'Conte comigo para clarear o próximo passo.',
    # cientista nuclear
    'Saudações, {nome}! ⚛️ Aqui é a NucleAI. Minha meia-vida é longa e a minha paciência, infinita: pode perguntar à vontade!',
    # motivacional
    'Oi, {nome}! 💪 Cada dúvida resolvida é um dia mais leve. Eu sou a NucleAI e vou te ajudar a ter o sistema na palma da mão!',
    # esportiva
    'Olá, {nome}! 🏁 A NucleAI entrando em campo! Eu passo a jogada e você faz o gol: me diga onde precisa de ajuda.',
    # chef
    'Bem-vindo(a) à cozinha, {nome}! 👩‍🍳 Eu sou a NucleAI e tenho a receita passo a passo de cada tela do sistema. '
    'Qual prato vamos preparar hoje?',
    # piloto
    'Aqui é a NucleAI, comandante {nome}! ✈️ Decolagem autorizada: me diga o destino (a tela) e eu traço a rota até lá.',
    # detetive
    'Olá, {nome}. 🔎 A NucleAI, detetive de dúvidas, já está no caso. Conte o mistério e eu desvendo o passo a passo.',
    # super-heroína
    'Chegou a NucleAI! 🦸‍♀️ Sempre pronta para salvar o seu dia de qualquer botão que insista em se esconder, {nome}!',
    # musical
    'Olá, {nome}! 🎵 Sou a NucleAI e a minha música preferida é a de uma dúvida resolvida. Vamos afinar esse sistema juntos?',
    # viajante / GPS
    'Olá, {nome}! 🧭 Eu sou a NucleAI, o seu GPS dentro do Nucleleste. Diga para onde quer ir e eu calculo a melhor rota.',
    # jardineira
    'Olá, {nome}! 🌱 A NucleAI cuida do jardim do sistema: aqui toda dúvida floresce em resposta. Como posso ajudar?',
    # amiga de longa data
    'Oi, {nome}, que bom te ver por aqui! 🤗 Eu sou a NucleAI, e se tem algo no sistema te deixando com dúvida, vamos resolver juntas.',
    # aventura
    'Olá, aventureiro(a) {nome}! 🗺️ A NucleAI é o seu guia nesta expedição pelo Nucleleste. Qual é o próximo tesouro a encontrar?',
    # plantão
    'Plantão da NucleAI aberto, {nome}! 🩺 Atendimento rápido e sem fila: qual é a sua dúvida do dia?',
    # concierge
    'Bem-vindo(a), {nome}! 🛎️ Eu sou a NucleAI, a concierge do sistema. Peça o que precisar e eu o acompanho até a tela certa.',
    # treinadora
    'Fala, {nome}! 📣 A NucleAI é a sua treinadora de sistema: eu mostro o passo a passo e você manda ver. Vamos?',
    # robô retrô
    'BIP BOP! 🤖 Sou a NucleAI e estou 100% carregada para te ajudar, {nome}. Aguardando as suas ordens com o maior carinho!',
]

# ------------------------------------------------------------------ 20 "não entendi" (resposta inválida)
NAO_ENTENDI = [
    'Desculpe, não entendi 😅 Responda apenas com o número de uma das opções, ou escreva a sua dúvida.',
    'Ops! Eu não entendi essa 🙈 Pode digitar só o número da opção que você quer, ou me contar a dúvida com as suas palavras?',
    'Hmm, não entendi o que você quis dizer. 🤔 Escolha um número da lista ou escreva a dúvida de outro jeito.',
    'Perdão, não entendi a sua resposta. Peço que informe o número de uma das opções, ou descreva a dúvida.',
    'Eita, não entendi! 😄 Me manda só o número da opção, ou escreve o que está precisando.',
    'Não entendi, mas já já a gente se acerta! 💚 Digite o número de uma opção, ou conte a sua dúvida.',
    'Meus circuitos deram um nó: não entendi essa 🤖 Responda com o número de uma opção ou escreva a dúvida de outra forma.',
    'Sinto muito, não entendi. Para eu acertar o caminho, use o número da opção ou descreva o que precisa.',
    'Epa, não entendi essa jogada! 🏁 Me diga o número da opção, ou escreva a sua dúvida.',
    'Nesse mapa eu não entendi o seu destino 🧭 Informe o número de uma opção, ou escreva a dúvida com outras palavras.',
    'Ih, não entendi 🙃 Tenta de novo: o número da opção ou a sua dúvida escrita.',
    'A receita não deu certo: não entendi o ingrediente 👩‍🍳 Escolha o número de uma opção ou me conte a dúvida.',
    'Não entendi a pista, detetive! 🔎 Me dê o número de uma das opções ou escreva a dúvida.',
    'Desculpa, não entendi. 😊 Responda com o número de uma opção, ou reformule a dúvida para mim.',
    'Quase! Mas não entendi 🎯 Digite o número da opção que você quer ou escreva a sua dúvida.',
    'Não entendi, e isso é culpa minha, não sua! 💚 Pode responder com o número da opção, ou descrever o que precisa.',
    'Meu radar não captou essa resposta 📡 Não entendi. Use o número de uma opção ou escreva a dúvida.',
    'Não entendi 🌱 Vamos plantar de novo? Escolha o número de uma opção ou descreva a sua dúvida.',
    'Poxa, não entendi essa. Mas calma: escolha um número da lista ou conte a dúvida com as suas palavras. ✨',
    'Atenção, comandante: não entendi a mensagem ✈️ Informe o número de uma opção ou escreva a sua dúvida.',
]

# ------------------------------------------------------------------ 12 "não entendi" a dúvida escrita
NAO_ENTENDI_DUVIDA = [
    'Hmm, não entendi bem a sua dúvida 🤔 Você pode seguir a lista abaixo ou reformular a dúvida com outras palavras.',
    'Desculpe, não entendi a sua dúvida. 😅 Tente escrever de outro jeito (por exemplo, o nome da tela e o que quer fazer) '
    'ou siga a lista abaixo.',
    'Ops, não entendi o que você precisa. 🙈 Pode reformular a dúvida, ou escolher um tema na lista abaixo.',
    'Não entendi a sua dúvida, mas não vou desistir! 💚 Escreva com outras palavras ou siga a lista abaixo.',
    'Meus circuitos deram um nó: não entendi essa dúvida 🤖 Reformule com outras palavras, ou escolha o caminho pela lista abaixo.',
    'Perdão, não entendi a dúvida. Se puder, diga o nome da tela e o que deseja fazer, ou use a lista abaixo.',
    'Não entendi 🔎 Que tal contar a dúvida de outro jeito? Ou, se preferir, siga a lista abaixo.',
    'Eita, essa dúvida eu não entendi 😄 Escreva com outras palavras (ex.: "fechar o caixa", "imprimir ficha") ou siga a lista.',
    'Não entendi a sua dúvida, e quero acertar! 🎯 Reformule, ou escolha na lista abaixo o tema mais próximo.',
    'Sinto muito, não entendi a dúvida. Você pode descrevê-la de outra forma ou seguir a lista abaixo.',
    'Ainda não entendi o que você quer saber 🧭 Reescreva a dúvida com outras palavras ou siga a lista abaixo.',
    'Não entendi, mas a lista abaixo pode te levar lá! ✨ Ou reformule a dúvida e eu tento de novo.',
]

# ------------------------------------------------------------------ 8 aberturas quando a dúvida escrita foi entendida
ENTENDI = [
    'Entendi! 🔎 Pelo que você escreveu, acho que a sua dúvida é sobre',
    'Já saquei! 😄 Acredito que você precise de ajuda com',
    'Captei! 💡 Parece que o assunto é',
    'Entendido! ✅ Pelo seu texto, a dúvida deve ser sobre',
    'Boa pergunta! 🤓 Isso me lembra o assunto',
    'Achei! 🎯 Creio que é sobre',
    'Compreendi. Parece que você precisa de ajuda com',
    'Beleza! 💚 Acho que o que você procura é',
]

# ------------------------------------------------------------------ 20 agradecimentos (a dúvida foi sanada)
AGRADECIMENTOS = [
    'Que ótimo, fico feliz em ter ajudado! 🥳 Obrigada por falar comigo, {nome}.',
    'Missão cumprida! 🎉 Muito obrigada pela confiança, {nome}. Foi um prazer ajudar.',
    'Eu que agradeço, {nome}! 💚 Obrigada por conversar comigo. Volte sempre que precisar.',
    'Obrigada, {nome}. Fico satisfeita em saber que a orientação foi útil. Estou à disposição.',
    'Dúvida resolvida e coração feliz! 😄 Obrigada por passar por aqui, {nome}.',
    'Boa, {nome}! 🏆 Gol de placa! Obrigada por me deixar ajudar.',
    'Que bom que deu certo! 🌱 Obrigada, {nome}, e até a próxima dúvida (mas tomara que não precise!).',
    'Receita aprovada! 👩‍🍳 Obrigada pela companhia na cozinha do sistema, {nome}.',
    'Pouso tranquilo, comandante {nome}! ✈️ Obrigada por voar comigo.',
    'Caso encerrado, {nome}! 🔎 Obrigada por colaborar com a investigação.',
    'Missão da NucleAI concluída! 🦸‍♀️ Obrigada, {nome}, e conte comigo sempre.',
    'Que a sua rotina agora fique afinada! 🎵 Obrigada por conversar comigo, {nome}.',
    'Rota concluída com sucesso! 🧭 Obrigada por navegar comigo, {nome}.',
    'Ver você resolver a dúvida alegra o meu dia! 🤗 Muito obrigada, {nome}.',
    'Obrigada, {nome}! ✨ Cada dúvida resolvida deixa o sistema mais leve para todo mundo.',
    'Feliz em ajudar! 🎯 Obrigada pela atenção, {nome}. Qualquer coisa, é só chamar.',
    'Treino concluído, {nome}! 📣 Obrigada por mandar ver. Você vai longe!',
    'BIP BOP! 🤖 Tarefa finalizada com 100% de satisfação. Obrigada, {nome}!',
    'Foi um prazer, {nome}! 🛎️ Obrigada pela visita à nossa central de ajuda.',
    'Atendimento concluído, {nome}. 🩺 Obrigada pela confiança e até a próxima!',
]

# ------------------------------------------------------------------ despedida de quem encerra sem dúvida / sem ajuda
DESPEDIDAS = [
    'Tudo bem! Quando precisar, é só clicar no botão redondo no canto da tela. Até logo! 👋💚',
    'Combinado! Estarei por aqui sempre que precisar. Até a próxima! ✨',
    'Sem problemas, {nome}! A NucleAI fica de plantão. É só me chamar. 🩺',
    'Até logo, {nome}! 🌱 Se aparecer uma dúvida, o botão redondo estará no canto da tela.',
    'Tchau, {nome}! 🤖 Conversa encerrada. Volte quando quiser!',
    'Foi um prazer! 🧭 Até a próxima rota, {nome}.',
]

PEDIDO_NOTA = ('Antes de terminar: de 1 a 5, que nota você dá para esta ajuda? ⭐\n'
               '(Responda de 1 a 5, sendo 5 a melhor nota. Se preferir pular, responda 0.)')

SUFIXO_APAGAR = 'Esta conversa será apagada em instantes. Quando precisar, é só chamar! 💚'
SUFIXO_ESCOLHA = 'Responda com o número do tema abaixo ou, se preferir, escreva a sua dúvida com as suas palavras. 👇'
