#!/usr/bin/env python3
"""Leest Verzonden items uit Outlook en koppelt ze aan de bestaande gesprekken.

Zonder dit ziet het systeem alleen wat er binnenkomt, nooit wat wij terugstuurden.
Elk gesprek lijkt daardoor onbeantwoord en blijft openstaan — ook als er al twee
keer een antwoord de deur uit is gegaan. Precies dat was het geval bij Marvin
Born: twee antwoorden verstuurd op 5 en 6 september, en zijn ticket stond nog
steeds op kritiek.

    ./.venv/bin/python scripts/verzonden_importeren.py           # tonen
    ./.venv/bin/python scripts/verzonden_importeren.py --doen    # koppelen
    ./.venv/bin/python scripts/verzonden_importeren.py --doen --sluiten

Met --sluiten worden gesprekken waarin wij als laatste iets stuurden ook echt op
afgehandeld gezet. Die keuze staat los, want "er is geantwoord" is niet altijd
hetzelfde als "hiermee is het klaar".
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.channels import email_microsoft as ms  # noqa: E402
from app.channels.email_common import html_to_text, strip_quotes  # noqa: E402


def verzonden(maximaal: int = 100) -> list[dict]:
    d = ms._get(f"{ms._basis()}/mailFolders/sentitems/messages", **{
        "$top": str(maximaal), "$orderby": "sentDateTime desc",
        "$select": "id,internetMessageId,conversationId,subject,body,bodyPreview,"
                   "toRecipients,sentDateTime"})
    return d.get("value", [])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--doen", action="store_true")
    p.add_argument("--sluiten", action="store_true",
                   help="gesprekken waarin wij als laatste stuurden op afgehandeld zetten")
    a = p.parse_args()

    if not ms.configured():
        return print("Outlook is niet gekoppeld.") or 1

    gekoppeld = overgeslagen = gesloten = 0
    for b in verzonden():
        ontvangers = [((r.get("emailAddress") or {}).get("address") or "").lower()
                      for r in (b.get("toRecipients") or [])]
        ontvangers = [x for x in ontvangers if x]
        if not ontvangers:
            continue

        # Zoek het gesprek van deze klant. Eerst op de Outlook-draad, anders op
        # het e-mailadres — dat laatste dekt ook mail die buiten het systeem om
        # verstuurd is.
        conv = db.one("""SELECT c.id, c.status FROM conversations c
                         WHERE c.external_thread_id = ? LIMIT 1""", (b.get("conversationId"),))
        if not conv:
            conv = db.one("""SELECT c.id, c.status FROM conversations c
                             JOIN customers k ON k.id = c.customer_id
                             WHERE lower(k.email) = ? ORDER BY c.id DESC LIMIT 1""", (ontvangers[0],))
        if not conv:
            overgeslagen += 1
            continue

        mid = b.get("internetMessageId") or b.get("id")
        if db.one("SELECT id FROM messages WHERE external_id = ?", (mid,)):
            continue

        tekst = (b.get("body") or {}).get("content") or b.get("bodyPreview") or ""
        if ((b.get("body") or {}).get("contentType") or "").lower() == "html":
            tekst = html_to_text(tekst)

        print(f"  {'+' if a.doen else ' '} naar {ontvangers[0][:30]:30s} -> gesprek #{conv['id']}"
              f"  {(b.get('subject') or '')[:36]}")
        if not a.doen:
            gekoppeld += 1
            continue

        db.insert("messages", {
            "conversation_id": conv["id"], "direction": "out", "kind": "public",
            "author_type": "agent", "author_name": "Farmers Atelier",
            "body_text": strip_quotes(tekst).strip()[:8000],
            "external_id": mid, "status": "sent", "sent_at": b.get("sentDateTime"),
            "source": db.dumps({"herkomst": "Outlook Verzonden items"}),
        })
        db.update("conversations", conv["id"], {
            "first_response_at": db.one("SELECT first_response_at FROM conversations WHERE id = ?",
                                        (conv["id"],))["first_response_at"] or b.get("sentDateTime"),
            "last_message_at": b.get("sentDateTime"),
        })
        gekoppeld += 1

    print(f"\n{gekoppeld} verzonden berichten gekoppeld, {overgeslagen} zonder bijpassend gesprek.")

    if a.doen and a.sluiten:
        # Een gesprek waarin het laatste bericht van ons is, is beantwoord.
        for c in db.rows("SELECT id FROM conversations WHERE status = 'open'"):
            laatste = db.one("SELECT direction FROM messages WHERE conversation_id = ? "
                             "ORDER BY id DESC LIMIT 1", (c["id"],))
            if laatste and laatste["direction"] == "out":
                db.update("conversations", c["id"], {
                    "status": "closed", "ai_status": "closed", "needs_human": 0,
                    "closed_at": db.now(),
                    "summary": "Afgehandeld: wij hebben als laatste geantwoord."})
                db.execute("UPDATE ai_drafts SET status = 'superseded' "
                           "WHERE conversation_id = ? AND status = 'pending'", (c["id"],))
                gesloten += 1
        print(f"{gesloten} gesprekken gesloten omdat wij als laatste antwoordden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
