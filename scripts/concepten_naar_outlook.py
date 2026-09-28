#!/usr/bin/env python3
"""Zet de AI-concepten uit de inbox als echte concepten in Outlook.

Zo hoef je niet in twee schermen te werken: je opent Outlook, ziet per klantvraag
een concept-antwoord klaarstaan in dezelfde draad, leest het na en drukt zelf op
Verzenden. Er wordt langs deze weg nooit iets automatisch verstuurd.

    ./.venv/bin/python scripts/concepten_naar_outlook.py                 # tonen
    ./.venv/bin/python scripts/concepten_naar_outlook.py --doen          # aanmaken
    ./.venv/bin/python scripts/concepten_naar_outlook.py --doen --intent other_shop

Een gesprek waarvoor al een concept in Outlook staat wordt overgeslagen; dat wordt
bijgehouden in de gebeurtenissen van het gesprek, dus twee keer draaien levert geen
dubbele concepten op.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.channels import email_microsoft as ms  # noqa: E402

GEBEURTENIS = "outlook_concept"


def al_gedaan(conversation_id: int) -> bool:
    return bool(db.one(
        "SELECT id FROM events WHERE conversation_id = ? AND type = ? LIMIT 1",
        (conversation_id, GEBEURTENIS)))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--doen", action="store_true", help="de concepten echt aanmaken")
    p.add_argument("--intent", default=None, help="alleen deze categorie, bv. other_shop")
    p.add_argument("--maximaal", type=int, default=100)
    a = p.parse_args()

    if not ms.configured():
        return print("Outlook is niet gekoppeld — vul 'microsoft' in .secrets.json.") or 1

    # Eén concept per gesprek, het nieuwste. Zonder deze beperking levert een
    # gesprek met twee openstaande concepten ook twee Outlook-concepten op, en dat
    # stond er bij de eerste keer dubbel in.
    sql = """SELECT c.id, c.subject, c.intent, c.order_name,
                    k.name AS klant, k.email AS email,
                    d.id AS draft_id, d.body AS concept
             FROM conversations c
             JOIN ai_drafts d ON d.id = (
                   SELECT id FROM ai_drafts x
                   WHERE x.conversation_id = c.id AND x.status = 'pending'
                   ORDER BY x.id DESC LIMIT 1)
             LEFT JOIN customers k ON k.id = c.customer_id
             WHERE c.channel = 'email' AND c.status = 'open'"""
    args: list = []
    if a.intent:
        sql += " AND c.intent = ?"
        args.append(a.intent)
    sql += " ORDER BY c.last_message_at DESC LIMIT ?"
    args.append(a.maximaal)

    rijen = [r for r in db.rows(sql, tuple(args)) if not al_gedaan(r["id"])]
    print(f"{len(rijen)} gesprekken met een concept dat nog niet in Outlook staat\n")
    if not rijen:
        print("Niets te doen. Staat de inbox nog leeg, importeer dan eerst de mail:")
        print("  ./.venv/bin/python scripts/mail_importeren.py --doen")
        return 0

    for r in rijen:
        print(f"  #{r['id']:<4} {(r['klant'] or r['email'] or '?')[:28]:28s} "
              f"{(r['intent'] or '-')[:18]:18s} {(r['subject'] or '')[:40]}")

    if not a.doen:
        print("\nDraai opnieuw met --doen om de concepten in Outlook te zetten.")
        return 0

    gelukt = mislukt = 0
    for r in rijen:
        # Het laatste binnengekomen bericht van de klant: daar antwoorden we op,
        # zodat het concept in de juiste draad belandt.
        laatste = db.one(
            "SELECT external_id FROM messages WHERE conversation_id = ? AND direction = 'in' "
            "AND external_id IS NOT NULL ORDER BY id DESC LIMIT 1", (r["id"],))
        if not laatste or not laatste["external_id"]:
            print(f"  ! #{r['id']}: geen bericht-id, overgeslagen")
            mislukt += 1
            continue
        uit = ms.maak_concept(laatste["external_id"], r["concept"])
        if uit.get("ok"):
            gelukt += 1
            db.insert("events", {"conversation_id": r["id"], "type": GEBEURTENIS,
                                 "actor_type": "system",
                                 "data": db.dumps({"concept_id": uit.get("concept_id"),
                                                   "draft_id": r["draft_id"]})})
            print(f"  + #{r['id']} concept staat in Outlook")
        else:
            mislukt += 1
            print(f"  ! #{r['id']}: {uit.get('reden')}")

    print(f"\n{gelukt} concepten klaargezet, {mislukt} mislukt.")
    print("Ze staan in Outlook onder Concepten, in de draad van de klant. "
          "Niets is verstuurd — dat doe je zelf.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
