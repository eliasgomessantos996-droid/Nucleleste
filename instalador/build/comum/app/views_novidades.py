"""Log de atualizações (aberto a partir de "Alterar senha"): lista as versões e gera o PDF de cada uma."""
import io

from flask import Blueprint, Response, abort, g, render_template, request, send_file

from . import login_obrigatorio, novidades
from .db import config_get

bp = Blueprint('nov', __name__, url_prefix='/atualizacoes')


@bp.route('')
@login_obrigatorio
def lista():
    from . import versao
    return render_template('atualizacoes.html', versoes=novidades.versoes(), versao_atual=versao())


@bp.route('/apostila.pdf')
@login_obrigatorio
def apostila():
    """Apostila do sistema em PDF (com as novidades da versão). Só para quem entrou no sistema."""
    from . import apostila as ap
    from . import versao
    from .db import get_db
    v = versao()
    pdf = ap.gerar_pdf(get_db(), v, config_get('clinica_nome', '') or '')
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': 'inline; filename="Apostila-Nucleleste-%s.pdf"' % v, 'Cache-Control': 'no-cache'})


@bp.route('/<versao>.pdf')
@login_obrigatorio
def pdf(versao):
    dados = novidades.pdf_versao(versao, config_get('clinica_nome', ''), g.usuario['usuario'])
    if dados is None:
        abort(404)
    return send_file(io.BytesIO(dados), mimetype='application/pdf', as_attachment=request.args.get('baixar') == '1',
                     download_name='atualizacoes-%s.pdf' % versao)
