"""Shopify-webhooks: orders/fulfillments/refunds/returns/customers → orders-cache en
fulfillment-events bijwerken. Webhook-payloads zijn REST-vormig (snake_case), anders dan
de GraphQL-antwoorden; daarom een eigen normalisatie.

Registreren: `scripts/shopify_webhooks_registreren.py` (of TOML in het Dev Dashboard).
Verificatie: X-Shopify-Hmac-SHA256 = base64(HMAC-SHA256(secret, raw body)).
"""

from __future__ import annotations

import base64
import hashlib
import hmac

import config
from app import db
from app.integrations import fulfillment, shopify

TOPICS = ["ORDERS_CREATE", "ORDERS_UPDATED", "ORDERS_FULFILLED", "ORDERS_CANCELLED", "ORDERS_PAID",
          "FULFILLMENTS_CREATE", "FULFILLMENTS_UPDATE", "FULFILLMENT_EVENTS_CREATE", "REFUNDS_CREATE",
          "RETURNS_REQUEST", "RETURNS_APPROVE", "RETURNS_CLOSE", "CUSTOMERS_UPDATE"]


def verify_signature(raw: bytes, header: str | None) -> bool:
    secret = config.secret("shopify", "webhook_secret") or config.secret("shopify", "client_secret")
    if not secret:
        return True
    if not header:
        return False
    digest = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(digest, header)


def normalize_rest_order(o: dict) -> dict:
    items = []
    for li in o.get("line_items") or []:
        items.append({"title": li.get("title") or li.get("name"), "sku": li.get("sku"), "quantity": li.get("quantity"),
                      "variant_title": li.get("variant_title"), "size": _optie(li, "Size", "Maat"), "color": _optie(li, "Color", "Kleur"),
                      "price": float(li.get("price") or 0), "line_item_gid": f"gid://shopify/LineItem/{li.get('id')}"})
    tracking = {}
    fuls = o.get("fulfillments") or []
    if fuls:
        f0 = fuls[-1]
        tracking = {"company": f0.get("tracking_company"), "number": f0.get("tracking_number"), "url": f0.get("tracking_url"),
                    "status": (f0.get("shipment_status") or f0.get("status") or "").upper() or None, "shipped_at": f0.get("created_at"),
                    "events": []}
    fs = (o.get("financial_status") or "").upper() or None
    ff = (o.get("fulfillment_status") or "unfulfilled").upper()
    return {
        "shopify_id": o.get("admin_graphql_api_id") or f"gid://shopify/Order/{o.get('id')}",
        "name": o.get("name"), "email": o.get("email") or o.get("contact_email"), "created_at": o.get("created_at"),
        "financial_status": fs, "fulfillment_status": ff, "return_status": None, "total": float(o.get("total_price") or 0),
        "currency": o.get("currency") or "EUR", "line_items": items, "shipping_address": o.get("shipping_address") or {},
        "tracking": tracking, "refunds": [{"id": r.get("admin_graphql_api_id"), "at": r.get("created_at"), "note": r.get("note"),
                                          "amount": sum(float(t.get("amount") or 0) for t in r.get("transactions") or [])}
                                         for r in o.get("refunds") or []],
        "cancelled_at": o.get("cancelled_at"), "note": o.get("note"),
        "tags": [t.strip() for t in (o.get("tags") or "").split(",") if t.strip()], "raw": {}, "synced_at": db.now(),
    }


def _optie(li: dict, *namen) -> str | None:
    for p in li.get("properties") or []:
        if p.get("name") in namen:
            return p.get("value")
    vt = li.get("variant_title") or ""
    for deel in vt.split(" / "):
        if deel.strip().upper() in ("XS", "S", "M", "L", "XL", "XXL") and "Size" in namen:
            return deel.strip()
    return None


