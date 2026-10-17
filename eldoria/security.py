import hmac
import secrets
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import abort, request, session
from werkzeug.exceptions import BadRequest


class CSRFError(BadRequest):
    description = 'Este formulário ficou desatualizado. Confira os dados e envie novamente.'


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf():
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    expected = session.get('csrf_token', '')
    if not supplied or len(supplied) > 200 or not hmac.compare_digest(supplied.encode('utf-8'), expected.encode('utf-8')):
        raise CSRFError()


def csrf_protected(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        validate_csrf()
        return view(*args, **kwargs)
    return wrapped


def safe_redirect_target(target, fallback="/"):
    if not target:
        return fallback
    host_url = request.host_url
    candidate = urlparse(urljoin(host_url, target))
    host = urlparse(host_url)
    if candidate.scheme in {"http", "https"} and candidate.netloc == host.netloc:
        return candidate.path + (("?" + candidate.query) if candidate.query else "")
    return fallback

