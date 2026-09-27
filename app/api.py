"""JSON-API voor de inbox. Elke functie krijgt (params, body, user_id) en geeft een
dict terug (of gooit ApiError). De router in server.py koppelt paden aan deze functies.
"""

from __future__ import annotations

import os
import re

import config
from app import db, knowledge, pipeline, service, stats, voorraad as voorraad_mod
from app.ai import agent as ai
from app.integrations import fulfillment, shopify
from app.channels import email_microsoft
from app.taxonomy import CHANNELS, ESCALATION_FLAGS, GROUPS, INTENTS, LEVELS, LEVEL_ORDER, MISSING_INFO_LABELS, PRIORITIES, intent_group


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _int(v, naam="id") -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ApiError(400, f"{naam} moet een getal zijn")


# ---------------------------------------------------------------------------------
def bootstrap(params, body, user_id):
    users = db.rows("SELECT id, name, email, role FROM users ORDER BY id")
    levels = {k: db.setting(f"level:{k}", v["default_level"]) for k, v in INTENTS.items()}
    return {
        "users": users, "intents": INTENTS, "groups": GROUPS, "channels": CHANNELS, "levels": LEVELS,
        "level_order": LEVEL_ORDER, "priorities": PRIORITIES, "missing_info": MISSING_INFO_LABELS,
        "escalation_flags": ESCALATION_FLAGS, "intent_levels": levels,
        "settings": {"ai_mode": db.setting("ai_mode", "auto"), "auto_send_enabled": bool(db.setting("auto_send_enabled", False)),
                     "global_max_level": db.setting("global_max_level", "action"), "tone": db.setting("tone", "")},
        "integrations": config.integratie_status(), "agent_mode": ai.agent_mode(),
        "counts": stats.view_counts(user_id), "brand": config.BRAND,
    }


VIEW_SQL = {
    "alle": "c.status IN ('open','snoozed')",
    "nieuw": "c.status = 'open' AND c.first_response_at IS NULL",
    "mijn": "c.status = 'open' AND c.assignee_id = :user",
    "ai_bezig": "c.status = 'open' AND c.ai_status IN ('processing','drafted','asked_info')",
    "ai_opgelost": "c.ai_status IN ('auto_answered','closed') AND c.status IN ('closed','spam')",
    "mens_nodig": "c.status = 'open' AND c.needs_human = 1",
    "high": "c.status = 'open' AND c.priority IN ('high','critical')",
    "social": "c.status = 'open' AND c.channel IN ('instagram','facebook','tiktok')",
    "snoozed": "c.status = 'snoozed'",
    "afgehandeld": "c.status = 'closed'",
    "spam": "c.status = 'spam'",
}


def conversations(params, body, user_id):
    view = params.get("view", "alle")
    q = (params.get("q") or "").strip()
    limit = min(_int(params.get("limit", 100), "limit"), 300)
    where, args = [], {"user": user_id}
    if view.startswith("groep:"):
        ints = [k for k, v in INTENTS.items() if v["group"] == view.split(":", 1)[1]]
        where.append("c.status = 'open' AND c.intent IN (%s)" % ",".join(f":i{n}" for n in range(len(ints))))
        args.update({f"i{n}": v for n, v in enumerate(ints)})
    elif view.startswith("kanaal:"):
        where.append("c.status IN ('open','snoozed') AND c.channel = :kanaal")
        args["kanaal"] = view.split(":", 1)[1]
    else:
        where.append(VIEW_SQL.get(view, VIEW_SQL["alle"]))
    if q:
        woorden = re.findall(r"[\wÀ-ÿ]{2,}", q)
        fts = "c.id IN (SELECT conversation_id FROM messages WHERE id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH :fts)) OR " if woorden else ""
        where.append(f"({fts}lower(k.name) LIKE :like OR lower(k.email) LIKE :like OR c.order_name LIKE :like OR lower(c.subject) LIKE :like)")
        if woorden:
            args["fts"] = " OR ".join(f'"{w}"' for w in woorden)
        args["like"] = f"%{q.lower()}%"
    sql = f"""SELECT c.id, c.channel, c.via, c.subject, c.status, c.priority, c.intent, c.sentiment, c.ai_status, c.needs_human,
                     c.needs_human_reason, c.assignee_id, c.order_name, c.tags, c.summary, c.last_message_at, c.last_customer_message_at,
                     c.created_at, c.first_response_at, c.snooze_until,
                     k.name AS customer_name, k.email AS customer_email, k.avatar_url,
                     (SELECT body_text FROM messages m WHERE m.conversation_id = c.id AND m.kind = 'public' ORDER BY m.id DESC LIMIT 1) AS last_body,
                     (SELECT author_type FROM messages m WHERE m.conversation_id = c.id AND m.kind = 'public' ORDER BY m.id DESC LIMIT 1) AS last_author,
                     (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id AND m.kind = 'public') AS n_messages,
                     (SELECT COUNT(*) FROM pending_actions a WHERE a.conversation_id = c.id AND a.status = 'pending') AS n_actions,
                     (SELECT 1 FROM ai_drafts d WHERE d.conversation_id = c.id AND d.status = 'pending' LIMIT 1) AS has_draft
              FROM conversations c LEFT JOIN customers k ON k.id = c.customer_id
              WHERE {' AND '.join(where)}
              ORDER BY CASE c.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, c.last_message_at DESC
              LIMIT {limit}"""
    rijen = db.rows(sql, args)
    for r in rijen:
        r["tags"] = db.loads(r["tags"], [])
        r["group"] = intent_group(r["intent"])
        r["last_body"] = (r["last_body"] or "")[:140]
    return {"items": rijen, "counts": stats.view_counts(user_id), "view": view}


