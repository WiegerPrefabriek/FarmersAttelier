# Onderzoek 3 — Open-source projecten, GitHub-repo's en Python-bibliotheken

Datum: 25-09-2026. Sterren en datums komen van de GitHub-API / PyPI op die dag, tenzij
gemarkeerd [unverified]. Alles is getoetst aan de harde randvoorwaarden van dit project:
**macOS, alleen Python 3.9 (systeem) en git, geen Node/Docker/Homebrew/Postgres**, één
bouwer met Claude Code, 20–50 tickets per dag.

## 0. Samenvatting

- **Geen bestaand open-source helpdesk kan de basis zijn.** Elke serieuze kandidaat
  (Chatwoot, Zammad, FreeScout, Libredesk, Frappe Helpdesk, UVdesk, Erxes) heeft een
  runtime nodig die de Mac niet heeft: Ruby/PHP/Go + PostgreSQL/MySQL + Redis, meestal
  via Docker. De enige in Python (Frappe Helpdesk) heeft MariaDB, Redis, Node en de
  Frappe-"bench"-toolchain nodig. De enige met *alle* gewenste kanalen (Chatwoot: e-mail,
  Messenger, Instagram-DM, TikTok-DM) doet nog steeds **geen Instagram- of Facebook-
  comments**, en de AI-laag (Captain) is enterprise/betaald bij self-hosting.
- **Helper (antiwork/helper) is niet meer open source.** Op 25-09-2026 geeft
  `github.com/antiwork/helper` een 404 en zegt `helper.ai/docs` "Helper is closed
  source". Niet op plannen.
- **De "70 % hergebruik"-wens is niet realistisch voor code, wél voor *ontwerp*.**
  Chatwoots kanaalmodellen, Instagram/Facebook-webhookservices, Shopify-zijbalk en
  Captain-promptstructuur zijn leesbare Ruby; een Python-port van de relevante 5–10
  bestanden is een paar honderd regels. Een heel nieuw Python/Django-project,
  **BrightBean Chat** (AGPL, 11 sterren, aug 2026), heeft al Instagram-DM + comment +
  story-mention, Messenger, WhatsApp en e-mail-adapters in Python; te jong en te zwaar
  (Docker/Postgres 16/Node 24) om over te nemen, maar de Meta-adapters zijn de beste
  Python-referentie.
- **Eén omgevingswijziging is nodig: Python 3.10+ (liefst 3.12).** De officiële
  `anthropic`-SDK 1.8.0 vereist ≥3.10, net als FastAPI, Starlette, uvicorn en
  `google-api-python-client` 2.200. (Zie de opmerking in het bouwplan: op 3.9 valt pip
  terug op een oudere SDK-versie; dat werkt voorlopig, maar upgraden is verstandig.) De
  python.org-installer of het losse `uv`-programma werken zonder Homebrew. Docker en
  Node blijven onnodig.
- **Aanbevolen stack:** Python 3.12 · lichte Python-server · SQLite met FTS5 ·
  `requests` rechtstreeks tegen de Shopify GraphQL Admin API en de Meta Graph API ·
  Gmail-API of `imap-tools` voor e-mail · `nh3` voor HTML-opschoning · `anthropic`-SDK
  met tool use en gestructureerde JSON voor triage/concepten · één self-contained
  HTML-pagina zonder build-stap · `cloudflared` quick tunnel voor lokale webhooks.

## 1. Volledige helpdeskplatformen

