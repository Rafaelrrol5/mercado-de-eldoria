import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from .auth import admin_required, login_required
from .db import get_db, utc_now
from .products import CATEGORIES, RARITIES, CLASSES, get_products
from .security import validate_csrf
from .game_release import GAME_INFO

bp = Blueprint('management', __name__)
PAYMENTS = {'PENDING': 'Pendente', 'PAID': 'Pago', 'REFUNDED': 'Reembolsado', 'CANCELLED': 'Cancelado'}
DELIVERIES = {'PENDING': 'Pendente', 'PROCESSING': 'Em preparação', 'DELIVERED': 'Entregue'}
TICKETS = {'OPEN': 'Aberto', 'IN_PROGRESS': 'Em atendimento', 'CLOSED': 'Resolvido'}


@bp.before_request
def upload_limit():
    if request.endpoint in ('management.game_admin', 'management.product_edit'):
        request.max_content_length = 512 * 1024 * 1024 if request.endpoint == 'management.game_admin' else 6 * 1024 * 1024


def audit(action, target, details=''):
    get_db().execute('INSERT INTO admin_events VALUES (?, ?, ?, ?, ?, ?)',
                     (str(uuid.uuid4()), g.user['id'], action, target, details, utc_now()))


def required_row(table, identity):
    # Table names are supplied exclusively by internal callers.
    row = get_db().execute(f'SELECT * FROM {table} WHERE id=?', (identity,)).fetchone()
    if row is None:
        abort(404)
    return row


def summary():
    db = get_db()
    return dict(customers=db.execute("SELECT COUNT(DISTINCT lower(trim(email))) FROM users WHERE role='CUSTOMER'").fetchone()[0],
                orders=db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
                tickets=db.execute("SELECT COUNT(*) FROM support_tickets WHERE status!='CLOSED'").fetchone()[0],
                pending=db.execute("SELECT COUNT(*) FROM orders WHERE status IN ('AWAITING_PAYMENT','PAID','PROCESSING')").fetchone()[0])


def page(template, **values):
    return render_template('admin/' + template, payments=PAYMENTS, deliveries=DELIVERIES, ticket_statuses=TICKETS, **values)


def overview():
    db = get_db()
    from .finance import financial_report, report_period
    return page('dashboard.html', title='Visão geral', counts=summary(), finance=financial_report(*report_period()),
                orders=db.execute("SELECT o.*, u.name FROM orders o JOIN users u ON u.id=o.user_id WHERE o.status IN ('AWAITING_PAYMENT','PAID','PROCESSING') ORDER BY o.created_at DESC LIMIT 8").fetchall(),
                tickets=db.execute("SELECT * FROM support_tickets WHERE status!='CLOSED' ORDER BY created_at LIMIT 8").fetchall(),
                events=db.execute('SELECT e.*, u.name FROM admin_events e JOIN users u ON u.id=e.admin_id ORDER BY e.created_at DESC LIMIT 8').fetchall())


@bp.get('/admin/orders')
@admin_required
def orders():
    q = request.args.get('q', '').strip()[:100]
    state = request.args.get('status', '')
    rows = get_db().execute("SELECT o.*, u.name, u.email FROM orders o JOIN users u ON u.id=o.user_id WHERE (o.number LIKE ? OR u.email LIKE ? OR u.name LIKE ?) AND (?='' OR o.status=?) ORDER BY o.created_at DESC LIMIT 200", ('%' + q + '%',) * 3 + (state, state)).fetchall()
    return page('orders.html', title='Pedidos', rows=rows, q=q, state=state)


