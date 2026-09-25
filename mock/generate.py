#!/usr/bin/env python3
"""Mock-data: 20 klanten, 30 orders, 50 gesprekken over alle kanalen, met AI-analyses,
concepten, verstuurde antwoorden en leerdata — zodat de hele app lokaal te testen is.

    ./.venv/bin/python mock/generate.py          (vult een lege database; --reset wist eerst)

Alle namen, adressen en berichten zijn verzonnen.
"""

from __future__ import annotations

import datetime as dt
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from app import db, knowledge, pipeline, rules, service  # noqa: E402
from app.integrations import fulfillment, shopify  # noqa: E402

R = random.Random(42)
NU = dt.datetime.utcnow()


def ts(dagen_terug: float, uur: int | None = None, minuut: int | None = None) -> str:
    t = NU - dt.timedelta(days=dagen_terug)
    if uur is not None:
        t = t.replace(hour=uur, minute=minuut if minuut is not None else R.randint(0, 59), second=R.randint(0, 59))
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def klok(waarde: str | None):
    db._FAKE_NOW = waarde


PRODUCTEN = [
    ("Essential Tee", "shirt", 34.95, ["Wit", "Zwart", "Olijf", "Zand"]),
    ("Heavyweight Tee", "shirt", 39.95, ["Wit", "Zwart", "Bordeaux"]),
    ("Farmers Logo Tee", "shirt", 36.95, ["Zwart", "Ecru"]),
    ("Atelier Crewneck", "trui", 79.95, ["Zwart", "Grijs melange", "Olijf"]),
    ("Heavy Hoodie", "trui", 89.95, ["Zwart", "Zand"]),
    ("Barn Zip Sweater", "trui", 94.95, ["Navy", "Bruin"]),
]
MATEN = ["S", "M", "L", "XL"]

KLANTEN = [
    ("Sophie Jansen", "sophie.jansen@voorbeeld.nl", "sophiej_", "06-12345678"),
    ("Daan de Vries", "daan.devries@voorbeeld.nl", "daandv", None),
    ("Emma Bakker", "emma.bakker@voorbeeld.nl", "emmabakker", None),
    ("Lucas Visser", "lucas.visser@voorbeeld.nl", None, "06-23456789"),
    ("Julia Smit", "julia.smit@voorbeeld.nl", "juliasmit", None),
    ("Milan Meijer", "milan.meijer@voorbeeld.nl", "milanm", None),
    ("Tess de Boer", "tess.deboer@voorbeeld.nl", "tessdb", None),
    ("Sem Mulder", "sem.mulder@voorbeeld.nl", None, None),
    ("Fleur Bos", "fleur.bos@voorbeeld.nl", "fleurbos", None),
    ("Noah Vos", "noah.vos@voorbeeld.nl", "noahvos", "06-34567890"),
    ("Lotte Peters", "lotte.peters@voorbeeld.nl", "lottep", None),
    ("Finn Hendriks", "finn.hendriks@voorbeeld.nl", None, None),
    ("Sara van Dijk", "sara.vandijk@voorbeeld.nl", "saravd", None),
    ("Bram Dekker", "bram.dekker@voorbeeld.nl", "bramdekker", None),
    ("Eva Brouwer", "eva.brouwer@voorbeeld.nl", "evabrouwer", None),
    ("Jesse van Leeuwen", "jesse.vanleeuwen@voorbeeld.nl", None, None),
    ("Anna Kok", "anna.kok@voorbeeld.nl", "annakok", None),
    ("Thomas Willems", "thomas.willems@voorbeeld.nl", "thomasw", None),
    ("Isa Groen", "isa.groen@voorbeeld.nl", "isagroen", None),
    ("James Miller", "james.miller@example.com", "jamesm", None),
]


def maak_producten() -> list[dict]:
    uit = []
    for i, (naam, soort, prijs, kleuren) in enumerate(PRODUCTEN):
        variants = []
        for k in kleuren:
            for m in MATEN:
                voorraad = R.choice([0, 0, 3, 8, 15, 25, 40]) if soort == "shirt" else R.choice([0, 2, 5, 9, 14])
                variants.append({"sku": f"FA-{i+1:02d}-{k[:2].upper()}-{m}", "title": f"{k} / {m}", "size": m, "color": k,
                                 "price": prijs, "inventory": voorraad})
        pid = db.insert("products", {"shopify_id": f"gid://shopify/Product/{1000+i}", "title": naam, "handle": naam.lower().replace(" ", "-"),
                                     "product_type": soort, "description": f"{naam} van Farmers Atelier. Zware kwaliteit, relaxed fit.",
                                     "price": prijs, "variants": variants, "synced_at": db.now()})
        uit.append({"id": pid, "naam": naam, "soort": soort, "prijs": prijs, "kleuren": kleuren})
    return uit


