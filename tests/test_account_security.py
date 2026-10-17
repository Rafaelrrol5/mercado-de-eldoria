import re
import time
import unittest
from unittest.mock import patch

import test_management
from eldoria.account_security import GENERIC_RESET, totp
from eldoria.db import get_db


class AccountSecurityTest(unittest.TestCase):
    setUp=test_management.ManagementTest.setUp
    tearDown=test_management.ManagementTest.tearDown
    csrf=test_management.ManagementTest.csrf
    register=test_management.ManagementTest.register
    post=test_management.ManagementTest.post
    as_admin=test_management.ManagementTest.as_admin

    def message_path(self, purpose):
        message=self.app.extensions['mail_outbox'][-1]
        prefix='/redefinir-senha/' if purpose=='reset' else '/confirmar-email/'
        return re.search(re.escape(prefix)+r'[A-Za-z0-9_-]+',message.get_content()).group(0)

    def test_confirmation_single_use_and_resend(self):
        first=self.message_path('verify')
        self.assertEqual(self.client.get(first).status_code,200)
        with self.app.app_context():
            self.assertIsNone(get_db().execute('SELECT email_verified_at FROM user_security WHERE user_id=?',(self.customer_id,)).fetchone()[0])
        self.client.post('/conta/reenviar-confirmacao',data={'csrf_token':self.csrf('/conta')})
        self.assertEqual(self.client.get(first).status_code,400)
        second=self.message_path('verify')
        self.post(second,{})
        self.assertEqual(self.client.get(second).status_code,400)
        self.assertIn('E-mail confirmado',self.client.get('/conta').get_data(as_text=True))

    def test_reset_is_generic_single_use_and_invalidates_sessions(self):
        with self.client.session_transaction() as session:
            old_cookie=dict(session)
        result=self.post('/esqueci-senha',{'email':'aventureiro@example.com'})
        self.assertIn(GENERIC_RESET,result.get_data(as_text=True))
        path=self.message_path('reset')
        result=self.post('/esqueci-senha',{'email':'nobody@example.com'})
        self.assertIn(GENERIC_RESET,result.get_data(as_text=True))
        old=self.app.test_client()
        with old.session_transaction() as session:
            session.update(old_cookie)
        result=self.post(path,{'password':'NovaSenha123','confirmation':'NovaSenha123'})
        self.assertIn('Senha redefinida',result.get_data(as_text=True))
        self.assertEqual(self.client.get(path).status_code,400)
        self.assertEqual(old.get('/conta').status_code,302)
        self.post('/login',{'email':'aventureiro@example.com','password':'NovaSenha123'})
        self.assertEqual(self.client.get('/conta').status_code,200)

    def test_expired_tokens_csrf_and_password_validation(self):
        self.post('/esqueci-senha',{'email':'aventureiro@example.com'})
        path=self.message_path('reset')
        self.assertEqual(self.client.post(path,data={'password':'Invalid123'}).status_code,400)
        result=self.post(path,{'password':'short','confirmation':'short'})
        self.assertIn('8 a 128',result.get_data(as_text=True))
        with self.app.app_context():
            get_db().execute("UPDATE account_tokens SET expires_at=0")
            get_db().commit()
        self.assertEqual(self.client.get(path).status_code,400)

    def test_login_throttling_and_preserved_fields(self):
        for _ in range(5):
            self.post('/login',{'email':'aventureiro@example.com','password':'Errada123'})
        token=self.csrf('/login')
        response=self.client.post('/login',data={'csrf_token':token,'email':'aventureiro@example.com','password':'Errada123'})
        self.assertEqual(response.status_code,429)
        self.assertIn('aventureiro@example.com',response.get_data(as_text=True))
        self.assertNotIn('value="Errada123"',response.get_data(as_text=True))
        response=self.post('/cadastro',{'name':'Nome Preservado','email':'invalido','password':'Senha123'})
        self.assertIn('Nome Preservado',response.get_data(as_text=True))
        self.assertIn('Informe um email válido',response.get_data(as_text=True))

    def enable_two_factor(self):
        self.as_admin()
        self.post('/admin/seguranca',{'action':'prepare','password':'Admin123'})
        with self.app.app_context():
            secret=get_db().execute("SELECT totp_pending FROM user_security WHERE user_id='test-admin'").fetchone()[0]
        response=self.post('/admin/seguranca',{'action':'enable','password':'Admin123','code':totp(secret)})
        codes=re.findall(r'<code>([a-f0-9]{12})</code>',response.get_data(as_text=True))
        self.assertEqual(len(codes),8)
        return secret,codes

    def test_admin_two_factor_and_recovery_code_single_use(self):
        secret,codes=self.enable_two_factor()
        with self.client.session_transaction() as session:
            session.clear()
        self.post('/admin/login',{'email':'admin@example.com','password':'Admin123'})
        self.assertEqual(self.client.get('/admin/dashboard').status_code,302)
        self.assertEqual(self.client.get('/admin/segundo-fator').status_code,200)
        self.post('/admin/segundo-fator',{'code':codes[0]})
        self.assertEqual(self.client.get('/admin/dashboard').status_code,200)
        with self.client.session_transaction() as session:
            session.clear()
        self.post('/admin/login',{'email':'admin@example.com','password':'Admin123'})
        result=self.post('/admin/segundo-fator',{'code':codes[0]})
        self.assertIn('já utilizado',result.get_data(as_text=True))
        self.assertEqual(self.client.get('/admin/dashboard').status_code,302)
        self.post('/admin/segundo-fator',{'code':totp(secret,int(time.time())//30+1)})
        self.assertEqual(self.client.get('/admin/dashboard').status_code,200)

    def test_two_factor_disable_requires_password_and_code(self):
        secret,codes=self.enable_two_factor()
        self.post('/admin/seguranca',{'action':'disable','password':'wrong','code':codes[0]})
        with self.app.app_context():
            self.assertIsNotNone(get_db().execute("SELECT totp_secret FROM user_security WHERE user_id='test-admin'").fetchone()[0])
        self.post('/admin/seguranca',{'action':'disable','password':'Admin123','code':codes[0]})
        with self.app.app_context():
            self.assertIsNone(get_db().execute("SELECT totp_secret FROM user_security WHERE user_id='test-admin'").fetchone()[0])

    def test_trusted_origin_and_smtp_failure(self):
        self.app.config['APP_ORIGIN']='https://eldoria.example'
        self.post('/esqueci-senha',{'email':'aventureiro@example.com'})
        self.assertIn('https://eldoria.example/redefinir-senha/',self.app.extensions['mail_outbox'][-1].get_content())
        self.app.config.update(MAIL_BACKEND='smtp',SMTP_HOST='invalid.example')
        with patch('smtplib.SMTP',side_effect=OSError('smtp unavailable')):
            result=self.post('/esqueci-senha',{'email':'aventureiro@example.com'})
        self.assertIn(GENERIC_RESET,result.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM account_tokens WHERE purpose='reset' AND used_at IS NULL").fetchone()[0],0)
