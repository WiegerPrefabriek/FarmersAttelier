"""Fulfillment-adapter: status van de externe fulfillmentpartij per order.

De partij en haar API zijn nog onbekend (OPENSTAANDE_ZAKEN.md §6). Daarom:
- één vaste statusreeks (STAGES) die de AI en de UI gebruiken;
- events komen binnen via `record_event()` (later: webhook of polling van de partij);
- `status_for_order()` combineert die events met de Shopify-tracking, zodat er altijd
  een antwoord is, ook zonder koppeling.
Een echte koppeling = een klasse met `poll()` die `record_event()` aanroept.
"""

from __future__ import annotations

import config
from app import db

STAGES = [
    ("received", "Order ontvangen"),
    ("picking", "Picking"),
    ("packed", "Ingepakt"),
    ("shipped", "Verzonden"),
    ("in_transit", "Onderweg"),
    ("out_for_delivery", "Wordt vandaag bezorgd"),
    ("delivered", "Bezorgd"),
    ("problem", "Probleem"),
    ("return_in_transit", "Retour onderweg"),
    ("return_received", "Retour ontvangen"),
]
STAGE_LABEL = dict(STAGES)

# Vertaling van Shopify-fulfillment-eventstatussen naar onze reeks.
SHOPIFY_EVENT_TO_STAGE = {
    "LABEL_PRINTED": "packed", "LABEL_PURCHASED": "packed", "CONFIRMED": "shipped",
    "CARRIER_PICKED_UP": "in_transit", "IN_TRANSIT": "in_transit", "OUT_FOR_DELIVERY": "out_for_delivery",
    "DELIVERED": "delivered", "ATTEMPTED_DELIVERY": "problem", "FAILURE": "problem", "DELAYED": "problem",
    "READY_FOR_PICKUP": "out_for_delivery",
}


def configured() -> bool:
    return bool(config.secret("fulfillment", "api_key"))


def record_event(order_name: str, stage: str, occurred_at: str, carrier: str | None = None,
                 tracking: str | None = None, detail: str | None = None, raw: dict | None = None) -> int:
    if stage not in STAGE_LABEL:
        raise ValueError(f"Onbekende fulfillment-stage: {stage}")
    return db.insert("fulfillment_events", dict(order_name=order_name, stage=stage, occurred_at=occurred_at,
                                                carrier=carrier, tracking=tracking, detail=detail, raw=raw or {}))


def events_for_order(order_name: str) -> list[dict]:
    return db.rows("SELECT stage, carrier, tracking, detail, occurred_at FROM fulfillment_events "
                   "WHERE order_name = ? ORDER BY occurred_at", (order_name,))


def status_for_order(order: dict) -> dict:
    """{stage, label, carrier, tracking, updated_at, events[], source}"""
    evs = events_for_order(order["name"])
    if evs:
        laatste = evs[-1]
        return {"stage": laatste["stage"], "label": STAGE_LABEL[laatste["stage"]], "carrier": laatste["carrier"],
                "tracking": laatste["tracking"], "updated_at": laatste["occurred_at"],
                "events": [dict(e, label=STAGE_LABEL.get(e["stage"], e["stage"])) for e in evs], "source": "fulfillment"}
    # Afleiden uit Shopify
    tr = order.get("tracking") or {}
    stage = "received"
    if order.get("cancelled_at"):
        stage = "problem"
    elif tr.get("status") in SHOPIFY_EVENT_TO_STAGE:
        stage = SHOPIFY_EVENT_TO_STAGE[tr["status"]]
    elif (order.get("fulfillment_status") or "").upper() == "FULFILLED":
        stage = "shipped"
    elif (order.get("fulfillment_status") or "").upper() in ("IN_PROGRESS", "PARTIALLY_FULFILLED"):
        stage = "picking"
    if (order.get("return_status") or "") == "RETURNED":
        stage = "return_received"
    elif (order.get("return_status") or "") in ("IN_PROGRESS", "RETURN_REQUESTED"):
        stage = "return_in_transit"
    events = [{"stage": SHOPIFY_EVENT_TO_STAGE.get(e.get("status"), "in_transit"),
               "label": STAGE_LABEL.get(SHOPIFY_EVENT_TO_STAGE.get(e.get("status"), "in_transit")),
               "occurred_at": e.get("at"), "detail": e.get("status")} for e in tr.get("events") or []]
    return {"stage": stage, "label": STAGE_LABEL[stage], "carrier": tr.get("company"), "tracking": tr.get("number"),
            "updated_at": (events[-1]["occurred_at"] if events else tr.get("shipped_at")) or order.get("synced_at"),
            "events": events, "source": "shopify"}
