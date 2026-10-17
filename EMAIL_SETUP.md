# E-mails e segurança de conta

O site oferece confirmação de e-mail (24 horas), recuperação de senha (1 hora), limites de tentativas e autenticação TOTP opcional para administradores. A verificação de e-mail não bloqueia os fluxos de compra existentes; a situação aparece na conta do cliente.

## Desenvolvimento local

O padrão `MAIL_BACKEND=local` salva mensagens `.eml` em `instance/outbox/`, sem enviar para a internet. Abra a mensagem localmente para usar o link de teste. Essa pasta fica fora de `static` e não é publicada pelo site. Os arquivos contêm links privados: não compartilhe e não mantenha mensagens expiradas desnecessariamente.

## Envio real por SMTP

Antes de iniciar o servidor, defina estas variáveis no ambiente (não salve senhas no código):

```powershell
$env:MAIL_BACKEND = 'smtp'
$env:APP_ORIGIN = 'https://seu-dominio.com'
$env:MAIL_FROM = 'Eldoria <contato@seu-dominio.com>'
$env:SMTP_HOST = 'smtp.seu-provedor.com'
$env:SMTP_PORT = '587'
$env:SMTP_USER = 'seu-usuario'
$env:SMTP_PASSWORD = 'sua-credencial-smtp'
$env:SMTP_SSL = '0'
```

Use `SMTP_SSL=1` e a porta 465 se o provedor exigir TLS implícito. Na porta 587, o aplicativo exige STARTTLS com validação de certificado. O remetente deve estar autorizado pelo provedor. Configure SPF/DKIM conforme as instruções dele. Reinicie o servidor depois de alterar o ambiente. A origem dos links vem de `APP_ORIGIN`, não do cabeçalho Host recebido.

## Administração

Entre em **Segurança**, informe a senha atual e clique em configurar. Cadastre a chave manual no autenticador (TOTP, 6 dígitos, 30 segundos), informe a senha e o código para ativar. Guarde os oito códigos de recuperação exibidos uma única vez. O próximo login exigirá senha e código. Para desativar, são exigidos senha e um código válido ou de recuperação. Contas administrativas não usam a recuperação de senha pública destinada aos clientes.

As chaves TOTP precisam ser recuperáveis para validar códigos e ficam no banco privado; códigos de recuperação e links ficam somente como hashes. Proteja o arquivo SQLite e seus backups com as permissões e criptografia de disco do servidor. Nunca publique `instance/`.

Os limites persistem no SQLite e usam conta e endereço IP. Cabeçalhos de proxy enviados pelo cliente não são considerados. Ao publicar atrás de proxy, configure a origem de IP confiável no servidor. Todos os formulários mantêm CSRF; não há CAPTCHA obrigatório nem bloqueio permanente.
