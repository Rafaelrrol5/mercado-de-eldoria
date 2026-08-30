import re
import tempfile
import unittest
from pathlib import Path

from eldoria import create_app


class EldoriaAppTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(Path(self.tempdir.name) / "test.sqlite3"),
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def csrf(self, path):
        response = self.client.get(path)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def register(self):
        token = self.csrf("/cadastro")
        return self.client.post("/cadastro", data={
            "csrf_token": token,
            "name": "Aventureiro Teste",
            "email": "aventureiro@example.com",
            "password": "Segura123",
            "game_identifier": "Aventureiro#1042",
        }, follow_redirects=True)

    def test_public_pages_and_no_admin_link(self):
        for path in ("/", "/loja", "/produto/espada-das-chamas-antigas", "/bolsa", "/como-funciona", "/suporte", "/termos", "/privacidade"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        public_html = self.client.get("/").get_data(as_text=True).lower()
        self.assertNotIn('href="/admin', public_html)
        self.assertNotIn("painel administrativo", public_html)

    def test_cart_is_persistent_in_session(self):
        token = self.csrf("/loja")
        response = self.client.post("/bolsa/adicionar", data={
            "csrf_token": token, "slug": "espada-das-chamas-antigas", "quantity": "2",
        }, follow_redirects=True)
        self.assertIn("Espada das Chamas Antigas", response.get_data(as_text=True))
        self.assertIn("R$ 29,80", self.client.get("/bolsa").get_data(as_text=True))

    def test_registration_support_and_checkout(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Minha conta", response.get_data(as_text=True))

        token = self.csrf("/loja")
        self.client.post("/bolsa/adicionar", data={"csrf_token": token, "slug": "amuleto-da-lua"})
        token = self.csrf("/checkout")
        checkout = self.client.post("/checkout", data={"csrf_token": token, "game_identifier": "Aventureiro#1042"})
        self.assertEqual(checkout.status_code, 200)
        self.assertIn("Pedido registrado", checkout.get_data(as_text=True))

        token = self.csrf("/suporte")
        support = self.client.post("/suporte", data={
            "csrf_token": token, "name": "Aventureiro Teste", "email": "aventureiro@example.com",
            "category": "Pedido", "order_number": "ELD-TESTE", "subject": "Dúvida sobre o pedido",
            "description": "Preciso de ajuda para acompanhar o pedido criado no teste.",
        })
        self.assertEqual(support.status_code, 200)
        self.assertIn("Solicitação enviada", support.get_data(as_text=True))

    def test_customer_cannot_access_admin(self):
        self.register()
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 404)
        self.assertEqual(self.client.get("/admin/api/summary").status_code, 404)

    def test_admin_requires_separate_login(self):
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

    def test_csrf_is_required(self):
        response = self.client.post("/bolsa/adicionar", data={"slug": "amuleto-da-lua"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

