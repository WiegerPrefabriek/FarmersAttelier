# Handleiding — Farmers Atelier Customer Service

Voor Wieger, en voor de Claude-sessie op je andere laptop. Dit bestand vertelt wat er
is gebouwd, hoe je het draait, en waar je verder gaat.

## 1. Wat is dit

Een eigen klantenservice-platform voor Farmers Atelier, functioneel nagebouwd naar
Gorgias: één inbox voor e-mail, Instagram, Facebook, TikTok en Shopify, met een
AI-agent die elk bericht analyseert, de Shopify-order erbij zoekt, een conceptantwoord
schrijft en alleen de zaken naar ons doorzet waar echt een mens voor nodig is.

Stand 25-09-2026: **eerste werkende lokale versie, volledig op nepdata.** Geen enkele
externe koppeling is nog actief; elk onderdeel schakelt zelf over op "echt" zodra de
sleutels in `.secrets.json` staan. Wat daarvoor nodig is staat in
`OPENSTAANDE_ZAKEN.md`.

## 2. Draaien op een (andere) laptop

Vereist: macOS of Linux met Python 3.9 of hoger en git. Geen Node, geen Docker.

```bash
git clone <repo-url> farmers-atelier-support
cd farmers-atelier-support
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python mock/generate.py        # nepdata: 20 klanten, 30 orders, 54 gesprekken
./.venv/bin/python run.py                  # open http://127.0.0.1:8800/
```

Uit de zip in plaats van git: uitpakken, dan dezelfde stappen vanaf `python3 -m venv`.

Tests: `./.venv/bin/python -m unittest -v` (16 tests).
Nepdata opnieuw: `./.venv/bin/python mock/generate.py --reset`.
Andere poort: `POORT=8801 ./.venv/bin/python run.py`.

Wat er NIET in git of de zip zit (bewust): `.venv/` (maak je zelf), `data/` (de
database, ontstaat vanzelf), `.secrets.json` (sleutels; kopieer `.secrets.json.example`).

## 3. Rondleiding door de app

| Tab | Wat je ziet |
|---|---|
| **Inbox** | Links de views (Alle, Nieuw, Mijn tickets, AI bezig, AI opgelost, Mens nodig, High priority, Goedkeuring nodig, per categorie, per kanaal). Midden het gesprek met bovenaan de AI-analyse en onderaan het conceptantwoord: **Versturen**, **Versturen & sluiten**, tekst aanpassen, **AI opnieuw**, **Interne notitie**, **Escaleren**, **Snoozen**, **Sluiten**, bij comments **Privé antwoorden (DM)** en **Comment verbergen**, bij een order **Actie op #…** (annuleren, refund, adres, tag; wordt eerst een voorstel dat je goedkeurt). Rechts de klant, de Shopify-order met tracking en fulfillment-tijdlijn, eerdere orders en gesprekken, relevante kennis, logboek. |
| **Dashboard** | Vandaag, open, door AI afgehandeld, mens nodig, high priority, responstijd, AI-acceptatie; per kanaal, per categorie, backlog; **ACTIE NODIG**. Elk cijfer heeft een ⓘ met de formule. |
| **Leren** | Per categorie: hoeveel AI-concepten wij aanpasten en of de categorie klaar is voor automatisch antwoorden. Elk antwoord: concept naast verstuurd. Knop **Analyseer nu** laat Claude verbetervoorstellen doen (in mock-modus alleen tellingen). |
| **Regels** | ALS/DAN-regels, aan/uit, bewerken, nieuwe maken. |
| **Kennisbank** | De bestanden uit `kb/`. Alles met `TODO` gebruikt de AI niet als bron. |
| **Instellingen** | Automatiseringsniveau per categorie (1 analyseren → 5 workflow), AI-modus, auto-versturen, tone of voice, status van de koppelingen. |

