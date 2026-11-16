"""Campanhas de saúde do mês (Outubro Rosa, Novembro Azul etc.): o sistema se personaliza sozinho.

Só muda o laço no menu, na tela de entrada e no Início, e a mensagem de conscientização.
As cores do sistema (tema e brilho) não mudam. A gerência liga ou desliga em Painéis do Início.
"""
from datetime import date

from .db import config_get

# chave na tabela config: '1' = ligado (padrão quando ainda não existe), '0' = desligado
CHAVE = 'campanhas_saude'

NOMES_MES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto',
             'Setembro', 'Outubro', 'Novembro', 'Dezembro']


def _campanha(nome, tema, cor, mensagem, laco=None, clinica=None):
    """Monta uma campanha. O laço usa a própria cor quando não for informado."""
    return {'nome': nome, 'tema': tema, 'cor': cor, 'laco': laco or cor, 'mensagem': mensagem, 'clinica': clinica}


# a primeira campanha de cada mês é a principal (aparece em destaque)
CAMPANHAS = {
    1: [_campanha('Janeiro Branco', 'saúde mental e emocional', '#8d99ae',
                  'Cuidar da mente é parte da saúde: vale conversar sobre emoções e buscar apoio quando precisar.',
                  laco='#ffffff')],
    2: [_campanha('Fevereiro Roxo', 'Alzheimer, lúpus e fibromialgia', '#7b2cbf',
                  'Conhecer essas doenças ajuda a reconhecer sinais cedo e a procurar orientação adequada.'),
        _campanha('Fevereiro Laranja', 'leucemia', '#f77f00',
                  'Informação sobre a leucemia ajuda a reconhecer sintomas e a procurar atendimento.')],
    3: [_campanha('Março Lilás', 'prevenção do câncer do colo do útero', '#b185db',
                  'A prevenção começa com informação e com os exames indicados pelo médico.'),
        _campanha('Março Azul-marinho', 'câncer colorretal', '#1d3557',
                  'Falar sobre o intestino e os exames de rotina ajuda a descobrir problemas a tempo.')],
    4: [_campanha('Abril Verde', 'segurança e saúde no trabalho', '#2b9348',
                  'Ambientes seguros protegem quem trabalha e quem é atendido.'),
        _campanha('Abril Azul', 'conscientização sobre o autismo', '#4895ef',
                  'Respeitar o tempo e as diferenças de cada pessoa faz parte do cuidado com todos.')],
    5: [_campanha('Maio Amarelo', 'atenção e cuidado no trânsito', '#e9b10a',
                  'No trânsito, a atenção de cada um protege a própria vida e a dos outros.'),
        _campanha('Dia Mundial da Tireoide', 'tireoide (25 de maio)', '#3a86ff',
                  'A tireoide regula o metabolismo, e sintomas persistentes merecem avaliação médica.',
                  clinica='Na clínica: cintilografia de tireoide e iodoterapia.')],
    6: [_campanha('Junho Vermelho', 'doação de sangue', '#d00000',
                  'Doar sangue é um gesto simples que pode salvar vidas.'),
        _campanha('Junho Laranja', 'anemia e leucemia', '#f77f00',
                  'Conhecer os sinais da anemia ajuda a buscar avaliação a tempo.')],
    7: [_campanha('Julho Amarelo', 'hepatites virais e câncer ósseo', '#e9b10a',
                  'Vacinação e testagem são formas eficazes de cuidar do fígado e da saúde.',
                  clinica='Na clínica: cintilografia óssea.')],
    8: [_campanha('Agosto Dourado', 'aleitamento materno', '#c9a227',
                  'Amamentar fortalece o vínculo e a saúde de mãe e bebê, com apoio de profissionais.'),
        _campanha('Agosto Branco', 'câncer de pulmão', '#8d99ae',
                  'Parar de fumar e evitar a poluição do ar reduzem o risco para os pulmões.',
                  laco='#ffffff', clinica='Na clínica: cintilografia pulmonar.')],
    9: [_campanha('Setembro Amarelo', 'prevenção do suicídio e valorização da vida', '#e9b10a',
                  'Se você está passando por um momento difícil, procure apoio. Falar ajuda.'),
        _campanha('Setembro Vermelho', 'saúde do coração', '#c1121f',
                  'Cuidar da alimentação, da pressão e da atividade física protege o coração.',
                  clinica='Na clínica: cintilografia de perfusão miocárdica (MIBI).'),
        _campanha('Setembro Verde', 'doação de órgãos', '#2b9348',
                  'Conversar em família sobre a doação de órgãos pode salvar outras vidas.')],
    10: [_campanha('Outubro Rosa', 'prevenção do câncer de mama', '#e75480',
                   'Mamografia e autoexame fazem parte da prevenção; procure orientação médica para o seu caso.',
                   clinica='Na clínica: pesquisa de linfonodo sentinela e cintilografia óssea.')],
    11: [_campanha('Novembro Azul', 'saúde do homem e prevenção do câncer de próstata', '#1e6fd9',
                   'Cuidar da saúde do homem inclui consultas de rotina e conversar com o médico.',
                   clinica='Na clínica: cintilografia óssea.')],
    12: [_campanha('Dezembro Vermelho', 'prevenção do HIV/aids e outras ISTs', '#c1121f',
                   'Testagem e uso de preservativo são formas de cuidar de si e do outro.'),
         _campanha('Dezembro Laranja', 'prevenção do câncer de pele', '#f77f00',
                   'Proteger a pele do sol e observar pintas e feridas ajuda na prevenção.')],
}


def do_mes(dia=None):
    """Lista de campanhas do mês de `dia` (hoje, se não informado)."""
    return CAMPANHAS[(dia or date.today()).month]


def ligado():
    """Gerência pode desligar; sem registro na tabela config, fica ligado."""
    return config_get(CHAVE, '1') == '1'


def atual(dia=None):
    """Campanha do mês para o contexto das telas, ou None quando estiver desligado."""
    if not ligado():
        return None
    dia = dia or date.today()
    lista = do_mes(dia)
    return {'principal': lista[0], 'outras': lista[1:], 'mes': NOMES_MES[dia.month - 1]}
