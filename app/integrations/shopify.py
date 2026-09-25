"""Shopify-koppeling: GraphQL Admin API 2026-07 + lokale cache in de tabel `orders`.

Twee lagen:
1. `ShopifyClient` praat met de echte API (custom app via client credentials, of een
   legacy `shpat_`-token). Alleen actief als `.secrets.json` de gegevens bevat.
2. De functies onderaan (`lookup_customer`, `orders_for_email`, `get_order`) zijn wat de
   rest van de app gebruikt. Ze lezen uit de cache en verversen via de API als die is
   geconfigureerd. Zonder API werkt alles op de mock-data in dezelfde tabellen.

Acties (annuleren, refund, adres) zijn hier ook, maar worden alleen aangeroepen vanuit
`pending_actions` na goedkeuring door een mens.
"""

from __future__ import annotations

import re
import threading
import time

import config
from app import db

try:
    import requests
except ImportError:  # requests staat in requirements; zonder is alleen mock mogelijk
    requests = None


class ShopifyError(RuntimeError):
    pass


class NotConfigured(ShopifyError):
    pass


ORDER_FIELDS = """
  id name createdAt cancelledAt cancelReason closedAt email phone
  displayFinancialStatus displayFulfillmentStatus returnStatus note tags
  customer { id displayName defaultEmailAddress { emailAddress } }
  totalPriceSet { shopMoney { amount currencyCode } }
  shippingAddress { name address1 address2 zip city countryCodeV2 phone }
  lineItems(first: 50) { nodes {
    id title sku quantity currentQuantity refundableQuantity
    originalUnitPriceSet { shopMoney { amount } }
    variant { id title sku inventoryQuantity selectedOptions { name value } }
  } }
  fulfillments(first: 10) {
    id status displayStatus estimatedDeliveryAt inTransitAt deliveredAt createdAt
    trackingInfo { company number url }
    events(first: 20) { nodes { status happenedAt } }
  }
  refunds { id createdAt note totalRefundedSet { shopMoney { amount } } }
  transactions(first: 10) { id kind status gateway amountSet { shopMoney { amount } } }
  returns(first: 10) { nodes { id name status
    returnLineItems(first: 20) { nodes { ... on ReturnLineItem { quantity returnReason returnReasonNote } } } } }
  events(first: 30) { nodes { id createdAt message } }
"""

Q_ORDERS = "query Orders($q: String!, $n: Int!) { orders(first: $n, query: $q, sortKey: CREATED_AT, reverse: true) { nodes { %s } } }" % ORDER_FIELDS
Q_CUSTOMERS = """
query FindCustomer($q: String!) {
  customers(first: 3, query: $q) { nodes {
    id displayName firstName lastName
    defaultEmailAddress { emailAddress } defaultPhoneNumber { phoneNumber }
    amountSpent { amount currencyCode } numberOfOrders tags note createdAt
    defaultAddress { address1 zip city countryCodeV2 }
  } }
}"""
Q_PRODUCTS = """
query Products($n: Int!, $after: String) {
  products(first: $n, after: $after, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    nodes { id title handle productType descriptionHtml status
      variants(first: 50) { nodes { id title sku price inventoryQuantity selectedOptions { name value } } } }
  }
}"""


