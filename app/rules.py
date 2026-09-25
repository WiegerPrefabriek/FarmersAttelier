"""Rules-engine: ALS (condities) DAN (acties), zoals Gorgias' WHEN/IF/THEN.

Een rule is een rij in `rules` met:
  trigger:    message_analyzed (na elke AI-analyse) | ticket_created | before_send
  conditions: [{"field": "intent", "op": "is", "value": "feedback.complaint"}, ...]  (AND)
  actions:    [{"type": "set_priority", "value": "high"}, {"type": "needs_human", "value": "Klacht"}]

Velden die je kunt testen: intent, intent_group, sentiment, priority, channel, via,
language, needs_human, escalation_flags (contains), missing_info (contains), order_found,
tracking_available, order_fulfillment_status, order_financial_status, customer_orders_count,
customer_total_spent, body (contains), subject (contains), tags (contains), hour (0-23), weekday (0-6).
Ops: is, is_not, contains, not_contains, in, gt, lt, gte, lte, is_empty, not_empty, matches (regex).
Acties: set_priority, set_status, needs_human, allow_ai (max niveau: analyze|draft|auto_reply|action),
add_tag, remove_tag, assign_user, set_intent, add_note, snooze_hours, close, mark_spam.
"""

from __future__ import annotations

import datetime as dt
import re

from app import db
from app.taxonomy import intent_group

DEFAULT_RULES = [
    dict(name="Klacht + negatief → hoge prioriteit, mens nodig", priority=10,
         conditions=[{"field": "intent", "op": "is", "value": "feedback.complaint"},
                     {"field": "sentiment", "op": "is", "value": "negative"}],
         actions=[{"type": "set_priority", "value": "high"}, {"type": "needs_human", "value": "Klacht met negatief sentiment"},
                  {"type": "add_tag", "value": "klacht"}],
         description="Boze klanten willen een mens, geen bot."),
    dict(name="Juridisch / chargeback / dreigend → kritiek, mens nodig", priority=5,
         conditions=[{"field": "escalation_flags", "op": "contains_any", "value": ["legal_threat", "chargeback", "abusive"]}],
         actions=[{"type": "set_priority", "value": "critical"}, {"type": "needs_human", "value": "Juridische dreiging / chargeback / dreigend"},
                  {"type": "allow_ai", "value": "analyze"}, {"type": "add_tag", "value": "escalatie"}],
         description="Serieuze problemen gaan altijd direct naar een mens."),
    dict(name="Klant vraagt om een mens → mens nodig", priority=6,
         conditions=[{"field": "escalation_flags", "op": "contains", "value": "human_requested"}],
         actions=[{"type": "needs_human", "value": "Klant vraagt om een medewerker"}, {"type": "allow_ai", "value": "analyze"}]),
    dict(name="Refund-verzoek → mens nodig", priority=20,
         conditions=[{"field": "intent", "op": "in", "value": ["refund.request", "payment.issue"]}],
         actions=[{"type": "needs_human", "value": "Geldzaken beslist een mens"}, {"type": "allow_ai", "value": "draft"}]),
    dict(name="Orderstatus + order gevonden + tracking → AI mag concept maken", priority=30,
         conditions=[{"field": "intent", "op": "is", "value": "shipping.status"},
                     {"field": "order_found", "op": "is", "value": True},
                     {"field": "tracking_available", "op": "is", "value": True}],
         actions=[{"type": "allow_ai", "value": "draft"}, {"type": "add_tag", "value": "wismo"}],
         description="Het klassieke Gorgias-scenario: alles is bekend, AI schrijft het antwoord."),
    dict(name="Orderstatus zonder order → eerst ordernummer vragen", priority=31,
         conditions=[{"field": "intent", "op": "is", "value": "shipping.status"},
                     {"field": "order_found", "op": "is", "value": False}],
         actions=[{"type": "allow_ai", "value": "draft"}, {"type": "add_tag", "value": "wismo"}]),
    dict(name="Bezorgprobleem / beschadigd / verkeerd → hoge prioriteit", priority=40,
         conditions=[{"field": "intent", "op": "in", "value": ["shipping.delivery_issue", "order.damaged", "order.wrong_item", "order.missing_item"]}],
         actions=[{"type": "set_priority", "value": "high"}, {"type": "add_tag", "value": "orderprobleem"}]),
    dict(name="Adres wijzigen / annuleren → tijdkritisch", priority=41,
         conditions=[{"field": "intent", "op": "in", "value": ["shipping.address_change", "order.cancel", "order.change"]}],
         actions=[{"type": "set_priority", "value": "high"}, {"type": "needs_human", "value": "Actie op order vereist goedkeuring"}]),
    dict(name="VIP-klant (3+ orders of €250+) → tag + hoge prioriteit", priority=50,
         conditions=[{"field": "customer_orders_count", "op": "gte", "value": 3}],
         actions=[{"type": "add_tag", "value": "vip"}, {"type": "set_priority", "value": "high"}]),
    dict(name="Spam → sluiten", priority=90,
         conditions=[{"field": "intent", "op": "is", "value": "spam"}],
         actions=[{"type": "mark_spam", "value": True}, {"type": "allow_ai", "value": "analyze"}]),
    dict(name="Bedankje / afsluiter → sluiten zonder antwoord", priority=91,
         conditions=[{"field": "intent", "op": "is", "value": "other.thanks"}],
         actions=[{"type": "close", "value": True}, {"type": "allow_ai", "value": "analyze"}]),
    dict(name="Social comment zonder vraag → lage prioriteit", priority=92,
         conditions=[{"field": "intent", "op": "is", "value": "social.comment"}],
         actions=[{"type": "set_priority", "value": "low"}, {"type": "allow_ai", "value": "analyze"}]),
]