@bp.route('/admin/orders/<identity>', methods=['GET', 'POST'])
@admin_required
def order_detail(identity):
    db = get_db()
    order = required_row('orders', identity)
    if request.method == 'POST':
        validate_csrf()
        payment, delivery = request.form.get('payment'), request.form.get('delivery')
        note = request.form.get('note', '').strip()
        if payment not in PAYMENTS or delivery not in DELIVERIES or len(note) > 2000:
            abort(400)
        db.execute('BEGIN IMMEDIATE')
        order = required_row('orders', identity)
        if payment != 'PAID' and delivery != 'PENDING':
            db.rollback()
            flash('Somente pedidos pagos podem ser preparados ou entregues.', 'error')
        else:
            from .finance import record_payment
            try:
                record_payment(order, payment)
            except ValueError as exc:
                db.rollback()
                flash(str(exc), 'error')
                return redirect(url_for('management.order_detail', identity=identity))
            status = ('DELIVERED' if delivery == 'DELIVERED' else 'PROCESSING' if delivery == 'PROCESSING' else 'PAID') if payment == 'PAID' else {'PENDING': 'AWAITING_PAYMENT', 'CANCELLED': 'CANCELLED', 'REFUNDED': 'REFUNDED'}[payment]
            previous = db.execute('SELECT * FROM order_management WHERE order_id=?', (identity,)).fetchone()
            db.execute('INSERT INTO order_management VALUES (?, ?, ?, ?) ON CONFLICT(order_id) DO UPDATE SET payment=excluded.payment, delivery=excluded.delivery, note=excluded.note', (identity, payment, delivery, note))
            db.execute('UPDATE orders SET status=? WHERE id=?', (status, identity))
            audit('Pedido atualizado', order['number'], json.dumps({'before': dict(previous) if previous else {'status': order['status']}, 'after': {'payment': payment, 'delivery': delivery, 'note': note}}, ensure_ascii=False))
            db.commit()
            flash('Pedido atualizado. O registro é manual e não realiza cobrança ou entrega automática.', 'success')
            return redirect(url_for('management.order_detail', identity=identity))
    state = db.execute('SELECT * FROM order_management WHERE order_id=?', (identity,)).fetchone()
    if state is None:
        state = {'payment': 'PAID' if order['status'] in ('PAID','PROCESSING','DELIVERED') else order['status'] if order['status'] in ('REFUNDED','CANCELLED') else 'PENDING', 'delivery': 'DELIVERED' if order['status']=='DELIVERED' else 'PROCESSING' if order['status']=='PROCESSING' else 'PENDING', 'note': ''}
    return page('order.html', title=order['number'], order=order, state=state,
                customer=required_row('users', order['user_id']),
                lines=db.execute('SELECT * FROM order_items WHERE order_id=?', (identity,)).fetchall())


@bp.get('/admin/customers')
@admin_required
def customers():
    q = request.args.get('q', '').strip()[:100]
    rows = get_db().execute("SELECT * FROM users WHERE role='CUSTOMER' AND (name LIKE ? OR email LIKE ?) ORDER BY created_at DESC LIMIT 200", ('%' + q + '%',) * 2).fetchall()
    return page('customers.html', title='Clientes', rows=rows, q=q)


@bp.route('/admin/customers/<identity>', methods=['GET', 'POST'])
@admin_required
def customer_detail(identity):
    db = get_db()
    customer = required_row('users', identity)
    if customer['role'] != 'CUSTOMER':
        abort(404)
    if request.method == 'POST':
        validate_csrf()
        state = request.form.get('status')
        if state not in ('ACTIVE', 'SUSPENDED'):
            abort(400)
        db.execute('UPDATE users SET status=? WHERE id=?', (state, identity))
        audit('Status do cliente', identity, customer['status'] + ' → ' + state)
        db.commit()
        flash('Status da conta atualizado.', 'success')
        return redirect(url_for('management.customer_detail', identity=identity))
    return page('customer.html', title=customer['name'], customer=customer,
                orders=db.execute('SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC', (identity,)).fetchall())


@bp.get('/admin/tickets')
@admin_required
def tickets():
    q = request.args.get('q', '').strip()[:100]
    state = request.args.get('status', '')
    rows = get_db().execute("SELECT * FROM support_tickets WHERE (subject LIKE ? OR email LIKE ?) AND (?='' OR status=?) ORDER BY created_at DESC LIMIT 200", ('%' + q + '%',) * 2 + (state, state)).fetchall()
    return page('tickets.html', title='Suporte', rows=rows, q=q, state=state)


