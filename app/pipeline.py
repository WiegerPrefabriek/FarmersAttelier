"""De verwerkingspipeline: van binnenkomend bericht tot conceptantwoord.

    inbound (genormaliseerd door een kanaaladapter)
      → klant herkennen / aanmaken
      → gesprek vinden (thread-id of open gesprek binnen venster) / aanmaken
      → bericht opslaan (dedupe op external_id)
      → process_conversation():
          Shopify: orders van de klant + ordernummers uit de tekst
          AI-analyse → rules → automatiseringsniveau → concept → controle
          → conceptantwoord klaar (of auto-verstuurd bij niveau 3+)

Inbound-vorm (dict):
  channel: email|instagram|facebook|tiktok|shopify
  via: email|dm|comment|mention|contact_form|api
  external_message_id, external_thread_id (optioneel)
  sender: {channel, external_id, handle, name, email, avatar_url}
  text, html (optioneel), subject (optioneel), attachments [{name,url,content_type}]
  sent_at (ISO), external_ref (dict: post_id, comment_id, permalink, …)
  is_echo (bool): eigen bericht dat via het kanaal terugkomt (dan als 'out' opslaan)
"""

from __future__ import annotations

import datetime as dt
import threading
import traceback

import config
from app import db, events, rules
from app.ai import agent as ai
from app.integrations import fulfillment, shopify
from app.taxonomy import INTENTS, level_rank

_QUEUE_LOCK = threading.Lock()


# ----------------------------------------------------------------------------------
# Klant en gesprek
# ----------------------------------------------------------------------------------

def find_or_create_customer(sender: dict, channel: str) -> int:
    email = (sender.get("email") or "").strip().lower() or None
    ext = sender.get("external_id") or email
    # 1. identiteit op dit kanaal
    if ext:
        ident = db.one("SELECT customer_id FROM customer_identities WHERE channel = ? AND external_id = ?", (channel, ext))
        if ident:
            cid = ident["customer_id"]
            if email:
                k = db.one("SELECT email FROM customers WHERE id = ?", (cid,))
                if k and not k["email"]:
                    db.update("customers", cid, {"email": email})
            return cid
    # 2. e-mail bekend (kanaaloverstijgend, zoals Gorgias: e-mail eerst)
    cid = None
    if email:
        k = db.one("SELECT id FROM customers WHERE lower(email) = ?", (email,))
        if k:
            cid = k["id"]
    if cid is None:
        profiel = shopify.lookup_customer(email) if email else None
        cid = db.insert("customers", {
            "name": sender.get("name") or (profiel or {}).get("name") or sender.get("handle"),
            "email": email, "phone": (profiel or {}).get("phone"),
            "shopify_customer_id": (profiel or {}).get("shopify_customer_id"),
            "avatar_url": sender.get("avatar_url"),
            "total_spent": (profiel or {}).get("total_spent") or 0,
            "orders_count": (profiel or {}).get("orders_count") or 0,
            "tags": (profiel or {}).get("tags") or [],
        })
        events.emit("customer-created", customer_id=cid, data={"channel": channel})
    if ext:
        db.execute("INSERT OR IGNORE INTO customer_identities(customer_id, channel, external_id, handle, display_name) VALUES (?,?,?,?,?)",
                   (cid, channel, ext, sender.get("handle"), sender.get("name")))
    return cid


