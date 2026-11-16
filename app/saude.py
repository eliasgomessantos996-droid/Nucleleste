"""Avaliação da saúde do sistema: cada indicador recebe um nível de cor e o conjunto vira uma nota de 0 a 100.

Níveis (as cores da tela):
  otimo (azul)     tudo sobrando
  bom (verde)      dentro do esperado
  medio (amarelo)  merece atenção em breve
  ruim (vermelho)  precisa de ação agora
"""
from __future__ import annotations

OTIMO, BOM, MEDIO, RUIM = 'otimo', 'bom', 'medio', 'ruim'
ROTULO = {OTIMO: 'Ótimo', BOM: 'Bom', MEDIO: 'Atenção', RUIM: 'Crítico'}
PONTOS = {OTIMO: 100, BOM: 80, MEDIO: 50, RUIM: 12}
PESOS = {'disco': 25, 'backup': 25, 'banco': 20, 'caixa': 10, 'docs': 10, 'erros': 10}
MINIMO_GB = 2.0          # o sistema sempre quer pelo menos isto livre
FATOR_NECESSARIO = 20    # ...ou 20 vezes o tamanho do banco somado aos backups, o que for maior


def necessario_gb(banco_mb, backups_mb):
    return max(MINIMO_GB, (banco_mb + backups_mb) * FATOR_NECESSARIO / 1024)


def nivel_disco(livre_gb, necessario):
    razao = livre_gb / necessario if necessario else 99
    if livre_gb < 1 or razao < 1:
        return RUIM
    if razao < 3:
        return MEDIO
    return BOM if razao < 8 else OTIMO


def nivel_backup(idade_dias):
    if idade_dias is None:
        return RUIM
    if idade_dias <= 1:
        return OTIMO
    if idade_dias <= 3:
        return BOM
    return MEDIO if idade_dias <= 7 else RUIM


def nivel_caixa(abertos_antigos, abertos_hoje):
    if abertos_antigos:
        return RUIM
    return BOM if abertos_hoje else OTIMO


def nivel_documentos(vencidos, a_vencer):
    if vencidos:
        return RUIM
    return MEDIO if a_vencer else OTIMO


def nivel_erros(ultimas_24h, ultimos_7d):
    if ultimas_24h > 3:
        return RUIM
    if ultimas_24h:
        return MEDIO
    return BOM if ultimos_7d else OTIMO


def nivel_geral(nota):
    if nota >= 90:
        return OTIMO
    if nota >= 70:
        return BOM
    return MEDIO if nota >= 45 else RUIM


def nota(itens):
    """Média ponderada dos itens avaliados (os que têm peso)."""
    total = sum(PESOS[i['chave']] for i in itens if i['chave'] in PESOS)
    soma = sum(PESOS[i['chave']] * PONTOS[i['nivel']] for i in itens if i['chave'] in PESOS)
    return round(soma / total) if total else 100


MENSAGEM_GERAL = {
    OTIMO: ('Tudo em ordem', 'O sistema está saudável e com folga. Nada precisa da sua atenção agora.'),
    BOM: ('Funcionando bem', 'Tudo dentro do esperado. Há pequenos pontos para acompanhar abaixo.'),
    MEDIO: ('Pede atenção', 'Alguns itens estão no amarelo. Resolva antes que virem problema.'),
    RUIM: ('Precisa de ação agora', 'Há itens em vermelho. Veja os cartões marcados e resolva primeiro esses.'),
}


