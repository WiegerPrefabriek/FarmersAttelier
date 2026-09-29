#!/usr/bin/env python3
"""Haalt het volledige klantenbestand uit Shopify en zet het lokaal weg.

    ./.venv/bin/python scripts/klanten_export.py            # tellen, niets opslaan
    ./.venv/bin/python scripts/klanten_export.py --doen     # ophalen en wegschrijven

Dit script LEEST alleen. Het verstuurt niets, schrijft niets terug naar Shopify en
maakt geen campagne aan.

Het resultaat is een bestand met persoonsgegevens van ruim twintigduizend mensen.
Het landt daarom in `data/`, dat in `.gitignore` staat, met leesrechten alleen voor
de eigenaar. Niet doorsturen, niet in een chat plakken, niet naar een clouddienst
uploaden die er niet voor bedoeld is.

Per klant komt mee: naam, e-mail, of iemand toestemming voor e-mail heeft gegeven,
aantal bestellingen, totaal besteed bedrag, land, taal en de datum van de laatste
bestelling. Genoeg om een campagne op te bouwen; geen betaalgegevens, geen
volledige adressen.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from app.integrations import shopify  # noqa: E402

VRAAG = """query($cursor: String) {
  customers(first: 250, after: $cursor, sortKey: CREATED_AT) {
    edges { node {
      id firstName lastName email phone createdAt note
      numberOfOrders amountSpent { amount }
      emailMarketingConsent { marketingState marketingOptInLevel consentUpdatedAt }
      smsMarketingConsent { marketingState }
      defaultAddress { country countryCodeV2 city }
      locale tags
      lastOrder { name createdAt }
    } }
    pageInfo { hasNextPage endCursor }
  } }"""


def haal_alles(maximaal_rondes: int = 200) -> list[dict]:
    c = shopify.client()
    if not c.configured:
        raise SystemExit("Shopify is niet gekoppeld.")
    uit, cursor = [], None
    for ronde in range(maximaal_rondes):
        d = c.graphql(VRAAG, {"cursor": cursor})["customers"]
        for e in d["edges"]:
            n = e["node"]
            toestemming = (n.get("emailMarketingConsent") or {})
            adres = (n.get("defaultAddress") or {})
            laatste = (n.get("lastOrder") or {})
            uit.append({
                "id": (n["id"] or "").rsplit("/", 1)[-1],
                "voornaam": n.get("firstName") or "",
                "achternaam": n.get("lastName") or "",
                "email": n.get("email") or "",
                "email_toestemming": toestemming.get("marketingState") or "",
                "toestemming_niveau": toestemming.get("marketingOptInLevel") or "",
                "toestemming_datum": (toestemming.get("consentUpdatedAt") or "")[:10],
                "sms_toestemming": (n.get("smsMarketingConsent") or {}).get("marketingState") or "",
                "bestellingen": n.get("numberOfOrders") or 0,
                "besteed_eur": (n.get("amountSpent") or {}).get("amount") or "0",
                "land": adres.get("country") or "",
                "landcode": adres.get("countryCodeV2") or "",
                "stad": adres.get("city") or "",
                "taal": n.get("locale") or "",
                "klant_sinds": (n.get("createdAt") or "")[:10],
                "laatste_order": laatste.get("name") or "",
                "laatste_order_datum": (laatste.get("createdAt") or "")[:10],
                "tags": ", ".join(n.get("tags") or []),
            })
        print(f"  ronde {ronde + 1}: {len(uit)} klanten opgehaald", end="\r", flush=True)
        if not d["pageInfo"]["hasNextPage"]:
            break
        cursor = d["pageInfo"]["endCursor"]
    print()
    return uit


def samenvatting(rijen: list[dict]) -> None:
    abonnees = [r for r in rijen if r["email_toestemming"] == "SUBSCRIBED"]
    metmail = [r for r in rijen if r["email"]]
    kopers = [r for r in rijen if int(r["bestellingen"] or 0) > 0]
    print(f"\n  totaal            {len(rijen):>7,}".replace(",", "."))
    print(f"  met e-mailadres   {len(metmail):>7,}".replace(",", "."))
    print(f"  toestemming JA    {len(abonnees):>7,}".replace(",", "."))
    print(f"  heeft besteld     {len(kopers):>7,}".replace(",", "."))
    if kopers:
        besteed = sum(float(r["besteed_eur"] or 0) for r in kopers)
        print(f"  samen besteed     € {besteed:>9,.2f}".replace(",", "@").replace(".", ",").replace("@", "."))
        print(f"  gemiddeld         € {besteed / len(kopers):>9,.2f}".replace(",", "@").replace(".", ",").replace("@", "."))
    landen = Counter(r["land"] for r in rijen if r["land"])
    print("\n  landen (top 8):")
    for land, n in landen.most_common(8):
        print(f"    {land[:26]:<26} {n:>6,}".replace(",", "."))
    status = Counter(r["email_toestemming"] or "(leeg)" for r in rijen)
    print("\n  toestemmingsstatus:")
    for s, n in status.most_common():
        print(f"    {s:<26} {n:>6,}".replace(",", "."))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--doen", action="store_true", help="ook echt wegschrijven")
    a = p.parse_args()

    print("Klantenbestand ophalen uit Shopify (alleen lezen)…")
    rijen = haal_alles()
    samenvatting(rijen)

    if not a.doen:
        print("\nNiets opgeslagen. Draai opnieuw met --doen om het bestand weg te schrijven.")
        return 0

    map_ = os.path.join(config.DATA_DIR, "export")
    os.makedirs(map_, exist_ok=True)
    csv_pad = os.path.join(map_, "klanten.csv")
    json_pad = os.path.join(map_, "klanten.json")

    velden = list(rijen[0].keys()) if rijen else []
    with open(csv_pad, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=velden, delimiter=";")
        w.writeheader()
        w.writerows(rijen)
    with open(json_pad, "w", encoding="utf-8") as f:
        json.dump(rijen, f, ensure_ascii=False, indent=1)
    for pad in (csv_pad, json_pad):
        os.chmod(pad, 0o600)

    print(f"\n  {csv_pad}")
    print(f"  {json_pad}")
    print(f"  {os.path.getsize(csv_pad) // 1024} kB, rechten 600 (alleen jij kunt erbij)")
    print("\nDit zijn persoonsgegevens van ruim twintigduizend mensen. De map data/ staat in")
    print(".gitignore, dus het gaat niet mee naar GitHub. Niet doorsturen of ergens uploaden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
