"""Financial projections over the same database used by checkout and support."""
import csv
import io
from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, Response, abort, render_template, request

from .auth import admin_required
from .db import get_db, utc_now

bp = Blueprint('finance', __name__)
BRASILIA = timezone(timedelta(hours=-3))


def record_payment(order, payment):
    """Called inside the order update transaction; one receipt/refund per order."""
    db = get_db()
    paid = db.execute("SELECT 1 FROM financial_events WHERE order_id=? AND kind='PAYMENT'", (order['id'],)).fetchone()
    refunded = db.execute("SELECT 1 FROM financial_events WHERE order_id=? AND kind='REFUND'", (order['id'],)).fetchone()
    if refunded and payment != 'REFUNDED':
        raise ValueError('Este pedido foi reembolsado. Crie um novo pedido para uma nova compra.')
    if payment in ('PENDING','CANCELLED') and paid:
        raise ValueError('Um pagamento confirmado só pode ser estornado pelo status Reembolsado.')
    if payment == 'REFUNDED' and not paid:
        raise ValueError('Não é possível reembolsar um pedido sem pagamento confirmado.')
    kind = 'PAYMENT' if payment == 'PAID' else 'REFUND' if payment == 'REFUNDED' else None
    if kind:
        db.execute('INSERT OR IGNORE INTO financial_events (order_id,kind,amount_cents,occurred_at) VALUES (?,?,?,?)',
                   (order['id'], kind, order['total_cents'], utc_now()))


def report_period():
    today = datetime.now(BRASILIA).date()
    try:
        start = date.fromisoformat(request.args.get('start') or str(today - timedelta(days=29)))
        end = date.fromisoformat(request.args.get('end') or str(today))
    except ValueError:
        abort(400, description='Período inválido. Use datas válidas.')
    if start > end or end == date.max or (end-start).days > 365:
        abort(400, description='Selecione um período de até 366 dias, com início anterior ao fim.')
    return start, end


def bounds(start, end):
    return (datetime.combine(start,time.min,BRASILIA).astimezone(timezone.utc).isoformat(),
            datetime.combine(end+timedelta(days=1),time.min,BRASILIA).astimezone(timezone.utc).isoformat())


def financial_report(start, end):
    db = get_db()
    low, high = bounds(start,end)
    period = 'julianday(occurred_at)>=julianday(?) AND julianday(occurred_at)<julianday(?)'
    totals = db.execute("SELECT kind, COALESCE(SUM(amount_cents),0) amount, COUNT(*) count FROM financial_events WHERE " + period + ' GROUP BY kind', (low, high)).fetchall()
    grouped = {row['kind']: dict(row) for row in totals}
    gross, refund = grouped.get('PAYMENT',{}).get('amount',0), grouped.get('REFUND',{}).get('amount',0)
    sales = grouped.get('PAYMENT',{}).get('count',0)
    lifetime = db.execute("SELECT COALESCE(SUM(CASE kind WHEN 'PAYMENT' THEN amount_cents ELSE -amount_cents END),0) FROM financial_events").fetchone()[0]
    days = {str(start+timedelta(days=i)): dict(date=str(start+timedelta(days=i)),gross=0,refund=0,net=0) for i in range((end-start).days+1)}
    rows = db.execute("SELECT date(occurred_at,'-3 hours') day, kind, SUM(amount_cents) amount FROM financial_events WHERE " + period + ' GROUP BY day,kind', (low,high)).fetchall()
    for row in rows:
        if row['day'] in days:
            days[row['day']]['gross' if row['kind']=='PAYMENT' else 'refund'] = row['amount']
    daily = list(days.values())
    for day in daily:
        day['net'] = day['gross']-day['refund']
    return dict(start=str(start),end=str(end),gross_cents=gross,refund_cents=refund,net_cents=gross-refund,
                lifetime_cents=lifetime,sales=sales,refunds=grouped.get('REFUND',{}).get('count',0),
                average_cents=(gross+sales//2)//sales if sales else 0,
                orders=db.execute('SELECT COUNT(*) FROM orders WHERE julianday(created_at)>=julianday(?) AND julianday(created_at)<julianday(?)',(low,high)).fetchone()[0],
                pending_cents=db.execute("SELECT COALESCE(SUM(total_cents),0) FROM orders WHERE status='AWAITING_PAYMENT'").fetchone()[0],
                daily=daily,chart_max=max([1]+[max(day['gross'],day['refund']) for day in daily]),
                inferred=db.execute('SELECT COUNT(*) FROM financial_events WHERE inferred=1 AND ' + period,(low,high)).fetchone()[0],
                statuses=[dict(row) for row in db.execute('SELECT status,COUNT(*) count FROM orders GROUP BY status')],
                generated_at=utc_now())


@bp.get('/admin/finance')
@admin_required
def reports():
    from .management import summary
    return render_template('admin/finance.html',title='Financeiro',finance=financial_report(*report_period()),counts=summary())


@bp.get('/admin/api/dashboard')
@admin_required
def dashboard_api():
    from .management import summary
    return dict(counts=summary(), finance=financial_report(*report_period()))


@bp.get('/admin/finance/export.csv')
@admin_required
def export():
    start,end=report_period()
    low,high=bounds(start,end)
    rows=get_db().execute("SELECT e.*, o.number FROM financial_events e JOIN orders o ON o.id=e.order_id WHERE julianday(e.occurred_at)>=julianday(?) AND julianday(e.occurred_at)<julianday(?) ORDER BY e.occurred_at",(low,high)).fetchall()
    output=io.StringIO(newline='')
    writer=csv.writer(output,delimiter=';')
    writer.writerow(['Pedido','Movimento','Data (Brasília)','Valor (R$)','Data histórica estimada'])
    for row in rows:
        # A leading apostrophe prevents spreadsheet formula execution by untrusted order labels.
        number=row['number']
        if number.lstrip().startswith(('=','+','-','@')):
            number="'"+number
        cents=row['amount_cents'] * (1 if row['kind']=='PAYMENT' else -1)
        value=('-' if cents<0 else '')+f'{abs(cents)//100},{abs(cents)%100:02d}'
        writer.writerow([number,'Pagamento' if row['kind']=='PAYMENT' else 'Reembolso',datetime.fromisoformat(row['occurred_at']).astimezone(BRASILIA).strftime('%d/%m/%Y %H:%M'),value,'Sim' if row['inferred'] else 'Não'])
    return Response('\ufeff'+output.getvalue(),content_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename=financeiro-{start}-{end}.csv'})
