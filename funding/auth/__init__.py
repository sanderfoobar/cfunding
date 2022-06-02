import peewee
from quart import session, redirect, url_for, Blueprint, render_template, request

import settings
from funding import login_required
from funding.factory import openid
from funding.models.database import User


if openid:
    @openid.after_token()
    async def handle_user_login(resp: dict):
        access_token = resp["access_token"]
        openid.verify_token(access_token)

        user = await openid.user_info(access_token)
        username = user['preferred_username']
        uid = user['sub']

        try:
            user = User.select().where(User.id == uid).get()
        except peewee.DoesNotExist:
            user = None

        if not user:
            # create new user if it does not exist yet
            user = User.create(id=uid, username=username)

        # user is now logged in
        session['user'] = await user.to_json()
        return redirect(url_for('bp_routes.dashboard'))
