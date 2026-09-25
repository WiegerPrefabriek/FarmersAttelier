# Farmers Atelier · Customer Service

Eén eigen klantenservice-omgeving voor Farmers Atelier: alle klantvragen (e-mail,
Instagram, Facebook, TikTok, Shopify) in één inbox, met een AI-agent die elk bericht
analyseert, de Shopify-order erbij zoekt, een conceptantwoord schrijft en alleen de
zaken naar ons doorzet waarvoor echt een mens nodig is. Functioneel gemodelleerd naar
Gorgias (zie `docs/onderzoek/`), gebouwd als kleine Python-app die lokaal op een Mac
draait.

## Snel starten

```bash
cd farmers-atelier-support
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python mock/generate.py        # 20 klanten, 30 orders, 54 gesprekken (nepdata)
./.venv/bin/python run.py                  # http://127.0.0.1:8800/
```

Zonder `.secrets.json` draait alles in **mock-modus**: de AI classificeert op
trefwoorden, Shopify komt uit de lokale cache, versturen wordt alleen gelogd. Zodra je
sleutels toevoegt (zie `OPENSTAANDE_ZAKEN.md`) schakelt elk onderdeel apart over op echt.

Tests: `./.venv/bin/python -m unittest -v`

## Wat zit erin

| Onderdeel | Waar | Wat |
|---|---|---|
| Inbox | `static/` | Views (Alle, Nieuw, Mijn, AI bezig, Mens nodig, High priority, per categorie, per kanaal), gesprek, AI-analyse, conceptantwoord met Versturen / Aanpassen / AI opnieuw / Notitie / Toewijzen / Escaleren / Snoozen / Sluiten, Shopify-zijbalk, acties met goedkeuring |
| Dashboard | tab Dashboard | Vandaag, responstijd, per kanaal, per categorie, AI-acceptatie, backlog, **ACTIE NODIG**; elk cijfer heeft een ⓘ met formule |
| Leren | tab Leren | Concept vs verstuurd per antwoord, per categorie de bewerkingsgraad, AI-analyse van onze correcties met verbetervoorstellen |
| Regels | tab Regels | ALS/DAN-regels (Gorgias-stijl), zelf aan te passen |
| Kennisbank | `kb/*.md` + tab Kennisbank | Retourbeleid, verzending, maten, producten, FAQ, tone of voice… Artikelen met `TODO` gebruikt de AI niet als bron |
| Instellingen | tab Instellingen | Automatiseringsniveau per categorie (1 analyseren → 5 workflow), AI-modus, auto-versturen, koppelingsstatus |
| AI-agent | `app/ai/` | Claude (`claude-opus-5`) met gestructureerde output: analyse → concept → controle (belooft het niets? klopt het met het beleid?). Mock-variant zonder sleutel |
| Pipeline | `app/pipeline.py` | Bericht binnen → klant herkennen → gesprek threaden → Shopify-orders → AI → regels → niveau → concept |
| Kanalen | `app/channels/` | E-mail (Gmail-API of IMAP/SMTP), Meta (Instagram/Facebook DM's + comments, verbergen, privé-antwoord), TikTok (comments), Shopify-webhooks, fulfillment-webhook |
| Shopify | `app/integrations/shopify.py` | GraphQL Admin API 2026-07: klanten, orders, tracking, refunds, retouren; acties (annuleren, refund, adres) alleen na goedkeuring |
| Database | `app/schema.sql` | SQLite in `data/support.db` (gitignored). Back-up = bestand kopiëren |

## Hoe een bericht loopt

```
kanaal → adapter → klant (e-mail eerst, dan social-ID) → gesprek (thread of venster 3/10 dagen)
  → Shopify: orders van de klant + #nummers uit de tekst
  → AI-analyse: categorie, prioriteit, sentiment, taal, ontbrekende info, mens nodig?
  → regels (ALS klacht+negatief DAN high + mens nodig, …)
  → niveau van de categorie: analyseren / concept / auto-antwoord / actie
  → AI-concept + controle → in de inbox (of automatisch verstuurd bij niveau 3 + controle ok)
  → wij: Versturen / Aanpassen / AI opnieuw → leerrecord (concept vs verstuurd)
```

## Webhooks lokaal testen

Meta en Shopify hebben een publieke HTTPS-URL nodig. Gratis en zonder account:

```bash
cloudflared tunnel --url http://127.0.0.1:8800
```

Gebruik de `https://….trycloudflare.com`-URL als webhook-adres (`/webhooks/meta`,
`/webhooks/shopify`, `/webhooks/fulfillment`).

## Mappen

```
app/            server, api, pipeline, service, rules, stats, knowledge, db, schema.sql
app/ai/         prompts + agent (Claude / mock)
app/channels/   e-mail, meta, tiktok, shopify-webhooks, dispatch
app/integrations/  shopify (GraphQL), fulfillment (adapter)
static/         index.html, app.js, style.css (geen build-stap)
kb/             kennisbank (Markdown)
mock/           generate.py (nepdata)
scripts/        gmail_koppelen.py, shopify_webhooks_registreren.py
tests/          unittest
docs/onderzoek/ de vier onderzoeksrapporten
```

Zie `BOUWPLAN.md` voor de keuzes en fases, en `OPENSTAANDE_ZAKEN.md` voor wat er nog
van Wieger nodig is.
