"""Centrale configuratie voor Farmers Atelier Support.

Eén plek voor paden, poorten en geheimen. Geheimen staan in `.secrets.json`
(gitignored); `.secrets.json.example` laat zien welke sleutels er bestaan.
Ontbreekt een geheim, dan draait dat onderdeel in mock-modus en zegt de app dat
duidelijk in het dashboard — niets faalt stil.
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "support.db")
KB_DIR = os.path.join(ROOT, "kb")
STATIC_DIR = os.path.join(ROOT, "static")
SECRETS_PATH = os.path.join(ROOT, ".secrets.json")

POORT = int(os.environ.get("POORT", "8800"))
BIND = os.environ.get("BIND", "127.0.0.1")

BRAND = "Farmers Atelier"
SUPPORT_EMAIL_FALLBACK = "support@farmersatelier.nl"

# Claude-model voor triage, concepten en de controle-stap.
AI_MODEL = os.environ.get("FA_AI_MODEL", "claude-opus-5")

# Vensters waarbinnen een nieuw klantbericht bij een bestaand gesprek hoort
# (Gorgias: 10 dagen e-mail, 3 dagen social/chat).
THREAD_WINDOW_DAYS = {"email": 10, "instagram": 3, "facebook": 3, "tiktok": 3, "shopify": 10}


def testmodus() -> bool:
    """Draait dit een test? Dan mag niets naar buiten.

    Op 28-09-2026 stuurde de testsuite vijf echte e-mails vanuit
    info@farmersatelier.com naar het verzonnen adres sophie@test.nl. De tests
    gebruikten wel een eigen database, maar lazen gewoon de echte `.secrets.json`
    — dus zodra Outlook gekoppeld was, verstuurde `send_reply` in een test ook
    werkelijk post. Met deze vlag geeft `load_secrets()` niets terug en valt alles
    terug op mock: geen mail, geen Shopify-aanroep, geen AI-kosten.
    """
    return os.environ.get("FA_TESTMODUS") == "1"


def load_secrets() -> dict:
    """Leest .secrets.json; ontbreekt het bestand dan een lege dict (mock-modus)."""
    if testmodus():
        return {}
    try:
        with open(SECRETS_PATH, encoding="utf-8") as bestand:
            return json.load(bestand)
    except FileNotFoundError:
        return {}
    except ValueError as fout:
        raise SystemExit(f".secrets.json is geen geldige JSON: {fout}")


# Waarden die in .secrets.json.example staan als voorbeeld. Blijven ze staan, dan is
# het veld in feite leeg — maar ziet elke check hem als ingevuld. Dat is precies wat
# op 28-09-2026 misging: "sk-ant-..." bleef staan, de statuscheck zei dat Claude
# klaarstond, en pas bij het verwerken van 41 mails bleek de sleutel ongeldig.
PLAATSHOUDERS = ("sk-ant-...", "verzin-hier-een-lang-willekeurig-woord", "...", "xxx", "<vul in>")


def is_plaatshouder(waarde) -> bool:
    if not isinstance(waarde, str):
        return False
    schoon = waarde.strip()
    return schoon in PLAATSHOUDERS or schoon.endswith("...") or schoon.startswith("<")


def secret(*pad: str, default=None):
    """secret("shopify", "admin_token") -> waarde of default. Env-vars gaan voor.

    Een onveranderde voorbeeldwaarde telt als leeg: beter geen sleutel dan een
    sleutel waarvan je pas merkt dat hij nep is als het misgaat.
    """
    env_naam = "FA_" + "_".join(p.upper() for p in pad)
    if os.environ.get(env_naam):
        return os.environ[env_naam]
    waarde = load_secrets()
    for stap in pad:
        if not isinstance(waarde, dict):
            return default
        waarde = waarde.get(stap)
    if waarde in (None, "") or is_plaatshouder(waarde):
        return default
    return waarde


def anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or secret("anthropic", "api_key")


def integratie_status() -> dict:
    """Welke koppelingen zijn echt geconfigureerd? Voor het dashboard en de logs.

    Shopify kan op twee manieren: een oud `admin_token` van vóór 2026, of een
    client id + secret waarmee de app zelf een token ophaalt. Alleen op het
    admin_token kijken zou een correct ingestelde nieuwe app als 'niet gekoppeld'
    tonen.
    """
    shopify_ok = bool(secret("shopify", "store_domain")) and bool(
        secret("shopify", "admin_token")
        or (secret("shopify", "client_id") and secret("shopify", "client_secret")))
    ms_modus = secret("microsoft", "mode", default="application")
    microsoft_ok = bool(
        secret("microsoft", "tenant_id") and secret("microsoft", "client_id")
        and secret("microsoft", "postbus")
        and (secret("microsoft", "client_secret") if ms_modus == "application"
             else secret("microsoft", "refresh_token")))
    return {
        "anthropic": bool(anthropic_key()),
        "shopify": shopify_ok,
        "microsoft": microsoft_ok,
        "gmail": bool(secret("gmail", "refresh_token")),
        "meta": bool(secret("meta", "page_access_token")),
        "tiktok": bool(secret("tiktok", "access_token")),
        "fulfillment": bool(secret("fulfillment", "api_key")),
    }
