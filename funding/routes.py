import os
from uuid import uuid4
from typing import Optional

from dataclasses import dataclass
import aiohttp
from pydantic import BaseModel, EmailStr
from quart_schema import QuartSchema, validate_request, validate_response
from quart_schema.validation import DataSource
from quart import (
    render_template, request, redirect, url_for, current_app,
    jsonify, Blueprint, abort, flash, send_from_directory,
    session, make_response, Response, send_file, g
)

import settings
from funding import login_required
from funding.factory import openid
from funding.utils import get_ip
from funding.utils.qr import QrCodeGenerator, QR_LOCK
from funding.utils.crumbs import *
from funding.utils.markdown import generate_html
from funding.utils.gravatar import gravatar_download
from funding.models.database import User, Proposal, ProposalStatus, ProposalCategory

bp_routes = Blueprint('bp_routes', __name__)

proposals_by_status = lambda status: Proposal.select()\
    .filter(Proposal.status == status)\
    .order_by(Proposal.created.desc())


@bp_routes.get("/")
async def root():
    q = Proposal.select()
    if not g.user.is_moderator:
        q = q.filter(Proposal.status != ProposalStatus.disabled)
    proposals = q.order_by(Proposal.created.desc())

    return await render_template('index.html', proposals=proposals)


@bp_routes.get("/ideas/")
async def ideas():
    proposals = proposals_by_status(ProposalStatus.idea)
    return await render_template(
        'proposals.html',
        title='Ideas',
        proposals=proposals,
        state=ProposalStatus.idea,
        crumbs=[crumb_home, crumb_ideas]
    )


@bp_routes.get("/funding-required/")
async def funding():
    proposals = proposals_by_status(ProposalStatus.funding_required)
    return await render_template(
        'proposals.html',
        title='Funding required',
        proposals=proposals,
        state=ProposalStatus.funding_required,
        crumbs=[crumb_home, crumb_funding]
    )


@bp_routes.get("/work-in-progress/")
async def wip():
    proposals = proposals_by_status(ProposalStatus.wip)
    return await render_template(
        'proposals.html',
        title='Work in Progress',
        proposals=proposals,
        state=ProposalStatus.wip,
        crumbs=[crumb_home, crumb_wip])


@bp_routes.get("/completed-proposals/")
async def completed():
    proposals = proposals_by_status(ProposalStatus.completed)
    return await render_template(
        'proposals.html',
        title='Completed',
        proposals=proposals,
        state=ProposalStatus.completed,
        crumbs=[crumb_home, crumb_completed])


@bp_routes.get("/search")
async def search():
    needle = request.args.get('username')
    if needle:
        if len(needle) <= 1:
            raise Exception("Search term needs to be longer")

        users = [u for u in await User.search(needle)]
        if users:
            return await render_template('search_results.html', users=users)
        else:
            return await render_template('search_results.html')

    q = User.select()
    q = q.where(User.address.is_null(False))
    q = q.limit(100)

    users = [u for u in q]
    return await render_template('search.html', users=users)


@bp_routes.get("/users")
async def users_page():
    q = User.select()
    if g.user.is_anon:
        q = q.filter(User.enabled == True)

    users = q.order_by(User.created.desc())
    return await render_template('users.html', users=users)


@bp_routes.get("/user/<path:name>")
async def user_page(name: str):
    if not name or len(name) <= 1:
        raise Exception("invalid name")

    try:
        u = User.select().where(
            User.username == name
        ).get()
    except:
        u = None

    proposals = []
    if u:
        q = Proposal.select()
        if not g.user.is_moderator:
            q = q.filter(Proposal.status != ProposalStatus.disabled)

        q = q.filter(Proposal.user == u)
        proposals = q.order_by(Proposal.created.desc())

    return await render_template(
        'user.html',
        proposals=proposals,
        u=u)


@bp_routes.route("/how-to-contribute")
async def how_to_contribute():
    return await render_template(
        'how.html',
        crumbs=[crumb_home, crumb_how])


