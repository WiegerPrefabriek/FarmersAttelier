"""Tijdelijke stand: bestellingen die niet van ons zijn.

Er draait een andere webwinkel die hetzelfde kledingmerk verkoopt en zich als
Farmers Atelier presenteert. Klanten die daar besteld hebben mailen ons over
retouren, verkeerde artikelen en geld terug. Zolang onze eigen winkel dicht is
gaat het bij zulke vragen vrijwel altijd om die andere partij.

Deze stand zet daarom voor die categorieën één vast antwoord klaar, in plaats van
het gewone retourantwoord. Hij is bedoeld om **tijdelijk** aan te staan: zodra de
winkel weer open is en de gewone stroom op gang komt, zet je hem uit en werkt
alles weer als normaal.

    db.set_setting("nepshop_modus", True)    # aan
    db.set_setting("nepshop_modus", False)   # uit

**De veiligheidsklep.** Niet elke vraag komt van die andere winkel. In de mailbox
stonden er op 28-09-2026 drie, en ze lagen niet zoals verwacht:

* **#1008 en #1010** staan nergens in Shopify → die komen van de andere winkel.
* **19144 bestaat wél**: Marvin Born, 1 februari 2026, EUR 279,80, vier artikelen,
  afgehandeld met tracking. Een echte klant die al acht maanden op antwoord wacht.
  Die het antwoord "dit is niet onze bestelling" sturen zou aantoonbaar onjuist
  zijn.

Daarom kijkt deze stand eerst of de bestelling bij ons bestaat:

* Staat het ordernummer in Shopify → gewone route, dit antwoord komt er niet.
* Past het nummer bij onze reeks (14541-19350) maar is Shopify niet gekoppeld →
  naar een mens. Bij twijfel geen standaardantwoord.
* Kennen we de bestelling niet en past het nummer niet bij de reeks → dit
  antwoord, als concept, met een mens die het nog naleest.
"""

from __future__ import annotations

import re

from app import db

# Categorieën waar dit over kan gaan. Een productvraag of een compliment hoort er
# niet bij: die gaan niet over een bestelling.
INTENTS = {
    "return.request", "return.status", "refund.request", "refund.status",
    "exchange.request", "order.wrong_item", "order.missing_item", "order.damaged",
    "shipping.status", "shipping.delay", "shipping.delivery_issue", "order.invoice",
}

# De winkel staat stil. De laatste bestelling in Shopify is 19350 van 9 juni 2026;
# daarna is er niets meer binnengekomen. Gaat een vraag over een bestelling die
# ná die datum geplaatst zou zijn, dan kan die niet van ons zijn.
LAATSTE_BESTELDATUM = "2026-06-09"
HOOGSTE_ORDERNUMMER = 19350

# Onze eigen nummers zijn VIJFcijferig en lopen van 14541 tot 19350. Viercijferige
# nummers als #1008 en #1010 komen niet uit onze winkel.
#
# LET OP, dit is een keer goed misgegaan. Eerst stond hier een regel voor
# viercijferige nummers (#1xxx), overgenomen uit de mock-data waarmee het project
# begon. Daardoor gold order 19144 als "niet van ons" terwijl die wél bestaat —
# Marvin Born, 1 februari, EUR 279,80, vier artikelen, met tracking — en golden
# #1008 en #1010 als echt terwijl ze nergens te vinden zijn. Precies omgekeerd.
# De vorm van een nummer is hooguit een aanwijzing; het antwoord staat in Shopify.
ONZE_REEKS = re.compile(r"^#?1[4-9]\d{3}$")


def _binnen_onze_reeks(ordernaam: str) -> bool:
    schoon = ordernaam.strip().lstrip("#")
    if not ONZE_REEKS.match(schoon):
        return False
    try:
        return int(schoon) <= HOOGSTE_ORDERNUMMER
    except ValueError:
        return False


def aan() -> bool:
    return bool(db.setting("nepshop_modus", False))


