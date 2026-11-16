"""Registro automático de atividades: quem fez, o quê e quando, para todo salvamento do sistema."""
import json

from flask import g, request, session

from . import desfazer as desfazer_geral
from . import modulos
from .db import agora, get_db

# endpoint -> texto da ação
ACOES = {
    'cad.cliente_novo': 'Cadastrou cliente', 'cad.cliente_editar': 'Alterou cliente', 'cad.cliente_excluir': 'Excluiu cliente',
    'cad.convenios': 'Salvou convênio', 'cad.convenio_excluir': 'Excluiu convênio',
    'cad.medicos': 'Salvou médico', 'cad.medico_excluir': 'Excluiu médico', 'cad.exame_editar': 'Salvou exame/fichas',
    'cad.exame_ficha_editar': 'Salvou ficha personalizada', 'cad.exame_ficha_excluir': 'Excluiu ficha personalizada',
    'lanc.editar': 'Alterou exame realizado', 'lanc.excluir': 'Excluiu exame realizado', 'lanc.atendimentos_dia': 'Trouxe atendimentos para exames realizados',
    'lanc.cores': 'Alterou cores dos exames', 'lanc.importar': 'Importou a planilha de exames',
    'atend.novo': 'Lançou atendimento', 'atend.excluir': 'Excluiu atendimento', 'atend.guia_salvar': 'Atualizou guia',
    'atend.caixa_salvar': 'Atualizou lançamento do caixa',
    'med.editar': 'Salvou agendamento de medicamento', 'med.status': 'Alterou situação da dose',
    'est.item_editar': 'Salvou item de estoque', 'est.item_excluir': 'Excluiu item de estoque', 'est.entrada': 'Lançou entrada no estoque',
    'est.saida': 'Lançou baixa manual no estoque', 'est.ajuste': 'Fez ajuste de inventário no estoque',
    'est.pedido_novo': 'Criou pedido de compra', 'est.pedido': 'Salvou pedido de compra', 'est.pedido_enviar': 'Marcou pedido de compra como enviado',
    'est.pedido_receber': 'Registrou recebimento de pedido de compra', 'est.pedido_cancelar': 'Cancelou pedido de compra',
    'est.pedido_duplicar': 'Duplicou pedido de compra',
    'fin.conta_editar': 'Salvou conta a pagar', 'fin.conta_quitar': 'Quitou conta a pagar', 'fin.conta_reabrir': 'Reabriu conta a pagar',
    'fin.conta_excluir': 'Excluiu conta a pagar', 'fin.contas_imprimir': 'Gerou lote de pagamento de contas',
    'fin.conta_lote_acao': 'Quitou ou devolveu contas de um lote de pagamento',
    'fin.conta_recorrente_editar': 'Salvou conta recorrente', 'fin.conta_recorrente_alternar': 'Pausou ou reativou conta recorrente',
    'fin.conta_recorrente_excluir': 'Excluiu conta recorrente',
    'fat.editar': 'Salvou fatura', 'fat.quitar': 'Registrou recebimento de fatura (com glosa)', 'fat.reabrir': 'Desfez o recebimento da fatura',
    'fat.emitir': 'Emitiu a nota fiscal da fatura', 'fat.desfazer_emissao': 'Desfez a emissão da nota fiscal',
    'fat.protocolo_enviar': 'Importou o PDF do protocolo da fatura', 'fat.protocolo_remover': 'Removeu o PDF do protocolo da fatura',
    'fat.excluir': 'Excluiu fatura',
    'doc.documento': 'Gerou documento', 'doc.pedido_exame': 'Emitiu pedido de exame',
    'doc.guia_editar': 'Salvou guia de convênio (SP/SADT ou IPSEMG)', 'doc.guia_excluir': 'Excluiu guia de convênio',
    'admin.pastas': 'Alterou atalhos de pastas', 'admin.backup': 'Fez backup', 'admin.backup_restaurar': 'Restaurou backup', 'admin.backup_pasta': 'Buscou backups em outra pasta', 'admin.backup_destino': 'Mudou a pasta externa dos backups', 'admin.backup_destino_remover': 'Tirou uma pasta externa da lista de cópias','admin.backup_automatico': 'Alterou o backup automático',
    'admin.backup_pasta_escolher': 'Escolheu um backup de outra pasta','admin.configuracoes': 'Alterou dados da clínica',
    'admin.usuario_novo': 'Criou usuário', 'admin.usuario_editar': 'Alterou usuário/permissões',
    'admin.usuario_senha': 'Redefiniu senha de usuário', 'admin.usuario_status': 'Alterou situação do usuário',
    'auth.minha_senha': 'Alterou a própria senha',
    'bh.funcionario_novo': 'Cadastrou funcionário (banco de horas)', 'bh.funcionario_editar': 'Alterou funcionário (banco de horas)',
    'bh.funcionario_jornada': 'Salvou jornada', 'bh.importacao_enviar': 'Importou planilha do relógio de ponto',
    'bh.correcao': 'Corrigiu dia do ponto', 'bh.ajuste': 'Ajustou saldo do banco de horas',
    'bh.relatorio_pdf': 'Emitiu relatório mensal (PDF)', 'bh.escala_salvar': 'Alterou a escala',
    'bh.portal_acesso_criar': 'Criou acesso de funcionário', 'bh.portal_acesso_atualizar': 'Alterou acesso de funcionário',
    'bh.dp_enviar': 'Anexou documento (Dep. Pessoal)', 'bh.dp_arquivar': 'Arquivou documento (Dep. Pessoal)',
    'bh.dp_restaurar': 'Restaurou documento (Dep. Pessoal)', 'bh.msg_enviar': 'Enviou mensagem',
    'blind.novo': 'Cadastrou blindagem', 'blind.editar': 'Alterou blindagem', 'blind.excluir': 'Excluiu blindagem',
    'blind.devolucao': 'Solicitou devolução de blindagens', 'blind.devolvidas': 'Confirmou devolução de blindagens',
    'agenda.criar': 'Criou agenda de exame', 'agenda.excluir_agenda': 'Excluiu agenda de exame',
    'agenda.horario_adicionar': 'Acrescentou horário na agenda', 'agenda.horario_excluir': 'Retirou horário da agenda',
    'agenda.status': 'Mudou o status na agenda', 'agenda.chegou': 'Marcou/desmarcou a chegada do paciente na agenda', 'agenda.remarcar': 'Remarcou paciente na agenda',
    'mov.abrir': 'Abriu o caixa do dia', 'mov.fechar': 'Fechou o caixa do dia', 'mov.receber': 'Registrou recebimento no caixa',
    'mov.reabrir': 'Reabriu um caixa fechado',
    'ajuda.comandos': 'Alterou as permissões dos comandos da NucleAI', 'ajuda.comando_responder': 'Respondeu a um pedido da NucleAI',
    'qual.satisf_perguntas': 'Alterou as perguntas da pesquisa de satisfação', 'qual.satisf_config': 'Alterou a configuração da pesquisa de satisfação',
    'qual.satisf_revisar': 'Avaliou uma resposta da pesquisa de satisfação', 'qual.satisf_lancar': 'Lançou um questionário impresso da pesquisa de satisfação', 'mov.editar': 'Corrigiu recebimento do caixa', 'mov.excluir': 'Excluiu lançamento do movimento de caixa',
    'mov.excluir_varios': 'Excluiu vários lançamentos do movimento de caixa',
    'fin.conta_fornecedor_editar': 'Salvou fornecedor', 'fin.conta_fornecedor_excluir': 'Excluiu fornecedor',
    'preco.editar': 'Salvou tabela de preços', 'preco.acao': 'Alterou tabela de preços (reajuste, cópia, duplicação ou exclusão)',
    'arq.novo': 'Enviou documento (módulo Documentos)', 'arq.editar': 'Alterou documento (módulo Documentos)',
    'arq.excluir': 'Excluiu documento (módulo Documentos)',
    'agenda.copiar': 'Copiou agenda para outro dia', 'agenda.copiar_linha': 'Copiou paciente para outro horário na agenda',
    'agenda.bloquear': 'Bloqueou dia na agenda',
    'agenda.desbloquear': 'Desbloqueou dia na agenda', 'agenda.espera_adicionar': 'Incluiu na lista de espera',
    'agenda.espera_excluir': 'Retirou da lista de espera', 'agenda.espera_encaixar': 'Encaixou paciente da lista de espera',
    'sup.sugestao_enviar': 'Enviou sugestão ao desenvolvedor', 'sup.bug_enviar': 'Enviou correção de bug ao desenvolvedor',
    'sup.decidir': 'Aceitou ou recusou um formulário do suporte', 'sup.texto_salvar': 'Editou o texto de um item da pasta do suporte',
    'sup.situacao': 'Mudou a situação de um item da pasta do suporte', 'sup.aplicar_todas': 'Marcou os itens aceitos como aplicados',
    'agenda.reagendar': 'Reagendou paciente na agenda', 'agenda.reserva': 'Reservou/liberou horário para o UNACON',
    'agenda.reservar': 'Reservou/liberou horários para o UNACON', 'reg.desfazer': 'Desfez uma ação do registro de atividades',
    'nucleaiia.config': 'Alterou as configurações da NucleAI IA', 'nucleaiia.niveis': 'Alterou os níveis da NucleAI IA',
    'nucleaiia.liberar': 'Tentou liberar a NucleAI IA para o time', 'nucleaiia.desativar': 'Desativou a NucleAI IA',
    'nucleaiia.treinar': 'Voltou a NucleAI IA ao treino', 'nucleaiia.codigo': 'Gerou o código de liberação da NucleAI IA',
    'nucleaiia.memoria': 'Editou a memória da NucleAI IA', 'nucleaiia.memoria_reverter': 'Reverteu a memória da NucleAI IA',
    'nucleaiia.reverter': 'Reverteu a memória da NucleAI IA', 'nucleaiia.teste': 'Testou a conexão da NucleAI IA',
    'pront.doc': 'Salvou documento do prontuário', 'pront.doc_novo': 'Criou documento no prontuário',
    'pront.doc_excluir': 'Excluiu documento do prontuário', 'pront.doc_reabrir': 'Reabriu documento do prontuário',
    'lem.salvar': 'Salvou lembrete', 'lem.excluir': 'Excluiu lembrete', 'lem.ativar': 'Reativou lembrete', 'lem.desativar': 'Desativou lembrete',
}
# POSTs que respondem 200 (abrem a impressão, ou JSON da agenda) mas contam como atividade
# (a edição de células da agenda, 'agenda.campo', é frequente demais e não entra no registro)
RESPONDE_200 = {'admin.backup_pasta', 'doc.documento', 'doc.pedido_exame','bh.relatorio_pdf', 'agenda.criar', 'agenda.excluir_agenda',
                'agenda.horario_adicionar', 'agenda.horario_excluir', 'agenda.status', 'agenda.chegou', 'agenda.remarcar', 'agenda.copiar',
                'agenda.copiar_linha', 'agenda.bloquear', 'agenda.desbloquear', 'agenda.espera_adicionar', 'agenda.espera_excluir', 'agenda.espera_encaixar',
                'agenda.reagendar', 'agenda.reserva', 'agenda.reservar', 'lem.ativar', 'lem.desativar'}
