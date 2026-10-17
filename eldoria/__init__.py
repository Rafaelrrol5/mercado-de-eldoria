import os
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, g, render_template, request, session

from . import admin, auth, db, store, management, finance, account_security
from .products import format_brl
from .security import csrf_token, CSRFError


def persistent_secret(instance_path):
    configured = os.environ.get('SECRET_KEY')
    if configured and configured != 'dev-only-change-me-before-production':
        return configured
    path = Path(instance_path)
    path.mkdir(parents=True, exist_ok=True)
    key_file = path / '.secret_key'
    try:
        descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return key_file.read_text(encoding='ascii').strip()
    with os.fdopen(descriptor, 'w', encoding='ascii') as stream:
        key = secrets.token_hex(32)
        stream.write(key)
    return key


def create_app(test_config=None):
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.config.from_mapping(
        SECRET_KEY=(test_config or {}).get('SECRET_KEY') or persistent_secret(app.instance_path),
        DATABASE=os.environ.get("DATABASE_PATH", str(Path(app.instance_path) / "eldoria.sqlite3")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
        MAX_CONTENT_LENGTH=32 * 1024,
        APP_ORIGIN=os.environ.get('APP_ORIGIN','http://localhost:5000'),
        MAIL_BACKEND=os.environ.get('MAIL_BACKEND','local'),
        MAIL_FROM=os.environ.get('MAIL_FROM','Eldoria <no-reply@eldoria.local>'),
        SMTP_HOST=os.environ.get('SMTP_HOST',''),
        SMTP_PORT=int(os.environ.get('SMTP_PORT','587')),
        SMTP_USER=os.environ.get('SMTP_USER',''),
        SMTP_PASSWORD=os.environ.get('SMTP_PASSWORD',''),
        SMTP_SSL=os.environ.get('SMTP_SSL','0')=='1',
    )
    if test_config:
        app.config.update(test_config)
    if app.testing and not (test_config or {}).get('MAIL_BACKEND'):
        app.config['MAIL_BACKEND']='memory'
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(store.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(management.bp)
    app.register_blueprint(finance.bp)
    app.register_blueprint(account_security.bp)
    app.cli.add_command(admin.create_admin_command)

    app.jinja_env.globals.update(csrf_token=csrf_token)
    app.jinja_env.filters["brl"] = format_brl

    @app.context_processor
    def global_context():
        cart = session.get("cart", {})
        return {"cart_count": sum(value for value in cart.values() if isinstance(value, int)), "current_year": datetime.now().year}

    @app.after_request
    def security_headers(response):
        if request.path.startswith(('/admin','/conta','/login','/cadastro','/esqueci-senha','/redefinir-senha','/confirmar-email')):
            response.headers['Cache-Control'] = 'no-store, private'
            response.headers['Referrer-Policy']='no-referrer'
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        return response

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html", title="Página não encontrada"), 404

    @app.errorhandler(CSRFError)
    def stale_form(error):
        message='O formulário ficou desatualizado ou sua sessão expirou. Seus dados foram preservados; digite a senha novamente e envie.'
        if request.endpoint == 'auth.register':
            return render_template('auth/register.html',title='Criar conta',errors={'form':message}),400
        if request.endpoint == 'auth.login':
            return render_template('auth/login.html',title='Entrar',error=message),400
        if request.endpoint == 'admin.login':
            return render_template('admin/login.html',title='Acesso administrativo',error=message),400
        return render_template('form_expired.html',title='Formulário desatualizado'),400

    return app
