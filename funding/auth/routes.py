import bcrypt

import peewee
from quart import session, redirect, url_for, Blueprint, render_template, request, abort, flash
from dataclasses import dataclass
from quart_schema.validation import DataSource
from quart_schema import QuartSchema, validate_request, validate_response
from email_validator import validate_email, EmailNotValidError

import settings
from funding import login_required, admin_required, moderator_required
from funding.factory import openid
from funding.auth.models import UserRegisterForm
from funding.models.database import User, UserRole


bp_auth = Blueprint('bp_auth', __name__)


@bp_auth.route("/auth/login/", methods=['GET', 'POST'])
async def login():
    if settings.OPENID_CFG:
        if request.method == "POST":
            raise Exception("GET only")
        return redirect(url_for(openid.endpoint_name_login))
    elif request.method == "POST":
        blob = await request.form
        username = blob.get('username')
        password = blob.get('password')

        try:
            if not username or not password:
                raise Exception("No credentials")
            user = User.validate(username, password)
            if not user.enabled:
                await flash("user is disabled")
                return await render_template("login.html")
            session['user'] = await user.to_json()
            await flash("Successful log-in")
            return redirect(url_for('bp_routes.root'))
        except Exception as ex:
            await flash("login failed")
            return await render_template("login.html")
    return await render_template('login.html')


@bp_auth.route("/auth/forgot/", methods=['GET', 'POST'])
async def forgot():
    message = "'Forgot password' functionality is currently unsupported. Please ask an admin for a password change."
    return await render_template("error.html", message=message, code=404)


@bp_auth.route("/auth/user/<path:name>/admin/toggle", methods=["POST"])
@moderator_required
async def user_admin_toggle(name: str):
    try:
        user = User.select().filter(User.username == name).get()
    except:
        return abort(404)

    if user.role == UserRole.admin:
        user.role = UserRole.user
    else:
        user.role = UserRole.admin
    user.save()

    await flash(f"User is admin: {user.role == UserRole.admin}")
    return redirect(url_for('bp_routes.user_page', name=name))


@bp_auth.route("/auth/user/<path:name>/moderator/toggle", methods=["POST"])
@moderator_required
async def user_moderator_toggle(name: str):
    try:
        user = User.select().filter(User.username == name).get()
    except:
        return abort(404)

    if user.role == UserRole.moderator:
        user.role = UserRole.user
    else:
        user.role = UserRole.moderator
    user.save()

    await flash(f"User is moderator: {user.role == UserRole.moderator}")
    return redirect(url_for('bp_routes.user_page', name=name))


@bp_auth.route("/auth/user/<path:name>/enabled/toggle", methods=["POST"])
@moderator_required
async def user_enabled_toggle(name: str):
    try:
        user = User.select().filter(User.username == name).get()
    except:
        return abort(404)

    if user.is_admin:
        return "cannot enable/disable an admin user"

    user.enabled = not user.enabled
    user.save()

    if user.enabled:
        msg = f"user '{user.username}' has been unbanned"
    else:
        msg = f"user '{user.username}' has been banned"

    await flash(msg)
    return redirect(url_for('bp_routes.user_page', name=name))


@bp_auth.get("/auth/register/")
async def register():
    return await render_template("register.html")


@bp_auth.post("/auth/register/")
@validate_request(UserRegisterForm, source=DataSource.FORM)
async def register_post(data: UserRegisterForm):
    if data.captcha != session['captcha']:
        await flash("Invalid captcha!")
        return await render_template('register.html', username=data.username, password=data.password, email=data.email)

    if len(data.password) <= 4:
        await flash("Password length must exceed 5 characters")
        return await render_template('register.html', username=data.username, password=data.password, email=data.email)

    try:
        User.select().where(User.username == data.username).get()
        await flash("Username taken.")
        return await render_template('register.html', username=data.username, password=data.password, email=data.email)
    except peewee.DoesNotExist:
        pass

    user_count = User.select().count()
    hashed = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt())
    user = User.create(
        username=data.username,
        password=hashed,
        mail=data.email,
        role=UserRole.admin if user_count == 0 else UserRole.user
    )

    session['user'] = await user.to_json()
    await flash(f"Welcome {user.username}!")
    return redirect(url_for('bp_routes.root'))


@bp_auth.route("/logout")
@login_required
async def logout():
    session['user'] = None
    return redirect(url_for('bp_routes.root'))
