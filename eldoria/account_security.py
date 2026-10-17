import base64
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import ssl
import struct
import time
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote, urlsplit

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import admin_required, login_required
from .db import get_db, utc_now
from .security import validate_csrf

bp = Blueprint('account_security', __name__)
GENERIC_RESET = 'Se houver uma conta de cliente ativa com esse e-mail, você receberá as instruções de recuperação.'
DUMMY_PASSWORD_HASH = generate_password_hash('unavailable-account-' + secrets.token_hex(24))


def password_matches(user, password):
    # Perform the expensive hash check even when no account matches.
    if len(password)>128:
        return False
    valid=check_password_hash(user['password_hash'] if user else DUMMY_PASSWORD_HASH,password)
    return bool(user and valid and user['status']=='ACTIVE')


def password_error(value):
    if not 8 <= len(value) <= 128 or not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        return 'Use de 8 a 128 caracteres, incluindo letras e números.'
    return None


def ensure_security(user_id):
    get_db().execute('INSERT OR IGNORE INTO user_security (user_id) VALUES (?)', (user_id,))


def consume_limit(scope, identity='', limit=5, seconds=900):
    """Bounded account and IP counters. Ignore forwarded headers unless a trusted proxy is configured."""
    db, now = get_db(), int(time.time())
    buckets = []
    for value, maximum in [('ip:'+str(request.remote_addr), limit*5), ('account:'+identity.strip().lower(), limit)]:
        if value == 'account:':
            continue
        digest=hmac.new(str(current_app.secret_key).encode(),(scope+':'+value).encode(),hashlib.sha256).hexdigest()
        buckets.append((digest,maximum))
    db.execute('DELETE FROM auth_throttle WHERE expires_at<=?',(now,))
    for bucket, maximum in buckets:
        row=db.execute('SELECT * FROM auth_throttle WHERE bucket=?',(bucket,)).fetchone()
        if row and row['attempts']>=maximum:
            db.commit()
            return False
    for bucket, _ in buckets:
        db.execute('INSERT INTO auth_throttle VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1',(bucket,now+seconds))
    db.commit()
    return True


def establish_session(user, two_factor=False):
    ensure_security(user['id'])
    security=get_db().execute('SELECT session_version FROM user_security WHERE user_id=?',(user['id'],)).fetchone()
    get_db().commit()
    cart=session.get('cart',{})
    csrf=session.get('csrf_token')
    session.clear()
    session.update(user_id=user['id'],session_version=security['session_version'],cart=cart)
    if csrf:
        session['csrf_token']=csrf
    if two_factor:
        session['admin_2fa']=True


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def make_token(user_id, purpose):
    db=get_db()
    token=secrets.token_urlsafe(32)
    now=int(time.time())
    # Superseded links cannot be replayed.
    db.execute('UPDATE account_tokens SET used_at=? WHERE user_id=? AND purpose=? AND used_at IS NULL',(now,user_id,purpose))
    db.execute('INSERT INTO account_tokens VALUES (?,?,?,?,NULL)',(token_digest(token),user_id,purpose,now+(3600 if purpose=='reset' else 86400)))
    db.commit()
    return token


def find_token(token,purpose):
    if not token or len(token)>200:
        return None
    return get_db().execute('SELECT t.*,u.email,u.status,u.role FROM account_tokens t JOIN users u ON u.id=t.user_id WHERE token_hash=? AND purpose=? AND used_at IS NULL AND expires_at>?',(token_digest(token),purpose,int(time.time()))).fetchone()


def deliver(user, purpose):
    token=make_token(user['id'],purpose)
    origin=current_app.config['APP_ORIGIN'].rstrip('/')
    parsed=urlsplit(origin)
    if parsed.scheme not in ('http','https') or not parsed.netloc:
        raise ValueError('APP_ORIGIN inválido')
    endpoint='account_security.reset' if purpose=='reset' else 'account_security.verify'
    link=origin+url_for(endpoint,token=token)
    message=EmailMessage()
    message['From']=current_app.config['MAIL_FROM']
    message['To']=user['email']
    message['Subject']='Redefina sua senha · Eldoria' if purpose=='reset' else 'Confirme seu e-mail · Eldoria'
    message.set_content(('Use o link para redefinir sua senha. Válido por 1 hora.' if purpose=='reset' else 'Confirme seu endereço de e-mail. Link válido por 24 horas.')+'\n\n'+link+'\n\nSe você não solicitou, ignore esta mensagem. Nunca compartilhe este link.')
    backend=current_app.config['MAIL_BACKEND']
    try:
        if backend=='memory':
            if not current_app.testing:
                raise RuntimeError('O backend memory é exclusivo para testes.')
            current_app.extensions.setdefault('mail_outbox',[]).append(message)
        elif backend=='local':
            folder=Path(current_app.instance_path)/'outbox'
            folder.mkdir(parents=True,exist_ok=True)
            target=folder/(secrets.token_hex(16)+'.eml')
            descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(message.as_bytes())
        elif backend=='smtp':
            context=ssl.create_default_context()
            ssl_mode=current_app.config['SMTP_SSL']
            transport=smtplib.SMTP_SSL if ssl_mode else smtplib.SMTP
            with transport(current_app.config['SMTP_HOST'],current_app.config['SMTP_PORT'],timeout=10,**({'context':context} if ssl_mode else {})) as smtp:
                if not ssl_mode:
                    smtp.starttls(context=context)
                if current_app.config['SMTP_USER']:
                    smtp.login(current_app.config['SMTP_USER'],current_app.config['SMTP_PASSWORD'])
                smtp.send_message(message)
        else:
            raise ValueError('MAIL_BACKEND inválido')
    except Exception:
        # No addresses, credentials or token-bearing URLs in logs.
        current_app.logger.error('Não foi possível entregar a mensagem de autenticação.')
        get_db().execute('UPDATE account_tokens SET used_at=? WHERE token_hash=?',(int(time.time()),token_digest(token)))
        get_db().commit()
        return False
    return True


