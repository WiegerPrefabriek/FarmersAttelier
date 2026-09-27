"""Uitgaand verkeer: stuurt een antwoord naar het kanaal waar het gesprek vandaan komt.

Niet geconfigureerd kanaal → mock: het bericht wordt als verzonden gemarkeerd met een
`mock-`-id, zodat de hele flow lokaal te testen is. In de UI is dat zichtbaar.
"""

from __future__ import annotations

from app import db
from app.channels import email_gmail, email_imap, email_microsoft, meta, tiktok


def _mock(msg_id: int, reden: str) -> dict:
    return {"mock": True, "external_id": f"mock-{msg_id}", "note": reden}


def send(conv: dict, body: str, msg_id: int) -> dict:
    kanaal = conv["channel"]
    ref = db.loads(conv.get("external_ref"), {})
    if kanaal in ("email", "shopify"):
        klant = db.one("SELECT email, name FROM customers WHERE id = ?", (conv.get("customer_id"),)) or {}
        if not klant.get("email"):
            raise ValueError("Klant heeft geen e-mailadres; antwoord kan niet per mail")
        laatste_in = db.one("SELECT external_id, source FROM messages WHERE conversation_id = ? AND direction = 'in' "
                            "ORDER BY id DESC LIMIT 1", (conv["id"],)) or {}
        bron = (db.loads(laatste_in.get("source"), {}) or {}).get("external_ref") or {}
        onderwerp = conv.get("subject") or "Je bericht aan Farmers Atelier"
        if not onderwerp.lower().startswith("re:"):
            onderwerp = "Re: " + onderwerp
        if email_microsoft.configured():
            return email_microsoft.send(klant["email"], onderwerp, body, in_reply_to=laatste_in.get("external_id"),
                                        thread_id=conv.get("thread_id"))
        if email_gmail.configured():
            return email_gmail.send(klant["email"], onderwerp, body, in_reply_to=laatste_in.get("external_id"),
                                    references=bron.get("references"), thread_id=conv.get("external_thread_id"))
        if email_imap.configured():
            return email_imap.send(klant["email"], onderwerp, body, in_reply_to=laatste_in.get("external_id"),
                                   references=bron.get("references"))
        return _mock(msg_id, "e-mail niet gekoppeld")
    if kanaal in ("instagram", "facebook"):
        if not meta.configured():
            return _mock(msg_id, "Meta niet gekoppeld")
        if conv.get("via") == "comment":
            return meta.reply_comment(ref.get("comment_id"), body, kanaal)
        ident = db.one("SELECT external_id FROM customer_identities WHERE customer_id = ? AND channel = ?",
                       (conv.get("customer_id"), kanaal))
        if not ident:
            raise ValueError("Geen Meta-identiteit voor deze klant")
        return meta.send_dm(ident["external_id"], body, kanaal, conv)
    if kanaal == "tiktok":
        if not tiktok.configured():
            return _mock(msg_id, "TikTok niet gekoppeld")
        if conv.get("via") == "comment":
            return tiktok.reply_comment(ref.get("comment_id"), ref.get("video_id"), body)
        raise ValueError("TikTok-DM's zijn niet via de API te beantwoorden (zie OPENSTAANDE_ZAKEN §7)")
    raise ValueError(f"onbekend kanaal {kanaal}")


def hide_comment(conv: dict, params: dict) -> dict:
    ref = db.loads(conv.get("external_ref"), {})
    kanaal = conv["channel"]
    hide = params.get("hide", True)
    if kanaal in ("instagram", "facebook"):
        if not meta.configured():
            return {"mock": True, "hidden": hide}
        return meta.hide_comment(ref.get("comment_id"), hide, kanaal)
    if kanaal == "tiktok":
        if not tiktok.configured():
            return {"mock": True, "hidden": hide}
        return tiktok.hide_comment(ref.get("comment_id"), ref.get("video_id"), hide)
    raise ValueError("verbergen kan alleen bij social comments")


def private_reply(conv: dict, body: str) -> dict:
    ref = db.loads(conv.get("external_ref"), {})
    if conv["channel"] in ("instagram", "facebook") and conv.get("via") == "comment":
        if not meta.configured():
            return {"mock": True}
        return meta.private_reply(ref.get("comment_id"), body)
    raise ValueError("privé antwoord alleen bij Meta-comments")