| Project | Stack / licentie | Sterren · laatste push | E-mail | IG DM | IG comments | FB Messenger | FB comments | TikTok | Shopify | AI | Draait op onze Mac? | Oordeel |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Chatwoot** | Rails + Vue; MIT-kern, `enterprise/` aparte licentie | 37,2k · 25-09-2026 | Ja (IMAP/SMTP, Gmail) | Ja (Instagram Business Login) | Nee (open sinds 2021) | Ja | Nee | Ja, alleen DM's, 48u-venster | Zijbalk: klantinfo + orderhistorie; vereist Shopify Partner-app | Captain = Enterprise/betaald | Nee: Ruby 3.3, pnpm, Postgres, Redis | **Onderdelen lenen** |
| **Zammad** | Rails; AGPL-3.0 | 5,95k · 25-09-2026 | Ja | Nee | Nee | Ja | Nee | Nee | Geen | Samenvatting, schrijfhulp | Nee | Negeren |
| **FreeScout** | PHP + MySQL/Postgres; AGPL-3.0 | 4,56k · 25-09-2026 | Ja (kern) | Geen module | Nee | Betaalde module, alleen DM's | Nee | Nee | Derde-partij-app "Scoutify" $35/mnd | Betaalde module | Nee | Alleen e-mail-threading-ideeën |
| **Helper (antiwork)** | was Next.js/Supabase, MIT | repo 404 | – | – | – | – | – | – | – | – | – | **Negeren (closed source)** |
| **Libredesk** | Go single binary + Vue; AGPL-3.0 | 2,96k · 25-09-2026 | Ja | Nee | Nee | Nee | Nee | Nee | Geen | KB-assistent, copilot | Nee: Postgres + Redis | Datamodel/UI-ideeën |
| **Papercups** | Elixir; MIT | 6,1k · 15-02-2024 | Deels | Nee | Nee | Nee | Nee | Nee | Geen | Geen | Nee | Negeren (onderhoudsmodus) |
| **osTicket** | PHP; GPL-2.0 | 3,9k · 17-06-2026 | Ja | Nee | Nee | Nee | Nee | Nee | Geen | Geen | Nee | Negeren |
| **UVdesk** | PHP/Symfony; OSL-3.0 | 19,6k · 01-10-2025 | Ja | Alleen betaalde SaaS | Nee | Idem | Nee | Nee | Alleen betaald | Geen | Nee | Negeren (stil) |
| **Erxes** | TypeScript; AGPL + ee | 4,1k · 25-09-2026 | Ja | Ja [unverified] | ? | Ja [unverified] | ? | Nee | Plugins [unverified] | Iets | Nee (multi-service Docker) | Negeren (te groot) |
| **Frappe Helpdesk** | Python (Frappe) + Vue; AGPL-3.0 | 3,4k · 24-09-2026 | Ja | Nee | Nee | Nee | Nee | Nee | Geen | Geen | Nee: bench, MariaDB, Redis, Node | Negeren (Python maar zwaar) |
| **Tiledesk** | Node/Angular/Mongo; MIT | 322 · 14-09-2026 | Deels | Nee | Nee | Ja [unverified] | Nee | Nee | Geen | Chatbot-builder | Nee | Negeren |
| **Helpy** | Rails; MIT | 2,5k · 08-03-2023 | Ja | Nee | Nee | Nee | Nee | Nee | Geen | Geen | Nee | Negeren (dood) |
| **Faveo** | Laravel; OSL-3.0 | 1,26k · 25-09-2026 | Ja | Nee | Nee | Betaald | Nee | Nee | Geen | Geen | Nee | Negeren |
| **AgentDesk (huabeitech/agent-desk)** | Go + Next.js; Apache-2.0 | 253 · 23-09-2026 | Nee | Nee | Nee | Nee | Nee | Nee | Geen | AI-first met "answerability gate", bevestiging, mens-samenwerking | Nee | AI-first-ontwerp lenen |
| **BrightBean Chat** | Python 3.12 / Django 5; AGPL-3.0 | 11 · 25-09-2026 (aangemaakt 20-08-2026) | Ja | Ja | **Ja** (+ story-mentions) | Ja | ? | Nee | Geen | Flows, AI-antwoorden | Nee (Docker, Postgres 16, Node 24) | **Python-Meta-adapters lenen** |
| **Inbox Orchard** | TS op Cloudflare Workers/D1; MIT | 0 · 23-09-2026 | Optioneel | Ja | **Ja** | Nee | Nee | Nee | Geen | Automatisering | Nee | Webhook-idempotentie lenen |

Ook bekeken en genegeerd: Huly (projectmanagement), Hesk (closed freeware), Unthread
(SaaS), Open-Ticket (evenementtickets), Apache Answer (Q&A-platform), Commslayer
(commercieel, op Chatwoot-SDK).

### Per project

