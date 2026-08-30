import re
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
        "SELECT id, name, email, role, status, game_identifier FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if g.user is not None and g.user["status"] != "ACTIVE":
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
    if request.method == "POST":
        from .security import validate_csrf
        validate_csrf()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ? AND role = 'CUSTOMER'", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password) or user["status"] != "ACTIVE":
            flash("Email ou senha inválidos.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(safe_redirect_target(request.args.get("retorno"), url_for("store.account")))
    return render_template("auth/login.html", title="Entrar")


@bp.route("/cadastro", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        from .security import validate_csrf
        validate_csrf()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        game_identifier = request.form.get("game_identifier", "").strip() or None
        error = None
        if len(name) < 2 or len(name) > 80:
            error = "Informe um nome válido."
        elif not EMAIL_RE.fullmatch(email) or len(email) > 254:
            error = "Informe um email válido."
        elif len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            error = "A senha deve ter ao menos 8 caracteres, letras e números."
        elif game_identifier and len(game_identifier) > 80:
            error = "Identificador do jogo inválido."
        if error:
            flash(error, "error")
        else:
            try:
                user_id = str(uuid.uuid4())
                db = get_db()
                db.execute(
                    "INSERT INTO users (id, name, email, password_hash, role, status, game_identifier, created_at) VALUES (?, ?, ?, ?, 'CUSTOMER', 'ACTIVE', ?, ?)",
                    (user_id, name, email, generate_password_hash(password), game_identifier, utc_now()),
                )
                db.commit()
                session.clear()
                session["user_id"] = user_id
                flash("Conta criada com sucesso.", "success")
                return redirect(url_for("store.account"))
            except Exception as exc:
                if "UNIQUE" not in str(exc).upper():
                    raise
                flash("Este email já está cadastrado.", "error")
    return render_template("auth/register.html", title="Criar conta")


@bp.post("/logout")
@csrf_protected
def logout():
    session.clear()
    return redirect(url_for("store.home"))

