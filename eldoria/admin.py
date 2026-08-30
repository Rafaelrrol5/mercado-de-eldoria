import uuid

import click
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import admin_required
from .db import get_db, utc_now
from .security import validate_csrf

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        validate_csrf()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ? AND role = 'ADMIN'", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password) or user["status"] != "ACTIVE":
            flash("Credenciais administrativas inválidas.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html", title="Acesso administrativo", admin_layout=True)


@bp.get("/")
@admin_required
def index():
    return redirect(url_for("admin.dashboard"))


@bp.get("/dashboard")
@admin_required
def dashboard():
    db = get_db()
    counts = {
        "customers": db.execute("SELECT COUNT(*) FROM users WHERE role = 'CUSTOMER'").fetchone()[0],
        "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "tickets": db.execute("SELECT COUNT(*) FROM support_tickets WHERE status != 'CLOSED'").fetchone()[0],
    }
    return render_template("admin/dashboard.html", title="Painel", admin_layout=True, counts=counts)


@bp.get("/api/summary")
@admin_required
def api_summary():
    return {"ok": True}


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
