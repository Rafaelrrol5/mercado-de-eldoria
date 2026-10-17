import unittest
import test_management
from eldoria.db import get_db


class CSRFRegressionTest(unittest.TestCase):
    setUp=test_management.ManagementTest.setUp
    tearDown=test_management.ManagementTest.tearDown
    csrf=test_management.ManagementTest.csrf
    register=test_management.ManagementTest.register

    def test_admin_login_preserves_other_tab_registration_token(self):
        token=self.csrf('/cadastro')
        response=self.client.post('/admin/login',data={'csrf_token':token,'email':'admin@example.com','password':'Admin123'})
        self.assertEqual(response.status_code,302)
        response=self.client.post('/cadastro',data={'csrf_token':token,'name':'Nova Conta','email':'nova@example.com','password':'Conta1234'})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            self.assertIsNotNone(get_db().execute("SELECT id FROM users WHERE email='nova@example.com'").fetchone())

    def test_expired_registration_preserves_fields_but_does_not_create_account(self):
        token=self.csrf('/cadastro')
        with self.client.session_transaction() as session:
            session.clear()
        data={'csrf_token':token,'name':'Nome Preservado','email':'preservado@example.com','password':'Segredo123'}
        response=self.client.post('/cadastro',data=data)
        self.assertEqual(response.status_code,400)
        html=response.get_data(as_text=True)
        self.assertIn('Nome Preservado',html)
        self.assertIn('preservado@example.com',html)
        self.assertIn('formulário ficou desatualizado',html)
        self.assertNotIn('value="Segredo123"',html)
        with self.app.app_context():
            self.assertIsNone(get_db().execute("SELECT id FROM users WHERE email='preservado@example.com'").fetchone())
        import re
        data['csrf_token']=re.search(r'name="csrf_token" value="([^"]+)"',html).group(1)
        self.assertEqual(self.client.post('/cadastro',data=data).status_code,302)

    def test_forged_and_unicode_tokens_remain_rejected(self):
        self.csrf('/cadastro')
        for token in ['','forged','é'*20]:
            response=self.client.post('/cadastro',data={'csrf_token':token,'name':'Teste','email':'forged@example.com','password':'Teste1234'})
            self.assertEqual(response.status_code,400)