@bp.route('/admin/tickets/<identity>', methods=['GET', 'POST'])
@admin_required
def ticket_detail(identity):
    db = get_db()
    ticket = required_row('support_tickets', identity)
    if request.method == 'POST':
        validate_csrf()
        body, state = request.form.get('body', '').strip(), request.form.get('status')
        if state not in TICKETS or len(body) > 5000:
            abort(400)
        if body:
            db.execute('INSERT INTO ticket_messages VALUES (?, ?, ?, ?, ?)', (str(uuid.uuid4()), identity, g.user['id'], body, utc_now()))
        db.execute('UPDATE support_tickets SET status=? WHERE id=?', (state, identity))
        audit('Chamado atualizado', identity, state + (' · resposta enviada' if body else ''))
        db.commit()
        flash('Chamado atualizado. A resposta fica disponível na conta do cliente.', 'success')
        return redirect(url_for('management.ticket_detail', identity=identity))
    return page('ticket.html', title=ticket['subject'], ticket=ticket, messages=ticket_messages(identity))


def ticket_messages(identity):
    return get_db().execute('SELECT m.*, u.name, u.role FROM ticket_messages m JOIN users u ON u.id=m.author_id WHERE ticket_id=? ORDER BY m.created_at', (identity,)).fetchall()


@bp.route('/conta/suporte/<identity>', methods=['GET', 'POST'])
@login_required
def customer_ticket(identity):
    ticket = required_row('support_tickets', identity)
    if ticket['user_id'] != g.user['id']:
        abort(404)
    if request.method == 'POST':
        validate_csrf()
        body = request.form.get('body', '').strip()
        if not 1 <= len(body) <= 5000:
            abort(400)
        db = get_db()
        db.execute('INSERT INTO ticket_messages VALUES (?, ?, ?, ?, ?)', (str(uuid.uuid4()), identity, g.user['id'], body, utc_now()))
        db.execute("UPDATE support_tickets SET status='OPEN' WHERE id=?", (identity,))
        db.commit()
        return redirect(url_for('management.customer_ticket', identity=identity))
    return render_template('ticket_thread.html', title=ticket['subject'], ticket=ticket, messages=ticket_messages(identity), ticket_statuses=TICKETS)


def save_image(upload):
    if not upload or not upload.filename:
        return None
    content = upload.read(5 * 1024 * 1024 + 1)
    extension = Path(secure_filename(upload.filename)).suffix.lower()
    valid = (extension == '.png' and content.startswith(b'\x89PNG\r\n\x1a\n') or extension in ('.jpg', '.jpeg') and content.startswith(b'\xff\xd8\xff') or extension == '.webp' and content[:4] == b'RIFF' and content[8:12] == b'WEBP')
    if not valid or len(content) > 5 * 1024 * 1024:
        raise ValueError('Envie uma imagem PNG, JPG ou WebP de até 5 MB.')
    filename = 'uploads/' + uuid.uuid4().hex + extension
    path = Path(current_app.static_folder) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return filename


@bp.get('/admin/products')
@admin_required
def products():
    return page('products.html', title='Produtos', products=get_products(True))


