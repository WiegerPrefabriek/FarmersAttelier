#!/usr/bin/env python3
"""Haalt bestaande post uit Outlook en laat de pipeline er gesprekken van maken.

De achtergrondlus pakt alleen nieuwe post in het Postvak IN op. Dit script is voor
de eenmalige inhaalslag: ook het archief, en desgewenst de ongewenste map.

    ./.venv/bin/python scripts/mail_importeren.py --toon          # alleen tonen
    ./.venv/bin/python scripts/mail_importeren.py --doen          # inbox + archief
    ./.venv/bin/python scripts/mail_importeren.py --doen --spam   # ook ongewenst
    ./.venv/bin/python scripts/mail_importeren.py --doen --vanaf 2026-08-01

Elk bericht gaat door dezelfde weg als een nieuw bericht: klant herkennen, gesprek
zoeken, AI laten analyseren, concept schrijven. Berichten die al binnen zijn worden
overgeslagen op hun external_id, dus twee keer draaien levert geen dubbele
gesprekken op.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from app import db, pipeline  # noqa: E402
from app.channels import email_microsoft as ms  # noqa: E402
from app.channels.email_common import html_to_text, strip_quotes  # noqa: E402

MAPPEN = {"inbox": "Postvak IN", "archive": "Archief", "junkemail": "Ongewenst"}

# Afzenders die nooit een klant zijn. Deze eruit houden scheelt AI-werk en houdt de
# inbox leesbaar; het zijn nieuwsbrieven, platformmeldingen en koude acquisitie.
RUIS = re.compile(
    r"(no-?reply|noreply|newsletter|notifications?@|marketing@|pinmail|pinbot|testflight|"
    r"@microsoft\.com|@klaviyo|@yotpo|@tailwindapp|@tryatria|@triplewhale|@pinterest|"
    r"@tiktok\.com|@trustpilot|@paypal|@billink|@shopifyemail|@godaddy|@trengo|@wonderment|"
    r"@instant\.so|@itsperfect|@wetracked|@returnless|@gotrusted|@apple\.com|@service\.tiktok)", re.I)


def berichten_uit(mapnaam: str, vanaf: str | None, maximaal: int = 200) -> list[dict]:
    params = {"$top": str(maximaal), "$orderby": "receivedDateTime desc",
              "$select": "id,conversationId,internetMessageId,subject,bodyPreview,body,"
                         "from,receivedDateTime,isDraft"}
    if vanaf:
        params["$filter"] = f"receivedDateTime ge {vanaf}T00:00:00Z"
    return ms._get(f"{ms._basis()}/mailFolders/{mapnaam}/messages", **params).get("value", [])


def naar_inbound(b: dict, mapnaam: str) -> dict | None:
    """Eén Graph-bericht naar de vorm die de pipeline verwacht.

    Gebruikt bewust dezelfde functie als het kanaal zelf, zodat import en de
    dagelijkse ronde niet uit elkaar kunnen lopen.
    """
    adres = ((b.get("from") or {}).get("emailAddress") or {})
    van = (adres.get("address") or "").lower()
    if not van or van == ms.afzender().lower():
        return None
    inhoud = (b.get("body") or {}).get("content") or b.get("bodyPreview") or ""
    if ((b.get("body") or {}).get("contentType") or "").lower() == "html":
        inhoud = html_to_text(inhoud)
    inb = ms.naar_inbound_dict(b, van, adres.get("name") or "", inhoud)
    inb["external_ref"]["map"] = MAPPEN.get(mapnaam, mapnaam)
    return inb


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--doen", action="store_true", help="echt importeren")
    p.add_argument("--toon", action="store_true", help="alleen laten zien")
    p.add_argument("--spam", action="store_true", help="ook de map Ongewenst meenemen")
    p.add_argument("--alles", action="store_true", help="ook nieuwsbrieven en acquisitie")
    p.add_argument("--vanaf", default=None, help="alleen vanaf deze datum (JJJJ-MM-DD)")
    a = p.parse_args()

    if not ms.configured():
        return print("Outlook is niet gekoppeld — vul 'microsoft' in .secrets.json.") or 1
    proef = ms.test()
    if not proef.get("ok"):
        return print(f"Outlook antwoordt niet: {proef.get('reden')}") or 1
    print(f"Postbus {proef['postbus']} — {proef['berichten']} in {proef['map']}\n")

    mappen = ["inbox", "archive"] + (["junkemail"] if a.spam else [])
    kandidaten, overgeslagen = [], 0
    for m in mappen:
        try:
            ruw = berichten_uit(m, a.vanaf)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {m}: {e}")
            continue
        for b in ruw:
            if b.get("isDraft"):
                continue
            inb = naar_inbound(b, m)
            if not inb:
                continue
            if not a.alles and RUIS.search(inb["sender"]["email"]):
                overgeslagen += 1
                continue
            kandidaten.append(inb)
        print(f"  {MAPPEN.get(m, m):12s} {len(ruw):4d} berichten")

    kandidaten.sort(key=lambda x: x.get("sent_at") or "")
    print(f"\n{len(kandidaten)} te importeren, {overgeslagen} overgeslagen als nieuwsbrief/acquisitie")

    if a.toon or not a.doen:
        for k in kandidaten:
            print(f"  {(k['sent_at'] or '')[:10]}  {k['sender']['email'][:34]:34s}  {k['subject'][:50]}")
        print("\nDraai opnieuw met --doen om te importeren.")
        return 0

    nieuw = bestond = mislukt = 0
    for k in kandidaten:
        if db.one("SELECT id FROM messages WHERE external_id = ?", (k["external_message_id"],)):
            bestond += 1
            continue
        try:
            pipeline.ingest(k)
            nieuw += 1
            print(f"  + {k['sender']['email'][:30]:30s} {k['subject'][:44]}")
        except Exception as e:  # noqa: BLE001
            mislukt += 1
            print(f"  ! {k['sender']['email'][:30]:30s} {str(e)[:70]}")

    print(f"\n{nieuw} nieuw, {bestond} stond er al, {mislukt} mislukt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
