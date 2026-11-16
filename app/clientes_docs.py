"""Histórico do paciente em PDF, no modelo comum de relatórios (relatorio_base)."""
from __future__ import annotations

from reportlab.platypus import Paragraph

from . import util
from .relatorio_base import RelatorioPDF


def _periodo(de, ate):
    if de and ate:
        return 'período: %s a %s' % (util.data_br(de), util.data_br(ate))
    if de:
        return 'período: a partir de %s' % util.data_br(de)
    if ate:
        return 'período: até %s' % util.data_br(ate)
    return 'todo o histórico'


def historico_pdf(cliente, linhas, de, ate, clinica):
    """PDF do histórico: cabeçalho com nome, CPF, nascimento e período; tabela Data | Exame | Médico solicitante; total no fim."""
    subtitulo = 'Nome: %s · CPF: %s · Nascimento: %s · %s' % (
        cliente['nome'] or '', cliente['cpf'] or 'não informado', util.data_br(cliente['data_nasc']) or 'não informado', _periodo(de, ate))
    rp = RelatorioPDF('Histórico do paciente', clinica, subtitulo)
    e = rp.e
    historia = [rp.tabela(['Data', 'Exame', 'Médico solicitante'],
                          [[util.data_br(l['data']), l['exame'] or '', (l['medico'] or '').strip() or 'Não informado'] for l in linhas],
                          [30, 90, 60], totais=['Total de atendimentos', '', str(len(linhas))], direita=())]
    if not linhas:
        historia.append(Paragraph('Nenhum atendimento no período.', e['nota']))
    return rp.bytes(historia)
