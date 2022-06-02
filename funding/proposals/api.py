from slugify import slugify
from quart_schema import QuartSchema, validate_request, validate_response
from quart_schema.validation import DataSource
from quart import (
    render_template, request, redirect, url_for, current_app,
    jsonify, Blueprint, abort, flash, send_from_directory,
    session, make_response, Response, send_file, g
)

import settings
from funding import login_required
from funding.factory import openid, crypto_provider
from funding.utils.crumbs import *
from funding.utils.markdown import generate_html, MARKDOWN_PROPOSAL_DEFAULT
from funding.proposals.models import ProposalUpsert, CommentPost, CommentPostReply
from funding.models.database import User, Proposal, ProposalStatus

bp_proposals_api = Blueprint('bp_proposals_api', __name__, url_prefix='/api/proposals')


@bp_proposals_api.post("/upsert")
@validate_request(ProposalUpsert, source=DataSource.JSON)
@login_required
async def upsert(data: ProposalUpsert):
    """new/modify proposal"""
    try:
        proposal = await Proposal.upsert(data)
    except Exception as ex:
        current_app.logger.error(f"Proposal.upsert error: {ex}")
        return jsonify({"error": "unknown error, see web application log"})

    url = url_for('bp_proposals.view', slug=proposal.slug)
    return jsonify({"url": url})