@bp.route('/esqueci-senha',methods=['GET','POST'])
def forgot():
    if request.method=='POST':
        validate_csrf()
        email=request.form.get('email','').strip().lower()[:254]
        if not consume_limit('reset',email,3,900):
            flash('Aguarde alguns minutos antes de solicitar outro link.','error')
            return render_template('auth/forgot.html',title='Recuperar senha'),429
        user=get_db().execute("SELECT * FROM users WHERE email=? AND role='CUSTOMER' AND status='ACTIVE'",(email,)).fetchone()
        if user:
            deliver(user,'reset')
        flash(GENERIC_RESET,'success')
        return redirect(url_for('account_security.forgot'))
    return render_template('auth/forgot.html',title='Recuperar senha')


@bp.route('/redefinir-senha/<token>',methods=['GET','POST'])
def reset(token):
    record=find_token(token,'reset')
    valid=bool(record and record['status']=='ACTIVE' and record['role']=='CUSTOMER')
    error=None
    if request.method=='POST':
        validate_csrf()
        if not consume_limit('reset-use',request.remote_addr or '',10,900):
            abort(429)
        password=request.form.get('password','')
        error=password_error(password)
        if password!=request.form.get('confirmation',''):
            error='As senhas precisam ser iguais.'
        if valid and not error:
            db=get_db()
            updated=db.execute('UPDATE account_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires_at>?',(int(time.time()),token_digest(token),int(time.time())))
            if updated.rowcount!=1:
                db.rollback()
                valid=False
            else:
                ensure_security(record['user_id'])
                db.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(password),record['user_id']))
                db.execute('UPDATE user_security SET session_version=session_version+1 WHERE user_id=?',(record['user_id'],))
                db.execute("UPDATE account_tokens SET used_at=? WHERE user_id=? AND purpose='reset' AND used_at IS NULL",(int(time.time()),record['user_id']))
                db.commit()
                session.clear()
                flash('Senha redefinida. Entre novamente com sua nova senha.','success')
                return redirect(url_for('auth.login'))
    return render_template('auth/reset.html',title='Redefinir senha',valid=valid,error=error),200 if valid else 400


@bp.route('/confirmar-email/<token>',methods=['GET','POST'])
def verify(token):
    record=find_token(token,'verify')
    valid=bool(record and record['status']=='ACTIVE')
    if request.method=='POST':
        validate_csrf()
        if valid:
            db=get_db()
            changed=db.execute('UPDATE account_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires_at>?',(int(time.time()),token_digest(token),int(time.time())))
            if changed.rowcount==1:
                ensure_security(record['user_id'])
                db.execute('UPDATE user_security SET email_verified_at=? WHERE user_id=?',(utc_now(),record['user_id']))
                db.commit()
                flash('E-mail confirmado com sucesso.','success')
                return redirect(url_for('store.account'))
            db.rollback()
            valid=False
    return render_template('auth/verify.html',title='Confirmar e-mail',valid=valid),200 if valid else 400


@bp.post('/conta/reenviar-confirmacao')
@login_required
def resend():
    validate_csrf()
    if not consume_limit('verify',g.user['email'],3,900):
        flash('Aguarde antes de solicitar outro e-mail.','error')
    elif not g.user['email_verified_at']:
        sent=deliver(g.user,'verify')
        flash('Link de confirmação preparado.' if sent else 'Não foi possível enviar agora. Tente novamente mais tarde.','success' if sent else 'error')
    return redirect(url_for('store.account'))


def totp(secret, step=None):
    step=int(time.time())//30 if step is None else step
    key=base64.b32decode(secret)
    digest=hmac.new(key,struct.pack('>Q',step),hashlib.sha1).digest()
    offset=digest[-1]&15
    return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)