**Chatwoot** is het referentieontwerp. Kanaalabstractie in `app/models/channel/`
(`email.rb`, `facebook_page.rb`, `instagram.rb`, `tiktok.rb`, `whatsapp.rb`, `api.rb` …).
Instagram in `app/services/instagram/` (`webhooks_base_service.rb`,
`send_on_instagram_service.rb`, `refresh_oauth_token_service.rb`,
`user_details_service.rb`). TikTok-model slaat `business_id`, `access_token`,
`refresh_token` op en ververst via `Tiktok::TokenService`; gebruikt TikTok Business
Accounts, klant-geïnitieerde gesprekken, 48-uursvenster. Shopify in
`app/services/shopify/`; toont klantinfo en orderhistorie in de zijbalk en vereist een
Shopify Partner-app met OAuth. Captain (AI) in `enterprise/app/services/captain/`
(`assistant/`, `copilot/`, `tools/`, `tool_registry_service.rb`,
`faq_suggestion_approval_service.rb`). Self-hosting: Ruby 3.3, pnpm/Node, PostgreSQL,
Redis, Sidekiq. De Instagram-doc vereist een Meta-app met `instagram_business_basic` +
`instagram_business_manage_messages`, webhookvelden `messages`, `messaging_seen`,
`message_reactions`, en App Review vóór echte klantberichten binnenkomen. Instagram- én
Facebook-comments worden niet ondersteund (verzoeken open sinds 2021).

**FreeScout** is een degelijke e-mail-inbox, maar social zit in betaalde modules; de
Facebook-module doet alleen pagina-DM's en de maker zegt expliciet geen support te geven
als Meta `pages_messaging` weigert. Waarde: hoe het e-mails threadt.

**Libredesk** is het modernste lichte helpdesk (Go, single binary) met KB-gegronde
AI-assistent en copilot, maar alleen e-mail + livechat; Instagram/Facebook/Shopify niet
op de roadmap; heeft Postgres en Redis nodig.

**BrightBean Chat** is het enige gevonden Python-project dat al met Instagram-DM's,
comments en story-mentions, Messenger, WhatsApp, Telegram, SMS en e-mail praat, met een
gedeelde inbox met toewijzing, labels, inboxregels en "human takeover pauzeert
automatisering". AGPL, vijf weken oud, 11 sterren, zware runtime. De Meta-webhook/
antwoordcode is een goede Python-referentie. Let op: code kopiëren maakt onze app AGPL —
acceptabel bij intern self-hosten.

**AgentDesk**: lezen voor het AI-first-ontwerp: een "answerability gate" beslist of de
opgehaalde kennis een antwoord ondersteunt vóórdat de bot antwoordt, met fallback,
bevestiging en mens-samenwerking. Apache-2.0.

## 2. AI-supportagent-projecten en frameworks

| Project | Taal / licentie | Sterren · push | Herbruikbaar |
|---|---|---|---|
| **Anthropic `claude-quickstarts/customer-support-agent`** | TypeScript; MIT | 17,7k · 24-09-2026 | Promptstructuur, stemmingsdetectie + omleiding, debug-paneel-UX. RAG is Bedrock — overslaan. |
| **OpenAI Agents SDK `examples/customer_service/main.py`** | Python; MIT | 29,7k · 25-09-2026 | Patroon: triage-agent → FAQ-agent / actie-agent, function tools, getypte context (klant, order). Eenvoudig na te bouwen met de Anthropic-SDK. |
| **LangGraph interrupts** | Python; MIT | – | Het "gevoelige tools hebben goedkeuring nodig"-patroon. Geen LangGraph nodig: voorgestelde actie in SQLite, tonen in inbox, uitvoeren bij klik. |
| **Dify** | Apache-2.0 + voorwaarden | 157k | Alleen Docker. Negeren. |
| **Flowise** | Apache-2.0 | 55k · 13-08-2026 | **End-of-life aug 2026, gearchiveerd.** Negeren. |
| **Rasa** | Python; Apache-2.0 | 21,3k · 24-07-2026 | Klassieke NLU; enorme afhankelijkheidsboom; verkeerd gereedschap als een LLM intent + sentiment in één call doet. |
| **Botpress / Typebot / Sim / Khoj** | diverse | – | Negeren. |
| **coder-red/store-agent** | Python FastAPI + LangGraph | 0 sterren, **geen licentie** | Zes Shopify-tools (orderstatus, retourgeschiktheid, productinfo, fulfillment, beleid, escaleren) — nuttige toollijst, code niet kopiëren. |
| **gorgias/ai-agent-benchmark** | JS; geen licentie | 1 ster | Gorgias' publieke benchmark: `eval-rubric.md`, `pools.js` (testscenario's), `classify.js` (overdrachtdetectie). Lezen voor evaluatie-ideeën. |

