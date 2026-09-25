"""TikTok: comments op eigen video's via de TikTok API for Business (scope "TikTok
Accounts"), na goedkeuring van het Accounts API Access-formulier. DM's zijn niet
beschikbaar zonder allowlist (zie OPENSTAANDE_ZAKEN §7).

Er is geen comment-webhook: we pollen. Endpoints (v1.3, business-api.tiktok.com):
  GET  /business/video/list/     — recente video's van het account
  GET  /business/comment/list/   — comments per video
  POST /business/comment/reply/  — antwoorden
  POST /business/comment/hide/   — verbergen  [parameters te verifiëren zodra we toegang hebben]
"""

from __future__ import annotations

import config
from app import db

try:
    import requests
except ImportError:
    requests = None

BASE = "https://business-api.tiktok.com/open_api/v1.3"


def configured() -> bool:
    t = config.secret("tiktok") or {}
    return bool(requests and t.get("access_token") and t.get("business_id"))


def _get(pad: str, params: dict) -> dict:
    r = requests.get(f"{BASE}{pad}", params=params, headers={"Access-Token": config.secret("tiktok", "access_token")}, timeout=30)
    data = r.json()
    if data.get("code") not in (0, None):
        raise RuntimeError(f"TikTok {data.get('code')}: {data.get('message')}")
    return data.get("data") or {}


def _post(pad: str, body: dict) -> dict:
    r = requests.post(f"{BASE}{pad}", json=body, headers={"Access-Token": config.secret("tiktok", "access_token")}, timeout=30)
    data = r.json()
    if data.get("code") not in (0, None):
        raise RuntimeError(f"TikTok {data.get('code')}: {data.get('message')}")
    return data.get("data") or {}


def fetch_new() -> list[dict]:
    """Nieuwe comments op de laatste video's → inbound-dicts."""
    if not configured():
        return []
    bid = config.secret("tiktok", "business_id")
    uit = []
    videos = _get("/business/video/list/", {"business_id": bid, "fields": '["item_id","caption","create_time"]', "max_count": 10})
    for v in videos.get("videos", []):
        comments = _get("/business/comment/list/", {"business_id": bid, "video_id": v.get("item_id"), "max_count": 30,
                                                    "sort_field": "create_time", "sort_order": "DESC"})
        for c in comments.get("comments", []):
            cid = c.get("comment_id")
            if db.one("SELECT 1 FROM inbound_queue WHERE source = 'tiktok' AND external_id = ?", (cid,)):
                continue
            db.insert("inbound_queue", {"source": "tiktok", "external_id": cid, "payload": c, "status": "done", "processed_at": db.now()})
            if c.get("owner"):
                continue
            uit.append({
                "channel": "tiktok", "via": "comment", "external_message_id": f"tt-comment-{cid}",
                "external_thread_id": c.get("parent_comment_id") or cid,
                "sender": {"channel": "tiktok", "external_id": str(c.get("user_id") or c.get("username")),
                           "handle": c.get("username"), "name": c.get("display_name") or c.get("username")},
                "text": c.get("text") or "", "attachments": [], "sent_at": None,
                "external_ref": {"comment_id": cid, "video_id": v.get("item_id"), "caption": (v.get("caption") or "")[:80]},
            })
    return uit


def reply_comment(comment_id: str, video_id: str, tekst: str) -> dict:
    data = _post("/business/comment/reply/", {"business_id": config.secret("tiktok", "business_id"),
                                              "video_id": video_id, "comment_id": comment_id, "text": tekst[:150]})
    return {"external_id": data.get("comment_id")}


def hide_comment(comment_id: str, video_id: str, hide: bool) -> dict:
    return _post("/business/comment/hide/", {"business_id": config.secret("tiktok", "business_id"),
                                             "video_id": video_id, "comment_id": comment_id, "action": "HIDE" if hide else "UNHIDE"})
