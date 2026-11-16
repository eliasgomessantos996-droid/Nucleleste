"""Tutorial animado da NucleAI: roteiro personalizado pelos módulos que o usuário pode usar.

O roteiro é montado a partir do menu que a pessoa enxerga (só entra o que ela tem). A ordem segue o perfil de uso
dela: quem trabalha mais com o financeiro começa por ele; quem trabalha na recepção começa por lançamentos e agenda.
O desenho e a animação ficam em static/js/tutorial.js.
"""
from __future__ import annotations

# perfis de trabalho: temas do menu que formam cada perfil, na ordem em que fazem sentido explicar
PERFIS = {
    'recepcao': ('Lançamentos', 'Agenda', 'Cadastros'),
    'financeiro': ('Financeiro',),
    'gestao': ('Qualidade', 'Documentos', 'Controle de Blindagens', 'Configuração'),
    'pessoal': ('Banco de Horas',),
}
ORDEM_PADRAO = ('Lançamentos', 'Agenda', 'Cadastros', 'Financeiro', 'Documentos', 'Qualidade', 'Controle de Blindagens',
                'Outros', 'Banco de Horas', 'Configuração')

TEXTO_GRUPO = {
    'Lançamentos': 'Aqui fica o dia a dia da clínica: lançar o atendimento do paciente, acompanhar o laudo até a entrega e registrar os exames realizados.',
    'Agenda': 'A agenda marca os pacientes por exame e horário, mostra quem veio e quem faltou e ajuda a chamar de volta quem não compareceu.',
    'Cadastros': 'Clientes, convênios, médicos e exames ficam cadastrados aqui. Quanto mais completo o cadastro, menos você digita nos lançamentos.',
    'Financeiro': 'O dinheiro da clínica: caixa, contas a pagar, faturamento dos convênios e o que ainda está para receber.',
    'Documentos': 'Documentos de fiscalização e arquivos importantes, com aviso antes de vencer.',
    'Qualidade': 'Indicadores, relatórios e ferramentas de qualidade (ONA), feitos com os dados que o próprio sistema já guarda.',
    'Controle de Blindagens': 'Controle das blindagens: cadastro, devolução e o que está pendente.',
    'Outros': 'Telas de apoio que não cabem nos outros temas.',
    'Banco de Horas': 'O seu banco de horas: marcações, saldo e solicitações.',
    'Configuração': 'Ajustes do sistema, usuários e permissões. Só aparece para quem cuida da administração.',
}

# telas que merecem um passo só delas (rótulo do item do menu -> explicação)
TEXTO_ITEM = {
    'Início': 'Esta é a tela inicial: um resumo do dia e atalhos para o que você mais usa.',
    'Mensagens': 'As mensagens internas, como um WhatsApp da clínica. O número vermelho avisa o que você ainda não leu, e dá para mandar imagens.',
    'Atendimentos': 'Aqui você lança o atendimento do paciente. O convênio e a previsão de entrega do laudo já vêm calculados, e as fichas saem prontas para imprimir.',
    'Mapa de laudos': 'Acompanhe cada exame até o laudo ser entregue. Você só enxerga as etapas que a gerência liberou para o seu usuário.',
    'Exames realizados': 'Os exames feitos no dia, com rádio-fármaco, lote e atividade. A aba “Atendimentos do dia” traz o que a recepção lançou.',
    'Caixa': 'O caixa do dia: o que foi recebido, a forma de pagamento e o fechamento.',
    'Dashboard': 'Gráficos e números da clínica para acompanhar a produção.',
    'Meus favoritos': 'Seus atalhos pessoais: monte o painel com as telas que você mais usa.',
}
DESTAQUES_TOPO = ('Início', 'Mensagens')


PESO_GRUPO = {'Cadastros': 0.5, 'Outros': 0}   # temas de apoio pesam menos para decidir o perfil


def _perfil_principal(grupos):
    """Perfil de quem mais usa um conjunto de temas. Quem enxerga muitos perfis (ex.: administrador) não tem perfil único."""
    pontos = {p: sum(PESO_GRUPO.get(g, 1) for g in gs if g in grupos) for p, gs in PERFIS.items()}
    if sum(1 for v in pontos.values() if v >= 1) >= 3 or not any(pontos.values()):
        return None
    melhor = max(pontos.values())
    return next(p for p in PERFIS if pontos[p] == melhor)   # empate: vale a ordem de PERFIS


