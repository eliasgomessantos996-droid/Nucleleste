"""Mensagens do WhatsApp da agenda, editáveis pela gerência (Administração > Mensagens do WhatsApp).

Os textos ficam na configuração da clínica (chave "whats_mensagens", em JSON). Quando a gerência não personaliza um
tipo, vale o texto padrão. Marcas entre chaves são trocadas pelos dados do paciente e do exame ao enviar; {saudacao}
vira "Olá, Maria" (ou só "Olá", quando não há nome).
"""
import json
import re

from .db import config_get, config_set

CHAVE = 'whats_mensagens'
LIMITE = 1000

# tipo: (rótulo na tela, texto padrão)
TIPOS = {
    'lembrete': ('Lembrete do exame (agenda, para quem está marcado)',
                 '{saudacao}! Lembrete: seu exame ({exame}) está marcado para {data} às {hora}. Pode confirmar sua presença?'),
    'falta': ('Quem faltou (resgate, pela agenda)',
              '{saudacao}! Tudo bem? 😊 Aqui é da Nucleleste. Notamos que você não pôde comparecer ao seu exame de {exame}, '
              'marcado para {data} às {hora}. Gostaríamos muito de te ajudar: esse exame é importante para o seu diagnóstico e para '
              'acompanhar a sua saúde, e fazê-lo no tempo certo faz toda a diferença. Podemos encontrar um novo dia e horário que '
              'funcione para você? Responda esta mensagem que a gente organiza tudo com muito carinho! 💚'),
    'reagendamento': ('Convite para reagendar (tela de faltas)',
                      '{saudacao}! Tudo bem? 😊 Aqui é da Nucleleste. Sentimos sua falta no seu exame de {exame} marcado para {data}. '
                      'Sabemos que imprevistos acontecem, e tudo bem! Podemos encontrar um novo horário que funcione melhor para você? '
                      'É só responder aqui. 💚'),
}

VARIAVEIS = [
    ('{saudacao}', 'Olá, Maria (ou só Olá, quando o paciente não tem nome)'),
    ('{nome}', 'primeiro nome do paciente'),
    ('{exame}', 'nome da agenda (o que está escrito no nome da agenda; pode ser renomeado na agenda)'),
    ('{agenda}', 'o mesmo nome da agenda'),
    ('{data}', 'data do exame (dd/mm/aaaa)'),
    ('{hora}', 'horário do exame'),
]


def atuais():
    """Texto de cada tipo: o personalizado pela gerência ou o padrão."""
    try:
        guardados = json.loads(config_get(CHAVE, '') or '{}')
    except ValueError:
        guardados = {}
    return {t: (guardados.get(t) or '').strip() or padrao for t, (_, padrao) in TIPOS.items()}


def salvar(form):
    """Grava os textos enviados. Texto igual ao padrão (ou vazio) volta a ser o padrão."""
    guardados = {}
    for tipo, (_, padrao) in TIPOS.items():
        texto = (form.get(tipo) or '').strip()[:LIMITE]
        if texto and texto != padrao:
            guardados[tipo] = texto
    config_set(CHAVE, json.dumps(guardados, ensure_ascii=False))


def restaurar():
    config_set(CHAVE, '')


def montar(modelo, nome='', exame='', data='', hora=''):
    """Preenche as marcas do modelo. Marca desconhecida fica como está."""
    primeiro = (nome or '').strip().split(' ')[0].capitalize() if (nome or '').strip() else ''
    valores = {'saudacao': ('Olá, ' + primeiro) if primeiro else 'Olá', 'nome': primeiro,
               'exame': exame or '', 'data': data or '', 'hora': hora or ''}
    return re.sub(r'\{(\w+)\}', lambda m: valores.get(m.group(1), m.group(0)), modelo)