def accept_otp(user_id, code):
    db=get_db()
    security=db.execute('SELECT * FROM user_security WHERE user_id=?',(user_id,)).fetchone()
    if not security or not security['totp_secret']:
        return False
    code=code.strip().replace(' ','')
    if len(code)==6 and code.isascii() and code.isdigit():
        now=int(time.time())//30
        for step in (now-1,now,now+1):
            if step>security['totp_last_step'] and hmac.compare_digest(totp(security['totp_secret'],step),code):
                changed=db.execute('UPDATE user_security SET totp_last_step=? WHERE user_id=? AND totp_last_step<?',(step,user_id,step))
                db.commit()
                return changed.rowcount==1
    digest=token_digest(code.lower().replace('-',''))
    codes=json.loads(security['recovery_codes'])
    if digest in codes:
        codes.remove(digest)
        changed=db.execute('UPDATE user_security SET recovery_codes=? WHERE user_id=? AND recovery_codes=?',(json.dumps(codes),user_id,security['recovery_codes']))
        db.commit()
        return changed.rowcount==1
    return False


@bp.route('/admin/segundo-fator',methods=['GET','POST'])
def challenge():
    pending=session.get('pending_admin')
    if not pending or time.time()-session.get('pending_at',0)>300:
        session.clear()
        return redirect(url_for('admin.login'))
    user=get_db().execute("SELECT * FROM users WHERE id=? AND role='ADMIN' AND status='ACTIVE'",(pending,)).fetchone()
    if not user:
        session.clear()
        return redirect(url_for('admin.login'))
    error=None
    if request.method=='POST':
        validate_csrf()
        if not consume_limit('otp',pending,5,900):
            error='Muitas tentativas. Aguarde alguns minutos.'
            return render_template('admin/challenge.html',title='Verificar acesso',error=error),429
        if accept_otp(pending,request.form.get('code','')):
            establish_session(user,True)
            return redirect(url_for('admin.dashboard'))
        error='Código inválido, expirado ou já utilizado.'
    return render_template('admin/challenge.html',title='Verificar acesso',error=error)


@bp.route('/admin/seguranca',methods=['GET','POST'])
@admin_required
def admin_security():
    db=get_db()
    ensure_security(g.user['id'])
    db.commit()
    row=db.execute('SELECT * FROM user_security WHERE user_id=?',(g.user['id'],)).fetchone()
    recovery=None
    error=None
    if request.method=='POST':
        validate_csrf()
        if not consume_limit('2fa-settings',g.user['id'],8,900):
            abort(429)
        user=db.execute('SELECT password_hash FROM users WHERE id=?',(g.user['id'],)).fetchone()
        if not check_password_hash(user['password_hash'],request.form.get('password','')):
            error='Senha atual incorreta.'
        else:
            action=request.form.get('action')
            if action=='prepare' and not row['totp_secret']:
                secret=base64.b32encode(secrets.token_bytes(20)).decode()
                db.execute('UPDATE user_security SET totp_pending=?, pending_expires=? WHERE user_id=?',(secret,int(time.time())+600,g.user['id']))
                db.commit()
                return redirect(url_for('account_security.admin_security'))
            if action=='enable' and not row['totp_secret'] and row['totp_pending'] and row['pending_expires']>time.time():
                code=request.form.get('code','').strip()
                now=int(time.time())//30
                match=next((step for step in (now-1,now,now+1) if hmac.compare_digest(totp(row['totp_pending'],step),code)),None) if len(code)==6 and code.isascii() and code.isdigit() else None
                if match is not None:
                    recovery=[secrets.token_hex(6) for _ in range(8)]
                    db.execute('UPDATE user_security SET totp_secret=totp_pending,totp_pending=NULL,pending_expires=NULL,totp_last_step=?, recovery_codes=?,session_version=session_version+1 WHERE user_id=?',(match,json.dumps([token_digest(code) for code in recovery]),g.user['id']))
                    from .management import audit
                    audit('Duas etapas ativadas',g.user['id'])
                    db.commit()
                    session['session_version']=row['session_version']+1
                    session['admin_2fa']=True
                else:
                    error='Código inválido. Confira o relógio do celular e tente novamente.'
            elif action=='disable' and row['totp_secret']:
                if accept_otp(g.user['id'],request.form.get('code','')):
                    db.execute("UPDATE user_security SET totp_secret=NULL,recovery_codes='[]',totp_last_step=-1,session_version=session_version+1 WHERE user_id=?",(g.user['id'],))
                    from .management import audit
                    audit('Duas etapas desativadas',g.user['id'])
                    db.commit()
                    session['session_version']=row['session_version']+1
                    flash('Autenticação em duas etapas desativada.','success')
                    return redirect(url_for('account_security.admin_security'))
                error='Código inválido ou já utilizado.'
            elif not recovery and not error:
                error='Configuração expirada ou ação inválida. Inicie a configuração novamente.'
    row=db.execute('SELECT * FROM user_security WHERE user_id=?',(g.user['id'],)).fetchone()
    pending=row['totp_pending'] if row['pending_expires'] and row['pending_expires']>time.time() else None
    uri=('otpauth://totp/'+quote('Eldoria:'+g.user['email'])+'?secret='+pending+'&issuer=Eldoria&digits=6&period=30') if pending else None
    return render_template('admin/security.html',title='Segurança da conta',enabled=bool(row['totp_secret']),pending=pending,uri=uri,recovery=recovery,error=error)
