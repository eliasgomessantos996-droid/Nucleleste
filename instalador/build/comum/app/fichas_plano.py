"""Fichas "Plano terapêutico MDN" (Anexo 01, POP MDN 24), uma por exame, vindas dos modelos em Word da clínica.

São criadas uma única vez como fichas personalizadas (as mesmas de "Exames e fichas → Fichas personalizadas"): aparecem
como opção de documento no cadastro de cada exame e já saem preenchidas com os dados do paciente e do atendimento.
Dados de paciente que existiam nos modelos foram trocados pelos campos automáticos ({nome}, {nascimento}, {convenio}, {data}).
"""
from __future__ import annotations

from .db import agora

CHAVE_CONTROLE = 'fichas_plano_v1'

_ABERTURA = """# PLANO TERAPÊUTICO MDN
Anexo 01 · POP MDN 24
---
**Paciente:** {nome}
**Data de nascimento:** {nascimento}      **Convênio:** {convenio}
---
## HISTÓRICO"""

_PERGUNTAS_PADRAO = """No caso de paciente do sexo feminino: está grávida ou há suspeita de gravidez? [ ] Sim   [ ] Não
Possui alguma alergia ou restrição de medicamentos? [ ] Sim. Qual(is)? {linha}   [ ] Não
Alguma individualidade relacionada a crenças, valores ou religião a ser observada? [ ] Sim   [ ] Não
Obs.: {linha}"""

_EVOLUCAO = """## EVOLUÇÃO



## PRESCRIÇÃO MÉDICA"""

_PROCEDIMENTO = """---
## PROCEDIMENTO: ORIENTAÇÕES COMPARTILHADAS COM PACIENTE E/OU ACOMPANHANTE"""

_FECHO = """Data: {data}


{linha}
Assinatura do paciente ou responsável"""

_SEM_CONTRASTE = 'Como não usamos contrastes, nossos exames não causam nenhum tipo de reação alérgica.'
_SEM_PREPARO = 'Não é necessário nenhum tipo de preparação, dieta ou restrição para o procedimento.'


def _ficha(perguntas, prescricao, exame, texto):
    return '\n'.join([_ABERTURA, perguntas, _EVOLUCAO, prescricao, _PROCEDIMENTO, '**EXAME: %s**' % exame, '', texto, '', _FECHO])