class ShopifyClient:
    def __init__(self):
        self.domain = config.secret("shopify", "store_domain")
        self.version = config.secret("shopify", "api_version", default="2026-07")
        self.client_id = config.secret("shopify", "client_id")
        self.client_secret = config.secret("shopify", "client_secret")
        self.admin_token = config.secret("shopify", "admin_token")
        self._token = None
        self._token_expires = 0.0
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.domain and (self.admin_token or (self.client_id and self.client_secret)) and requests)

    # --- auth -------------------------------------------------------------
    def token(self) -> str:
        if self.admin_token:
            return self.admin_token
        with self._lock:
            if self._token and time.time() < self._token_expires - 300:
                return self._token
            r = requests.post(f"https://{self.domain}/admin/oauth/access_token",
                              json={"grant_type": "client_credentials", "client_id": self.client_id,
                                    "client_secret": self.client_secret}, timeout=20)
            if r.status_code != 200:
                raise ShopifyError(f"Token ophalen mislukt ({r.status_code}): {r.text[:200]}")
            data = r.json()
            self._token = data["access_token"]
            self._token_expires = time.time() + int(data.get("expires_in", 86000))
            return self._token

    # --- graphql ------------------------------------------------------------
    def graphql(self, query: str, variables: dict | None = None) -> dict:
        if not self.configured:
            raise NotConfigured("Shopify is niet geconfigureerd (zie OPENSTAANDE_ZAKEN.md §2).")
        url = f"https://{self.domain}/admin/api/{self.version}/graphql.json"
        for poging in range(4):
            r = requests.post(url, json={"query": query, "variables": variables or {}},
                              headers={"X-Shopify-Access-Token": self.token(),
                                       "Content-Type": "application/json"}, timeout=30)
            if r.status_code == 429:
                time.sleep(1.5 * (poging + 1))
                continue
            if r.status_code != 200:
                raise ShopifyError(f"Shopify {r.status_code}: {r.text[:300]}")
            body = r.json()
            fouten = body.get("errors") or []
            if any((f.get("extensions") or {}).get("code") == "THROTTLED" for f in fouten):
                time.sleep(1.5 * (poging + 1))
                continue
            if fouten:
                raise ShopifyError("; ".join(f.get("message", "?") for f in fouten))
            return body.get("data") or {}
        raise ShopifyError("Shopify blijft throttlen; later opnieuw proberen.")

    # --- lezen ---------------------------------------------------------------
    def fetch_orders(self, query: str, n: int = 10) -> list[dict]:
        data = self.graphql(Q_ORDERS, {"q": query, "n": n})
        return [normalize_order(node) for node in (data.get("orders") or {}).get("nodes", [])]

    def fetch_customer(self, query: str) -> dict | None:
        data = self.graphql(Q_CUSTOMERS, {"q": query})
        nodes = (data.get("customers") or {}).get("nodes", [])
        return normalize_customer(nodes[0]) if nodes else None

    def fetch_products(self) -> list[dict]:
        uit, after = [], None
        while True:
            data = self.graphql(Q_PRODUCTS, {"n": 50, "after": after})
            blok = data.get("products") or {}
            for node in blok.get("nodes", []):
                uit.append(normalize_product(node))
            if not blok.get("pageInfo", {}).get("hasNextPage"):
                break
            after = blok["pageInfo"]["endCursor"]
        return uit

    # --- acties (alleen na goedkeuring) ---------------------------------------
    def cancel_order(self, order_gid: str, refund: bool = True, restock: bool = True,
                     reason: str = "CUSTOMER", note: str = "") -> dict:
        m = """mutation Cancel($id: ID!, $refund: Boolean!, $restock: Boolean!, $reason: OrderCancelReason!, $note: String) {
          orderCancel(orderId: $id, refund: $refund, restock: $restock, reason: $reason, notifyCustomer: true, staffNote: $note) {
            job { id done } orderCancelUserErrors { field message } } }"""
        data = self.graphql(m, {"id": order_gid, "refund": refund, "restock": restock, "reason": reason, "note": note[:255]})
        res = data.get("orderCancel") or {}
        if res.get("orderCancelUserErrors"):
            raise ShopifyError("; ".join(e["message"] for e in res["orderCancelUserErrors"]))
        return res

    def update_shipping_address(self, order_gid: str, address: dict) -> dict:
        m = """mutation FixAddress($input: OrderInput!) {
          orderUpdate(input: $input) { order { id shippingAddress { address1 zip city } } userErrors { field message } } }"""
        data = self.graphql(m, {"input": {"id": order_gid, "shippingAddress": address}})
        res = data.get("orderUpdate") or {}
        if res.get("userErrors"):
            raise ShopifyError("; ".join(e["message"] for e in res["userErrors"]))
        return res

    def add_tags(self, gid: str, tags: list[str]) -> dict:
        m = "mutation Tag($id: ID!, $tags: [String!]!) { tagsAdd(id: $id, tags: $tags) { userErrors { field message } } }"
        return self.graphql(m, {"id": gid, "tags": tags})

    def refund_order(self, order_gid: str, amount: str, transaction_parent_id: str, gateway: str,
                     line_items: list[dict], note: str, idem_key: str) -> dict:
        m = """mutation Refund($input: RefundInput!) {
          refundCreate(input: $input) @idempotent(key: "%s") {
            refund { id totalRefundedSet { shopMoney { amount currencyCode } } } userErrors { field message } } }""" % idem_key
        inp = {"orderId": order_gid, "notify": True, "note": note, "refundLineItems": line_items,
               "transactions": [{"parentId": transaction_parent_id, "amount": amount, "kind": "REFUND", "gateway": gateway}]}
        data = self.graphql(m, {"input": inp})
        res = data.get("refundCreate") or {}
        if res.get("userErrors"):
            raise ShopifyError("; ".join(e["message"] for e in res["userErrors"]))
        return res

    def create_webhook(self, topic: str, uri: str) -> dict:
        m = """mutation Sub($topic: WebhookSubscriptionTopic!, $sub: WebhookSubscriptionInput!) {
          webhookSubscriptionCreate(topic: $topic, webhookSubscription: $sub) {
            webhookSubscription { id topic } userErrors { field message } } }"""
        return self.graphql(m, {"topic": topic, "sub": {"uri": uri, "format": "JSON"}})


