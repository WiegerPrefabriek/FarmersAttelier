"""E-mail via IMAP (ophalen) en SMTP (versturen) — voor gewone hosting zoals TransIP,
Hostnet, Strato. Config in `.secrets.json` onder "imap" en "smtp".
"""

from __future__ import annotations

import imaplib
import smtplib
import ssl

import config
from app.channels import email_common


def configured() -> bool:
    i = config.secret("imap") or {}
    s = config.secret("smtp") or {}
    return bool(i.get("host") and i.get("user") and i.get("password") and s.get("host") and s.get("from"))


def fetch_new() -> list[dict]:
    if not configured():
        return []
    i = config.secret("imap")
    uit = []
    with imaplib.IMAP4_SSL(i["host"], int(i.get("port", 993))) as box:
        box.login(i["user"], i["password"])
        box.select("INBOX")
        status, data = box.search(None, "UNSEEN")
        if status != "OK":
            return []
        for num in data[0].split():
            status, msg_data = box.fetch(num, "(RFC822)")
            if status != "OK":
                continue
            raw = msg_data[0][1]
            inbound = email_common.parse_rfc822(raw, ons_adres=config.secret("smtp", "from"))
            box.store(num, "+FLAGS", "\\Seen")
            if inbound:
                uit.append(inbound)
    return uit


def send(naar: str, onderwerp: str, body: str, in_reply_to: str | None = None, references: str | None = None) -> dict:
    s = config.secret("smtp")
    m = email_common.build_reply(s["from"], naar, onderwerp, body, in_reply_to, references)
    poort = int(s.get("port", 587))
    ctx = ssl.create_default_context()
    if poort == 465:
        server = smtplib.SMTP_SSL(s["host"], poort, context=ctx, timeout=30)
    else:
        server = smtplib.SMTP(s["host"], poort, timeout=30)
        server.starttls(context=ctx)
    with server:
        if s.get("user"):
            server.login(s["user"], s["password"])
        server.send_message(m)
    return {"external_id": m["Message-ID"], "references": m.get("References")}
