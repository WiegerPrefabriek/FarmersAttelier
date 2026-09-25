"""Meta: Instagram-DM's en -comments, Facebook Messenger en pagina-comments.

Route (a) uit docs/onderzoek/04: één Meta-app, één Page access token (System User),
Instagram gekoppeld aan de Facebook-pagina. Webhooks komen binnen op /webhooks/meta:
  GET  → verificatie (hub.challenge terugsturen)
  POST → X-Hub-Signature-256 controleren, payload in de wachtrij, 200 terug.
`parse_webhook()` maakt er inbound-dicts van; de rest is versturen/verbergen.

Vensters: 24 uur na het laatste klantbericht; daarna alleen met HUMAN_AGENT-tag
(7 dagen, vereist App Review). We proberen eerst zonder tag, dan met tag.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import config
from app import db

try:
    import requests
except ImportError:
    requests = None

GRAPH = "https://graph.facebook.com"


def configured() -> bool:
    m = config.secret("meta") or {}
    return bool(requests and m.get("page_access_token") and m.get("page_id"))


def _v() -> str:
    return config.secret("meta", "graph_version", default="v25.0")


def _token() -> str:
    return config.secret("meta", "page_access_token")


def _page_id() -> str:
    return config.secret("meta", "page_id")


def _ig_id() -> str:
    return config.secret("meta", "ig_account_id") or ""


def verify_challenge(params: dict) -> str | None:
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == config.secret("meta", "verify_token"):
        return params.get("hub.challenge")
    return None


def verify_signature(raw: bytes, header: str | None) -> bool:
    secret = config.secret("meta", "app_secret")
    if not secret:
        return True  # nog niet geconfigureerd: niet blokkeren tijdens lokaal testen
    if not header or not header.startswith("sha256="):
        return False
    verwacht = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(verwacht, header.split("=", 1)[1])


def _graph(method: str, pad: str, **kwargs) -> dict:
    url = f"{GRAPH}/{_v()}/{pad}"
    params = kwargs.pop("params", {})
    params["access_token"] = _token()
    r = requests.request(method, url, params=params, timeout=30, **kwargs)
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text}
    if r.status_code >= 400 or "error" in data:
        fout = (data.get("error") or {})
        raise RuntimeError(f"Meta {r.status_code}: {fout.get('message') or data} (code {fout.get('code')}, sub {fout.get('error_subcode')})")
    return data


def fetch_profile(psid: str, kanaal: str) -> dict:
    """Naam/username/profielfoto van de afzender (alleen deze velden geeft Meta vrij)."""
    if not configured():
        return {}
    velden = "name,username,profile_pic,follower_count,is_user_follow_business" if kanaal == "instagram" else "name,profile_pic"
    try:
        return _graph("GET", psid, params={"fields": velden})
    except RuntimeError as fout:
        print(f"   ! Meta-profiel {psid}: {fout}", flush=True)
        return {}


def parse_webhook(payload: dict) -> list[dict]:
    """Webhook-payload → lijst inbound-dicts (DM's en comments)."""
    uit = []
    objekt = payload.get("object")
    kanaal = "instagram" if objekt == "instagram" else "facebook"
    eigen_ids = {str(_page_id()), str(_ig_id())}
    for entry in payload.get("entry", []):
        eigen_ids.add(str(entry.get("id")))
        # --- DM's ---
        for ev in entry.get("messaging", []):
            msg = ev.get("message") or {}
            if not msg or msg.get("is_deleted"):
                continue
            sender = str((ev.get("sender") or {}).get("id"))
            recipient = str((ev.get("recipient") or {}).get("id"))
            echo = bool(msg.get("is_echo")) or sender in eigen_ids
            klant_id = recipient if echo else sender
            bijlagen = [{"name": a.get("type"), "url": (a.get("payload") or {}).get("url"), "content_type": a.get("type")}
                        for a in msg.get("attachments") or []]
            tekst = msg.get("text") or ""
            if not tekst and bijlagen:
                tekst = "[" + ", ".join(b["name"] or "bijlage" for b in bijlagen) + "]"
            profiel = {} if echo else fetch_profile(klant_id, kanaal)
            uit.append({
                "channel": kanaal, "via": "dm", "external_message_id": msg.get("mid"),
                "external_thread_id": klant_id,
                "sender": {"channel": kanaal, "external_id": klant_id, "handle": profiel.get("username"),
                           "name": profiel.get("name") or profiel.get("username") or f"{kanaal}-{klant_id[-6:]}",
                           "avatar_url": profiel.get("profile_pic")},
                "text": tekst, "attachments": bijlagen, "is_echo": echo,
                "sent_at": _ts(ev.get("timestamp")),
                "external_ref": {"reply_to": (msg.get("reply_to") or {}).get("mid"), "psid": klant_id},
            })
        # --- Comments / mentions ---
        for ch in entry.get("changes", []):
            veld, v = ch.get("field"), ch.get("value") or {}
            if kanaal == "instagram" and veld in ("comments", "mentions"):
                van = v.get("from") or {}
                if str(van.get("id")) in eigen_ids:
                    continue
                cid = v.get("id") or v.get("comment_id")
                media = v.get("media") or {}
                uit.append({
                    "channel": "instagram", "via": "comment" if veld == "comments" else "mention",
                    "external_message_id": f"ig-comment-{cid}",
                    "external_thread_id": v.get("parent_id") or cid,
                    "sender": {"channel": "instagram", "external_id": str(van.get("id")), "handle": van.get("username"),
                               "name": van.get("username") or "instagram-gebruiker"},
                    "text": v.get("text") or "", "attachments": [], "sent_at": _ts(entry.get("time")),
                    "external_ref": {"comment_id": cid, "media_id": media.get("id") or v.get("media_id"),
                                     "media_type": media.get("media_product_type"), "parent_id": v.get("parent_id")},
                })
            elif kanaal == "facebook" and veld == "feed" and v.get("item") == "comment" and v.get("verb") == "add":
                van = v.get("from") or {}
                if str(van.get("id")) in eigen_ids:
                    continue
                cid = v.get("comment_id")
                ouder = v.get("parent_id")
                uit.append({
                    "channel": "facebook", "via": "comment", "external_message_id": f"fb-comment-{cid}",
                    "external_thread_id": ouder if ouder and ouder != v.get("post_id") else cid,
                    "sender": {"channel": "facebook", "external_id": str(van.get("id")), "name": van.get("name") or "facebook-gebruiker"},
                    "text": v.get("message") or "", "attachments": [], "sent_at": _ts(v.get("created_time")),
                    "external_ref": {"comment_id": cid, "post_id": v.get("post_id"), "parent_id": ouder,
                                     "permalink": v.get("permalink_url")},
                })
    return uit


def _ts(waarde) -> str | None:
    import datetime as dt
    if not waarde:
        return None
    try:
        w = float(waarde)
        if w > 1e12:
            w /= 1000
        return dt.datetime.utcfromtimestamp(w).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def send_dm(psid: str, tekst: str, kanaal: str, conv: dict | None = None) -> dict:
    """DM sturen; buiten 24 uur opnieuw proberen met HUMAN_AGENT-tag."""
    body = {"recipient": {"id": psid}, "message": {"text": tekst[:1000 if kanaal == "instagram" else 2000]}}
    try:
        data = _graph("POST", f"{_page_id()}/messages", json=body)
    except RuntimeError as fout:
        if "2018278" in str(fout) or "24 hour" in str(fout).lower() or "outside" in str(fout).lower():
            body.update({"messaging_type": "MESSAGE_TAG", "tag": "HUMAN_AGENT"})
            data = _graph("POST", f"{_page_id()}/messages", json=body)
        else:
            raise
    return {"external_id": data.get("message_id"), "recipient_id": data.get("recipient_id")}


def reply_comment(comment_id: str, tekst: str, kanaal: str) -> dict:
    if not comment_id:
        raise ValueError("comment_id ontbreekt")
    if kanaal == "instagram":
        data = _graph("POST", f"{comment_id}/replies", params={"message": tekst})
    else:
        data = _graph("POST", f"{comment_id}/comments", params={"message": tekst})
    return {"external_id": data.get("id")}


def hide_comment(comment_id: str, hide: bool, kanaal: str) -> dict:
    if kanaal == "instagram":
        return _graph("POST", comment_id, params={"hide": "true" if hide else "false"})
    return _graph("POST", comment_id, params={"is_hidden": "true" if hide else "false"})


def private_reply(comment_id: str, tekst: str) -> dict:
    data = _graph("POST", f"{_page_id()}/messages", json={"recipient": {"comment_id": comment_id}, "message": {"text": tekst}})
    return {"external_id": data.get("message_id")}


def subscribe_page(velden: str = "messages,messaging_postbacks,message_echoes,feed") -> dict:
    return _graph("POST", f"{_page_id()}/subscribed_apps", params={"subscribed_fields": velden})


def voorbeeld_payload_ig_dm() -> dict:
    """Voor tests en handmatig oefenen."""
    return json.loads("""{"object":"instagram","entry":[{"id":"17841400000000000","time":1758790000000,
      "messaging":[{"sender":{"id":"1234567890123456"},"recipient":{"id":"17841400000000000"},"timestamp":1758790000000,
      "message":{"mid":"mid.test.1","text":"Hoi, is maat M nog op voorraad?"}}]}]}""")
