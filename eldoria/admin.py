import uuid
import time

import click
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import admin_required
from .db import get_db, utc_now
from .security import validate_csrf

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/login", methods=("GET", "POST"))
def login():
    error=None
    if request.method == "POST":
        from .account_security import consume_limit, establish_session, password_matches
        validate_csrf()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not consume_limit('admin-login',email):
            return render_template('admin/login.html',title='Acesso administrativo',error='Muitas tentativas. Aguarde 15 minutos.'),429
        user = get_db().execute("SELECT * FROM users WHERE email = ? AND role = 'ADMIN'", (email,)).fetchone()
        if not password_matches(user,password):
            error='Credenciais administrativas inválidas.'
        else:
            security=get_db().execute('SELECT totp_secret FROM user_security WHERE user_id=?',(user['id'],)).fetchone()
            if security and security['totp_secret']:
                csrf=session.get('csrf_token')
                session.clear()
                session.update(pending_admin=user['id'],pending_at=int(time.time()))
                if csrf:
                    session['csrf_token']=csrf
                return redirect(url_for('account_security.challenge'))
            establish_session(user)
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html", title="Acesso administrativo", admin_layout=True,error=error)


@bp.get("/")
@admin_required
def index():
    return redirect(url_for("admin.dashboard"))


@bp.get("/dashboard")
@admin_required
def dashboard():
    from .management import overview
    return overview()


@bp.get("/api/summary")
@admin_required
def api_summary():
    from .management import summary
    return summary()


@click.command("create-admin")
@click.option("--name", prompt=True)
@click.option("--email", prompt=True)
@click.password_option()
def create_admin_command(name, email, password):
    """Cria um administrador sem expor cadastro na interface pública."""
    db = get_db()
    db.execute(
        "INSERT INTO users (id, name, email, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, 'ADMIN', 'ACTIVE', ?)",
        (str(uuid.uuid4()), name.strip(), email.strip().lower(), generate_password_hash(password), utc_now()),
    )
    db.commit()
    click.echo("Administrador criado.")