def conversation(params, body, user_id):
    cid = _int(params["id"])
    try:
        b = pipeline.load_bundle(cid)
    except KeyError:
        raise ApiError(404, "gesprek niet gevonden")
    conv = b["conversation"]
    analysis = db.one("SELECT * FROM ai_analyses WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (cid,))
    if analysis:
        for k in ("secondary_intents", "escalation_flags", "missing_info", "used_knowledge"):
            analysis[k] = db.loads(analysis.get(k), [])
        analysis.pop("raw", None)
    draft = db.one("SELECT * FROM ai_drafts WHERE conversation_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (cid,))
    if draft:
        draft["verifier"] = db.loads(draft.get("verifier"), {})
        draft["used_knowledge"] = db.loads(draft.get("used_knowledge"), [])
    drafts_hist = db.rows("SELECT id, status, edited, similarity, feedback, created_at, decided_at FROM ai_drafts WHERE conversation_id = ? ORDER BY id DESC LIMIT 10", (cid,))
    acties = db.rows("SELECT * FROM pending_actions WHERE conversation_id = ? ORDER BY id DESC", (cid,))
    for a in acties:
        a["params"] = db.loads(a["params"], {})
    evs = db.rows("SELECT id, type, actor_type, actor_id, data, created_at FROM events WHERE conversation_id = ? ORDER BY id DESC LIMIT 40", (cid,))
    for e in evs:
        e["data"] = db.loads(e["data"], {})
    for m in b["messages"]:
        m["attachments"] = db.loads(m.get("attachments"), [])
        m["source"] = db.loads(m.get("source"), {})
    eerdere = db.rows("SELECT id, subject, status, intent, channel, created_at FROM conversations WHERE customer_id = ? AND id != ? ORDER BY created_at DESC LIMIT 10",
                      (conv["customer_id"], cid)) if conv.get("customer_id") else []
    identiteiten = db.rows("SELECT channel, external_id, handle, display_name FROM customer_identities WHERE customer_id = ?", (conv["customer_id"],)) if conv.get("customer_id") else []
    kb_used = knowledge.search(" ".join(m["body_text"] for m in b["messages"] if m["author_type"] == "customer")[:500], limit=3)
    return {
        "conversation": conv, "messages": b["messages"], "customer": b["customer"], "identities": identiteiten,
        "orders": b["orders"], "order": b["order"], "fulfillment": b["fulfillment"], "order_refs": b["order_refs"],
        "analysis": analysis, "draft": draft, "drafts_history": drafts_hist, "actions": acties, "events": evs,
        "previous_conversations": eerdere, "knowledge_hits": [{"slug": k["slug"], "title": k["title"], "complete": bool(k["is_complete"])} for k in kb_used],
        "level": pipeline.effective_level(conv.get("intent"), None) if conv.get("intent") else None,
    }


def reply(params, body, user_id):
    cid = _int(params["id"])
    r = service.send_reply(cid, body.get("body", ""), user_id, draft_id=body.get("draft_id"), close_after=bool(body.get("close")))
    return {"ok": True, **r}


def note(params, body, user_id):
    return {"ok": True, "message_id": service.add_note(_int(params["id"]), body.get("body", ""), user_id)}


def assign(params, body, user_id):
    wie = body.get("assignee_id")
    if wie is not None and not db.one("SELECT 1 FROM users WHERE id = ?", (wie,)):
        raise ApiError(400, "onbekende medewerker")
    service.assign(_int(params["id"]), wie, user_id)
    return {"ok": True}


def status(params, body, user_id):
    service.set_status(_int(params["id"]), body.get("status", "open"), user_id, body.get("snooze_hours"))
    return {"ok": True}


def priority(params, body, user_id):
    if body.get("priority") not in PRIORITIES:
        raise ApiError(400, "ongeldige prioriteit")
    service.set_priority(_int(params["id"]), body["priority"], user_id)
    return {"ok": True}


def intent(params, body, user_id):
    if body.get("intent") not in INTENTS:
        raise ApiError(400, "onbekende categorie")
    service.set_intent(_int(params["id"]), body["intent"], user_id)
    return {"ok": True}


def escalate(params, body, user_id):
    service.escalate(_int(params["id"]), body.get("reason", ""), user_id, body.get("assignee_id"))
    return {"ok": True}


def resolve_human(params, body, user_id):
    service.resolve_human(_int(params["id"]), user_id)
    return {"ok": True}


def tag(params, body, user_id):
    return {"ok": True, "tags": service.add_tag(_int(params["id"]), body.get("tag", ""), user_id, remove=bool(body.get("remove")))}


def regenerate(params, body, user_id):
    return {"ok": True, "result": service.regenerate(_int(params["id"]))}


def propose_action(params, body, user_id):
    cid = _int(params["id"])
    t = body.get("type")
    if t not in service.ACTION_LABELS:
        raise ApiError(400, "onbekend actietype")
    p = body.get("params") or {}
    conv = db.one("SELECT order_name FROM conversations WHERE id = ?", (cid,))
    omschrijving = body.get("description") or _beschrijf_actie(t, p, conv)
    aid = service.propose_action(cid, t, p, omschrijving, proposed_by="agent")
    return {"ok": True, "action_id": aid}


def _beschrijf_actie(t: str, p: dict, conv: dict | None) -> str:
    order = shopify.get_order(p.get("order_name") or (conv or {}).get("order_name"), refresh=False)
    naam = order["name"] if order else "(order)"
    if t == "cancel_order":
        return f"Order {naam} annuleren" + (f" en €{order['total']:.2f} terugstorten?" if order and p.get("refund", True) else "?")
    if t == "refund":
        return f"€{float(p.get('amount', 0)):.2f} terugstorten op {naam}?"
    if t == "address_change":
        a = p.get("address") or {}
        return f"Adres van {naam} wijzigen naar {a.get('address1', '')}, {a.get('zip', '')} {a.get('city', '')}?"
    if t == "hide_comment":
        return "Deze comment verbergen?" if p.get("hide", True) else "Deze comment weer tonen?"
    if t == "tag_order":
        return f"Order {naam} taggen met {', '.join(p.get('tags', []))}?"
    return service.ACTION_LABELS.get(t, t)


def private_reply(params, body, user_id):
    from app.channels import dispatch
    cid = _int(params["id"])
    conv = db.one("SELECT * FROM conversations WHERE id = ?", (cid,))
    if not conv:
        raise ApiError(404, "gesprek niet gevonden")
    r = dispatch.private_reply(conv, body.get("body", ""))
    service.add_note(cid, "Privé antwoord (DM) verstuurd op deze comment:\n" + body.get("body", ""), user_id)
    return {"ok": True, **r}


def draft_feedback(params, body, user_id):
    service.draft_feedback(_int(params["id"]), body.get("feedback", "down"), body.get("reason"), user_id)
    return {"ok": True}


def draft_reject(params, body, user_id):
    service.reject_draft(_int(params["id"]), user_id)
    return {"ok": True}


def action_decide(params, body, user_id):
    return service.decide_action(_int(params["id"]), bool(body.get("approve")), user_id)


def actions_list(params, body, user_id):
    rijen = db.rows("SELECT a.*, c.subject, c.channel, k.name customer_name FROM pending_actions a JOIN conversations c ON c.id = a.conversation_id "
                    "LEFT JOIN customers k ON k.id = c.customer_id WHERE a.status = ? ORDER BY a.created_at DESC LIMIT 100", (params.get("status", "pending"),))
    for a in rijen:
        a["params"] = db.loads(a["params"], {})
    return {"items": rijen}


def dashboard(params, body, user_id):
    return stats.dashboard()


def learning(params, body, user_id):
    return stats.learning_overview()


def learning_analyze(params, body, user_id):
    rec = db.rows("SELECT * FROM learning_records ORDER BY created_at DESC LIMIT 150")
    if not rec:
        raise ApiError(400, "Nog geen leerdata: verstuur eerst wat antwoorden.")
    uit = ai.get_agent().learn(rec)
    uit["generated_at"] = db.now()
    db.set_setting("learning_analysis", uit)
    return uit


# --- rules -------------------------------------------------------------------------
def rules_list(params, body, user_id):
    rijen = db.rows("SELECT * FROM rules ORDER BY priority, id")
    for r in rijen:
        r["conditions"] = db.loads(r["conditions"], [])
        r["actions"] = db.loads(r["actions"], [])
    return {"items": rijen, "fields": ["intent", "intent_group", "sentiment", "priority", "channel", "via", "language", "needs_human",
                                       "escalation_flags", "missing_info", "order_found", "tracking_available", "order_fulfillment_status",
                                       "order_financial_status", "customer_orders_count", "customer_total_spent", "body", "subject", "tags", "hour", "weekday"],
            "ops": ["is", "is_not", "contains", "not_contains", "contains_any", "in", "not_in", "gt", "lt", "gte", "lte", "is_empty", "not_empty", "matches"],
            "action_types": ["set_priority", "set_status", "needs_human", "allow_ai", "add_tag", "remove_tag", "assign_user", "set_intent", "add_note", "snooze_hours", "close", "mark_spam"]}


def rules_save(params, body, user_id):
    waarden = {k: body.get(k) for k in ("name", "enabled", "priority", "trigger", "conditions", "actions", "stop", "description") if k in body}
    if "name" in waarden and not waarden["name"]:
        raise ApiError(400, "naam is verplicht")
    if params.get("id"):
        db.update("rules", _int(params["id"]), waarden)
        return {"ok": True, "id": _int(params["id"])}
    waarden.setdefault("name", "Nieuwe regel")
    waarden.setdefault("trigger", "message_analyzed")
    waarden.setdefault("conditions", [])
    waarden.setdefault("actions", [])
    return {"ok": True, "id": db.insert("rules", waarden)}


def rules_delete(params, body, user_id):
    db.execute("DELETE FROM rules WHERE id = ?", (_int(params["id"]),))
    return {"ok": True}


# --- kennisbank ----------------------------------------------------------------------
def knowledge_list(params, body, user_id):
    return {"items": knowledge.all_articles()}


def knowledge_save(params, body, user_id):
    slug = re.sub(r"[^a-z0-9-]", "", (params.get("slug") or "").lower())
    if not slug:
        raise ApiError(400, "ongeldige slug")
    tekst = body.get("body", "")
    pad = os.path.join(config.KB_DIR, slug + ".md")
    tmp = pad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(tekst)
    os.replace(tmp, pad)
    knowledge.sync_from_disk()
    return {"ok": True}


def knowledge_sync(params, body, user_id):
    return {"ok": True, "status": knowledge.sync_from_disk()}


# --- instellingen ---------------------------------------------------------------------
def settings_save(params, body, user_id):
    for k, v in (body.get("intent_levels") or {}).items():
        if k in INTENTS and v in LEVEL_ORDER:
            db.set_setting(f"level:{k}", v)
    for k in ("ai_mode", "global_max_level", "tone"):
        if k in body:
            db.set_setting(k, body[k])
    if "auto_send_enabled" in body:
        db.set_setting("auto_send_enabled", bool(body["auto_send_enabled"]))
    return {"ok": True}


# --- klanten / orders / zoeken ----------------------------------------------------------
def customer(params, body, user_id):
    k = db.one("SELECT * FROM customers WHERE id = ?", (_int(params["id"]),))
    if not k:
        raise ApiError(404, "klant niet gevonden")
    k["tags"] = db.loads(k["tags"], [])
    return {"customer": k, "orders": shopify.orders_for_email(k.get("email")),
            "conversations": db.rows("SELECT id, subject, status, intent, channel, created_at FROM conversations WHERE customer_id = ? ORDER BY created_at DESC", (k["id"],)),
            "identities": db.rows("SELECT channel, external_id, handle FROM customer_identities WHERE customer_id = ?", (k["id"],))}


def order(params, body, user_id):
    o = shopify.get_order(params["name"])
    if not o:
        raise ApiError(404, "order niet gevonden")
    return {"order": o, "fulfillment": fulfillment.status_for_order(o)}


def simulate(params, body, user_id):
    """Testbericht injecteren (dev-tool in de UI): doet alsof er iets binnenkomt."""
    kanaal = body.get("channel", "email")
    via = body.get("via") or ("email" if kanaal == "email" else "dm")
    naam = body.get("name") or "Testklant"
    email = body.get("email") or (f"{naam.lower().replace(' ', '.')}@voorbeeld.nl" if kanaal == "email" else None)
    handle = body.get("handle") or naam.lower().replace(" ", "_")
    inbound = {
        "channel": kanaal, "via": via, "external_message_id": None,
        "external_thread_id": body.get("thread_id") or (email if kanaal == "email" else f"sim-{handle}"),
        "sender": {"channel": kanaal, "external_id": email if kanaal == "email" else f"sim-{handle}", "name": naam, "email": email, "handle": handle},
        "subject": body.get("subject"), "text": body.get("text", ""), "attachments": body.get("attachments") or [],
        "external_ref": {"comment_id": f"sim-c-{db.now()}", "simulated": True} if via == "comment" else {"simulated": True},
    }
    return pipeline.ingest(inbound)


def integrations_status(params, body, user_id):
    return {"integrations": config.integratie_status(), "agent_mode": ai.agent_mode(),
            "shopify_domain": config.secret("shopify", "store_domain"), "db_mb": db.db_size_mb(),
            "queue": {r["status"]: r["n"] for r in db.rows("SELECT status, COUNT(*) n FROM inbound_queue GROUP BY status")},
            "knowledge": knowledge.article_status()}


def fulfillment_event(params, body, user_id):
    """Handmatig of via een eenvoudige webhook van de fulfillmentpartij."""
    fulfillment.record_event(body["order_name"], body["stage"], body.get("occurred_at") or db.now(),
                             carrier=body.get("carrier"), tracking=body.get("tracking"), detail=body.get("detail"), raw=body)
    return {"ok": True}


def voorraad(params, body, user_id):
    """Voorraad, retouren en de kosten van hergebruik, voor de Voorraad-tab."""
    return voorraad_mod.overzicht()


def voorraad_kosten(params, body, user_id):
    """Herrekent het kostenmodel met andere aannames (weken opslag, land).

    `params` is een dict van strings (de router heeft de querystring al platgeslagen),
    dus niet indexeren met [0] — dan pak je het eerste teken en wordt "52" ineens 5.
    """
    weken = _int(params.get("weken") or 12, "weken")
    land = (params.get("land") or "NL").strip().upper()
    aantal = _int(params.get("aantal") or 0, "aantal")
    return voorraad_mod.kosten_hergebruik(aantal=aantal or None, weken_opslag=weken, land=land)


def integrations_test(params, body, user_id):
    """Probeert elke koppeling echt aan te spreken en zegt wat eruit komt.

    Niet 'staat er een sleutel in het bestand' maar 'komen we binnen' — dat is
    het enige dat telt, en het scheelt zoeken als er iets net niet klopt.
    """
    uit = {}

    uit["microsoft"] = email_microsoft.test()

    try:
        c = shopify.client()
        if not c.configured:
            uit["shopify"] = {"ok": False, "reden": "niet ingesteld: winkeldomein plus client id en secret nodig"}
        else:
            d = c.graphql("{ shop { name myshopifyDomain currencyCode } }")
            winkel = (d.get("data") or {}).get("shop") or {}
            uit["shopify"] = {"ok": bool(winkel), "winkel": winkel.get("name"),
                              "domein": winkel.get("myshopifyDomain"), "valuta": winkel.get("currencyCode")}
    except Exception as e:  # noqa: BLE001
        uit["shopify"] = {"ok": False, "reden": str(e)[:400]}

    uit["anthropic"] = {"ok": bool(config.anthropic_key()),
                        "modus": ai.agent_mode()}
    return {"koppelingen": uit}
