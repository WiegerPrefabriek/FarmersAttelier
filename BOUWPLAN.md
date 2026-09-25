# Bouwplan — Farmers Atelier Customer Service

Kort en begrijpelijk: wat we bouwen, waarom zo, en in welke volgorde. De volledige
onderbouwing staat in `docs/onderzoek/` (vier rapporten: Gorgias, concurrenten,
open source, API's).

## 1. Conclusie van het onderzoek in vijf zinnen

1. **Gorgias** is functioneel: één inbox met tickets per kanaal, klant-samenvoeging over
   kanalen, een Shopify-zijbalk met acties, intent/sentiment-detectie op elk klantbericht,
   een WHEN/IF/THEN-rules-engine, macro's, en een AI Agent die uit "guidance" + FAQ +
   orderdata antwoordt, eerst door een tweede model wordt gecontroleerd en anders
   overdraagt aan een mens.
2. **De beste andere systemen** (Intercom Fin, Zendesk, Gladly, Richpanel, Sierra, Ada)
   doen hetzelfde met dezelfde patronen: intent → procedure, confidence-gating,
   read-only acties automatisch, geldacties met goedkeuring, overdrachtsnotitie, leren
   van bewerkte concepten.
3. **Geen open-source helpdesk kan de basis zijn** op jouw Mac (allemaal Rails/PHP/Go +
   Postgres/Redis/Docker; Instagram-/Facebook-comments doet geen van hen; Helper is
   closed source geworden). We lenen ontwerp en API-kennis (vooral van Chatwoot) en
   bouwen zelf klein en in Python — precies zoals je andere tools.
4. **De API's zijn er**: Shopify GraphQL Admin API 2026-07 (custom app via Dev
   Dashboard), Meta Graph API voor Instagram-DM's/comments en Facebook Messenger/comments
   (één app, één Page-token; Human Agent-venster vereist App Review), e-mail via Gmail
   API of IMAP/SMTP.
5. **TikTok** organische DM's zijn zonder allowlist niet mogelijk; comments op eigen
   video's wel na een aanvraag; TikTok Shop-chat alleen als je daar verkoopt.

## 2. Wat we bouwen (en wat niet)

**Wel:** één lokale webapp (Python + SQLite + één HTML-pagina) met:
- inbox met views (Alle, Nieuw, Mijn tickets, AI bezig, AI opgelost, Mens nodig, High
  priority, per categorie, Social, Afgehandeld)
- gesprek in het midden, Shopify-klant/orderinfo rechts, AI-analyse + conceptantwoord
- knoppen: Versturen, Aanpassen, AI opnieuw, Interne notitie, Toewijzen, Escaleren,
  Snoozen, Sluiten
- AI-agent: analyseert → categoriseert → zoekt orderinfo → maakt concept → (later)
  antwoordt of handelt zelf, per categorie instelbaar in vijf niveaus
- acties met goedkeuring (annuleren, refund, adres wijzigen, comment verbergen)
- kennisbank uit Markdown-bestanden in `kb/`
- rules (ALS … DAN …) die je zelf kunt aanpassen
- dashboard met vandaag, per kanaal, per categorie, AI-acceptatie, ACTIE NODIG
- leren: elk verstuurd antwoord wordt met het AI-concept vergeleken en opgeslagen
- kanaaladapters: e-mail, Instagram, Facebook, TikTok (comments), Shopify-webhooks,
  fulfillment (adapter-interface), allemaal met mock-modus zolang er geen sleutels zijn

**Niet:** helpcenter-website, chatwidget, WhatsApp/SMS/telefoon, TikTok Shop, omzet-
rapportage, Flows, meerdere winkels, multi-tenant.

## 3. Techniek (past bij je andere tools)