def _bestaat_in_shopify(ordernaam: str) -> bool | None:
    """True/False als Shopify antwoordt, None als we het niet kunnen nagaan."""
    try:
        from app.integrations import shopify
        if not shopify.client().configured:
            return None
        return shopify.get_order(ordernaam, refresh=True) is not None
    except Exception:  # noqa: BLE001 — niet kunnen nagaan is iets anders dan 'bestaat niet'
        return None


def beoordeel(intent: str | None, ordernaam: str | None, tekst: str = "") -> dict:
    """Moet dit bericht het nepshop-antwoord krijgen?

    Geeft altijd een reden terug, zodat in het gesprek terug te lezen is waaróm
    een klant dit antwoord kreeg — of juist niet.
    """
    if not aan():
        return {"van_toepassing": False, "reden": "de tijdelijke stand staat uit"}
    if intent not in INTENTS:
        return {"van_toepassing": False, "reden": f"categorie {intent} gaat niet over een bestelling"}

    if ordernaam:
        bestaat = _bestaat_in_shopify(ordernaam)
        if bestaat is True:
            return {"van_toepassing": False, "mens_nodig": True,
                    "reden": f"order {ordernaam} bestaat wél in Shopify — dit is een echte klant"}
        if bestaat is None and _binnen_onze_reeks(ordernaam):
            return {"van_toepassing": False, "mens_nodig": True,
                    "reden": (f"order {ordernaam} past bij onze eigen nummerreeks, maar Shopify is niet "
                              "gekoppeld dus we kunnen het niet nagaan. Bij twijfel geen standaardantwoord.")}
        if bestaat is False:
            return {"van_toepassing": True,
                    "reden": f"order {ordernaam} bestaat niet in Shopify"}
        return {"van_toepassing": True,
                "reden": f"order {ordernaam} past niet bij onze nummerreeks"}

    return {"van_toepassing": True,
            "reden": "geen ordernummer genoemd en onze winkel was dicht in deze periode"}


ANTWOORD = """Hoi {voornaam},

Wat vervelend dat je hiermee zit, en dank dat je ons hebt gemaild.

We hebben het nagekeken, maar deze bestelling kunnen we bij ons niet terugvinden.
Dat heeft een vervelende oorzaak: er is een andere webwinkel die hetzelfde
kledingmerk verkoopt en zich als Farmers Atelier presenteert. Klanten denken
daardoor bij ons besteld te hebben, terwijl de bestelling en het geld bij een
andere partij terecht zijn gekomen. Onze eigen winkel is in deze periode gesloten
geweest.

Dat betekent helaas dat wij je hier niet mee kunnen helpen: we kunnen je
bestelling niet inzien, geen retour aannemen en het geld niet terugstorten, omdat
het nooit bij ons is binnengekomen.

Wat je wel kunt doen:

1. Zoek de orderbevestiging op die je destijds hebt ontvangen. Daarin staan de
   website en het e-mailadres van de winkel waar je werkelijk besteld hebt.
2. Vraag je geld terug via je bank of creditcardmaatschappij. Bij iDEAL, PayPal of
   creditcard kun je een terugboeking of koperbescherming aanvragen. Daar zitten
   termijnen aan, dus wacht er niet te lang mee.
3. Maak melding bij de Fraudehelpdesk via fraudehelpdesk.nl of 088 - 786 73 72.

Het spijt ons oprecht dat dit onder onze naam gebeurt. We vinden het net zo
vervelend als jij.

Denk je dat het tóch bij ons besteld is? Stuur dan je ordernummer, de datum van je
bestelling en het e-mailadres waarmee je bestelde, dan zoeken we het opnieuw uit.

Met vriendelijke groet,
Farmers Atelier"""


def antwoord_voor(klantnaam: str | None) -> str:
    voornaam = (klantnaam or "").strip().split(" ")[0] if klantnaam else ""
    return ANTWOORD.format(voornaam=voornaam or "daar")
