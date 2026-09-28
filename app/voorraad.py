"""Voorraad, retouren en de kosten van het opnieuw verkopen daarvan.

Staat los van de klantenservice-kant: dit is de tweede kijkrichting die Wieger
wil, met de vraag "wat ligt er nog en wat kost het om het weer te verkopen".

Twee bronnen, en ze weten allebei iets wat de ander niet weet:

* `data/bronnen/artikelen.json` — uit de hand bijgehouden Excel. Weet welke
  modellen, kleuren en maten bestaan en hoeveel er van de shirts op voorraad
  liggen. Weet niets van orders.
* Shopify — weet de orders, de retouren en de actuele voorraad, maar alleen
  zolang de app gekoppeld is.

Zolang Shopify niet gekoppeld is werkt alles hier gewoon door op de Excel, en
zegt `herkomst` per cijfer waar het vandaan komt. Er wordt nooit een getal
getoond zonder te vermelden waar het op rust.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

import config

BRONNEN = os.path.join(config.DATA_DIR, "bronnen")
MAATVOLGORDE = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "One size"]


def _lees(bestand: str) -> dict:
    try:
        with open(os.path.join(BRONNEN, bestand), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _maatsleutel(maat: str | None) -> tuple[int, str]:
    """Sorteert S, M, L, XL — niet alfabetisch, want dan komt L vóór M."""
    if not maat:
        return (len(MAATVOLGORDE) + 1, "")
    try:
        return (MAATVOLGORDE.index(maat), "")
    except ValueError:
        return (len(MAATVOLGORDE), maat)


def artikelen() -> dict:
    """Voorraad per model, met de maten eronder zodat het dashboard kan uitklappen."""
    ruw = _lees("artikelen.json")
    regels = ruw.get("regels", [])

    modellen: dict[tuple, dict] = {}
    for r in regels:
        sleutel = (r["groep"], r["model"], r.get("kleur"))
        m = modellen.setdefault(sleutel, {
            "groep": r["groep"], "model": r["model"], "kleur": r.get("kleur"),
            "varianten": 0, "voorraad": 0, "voorraad_bekend": False, "maten": [],
        })
        m["varianten"] += 1
        m["maten"].append({"maat": r.get("maat"), "sku": r.get("sku"), "voorraad": r.get("voorraad")})
        if r.get("voorraad") is not None:
            m["voorraad"] += r["voorraad"]
            m["voorraad_bekend"] = True

    lijst = list(modellen.values())
    for m in lijst:
        m["maten"].sort(key=lambda x: _maatsleutel(x["maat"]))
        if not m["voorraad_bekend"]:
            m["voorraad"] = None          # niets is niet nul

    # Meeste voorraad bovenaan, want dat is waar het meeste geld in zit. Modellen
    # zonder voorraadgetal horen achteraan: die zijn niet leeg, die zijn onbekend,
    # en bovenaan zetten zou suggereren dat ze het belangrijkst zijn.
    lijst.sort(key=lambda m: (m["voorraad"] is None, -(m["voorraad"] or 0), m["model"]))

    per_groep: dict[str, dict] = defaultdict(lambda: {"modellen": 0, "varianten": 0,
                                                      "voorraad": 0, "voorraad_bekend": False})
    for m in lijst:
        g = per_groep[m["groep"]]
        g["modellen"] += 1
        g["varianten"] += m["varianten"]
        if m["voorraad"] is not None:
            g["voorraad"] += m["voorraad"]
            g["voorraad_bekend"] = True
    for g in per_groep.values():
        if not g["voorraad_bekend"]:
            g["voorraad"] = None

    per_maat: dict[str, int] = defaultdict(int)
    for r in regels:
        if r.get("voorraad"):
            per_maat[r.get("maat") or "onbekend"] += r["voorraad"]

    return {
        "bron": ruw.get("bron"),
        "modellen": lijst,
        "per_groep": dict(per_groep),
        "per_maat": dict(sorted(per_maat.items(), key=lambda x: _maatsleutel(x[0]))),
        "totaal_varianten": len(regels),
        "totaal_voorraad": sum(r["voorraad"] for r in regels if r.get("voorraad")),
        "varianten_zonder_voorraadgetal": sum(1 for r in regels if r.get("voorraad") is None),
    }


def retouren() -> dict:
    """De teruggekomen zendingen.

    De Excel levert alleen trackingnummers: hoeveel pakketten er fysiek binnen
    zijn, niet wat erin zat. Wat erin zat komt uit Shopify zodra dat gekoppeld
    is; tot die tijd staat `artikelen_bekend` op false en zegt het dashboard dat
    er wel een aantal is maar nog geen inhoud.
    """
    ruw = _lees("retourscans.json")
    codes = ruw.get("codes", [])
    return {
        "bron": ruw.get("bron"),
        "aantal_zendingen": ruw.get("aantal", len(codes)),
        "per_vervoerder": ruw.get("per_vervoerder", {}),
        "artikelen_bekend": False,
        "regels": [],
        "toelichting": ("Uit de Excel komt per retour alleen een trackingnummer. "
                        "Welke artikelen en maten erin zaten is pas bekend als Shopify "
                        "gekoppeld is en de retouren daar opgehaald kunnen worden."),
    }


def _tarieven() -> dict:
    return _lees("fulfilment_tarieven.json")


def kosten_hergebruik(aantal: int | None = None, weken_opslag: int = 12,
                      land: str = "NL") -> dict:
    """Wat kost het om één teruggekomen artikel opnieuw te verkopen?

    Rekent met de tarieven uit de Innostock-offerte. Drie posten:
    binnenkomst (retourverwerking + inslag), liggen (opslag per week) en
    opnieuw verzenden (pick & pack + verpakking + label).
    """
    t = _tarieven()
    if not t:
        return {"beschikbaar": False}

    h = t.get("handling", {})
    o = t.get("opslag", {})
    labels = t.get("verzendlabels", [])
    verpakking = t.get("verpakking", [])

    label = next((l for l in labels if l.get("land") == land), labels[0] if labels else {})
    # Een shirt past in de brievenbusdoos; dat is de goedkoopste realistische keuze.
    doos = next((v for v in verpakking if "Brievenbus" in v.get("naam", "")),
                verpakking[0] if verpakking else {})

    retourverwerking = h.get("retourverwerking", {}).get("bedrag", 0)
    inslag = h.get("inslag", {}).get("bedrag", 0)
    opslag_week = o.get("sku_locatie", {}).get("bedrag", 0)
    pick = h.get("pick_and_pack_eerste_item", {}).get("bedrag", 0)
    doosprijs = doos.get("bedrag", 0)
    labelprijs = label.get("bedrag", 0)

    binnenkomst = retourverwerking + inslag
    liggen = opslag_week * weken_opslag
    opnieuw_versturen = pick + doosprijs + labelprijs
    per_stuk = binnenkomst + liggen + opnieuw_versturen

    uit = {
        "beschikbaar": True,
        "bron": t.get("_bron"),
        "leverancier": t.get("leverancier"),
        "btw_percentage": t.get("btw_percentage", 21),
        "aannames": {
            "weken_opslag": weken_opslag,
            "land": land,
            "verpakking": doos.get("naam"),
            "label": f"{label.get('vervoerder','')} {label.get('land','')} ({label.get('grens','')})".strip(),
        },
        "posten": [
            {"post": "Retourverwerking", "bedrag": retourverwerking,
             "uitleg": "Uitpakken, controleren en terugleggen van één teruggekomen zending."},
            {"post": "Inslag", "bedrag": inslag,
             "uitleg": "Eenmalig bij het inboeken van het artikel in het magazijn."},
            {"post": f"Opslag ({weken_opslag} weken)", "bedrag": liggen,
             "uitleg": f"€{opslag_week:.2f} per sku-locatie per week. Loopt door zolang het blijft liggen."},
            {"post": "Pick & pack", "bedrag": pick,
             "uitleg": "Vaste startprijs per order, inclusief het eerste artikel."},
            {"post": f"Verpakking ({doos.get('naam','')})", "bedrag": doosprijs,
             "uitleg": "Aangenomen dat één shirt in een brievenbusdoos past."},
            {"post": f"Verzendlabel {label.get('vervoerder','')} {label.get('land','')}".strip(),
             "bedrag": labelprijs, "uitleg": label.get("grens", "")},
        ],
        "per_stuk_ex_btw": round(per_stuk, 2),
        "per_stuk_incl_btw": round(per_stuk * (1 + t.get("btw_percentage", 21) / 100), 2),
        "opsplitsing": {
            "binnenkomst": round(binnenkomst, 2),
            "liggen": round(liggen, 2),
            "opnieuw_versturen": round(opnieuw_versturen, 2),
        },
        "open_punten": t.get("open_punten", []),
    }

    if aantal:
        uit["aantal"] = aantal
        uit["totaal_ex_btw"] = round(per_stuk * aantal, 2)
        uit["totaal_incl_btw"] = round(per_stuk * aantal * (1 + t.get("btw_percentage", 21) / 100), 2)
        uit["opsplitsing_totaal"] = {k: round(v * aantal, 2) for k, v in uit["opsplitsing"].items()}
    return uit


def dropwaarde() -> dict:
    """Wat er ligt en wat het waard is, volgens de opgave van Wieger.

    Bewust gescheiden van de Excel-telling. De Excel telt 1146 shirts en kent geen
    aantallen voor truien; de opgave is 1750 shirts en 400 truien. Beide worden
    getoond, want een verschil van 604 stuks verzwijgen zou het dashboard
    betrouwbaarder laten lijken dan het is.
    """
    d = _lees("dropwaarde.json")
    if not d:
        return {"beschikbaar": False}
    d["beschikbaar"] = True
    return d


def overzicht() -> dict:
    """Alles wat de Voorraad-tab nodig heeft, in één keer."""
    a = artikelen()
    r = retouren()
    return {
        "artikelen": a,
        "retouren": r,
        "drop": dropwaarde(),
        "kosten": kosten_hergebruik(aantal=r["aantal_zendingen"]),
        "tarieven": _tarieven(),
    }