| Onderdeel | Keuze | Waarom |
|---|---|---|
| Server | Python `http.server` (threading) + eigen router, één proces | Geen frameworks, geen Node, geen Docker; zelfde patroon als `serve.py` in je andere projecten (no-cache, Host-check, alleen webroot serveren) |
| Database | SQLite (WAL) + FTS5 | Zit in macOS; één bestand `data/support.db`; back-up = bestand kopiëren |
| Frontend | Eén `static/index.html` + `app.js` + `style.css`, vanilla JS, geen build | Zelfde werkwijze als je dashboards; werkt offline |
| AI | `anthropic`-SDK, model `claude-opus-5`, gestructureerde JSON-output, prompt caching op kennisbank | Officiële SDK; werkt op de huidige Python 3.9 (SDK 0.125) |
| Zonder API-sleutel | Mock-AI op trefwoorden + sjablonen | Hele app werkt lokaal vóór er sleutels zijn |
| Shopify | GraphQL Admin API 2026-07 via `requests`; custom app (client credentials) of legacy token | Geen bibliotheek nodig; ~15 regels |
| Meta | Graph API v25 via `requests`, webhooks met HMAC-check | Idem |
| E-mail | Gmail API (OAuth, zoals `gmail_koppelen.py`) of IMAP/SMTP | Afhankelijk van waar farmersatelier.nl mailt |
| Lokale webhooks | `cloudflared tunnel --url http://127.0.0.1:8800` | Gratis, geen account |
| Python-versie | 3.9 werkt nu; upgrade naar 3.12 aanbevolen (zie OPENSTAANDE_ZAKEN) | Nieuwste SDK's vereisen ≥3.10 |

Ontwerptoets: **gelijktijdigheid** — één SQLite-schrijver met lock, webhooks worden
eerst opgeslagen en dan in een achtergrondthread verwerkt, twee agents op hetzelfde
gesprek krijgen een "ook bezig"-waarschuwing. **Schaal** — tienduizenden berichten in
SQLite zijn geen probleem; bij >5 agents of meerdere winkels naar Postgres.

## 4. Hoe een bericht door het systeem gaat

```
Instagram-DM / e-mail / comment / TikTok
  → kanaaladapter maakt er één standaardvorm van
  → klant herkennen (e-mail → Shopify-klant; social-ID → identiteit; anders nieuw)
  → gesprek vinden (zelfde thread, of open gesprek binnen 3/10 dagen) of aanmaken
  → Shopify: orders van de klant + ordernummers uit de tekst (#1843) ophalen
  → AI-analyse: categorie, prioriteit, sentiment, taal, mens nodig?, wat ontbreekt?
  → rules: ALS klacht+negatief DAN high+mens nodig, enz.
  → automatiseringsniveau van die categorie bepaalt: alleen analyseren / concept /
    automatisch antwoorden / actie voorstellen
  → AI-concept (met kennisbank + orderdata) → controle-stap (belooft het niets? klopt
    het met het beleid?) → in de inbox als concept, of verstuurd bij niveau 3+
  → wij: Versturen / Aanpassen / AI opnieuw / Escaleren / Sluiten
  → verstuurd antwoord + AI-concept + verschil worden opgeslagen om van te leren
```

## 5. Volgorde van bouwen

| Fase | Wat | Status |
|---|---|---|
| 0 | Onderzoek (4 rapporten) | ✅ klaar |
| 1 | Schema, mock-data (20 klanten, 30 orders, 50 gesprekken), server, inbox-UI, AI-pipeline (mock + echt), rules, kennisbank, dashboard, OPENSTAANDE_ZAKEN.md, GitHub | 🔨 deze sessie |
| 2 | Echte Shopify-koppeling (lezen) zodra sleutels er zijn; e-mailkanaal live | wacht op Wieger |
| 3 | Meta-app aanmaken, Instagram/Facebook live; App Review voor Human Agent | wacht op Wieger + Meta |
| 4 | Shopify-acties met goedkeuring (annuleren, refund, adres); fulfillment-koppeling | na fase 2 |
| 5 | AI-niveau 3 (auto-antwoord) per veilige categorie aanzetten op basis van de leerdata; TikTok-comments | na 2–4 weken draaien |

## 6. Wat we van je andere projecten hergebruiken

- `serve.py`-patroon: alleen webroot serveren, no-cache-headers, Host-header-check,
  atomair schrijven, secrets in gitignored `.secrets.json` + `.example`.
- `gmail_koppelen.py` + `mail.py`: OAuth-koppeling zonder wachtwoord, "verstuurd is pas
  verstuurd als Gmail een id teruggeeft".
- Het ⓘ-principe: elk cijfer op het dashboard heeft een uitleg met formule.
- Append-only logs (events-tabel) als audittrail.
- Lek-assert: de server weigert te starten als een secret in de statische HTML staat.