def handle(topic: str, payload: dict) -> list[dict]:
    """Verwerkt een webhook; geeft [] terug (Shopify-webhooks maken geen gesprekken)."""
    topic = (topic or "").lower().replace("_", "/")
    if topic.startswith("orders/"):
        o = normalize_rest_order(payload)
        klant = db.one("SELECT id FROM customers WHERE lower(email) = lower(?)", (o.get("email") or "",)) if o.get("email") else None
        shopify.upsert_order(o, customer_id=klant["id"] if klant else None)
        if topic == "orders/fulfilled":
            fulfillment.record_event(o["name"], "shipped", db.now(), carrier=o["tracking"].get("company"),
                                     tracking=o["tracking"].get("number"), detail="Shopify: fulfilled", raw={"topic": topic})
        if topic == "orders/cancelled":
            fulfillment.record_event(o["name"], "problem", db.now(), detail="Order geannuleerd", raw={"topic": topic})
    elif topic in ("fulfillments/create", "fulfillments/update"):
        naam = (payload.get("name") or "").split(".")[0] or (f"#{payload.get('order_id')}" if payload.get("order_id") else None)  # "#1001.1" → "#1001"
        order = db.one("SELECT name FROM orders WHERE shopify_id = ?", (f"gid://shopify/Order/{payload.get('order_id')}",))
        naam = order["name"] if order else naam
        if naam:
            status = (payload.get("shipment_status") or "").upper()
            stage = fulfillment.SHOPIFY_EVENT_TO_STAGE.get(status, "shipped")
            fulfillment.record_event(naam, stage, payload.get("updated_at") or db.now(), carrier=payload.get("tracking_company"),
                                     tracking=payload.get("tracking_number"), detail=status or "fulfillment", raw={"topic": topic})
            bestaand = shopify.get_order(naam, refresh=False)
            if bestaand:
                tr = dict(bestaand.get("tracking") or {})
                tr.update({"company": payload.get("tracking_company") or tr.get("company"), "number": payload.get("tracking_number") or tr.get("number"),
                           "url": payload.get("tracking_url") or tr.get("url"), "status": status or tr.get("status")})
                shopify.upsert_order(dict(bestaand, tracking=tr, fulfillment_status="FULFILLED"))
    elif topic == "fulfillment/events/create" or topic == "fulfillment/events/create":
        pass
    elif topic == "refunds/create":
        order = db.one("SELECT name FROM orders WHERE shopify_id = ?", (f"gid://shopify/Order/{payload.get('order_id')}",))
        if order:
            bestaand = shopify.get_order(order["name"], refresh=False)
            refunds = list(bestaand.get("refunds") or []) + [{"at": payload.get("created_at"), "note": payload.get("note"),
                                                             "amount": sum(float(t.get("amount") or 0) for t in payload.get("transactions") or [])}]
            shopify.upsert_order(dict(bestaand, refunds=refunds))
    elif topic.startswith("returns/"):
        order_gid = payload.get("order_id") or (payload.get("order") or {}).get("id")
        order = db.one("SELECT name FROM orders WHERE shopify_id = ? OR shopify_id = ?", (str(order_gid), f"gid://shopify/Order/{order_gid}"))
        if order:
            status = {"returns/request": "RETURN_REQUESTED", "returns/approve": "IN_PROGRESS", "returns/close": "RETURNED"}.get(topic, "IN_PROGRESS")
            bestaand = shopify.get_order(order["name"], refresh=False)
            shopify.upsert_order(dict(bestaand, return_status=status))
            stage = "return_received" if status == "RETURNED" else "return_in_transit"
            fulfillment.record_event(order["name"], stage, db.now(), detail=f"Shopify {topic}", raw={"topic": topic})
    elif topic == "customers/update":
        email = payload.get("email")
        if email:
            k = db.one("SELECT id FROM customers WHERE lower(email) = lower(?)", (email,))
            if k:
                db.update("customers", k["id"], {"name": f"{payload.get('first_name', '')} {payload.get('last_name', '')}".strip() or None,
                                                  "phone": payload.get("phone"), "total_spent": float(payload.get("total_spent") or 0),
                                                  "orders_count": int(payload.get("orders_count") or 0),
                                                  "tags": [t.strip() for t in (payload.get("tags") or "").split(",") if t.strip()]})
    return []
