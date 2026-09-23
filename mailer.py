"""Outgoing email over SMTP. Configure the [smtp] table in Streamlit secrets."""
import smtplib
import ssl
from email.message import EmailMessage

from core.config import secret_section


def configured():
    s = secret_section("smtp")
    return all(s.get(k) for k in ("host", "username", "password"))


def send(to, subject, body):
    s = secret_section("smtp")
    if not configured():
        return False, "Email is not configured."
    port = int(s.get("port", 587))
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s.get("sender") or s["username"]
    msg["To"] = to
    msg.set_content(body)
    try:
        if port == 465:
            with smtplib.SMTP_SSL(s["host"], port, context=ssl.create_default_context(), timeout=15) as server:
                server.login(s["username"], s["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(s["host"], port, timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(s["username"], s["password"])
                server.send_message(msg)
        return True, None
    except Exception as exc:  # network or auth failure
        return False, f"{type(exc).__name__}: {exc}"