def maak_klanten() -> list[dict]:
    uit = []
    for naam, email, handle, tel in KLANTEN:
        cid = db.insert("customers", {"name": naam, "email": email, "phone": tel, "shopify_customer_id": f"gid://shopify/Customer/{R.randint(10**8, 10**9)}",
                                      "tags": [], "created_at": ts(R.uniform(30, 400))})
        db.execute("INSERT OR IGNORE INTO customer_identities(customer_id, channel, external_id, handle, display_name) VALUES (?,?,?,?,?)",
                   (cid, "email", email, None, naam))
        # Social-identiteiten vooraf bekend (alsof ze eerder al samengevoegd zijn), zodat een DM of
        # comment bij dezelfde klant terechtkomt. In het echt gebeurt dat via e-mailmatch of handmatig samenvoegen.
        h = handle or naam.split()[0].lower()
        for kanaal, prefix in (("instagram", "ig"), ("facebook", "fb"), ("tiktok", "tt")):
            db.execute("INSERT OR IGNORE INTO customer_identities(customer_id, channel, external_id, handle, display_name) VALUES (?,?,?,?,?)",
                       (cid, kanaal, f"{prefix}-{R.randint(10**14, 10**15)}", h, naam))
        uit.append({"id": cid, "naam": naam, "email": email, "handle": h})
    return uit