**Wat we echt hergebruiken:** (1) triage → specialist → tools-vorm; (2) "interrupt vóór
gevoelige tools" als `pending_actions`-tabel; (3) answerability gate; (4) Chatwoot
Captains scheiding *assistant* (auto-antwoord uit KB), *copilot* (concept voor agent) en
*FAQ-suggestie-goedkeuring* (afgesloten tickets minen tot KB-kandidaten die een mens
goedkeurt); (5) Gorgias' rubric als eval-checklist.

## 3. Python-bibliotheken en connectors

| Behoefte | Package | Laatste · datum | Licentie | Python | Onderhouden? | Opmerking |
|---|---|---|---|---|---|---|
| Shopify Admin API | `shopifyapp` (Shopify/shopify-app-python) | 1.0.2 · 03-09-2026 | MIT | ≥3.8 | Ja, officieel | GraphQL-requests met retry, webhook-HMAC, token exchange. Voor één winkel overbodig: custom-app-token + `requests.post(".../admin/api/2026-07/graphql.json")` is ~15 regels. |
| Shopify (legacy) | `ShopifyAPI` | 12.7.0 · 04-11-2024 | MIT | 3.7–3.12 | **Deprecated** | Niet gebruiken. |
| Meta Graph API | `requests` | – | – | – | – | `facebook-sdk` en `pymessenger` zijn dood. Nodig: webhook-GET-verificatie, `X-Hub-Signature-256`-HMAC, `POST /{page-id}/messages`, `POST /{ig-comment-id}/replies`, private replies, 24u-venster + `HUMAN_AGENT`-tag. |
| TikTok DM's | `requests` tegen Business Messaging API v1.3 | – | – | – | – | Open bèta; vereist TikTok Business Account, developer-app en TikTok-review; geen comment-webhook. Fase 3/optioneel. |
| Gmail | `google-api-python-client` + `google-auth-oauthlib` | 2.200.0 · 01-09-2026 | Apache-2.0 | ≥3.10 (oudere versies op 3.9) | Onderhoudsmodus | Al in gebruik; pollen via `history.list` elke 30–60 s volstaat. |
| IMAP | `imap-tools` | 1.15.0 · 19-12-2024 | Apache-2.0 | ≥3.8 | Ja | Zonder afhankelijkheden, IDLE. Fallback zonder Google-OAuth. |
| E-mail parsen | `mail-parser` of stdlib `email` | 4.6.5 · 10-09-2026 | Apache-2.0 | ≥3.9 | Ja | stdlib volstaat. |
| Quotes strippen | `email-reply-parser` | 0.5.12 · 2020 | MIT | – | Stabiel, klein | Goed genoeg. |
| HTML opschonen | `nh3` | 0.3.7 · 23-08-2026 | MIT | ≥3.8 | Ja | `bleach` is niet meer onderhouden. |
| Webframework | stdlib `http.server` (`ThreadingHTTPServer`) | – | PSF | 3.9 | – | Past bij huidige werkwijze; prima voor 50 tickets/dag; SSE werkt met chunked responses. |
| | `flask` | 3.1.3 | BSD-3 | ≥3.9 | Ja | Enige mainstream framework dat 3.9 nog ondersteunt. |
| | `fastapi` / `uvicorn` | 0.141 / 0.54 | MIT / BSD | ≥3.10 | Ja | Mooiste voor async webhooks + SSE. |
| DB | stdlib `sqlite3` | – | – | – | – | FTS5 voor zoeken; WAL + één schrijver. |
| Vectoren (optioneel) | `sqlite-vec` | 0.1.9 | MIT/Apache | – | Ja | Alleen als de KB te groot wordt voor de prompt. Voor een kledingmerk: hele KB in de prompt met caching. |
| Achtergrondtaken | `APScheduler` of `threading.Thread` | 3.11.3 | MIT | ≥3.8 | Ja | Pollen volstaat. |
| Claude | `anthropic` | 1.8.0 · 22-09-2026 | MIT | ≥3.10 | Ja | Tool use, gestructureerde output, prompt caching. |
| Retry | eigen decorator (10 regels) | – | – | – | – | `tenacity` 9 vereist ≥3.10. |
| Lokale webhook-tunnel | `cloudflared` quick tunnel | – | Apache-2.0 | – | Ja | Gratis, geen account, publieke HTTPS-URL `*.trycloudflare.com`. |

