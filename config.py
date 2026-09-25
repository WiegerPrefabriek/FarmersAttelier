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


def load_secrets() -> dict:
    """Leest .secrets.json; ontbreekt het bestand dan een lege dict (mock-modus)."""
    try:
        with open(SECRETS_PATH, encoding="utf-8") as bestand:
            return json.load(bestand)
    except FileNotFoundError:
        return {}
    except ValueError as fout:
        raise SystemExit(f".secrets.json is geen geldige JSON: {fout}")


def secret(*pad: str, default=None):
    """secret("shopify", "admin_token") -> waarde of default. Env-vars gaan voor."""
    env_naam = "FA_" + "_".join(p.upper() for p in pad)
    if os.environ.get(env_naam):
        return os.environ[env_naam]
    waarde = load_secrets()
    for stap in pad:
        if not isinstance(waarde, dict):
            return default
        waarde = waarde.get(stap)
    return waarde if waarde not in (None, "") else default


def anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or secret("anthropic", "api_key")


def integratie_status() -> dict:
    """Welke koppelingen zijn echt geconfigureerd? Voor het dashboard en de logs."""
    return {
        "anthropic": bool(anthropic_key()),
        "shopify": bool(secret("shopify", "admin_token") and secret("shopify", "store_domain")),
        "gmail": bool(secret("gmail", "refresh_token")),
        "meta": bool(secret("meta", "page_access_token")),
        "tiktok": bool(secret("tiktok", "access_token")),
        "fulfillment": bool(secret("fulfillment", "api_key")),
    }