def seed_defaults() -> None:
    if db.scalar("SELECT COUNT(*) FROM rules"):
        return
    for r in DEFAULT_RULES:
        db.insert("rules", dict(name=r["name"], priority=r["priority"], trigger="message_analyzed",
                                conditions=r["conditions"], actions=r["actions"], description=r.get("description")))


_PRIO_RANG = {"low": 0, "normal": 1, "high": 2, "critical": 3}


def max_priority(*waarden) -> str | None:
    """De hoogste van de opgegeven prioriteiten (None's genegeerd)."""
    geldig = [w for w in waarden if w in _PRIO_RANG]
    return max(geldig, key=_PRIO_RANG.get) if geldig else None


def _cmp(op: str, links, rechts) -> bool:
    if op in ("in", "not_in", "contains_any"):
        # Eén waarde uit de editor komt als string binnen; altijd als lijst behandelen.
        rechts = [rechts] if isinstance(rechts, (str, int, float, bool)) else list(rechts or [])
    if op == "is":
        return links == rechts
    if op == "is_not":
        return links != rechts
    if op == "contains":
        if isinstance(links, list):
            return rechts in links
        return str(rechts).lower() in str(links or "").lower()
    if op == "not_contains":
        return not _cmp("contains", links, rechts)
    if op == "contains_any":
        if isinstance(links, list):
            return any(x in links for x in rechts)
        return any(str(x).lower() in str(links or "").lower() for x in rechts)
    if op == "in":
        return links in (rechts or [])
    if op == "not_in":
        return links not in (rechts or [])
    if op in ("gt", "lt", "gte", "lte"):
        try:
            a, b = float(links or 0), float(rechts)
        except (TypeError, ValueError):
            return False
        return {"gt": a > b, "lt": a < b, "gte": a >= b, "lte": a <= b}[op]
    if op == "is_empty":
        return not links
    if op == "not_empty":
        return bool(links)
    if op == "matches":
        try:
            return re.search(str(rechts), str(links or ""), re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def build_context(conversation: dict, analysis: dict | None, customer: dict | None, order: dict | None,
                  body: str = "") -> dict:
    nu = dt.datetime.now()
    tr = (order or {}).get("tracking") or {}
    return {
        "intent": (analysis or {}).get("intent") or conversation.get("intent"),
        "intent_group": intent_group((analysis or {}).get("intent") or conversation.get("intent")),
        "sentiment": (analysis or {}).get("sentiment") or conversation.get("sentiment"),
        "priority": (analysis or {}).get("priority") or conversation.get("priority"),
        "channel": conversation.get("channel"),
        "via": conversation.get("via"),
        "language": (analysis or {}).get("language") or conversation.get("language"),
        "needs_human": bool((analysis or {}).get("needs_human") or conversation.get("needs_human")),
        "escalation_flags": (analysis or {}).get("escalation_flags") or [],
        "missing_info": (analysis or {}).get("missing_info") or [],
        "order_found": order is not None,
        "tracking_available": bool(tr.get("number") or tr.get("url")),
        "order_fulfillment_status": (order or {}).get("fulfillment_status"),
        "order_financial_status": (order or {}).get("financial_status"),
        "customer_orders_count": (customer or {}).get("orders_count") or 0,
        "customer_total_spent": (customer or {}).get("total_spent") or 0,
        "body": body or "",
        "subject": conversation.get("subject") or "",
        "tags": db.loads(conversation.get("tags"), []) if isinstance(conversation.get("tags"), str) else (conversation.get("tags") or []),
        "hour": nu.hour,
        "weekday": nu.weekday(),
    }


def evaluate(trigger: str, ctx: dict) -> dict:
    """Draait alle actieve rules voor de trigger. Geeft het resultaat terug:
    {set: {priority, status, intent}, needs_human: reason|None, allow_ai: laagste niveau|None,
     add_tags: [], remove_tags: [], assign_user: id|None, notes: [], snooze_hours: n|None,
     close: bool, spam: bool, fired: [rule-namen]}"""
    uit = {"set": {}, "needs_human": None, "allow_ai": None, "add_tags": [], "remove_tags": [],
           "assign_user": None, "notes": [], "snooze_hours": None, "close": False, "spam": False, "fired": []}
    regels = db.rows("SELECT * FROM rules WHERE enabled = 1 AND trigger = ? ORDER BY priority, id", (trigger,))
    from app.taxonomy import level_rank
    for r in regels:
        condities = db.loads(r["conditions"], [])
        if not all(_cmp(c.get("op", "is"), ctx.get(c.get("field")), c.get("value")) for c in condities):
            continue
        uit["fired"].append(r["name"])
        for a in db.loads(r["actions"], []):
            t, v = a.get("type"), a.get("value")
            if t == "set_priority":
                uit["set"]["priority"] = max_priority(uit["set"].get("priority"), v)  # alleen omhoog, nooit omlaag
            elif t == "set_status":
                uit["set"]["status"] = v
            elif t == "set_intent":
                uit["set"]["intent"] = v
            elif t == "needs_human":
                uit["needs_human"] = v if isinstance(v, str) else "Regel: " + r["name"]
            elif t == "allow_ai":
                if uit["allow_ai"] is None or level_rank(v) < level_rank(uit["allow_ai"]):
                    uit["allow_ai"] = v
            elif t == "add_tag":
                uit["add_tags"].append(v)
            elif t == "remove_tag":
                uit["remove_tags"].append(v)
            elif t == "assign_user":
                uit["assign_user"] = v
            elif t == "add_note":
                uit["notes"].append(v)
            elif t == "snooze_hours":
                uit["snooze_hours"] = v
            elif t == "close":
                uit["close"] = True
            elif t == "mark_spam":
                uit["spam"] = True
        db.execute("UPDATE rules SET hits = hits + 1 WHERE id = ?", (r["id"],))
        if r.get("stop"):
            break
    return uit