# campos do formulário que ajudam a identificar o registro (nunca senhas)
CAMPOS_RESUMO = ['titulo', 'nome', 'usuario', 'descricao', 'cliente_id', 'exame', 'medicamento', 'convenio', 'nota_fiscal', 'referencia',
                 'valor_bruto', 'tributos', 'valor', 'valor_recebido', 'banco', 'status', 'data', 'data_dose', 'horario', 'acao',
                 'name', 'clock_id', 'kind', 'month', 'category', 'paciente', 'exame', 'lote']


def resumo_form():
    partes = []
    for k in CAMPOS_RESUMO:
        v = (request.form.get(k) or '').strip()
        if v and 'senha' not in k:
            partes.append('%s=%s' % (k, v[:60]))
    if request.view_args:
        for k, v in request.view_args.items():
            partes.append('%s=%s' % (k, v))
    if g.get('detalhe_auditoria'):   # a própria tela pode acrescentar o que foi feito (ex.: ids excluídos de uma vez)
        partes.append(g.detalhe_auditoria)
    return '; '.join(partes)[:400]


def registrar(modulo, acao, detalhe='', rota=None, desfazer=None):
    """`desfazer`: como voltar atrás nesta ação (dicionário JSON), mostrado como botão "Desfazer" nos registros."""
    db = get_db()
    db.execute('INSERT INTO auditoria (data_hora, usuario, modulo, acao, detalhe, rota, ip, desfazer) VALUES (?,?,?,?,?,?,?,?)',
               (agora(), g.usuario['usuario'] if g.get('usuario') else None, modulo, acao, detalhe, rota or request.path,
                request.remote_addr, json.dumps(desfazer) if desfazer else None))
    db.commit()


