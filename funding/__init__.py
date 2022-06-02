from quart import session, abort, url_for, redirect, g, flash

from functools import wraps


def login_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if g.user.is_anon:
            await flash("this action requires a login")
            return redirect(url_for('bp_auth.login'))

        if not g.user.enabled:
            await flash("this action requires an enabled account")
            return redirect(url_for('bp_auth.login'))

        return await func(*args, **kwargs)
    return wrapper


def moderator_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if g.user.is_anon:
            await flash("this action requires a login")
            return redirect(url_for('bp_auth.login'))

        if not g.user.enabled:
            await flash("this action requires an enabled account")
            return redirect(url_for('bp_auth.login'))

        if not g.user.is_moderator:
            await flash("this action requires a moderator or admin")
            return redirect(url_for('bp_auth.login'))

        return await func(*args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if g.user.is_anon:
            await flash("this action requires a login")
            return redirect(url_for('bp_auth.login'))

        if not g.user.enabled:
            await flash("this action requires an enabled account")
            return redirect(url_for('bp_auth.login'))

        if not g.user.is_admin:
            await flash("this action requires an admin")
            return redirect(url_for('bp_auth.login'))

        return await func(*args, **kwargs)
    return wrapper