Knop **+ Test** in de inbox laat een nepbericht binnenkomen via elk kanaal en toont wat
de pipeline ermee doet. Sneltoetsen: `j`/`k` volgend/vorig gesprek, `r` antwoorden,
`c` sluiten, `⌘+Enter` versturen.

## 4. Hoe de code in elkaar zit

```
run.py                    start de server (app/server.py)
config.py                 paden, poort, secrets-loader, koppelingsstatus
app/server.py             http.server + router, statische bestanden, SSE (/events), webhooks, achtergrondthread
app/api.py                alle JSON-endpoints (/api/…)
app/pipeline.py           bericht binnen → klant → gesprek → Shopify → AI → regels → niveau → concept
app/service.py            medewerker-acties: versturen, notitie, toewijzen, status, escaleren, acties goedkeuren
app/ai/prompts.py         systemprompt, instructies en JSON-schema's (analyse, concept, controle, leren)
app/ai/agent.py           ClaudeAgent (echt) en MockAgent (trefwoorden); get_agent() kiest
app/rules.py              rules-engine + standaardregels
app/taxonomy.py           intents, prioriteiten, niveaus, benodigde info per intent
app/knowledge.py          kb/*.md → database + zoeken
app/stats.py              dashboardcijfers (met ⓘ-uitleg) en leeroverzicht
app/db.py, schema.sql     SQLite-laag en schema
app/channels/             email_gmail, email_imap, email_common, meta, tiktok, shopify_webhooks, dispatch
app/integrations/         shopify (GraphQL 2026-07 + cache), fulfillment (adapter)
static/                   index.html, app.js, style.css — geen build-stap
kb/                       kennisbank (Markdown)
mock/generate.py          nepdata
scripts/                  gmail_koppelen.py, shopify_webhooks_registreren.py
tests/                    unittest
docs/onderzoek/           de vier onderzoeksrapporten
BOUWPLAN.md               keuzes en fases
OPENSTAANDE_ZAKEN.md      wat Wieger nog moet aanleveren, stap voor stap
```

Een bericht doorloopt altijd dezelfde weg (`app/pipeline.py`): kanaaladapter maakt er één
standaardvorm van → klant herkennen (e-mail eerst, dan social-ID) → gesprek vinden
(zelfde thread, anders open gesprek binnen 3 dagen social / 10 dagen e-mail) →
Shopify-orders ophalen en `#nummers` uit de tekst → AI-analyse → regels → niveau van die
categorie → concept + controle → in de inbox, of automatisch verstuurd bij niveau 3 met
goedgekeurde controle en `auto_send_enabled` aan.

## 5. Voor de Claude-sessie die hieraan verder werkt

- Lees eerst `BOUWPLAN.md` en `OPENSTAANDE_ZAKEN.md`, dan dit bestand.
- Werkwijze van Wieger: alleen Python-stdlib-server + SQLite + één HTML-pagina, geen
  frameworks, geen Node, geen Docker. Secrets uitsluitend in `.secrets.json`
  (gitignored). Nooit tokens in chat of code. Elk dashboardcijfer krijgt een ⓘ met formule.
- Volgende bouwstappen in volgorde: (1) Anthropic-sleutel → echte AI testen op de
  nepdata en de prompts bijstellen; (2) Shopify-koppeling (lezen) live; (3) e-mailkanaal
  live; (4) Meta-app + webhooks via `cloudflared tunnel`; (5) Shopify-acties met
  goedkeuring live; (6) niveau 3 aanzetten per veilige categorie op basis van de leerdata.
- Test altijd met `python -m unittest` en met `mock/generate.py --reset` + de app in de
  browser. De Browser-pane kan de venv niet zelf starten; start de server via een
  terminal en open de URL.
- Python 3.9 werkt; de nieuwste `anthropic`-SDK (1.x) vereist 3.10+. Na een upgrade naar
  3.12: `requirements.txt` bijwerken (`anthropic>=1.8`).