def maak_orders(klanten: list[dict], producten: list[dict]) -> list[dict]:
    uit = []
    scenario = (["unfulfilled"] * 5 + ["in_transit"] * 8 + ["delivered"] * 10 + ["cancelled"] * 2 + ["returned"] * 3 + ["refunded"] * 2)
    R.shuffle(scenario)
    nummer = 1801
    for i, soort in enumerate(scenario):
        klant = klanten[i % len(klanten)] if i < len(klanten) else R.choice(klanten)
        dagen = {"unfulfilled": R.uniform(0.2, 2), "in_transit": R.uniform(1, 5), "delivered": R.uniform(4, 28),
                 "cancelled": R.uniform(2, 20), "returned": R.uniform(10, 30), "refunded": R.uniform(8, 25)}[soort]
        items = []
        for _ in range(R.choice([1, 1, 1, 2, 2, 3])):
            p = R.choice(producten)
            kleur, maat = R.choice(p["kleuren"]), R.choice(MATEN)
            items.append({"title": p["naam"], "sku": f"FA-{producten.index(p)+1:02d}-{kleur[:2].upper()}-{maat}", "quantity": 1,
                          "variant_title": f"{kleur} / {maat}", "size": maat, "color": kleur, "price": p["prijs"], "inventory": R.randint(0, 20)})
        totaal = round(sum(x["price"] for x in items) + (0 if sum(x["price"] for x in items) >= 75 else 4.95), 2)
        vervoerder = R.choice(["PostNL", "PostNL", "DHL"])
        track_nr = f"3S{R.randint(10**12, 10**13)}" if vervoerder == "PostNL" else f"JVGL{R.randint(10**14, 10**15)}"
        track_url = (f"https://jouw.postnl.nl/track-and-trace/{track_nr}-NL-1234AB" if vervoerder == "PostNL"
                     else f"https://www.dhlparcel.nl/nl/volg-je-zending?tt={track_nr}")
        besteld = NU - dt.timedelta(days=dagen)
        tracking, ful_status, fin, ret_status, cancelled, refunds = {}, "UNFULFILLED", "PAID", "NO_RETURN", None, []
        events = []
        if soort in ("in_transit", "delivered", "returned", "refunded"):
            verzonden = besteld + dt.timedelta(hours=R.uniform(6, 30))
            events = [{"status": "LABEL_PRINTED", "at": verzonden.strftime("%Y-%m-%dT%H:%M:%SZ")},
                      {"status": "IN_TRANSIT", "at": (verzonden + dt.timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")}]
            ful_status = "FULFILLED"
            if soort == "in_transit" and dagen > 3:
                events.append({"status": "IN_TRANSIT", "at": (verzonden + dt.timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")})
            if soort in ("delivered", "returned", "refunded"):
                events.append({"status": "OUT_FOR_DELIVERY", "at": (verzonden + dt.timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")})
                events.append({"status": "DELIVERED", "at": (verzonden + dt.timedelta(hours=34)).strftime("%Y-%m-%dT%H:%M:%SZ")})
            tracking = {"company": vervoerder, "number": track_nr, "url": track_url, "status": events[-1]["status"],
                        "estimated_delivery": (verzonden + dt.timedelta(days=2)).strftime("%Y-%m-%d"),
                        "delivered_at": events[-1]["at"] if events[-1]["status"] == "DELIVERED" else None,
                        "shipped_at": verzonden.strftime("%Y-%m-%dT%H:%M:%SZ"), "events": events}
        if soort == "cancelled":
            cancelled = (besteld + dt.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
            fin = "REFUNDED"
            refunds = [{"at": cancelled, "amount": totaal, "note": "Geannuleerd op verzoek klant"}]
        if soort == "returned":
            ret_status = R.choice(["RETURN_REQUESTED", "IN_PROGRESS", "RETURNED"])
            if ret_status == "RETURNED":
                fin = "REFUNDED"
                refunds = [{"at": ts(R.uniform(1, 5)), "amount": items[0]["price"], "note": "Retour ontvangen"}]
        if soort == "refunded":
            fin = "PARTIALLY_REFUNDED"
            refunds = [{"at": ts(R.uniform(1, 6)), "amount": round(items[0]["price"], 2), "note": "Beschadigd artikel"}]
        naam = f"#{nummer}"
        nummer += 1
        oid = shopify.upsert_order({
            "shopify_id": f"gid://shopify/Order/{5000+i}", "name": naam, "email": klant["email"],
            "created_at": besteld.strftime("%Y-%m-%dT%H:%M:%SZ"), "financial_status": fin, "fulfillment_status": ful_status,
            "return_status": ret_status, "total": totaal, "currency": "EUR", "line_items": items,
            "shipping_address": {"name": klant["naam"], "address1": f"{R.choice(['Dorpsstraat', 'Kerklaan', 'Molenweg', 'Lindenlaan'])} {R.randint(1, 120)}",
                                 "zip": f"{R.randint(1000, 9999)} {R.choice(['AB', 'CD', 'XZ', 'KL'])}", "city": R.choice(["Amsterdam", "Utrecht", "Zwolle", "Groningen", "Eindhoven", "Leeuwarden"]), "countryCodeV2": "NL"},
            "tracking": tracking, "refunds": refunds, "returns": [] if ret_status == "NO_RETURN" else [{"name": f"R{nummer}", "status": ret_status, "items": [{"quantity": 1, "reason": R.choice(["SIZE_TOO_SMALL", "SIZE_TOO_LARGE", "NOT_AS_DESCRIBED"])}]}],
            "cancelled_at": cancelled, "note": None, "tags": ["mock"], "raw": {}, "synced_at": db.now(),
        }, customer_id=klant["id"])
        # Fulfillment-events van de (nep) fulfillmentpartij voor een deel van de orders
        if soort in ("in_transit", "delivered") and R.random() < 0.6:
            b = besteld
            for stage, uren in (("received", 0.2), ("picking", 3), ("packed", 6), ("shipped", 9)):
                fulfillment.record_event(naam, stage, (b + dt.timedelta(hours=uren)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                         carrier=vervoerder if stage == "shipped" else None, tracking=track_nr if stage == "shipped" else None,
                                         detail="mock fulfillment", raw={})
            for e in events[1:]:
                fulfillment.record_event(naam, fulfillment.SHOPIFY_EVENT_TO_STAGE.get(e["status"], "in_transit"), e["at"], carrier=vervoerder, tracking=track_nr, detail=e["status"], raw={})
        db.execute("UPDATE customers SET orders_count = orders_count + 1, total_spent = total_spent + ? WHERE id = ?", (totaal, klant["id"]))
        uit.append({"id": oid, "name": naam, "klant": klant, "soort": soort, "totaal": totaal, "items": items, "tracking": tracking})
    return uit


# (kanaal, via, klantindex of None, ordersoort-voorkeur, berichten[], vervolg: 'reply'|'reply_edit'|'close'|'reject'|None)
SCENARIOS = [
    ("email", "email", 0, "in_transit", ["Hoi, waar blijft mijn bestelling? Ik heb {order} vorige week besteld en nog niets ontvangen. Groet, {voornaam}"], "reply"),
    ("email", "email", 1, "in_transit", ["Hallo, wanneer komt mijn pakket aan? Ik heb geen trackingmail gekregen."], "followup_order"),
    ("instagram", "dm", 2, "in_transit", ["Hey! Waar blijft mijn pakket? 😅"], "followup_order"),
    ("email", "email", 3, "delivered", ["Mijn bestelling {order} staat op bezorgd maar ik heb niets ontvangen. Buren hebben ook niets. Wat nu?"], "reply_edit"),
    ("email", "email", 4, "in_transit", ["Ik wacht nu al drie weken op bestelling {order}. De tracking staat al dagen stil. Dit duurt echt te lang."], "reply_edit"),
    ("email", "email", 5, "unfulfilled", ["Hoi, ik heb per ongeluk het verkeerde adres ingevuld bij {order}. Het moet zijn: Lindenlaan 8, 3512 AB Utrecht. Kunnen jullie dat aanpassen?"], "action_address"),
    ("email", "email", 6, "unfulfilled", ["Kan ik bestelling {order} nog annuleren? Ik heb 'm dubbel besteld."], "action_cancel"),
    ("email", "email", 7, "in_transit", ["Ik wil {order} annuleren, ik heb me bedacht."], None),
    ("email", "email", 8, "delivered", ["Ik heb {order} ontvangen maar er zit een Heavy Hoodie in maat L in terwijl ik M had besteld. Verkeerd artikel dus. Hoe lossen we dit op?"], "reply"),
    ("email", "email", 9, "delivered", ["Mijn trui uit {order} is beschadigd aangekomen, er zit een gat in de mouw. Foto in de bijlage."], "reply"),
    ("email", "email", 10, "delivered", ["Hoi, in mijn pakket ({order}) ontbreekt één van de twee shirts. Ik heb er maar één ontvangen."], "reply"),
    ("email", "email", 11, "delivered", ["Ik wil graag een retour aanvragen voor {order}. De crewneck valt me te groot."], "reply_edit"),
    ("email", "email", 12, "returned", ["Ik heb mijn retour van {order} vorige week verstuurd. Is die al aangekomen? En wanneer krijg ik mijn geld terug?"], "reply"),
    ("email", "email", 13, "delivered", ["Kan ik het shirt uit {order} omruilen voor maat L? Hij is net te klein."], "reply"),
    ("email", "email", 14, "refunded", ["Ik zou een terugbetaling krijgen voor {order} maar ik zie nog niets op mijn rekening."], "reply"),
    ("email", "email", 15, "delivered", ["Ik wil mijn geld terug voor {order}. De kwaliteit valt tegen en de kleur is anders dan op de site."], None),
    ("email", "email", 16, None, ["Wat een kutbedrijf, ik wacht al drie weken en niemand reageert. Ik ga een chargeback doen bij mijn bank en een klacht indienen bij de Consumentenbond."], None),
    ("email", "email", 17, "in_transit", ["Als ik mijn bestelling {order} niet binnen 2 dagen heb, schakel ik mijn advocaat in. Dit is onacceptabel."], None),
    ("email", "email", 18, "delivered", ["Ik wil graag een echt persoon spreken, geen bot. Kunnen jullie me bellen over {order}?"], None),
    ("email", "email", 19, "in_transit", ["Hi, where is my order {order}? I ordered last week and haven't received any tracking info. Thanks, James"], "reply"),
    ("email", "email", 0, None, ["Hoi! Ik twijfel tussen maat M en L voor de Atelier Crewneck. Ik ben 1.82 en draag normaal M bij andere merken. Valt hij groot?"], "reply_edit"),
    ("email", "email", 1, None, ["Waar zijn de shirts van gemaakt? Is het biologisch katoen? En krimpt het in de was?"], "reply"),
    ("email", "email", 2, None, ["Mijn kortingscode WELKOM10 werkt niet bij het afrekenen. Kunnen jullie helpen?"], "reply"),
    ("email", "email", 3, "unfulfilled", ["Ik heb via iDEAL betaald voor {order} maar de bestelling staat nog op 'betaling in behandeling'. Is het geld wel binnen? Ik zie dat het is afgeschreven."], None),
    ("email", "email", 4, "delivered", ["Kunnen jullie me de factuur van {order} sturen? Ik heb 'm nodig voor mijn administratie."], "reply"),
    ("email", "email", 5, None, ["Hoi, wat zijn de verzendkosten naar België en hoe lang duurt het?"], "reply"),
    ("email", "email", 6, None, ["Bedankt voor de snelle hulp, helemaal goed zo! Groet"], None),
    ("email", "email", 7, None, ["Hallo, ik ben influencer met 25k volgers en wil graag een samenwerking bespreken. Sturen jullie PR packages?"], None),
    ("email", "email", 8, None, ["Boost your website traffic with our SEO services! Guaranteed backlinks. Unsubscribe here."], None),
    ("email", "email", 9, None, ["Wat is jullie retourbeleid precies? Hoeveel dagen heb ik en wie betaalt de retourverzending?"], "reply_edit"),
    ("instagram", "dm", 10, "in_transit", ["Hoi! Mijn bestelling {order} zou vandaag komen maar de tracking zegt nu 'vertraagd'. Weten jullie meer?"], "reply"),
    ("instagram", "dm", 11, None, ["Komt de Heavy Hoodie in zand nog terug in maat M? Al weken uitverkocht 😢"], "reply"),
    ("instagram", "dm", 12, None, ["Welke maat moet ik nemen in de Essential Tee? Ik draag normaal L maar hoor dat ze ruim vallen"], "reply_edit"),
    ("instagram", "dm", 13, "delivered", ["Hey, ik wil m'n crewneck ruilen voor een andere kleur, kan dat? Order {order}"], "reply"),
    ("instagram", "dm", 14, None, ["Hebben jullie nog een kortingscode? 🙏"], "reply"),
    ("instagram", "dm", 15, "delivered", ["Net binnen, wat een mooie kwaliteit! Superblij mee 🔥"], "reply"),
    ("instagram", "dm", 16, "delivered", ["Mijn shirt heeft na 1x wassen al een vlek/verkleuring. Echt teleurgesteld. Order {order}"], None),
    ("instagram", "dm", 17, None, ["Verzenden jullie ook naar Duitsland?"], "reply"),
    ("instagram", "comment", 18, None, ["Wanneer komt maat M terug?"], "reply"),
    ("instagram", "comment", 0, None, ["🔥🔥🔥"], None),
    ("instagram", "comment", 1, None, ["Wat een kutbedrijf, ik wacht al drie weken op mijn bestelling en krijg geen antwoord!!"], None),
    ("instagram", "comment", 2, None, ["Is dit 100% katoen?"], "reply"),
    ("instagram", "comment", 3, None, ["Waar blijft mijn bestelling? Al 2 weken geleden besteld"], "reply"),
    ("instagram", "comment", 4, None, ["Prachtige kleur die olijf 😍"], "reply"),
    ("instagram", "comment", 5, None, ["Doen jullie ook maat XXL?"], "reply"),
    ("facebook", "dm", 6, "in_transit", ["Goedemiddag, ik heb een vraag over de status van mijn bestelling {order}. Kunt u mij informeren?"], "reply"),
    ("facebook", "dm", 7, "delivered", ["Mijn bestelling klopt niet."], "followup_detail"),
    ("facebook", "dm", 8, None, ["Kan ik mijn bestelling ook afhalen?"], "reply"),
    ("facebook", "comment", 9, None, ["Zijn deze truien warm genoeg voor de winter?"], "reply"),
    ("facebook", "comment", 10, None, ["Ik heb al 3x gemaild en geen reactie. Slechte service."], None),
    ("tiktok", "comment", 11, None, ["waar kan ik deze kopen??"], "reply"),
    ("tiktok", "comment", 12, None, ["hebben jullie ook kids maten"], "reply"),
    ("tiktok", "comment", 13, None, ["te duur voor een shirt"], None),
    ("tiktok", "comment", 14, None, ["link in bio werkt niet"], "reply"),
]


def kies_order(orders: list[dict], klant: dict, soort: str | None) -> dict | None:
    eigen = [o for o in orders if o["klant"]["id"] == klant["id"]]
    if soort:
        for o in eigen:
            if o["soort"] == soort:
                return o
        # Geen eigen order van die soort: maak er één bij van deze klant
        return None
    return eigen[0] if eigen else None


def maak_gesprekken(klanten: list[dict], orders: list[dict]) -> None:
    n = len(SCENARIOS)
    tijden = sorted(R.uniform(0.02, 13.5) for _ in range(n))
    tijden.reverse()  # oudste eerst
    for i, (kanaal, via, ki, soort, berichten, vervolg) in enumerate(SCENARIOS):
        klant = klanten[ki % len(klanten)]
        order = kies_order(orders, klant, soort)
        if soort and order is None:
            # Klant zonder passende order: pak een willekeurige order van die soort en koppel 'm aan de klant
            kandidaat = R.choice([o for o in orders if o["soort"] == soort])
            db.execute("UPDATE orders SET email = ?, customer_id = ? WHERE name = ?", (klant["email"], klant["id"], kandidaat["name"]))
            kandidaat["klant"] = klant
            order = kandidaat
        voornaam = klant["naam"].split()[0]
        dagen = tijden[i]
        klok(ts(dagen))
        ref = {"comment_id": f"c{R.randint(10**10, 10**11)}", "media_id": f"m{R.randint(10**10, 10**11)}", "permalink": "https://www.instagram.com/p/mock/"} if via == "comment" else {}
        sender = {"channel": kanaal, "name": klant["naam"] if kanaal in ("email", "facebook") else klant["handle"],
                  "handle": klant["handle"], "email": klant["email"] if kanaal == "email" else None,
                  "external_id": klant["email"]}
        if kanaal != "email":
            ident = db.one("SELECT external_id FROM customer_identities WHERE customer_id = ? AND channel = ?", (klant["id"], kanaal))
            sender["external_id"] = ident["external_id"] if ident else f"{kanaal}-{klant['id']}"
        thread = f"mock-thread-{i}" if kanaal == "email" else (ref["comment_id"] if via == "comment" else sender["external_id"])
        tekst = berichten[0].format(order=order["name"] if order else "#18xx", voornaam=voornaam)
        bijlagen = [{"name": "IMG_2041.jpg", "url": None, "content_type": "image/jpeg"}] if "bijlage" in tekst.lower() or "foto" in tekst.lower() else []
        onderwerp = None
        if kanaal == "email":
            onderwerp = {"reply": "Vraag over mijn bestelling", "followup_order": "Waar blijft mijn pakket?"}.get(vervolg or "", None) or tekst[:50]
            if order and order["name"] in tekst:
                onderwerp = f"Bestelling {order['name']}"
        res = pipeline.ingest({"channel": kanaal, "via": via, "external_message_id": f"mock-{i}-1",
                               "external_thread_id": thread,
                               "sender": sender, "subject": onderwerp, "text": tekst, "attachments": bijlagen,
                               "sent_at": ts(dagen), "external_ref": ref})
        cid = res["conversation_id"]
        # Vervolgstappen
        if vervolg == "followup_order" and order:
            klok(ts(dagen - 0.05))
            d = db.one("SELECT id, body FROM ai_drafts WHERE conversation_id = ? AND status = 'pending'", (cid,))
            if d:
                service.send_reply(cid, d["body"], user_id=1, draft_id=d["id"])
            klok(ts(dagen - 0.12))
            pipeline.ingest({"channel": kanaal, "via": via, "external_message_id": f"mock-{i}-2", "external_thread_id": thread,
                             "sender": sender, "text": f"Het is {order['name']}", "sent_at": ts(dagen - 0.12), "external_ref": {}})
            if R.random() < 0.6:
                klok(ts(dagen - 0.15))
                d = db.one("SELECT id, body FROM ai_drafts WHERE conversation_id = ? AND status = 'pending'", (cid,))
                if d:
                    service.send_reply(cid, d["body"], user_id=1, draft_id=d["id"], close_after=True)
        elif vervolg == "followup_detail" and order:
            klok(ts(dagen - 0.04))
            d = db.one("SELECT id, body FROM ai_drafts WHERE conversation_id = ? AND status = 'pending'", (cid,))
            if d:
                service.send_reply(cid, d["body"], user_id=1, draft_id=d["id"])
            klok(ts(dagen - 0.3))
            pipeline.ingest({"channel": kanaal, "via": via, "external_message_id": f"mock-{i}-2", "external_thread_id": thread,
                             "sender": sender, "text": f"Order {order['name']}, ik heb een Essential Tee in zwart ontvangen maar ik had olijf besteld.",
                             "sent_at": ts(dagen - 0.3), "external_ref": {}})
        elif vervolg in ("reply", "reply_edit") and dagen > 0.3:
            klok(ts(dagen - R.uniform(0.02, 0.4)))
            d = db.one("SELECT id, body FROM ai_drafts WHERE conversation_id = ? AND status = 'pending'", (cid,))
            if d:
                body = d["body"]
                if vervolg == "reply_edit":
                    body = body.replace("Groet,\nFarmers Atelier", f"Fijne dag!\nWieger, Farmers Atelier").replace("Hoi", "Hé")
                    body = body.replace("[", "").replace("]", "").replace("— nog in te vullen door Wieger.", "")
                service.send_reply(cid, body, user_id=R.choice([1, 1, 2]), draft_id=d["id"], close_after=R.random() < 0.7)
                if vervolg == "reply_edit" and R.random() < 0.5:
                    service.draft_feedback(d["id"], "down", R.choice(["toon", "feiten", "te lang"]), 1)
                elif R.random() < 0.3:
                    service.draft_feedback(d["id"], "up", None, 1)
            elif R.random() < 0.5:
                service.send_reply(cid, f"Hoi {voornaam},\n\nDank voor je bericht, ik pak het meteen op en kom vandaag bij je terug.\n\nGroet,\nWieger", user_id=1)
        elif vervolg == "action_address" and order:
            service.propose_action(cid, "address_change", {"order_name": order["name"], "address": {"address1": "Lindenlaan 8", "zip": "3512 AB", "city": "Utrecht", "country": "NL"}},
                                   f"Adres van {order['name']} wijzigen naar Lindenlaan 8, 3512 AB Utrecht?")
        elif vervolg == "action_cancel" and order:
            service.propose_action(cid, "cancel_order", {"order_name": order["name"], "refund": True, "restock": True},
                                   f"Order {order['name']} annuleren en €{order['totaal']:.2f} terugstorten?")
        klok(None)
    # Een paar gesprekken toewijzen en één snoozen
    open_ids = [r["id"] for r in db.rows("SELECT id FROM conversations WHERE status = 'open' ORDER BY id")]
    for cid in open_ids[::4]:
        service.assign(cid, 1, 1)
    for cid in open_ids[1::7]:
        service.assign(cid, 2, 1)
    if len(open_ids) > 5:
        service.set_status(open_ids[5], "snoozed", 1, snooze_hours=48)


def main() -> None:
    if "--reset" in sys.argv and os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
        for ext in ("-wal", "-shm"):
            if os.path.exists(config.DB_PATH + ext):
                os.remove(config.DB_PATH + ext)
    db.init_db()
    rules.seed_defaults()
    knowledge.sync_from_disk()
    if db.scalar("SELECT COUNT(*) FROM conversations"):
        print("Database bevat al gesprekken. Gebruik --reset om opnieuw te beginnen.")
        return
    db.set_setting("ai_mode", "mock")  # mock-data altijd met de mock-agent (geen API-kosten, reproduceerbaar)
    print("Producten…")
    producten = maak_producten()
    print("Klanten…")
    klanten = maak_klanten()
    print("Orders…")
    orders = maak_orders(klanten, producten)
    print("Gesprekken (dit duurt even, elk bericht loopt door de pipeline)…")
    maak_gesprekken(klanten, orders)
    db.set_setting("ai_mode", "auto")
    print(f"Klaar: {db.scalar('SELECT COUNT(*) FROM customers')} klanten, {db.scalar('SELECT COUNT(*) FROM orders')} orders, "
          f"{db.scalar('SELECT COUNT(*) FROM conversations')} gesprekken, {db.scalar('SELECT COUNT(*) FROM messages')} berichten, "
          f"{db.scalar('SELECT COUNT(*) FROM ai_drafts')} AI-concepten, {db.scalar('SELECT COUNT(*) FROM learning_records')} leerrecords.")


if __name__ == "__main__":
    main()
