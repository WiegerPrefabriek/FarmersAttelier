"""E-mail via de Gmail API (Google Workspace of Gmail).

Koppelen: `scripts/gmail_koppelen.py` (OAuth, zelfde aanpak als het inkoopsysteem):
je logt één keer in, Google geeft een refresh_token, dat komt in `.secrets.json` onder
"gmail". Scopes: gmail.modify (lezen + label) en gmail.send.

Ophalen: pollen met `history.list` vanaf de laatste historyId (elke 30-60 s); de
eerste keer `messages.list` op INBOX van de laatste 7 dagen. Verstuurde antwoorden gaan
in dezelfde Gmail-thread (threadId + In-Reply-To/References).
"""

from __future__ import annotations

import base64
import time

import config
from app import db
from app.channels import email_common

try:
    import requests
except ImportError:
    requests = None

TOKEN_URI = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
_TOKEN = {"value": None, "expires": 0.0}


def configured() -> bool:
    g = config.secret("gmail") or {}
    return bool(requests and g.get("refresh_token") and g.get("client_id") and g.get("client_secret"))


def afzender() -> str:
    return config.secret("gmail", "afzender", default=config.SUPPORT_EMAIL_FALLBACK)


def _access_token() -> str:
    if _TOKEN["value"] and time.time() < _TOKEN["expires"] - 60:
        return _TOKEN["value"]
    g = config.secret("gmail")
    r = requests.post(TOKEN_URI, data={"client_id": g["client_id"], "client_secret": g["client_secret"],
                                       "refresh_token": g["refresh_token"], "grant_type": "refresh_token"}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Gmail-token verversen mislukt ({r.status_code}): {r.text[:200]}")
    data = r.json()
    _TOKEN["value"] = data["access_token"]
    _TOKEN["expires"] = time.time() + int(data.get("expires_in", 3600))
    return _TOKEN["value"]


def _get(pad: str, **params) -> dict:
    r = requests.get(f"{API}/{pad}", params=params, headers={"Authorization": f"Bearer {_access_token()}"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Gmail GET {pad}: {r.status_code} {r.text[:200]}")
    return r.json()


def _post(pad: str, body: dict) -> dict:
    r = requests.post(f"{API}/{pad}", json=body, headers={"Authorization": f"Bearer {_access_token()}"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Gmail POST {pad}: {r.status_code} {r.text[:200]}")
    return r.json()


def fetch_new() -> list[dict]:
    """Nieuwe inbox-berichten sinds de laatste keer → inbound-dicts."""
    if not configured():
        return []
    start = db.setting("gmail_history_id")
    ids = []
    if start:
        try:
            data = _get("history", startHistoryId=start, historyTypes="messageAdded", labelId="INBOX")
            for h in data.get("history", []):
                for m in h.get("messagesAdded", []):
                    ids.append(m["message"]["id"])
            if data.get("historyId"):
                db.set_setting("gmail_history_id", data["historyId"])
        except RuntimeError as fout:
            if "404" in str(fout):  # historyId te oud → opnieuw beginnen
                start = None
            else:
                raise
    if not start:
        data = _get("messages", q="in:inbox newer_than:7d", maxResults=50)
        ids = [m["id"] for m in data.get("messages", [])]
        profiel = _get("profile")
        db.set_setting("gmail_history_id", profiel.get("historyId"))
    uit = []
    for mid in ids:
        if db.one("SELECT 1 FROM inbound_queue WHERE source = 'gmail' AND external_id = ?", (mid,)):
            continue
        raw = _get(f"messages/{mid}", format="raw")
        inbound = email_common.parse_rfc822(base64.urlsafe_b64decode(raw["raw"] + "=="), thread_id=raw.get("threadId"),
                                            ons_adres=afzender())
        db.insert("inbound_queue", {"source": "gmail", "external_id": mid, "payload": {"id": mid}, "status": "done",
                                    "processed_at": db.now()})
        if inbound:
            uit.append(inbound)
    return uit


def send(naar: str, onderwerp: str, body: str, in_reply_to: str | None = None, references: str | None = None,
         thread_id: str | None = None) -> dict:
    m = email_common.build_reply(afzender(), naar, onderwerp, body, in_reply_to, references)
    raw = base64.urlsafe_b64encode(m.as_bytes()).decode("ascii")
    payload = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    resp = _post("messages/send", payload)
    if not resp.get("id"):
        raise RuntimeError("Gmail gaf geen bericht-id terug — niet verzonden")
    return {"external_id": m["Message-ID"], "gmail_id": resp["id"], "thread_id": resp.get("threadId"), "references": m.get("References")}
