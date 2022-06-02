import os, re, json, logging, hashlib, asyncio
from typing import List, Set, Optional
from datetime import datetime

import timeago
from peewee import PostgresqlDatabase, SqliteDatabase, ProgrammingError
from playhouse.shortcuts import ReconnectMixin
from aiocryptocurrency.coins import Coin, SUPPORTED_COINS
from aiocryptocurrency.coins.nero import Wownero, Monero
from aiocryptocurrency.coins.firo import Firo
from quart import Quart, render_template, session, request, g
from quart_schema import RequestSchemaValidationError
from quart_session import Session
from quart_session_openid import OpenID

from funding.utils.discourse import Discourse
from funding.utils.globals import COINS_LOOKUP
from funding.utils.rates import Rates
import settings

cache = None
peewee = None
rates = Rates()
app: Optional[Quart] = None
openid: Optional[OpenID] = None
crypto_provider: Optional[Firo] = None
coin: Optional[dict] = None
discourse = Discourse()
proposal_task = None


class ReconnectingPGDatabase(ReconnectMixin, PostgresqlDatabase):
    def __init__(self, *args, **kwargs):
        import peewee as pw
        super(ReconnectingPGDatabase, self).__init__(*args, **kwargs)
        self._reconnect_errors = {
            pw.InterfaceError: ["connection already closed"]
        }


database = ReconnectingPGDatabase(
    settings.DB_NAME,
    autorollback=True,
    user=settings.DB_USER,
    password=settings.DB_PASSWD,
    host=settings.DB_HOST,
    port=settings.DB_PORT
)


async def _setup_postgres(app: Quart):
    import peewee
    import funding.models.database
    models = peewee.Model.__subclasses__()
    for m in models:
        m.create_table()


async def _setup_openid(app: Quart):
    global openid
    if settings.OPENID_CFG:
        openid = OpenID(app, **settings.OPENID_CFG)


async def _setup_settings(app: Quart):
    global coin
    # simple configuration validation
    coin_names = ",".join(SUPPORTED_COINS.keys())
    if not settings.COIN_NAME:
        raise Exception("Please specify a coin name")

    ttf = settings.CAPTCHA_TTF
    if not os.path.exists(ttf):
        raise Exception(f"Font not found: {ttf}")

    if settings.COIN_NAME not in SUPPORTED_COINS:
        raise Exception(f"{settings.COIN_NAME} is not supported. "
                        f"Accepted names: {coin_names}")
    coin = COINS_LOOKUP[settings.COIN_NAME]

    if settings.COIN_RPC_AUTH:
        if ',' not in settings.COIN_RPC_AUTH:
            raise Exception("COIN_RPC_AUTH needs to be a tuple delimited by: ,")
        settings.COIN_RPC_AUTH = settings.COIN_RPC_AUTH.split(",", 1)

    if not settings.DOMAIN:
        raise Exception(
            "Please set variable 'DOMAIN' to the domain where this "
            "web application will run under. e.g: \"funding.domain.org\"")
    app.config['SERVER_NAME'] = settings.DOMAIN

    if settings.DISCOURSE_ENABLED:
        if not settings.DISCOURSE_DOMAIN:
            raise Exception("DISCOURSE_DOMAIN not set. e.g: forum.domain.org")
        if not settings.DISCOURSE_API_KEY:
            raise Exception("DISCOURSE_API_KEY not set.")
        settings.DISCOURSE_DOMAIN = settings.DISCOURSE_DOMAIN.replace("/", "")

    if isinstance(settings.OPENID_CFG, dict):
        for needle in ['client_id', 'client_secret', 'configuration']:
            if needle not in settings.OPENID_CFG:
                raise Exception(f"missing key '{needle}' in OPENID_CFG")


async def _setup_crypto(app: Quart):
    global crypto_provider
    providers = {
        "wownero": Wownero,
        "monero": Monero,
        "firo": Firo
    }

    crypto_provider = providers[settings.COIN_NAME]()
    crypto_provider.port = settings.COIN_RPC_PORT
    if settings.COIN_RPC_AUTH:
        crypto_provider.basic_auth = settings.COIN_RPC_AUTH


async def _setup_cache(app: Quart):
    global cache
    app.config['SESSION_TYPE'] = 'redis'
    app.config['SESSION_URI'] = settings.REDIS_URI
    Session(app)


async def _setup_tasks(app: Quart):
    """Schedules a series of tasks at an interval."""
    asyncio.create_task(discourse.fetch_task())
    asyncio.create_task(rates.rate_task())
    from funding.proposals.task import ProposalFundedTask
    asyncio.create_task(ProposalFundedTask().is_funded_task())


async def _setup_error_handlers(app: Quart):
    @app.errorhandler(500)
    async def page_error(e):
        return await render_template('error.html', code=500, msg="Error occurred"), 500

    @app.errorhandler(403)
    async def page_forbidden(e):
        return await render_template('error.html', code=403, msg="Forbidden"), 403

    @app.errorhandler(404)
    async def page_not_found(e):
        return await render_template('error.html', code=404, msg="Page not found"), 404


def create_app():
    global app
    app = Quart(__name__)

    app.logger.setLevel(logging.INFO)
    app.secret_key = settings.APP_SECRET

    @app.template_filter()
    def to_usd(val: float):
        global rates
        return rates.to_usd(val)

    @app.template_filter()
    def dt_human(val):
        return val.strftime('%Y-%m-%d %H:%M')

    @app.template_filter()
    def dt_ago(val):
        val = val.replace(tzinfo=None)
        return timeago.format(val, datetime.now())

    @app.template_filter()
    def hash_md5(val):
        if not val:
            return ""
        return hashlib.md5(val.encode()).hexdigest()

    @app.context_processor
    def template_variables():
        global openid
        from funding.models.database import User, UserRole
        from funding.utils.globals import GLOBALS
        now = datetime.now()

        data = {
            'settings': settings,
            'path': request.path,
            'coin': COINS_LOOKUP[settings.COIN_NAME],
            'rates': rates,
            'UserRole': UserRole,
            'user': g.user,
            'logged_in': g.user.is_anon is not True,
            **GLOBALS
        }

        if settings.OPENID_CFG:
            data['url_login'] = openid.endpoint_name_login

        return dict(year=now.year, **data)

    @app.errorhandler(RequestSchemaValidationError)
    async def handle_request_validation_error(error):
        return {"errors": error.validation_error.json()}, 400

    @app.before_serving
    async def startup():
        await _setup_error_handlers(app)
        await _setup_settings(app)
        await _setup_crypto(app)
        await _setup_cache(app)
        await _setup_openid(app)
        await _setup_postgres(app)
        await _setup_tasks(app)

        from funding.routes import bp_routes
        from funding.auth.routes import bp_auth
        from funding.proposals.routes import bp_proposals
        from funding.proposals.api import bp_proposals_api
        app.register_blueprint(bp_routes)
        app.register_blueprint(bp_auth)
        app.register_blueprint(bp_proposals)
        app.register_blueprint(bp_proposals_api)

        app.jinja_env.trim_blocks = True
        app.jinja_env.lstrip_blocks = True

        from funding.utils import crumbs

    @app.before_request
    async def set_request_ctx():
        from funding.models.database import User, UserRole
        g.user = User()
        g.user.role = UserRole.anonymous

        if '/static/' in request.url:
            return

        ses = session.get('user')
        if not isinstance(ses, dict):
            return

        try:
            user = User.by_uuid(ses['uuid'])
            if not user or not user.enabled:
                raise Exception("clear session")
            g.user = user
        except:
            session.clear()

    return app
