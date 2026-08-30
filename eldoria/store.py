import uuid
from datetime import datetime

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

from .auth import login_required
from .db import get_db, utc_now
from .products import CATEGORIES, CLASSES, PRODUCTS, RARITIES, format_brl, get_product
from .security import csrf_protected, safe_redirect_target, validate_csrf

bp = Blueprint("store", __name__)


def cart_data():
    raw = session.get("cart", {})
    lines = []
    for slug, quantity in raw.items():
        product = get_product(slug)
        if product and isinstance(quantity, int) and quantity > 0:
            lines.append({"product": product, "quantity": quantity, "line_total": product["price_cents"] * quantity})
    return lines


def save_quantity(slug, quantity):
    cart = dict(session.get("cart", {}))
    if quantity <= 0:
        cart.pop(slug, None)
    else:
        cart[slug] = min(quantity, 20)
    session["cart"] = cart
    session.modified = True


@bp.get("/")
def home():
    return render_template("home.html", title="Mercado de Eldoria")


@bp.get("/loja")
def shop():
    return render_template(
        "shop.html", title="Loja de Eldoria", products=PRODUCTS, categories=CATEGORIES,
        rarities=RARITIES, classes=CLASSES, initial_offers=request.args.get("filtro") == "ofertas",
    )


@bp.get("/produto/<slug>")
def product_detail(slug):
    product = get_product(slug)
    if not product:
        abort(404)
    return render_template("product.html", title=product["name"], product=product)


@bp.get("/bolsa")
def cart():
    lines = cart_data()
    total = sum(line["line_total"] for line in lines)
    return render_template("cart.html", title="Bolsa do Aventureiro", lines=lines, total=total)


@bp.post("/bolsa/adicionar")
@csrf_protected
def add_to_cart():
    slug = request.form.get("slug", "")
    product = get_product(slug)
    if not product:
        abort(404)
    try:
        quantity = max(1, min(int(request.form.get("quantity", 1)), 20))
    except ValueError:
        quantity = 1
    current = int(session.get("cart", {}).get(slug, 0))
    save_quantity(slug, current + quantity)
    flash(f"{product['name']} foi adicionado à Bolsa.", "success")
    target = safe_redirect_target(request.form.get("next") or request.referrer, url_for("store.cart"))
    return redirect(target)


@bp.post("/bolsa/atualizar")
@csrf_protected
def update_cart():
    slug = request.form.get("slug", "")
    if not get_product(slug):
        abort(404)
    try:
        quantity = int(request.form.get("quantity", 1))
    except ValueError:
        quantity = 1
    save_quantity(slug, quantity)
    return redirect(url_for("store.cart"))


@bp.get("/como-funciona")
def how_it_works():
    return render_template("how.html", title="Como funciona")


@bp.route("/suporte", methods=("GET", "POST"))
def support():
    success = False
    selected = request.form.get("category", request.args.get("categoria", "Outro problema"))
    if request.method == "POST":
        if g.user is None:
            flash("Entre na sua conta para enviar e acompanhar solicitações.", "error")
            return redirect(url_for("auth.login", retorno=url_for("store.support")))
        validate_csrf()
        values = {key: request.form.get(key, "").strip() for key in ("name", "email", "category", "order_number", "subject", "description")}
        errors = []
        if not 2 <= len(values["name"]) <= 80: errors.append("Informe seu nome.")
        if "@" not in values["email"] or len(values["email"]) > 254: errors.append("Informe um email válido.")
        if not 5 <= len(values["subject"]) <= 120: errors.append("O assunto deve ter entre 5 e 120 caracteres.")
        if not 20 <= len(values["description"]) <= 3000: errors.append("A descrição deve ter entre 20 e 3000 caracteres.")
        if len(values["order_number"]) > 40: errors.append("Número de pedido inválido.")
        if errors:
            for error in errors: flash(error, "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO support_tickets (id, user_id, order_number, name, email, category, subject, description, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)",
                (str(uuid.uuid4()), g.user["id"], values["order_number"] or None, values["name"], values["email"], values["category"], values["subject"], values["description"], utc_now()),
            )
            db.commit()
            success = True
    return render_template("support.html", title="Central de Suporte", selected_category=selected, success=success)


@bp.get("/conta")
@login_required
def account():
    orders = get_db().execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (g.user["id"],)).fetchall()
    tickets = get_db().execute("SELECT * FROM support_tickets WHERE user_id = ? ORDER BY created_at DESC", (g.user["id"],)).fetchall()
    return render_template("account.html", title="Minha conta", orders=orders, tickets=tickets)


@bp.route("/checkout", methods=("GET", "POST"))
@login_required
def checkout():
    lines = cart_data()
    if not lines:
        return redirect(url_for("store.cart"))
    total = sum(line["line_total"] for line in lines)
    if request.method == "POST":
        validate_csrf()
        game_identifier = request.form.get("game_identifier", "").strip()
        if not 3 <= len(game_identifier) <= 80:
            flash("Informe a conta do jogo que receberá os itens.", "error")
        else:
            order_id = str(uuid.uuid4())
            order_number = f"ELD-{datetime.now():%y%m%d}-{uuid.uuid4().hex[:6].upper()}"
            db = get_db()
            db.execute(
                "INSERT INTO orders (id, number, user_id, game_identifier, subtotal_cents, total_cents, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'AWAITING_PAYMENT', ?)",
                (order_id, order_number, g.user["id"], game_identifier, total, total, utc_now()),
            )
            for line in lines:
                product = line["product"]
                db.execute(
                    "INSERT INTO order_items (id, order_id, product_slug, product_name, unit_price_cents, quantity) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), order_id, product["slug"], product["name"], product["price_cents"], line["quantity"]),
                )
            db.execute("UPDATE users SET game_identifier = ? WHERE id = ?", (game_identifier, g.user["id"]))
            db.commit()
            session["cart"] = {}
            return render_template("order_pending.html", title="Pedido criado", order_number=order_number, total=total)
    return render_template("checkout.html", title="Finalizar compra", lines=lines, total=total)


@bp.get("/termos")
def terms():
    return render_template("legal.html", title="Termos de uso", heading="Termos de uso")


@bp.get("/privacidade")
def privacy():
    return render_template("legal.html", title="Privacidade", heading="Política de privacidade")
