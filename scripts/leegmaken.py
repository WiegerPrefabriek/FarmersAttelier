#!/usr/bin/env python3
"""Haalt alle gesprekken, klanten en orders uit de database.

Bedoeld om van nepdata naar echte data te gaan: wat hier weg gaat komt straks
terug uit Outlook en Shopify. Wat blíjft staan is alles wat jij hebt ingesteld —
regels, macro's, kennisbank, automatiseringsniveaus en gebruikers. Die zijn niet
nep en zou je anders opnieuw moeten invoeren.

    ./.venv/bin/python scripts/leegmaken.py            # laat zien wat er weg zou gaan
    ./.venv/bin/python scripts/leegmaken.py --doen     # voert het uit

Er wordt altijd eerst een kopie van de database gemaakt.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

# Volgorde is niet willekeurig: eerst wat naar iets anders verwijst.
WEG = [
    "learning_records", "ai_drafts", "ai_analyses", "pending_actions",
    "messages", "conversations", "fulfillment_events", "orders",
    "customer_identities", "customers", "products", "inbound_queue", "events",
]
# Dit is geen nepdata maar instelwerk, en blijft dus staan.
BLIJFT = ["rules", "macros", "knowledge_articles", "settings", "users"]


def tel(conn, tabel: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {tabel}").fetchone()[0]
    except sqlite3.OperationalError:
        return -1


def main() -> int:
    doen = "--doen" in sys.argv
    if not os.path.exists(config.DB_PATH):
        print("Geen database gevonden — er valt niets leeg te maken.")
        return 0

    conn = sqlite3.connect(config.DB_PATH)
    print("Gaat weg:")
    totaal = 0
    for t in WEG:
        n = tel(conn, t)
        if n < 0:
            continue
        totaal += n
        print(f"  {t:22s} {n:5d}")
    print("\nBlijft staan:")
    for t in BLIJFT:
        n = tel(conn, t)
        if n >= 0:
            print(f"  {t:22s} {n:5d}")

    if not doen:
        print(f"\n{totaal} regels zouden verdwijnen. Draai opnieuw met --doen om het echt te doen.")
        conn.close()
        return 0

    conn.close()
    kopie = f"{config.DB_PATH}.voor-leegmaken-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(config.DB_PATH, kopie)
    print(f"\nKopie gemaakt: {os.path.basename(kopie)}")

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    for t in WEG:
        try:
            conn.execute(f"DELETE FROM {t}")
        except sqlite3.OperationalError:
            pass
    # De teller van AUTOINCREMENT ook terug, anders begint het eerste echte
    # gesprek op nummer 55 en lijkt het alsof er iets weg is.
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN (%s)" % ",".join("?" * len(WEG)), WEG)
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    print("Leeggemaakt. De inbox is nu leeg tot er echte berichten binnenkomen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