def avaliar(s):
    """`s`: dicionário de indicadores brutos. Devolve os cartões, a nota e a mensagem geral."""
    necessario = necessario_gb(s['banco_mb'], s['backups_mb'])
    n_disco = nivel_disco(s['disco_livre_gb'], necessario)
    usado_pct = 100 - (s['disco_livre_gb'] / s['disco_total_gb'] * 100 if s['disco_total_gb'] else 0)
    razao = s['disco_livre_gb'] / necessario if necessario else 0
    b = s['backup']
    idade = s.get('backup_idade_dias')
    n_backup = nivel_backup(idade)
    n_banco = OTIMO if s['banco_integro'] else RUIM
    n_caixa = nivel_caixa(s['caixas_antigos'], s['caixas_abertos'] - s['caixas_antigos'])
    n_docs = nivel_documentos(s['docs_vencidos'], s['docs_a_vencer'])
    n_erros = nivel_erros(s['erros_24h'], s['erros_7d'])

    if b is None:
        det_backup, pct_backup = 'Nenhum backup encontrado. Faça um agora.', 0
    else:
        quando = 'hoje' if idade < 1 else ('ontem' if idade < 2 else 'há %d dias' % idade)
        det_backup = 'Feito %s · %.1f MB' % (quando, b['tamanho_mb'])
        pct_backup = max(6, 100 - min(idade, 10) * 10)
    itens = [
        {'chave': 'disco', 'titulo': 'Espaço livre', 'nivel': n_disco, 'icone': 'disco',
         'valor': '%.1f GB' % s['disco_livre_gb'], 'pct': max(2, min(100, round(razao / 8 * 100))),   # cheia = folga "ótima"
         'detalhe': 'livres de %.0f GB · o sistema precisa de cerca de %.1f GB' % (s['disco_total_gb'], necessario),
         'dica': {RUIM: 'Pouco espaço para o que o sistema precisa. Libere espaço no disco ou mova os backups para outro lugar.',
                  MEDIO: 'O espaço está ficando curto. Vale limpar arquivos que não usa mais.',
                  BOM: 'Espaço suficiente (%.0f vezes o necessário).' % razao,
                  OTIMO: 'Espaço de sobra (%.0f vezes o necessário).' % razao}[n_disco]},
        {'chave': 'backup', 'titulo': 'Último backup', 'nivel': n_backup, 'icone': 'backup',
         'valor': b['quando'] if b else 'nenhum', 'pct': pct_backup, 'detalhe': det_backup,
         'dica': {RUIM: 'Backup antigo ou inexistente. Faça um backup agora em Configuração → Backup.',
                  MEDIO: 'Faz alguns dias sem backup. Faça um hoje.',
                  BOM: 'Backup recente.', OTIMO: 'Backup de hoje ou de ontem. Perfeito.'}[n_backup]},
        {'chave': 'banco', 'titulo': 'Banco de dados', 'nivel': n_banco, 'icone': 'banco',
         'valor': '%.1f MB' % s['banco_mb'], 'pct': 100 if s['banco_integro'] else 20,
         'detalhe': 'Integridade verificada: %s' % ('sem problemas' if s['banco_integro'] else 'PROBLEMA ENCONTRADO'),
         'dica': 'Os dados estão íntegros.' if s['banco_integro'] else 'O banco apontou inconsistência. Não feche o sistema e chame o suporte; restaure um backup se preciso.'},
        {'chave': 'caixa', 'titulo': 'Caixas abertos', 'nivel': n_caixa, 'icone': 'caixa',
         'valor': str(s['caixas_abertos']), 'pct': 100 if n_caixa == OTIMO else (70 if n_caixa == BOM else 25),
         'detalhe': ('%d de dias anteriores' % s['caixas_antigos']) if s['caixas_antigos'] else ('em uso hoje' if s['caixas_abertos'] else 'todos fechados'),
         'dica': {RUIM: 'Há caixa de dia anterior aberto. Peça para fechar antes de abrir o de hoje.',
                  BOM: 'Caixa de hoje em uso. Lembre de fechar no fim do dia.', OTIMO: 'Nenhum caixa pendente.',
                  MEDIO: ''}[n_caixa]},
        {'chave': 'docs', 'titulo': 'Documentos de fiscalização', 'nivel': n_docs, 'icone': 'docs',
         'valor': str(s['docs_vencidos'] + s['docs_a_vencer']), 'pct': 100 if n_docs == OTIMO else (55 if n_docs == MEDIO else 15),
         'detalhe': '%d vencido(s) · %d a vencer em %d dias' % (s['docs_vencidos'], s['docs_a_vencer'], s['dias_vencimento']),
         'dica': {RUIM: 'Há documento vencido. Renove o quanto antes.', MEDIO: 'Há documento perto de vencer. Comece a renovação.',
                  OTIMO: 'Nenhum documento vencido ou perto de vencer.', BOM: ''}[n_docs]},
        {'chave': 'erros', 'titulo': 'Erros do sistema', 'nivel': n_erros, 'icone': 'erros',
         'valor': str(s['erros_24h']), 'pct': {OTIMO: 100, BOM: 80, MEDIO: 45, RUIM: 12}[n_erros],
         'detalhe': 'nas últimas 24 horas · %d nos últimos 7 dias' % s['erros_7d'],
         'dica': {RUIM: 'Muitos erros hoje. Veja a lista abaixo e avise o suporte.', MEDIO: 'Houve erro hoje. Veja o detalhe abaixo.',
                  BOM: 'Sem erros hoje; houve alguns na semana.', OTIMO: 'Nenhum erro na última semana.'}[n_erros]},
    ]
    pontos = nota(itens)
    geral = nivel_geral(pontos)
    titulo, texto = MENSAGEM_GERAL[geral]
    for i in itens:
        i['rotulo'] = ROTULO[i['nivel']]
    return {'itens': itens, 'nota': pontos, 'nivel': geral, 'rotulo': ROTULO[geral], 'titulo': titulo, 'texto': texto,
            'necessario_gb': necessario}
