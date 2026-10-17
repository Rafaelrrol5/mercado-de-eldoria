import re
import sqlite3
import uuid
from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, utc_now
from .security import csrf_protected, safe_redirect_target

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None if user_id is None else get_db().execute(
        "SELECT u.id,u.name,u.email,u.role,u.status,u.game_identifier,s.email_verified_at,COALESCE(s.session_version,0) session_version,(s.totp_secret IS NOT NULL) has_totp FROM users u LEFT JOIN user_security s ON s.user_id=u.id WHERE u.id=?", (user_id,)
    ).fetchone()
    if g.user is not None and (g.user["status"] != "ACTIVE" or session.get('session_version',0)!=g.user['session_version'] or (g.user['role']=='ADMIN' and g.user['has_totp'] and not session.get('admin_2fa'))):
        session.clear()
        g.user = None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", retorno=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("admin.login"))
        if g.user["role"] != "ADMIN":
            abort(404)
        return view(*args, **kwargs)
    return wrapped


@bp.route("/login", methods=("GET", "POST"))
def login():
    error=None
    if request.method == "POST":
        from .account_security import consume_limit, establish_session, password_matches
        from .security import validate_csrf
        validate_csrf()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not consume_limit('customer-login',email):
            return render_template('auth/login.html',title='Entrar',error='Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.'),429
        user = get_db().execute("SELECT * FROM users WHERE email = ? AND role = 'CUSTOMER'", (email,)).fetchone()
        if not password_matches(user,password):
            error='E-mail ou senha inválidos.'
        else:
            establish_session(user)
            return redirect(safe_redirect_target(request.args.get("retorno"), url_for("store.account")))
    return render_template("auth/login.html", title="Entrar",error=error)


@bp.route("/cadastro", methods=("GET", "POST"))
def register():
    errors={}
    if request.method == "POST":
        from .account_security import consume_limit, deliver, ensure_security, establish_session, password_error
        from .security import validate_csrf
        validate_csrf()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        game_identifier = request.form.get("game_identifier", "").strip() or None
        if not consume_limit('register',request.remote_addr or '',5,900):
            return render_template('auth/register.html',title='Criar conta',errors={'form':'Muitas tentativas. Aguarde alguns minutos.'}),429
        error = None
        if len(name) < 2 or len(name) > 80:
            error = "Informe um nome válido."
            errors['name']=error
        elif not EMAIL_RE.fullmatch(email) or len(email) > 254:
            error = "Informe um email válido."
            errors['email']=error
        elif password_error(password):
            error=password_error(password)
            errors['password']=error
        elif game_identifier and len(game_identifier) > 80:
            error = "Identificador do jogo inválido."
            errors['game_identifier']=error
        if error:
            pass
        else:
            try:
                user_id = str(uuid.uuid4())
                db = get_db()
                db.execute(
                    "INSERT INTO users (id, name, email, password_hash, role, status, game_identifier, created_at) VALUES (?, ?, ?, ?, 'CUSTOMER', 'ACTIVE', ?, ?)",
                    (user_id, name, email, generate_password_hash(password), game_identifier, utc_now()),
                )
                db.commit()
                ensure_security(user_id)
                db.commit()
                user=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
                establish_session(user)
                sent=deliver(user,'verify')
                flash("Conta criada com sucesso.", "success")
                flash('Confira o link de confirmação do seu e-mail.' if sent else 'A conta foi criada, mas o e-mail não pôde ser enviado. Você pode solicitar outro link na sua conta.','success' if sent else 'error')
                return redirect(url_for("store.account"))
            except sqlite3.IntegrityError:
                get_db().rollback()
                errors['email']='Este e-mail já está cadastrado. Entre ou recupere sua senha.'
    return render_template("auth/register.html", title="Criar conta",errors=errors)


@bp.post("/logout")
@csrf_protected
def logout():
    session.clear()
    return redirect(url_for("store.home"))

