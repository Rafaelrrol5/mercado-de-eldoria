import io
import unittest
from werkzeug.security import generate_password_hash
import test_app
from eldoria.db import get_db, utc_now


class ManagementTest(unittest.TestCase):
    csrf = test_app.EldoriaAppTest.csrf
    register = test_app.EldoriaAppTest.register
    tearDown = test_app.EldoriaAppTest.tearDown

    def setUp(self):
        test_app.EldoriaAppTest.setUp(self)
        self.app.instance_path = self.tempdir.name
        self.register()
        with self.app.app_context():
            db = get_db()
            self.customer_id = db.execute("SELECT id FROM users WHERE role='CUSTOMER'").fetchone()[0]
            db.execute("INSERT INTO users (id,name,email,password_hash,role,status,created_at) VALUES ('test-admin','Admin','admin@example.com',?,'ADMIN','ACTIVE',?)", (generate_password_hash('Admin123'), utc_now()))
            db.execute("INSERT INTO orders VALUES ('order1','ELD-TEST',?,'Player#1',2990,2990,'AWAITING_PAYMENT',?)", (self.customer_id, utc_now()))
            db.execute("INSERT INTO order_items VALUES ('item1','order1','pacote-inicial-do-aventureiro','Pacote',2990,1)")
            db.execute("INSERT INTO support_tickets VALUES ('ticket1',?,'ELD-TEST','Cliente','aventureiro@example.com','Pedido','Ajuda com pedido','Preciso de ajuda com meu pedido.','OPEN',?)", (self.customer_id, utc_now()))
            db.commit()

    def as_admin(self):
        with self.client.session_transaction() as session:
            session['user_id'] = 'test-admin'

    def post(self, path, data):
        data['csrf_token'] = self.csrf(path)
        return self.client.post(path, data=data, follow_redirects=True)

    def test_permissions_and_csrf(self):
        for path in ['/admin/orders','/admin/customers','/admin/tickets','/admin/products','/admin/game','/admin/orders/order1']:
            self.assertEqual(self.client.get(path).status_code, 404)
        self.as_admin()
        self.assertEqual(self.client.post('/admin/orders/order1', data={'payment':'PAID','delivery':'DELIVERED'}).status_code, 400)

    def test_admin_pages_and_order_flow(self):
        self.as_admin()
        for path in ['/admin/dashboard','/admin/orders','/admin/orders/order1','/admin/customers','/admin/customers/'+self.customer_id,'/admin/tickets','/admin/tickets/ticket1','/admin/products','/admin/products/new','/admin/products/amuleto-da-lua','/admin/game']:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.post('/admin/orders/order1', {'payment':'PENDING','delivery':'DELIVERED','note':''})
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT status FROM orders WHERE id='order1'").fetchone()[0], 'AWAITING_PAYMENT')
        self.post('/admin/orders/order1', {'payment':'PAID','delivery':'DELIVERED','note':'Conferido manualmente'})
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT status FROM orders WHERE id='order1'").fetchone()[0], 'DELIVERED')
            self.assertGreater(get_db().execute('SELECT COUNT(*) FROM admin_events').fetchone()[0], 0)

    def test_support_reply_ownership_and_suspension(self):
        self.as_admin()
        self.post('/admin/tickets/ticket1', {'body':'Entrega confirmada pela equipe','status':'CLOSED'})
        with self.client.session_transaction() as session:
            session['user_id'] = self.customer_id
        response = self.client.get('/conta/suporte/ticket1')
        self.assertIn('Entrega confirmada', response.get_data(as_text=True))
        self.post('/conta/suporte/ticket1', {'body':'Obrigada pela resposta'})
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT status FROM support_tickets WHERE id='ticket1'").fetchone()[0], 'OPEN')
            db = get_db()
            db.execute("INSERT INTO users (id,name,email,password_hash,role,status,created_at) VALUES ('other','Outro','other@example.com','x','CUSTOMER','ACTIVE',?)", (utc_now(),))
            db.commit()
        with self.client.session_transaction() as session:
            session['user_id'] = 'other'
        self.assertEqual(self.client.get('/conta/suporte/ticket1').status_code, 404)
        self.as_admin()
        self.post('/admin/customers/'+self.customer_id, {'status':'SUSPENDED'})
        with self.client.session_transaction() as session:
            session['user_id'] = self.customer_id
        self.assertEqual(self.client.get('/conta').status_code, 302)

    def test_products_persist_and_checkout_uses_new_price(self):
        self.as_admin()
        data = dict(name='Amuleto atualizado', price='42.50', category='Acessórios', rarity='Raro', class_name='Todas', short_description='Mana extra', description='Descrição atualizada', attributes='Mana: +50', active='on', offer='on')
        self.assertEqual(self.post('/admin/products/amuleto-da-lua', data).status_code, 200)
        self.assertIn('R$ 42,50', self.client.get('/produto/amuleto-da-lua').get_data(as_text=True))
        self.assertIn('4250', self.client.get('/loja').get_data(as_text=True))
        from eldoria.db import init_db
        with self.app.app_context():
            init_db()
        self.assertIn('R$ 42,50', self.client.get('/produto/amuleto-da-lua').get_data(as_text=True))
        with self.client.session_transaction() as session:
            session['user_id'] = self.customer_id
            session['cart'] = {'amuleto-da-lua': 2}
        self.post('/checkout', {'game_identifier':'Player#123'})
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT unit_price_cents FROM order_items WHERE product_slug='amuleto-da-lua'").fetchone()[0],4250)
        self.as_admin()
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT unit_price_cents FROM order_items WHERE id='item1'").fetchone()[0], 2990)
        data.pop('active')
        self.post('/admin/products/amuleto-da-lua', data)
        self.assertEqual(self.client.get('/produto/amuleto-da-lua').status_code, 404)
        data.update(slug='novo-item', active='on', price='19.90')
        self.post('/admin/products/new', data)
        self.assertEqual(self.client.get('/produto/novo-item').status_code, 200)

    def test_game_edit_and_image_validation(self):
        self.as_admin()
        response = self.post('/admin/game', dict(name='Eldoria Teste', description='Apresentação editada', version='2.0', platform='Windows', requirements='8 GB de RAM', news='Nova região disponível'))
        self.assertEqual(response.status_code, 200)
        html = self.client.get('/jogo').get_data(as_text=True)
        for value in ['Eldoria Teste','2.0','8 GB de RAM','Nova região disponível']:
            self.assertIn(value, html)
        response = self.post('/admin/products/new', dict(slug='invalid-image',name='Item teste',price='10',category='Armas',rarity='Raro',class_name='Todas',short_description='Teste',description='Teste',active='on',image=(io.BytesIO(b'<script>bad</script>'),'bad.png')))
        self.assertIn('Envie uma imagem', response.get_data(as_text=True))
        self.assertEqual(self.client.get('/produto/invalid-image').status_code,404)

    def test_release_upload_and_download(self):
        self.as_admin()
        import zipfile
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as archive:
            archive.writestr('leia-me.txt', 'Pacote de teste')
        payload = content.getvalue()
        self.post('/admin/game', dict(name='Eldoria',description='Jogo',version='3.0',platform='Windows',requirements='8 GB RAM',news='Nova versão',release=(io.BytesIO(payload),'Eldoria.zip')))
        response = self.client.get('/jogo/download')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data,payload)
        self.assertIn('attachment', response.headers['Content-Disposition'])
        response.close()


if __name__ == '__main__':
    unittest.main()
