"""One-time e-mail verification codes for password reset and first-time member setup.

* 6-digit code, stored only as an HMAC (keyed by APP_SECRET_KEY), never in plain text.
* Time-limited, single-use, burned after MAX_ATTEMPTS wrong guesses.
* A new code invalidates earlier ones; requests are throttled per account.
* Delivery uses SMTP when SMTP_HOST/SMTP_USER/SMTP_PASSWORD are configured; otherwise the code is
  written to the backend log for local development. The code is never returned by any API.
"""
import hashlib,hmac,logging,secrets,smtplib
from datetime import datetime,timedelta,timezone
from email.message import EmailMessage
from app.core.config import settings
from app.core.security import new_id
from app.models import PasswordReset

logger=logging.getLogger('uvicorn.error')
RESET_MINUTES=10
INVITE_HOURS=72
MAX_ATTEMPTS=5
COOLDOWN_SECONDS=60
MAX_CODES_PER_HOUR=5


def _now():
    return datetime.now(timezone.utc)


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def smtp_configured():
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def delivery_mode():
    return 'smtp' if smtp_configured() else 'local_log'


def _digest(user_id,code):
    return hmac.new(settings.app_secret_key.encode(),f'{user_id}:{code}'.encode(),hashlib.sha256).hexdigest()


def can_issue(db,user):
    """False while inside the cooldown or past the hourly cap (callers still answer generically)."""
    recent=db.query(PasswordReset).filter(PasswordReset.user_id==user.id,
        PasswordReset.created_at>=_now()-timedelta(hours=1)).order_by(PasswordReset.created_at.desc()).all()
    if len(recent)>=MAX_CODES_PER_HOUR:return False
    return not recent or (_now()-_aware(recent[0].created_at)).total_seconds()>=COOLDOWN_SECONDS


def issue_code(db,user,purpose='reset'):
    """Create a fresh code (invalidating older ones) and return it. Caller must send it; never return it to clients."""
    now=_now()
    for old in db.query(PasswordReset).filter_by(user_id=user.id,used_at=None):old.used_at=now
    code=f'{secrets.randbelow(1_000_000):06d}'
    ttl=timedelta(hours=INVITE_HOURS) if purpose=='invite' else timedelta(minutes=RESET_MINUTES)
    db.add(PasswordReset(id=new_id(),user_id=user.id,purpose=purpose,code_hash=_digest(user.id,code),expires_at=now+ttl))
    db.commit()
    return code


def consume_code(db,user,code):
    """True and the code is burned when valid; every failure is indistinguishable to the caller."""
    row=db.query(PasswordReset).filter_by(user_id=user.id,used_at=None).order_by(PasswordReset.created_at.desc()).first()
    now=_now()
    if not row or _aware(row.expires_at)<now or row.attempts>=MAX_ATTEMPTS:return False
    if not hmac.compare_digest(row.code_hash,_digest(user.id,code)):
        row.attempts+=1
        if row.attempts>=MAX_ATTEMPTS:row.used_at=now
        db.commit();return False
    row.used_at=now;db.commit();return True


def send_code(to,name,code,purpose='reset'):
    """Send the code by SMTP, or log it clearly for local development. Returns the delivery mode."""
    invite=purpose=='invite'
    minutes=INVITE_HOURS*60 if invite else RESET_MINUTES
    window=f'{INVITE_HOURS} hours' if invite else f'{RESET_MINUTES} minutes'
    if not smtp_configured():
        logger.warning('\n==== LOCAL DEV: SMTP not configured; verification e-mail NOT sent ====\n'
                       '  %s code for %s: %s (valid %s)\n'
                       '  Configure SMTP_HOST/SMTP_USER/SMTP_PASSWORD in backend/.env to send real e-mail.\n'
                       '====================================================================',
                       'Account setup' if invite else 'Password reset',to,code,window)
        return 'local_log'
    subject='Set up your AI Shorts account' if invite else 'Your AI Shorts password reset code'
    intro=('You have been invited to AI Shorts. Use this code on the sign-in page (Set up / verify account) to choose your password.'
           if invite else 'Use this code on the sign-in page (Forgot password) to choose a new password.')
    message=EmailMessage()
    message['Subject']=subject;message['From']=settings.smtp_from or settings.smtp_user;message['To']=to
    message.set_content(f'Hello {name},\n\n{intro}\n\nVerification code: {code}\n\nThe code works once and expires in {window}. '
                        'If you did not expect this e-mail, you can ignore it.\n')
    try:
        if settings.smtp_port==465:
            client=smtplib.SMTP_SSL(settings.smtp_host,settings.smtp_port,timeout=20)
        else:
            client=smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=20);client.starttls()
        with client:
            client.login(settings.smtp_user,settings.smtp_password);client.send_message(message)
        return 'smtp'
    except Exception as exc:
        logger.warning('Verification e-mail could not be sent (%s). The code was not logged.',type(exc).__name__)
        return 'failed'
