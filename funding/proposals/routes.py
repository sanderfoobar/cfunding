from slugify import slugify
from quart_schema import QuartSchema, validate_request, validate_response
from quart_schema.validation import DataSource
from quart import (
    render_template, request, redirect, url_for, current_app,
    jsonify, Blueprint, abort, flash, send_from_directory,
    session, make_response, Response, send_file, g
)

import settings
from funding import login_required, admin_required, moderator_required
from funding.factory import openid, crypto_provider, coin
from funding.utils.crumbs import *
from funding.utils.markdown import generate_html, MARKDOWN_PROPOSAL_DEFAULT
from funding.proposals.models import ProposalFundsTransfer
from funding.models.database import User, Proposal, ProposalStatus

bp_proposals = Blueprint('bp_proposals', __name__, url_prefix='/proposals/')


@bp_proposals.get("/")
async def proposal_root():
    return redirect(url_for('bp_routes.root'))


@bp_proposals.get("/<path:slug>")
async def view(slug: str):
    proposal = await Proposal.by_slug(slug)
    if not proposal:
        abort(404)

    if settings.VIEW_COUNTER:
        proposal.views += 1
        proposal.save()

    crumbs = proposal_crumbs_base(proposal)
    crumbs.append(Crumb(
        url=url_for('bp_proposals.view', slug=proposal.slug),
        name=proposal.title))

    return await render_template(
        "proposals/view.html",
        proposal=proposal,
        crumbs=crumbs)


@bp_proposals.get("/<path:slug>.md")
async def view_markdown(slug: str):
    proposal = await Proposal.by_slug(slug)
    if not proposal:
        abort(404)
    return proposal.markdown, {'Content-Type': 'text/plain'}


@bp_proposals.get("/<path:slug>/funds")
@admin_required
async def funds(slug: str = None):
    if not slug:
        abort(500)
    if not g.user.is_admin:
        return abort(403)
    proposal = await Proposal.by_slug(slug)
    if not proposal:
        abort(404)

    crumbs = proposal_crumbs_base(proposal)
    crumbs.append(Crumb(
        url=url_for('bp_proposals.view', slug=proposal.slug),
        name=proposal.title))
    crumbs.append(Crumb(
        url=url_for('bp_proposals.funds', slug=proposal.slug),
        name='Manage Funds'))

    return await render_template("proposals/funds.html", proposal=proposal, crumbs=crumbs)


@bp_proposals.post("/<path:slug>/funds/transfer")
@validate_request(ProposalFundsTransfer, source=DataSource.FORM)
@admin_required
async def funds_transfer(data: ProposalFundsTransfer, slug: str = None):
    from funding.factory import crypto_provider, discourse
    from funding.models.database import (
        Withdrawal, WithdrawalStatus, Event)
    if not slug:
        return abort(500)

    try:
        amount = float(data.amount)
    except:
        raise Exception("amount not valid")

    proposal = await Proposal.by_slug(slug)
    if not proposal:
        return abort(404)

    if session['captcha'] != data.captcha:
        raise Exception("bad captcha")

    spent_remaining = await proposal.spent_remaining
    if spent_remaining <= 0 or \
            amount > spent_remaining:
        raise Exception("Cannot spend this amount")

    destination = data.destination.strip()
    try:
        txid = await crypto_provider.send(
            address=destination,
            amount=amount)
    except Exception as ex:
        return f"Error sending to '{destination}': {ex}"

    Withdrawal.create(
        txid=txid,
        amount=amount,
        status=WithdrawalStatus.completed,
        proposal=proposal
    )

    message = f"Payment of {round(amount, 10)} " \
              f"{coin['ticker']} sent"

    Event.create(
        message=message,
        proposal=proposal,
        user=g.user)

    try:
        await discourse.new_post(proposal.discourse_topic_id, message)
    except:
        pass

    await flash(message)
    return redirect(url_for('bp_proposals.funds', slug=proposal.slug))


@bp_proposals.get("/edit")
@bp_proposals.get("/<path:slug>/edit")
@login_required
async def edit(slug: str = None):
    if slug:
        proposal = await Proposal.by_slug(slug)
        if not proposal:
            abort(404)

        if not proposal.can_edit(g.user):
            abort(403)
        crumbs = proposal_crumbs_base(proposal)
        crumbs.append(Crumb(
            name=proposal.title,
            url=url_for('bp_proposals.view', slug=proposal.slug)))
        crumbs.append(Crumb(
            name="Edit Proposal",
            url=url_for('bp_proposals.edit', slug=proposal.slug)))

        return await render_template(
            "proposals/edit.html",
            proposal=proposal,
            crumbs=crumbs)

    return await render_template("proposals/edit.html",
        crumbs=[crumb_home, crumb_disclaimer, crumb_proposal_add])


@bp_proposals.get("/disclaimer")
@login_required
async def disclaimer():
    return await render_template("proposals/rules.html",
        crumbs=[crumb_home, crumb_disclaimer])
