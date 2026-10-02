"""Envio de e-mails transacionais pelo SMTP do Brevo (ou qualquer SMTP com STARTTLS)."""
import html
import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger("meuingles.mail")


def configured() -> bool:
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM"))


def base_url() -> str:
    return (os.environ.get("APP_BASE_URL") or "https://meuingles.wellgois.com/").rstrip("/") + "/"


def send(to: str, subject: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> bool:
    """Envia um e-mail simples (texto + HTML). Devolve False se não estiver configurado ou falhar."""
    if not configured():
        log.warning("E-mail não configurado; mensagem para %s não enviada: %s", to, subject)
        return False
    text = "\n\n".join(paragraphs)
    if button:
        text += f"\n\n{button[0]}: {button[1]}"
    text += "\n\nMeuInglês · inglês falado para engenharia de dados"
    body = "".join(f'<p style="margin:0 0 14px">{html.escape(p)}</p>' for p in paragraphs)
    if button:
        body += (f'<p style="margin:22px 0"><a href="{html.escape(button[1])}" style="background:#0E6F7A;color:#fff;'
                 f'padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:700">{html.escape(button[0])}</a></p>'
                 f'<p style="font-size:12px;color:#5B6B75">Se o botão não funcionar, copie este endereço: {html.escape(button[1])}</p>')
    page = (f'<div style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;color:#142028;max-width:520px">'
            f'<p style="font-size:20px;font-weight:700;color:#0E6F7A;margin:0 0 18px">MeuInglês</p>{body}'
            f'<p style="font-size:12px;color:#5B6B75;margin-top:28px">Inglês falado para engenharia de dados.</p></div>')
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("MeuInglês", os.environ["MAIL_FROM"]))
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(page, subtype="html")
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=20) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        log.warning("Falha ao enviar e-mail para %s: %s", to, e)
        return False