def depois_da_requisicao(resp):
    """after_request: grava toda ação de escrita bem-sucedida do usuário logado."""
    try:
        if request.method != 'POST' or not g.get('usuario') or g.get('sem_auditoria'):   # sem_auditoria: exclusões do desenvolvedor não aparecem no registro
            return resp
        ep = request.endpoint
        if not ep or ep.startswith('auth.login') or ep == 'auth.logout':
            return resp
        sucesso = resp.status_code in (301, 302, 303) or (ep in RESPONDE_200 and resp.status_code == 200)
        if not sucesso:
            return resp
        # ação que terminou com mensagem de erro (ex.: "não pode excluir") não é registrada
        novos = (session.get('_flashes') or [])[g.get('_n_flashes', 0):]
        if any(cat == 'erro' for cat, _ in novos):
            return resp
        mod = modulos.modulo_do_endpoint(ep)
        if isinstance(mod, tuple):
            mod = mod[0]
        nome_mod = 'Usuários' if mod in ('__admin__', 'usuarios_gerir') else modulos.NOMES.get(mod, mod or 'Sistema')
        acao = ACOES.get(ep, 'Ação em %s' % ep)
        if ep == 'admin.usuario_editar' and not (request.view_args or {}).get('uid'):
            acao = 'Criou usuário'
        elif ep == 'fat.editar' and not (request.view_args or {}).get('fid'):
            acao = 'Lançou fatura'
        elif ep == 'lanc.editar' and not (request.view_args or {}).get('rid'):
            acao = 'Lançou exame realizado'
        detalhe = resumo_form()
        destino = resp.headers.get('Location')
        if destino:
            detalhe = (detalhe + ' → ' + destino.split('?')[0])[:400]
        explicito = g.pop('desfazer', None)   # ações que montam o próprio desfazer (agenda)
        registrar(nome_mod, acao, detalhe, desfazer=explicito or desfazer_geral.coletar(g.get('db')))
    except Exception:  # auditoria nunca pode derrubar a resposta ao usuário
        pass
    return resp