@bp_routes.route("/what-is-fcs")
async def what_is_fcs():
    return await render_template(
        'what.html',
        crumbs=[crumb_home, crumb_what])


@bp_routes.route("/about")
async def about():
    return await render_template(
        'about.html',
        crumbs=[crumb_home, crumb_about])


@bp_routes.route("/api/1/proposals")
async def api_proposals_list():
    q = Proposal.select()
    q = q.filter(Proposal.status != ProposalStatus.disabled)
    proposals: List[Proposal] = q.order_by(Proposal.created.desc())

    data = []
    for p in proposals:
        item = {
            "user": p.user.username,
            "headline": p.title,
            "content": p.html,
            "markdown": p.markdown,
            "slug": p.slug,
            "discourse_topic_link": None,
            "category": ProposalCategory.to_string(p.category),
            "status": ProposalStatus.to_string(p.status),
            "views": None,
            "addr_donation": p.crypto_address_donation,
            "date_posted": str(p.created),
            "date_updated": str(p.modified),
            "date_posted_epoch": p.created.timestamp(),
            "funded_pct": 0,
            "funds_target": p.funds_target
        }

        if settings.VIEW_COUNTER:
            item["views"] = p.views

        if p.discourse_topic_link:
            item['discourse_topic_link'] = p.discourse_topic_link

        try:
            item["funded_pct"] = round(await p.raised_pct, 4)
        except Exception as ex:
            msg = f"API funded_pct error: {ex}"
            current_app.logger.error(msg)
            raise Exception(msg)

        data.append(item)

    return jsonify({"data": data})


@bp_routes.get('/lib/qr/<path:address>')
async def utils_qr_image(address: str):
    """
    Generate a QR image. Subject to IP throttling.
    :param address: valid receiving address
    :return:
    """
    async with QR_LOCK:
        cache = current_app.session_interface
        qr = QrCodeGenerator()
        if not qr.exists(address):
            # create a new QR code
            ip = get_ip()
            cache_key = 'qr_ip_%s' % ip
            hit = await cache.get(cache_key)

            if hit and ip not in ['127.0.0.1', 'localhost']:
                return Response('Wait a bit before generating a new QR', 403)

            await cache.set(cache_key, "val", expiry=3)

            created = qr.create(address)
            if not created:
                raise Exception('Could not create QR code')

        from_dir = os.path.join(current_app.static_folder, 'qr')
        return await send_from_directory(from_dir, f'{address}.png')


@bp_routes.get('/lib/gravatar/')
@bp_routes.get('/lib/gravatar/<path:hash>')
async def utils_gravatar(hash: str = None):
    """:return: path to image"""
    _dir = os.path.join(current_app.static_folder, "gravatar")
    fn = f"{hash}.png"
    dest = os.path.join(_dir, fn)

    try:
        if not os.path.exists(dest):
            await gravatar_download(
                hash=hash,
                save_to_dir=_dir,
                filename=fn)

        return await send_from_directory(
            directory=_dir,
            file_name=fn
        )

    except Exception as ex:
        current_app.logger.error(f"Unable to fetch gravatar image: {ex}")

    return await send_from_directory(
        directory=current_app.static_folder,
        file_name='user.png'
    )


@bp_routes.get("/lib/captcha")
def utils_captcha():
    font = settings.CAPTCHA_TTF
    secret = uuid4().hex[:4]

    from funding.utils.captcha import FundingCaptcha
    image = FundingCaptcha(fonts=[font])
    data = image.generate(secret)

    session['captcha'] = secret
    return Response(data, mimetype='image/jpg')


class MarkdownToHtmlPost(BaseModel):
    markdown: str


@bp_routes.post("/lib/markdown/html")
@validate_request(MarkdownToHtmlPost, source=DataSource.JSON)
def utils_markdown_to_html(data: MarkdownToHtmlPost):
    if len(data.markdown) >= 20000:
        raise Exception("")
    html = generate_html(data.markdown)
    return jsonify({
        "html": html
    })

