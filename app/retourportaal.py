"""Retourportaal: de pagina waar een klant zijn retour aanmeldt.

Zo werkt het, en de volgorde is bewust:

1. Een klant mailt dat hij iets wil retourneren.
2. Wij zoeken de bestelling op in Shopify en maken een uitnodiging aan. Die krijgt
   een eigen token — een lange willekeurige reeks die in de link zit.
3. Wij sturen die link naar de klant. Daarmee komt hij op zijn eigen retourpagina,
   met alleen zijn eigen bestelling erop.
4. De klant kiest wat hij terugstuurt en waarom.
5. Wij zien de aanmelding in het dashboard en handelen hem af.

**Waarom een token en geen zoekformulier.** Zou de pagina vrij toegankelijk zijn met
alleen een ordernummer, dan kan iedereen die nummers raadt — ze lopen netjes op van
14541 tot 19350 — de naam, het adres en de bestelling van een ander inzien. Met een
token werkt alleen de link die wij zelf verstuurd hebben, en alleen naar het adres
dat al bij die bestelling hoorde.

Het portaal is bewust smal: het toont alleen wat de klant zelf al weet.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from app import db

# Hoe lang een uitnodiging geldig blijft. Ruim genoeg om er een weekend over te
# doen, kort genoeg dat een oude link niet jaren blijft werken.
GELDIG_DAGEN = 30

REDENEN = {
    "te_klein": "Te klein",
    "te_groot": "Te groot",
    "niet_mooi": "Ziet er anders uit dan verwacht",
    "kwaliteit": "Kwaliteit valt tegen",
    "beschadigd": "Beschadigd aangekomen",
    "verkeerd": "Verkeerd artikel ontvangen",
    "te_laat": "Te laat bezorgd",
    "anders": "Anders",
}


def _nu() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def nodig_uit(order_naam: str, klant_email: str, klant_naam: str | None = None,
              conversation_id: int | None = None) -> dict:
    """Maakt een retourlink voor één bestelling.

    De bestelling wordt opgezocht in Shopify; bestaat hij niet, dan komt er geen
    link. Dat is meteen de zeef tegen de andere webwinkel: wie mailt over een
    bestelling die wij niet hebben, krijgt geen portaal maar het uitlegantwoord.
    """
    from app.integrations import shopify

    bestaand = db.one("SELECT * FROM retouren WHERE order_naam = ? AND status = 'uitgenodigd'",
                      (order_naam,))
    if bestaand:
        return {"ok": True, "token": bestaand["token"], "hergebruikt": True,
                "link": link_voor(bestaand["token"])}

    order = None
    schoon = order_naam.strip().lstrip("#")
    try:
        c = shopify.client()
        if c.configured:
            # Vijf resultaten ophalen en zelf exact vergelijken. Shopify's
            # name:-zoekopdracht matcht ook gedeeltelijk: zoeken op "1008" gaf
            # "FH1008Slump" terug — de bestelling van een heel andere klant.
            # Zou dat portaal verstuurd zijn, dan had die klant de naam en de
            # bestelling van een vreemde gezien.
            d = c.graphql(
                '{ orders(first:5, query:"name:%s"){ edges{ node{ id name email createdAt '
                'displayFulfillmentStatus customer{ displayName email } '
                'lineItems(first:30){ edges{ node{ id title quantity variantTitle '
                'originalUnitPriceSet{ shopMoney{ amount } } } } } } } } }' % schoon)
            for e in d.get("orders", {}).get("edges") or []:
                gevonden = (e["node"].get("name") or "").strip().lstrip("#")
                if gevonden.lower() == schoon.lower():
                    order = e["node"]
                    break
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reden": f"Shopify niet bereikbaar: {str(e)[:150]}"}

    if not order:
        return {"ok": False, "reden": f"Bestelling {order_naam} bestaat niet in Shopify. "
                                      "Waarschijnlijk komt deze van de andere webwinkel."}

    regels = []
    for e in order["lineItems"]["edges"]:
        n = e["node"]
        regels.append({
            "id": n["id"], "titel": n["title"], "maat": n.get("variantTitle") or "",
            "aantal": n["quantity"],
            "prijs": (n.get("originalUnitPriceSet") or {}).get("shopMoney", {}).get("amount"),
            "retour_aantal": 0, "reden": None,
        })

    token = secrets.token_urlsafe(24)
    rid = db.insert("retouren", {
        "token": token, "order_naam": order["name"], "order_gid": order["id"],
        "klant_email": (klant_email or order.get("email") or "").lower(),
        "klant_naam": klant_naam or (order.get("customer") or {}).get("displayName"),
        "status": "uitgenodigd", "regels": db.dumps(regels),
        "conversation_id": conversation_id,
    })
    return {"ok": True, "id": rid, "token": token, "link": link_voor(token),
            "order": order["name"], "regels": len(regels)}


def link_voor(token: str) -> str:
    basis = db.setting("portaal_url") or f"http://localhost:{__import__('config').POORT}"
    return f"{basis}/retour/{token}"


def haal_op(token: str) -> dict | None:
    """Wat de klant te zien krijgt. Geeft None bij een onbekende of verlopen link."""
    r = db.one("SELECT * FROM retouren WHERE token = ?", (token,))
    if not r:
        return None
    gemaakt = r.get("created_at") or ""
    try:
        d = datetime.strptime(gemaakt[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - d > timedelta(days=GELDIG_DAGEN):
            return {"verlopen": True, "order_naam": r["order_naam"]}
    except ValueError:
        pass
    r["regels"] = db.loads(r["regels"], [])
    # Het e-mailadres niet volledig teruggeven: de klant weet het al, en zo staat
    # er geen adres in beeld als iemand over de schouder meekijkt.
    adres = r.get("klant_email") or ""
    r["email_gemaskeerd"] = (adres[:2] + "•••" + adres[adres.find("@"):]) if "@" in adres else ""
    r.pop("klant_email", None)
    r.pop("order_gid", None)
    return r


def meld_aan(token: str, keuzes: list[dict], reden: str | None = None,
             toelichting: str | None = None) -> dict:
    """De klant bevestigt zijn retour."""
    r = db.one("SELECT * FROM retouren WHERE token = ?", (token,))
    if not r:
        return {"ok": False, "reden": "Deze link werkt niet meer."}
    if r["status"] != "uitgenodigd":
        return {"ok": False, "reden": "Deze retour is al aangemeld."}

    regels = db.loads(r["regels"], [])
    per_id = {x["id"]: x for x in regels}
    totaal = 0
    for k in keuzes:
        regel = per_id.get(k.get("id"))
        if not regel:
            continue
        aantal = max(0, min(int(k.get("aantal") or 0), regel["aantal"]))
        regel["retour_aantal"] = aantal
        regel["reden"] = k.get("reden") if aantal else None
        totaal += aantal
    if totaal == 0:
        return {"ok": False, "reden": "Er is niets aangevinkt om terug te sturen."}

    db.update("retouren", r["id"], {
        "regels": db.dumps(regels), "status": "aangemeld", "reden": reden,
        "toelichting": (toelichting or "")[:2000], "aangemeld_op": _nu(),
    })
    return {"ok": True, "aantal": totaal, "order": r["order_naam"]}


def markeer(retour_id: int, status: str) -> dict:
    """Wij zetten de retour verder: ontvangen, afgehandeld of afgewezen."""
    if status not in ("ontvangen", "afgehandeld", "afgewezen"):
        return {"ok": False, "reden": f"onbekende status {status}"}
    veld = {"ontvangen": "ontvangen_op", "afgehandeld": "afgehandeld_op",
            "afgewezen": "afgehandeld_op"}[status]
    db.update("retouren", retour_id, {"status": status, veld: _nu()})
    return {"ok": True, "status": status}


def overzicht() -> dict:
    rijen = db.rows("SELECT * FROM retouren ORDER BY id DESC")
    for r in rijen:
        r["regels"] = db.loads(r["regels"], [])
        r["stuks"] = sum(x.get("retour_aantal") or 0 for x in r["regels"])
    per_status = {}
    for r in rijen:
        per_status[r["status"]] = per_status.get(r["status"], 0) + 1
    return {"retouren": rijen, "per_status": per_status,
            "stuks_totaal": sum(r["stuks"] for r in rijen),
            "redenen": REDENEN}