FICHAS = [
    ('Plano terapêutico MDN - Cisternocintilografia', _ficha(
        '\n'.join(['Possui alguma alergia ou restrição de medicamentos? [ ] Sim. Qual(is)? {linha}   [ ] Não',
                   'No caso de paciente do sexo feminino: está grávida ou há suspeita de gravidez? [ ] Sim   [ ] Não',
                   'Alguma individualidade relacionada a crenças, valores ou religião a ser observada? [ ] Sim   [ ] Não',
                   'Obs.: {linha}']),
        '5 mCi DTPA', 'CISTERNOCINTILOGRAFIA', '\n'.join([
            'A cisternografia é um exame que exige muitas sessões de imagens cerebrais, que devem ser tiradas até dois dias seguidos. '
            'Por isso pode ser necessária a punção lombar, que deve ser feita por um médico anestesista.',
            'Para a realização do exame de cisternografia cerebral é preciso:',
            '1. Aplicar anestésico no local da injeção e retirar uma amostra do líquido da coluna, que será misturado com o radiofármaco;',
            '2. Administrar uma injeção com o radiofármaco no final da coluna do paciente e tampar suas narinas com algodão;',
            '3. O paciente deve permanecer deitado por alguns minutos com os pés ligeiramente mais elevados que o resto do corpo;',
            '4. A seguir são realizadas imagens do tórax e da cabeça, aproximadamente 3 horas depois, repetidas após 6 e 24 horas da '
            'aplicação da substância, se necessário.',
            'É necessário um repouso de 24 horas após a realização do exame, e o resultado irá mostrar a presença de fístula liquórica, ou não.']))),
    ('Plano terapêutico MDN - Dacriocintilografia', _ficha(
        '\n'.join(['Lacrimeja algum dos olhos? Qual deles? {linha}',
                   'Possui alguma alergia ou restrição de medicamentos? [ ] Sim. Qual(is)? {linha}   [ ] Não',
                   'No caso de paciente do sexo feminino: está grávida ou há suspeita de gravidez? [ ] Sim   [ ] Não',
                   'Alguma individualidade relacionada a crenças, valores ou religião a ser observada? [ ] Sim   [ ] Não',
                   'Obs.: {linha}']),
        '', 'DACRIOCINTILOGRAFIA (VIAS LACRIMAIS)', '\n'.join([
            'Este procedimento é para determinar a presença de obstrução dos canalículos e do ducto lacrimal. É usada uma instilação do '
            'radiofármaco em ambos os olhos e uma aquisição das imagens oculares por cerca de 30 minutos.',
            _SEM_PREPARO, _SEM_CONTRASTE]))),
    ('Plano terapêutico MDN - Esvaziamento gástrico', _ficha(
        _PERGUNTAS_PADRAO, '5 MCI TC99', 'CINTILOGRAFIA PARA AVALIAÇÃO DE ESVAZIAMENTO GÁSTRICO', '\n'.join([
            'Uma pequena quantidade de radiofármaco será misturada com uma porção do leite/suco e fornecida ao paciente.',
            'Em seguida ele deverá ingerir o restante do conteúdo da mamadeira ou copo. É importante que o paciente tome todo o alimento '
            'para que o estômago fique cheio, aumentando a sensibilidade do método. Imediatamente após, o paciente será encaminhado à '
            'sala de exame e posicionado na maca do aparelho cintilográfico.',
            'Para que seja possível realizar o exame, o paciente será colocado na maca do equipamento, sendo contido pelo próprio '
            'acompanhante. A duração da aquisição das imagens é de 5 minutos a imediata e, 2 horas após a medicação, a imagem tardia '
            'também é feita em 5 minutos.',
            _SEM_PREPARO, _SEM_CONTRASTE]))),
    ('Plano terapêutico MDN - Gálio', _ficha(
        '\n'.join(['Próteses, pinos, parafusos, placas de metal e etc. em alguma parte do corpo? [ ] Sim   [ ] Não   Qual região? {linha}',
                   'Alguma biópsia ou cirurgia realizada de melanoma? [ ] Sim   [ ] Não',
                   'Realizou algum tratamento para tumores? [ ] Sim   [ ] Não',
                   'Possui alguma alergia ou restrição de medicamentos? [ ] Sim. Qual(is)? {linha}   [ ] Não',
                   'No caso de paciente do sexo feminino: está grávida ou há suspeita de gravidez? [ ] Sim   [ ] Não',
                   'Alguma individualidade relacionada a crenças, valores ou religião a ser observada? [ ] Sim   [ ] Não',
                   'Obs.: {linha}']),
        '___ GÁLIO', 'CINTILOGRAFIA COM GÁLIO-67', '\n'.join([
            'A cintilografia com Gálio-67 é um exame complementar para o diagnóstico e a avaliação terapêutica de processos infecciosos e '
            'tumorais. O estudo também está indicado na avaliação da febre de origem obscura, de doença pulmonar intersticial e na '
            'avaliação complementar da síndrome de imunodeficiência adquirida.',
            'Na maioria dos casos não há necessidade de qualquer preparo para a realização do exame.',
            'Serão feitas imagens do paciente 48 horas após a administração da medicação e, se necessário, 72 horas após a medicação '
            'serão feitas novas imagens.',
            _SEM_PREPARO, _SEM_CONTRASTE]))),
    ('Plano terapêutico MDN - Glândulas salivares', _ficha(
        _PERGUNTAS_PADRAO, '_____ MCI TC99\n1 COPO DE SUCO DE LIMÃO', 'CINTILOGRAFIA PARA GLÂNDULAS SALIVARES', '\n'.join([
            'O paciente será posicionado na maca do equipamento de Medicina Nuclear.',
            'Após a administração do radiofármaco, por via venosa, obtém-se uma sequência de imagens das glândulas salivares num período '
            'de 15 minutos. Logo em seguida, uma imagem estática focalizada da região facial é adquirida, com duração de 5 minutos.',
            'Numa segunda fase, após estímulo das glândulas salivares com o uso de ácido cítrico (10 ml de suco de limão para gargarejo), '
            'obtém-se uma nova imagem estática focalizada da face, mais uma vez com 5 minutos de duração, com o paciente sendo liberado '
            'logo em seguida.',
            _SEM_CONTRASTE]))),
    ('Plano terapêutico MDN - MIBG', _ficha(
        _PERGUNTAS_PADRAO, '5 MCI MIBG', 'CINTILOGRAFIA COM MIBG-131', '\n'.join([
            'A princípio o paciente deve ingerir, durante os 3 dias que antecedem o exame, 3 colheres ao dia de uma solução iodada, '
            'normalmente Iodeto de Potássio.',
            'No início da cintilografia com MIBG é injetado um radioisótopo (metaiodo-benzilguanidina iodo-131) na veia. Mais tarde, '
            'aproximadamente 48 horas após a administração da medicação, o paciente deverá ficar deitado sobre uma mesa posicionada e, '
            'a seguir, executa-se a cintilografia do corpo todo. Pode ser necessário repetir as varreduras por mais de um a três dias e '
            'cada cintilografia dura entre uma e duas horas.',
            'Após a injeção do radioisótopo, o paciente deve ingerir, durante 3 dias, 3 colheres ao dia (uma solução iodada) para bloquear '
            'a captação na tireoide. A radiação oriunda deste radioisótopo é muito alta se comparada à da maioria dos outros elementos '
            'radioativos e, por essa razão, algumas precauções serão necessárias durante alguns dias após o exame. O pessoal '
            'especializado em medicina nuclear instruirá o paciente sobre os cuidados específicos, que podem incluir a descarga dupla do '
            'vaso sanitário após o uso (para diluir o material radioativo excretado na urina) ou outras precauções.',
            'Este exame é realizado para confirmar a presença de um feocromocitoma, especialmente quando a tomografia computadorizada '
            'resulta negativa ou duvidosa, ou quando há suspeita da presença de vários tumores ou de um tumor que não esteja dentro da '
            'glândula adrenal (tumor extra-adrenal).',
            _SEM_CONTRASTE]))),
    ('Plano terapêutico MDN - Refluxo gastroesofágico', _ficha(
        _PERGUNTAS_PADRAO, '5 MCI TC99', 'CINTILOGRAFIA PARA PESQUISA DE REFLUXO GASTROESOFÁGICO', '\n'.join([
            'Uma pequena quantidade de radiofármaco será misturada com uma porção do leite/suco e fornecida ao paciente.',
            'Em seguida ele deverá ingerir o restante do conteúdo da mamadeira ou copo. É importante que o paciente tome todo o alimento '
            'para que o estômago fique cheio, aumentando a sensibilidade do método. Imediatamente após, o paciente será encaminhado à '
            'sala de exame e posicionado na maca do aparelho cintilográfico.',
            'Para que seja possível realizar o exame, o paciente será colocado na maca do equipamento, sendo contido pelo próprio '
            'acompanhante. A duração da aquisição das imagens é de 20 minutos.',
            _SEM_PREPARO, _SEM_CONTRASTE]))),
    ('Plano terapêutico MDN - Samário', _ficha(
        _PERGUNTAS_PADRAO, '', 'CINTILOGRAFIA COM SAMÁRIO', '\n'.join([
            '**Antes do tratamento:**',
            '* Não interrompa a sua medicação.',
            '* Sua alimentação deve ser normal no dia do tratamento (não é necessário jejum).',
            '',
            '**Nos 2 primeiros dias após o tratamento:**',
            '* Após a injeção de samário, evitar o contato próximo com gestantes e crianças.',
            '* Se possível, use banheiro separado, dê descarga 3 vezes e não respingue urina no piso.',
            '',
            '**Acompanhamento:**',
            '* Será necessário fazer exames de sangue quinzenais durante 2 meses. Nos dias em que vier colher exame de sangue, deverá estar em jejum.',
            '* No caso de aparecimento ou piora de sintomas clínicos, procurar o médico do Serviço de Medicina Nuclear ou, na ausência '
            'deste, o serviço de Pronto-Socorro.']))),
]


def garantir(con):
    """Cria as fichas uma única vez (se alguém excluir uma depois, ela não volta). Não mexe em fichas já existentes de mesmo título."""
    if con.execute('SELECT 1 FROM config WHERE chave=?', (CHAVE_CONTROLE,)).fetchone():
        return 0
    criadas = 0
    for titulo, conteudo in FICHAS:
        if con.execute('SELECT 1 FROM fichas_extras WHERE titulo=? COLLATE NOCASE', (titulo,)).fetchone():
            continue
        con.execute('INSERT INTO fichas_extras (titulo, conteudo, cabecalho, ativa, criado_por, criado_em) VALUES (?,?,1,1,?,?)',
                    (titulo, conteudo, 'SISTEMA', agora()))
        criadas += 1
    con.execute('INSERT OR IGNORE INTO config (chave, valor) VALUES (?,?)', (CHAVE_CONTROLE, agora()))
    return criadas
