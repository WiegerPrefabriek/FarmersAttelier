"""Gedeelde e-mailhulpjes: RFC822 parsen naar onze inbound-vorm, quotes strippen,
auto-replies en bounces herkennen, en een antwoordmail opbouwen met threading-headers.
"""

from __future__ import annotations

import datetime
import email
import email.utils
import html as _html
import re
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.policy import default as default_policy

AUTO_HEADERS = ("auto-submitted", "x-auto-response-suppress", "x-autoreply", "x-autorespond", "list-id", "list-unsubscribe")


def _decode(waarde) -> str:
    if not waarde:
        return ""
    try:
        return str(make_header(decode_header(str(waarde))))
    except Exception:  # noqa: BLE001
        return str(waarde)


def is_auto_reply(msg) -> bool:
    for h in AUTO_HEADERS:
        v = (msg.get(h) or "").lower()
        if h == "auto-submitted" and v and v != "no":
            return True
        if h != "auto-submitted" and v:
            return True
    prec = (msg.get("precedence") or "").lower()
    return prec in ("bulk", "auto_reply", "junk", "list")


def is_bounce(msg) -> bool:
    van = (msg.get("from") or "").lower()
    if "mailer-daemon" in van or "postmaster@" in van:
        return True
    ct = msg.get_content_type()
    return ct == "multipart/report" or (msg.get("return-path") or "").strip() in ("<>",)


QUOTE_PATTERNS = [
    r"^\s*Op .{5,120} schreef .{1,120}:\s*$",          # NL Gmail
    r"^\s*On .{5,120} wrote:\s*$",                      # EN Gmail
    r"^\s*-{2,}\s*Oorspronkelijk bericht\s*-{2,}",       # Outlook NL
    r"^\s*-{2,}\s*Original Message\s*-{2,}",
    r"^\s*Van:\s.+$",                                    # Outlook NL header block
    r"^\s*From:\s.+$",
    r"^\s*_{5,}\s*$",
    r"^\s*Verzonden vanaf mijn iPhone",
    r"^\s*Sent from my ",
]
_QUOTE_RE = re.compile("|".join(f"(?:{p})" for p in QUOTE_PATTERNS), re.IGNORECASE | re.MULTILINE)


def strip_quotes(tekst: str) -> str:
    """Houdt alleen het nieuwe deel van een antwoord over."""
    if not tekst:
        return ""
    m = _QUOTE_RE.search(tekst)
    if m and m.start() > 0:
        tekst = tekst[:m.start()]
    regels = [r for r in tekst.splitlines() if not r.lstrip().startswith(">")]
    uit = "\n".join(regels).strip()
    return uit or tekst.strip()


def html_to_text(html: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", html or "")
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"&amp;", "&", t)
    t = re.sub(r"&lt;", "<", t)
    t = re.sub(r"&gt;", ">", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def parse_rfc822(raw: bytes, thread_id: str | None = None, ons_adres: str | None = None) -> dict | None:
    """RFC822-bytes → inbound-dict, of None als het een auto-reply/bounce is."""
    msg = email.message_from_bytes(raw, policy=default_policy)
    if is_auto_reply(msg) or is_bounce(msg):
        return None
    naam, adres = email.utils.parseaddr(_decode(msg.get("from")))
    if ons_adres and adres.lower() == ons_adres.lower():
        is_echo = True
    else:
        is_echo = False
    tekst, html = "", None
    bijlagen = []
    if msg.is_multipart():
        for deel in msg.walk():
            ct = deel.get_content_type()
            disp = (deel.get("content-disposition") or "")
            if "attachment" in disp or deel.get_filename():
                bijlagen.append({"name": _decode(deel.get_filename()) or "bijlage", "content_type": ct, "url": None,
                                 "size": len(deel.get_payload(decode=True) or b"")})
            elif ct == "text/plain" and not tekst:
                tekst = deel.get_content()
            elif ct == "text/html" and not html:
                html = deel.get_content()
    else:
        if msg.get_content_type() == "text/html":
            html = msg.get_content()
        else:
            tekst = msg.get_content()
    if not tekst and html:
        tekst = html_to_text(html)
    datum = None
    try:
        d = email.utils.parsedate_to_datetime(msg.get("date"))
        datum = d.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None
    except Exception:  # noqa: BLE001
        datum = None
    refs = (msg.get("references") or "").split()
    return {
        "channel": "email", "via": "email",
        "external_message_id": (msg.get("message-id") or "").strip() or None,
        "external_thread_id": thread_id or (refs[0] if refs else (msg.get("message-id") or "").strip() or None),
        "sender": {"channel": "email", "external_id": adres.lower(), "name": naam or adres, "email": adres.lower()},
        "subject": _decode(msg.get("subject")),
        "text": strip_quotes(tekst), "html": html, "attachments": bijlagen, "sent_at": datum,
        "external_ref": {"in_reply_to": (msg.get("in-reply-to") or "").strip(), "references": " ".join(refs)},
        "is_echo": is_echo,
    }


def build_reply(van: str, naar: str, onderwerp: str, body: str, in_reply_to: str | None = None,
                references: str | None = None) -> EmailMessage:
    m = EmailMessage()
    m["From"] = van
    m["To"] = naar
    m["Subject"] = onderwerp
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = ((references or "") + " " + in_reply_to).strip()
    m["Message-ID"] = email.utils.make_msgid(domain=van.split("@")[-1] if "@" in van else None)
    m.set_content(body)
    html = "<div style=\"font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.5\">" + \
        "<br>".join(_html.escape(regel) for regel in body.split("\n")) + "</div>"
    m.add_alternative(html, subtype="html")
    return m
