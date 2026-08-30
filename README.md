# Mercado de Eldoria — Flask

Versão em Flask/Python da loja de itens digitais de Eldoria.

## Executar localmente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app run.py run
```

Abra `http://localhost:5000`.

Em produção, defina `SECRET_KEY`, `DATABASE_PATH` e `APP_ORIGIN`. Use Waitress no Windows:

```powershell
waitress-serve --call eldoria:create_app
```

Crie administradores exclusivamente pelo terminal:

```powershell
flask --app run.py create-admin
```

O checkout registra o pedido no banco, mas não cobra dinheiro. Para aceitar pagamentos reais, conecte um provedor certificado no backend e valide webhooks antes de marcar pedidos como pagos.