@bp.route('/admin/products/new', defaults={'slug': None}, methods=['GET', 'POST'])
@bp.route('/admin/products/<slug>', methods=['GET', 'POST'])
@admin_required
def product_edit(slug):
    db = get_db()
    catalog = get_products(True)
    options = {
        'category': list(dict.fromkeys([v for v in CATEGORIES if v not in ('Todas', 'Ofertas')] + [p['category'] for p in catalog if p['category'] not in ('Todas', 'Ofertas')])),
        'rarity': list(dict.fromkeys([v for v in RARITIES if v != 'Todas'] + [p['rarity'] for p in catalog if p['rarity'] != 'Todas'])),
        'class_name': list(dict.fromkeys(CLASSES + [p['class_name'] for p in catalog])),
    }
    product = next((p for p in catalog if p['slug'] == slug), None)
    if slug and not product:
        abort(404)
    initial = product or dict(slug='', name='', price_cents=0, category='Armas', rarity='Comum', class_name='Todas', short_description='', description='', attributes=[], image_position='0% 0%', image='', sales_rank=0, created_rank=0, offer=False, active=True)
    values = dict(initial)
    if request.method == 'POST':
        validate_csrf()
        try:
            for key in ('name','category','rarity','class_name','short_description','description'):
                values[key] = request.form.get(key, '').strip()
            if any(values[key] not in choices for key, choices in options.items()):
                raise ValueError('Selecione uma categoria, raridade e classe disponíveis nas listas.')
            values['slug'] = slug or request.form.get('slug', '').strip()
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', values['slug']) or len(values['slug']) > 100:
                raise ValueError('Use um identificador com letras minúsculas, números e hífens.')
            if not slug and db.execute('SELECT 1 FROM catalog_products WHERE slug=?', (values['slug'],)).fetchone():
                raise ValueError('Este identificador já existe.')
            price = Decimal(request.form.get('price', '').replace(',', '.'))
            if not price.is_finite() or price <= 0 or price > 100000 or price != price.quantize(Decimal('.01')):
                raise ValueError('Informe um preço maior que zero, com até duas casas decimais.')
            values['price_cents'] = int(price * 100)
            if not all(1 <= len(values[k]) <= n for k, n in [('name',120),('category',60),('rarity',40),('class_name',60),('short_description',200),('description',5000)]):
                raise ValueError('Preencha os campos de texto respeitando os limites.')
            attributes = []
            for line in request.form.get('attributes', '').splitlines():
                if line.strip():
                    pair = line.split(':', 1)
                    if len(pair) != 2 or not all(v.strip() for v in pair):
                        raise ValueError('Atributos: use Nome: Valor, um por linha.')
                    attributes.append([v.strip()[:100] for v in pair])
            values.update(attributes=attributes, offer='offer' in request.form, active='active' in request.form)
            image = save_image(request.files.get('image'))
            if image:
                values['image'] = image
            db.execute('INSERT INTO catalog_products VALUES (?, ?, ?) ON CONFLICT(slug) DO UPDATE SET data=excluded.data, active=excluded.active', (values['slug'], json.dumps(values, ensure_ascii=False), int(values['active'])))
            audit('Produto salvo', values['slug'])
            db.commit()
            flash('Produto salvo e catálogo atualizado.', 'success')
            return redirect(url_for('management.products'))
        except (ValueError, InvalidOperation) as exc:
            flash(str(exc) if isinstance(exc, ValueError) else 'Preço inválido.', 'error')
    return page('product_edit.html', title='Editar produto' if slug else 'Novo produto', product=values, editing=bool(slug), options=options)


GAME_DEFAULTS = dict(GAME_INFO)


def release_path(filename):
    name = secure_filename(filename)
    if not name or name != filename:
        return Path(current_app.instance_path) / 'releases' / 'unavailable'
    private = Path(current_app.instance_path) / 'releases' / name
    return private if private.is_file() else Path(current_app.static_folder) / 'downloads' / name


def game_settings():
    row = get_db().execute("SELECT value FROM site_settings WHERE key='game'").fetchone()
    game = dict(GAME_DEFAULTS, **(json.loads(row['value']) if row else {}))
    path = release_path(game['filename'])
    game['available'] = path.is_file()
    game['size'] = f'{path.stat().st_size / 1024 / 1024:.1f} MB' if game['available'] else 'Indisponível'
    return game


@bp.route('/admin/game', methods=['GET', 'POST'])
@admin_required
def game_admin():
    game = game_settings()
    if request.method == 'POST':
        validate_csrf()
        try:
            for key, limit in [('name',120),('description',5000),('version',40),('platform',120),('requirements',5000),('news',10000)]:
                game[key] = request.form.get(key, '').strip()
                if not 1 <= len(game[key]) <= limit:
                    raise ValueError('Preencha os campos e respeite os limites de texto.')
            upload = request.files.get('release')
            if upload and upload.filename:
                filename = secure_filename(upload.filename)
                if Path(filename).suffix.lower() not in ('.zip','.exe','.msi','.apk','.dmg','.appimage'):
                    raise ValueError('Formato de download não permitido. Use ZIP, EXE, MSI, APK, DMG ou AppImage.')
                folder = Path(current_app.instance_path) / 'releases'
                folder.mkdir(parents=True, exist_ok=True)
                filename = uuid.uuid4().hex[:12] + '-' + filename
                target = folder / filename
                upload.save(target)
                if target.stat().st_size == 0:
                    raise ValueError('O arquivo está vazio.')
                game['filename'] = filename
            db = get_db()
            db.execute("INSERT INTO site_settings VALUES ('game', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps({k: game[k] for k in GAME_DEFAULTS}, ensure_ascii=False),))
            audit('Conteúdo do jogo salvo', game['version'])
            db.commit()
            flash('Informações do jogo publicadas.', 'success')
            return redirect(url_for('management.game_admin'))
        except ValueError as exc:
            flash(str(exc), 'error')
    return page('game_edit.html', title='Jogo e download', game=game)