def find_conversation(customer_id: int, channel: str, via: str, thread_id: str | None,
                      reply_ids: list | None = None) -> dict | None:
    dagen = config.THREAD_WINDOW_DAYS.get(channel, 3)
    grens = (dt.datetime.utcnow() - dt.timedelta(days=dagen)).strftime("%Y-%m-%dT%H:%M:%S")
    if thread_id:
        if via == "dm":
            # Thread = de persoon; een DM van maanden later hoort niet bij het oude ticket.
            c = db.one("SELECT * FROM conversations WHERE channel = ? AND external_thread_id = ? "
                       "AND (status IN ('open','snoozed') OR (status = 'closed' AND closed_at > ?)) ORDER BY id DESC LIMIT 1",
                       (channel, thread_id, grens))
        else:
            c = db.one("SELECT * FROM conversations WHERE channel = ? AND external_thread_id = ? ORDER BY id DESC LIMIT 1", (channel, thread_id))
        if c:
            return c
    # E-mail: In-Reply-To/References wijzen naar een bericht (van ons of van de klant) dat we al hebben.
    for ref in reply_ids or []:
        m = db.one("SELECT conversation_id FROM messages WHERE external_id = ?", (ref,))
        if m:
            return db.one("SELECT * FROM conversations WHERE id = ?", (m["conversation_id"],))
    if thread_id and via in ("comment", "email"):
        return None  # nieuwe e-mailthread of nieuwe top-level comment = eigen ticket (Gorgias-model)
    if via == "comment":
        return None
    return db.one("SELECT * FROM conversations WHERE customer_id = ? AND channel = ? AND via = ? "
                  "AND (status IN ('open','snoozed') OR (status = 'closed' AND closed_at > ?)) "
                  "ORDER BY updated_at DESC LIMIT 1", (customer_id, channel, via, grens))


def ingest(inbound: dict, process: bool = True) -> dict:
    """Slaat een binnengekomen bericht op en start (optioneel) de verwerking.
    Geeft {conversation_id, message_id, duplicate} terug."""
    ext_id = inbound.get("external_message_id")
    if ext_id and db.one("SELECT id FROM messages WHERE external_id = ?", (ext_id,)):
        return {"duplicate": True, "conversation_id": None, "message_id": None}
    channel, via = inbound["channel"], inbound.get("via", "dm")
    sender = inbound.get("sender") or {}
    is_echo = bool(inbound.get("is_echo"))
    cid = find_or_create_customer(sender if not is_echo else inbound.get("recipient", sender), channel)
    ref = inbound.get("external_ref") or {}
    reply_ids = [x for x in ([ref.get("in_reply_to")] + (ref.get("references") or "").split()) if x]
    conv = find_conversation(cid, channel, via, inbound.get("external_thread_id"), reply_ids)
    nu = db.now()
    sent_at = inbound.get("sent_at") or nu
    nieuw = False
    if conv is None:
        nieuw = True
        conv_id = db.insert("conversations", {
            "customer_id": cid, "channel": channel, "via": via,
            "subject": inbound.get("subject") or _onderwerp_uit_tekst(inbound.get("text") or "", via),
            "status": "open", "external_thread_id": inbound.get("external_thread_id"),
            "external_ref": inbound.get("external_ref") or {},
            "last_message_at": sent_at, "last_customer_message_at": None if is_echo else sent_at,
            "ai_status": "none",
        })
        events.emit("ticket-created", conversation_id=conv_id, customer_id=cid,
                    actor_type="customer", data={"channel": channel, "via": via})
    else:
        conv_id = conv["id"]
        wijzig = {"last_message_at": sent_at}
        if not is_echo:
            wijzig["last_customer_message_at"] = sent_at
            if conv["status"] in ("closed", "snoozed", "spam"):
                wijzig["status"] = "open"
                wijzig["closed_at"] = None
                wijzig["snooze_until"] = None
                events.emit("ticket-reopened", conversation_id=conv_id, customer_id=cid, actor_type="customer")
        db.update("conversations", conv_id, wijzig)
    msg_id = db.insert("messages", {
        "conversation_id": conv_id, "direction": "out" if is_echo else "in", "kind": "public",
        "author_type": "agent" if is_echo else "customer", "author_name": sender.get("name") or sender.get("handle"),
        "body_text": (inbound.get("text") or "").strip(), "body_html": inbound.get("html"),
        "attachments": inbound.get("attachments") or [], "external_id": ext_id,
        "source": {"sender": sender, "external_ref": inbound.get("external_ref") or {}},
        "status": "received" if not is_echo else "sent", "sent_at": sent_at,
    })
    events.emit("message-created", conversation_id=conv_id, customer_id=cid,
                actor_type="agent" if is_echo else "customer", data={"message_id": msg_id, "new_ticket": nieuw})
    if process and not is_echo:
        process_conversation(conv_id, reason="new_message")
    return {"duplicate": False, "conversation_id": conv_id, "message_id": msg_id, "new": nieuw}