# --- normalisatie naar onze tabellen --------------------------------------------

def _opt(variant: dict | None, naam: str) -> str | None:
    for o in (variant or {}).get("selectedOptions") or []:
        if o.get("name", "").lower() in (naam, naam.lower()):
            return o.get("value")
    return None


def normalize_order(node: dict) -> dict:
    ful = node.get("fulfillments") or []
    tracking = {}
    if ful:
        f0 = ful[-1]
        ti = (f0.get("trackingInfo") or [{}])[0] if f0.get("trackingInfo") else {}
        evs = [{"status": e.get("status"), "at": e.get("happenedAt")} for e in (f0.get("events") or {}).get("nodes", [])]
        tracking = {"company": ti.get("company"), "number": ti.get("number"), "url": ti.get("url"),
                    "status": (evs[-1]["status"] if evs else f0.get("displayStatus")),
                    "estimated_delivery": f0.get("estimatedDeliveryAt"), "delivered_at": f0.get("deliveredAt"),
                    "shipped_at": f0.get("createdAt"), "events": evs}
    items = []
    for li in (node.get("lineItems") or {}).get("nodes", []):
        v = li.get("variant") or {}
        items.append({"title": li.get("title"), "sku": li.get("sku") or v.get("sku"),
                      "quantity": li.get("quantity"), "variant_title": v.get("title"),
                      "size": _opt(v, "Size") or _opt(v, "Maat"), "color": _opt(v, "Color") or _opt(v, "Kleur"),
                      "price": float(((li.get("originalUnitPriceSet") or {}).get("shopMoney") or {}).get("amount") or 0),
                      "inventory": v.get("inventoryQuantity"), "line_item_gid": li.get("id"), "variant_gid": v.get("id")})
    total = float(((node.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount") or 0)
    currency = ((node.get("totalPriceSet") or {}).get("shopMoney") or {}).get("currencyCode") or "EUR"
    email = node.get("email") or ((node.get("customer") or {}).get("defaultEmailAddress") or {}).get("emailAddress")
    return {
        "shopify_id": node.get("id"), "name": node.get("name"), "email": email,
        "created_at": node.get("createdAt"), "financial_status": node.get("displayFinancialStatus"),
        "fulfillment_status": node.get("displayFulfillmentStatus"), "return_status": node.get("returnStatus"),
        "total": total, "currency": currency, "line_items": items,
        "shipping_address": node.get("shippingAddress") or {}, "tracking": tracking,
        "refunds": [{"id": r.get("id"), "at": r.get("createdAt"), "note": r.get("note"),
                     "amount": float(((r.get("totalRefundedSet") or {}).get("shopMoney") or {}).get("amount") or 0)}
                    for r in node.get("refunds") or []],
        "returns": [{"id": r.get("id"), "name": r.get("name"), "status": r.get("status"),
                     "items": [{"quantity": x.get("quantity"), "reason": x.get("returnReason"), "note": x.get("returnReasonNote")}
                               for x in (r.get("returnLineItems") or {}).get("nodes", [])]}
                    for r in (node.get("returns") or {}).get("nodes", [])],
        "cancelled_at": node.get("cancelledAt"), "note": node.get("note"), "tags": node.get("tags") or [],
        "raw": {"events": [(e.get("createdAt"), e.get("message")) for e in (node.get("events") or {}).get("nodes", [])],
                "transactions": [{"id": t.get("id"), "kind": t.get("kind"), "status": t.get("status"), "gateway": t.get("gateway"),
                                  "amount": float(((t.get("amountSet") or {}).get("shopMoney") or {}).get("amount") or 0)}
                                 for t in node.get("transactions") or []]},
        "synced_at": db.now(),
    }


def normalize_customer(node: dict) -> dict:
    return {
        "shopify_customer_id": node.get("id"), "name": node.get("displayName"),
        "email": ((node.get("defaultEmailAddress") or {}).get("emailAddress")),
        "phone": ((node.get("defaultPhoneNumber") or {}).get("phoneNumber")),
        "total_spent": float(((node.get("amountSpent") or {}).get("amount")) or 0),
        "orders_count": int(node.get("numberOfOrders") or 0), "tags": node.get("tags") or [],
        "note": node.get("note"),
    }


def normalize_product(node: dict) -> dict:
    variants = []
    for v in (node.get("variants") or {}).get("nodes", []):
        variants.append({"sku": v.get("sku"), "title": v.get("title"), "price": float(v.get("price") or 0),
                         "inventory": v.get("inventoryQuantity"), "size": _opt(v, "Size") or _opt(v, "Maat"),
                         "color": _opt(v, "Color") or _opt(v, "Kleur"), "gid": v.get("id")})
    return {"shopify_id": node.get("id"), "title": node.get("title"), "handle": node.get("handle"),
            "product_type": node.get("productType"), "description": re.sub(r"<[^>]+>", " ", node.get("descriptionHtml") or "")[:2000],
            "price": min([v["price"] for v in variants] or [0]), "variants": variants, "status": "active", "synced_at": db.now()}


# --- cache-laag: dit gebruikt de rest van de app -------------------------------------

_CLIENT: ShopifyClient | None = None


def client() -> ShopifyClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = ShopifyClient()
    return _CLIENT


def upsert_order(o: dict, customer_id: int | None = None) -> int:
    bestaand = db.one("SELECT id FROM orders WHERE name = ?", (o["name"],))
    waarden = dict(o)
    if customer_id:
        waarden["customer_id"] = customer_id
    if bestaand:
        db.update("orders", bestaand["id"], waarden)
        return bestaand["id"]
    return db.insert("orders", waarden)


def _stale(synced_at: str | None, minutes: int = 10) -> bool:
    ts = db.parse_ts(synced_at)
    if ts is None:
        return True
    import datetime as dt
    return (dt.datetime.utcnow() - ts).total_seconds() > minutes * 60


def orders_for_email(email: str | None, refresh: bool = True) -> list[dict]:
    if not email:
        return []
    cached = db.rows("SELECT * FROM orders WHERE lower(email) = lower(?) ORDER BY created_at DESC LIMIT 20", (email,))
    if refresh and client().configured and (not cached or _stale(cached[0].get("synced_at"))):
        try:
            for o in client().fetch_orders(f"email:{email}", n=10):
                upsert_order(o)
            cached = db.rows("SELECT * FROM orders WHERE lower(email) = lower(?) ORDER BY created_at DESC LIMIT 20", (email,))
        except ShopifyError as fout:
            print(f"   ! Shopify orders voor {email}: {fout}", flush=True)
    return [_hydrate(o) for o in cached]


def get_order(name: str | None, refresh: bool = True) -> dict | None:
    if not name:
        return None
    name = str(name).strip()
    name = name if name.startswith("#") else f"#{name}"
    cached = db.one("SELECT * FROM orders WHERE name = ?", (name,))
    if refresh and client().configured and (not cached or _stale(cached.get("synced_at"))):
        try:
            gevonden = client().fetch_orders(f"name:{name}", n=1)
            if gevonden:
                upsert_order(gevonden[0])
                cached = db.one("SELECT * FROM orders WHERE name = ?", (name,))
        except ShopifyError as fout:
            print(f"   ! Shopify order {name}: {fout}", flush=True)
    return _hydrate(cached) if cached else None


def lookup_customer(email: str | None) -> dict | None:
    """Shopify-klantprofiel (naam, besteding, aantal orders) op e-mail."""
    if not email or not client().configured:
        return None
    try:
        return client().fetch_customer(f"email:{email}")
    except ShopifyError as fout:
        print(f"   ! Shopify klant {email}: {fout}", flush=True)
        return None


def _hydrate(o: dict) -> dict:
    o = dict(o)
    for k in ("line_items", "shipping_address", "tracking", "refunds", "returns", "tags", "raw", "fulfillment"):
        o[k] = db.loads(o.get(k), [] if k in ("line_items", "refunds", "returns", "tags") else {})
    return o


ORDER_REF_RE = re.compile(r"(?:#|order\s*(?:nummer|number|nr\.?|no\.?)?\s*[:#]?\s*)(\d{3,6})\b", re.IGNORECASE)


def find_order_refs(tekst: str) -> list[str]:
    """Haalt ordernummers uit vrije tekst: '#1843', 'order 1843', 'ordernummer: 1843'."""
    uit = []
    for m in ORDER_REF_RE.finditer(tekst or ""):
        ref = "#" + m.group(1)
        if ref not in uit:
            uit.append(ref)
    return uit


def status_summary(o: dict) -> str:
    """Eén leesbare regel voor de AI en de zijbalk."""
    tr = o.get("tracking") or {}
    delen = [f"{o['name']}: {o.get('financial_status') or '?'}, {o.get('fulfillment_status') or '?'}"]
    if tr.get("status"):
        delen.append(f"vervoerder {tr.get('company') or '?'} status {tr['status']}")
    if tr.get("number"):
        delen.append(f"tracking {tr['number']}")
    if o.get("return_status") and o["return_status"] not in ("NO_RETURN", None):
        delen.append(f"retour {o['return_status']}")
    if o.get("refunds"):
        delen.append(f"refund {sum(r.get('amount', 0) for r in o['refunds']):.2f}")
    if o.get("cancelled_at"):
        delen.append("geannuleerd")
    return "; ".join(delen)
