"""E-mailcampagnes: opstellen, doelgroep kiezen, klaarzetten. Nooit versturen.

Vaste afspraak met Wieger, en die staat hier omdat code langer meegaat dan een
gesprek: **dit systeem verstuurt nooit zelf een campagne.** Niet naar één klant,
niet naar 17.524. Er is geen `verstuur()` in dit bestand en die komt er niet.

Wat dit wel doet:

* een campagne opstellen met onderwerp en tekst;
* de doelgroep kiezen uit het klantenbestand, met het aantal ontvangers erbij;
* controleren of de campagne voldoet aan wat wettelijk moet (afmeldlink,
  afzender, geen mensen zonder toestemming);
* de campagne klaarzetten als concept, met een voorbeeld van hoe hij eruitziet.

Versturen doet Wieger zelf, met de hand, in Shopify Email of waar de campagne
uiteindelijk heen gaat. Dat is geen technische beperking maar een keuze: een mail
naar duizenden mensen is onomkeerbaar en hoort een menselijke handeling te zijn.
"""

from __future__ import annotations

import json
import os
import re

import config
from app import db

# Wie je mag mailen. Alleen wie uitdrukkelijk toestemming heeft gegeven.
# NOT_SUBSCRIBED, UNSUBSCRIBED en een lege status horen er allemaal buiten:
# geen toestemming is geen toestemming, ook niet als iemand ooit besteld heeft.
TOEGESTAAN = {"SUBSCRIBED"}

DOELGROEPEN = {
    "alle_abonnees": {
        "naam": "Iedereen met toestemming",
        "uitleg": "Alle klanten die toestemming hebben gegeven voor e-mail.",
        "filter": lambda k: k["email_toestemming"] in TOEGESTAAN,
    },
    "kopers": {
        "naam": "Heeft ooit besteld",
        "uitleg": "Klanten met minstens één bestelling. Zij kennen het merk en de pasvorm al.",
        "filter": lambda k: k["email_toestemming"] in TOEGESTAAN and int(k["bestellingen"] or 0) > 0,
    },
    "kopers_recent": {
        "naam": "Besteld in het laatste jaar",
        "uitleg": "De warmste groep: recente klanten die zich jou nog herinneren.",
        "filter": lambda k: (k["email_toestemming"] in TOEGESTAAN
                             and (k["laatste_order_datum"] or "") >= "2025-09-01"),
    },
    "meermaals": {
        "naam": "Meer dan één keer besteld",
        "uitleg": "Terugkerende klanten. Klein maar waardevol.",
        "filter": lambda k: k["email_toestemming"] in TOEGESTAAN and int(k["bestellingen"] or 0) > 1,
    },
    "nooit_besteld": {
        "naam": "Ingeschreven maar nooit besteld",
        "uitleg": "Wel interesse getoond, nooit tot een bestelling gekomen.",
        "filter": lambda k: k["email_toestemming"] in TOEGESTAAN and int(k["bestellingen"] or 0) == 0,
    },
    "nederland": {
        "naam": "Alleen Nederland",
        "uitleg": "Handig als de aanbieding of verzendtijd alleen voor NL geldt.",
        "filter": lambda k: k["email_toestemming"] in TOEGESTAAN and k["landcode"] == "NL",
    },
}


