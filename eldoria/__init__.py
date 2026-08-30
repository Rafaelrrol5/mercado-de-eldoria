import os
from datetime import datetime
from pathlib import Path

from flask import Flask, g, render_template, session

from . import admin, auth, db, store
from .products import format_brl
from .security import csrf_token


def create_app(test_config=None):
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me-before-production"),
        DATABASE=os.environ.get("DATABASE_PATH", str(Path(app.instance_path) / "eldoria.sqlite3")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
        MAX_CONTENT_LENGTH=32 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(store.bp)
    app.register_blueprint(admin.bp)
    app.cli.add_command(admin.create_admin_command)

    app.jinja_env.globals.update(csrf_token=csrf_token)
    app.jinja_env.filters["brl"] = format_brl

    @app.context_processor
    def global_context():
        cart = session.get("cart", {})
        return {"cart_count": sum(value for value in cart.values() if isinstance(value, int)), "current_year": datetime.now().year}

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        return response

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html", title="Página não encontrada"), 404

    return app