def _ordem_dos_grupos(grupos):
    """Grupos que a pessoa vê, com os do perfil principal primeiro; o resto segue a ordem padrão."""
    principal = _perfil_principal(grupos)
    primeiros = [g for g in PERFIS[principal] if g in grupos] if principal else []
    resto = [g for g in ORDEM_PADRAO if g in grupos and g not in primeiros]
    extras = [g for g in grupos if g not in primeiros and g not in resto]
    return primeiros + resto + extras


def _lista_de_nomes(nomes, limite=5):
    nomes = list(nomes)
    if len(nomes) > limite:
        return ', '.join(nomes[:limite]) + ' e mais %d' % (len(nomes) - limite)
    if len(nomes) > 1:
        return ', '.join(nomes[:-1]) + ' e ' + nomes[-1]
    return nomes[0] if nomes else ''


def montar(menu, usuario_nome='', nucleai_ativa=True):
    """Passos do tutorial. `menu` é a lista (grupo, itens) que o usuário enxerga."""
    primeiro = (usuario_nome or '').split(' ')[0].capitalize() if usuario_nome else ''
    por_grupo = {grupo: itens for grupo, itens in menu if grupo}
    topo = next((itens for grupo, itens in menu if not grupo), [])
    grupos = _ordem_dos_grupos(list(por_grupo))
    perfil = _perfil_principal(list(por_grupo))

    passos = [{'tipo': 'centro', 'titulo': 'Olá%s! Eu sou a NucleAI' % (', ' + primeiro if primeiro else ''),
               'texto': 'Vou te mostrar o sistema em poucos passos, só com o que o seu usuário pode usar. '
                        'Pode avançar com o botão piscando, com a seta → do teclado, ou pular quando quiser.'}]
    if any(g for g in grupos):
        frases = {'recepcao': 'Pelo que vi, o seu dia a dia é na recepção: vamos começar pelos lançamentos e pela agenda.',
                  'financeiro': 'Pelo que vi, o seu trabalho é no financeiro: vamos começar por ele.',
                  'gestao': 'Pelo que vi, você cuida da gestão e da qualidade: vamos começar por aí.',
                  'pessoal': 'Pelo que vi, você usa o banco de horas: vamos começar por ele.'}
        if perfil in frases:
            passos[0]['texto'] += ' ' + frases[perfil]
    passos.append({'tipo': 'busca', 'titulo': 'Pesquise qualquer tela',
                   'texto': 'Digite aqui o nome da tela que procura, ou aperte a tecla / em qualquer lugar do sistema.'})
    for it in topo:
        if it['rotulo'] in DESTAQUES_TOPO:
            passos.append({'tipo': 'item', 'valor': it['rotulo'], 'titulo': it['rotulo'], 'texto': TEXTO_ITEM[it['rotulo']]})
    for grupo in grupos:
        itens = por_grupo[grupo]
        nomes = [i['rotulo'] for i in itens]
        texto = TEXTO_GRUPO.get(grupo, 'Telas deste tema.')
        if nomes != [grupo]:
            texto += ' Você tem: ' + _lista_de_nomes(nomes) + '.'
        passos.append({'tipo': 'grupo', 'valor': grupo, 'titulo': grupo, 'texto': texto})
        for it in itens:
            if it['rotulo'] in TEXTO_ITEM and it['rotulo'] not in DESTAQUES_TOPO:
                passos.append({'tipo': 'item', 'valor': it['rotulo'], 'titulo': it['rotulo'], 'texto': TEXTO_ITEM[it['rotulo']]})
    if nucleai_ativa:
        passos.append({'tipo': 'nucleai', 'titulo': 'Qualquer dúvida, é só me chamar',
                       'texto': 'Este botão redondo, no canto da tela, abre uma conversa comigo. Escreva a sua dúvida do seu jeito que eu ajudo.'})
    passos.append({'tipo': 'conta', 'titulo': 'Minha conta',
                   'texto': 'Aqui você troca a senha e escolhe a cor e o brilho do sistema. O tutorial também fica aqui, para rever quando quiser.'})
    passos.append({'tipo': 'centro', 'titulo': 'Pronto! Bom trabalho 💚',
                   'texto': 'Quando quiser rever, use o botão “Rever o tutorial” em Minha conta ou no rodapé do menu.'})
    return passos