def _klantenbestand() -> list[dict]:
    pad = os.path.join(config.DATA_DIR, "export", "klanten.json")
    try:
        with open(pad, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def doelgroepen() -> list[dict]:
    """Elke doelgroep met het aantal ontvangers, zodat je weet wat je aanricht."""
    klanten = _klantenbestand()
    uit = []
    for sleutel, d in DOELGROEPEN.items():
        try:
            n = sum(1 for k in klanten if d["filter"](k))
        except Exception:  # noqa: BLE001
            n = 0
        uit.append({"sleutel": sleutel, "naam": d["naam"], "uitleg": d["uitleg"], "aantal": n})
    uit.sort(key=lambda x: -x["aantal"])
    return uit


def ontvangers(sleutel: str, maximaal: int | None = None) -> list[dict]:
    d = DOELGROEPEN.get(sleutel)
    if not d:
        return []
    uit = [k for k in _klantenbestand() if d["filter"](k)]
    return uit[:maximaal] if maximaal else uit


# ---------------------------------------------------------------------------
# Controle vóór het klaarzetten
# ---------------------------------------------------------------------------
def controleer(onderwerp: str, tekst: str, doelgroep: str) -> dict:
    """Loopt na wat er mis kan gaan. Blokkeert niets, maar meldt alles.

    De punten hieronder zijn niet willekeurig: het zijn de dingen waar een
    mailing op stukloopt, in volgorde van hoe vaak het misgaat.
    """
    punten = []

    if not onderwerp.strip():
        punten.append(("fout", "Geen onderwerp. Mail zonder onderwerp wordt vaak als spam gezien."))
    elif len(onderwerp) > 60:
        punten.append(("let op", f"Onderwerp is {len(onderwerp)} tekens. Op een telefoon zie je er "
                                 "ongeveer 40; de rest valt weg."))

    if "{{afmeldlink}}" not in tekst and "afmeld" not in tekst.lower():
        punten.append(("fout", "Geen afmeldlink. Die is wettelijk verplicht bij reclame, en zonder "
                               "afmeldlink melden mensen je aan als spam — dat is veel schadelijker."))

    if not re.search(r"farmers\s*atelier", tekst, re.I):
        punten.append(("let op", "De naam Farmers Atelier komt niet in de tekst voor. Ontvangers "
                                 "moeten meteen zien van wie de mail is."))

    d = DOELGROEPEN.get(doelgroep)
    if not d:
        punten.append(("fout", f"Onbekende doelgroep: {doelgroep}"))
    else:
        n = len(ontvangers(doelgroep))
        if n == 0:
            punten.append(("fout", "Deze doelgroep is leeg. Is het klantenbestand al opgehaald? "
                                   "Zo niet: scripts/klanten_export.py --doen"))
        elif n > 5000:
            punten.append(("let op", f"{n:,} ontvangers".replace(",", ".") +
                           ". Bij zo'n aantal is het verstandig in stukken te versturen — eerst "
                           "duizend, kijken of alles goed aankomt, dan de rest."))

    # Woorden die spamfilters laten aanslaan
    verdacht = [w for w in ("gratis!!!", "klik hier nu", "100% gratis", "!!!", "GRATIS", "WIN")
                if w in tekst]
    if verdacht:
        punten.append(("let op", "Deze woorden laten spamfilters aanslaan: " + ", ".join(verdacht)))

    return {
        "ok": not any(s == "fout" for s, _ in punten),
        "punten": [{"soort": s, "tekst": t} for s, t in punten],
        "ontvangers": len(ontvangers(doelgroep)) if d else 0,
    }


# ---------------------------------------------------------------------------
# Opslaan als concept
# ---------------------------------------------------------------------------
def bewaar(naam: str, onderwerp: str, tekst: str, doelgroep: str,
           campagne_id: int | None = None) -> dict:
    """Zet de campagne weg als CONCEPT. Verstuurt niets."""
    c = controleer(onderwerp, tekst, doelgroep)
    waarden = {
        "naam": naam, "onderwerp": onderwerp, "tekst": tekst, "doelgroep": doelgroep,
        "status": "concept", "ontvangers": c["ontvangers"],
        "controle": db.dumps(c["punten"]),
    }
    if campagne_id:
        db.update("campagnes", campagne_id, waarden)
    else:
        campagne_id = db.insert("campagnes", waarden)
    return {"id": campagne_id, "controle": c, "status": "concept",
            "let_op": "Staat klaar als concept. Versturen doet Wieger zelf."}


def lijst() -> list[dict]:
    rijen = db.rows("SELECT * FROM campagnes ORDER BY id DESC")
    for r in rijen:
        r["controle"] = db.loads(r.get("controle"), [])
    return rijen


def een(campagne_id: int) -> dict | None:
    r = db.one("SELECT * FROM campagnes WHERE id = ?", (campagne_id,))
    if r:
        r["controle"] = db.loads(r.get("controle"), [])
        r["voorbeeld_ontvangers"] = [
            {"naam": (k["voornaam"] + " " + k["achternaam"]).strip() or "(geen naam)",
             "email": k["email"], "bestellingen": k["bestellingen"]}
            for k in ontvangers(r["doelgroep"], maximaal=5)]
    return r


def verwijder(campagne_id: int) -> None:
    db.execute("DELETE FROM campagnes WHERE id = ?", (campagne_id,))
