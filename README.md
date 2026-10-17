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

## Funcionalidades

- Catálogo com filtros, carrinho com cálculo automático e registro de pedidos.
- Cadastro, login, confirmação de e-mail e recuperação de senha.
- Atendimento com histórico de mensagens entre cliente e administrador.
- Painel de pedidos, clientes, produtos e relatórios financeiros com exportação CSV.
- Autenticação de dois fatores opcional para administradores.
- Apresentação do jogo e configuração do download pelo painel.

Os dados do site e da administração usam o mesmo banco SQLite. Algumas telas consultam atualizações a cada cinco segundos.

## E-mail

O modo padrão grava mensagens em `instance/outbox/` para testes e não envia e-mails reais. Configure SMTP conforme [EMAIL_SETUP.md](EMAIL_SETUP.md) antes de disponibilizar os fluxos de confirmação e recuperação ao público.

## Jogo e arquivos privados

O instalador não faz parte do repositório. Envie-o separadamente pelo painel administrativo, em **Jogo e download**. O arquivo de metadados informa a versão 1.8.1, mas o botão de download só fica disponível quando o instalador existe no servidor.

Não publique `instance/`, backups, mensagens locais, chaves ou credenciais. O banco e a chave de sessão são criados localmente na primeira execução. Não há conta administrativa nem senha padrão no repositório.

## Testes

```powershell
python -m unittest discover -s tests -v
```

## Limitações atuais

O pagamento exige confirmação administrativa. A entrega de e-mail depende de SMTP configurado. A validação direta em diferentes navegadores e os testes de usabilidade com usuários permanecem como próximos passos.
