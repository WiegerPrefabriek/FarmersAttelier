"""Registreert de Shopify-webhooks op onze publieke URL (na het koppelen van Shopify).

    PUBLIC_BASE_URL=https://xxxx.trycloudflare.com ./.venv/bin/python scripts/shopify_webhooks_registreren.py

De URL moet publiek HTTPS zijn. Lokaal: start eerst  cloudflared tunnel --url http://127.0.0.1:8800
en gebruik de URL die dat geeft. Bij een vaste server: de echte domeinnaam.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from app.channels.shopify_webhooks import TOPICS  # noqa: E402
from app.integrations import shopify  # noqa: E402


def main() -> int:
    basis = os.environ.get("PUBLIC_BASE_URL") or config.secret("app", "public_base_url")
    if not basis or not basis.startswith("https://"):
        print("Zet PUBLIC_BASE_URL (https://…) als env-var of in .secrets.json onder app.public_base_url.")
        return 1
    c = shopify.client()
    if not c.configured:
        print("Shopify is niet geconfigureerd (zie OPENSTAANDE_ZAKEN.md §2).")
        return 1
    uri = basis.rstrip("/") + "/webhooks/shopify"
    for topic in TOPICS:
        try:
            r = c.create_webhook(topic, uri)
            fouten = (r.get("webhookSubscriptionCreate") or {}).get("userErrors") or []
            print(f"  {topic:28s} {'OK' if not fouten else 'FOUT: ' + fouten[0].get('message', '?')}")
        except shopify.ShopifyError as fout:
            print(f"  {topic:28s} FOUT: {fout}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
