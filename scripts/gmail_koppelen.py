"""Eenmalig het support-Gmail-account koppelen (OAuth, zonder wachtwoord in een bestand).

Zelfde aanpak als bij het inkoopsysteem: je logt één keer in bij Google in je eigen
browser, geeft toestemming voor "mail lezen en versturen", en Google geeft een
refresh_token terug dat lokaal in `.secrets.json` komt (gitignored).

WAT JE ÉÉN KEER DOET
1. https://console.cloud.google.com → project (mag het bestaande zijn) → API's & services →
   Bibliotheek → "Gmail API" → Inschakelen.
2. OAuth-toestemmingsscherm: Extern, naam "Farmers Atelier Support", jouw e-mail, en bij
   Testgebruikers het support-account toevoegen (bv. support@farmersatelier.nl).
3. Inloggegevens → Inloggegevens maken → OAuth-client-ID → type "Desktop-app" → JSON
   downloaden → opslaan als  gmail_client.json  in de projectmap (gitignored).
4. ./.venv/bin/python scripts/gmail_koppelen.py  → browser opent → inloggen met het
   support-account → toestemming geven. Klaar.

Intrekken: https://myaccount.google.com/permissions
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(ROOT, "gmail_client.json")
SECRETS = os.path.join(ROOT, ".secrets.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send"]


def main() -> int:
    if not os.path.exists(CLIENT):
        print(f"gmail_client.json ontbreekt in {ROOT}. Zie de uitleg bovenaan dit bestand.")
        return 1
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Installeer eerst: ./.venv/bin/pip install google-auth-oauthlib")
        return 1
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline",
                                  authorization_prompt_message="\nEr opent een browser. Log in met het support-account en geef toestemming.\n",
                                  success_message="Gelukt. Je kunt dit tabblad sluiten.")
    if not creds.refresh_token:
        print("Google gaf geen refresh_token. Trek de toegang in op https://myaccount.google.com/permissions en probeer opnieuw.")
        return 1
    with open(CLIENT, encoding="utf-8") as f:
        kern = json.load(f).get("installed") or {}
    geheimen = {}
    if os.path.exists(SECRETS):
        with open(SECRETS, encoding="utf-8") as f:
            geheimen = json.load(f)
    afzender = input("Welk e-mailadres is het support-adres (afzender)? ").strip()
    geheimen["gmail"] = {"refresh_token": creds.refresh_token, "client_id": kern.get("client_id"),
                         "client_secret": kern.get("client_secret"), "afzender": afzender}
    with open(SECRETS, "w", encoding="utf-8") as f:
        json.dump(geheimen, f, ensure_ascii=False, indent=2)
    os.chmod(SECRETS, 0o600)
    print("Gekoppeld. Herstart de server; e-mail wordt nu elke 30 seconden opgehaald.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
