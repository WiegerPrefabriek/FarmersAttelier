"""Acties van medewerkers (en van de AI bij auto-antwoord): versturen, notitie, toewijzen,
status, snoozen, escaleren, acties goedkeuren, feedback. Elke actie logt een event en,
bij versturen, een leerrecord.
"""

from __future__ import annotations

import datetime as dt

from app import db, events
from app.ai import agent as ai
from app.channels import dispatch
from app.integrations import shopify


def _conv(conv_id: int) -> dict:
    c = db.one("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    if not c:
        raise KeyError(f"gesprek {conv_id} bestaat niet")
    return c


def send_reply(conv_id: int, body: str, user_id: int | None, draft_id: int | None = None,
               author_type: str = "agent", close_after: bool = False) -> dict:
    conv = _conv(conv_id)
    body = (body or "").strip()
    if not body:
        raise ValueError("Leeg antwoord")
    user = db.one("SELECT name FROM users WHERE id = ?", (user_id,)) if user_id else None
    naam = user["name"] if user else ("AI" if author_type == "ai" else "Farmers Atelier")
    msg_id = db.insert("messages", {
        "conversation_id": conv_id, "direction": "out", "kind": "public", "author_type": author_type,
        "author_id": user_id, "author_name": naam, "body_text": body, "status": "pending", "draft_id": draft_id,
    })
    # Versturen via het kanaal (mock: markeert als verzonden)
    try:
        resultaat = dispatch.send(conv, body, msg_id)
        db.update("messages", msg_id, {"status": "sent", "sent_at": db.now(),
                                       "external_id": resultaat.get("external_id"), "source": resultaat})
    except Exception as fout:  # noqa: BLE001
        db.update("messages", msg_id, {"status": "failed", "error": str(fout)[:500]})
        events.emit("ticket-message-failed", conversation_id=conv_id, actor_type=author_type, actor_id=user_id,
                    data={"message_id": msg_id, "error": str(fout)[:300]})
        raise
    nu = db.now()
    wijzig = {"last_message_at": nu}
    if not conv.get("first_response_at"):
        wijzig["first_response_at"] = nu
    if close_after:
        wijzig.update({"status": "closed", "closed_at": nu})
    elif conv["status"] == "closed":
        pass
    db.update("conversations", conv_id, wijzig)
    events.emit("ticket-message-created", conversation_id=conv_id, actor_type=author_type, actor_id=user_id,
                data={"message_id": msg_id, "draft_id": draft_id})
    # Concept-status en leerrecord
    _record_learning(conv, body, draft_id, author_type, user_id)
    if close_after:
        events.emit("ticket-closed", conversation_id=conv_id, actor_type=author_type, actor_id=user_id)
    if author_type == "agent" and conv.get("ai_status") in ("drafted", "asked_info", "handover", "analyzed"):
        db.update("conversations", conv_id, {"ai_status": "answered_by_human" if not draft_id else "draft_sent"})
    return {"message_id": msg_id}


def _record_learning(conv: dict, final_body: str, draft_id: int | None, author_type: str, user_id: int | None) -> None:
    draft = db.one("SELECT * FROM ai_drafts WHERE id = ?", (draft_id,)) if draft_id else \
        db.one("SELECT * FROM ai_drafts WHERE conversation_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (conv["id"],))
    an = db.one("SELECT * FROM ai_analyses WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conv["id"],))
    vraag = db.one("SELECT body_text FROM messages WHERE conversation_id = ? AND author_type = 'customer' ORDER BY id DESC LIMIT 1", (conv["id"],))
    sim = ai.similarity(draft["body"], final_body) if draft else None
    edited = int(bool(draft) and sim is not None and sim < 0.98)
    if draft:
        db.update("ai_drafts", draft["id"], {
            "status": "auto_sent" if author_type == "ai" else ("edited_sent" if edited else "sent"),
            "sent_body": final_body, "edited": edited, "similarity": sim, "decided_by": user_id, "decided_at": db.now()})
    order = shopify.get_order(conv.get("order_name"), refresh=False) if conv.get("order_name") else None
    db.insert("learning_records", {
        "conversation_id": conv["id"], "channel": conv["channel"],
        "customer_question": (vraag or {}).get("body_text"),
        "ai_intent": (an or {}).get("intent"), "ai_priority": (an or {}).get("priority"), "ai_sentiment": (an or {}).get("sentiment"),
        "ai_draft": (draft or {}).get("body"), "final_answer": final_body, "edited": edited, "similarity": sim,
        "diff_summary": ai.diff_summary((draft or {}).get("body") or "", final_body) if draft else "geen concept",
        "sent_by": author_type, "escalated": 1 if conv.get("needs_human") else 0,
        "order_info": {"name": order["name"], "financial": order.get("financial_status"), "fulfillment": order.get("fulfillment_status")} if order else {},
        "used_knowledge": db.loads((draft or {}).get("used_knowledge"), []),
    })


def add_note(conv_id: int, body: str, user_id: int | None) -> int:
    _conv(conv_id)
    user = db.one("SELECT name FROM users WHERE id = ?", (user_id,)) if user_id else None
    msg_id = db.insert("messages", {"conversation_id": conv_id, "direction": "out", "kind": "note",
                                    "author_type": "agent", "author_id": user_id,
                                    "author_name": user["name"] if user else "Medewerker", "body_text": body.strip()})
    db.update("conversations", conv_id, {"last_message_at": db.now()})
    events.emit("note-added", conversation_id=conv_id, actor_type="agent", actor_id=user_id, data={"message_id": msg_id})
    return msg_id


def assign(conv_id: int, assignee_id: int | None, user_id: int | None) -> None:
    _conv(conv_id)
    db.update("conversations", conv_id, {"assignee_id": assignee_id})
    events.emit("ticket-assigned" if assignee_id else "ticket-unassigned", conversation_id=conv_id,
                actor_type="agent", actor_id=user_id, data={"assignee_id": assignee_id})


def set_status(conv_id: int, status: str, user_id: int | None, snooze_hours: float | None = None) -> None:
    conv = _conv(conv_id)
    if status not in ("open", "snoozed", "closed", "spam"):
        raise ValueError("ongeldige status")
    wijzig = {"status": status}
    if status == "closed":
        wijzig["closed_at"] = db.now()
        if conv.get("ai_status") in ("drafted", "asked_info", "handover", "analyzed"):
            wijzig["ai_status"] = "closed"
    elif status == "snoozed":
        uren = float(snooze_hours or 24)
        wijzig["snooze_until"] = (dt.datetime.utcnow() + dt.timedelta(hours=uren)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif status == "open":
        wijzig["closed_at"] = None
        wijzig["snooze_until"] = None
    db.update("conversations", conv_id, wijzig)
    events.emit({"closed": "ticket-closed", "open": "ticket-reopened", "snoozed": "ticket-snoozed", "spam": "ticket-marked-spam"}[status],
                conversation_id=conv_id, actor_type="agent", actor_id=user_id, data={"snooze_hours": snooze_hours})


def set_priority(conv_id: int, priority: str, user_id: int | None) -> None:
    _conv(conv_id)
    db.update("conversations", conv_id, {"priority": priority})
    events.emit("ticket-priority", conversation_id=conv_id, actor_type="agent", actor_id=user_id, data={"priority": priority})


def set_intent(conv_id: int, intent: str, user_id: int | None) -> None:
    conv = _conv(conv_id)
    db.update("conversations", conv_id, {"intent": intent})
    events.emit("ticket-intent-corrected", conversation_id=conv_id, actor_type="agent", actor_id=user_id,
                data={"from": conv.get("intent"), "to": intent})


def escalate(conv_id: int, reason: str, user_id: int | None, assignee_id: int | None = None) -> None:
    from app import rules
    conv = _conv(conv_id)
    wijzig = {"needs_human": 1, "needs_human_reason": reason or "Geëscaleerd door medewerker",
              "priority": rules.max_priority(conv.get("priority"), "high"), "ai_status": "handover"}
    if assignee_id:
        wijzig["assignee_id"] = assignee_id
    db.update("conversations", conv_id, wijzig)
    events.emit("ticket-escalated", conversation_id=conv_id, actor_type="agent", actor_id=user_id, data={"reason": reason})


def resolve_human(conv_id: int, user_id: int | None) -> None:
    db.update("conversations", conv_id, {"needs_human": 0, "needs_human_reason": None})
    events.emit("ticket-human-resolved", conversation_id=conv_id, actor_type="agent", actor_id=user_id)


def add_tag(conv_id: int, tag: str, user_id: int | None, remove: bool = False) -> list[str]:
    conv = _conv(conv_id)
    tags = db.loads(conv.get("tags"), [])
    tag = tag.strip().lower()
    if remove:
        tags = [t for t in tags if t != tag]
    elif tag and tag not in tags:
        tags.append(tag)
    db.update("conversations", conv_id, {"tags": tags})
    events.emit("tags-removed" if remove else "tags-added", conversation_id=conv_id, actor_type="agent", actor_id=user_id, data={"tag": tag})
    return tags


def draft_feedback(draft_id: int, feedback: str, reason: str | None, user_id: int | None) -> None:
    d = db.one("SELECT conversation_id FROM ai_drafts WHERE id = ?", (draft_id,))
    if not d:
        raise KeyError("concept bestaat niet")
    db.update("ai_drafts", draft_id, {"feedback": feedback, "feedback_reason": reason})
    db.execute("UPDATE learning_records SET feedback = ?, feedback_reason = ? WHERE conversation_id = ? AND id = "
               "(SELECT id FROM learning_records WHERE conversation_id = ? ORDER BY id DESC LIMIT 1)",
               (feedback, reason, d["conversation_id"], d["conversation_id"]))
    events.emit("ai-feedback", conversation_id=d["conversation_id"], actor_type="agent", actor_id=user_id,
                data={"draft_id": draft_id, "feedback": feedback, "reason": reason})


def reject_draft(draft_id: int, user_id: int | None) -> None:
    d = db.one("SELECT conversation_id FROM ai_drafts WHERE id = ?", (draft_id,))
    if d:
        db.update("ai_drafts", draft_id, {"status": "rejected", "decided_by": user_id, "decided_at": db.now()})
        events.emit("ai-draft-rejected", conversation_id=d["conversation_id"], actor_type="agent", actor_id=user_id, data={"draft_id": draft_id})


# --- acties met goedkeuring -----------------------------------------------------------

ACTION_LABELS = {
    "cancel_order": "Order annuleren", "refund": "Terugbetalen", "address_change": "Adres wijzigen",
    "hide_comment": "Comment verbergen", "tag_order": "Order taggen", "note_order": "Notitie op order",
    "create_return": "Retour aanmaken",
}


def propose_action(conv_id: int, type_: str, params: dict, description: str, proposed_by: str = "ai") -> int:
    _conv(conv_id)
    aid = db.insert("pending_actions", {"conversation_id": conv_id, "type": type_, "params": params,
                                        "description": description, "proposed_by": proposed_by})
    events.emit("action-proposed", conversation_id=conv_id, actor_type="ai" if proposed_by == "ai" else "agent",
                data={"action_id": aid, "type": type_, "description": description})
    return aid


def decide_action(action_id: int, approve: bool, user_id: int | None) -> dict:
    a = db.one("SELECT * FROM pending_actions WHERE id = ?", (action_id,))
    if not a or a["status"] != "pending":
        raise ValueError("actie bestaat niet of is al beslist")
    params = db.loads(a["params"], {})
    # Atomair claimen: twee gelijktijdige klikken mogen nooit twee refunds/annuleringen geven.
    nieuw = "approved" if approve else "rejected"
    with db.tx() as c:
        cur = c.execute("UPDATE pending_actions SET status = ?, decided_by = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
                        (nieuw, user_id, db.now(), action_id))
        if cur.rowcount == 0:
            raise ValueError("actie is intussen al door iemand anders beslist")
    if not approve:
        events.emit("action-rejected", conversation_id=a["conversation_id"], actor_type="agent", actor_id=user_id, data={"action_id": action_id})
        return {"status": "rejected"}
    events.emit("action-approved", conversation_id=a["conversation_id"], actor_type="agent", actor_id=user_id, data={"action_id": action_id})
    try:
        resultaat = _execute_action(a["type"], params, a["conversation_id"])
        db.update("pending_actions", action_id, {"status": "executed", "result": db.dumps(resultaat), "executed_at": db.now()})
        events.emit("action-executed", conversation_id=a["conversation_id"], actor_type="system", data={"action_id": action_id, "result": resultaat})
        return {"status": "executed", "result": resultaat}
    except Exception as fout:  # noqa: BLE001
        db.update("pending_actions", action_id, {"status": "failed", "result": str(fout)[:500]})
        events.emit("action-failed", conversation_id=a["conversation_id"], actor_type="system", data={"action_id": action_id, "error": str(fout)[:300]})
        return {"status": "failed", "error": str(fout)}


def _execute_action(type_: str, params: dict, conv_id: int) -> dict:
    conv = _conv(conv_id)
    if type_ in ("cancel_order", "refund", "address_change", "tag_order"):
        order = shopify.get_order(params.get("order_name") or conv.get("order_name"))
        if not order:
            raise ValueError("order niet gevonden")
        if not shopify.client().configured:
            # Mock: administratief doorvoeren in de cache zodat de flow te testen is
            if type_ == "cancel_order":
                shopify.upsert_order(dict(order, cancelled_at=db.now(), financial_status="REFUNDED" if params.get("refund", True) else order["financial_status"]))
            elif type_ == "address_change":
                shopify.upsert_order(dict(order, shipping_address=params.get("address") or order["shipping_address"]))
            elif type_ == "tag_order":
                shopify.upsert_order(dict(order, tags=sorted(set(order.get("tags", []) + params.get("tags", [])))))
            elif type_ == "refund":
                shopify.upsert_order(dict(order, refunds=order.get("refunds", []) + [{"at": db.now(), "amount": params.get("amount", 0), "note": params.get("note")}],
                                          financial_status="PARTIALLY_REFUNDED" if params.get("amount", 0) < order.get("total", 0) else "REFUNDED"))
            return {"mock": True, "note": "Shopify niet gekoppeld; alleen lokaal doorgevoerd"}
        c = shopify.client()
        if type_ == "cancel_order":
            return c.cancel_order(order["shopify_id"], refund=params.get("refund", True), restock=params.get("restock", True), note=params.get("note", ""))
        if type_ == "address_change":
            return c.update_shipping_address(order["shopify_id"], params["address"])
        if type_ == "tag_order":
            return c.add_tags(order["shopify_id"], params.get("tags", []))
        if type_ == "refund":
            # De ouder-transactie (de betaling) komt uit de order zelf; de UI hoeft die niet te kennen.
            transacties = [t for t in (order.get("raw") or {}).get("transactions") or [] if t.get("kind") in ("SALE", "CAPTURE") and t.get("status") == "SUCCESS"]
            parent = params.get("transaction_parent_id") or (transacties[-1]["id"] if transacties else None)
            gateway = params.get("gateway") or (transacties[-1]["gateway"] if transacties else "shopify_payments")
            if not parent:
                raise ValueError("geen geslaagde betaaltransactie gevonden op de order; refund handmatig in Shopify")
            return c.refund_order(order["shopify_id"], f"{float(params['amount']):.2f}", parent, gateway,
                                  params.get("line_items", []), params.get("note", ""), f"conv-{conv_id}-{params.get('key', 1)}")
    if type_ == "hide_comment":
        return dispatch.hide_comment(conv, params)
    raise ValueError(f"onbekende actie {type_}")


def regenerate(conv_id: int) -> dict:
    from app import pipeline
    return pipeline.process_conversation(conv_id, reason="regenerate", force_draft=True)


def unsnooze_due() -> int:
    """Heropent gesnoozde gesprekken waarvan de tijd om is (rule-trigger 'snooze ends')."""
    nu = db.now()
    rijen = db.rows("SELECT id FROM conversations WHERE status = 'snoozed' AND snooze_until IS NOT NULL AND snooze_until <= ?", (nu,))
    for r in rijen:
        db.update("conversations", r["id"], {"status": "open", "snooze_until": None})
        events.emit("ticket-self-unsnoozed", conversation_id=r["id"], actor_type="system")
    return len(rijen)
