from quart import Blueprint, render_template, Response

bp_admin = Blueprint('admin', __name__, url_prefix='/admin')


@bp_admin.route('/')
async def index():
    return await render_template('admin/index.html')