## 4. Frontend zonder build-stap

| Optie | Geschiktheid voor 3-koloms inbox met live updates |
|---|---|
| Vanilla JS + CSS | Wat we nu doen; wordt lastig bij 8–10 samenwerkende panelen. |
| **Preact + htm (standalone ESM via CDN of lokaal gevendord)** | Componentmodel, hooks, JSX-achtige templates in één HTML-bestand. Aanbevolen door het onderzoek. |
| Alpine.js | Goed voor sprinkles; state voor een volledige inbox wordt onhandig. |
| htmx (+ SSE) | Server-gerenderde partials; goede tweede keus bij Python-side rendering. |
| Vue 3 via CDN | Werkt zonder build; zwaarder dan Preact. |

## 5. Oordeel

### (a) Bestaand project als basis?

**Nee.** Chatwoot komt qua kanalen het dichtst in de buurt, maar draait niet op de Mac,
Captain is betaald, comments worden niet ondersteund en een 37k-sterren Rails-monoliet
aanpassen is het tegenovergestelde van onze werkwijze. Libredesk is het dichtst in
geest maar zonder social en met Postgres/Redis. De Python-opties slepen
MariaDB/Postgres/Redis/Node/Docker mee. Zelf een kleine app bouwen is het eerlijke
antwoord; de herbruikbare waarde zit in *ontwerpen en prompts* en in de Meta/Shopify-
API-kennis in die repo's.

### (b) Wat we lenen en waar het staat

1. **Datamodel** — Chatwoot `db/schema.rb`: `inboxes` (één per kanaal), `contacts` +
   `contact_inboxes` (zelfde mens over kanalen), `conversations` (status, assignee,
   labels, priority), `messages` (`message_type` incoming/outgoing/activity,
   `content_attributes`, `source_id` = extern bericht-id), `attachments`, `notes`.
2. **Instagram/Messenger-adapters** — Chatwoot `app/services/instagram/*`,
   `app/models/channel/instagram.rb` en `facebook_page.rb`; BrightBean Chats
   comment/story-mention-handlers (Python); Inbox Orchards idempotente webhook-ingestie.
3. **TikTok** — Chatwoot `app/models/channel/tiktok.rb` en `app/services/tiktok/`;
   TikTok Business Messaging API v1.3. Als laatste plannen.
4. **Shopify-zijbalk** — Chatwoot `app/services/shopify/*`. Voor één winkel: custom app in
   Shopify-admin, Admin-API-token, GraphQL `customers(query: "email:...")` en
   `orders(query: ...)`, plus webhooks `orders/create`, `orders/fulfilled`,
   `refunds/create`. Acties (`orderCancel`, `refundCreate`, …) achter de
   goedkeuringstabel.
5. **AI-structuur** — Chatwoot `enterprise/app/services/captain/*`; OpenAI Agents
   `examples/customer_service/main.py`; LangGraph-interrupts voor goedkeuren-vóór-
   uitvoeren; AgentDesk-README voor de answerability gate; Gorgias `eval-rubric.md`.
6. **E-mail** — FreeScouts fetch/threading-logica (`FetchEmails.php`,
   `Conversation.php`, `Thread.php` [paden unverified]) voor `Message-ID`/`In-Reply-To`/
   `References` en onderwerp-normalisatie; `email-reply-parser` en `nh3`.

### (c) Aanbevolen stack (concreet)

