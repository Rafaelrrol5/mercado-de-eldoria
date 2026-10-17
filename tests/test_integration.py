import re
import unittest
from datetime import datetime, timedelta

import test_management
from eldoria.db import get_db, init_db
from eldoria.finance import BRASILIA


class StoreIntegrationTest(unittest.TestCase):
    setUp = test_management.ManagementTest.setUp
    tearDown = test_management.ManagementTest.tearDown
    csrf = test_management.ManagementTest.csrf
    register = test_management.ManagementTest.register
    post = test_management.ManagementTest.post
    as_admin = test_management.ManagementTest.as_admin

    def test_financial_api_is_private_and_uncached(self):
        for path in ['/admin/finance','/admin/api/dashboard','/admin/finance/export.csv']:
            self.assertEqual(self.client.get(path).status_code,404)
        self.as_admin()
        response=self.client.get('/admin/api/dashboard')
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertNotIn('password',response.get_data(as_text=True))
        self.assertEqual(response.json['finance']['gross_cents'],0)
        self.assertEqual(response.json['counts']['customers'],1)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/admin/api/dashboard').status_code,302)

    def test_receipt_and_refund_are_idempotent_and_audited(self):
        self.as_admin()
        for _ in range(2):
            self.post('/admin/orders/order1', {'payment':'PAID','delivery':'PENDING','note':'Pagamento conferido'})
        finance=self.client.get('/admin/api/dashboard').json['finance']
        self.assertEqual((finance['gross_cents'],finance['sales'],finance['net_cents']),(2990,1,2990))
        self.assertEqual(finance['pending_cents'],0)
        for _ in range(2):
            self.post('/admin/orders/order1', {'payment':'REFUNDED','delivery':'PENDING','note':'Reembolso realizado'})
        finance=self.client.get('/admin/api/dashboard').json['finance']
        self.assertEqual((finance['gross_cents'],finance['refund_cents'],finance['net_cents']),(2990,2990,0))
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM financial_events').fetchone()[0],2)
            self.assertGreater(get_db().execute('SELECT COUNT(*) FROM admin_events').fetchone()[0],0)
        self.post('/admin/orders/order1', {'payment':'PAID','delivery':'PENDING','note':''})
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT status FROM orders WHERE id='order1'").fetchone()[0],'REFUNDED')

    def test_unpaid_order_cannot_be_refunded(self):
        self.as_admin()
        self.post('/admin/orders/order1', {'payment':'REFUNDED','delivery':'PENDING','note':''})
        self.assertEqual(self.client.get('/admin/api/dashboard').json['finance']['refund_cents'],0)

    def test_site_checkout_is_visible_immediately_in_admin_database(self):
        with self.client.session_transaction() as session:
            session['cart']={'amuleto-da-lua':2}
        self.post('/checkout', {'game_identifier':'Player#123'})
        self.as_admin()
        data=self.client.get('/admin/api/dashboard').json
        self.assertEqual(data['counts']['orders'],2)
        self.assertEqual(data['finance']['pending_cents'],4970)
        self.assertEqual(data['finance']['gross_cents'],0)
        self.assertIn('R$ 19,80',self.client.get('/admin/orders').get_data(as_text=True))

    def test_email_duplicates_and_site_support_replies_share_data(self):
        self.post('/cadastro',dict(name='Duplicado',email=' AVentureiro@EXAMPLE.com ',password='Teste1234'))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM users WHERE role='CUSTOMER'").fetchone()[0],1)
        self.post('/suporte',dict(name='Cliente',email='aventureiro@example.com',category='Pedido',order_number='ELD-TEST',subject='Chamado criado no site',description='Descrição de teste enviada através do site.'))
        self.as_admin()
        self.assertIn('Chamado criado no site', self.client.get('/admin/tickets').get_data(as_text=True))
        self.assertEqual(self.client.get('/admin/api/dashboard').json['counts']['tickets'],2)
        self.post('/admin/tickets/ticket1', {'body':'Resposta integrada','status':'CLOSED'})
        with self.client.session_transaction() as session:
            session['user_id']=self.customer_id
        self.assertIn('Resposta integrada',self.client.get('/conta/suporte/ticket1').get_data(as_text=True))
        self.post('/conta/suporte/ticket1', {'body':'Nova mensagem do cliente'})
        self.as_admin()
        self.assertIn('Nova mensagem do cliente',self.client.get('/admin/tickets/ticket1').get_data(as_text=True))
        self.assertEqual(self.client.get('/admin/api/dashboard').json['counts']['tickets'],2)

    def test_financial_dates_export_and_legacy_migration(self):
        self.as_admin()
        with self.app.app_context():
            db=get_db()
            db.execute("UPDATE orders SET status='DELIVERED', created_at='2026-01-02T01:00:00+00:00' WHERE id='order1'")
            db.commit()
            init_db()
            init_db()
            self.assertEqual(db.execute('SELECT COUNT(*) FROM financial_events').fetchone()[0],1)
        data=self.client.get('/admin/api/dashboard?start=2026-01-01&end=2026-01-01').json['finance']
        self.assertEqual(data['gross_cents'],2990)
        self.assertEqual(data['inferred'],1)
        self.assertEqual(data['daily'][0]['gross'],2990)
        self.assertEqual(self.client.get('/admin/api/dashboard?start=2026-01-02&end=2026-01-02').json['finance']['gross_cents'],0)
        response=self.client.get('/admin/finance/export.csv?start=2026-01-01&end=2026-01-01')
        self.assertIn('29,90',response.get_data(as_text=True))
        self.assertIn('01/01/2026 22:00',response.get_data(as_text=True))
        self.assertIn('attachment',response.headers['Content-Disposition'])
        for query in ['start=wrong','start=2026-10-16&end=2026-10-01','start=2020-01-01&end=2026-10-16']:
            self.assertEqual(self.client.get('/admin/api/dashboard?'+query).status_code,400)

    def test_live_regions_and_finance_render_without_javascript(self):
        self.as_admin()
        for path in ['/admin/dashboard','/admin/finance','/admin/orders','/admin/tickets','/admin/customers','/admin/tickets/ticket1']:
            response=self.client.get(path,headers={'X-Live-Refresh':'1'})
            self.assertEqual(response.status_code,200,path)
            self.assertIn('data-live-region',response.get_data(as_text=True))
        self.assertIn('Receita total acumulada',self.client.get('/admin/dashboard').get_data(as_text=True))
        self.assertIn('Ver dados do gráfico',self.client.get('/admin/finance').get_data(as_text=True))