def _onderwerp_uit_tekst(tekst: str, via: str) -> str:
    t = " ".join(tekst.split())
    prefix = {"comment": "Comment: ", "dm": "", "mention": "Mention: "}.get(via, "")
    return (prefix + t[:70] + ("…" if len(t) > 70 else "")) or "(geen tekst)"


# ----------------------------------------------------------------------------------
# Verwerking
# ----------------------------------------------------------------------------------

def load_bundle(conv_id: int) -> dict:
    conv = db.one("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    if not conv:
        raise KeyError(conv_id)
    conv["tags"] = db.loads(conv.get("tags"), [])
    conv["external_ref"] = db.loads(conv.get("external_ref"), {})
    msgs = db.rows("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at, id", (conv_id,))
    customer = db.one("SELECT * FROM customers WHERE id = ?", (conv["customer_id"],)) if conv.get("customer_id") else None
    if customer:
        customer["tags"] = db.loads(customer.get("tags"), [])
    orders = shopify.orders_for_email((customer or {}).get("email"))
    tekst = " ".join(m["body_text"] for m in msgs if m["author_type"] == "customer")
    order = None
    refs = shopify.find_order_refs(tekst)
    if conv.get("order_name"):
        order = shopify.get_order(conv["order_name"])
    if order is None:
        for ref in refs:
            order = shopify.get_order(ref)
            if order:
                break
    if order is None and orders:
        # Zonder expliciet nummer: de meest recente order van de herkende klant
        order = orders[0]
    # Privacy: een order die via nummer is gevonden maar niet bij dit e-mailadres hoort → alleen tonen als de klant onbekend is
    if order and customer and customer.get("email") and order.get("email") and order["email"].lower() != customer["email"].lower():
        order = dict(order, _email_mismatch=True)
    ful = fulfillment.status_for_order(order) if order else None
    return {"conversation": conv, "messages": msgs, "customer": customer, "orders": orders, "order": order,
            "fulfillment": ful, "order_refs": refs}


def effective_level(intent: str | None, rule_cap: str | None) -> str:
    """Het laagste van: instelling per intent, standaard van de intent, en de rule-grens."""
    standaard = INTENTS.get(intent or "", INTENTS["other"])["default_level"]
    ingesteld = db.setting(f"level:{intent}", standaard) if intent else standaard
    niveau = ingesteld if level_rank(ingesteld) <= level_rank(standaard) or db.setting(f"level:{intent}") else standaard
    if rule_cap and level_rank(rule_cap) < level_rank(niveau):
        niveau = rule_cap
    globaal = db.setting("global_max_level", "action")
    if level_rank(globaal) < level_rank(niveau):
        niveau = globaal
    return niveau


def process_conversation(conv_id: int, reason: str = "manual", force_draft: bool = False) -> dict:
    """Voert analyse, rules en concept uit. Geeft een samenvatting terug voor de API."""
    db.update("conversations", conv_id, {"ai_status": "processing"})
    events.broadcast({"event": "ai-processing", "conversation_id": conv_id})
    try:
        return _process(conv_id, reason, force_draft)
    except Exception as fout:  # noqa: BLE001
        traceback.print_exc()
        db.update("conversations", conv_id, {"ai_status": "error"})
        events.emit("ai-error", conversation_id=conv_id, actor_type="ai", data={"error": str(fout)[:500]})
        return {"error": str(fout)}


def _process(conv_id: int, reason: str, force_draft: bool) -> dict:
    b = load_bundle(conv_id)
    conv, msgs, customer, orders, order, ful = b["conversation"], b["messages"], b["customer"], b["orders"], b["order"], b["fulfillment"]
    laatste_klant = next((m for m in reversed(msgs) if m["author_type"] == "customer"), None)
    if not laatste_klant:
        db.update("conversations", conv_id, {"ai_status": "none"})
        return {"skipped": "geen klantbericht"}
    agent = ai.get_agent()

    # 1. Analyse
    an = agent.analyze(conv, msgs, customer, orders, order, ful)
    an_id = db.insert("ai_analyses", {
        "conversation_id": conv_id, "message_id": laatste_klant["id"], "intent": an["intent"],
        "intent_confidence": an.get("intent_confidence"), "secondary_intents": an.get("secondary_intents") or [],
        "priority": an["priority"], "sentiment": an["sentiment"], "language": an.get("language"),
        "needs_human": 1 if an.get("needs_human") else 0, "needs_human_reason": an.get("needs_human_reason"),
        "escalation_flags": an.get("escalation_flags") or [], "missing_info": an.get("missing_info") or [],
        "order_ref": an.get("order_ref"), "next_action": an["next_action"], "summary": an.get("summary"),
        "reasoning": an.get("reasoning"), "model": an.get("model"), "is_mock": an.get("is_mock", 0),
        "raw": {k: v for k, v in an.items() if k != "reasoning"},
    })
    # Order alsnog koppelen als de AI een nummer zag
    if not order and an.get("order_ref"):
        order = shopify.get_order(an["order_ref"])
        ful = fulfillment.status_for_order(order) if order else None

    # 2. Rules
    ctx = rules.build_context(conv, an, customer, order, body=laatste_klant["body_text"])
    r = rules.evaluate("message_analyzed", ctx)
    if r["fired"]:
        events.emit("rule-executed", conversation_id=conv_id, actor_type="rule", data={"rules": r["fired"]})

    tags = list(conv["tags"])
    for t in r["add_tags"]:
        if t not in tags:
            tags.append(t)
    tags = [t for t in tags if t not in r["remove_tags"]]
    prio = rules.max_priority(r["set"].get("priority"), an["priority"], conv.get("priority") if conv.get("priority") != "normal" else None) or "normal"
    needs_human = bool(an.get("needs_human")) or r["needs_human"] is not None
    reden = r["needs_human"] or an.get("needs_human_reason") or None
    intent = r["set"].get("intent") or an["intent"]
    wijzig = {
        "intent": intent, "sentiment": an["sentiment"], "language": an.get("language"), "priority": prio,
        "needs_human": 1 if needs_human else 0, "needs_human_reason": reden if needs_human else None,
        "tags": tags, "summary": an.get("summary"), "ai_status": "analyzed",
    }
    if order and not conv.get("order_name") and not order.get("_email_mismatch"):
        wijzig["order_name"] = order["name"]
    if r["assign_user"]:
        wijzig["assignee_id"] = r["assign_user"]
    for n in r["notes"]:
        db.insert("messages", {"conversation_id": conv_id, "direction": "out", "kind": "note", "author_type": "rule",
                               "author_name": "Regel", "body_text": n})
    events.emit("ai-analyzed", conversation_id=conv_id, actor_type="ai",
                data={"intent": intent, "priority": prio, "sentiment": an["sentiment"], "needs_human": needs_human,
                      "next_action": an["next_action"], "mock": bool(an.get("is_mock"))})

    # 3. Sluiten/spam zonder antwoord?
    if r["spam"] or (an["next_action"] == "close" and intent == "spam"):
        wijzig.update({"status": "spam", "ai_status": "closed", "closed_at": db.now()})
        db.update("conversations", conv_id, wijzig)
        events.emit("ticket-marked-spam", conversation_id=conv_id, actor_type="ai")
        return {"analysis_id": an_id, "closed": "spam"}
    if r["close"] or (an["next_action"] == "close" and not force_draft):
        wijzig.update({"status": "closed", "ai_status": "closed", "closed_at": db.now()})
        db.update("conversations", conv_id, wijzig)
        events.emit("ticket-closed", conversation_id=conv_id, actor_type="ai", data={"reason": "geen antwoord nodig"})
        return {"analysis_id": an_id, "closed": "no_reply_needed"}

    # 4. Niveau bepalen
    niveau = effective_level(intent, r["allow_ai"])
    if needs_human and an.get("escalation_flags"):
        niveau = "analyze"
    if niveau == "analyze" and not force_draft:
        wijzig["ai_status"] = "handover" if needs_human else "analyzed"
        db.update("conversations", conv_id, wijzig)
        if needs_human:
            _handoff_note(conv_id, an, order, r)
        return {"analysis_id": an_id, "level": niveau, "draft": None}

    # 5. Concept
    db.update("conversations", conv_id, wijzig)
    d = agent.draft(conv, msgs, customer, orders, order, ful, an)
    v = agent.verify(conv, msgs, customer, order, d["body"], an)
    db.execute("UPDATE ai_drafts SET status = 'superseded' WHERE conversation_id = ? AND status = 'pending'", (conv_id,))
    draft_id = db.insert("ai_drafts", {
        "conversation_id": conv_id, "analysis_id": an_id, "body": d["body"], "kind": d.get("kind", "answer"),
        "verifier": {k: v.get(k) for k in ("ok", "issues", "contains_promise", "grounded", "policy_ok", "privacy_ok", "tone_ok", "suggested_fix")},
        "used_knowledge": d.get("used_knowledge") or [], "model": d.get("model"), "is_mock": d.get("is_mock", 0),
    })
    events.emit("ai-drafted", conversation_id=conv_id, actor_type="ai",
                data={"draft_id": draft_id, "kind": d.get("kind"), "verifier_ok": bool(v.get("ok")), "mock": bool(d.get("is_mock"))})

    # 6. Automatisch versturen? Alleen bij niveau 3+, controle ok, geen mens nodig, geen mismatch.
    mag_auto = (level_rank(niveau) >= level_rank("auto_reply") and v.get("ok") and not needs_human
                and not (order or {}).get("_email_mismatch") and db.setting("auto_send_enabled", False))
    if mag_auto:
        from app import service
        service.send_reply(conv_id, d["body"], user_id=None, draft_id=draft_id, author_type="ai")
        db.update("conversations", conv_id, {"ai_status": "auto_answered"})
        return {"analysis_id": an_id, "level": niveau, "draft_id": draft_id, "auto_sent": True}

    status = "asked_info" if d.get("kind") == "ask_info" else "drafted"
    if needs_human:
        status = "handover"
        _handoff_note(conv_id, an, order, r)
    db.update("conversations", conv_id, {"ai_status": status})
    return {"analysis_id": an_id, "level": niveau, "draft_id": draft_id, "auto_sent": False}


def _handoff_note(conv_id: int, an: dict, order: dict | None, r: dict) -> None:
    """Overdrachtsnotitie (Intercom/Zendesk-patroon): wat weet de AI, wat ontbreekt."""
    regels = [f"Overdracht aan mens — {an.get('needs_human_reason') or (r.get('needs_human') or 'regel')}",
              f"Categorie: {an.get('intent')} ({an.get('intent_confidence')}), prioriteit {an.get('priority')}, sentiment {an.get('sentiment')}"]
    if an.get("escalation_flags"):
        regels.append("Vlaggen: " + ", ".join(an["escalation_flags"]))
    if order:
        regels.append("Order: " + shopify.status_summary(order))
    if an.get("missing_info"):
        regels.append("Ontbreekt nog: " + ", ".join(an["missing_info"]))
    if r.get("fired"):
        regels.append("Regels: " + ", ".join(r["fired"]))
    db.insert("messages", {"conversation_id": conv_id, "direction": "out", "kind": "note", "author_type": "ai",
                           "author_name": "AI", "body_text": "\n".join(regels)})


# ----------------------------------------------------------------------------------
# Achtergrondverwerking van de inbound_queue (webhooks slaan eerst op, dan verwerken)
# ----------------------------------------------------------------------------------

def enqueue(source: str, payload: dict, external_id: str | None = None) -> int | None:
    try:
        return db.insert("inbound_queue", {"source": source, "external_id": external_id, "payload": payload})
    except Exception as fout:  # noqa: BLE001 — unieke index = duplicaat
        if "UNIQUE" in str(fout):
            return None
        raise


def drain_queue(handlers: dict) -> int:
    """Verwerkt wachtende rijen. handlers = {source: functie(payload) -> list[inbound]}"""
    n = 0
    with _QUEUE_LOCK:
        for rij in db.rows("SELECT * FROM inbound_queue WHERE status = 'queued' ORDER BY id LIMIT 50"):
            handler = handlers.get(rij["source"])
            try:
                if handler is None:
                    raise RuntimeError(f"geen handler voor {rij['source']}")
                for inbound in handler(db.loads(rij["payload"], {})):
                    ingest(inbound)
                db.update("inbound_queue", rij["id"], {"status": "done", "processed_at": db.now()})
                n += 1
            except Exception as fout:  # noqa: BLE001
                traceback.print_exc()
                db.update("inbound_queue", rij["id"], {"status": "failed", "error": str(fout)[:500], "processed_at": db.now()})
    return n