- **Runtime:** Python 3.12 van python.org of via `uv`. Verder: git, SQLite, één proces.
- **Server:** één Python-proces met routes `/webhooks/meta`, `/webhooks/shopify`,
  `/api/...`, `/events` (SSE), `/` (inbox-HTML).
- **Opslag:** SQLite (WAL) + FTS5 voor berichten en KB-artikelen; JSON-kolommen voor
  ruwe payloads.
- **Kanalen, in volgorde:** (1) e-mail via Gmail-API of `imap-tools`; (2) Facebook-
  pagina-DM's + pagina-comments; (3) Instagram-DM's + comments via **Instagram API met
  Instagram Login**; (4) TikTok Business Messaging als het account wordt toegelaten.
- **AI:** `anthropic`-SDK. Eén `triage`-call met JSON-schema (intent, prioriteit,
  sentiment, taal, benodigde info); één `draft`-call met tools `lookup_customer`,
  `lookup_orders`, `search_kb` en de volledige KB gecachet in de systemprompt; elk
  uitgaand antwoord en elke Shopify-mutatie in `pending_action` tot een agent klikt.
  Log elke modelcall.
- **Rules-engine:** rijen in `rule` (`when`-condities op kanaal/intent/sentiment/
  trefwoorden → `then`-acties toewijzen/labelen/prioriteit/auto-antwoord/snoozen).
- **Kennisbank:** Markdown-bestanden in `kb/` gesynchroniseerd naar de DB; Captain-stijl
  "stel FAQ voor uit afgesloten ticket → mens keurt goed".
- **Dashboard:** zelfde HTML met een Stats-tab uit SQL-aggregaten.
- **Lokaal / deploy:** `cloudflared tunnel --url http://localhost:8000` voor webhooks;
  later een kleine VPS of Cloudflare Tunnel vanaf een Mac mini. Tokens in een gitignored
  secretsbestand.

Realistische inschatting: schema + e-mailkanaal + inbox-UI in de eerste week; Meta App
Review is het langste pad (weken, buiten onze controle) — **start de Meta-developer-app
en Business Verification op dag één.**

## Geraadpleegde bronnen

- Chatwoot: https://github.com/chatwoot/chatwoot (models/channel, services/instagram,
  services/shopify, enterprise/app/services/captain, lib/integrations),
  https://developers.chatwoot.com/self-hosted/configuration/features/integrations/instagram-via-instagram-business-login,
  https://developers.chatwoot.com/self-hosted/configuration/features/integrations/shopify-integration-setup,
  https://www.chatwoot.com/blog/tiktok-channel, issues #2096, #3448, discussie #8455
- Zammad: https://zammad.com/en/product/features · FreeScout: https://freescout.net/modules/,
  https://apps.shopify.com/scoutify · Helper: https://helper.ai/docs (closed source)
- Libredesk: https://github.com/abhinavxd/libredesk (ROADMAP.md) · Papercups, osTicket,
  UVdesk, Erxes, Frappe Helpdesk, Tiledesk, Helpy, Faveo, Apache Answer via GitHub-API
- AgentDesk: https://github.com/huabeitech/agent-desk · BrightBean Chat:
  https://github.com/brightbeanxyz/brightbean-chat · Inbox Orchard:
  https://github.com/danekweaga/inboxorchard · https://github.com/gorgias/ai-agent-benchmark
- https://github.com/anthropics/anthropic-quickstarts/tree/main/customer-support-agent ·
  https://github.com/openai/openai-agents-python (examples/customer_service/main.py) ·
  https://docs.langchain.com/oss/python/langgraph/interrupts
- PyPI: shopifyapp, ShopifyAPI, anthropic, google-api-python-client, imap-tools,
  mail-parser, email-reply-parser, talon, nh3, bleach, sqlite-vec, fastapi, flask,
  httpx, APScheduler, tenacity · https://shopify.dev/docs/api/admin-graphql/latest
- https://developers.facebook.com/docs/instagram-platform/webhooks ·
  https://developers.facebook.com/docs/messenger-platform/webhooks ·
  https://business-api.tiktok.com/portal/docs/business-messaging-api/v1.3
- https://github.com/developit/htm · https://github.com/preactjs/preact ·
  https://github.com/bigskysoftware/htmx
