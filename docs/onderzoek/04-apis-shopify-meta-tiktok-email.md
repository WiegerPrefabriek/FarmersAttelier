# Onderzoek 4 — API's: Shopify, Meta (Facebook/Instagram), TikTok en e-mail

Stand: 25-09-2026. Alles is gecontroleerd tegen officiële documentatie tenzij gemarkeerd
**[unverified]**. Versienummers, permissienamen en datums komen uit de bronnen onderaan.

---

## 1. SHOPIFY ADMIN API

### 1.1 Versies, REST vs GraphQL, rate limits

- **Versiebeheer:** `JJJJ-MM`, elk kwartaal een release. Stabiel nu: `2026-01`, `2026-04`,
  **`2026-07` (nieuwste stabiele)**; `2026-10` is release candidate (stabiel per 1 okt
  2026). Elke versie ≥12 maanden ondersteund. **Pin `2026-07`**, bump elk kwartaal.
- **REST-status:** "The REST Admin API is a legacy API as of October 1, 2024." Nieuwe
  functies (returns, fulfillment orders, nieuwere ordervelden) bestaan alleen in GraphQL.
  **Bouw uitsluitend op de GraphQL Admin API.**
- **Rate limits (kosten-gebaseerde leaky bucket):** herstel 100 punten/s (Standard), 200
  (Advanced), 1.000 (Plus). Max. kosten per query 1.000 punten. Elke response bevat
  `extensions.cost.throttleStatus`. Bij throttling: `errors[].extensions.code =
  "THROTTLED"` (soms HTTP 429) — beide afvangen, ≥1 s wachten.
- **Wijzigingen 2026:** `2026-04`: `refundCreate` vereist de `@idempotent(key:)`-
  directive; `2026-10`: adreswijziging op onvervulde order herberekent btw.

### 1.2 De custom app aanmaken (veranderd per 1 januari 2026)

**Belangrijk:** "Starting January 1, 2026, you will not be able to create new legacy
custom apps" in de admin. Het oude pad *Settings → Apps and sales channels → Develop
apps* verwijst nu door naar het **Dev Dashboard** (`https://dev.shopify.com/dashboard/`).
Oude custom apps (vóór 2026) blijven werken met hun eenmalig getoonde `shpat_…`-token.

Exacte stappen 2026 (winkeleigenaar, of medewerker met "App development → Develop"):

1. Log in op `https://dev.shopify.com/dashboard/` met het eigenaarsaccount.
2. **Apps** → **Create app** → **Start from Dev Dashboard** → naam → **Create**.
3. **Versions** → App URL (standaard) → Webhooks API version (`2026-07`) → **Scopes**
   (lijst hieronder) → **Release**.
4. **Home** → **Install app** → kies de live winkel → **Install**.
5. **Settings** → kopieer **Client ID** en **Client secret**.
6. Token via **client credentials grant** (er is geen token in de UI):

```http
POST https://{shop}.myshopify.com/admin/oauth/access_token
Content-Type: application/json
{"grant_type":"client_credentials","client_id":"…","client_secret":"…"}
→ {"access_token":"…","scope":"read_orders,…","expires_in":86399}
```
Tokens leven **24 uur**; cachen en vóór verloop verversen. Werkt alleen als app en winkel
in **dezelfde Dev Dashboard-organisatie** zitten. Gebruik als `X-Shopify-Access-Token`.

**Na het wijzigen van scopes:** nieuwe versie releasen én opnieuw **Install app**
klikken, anders houdt het token de oude scopes (403 "protected customer data" is het
gebruikelijke symptoom).

**Protected customer data (PCD):** "Custom apps get Level 1 and Level 2 PCD
automatically" (Shopify-staff, 23-06-2026). Level 2 = naam, adres, telefoon, e-mail.
Enige voorwaarde: voor admin-aangemaakte custom apps vereist Level 2 het **Grow-plan of
hoger**.

**Scopes** — LEZEN nu: `read_customers, read_orders, read_all_orders (orders ouder dan 60
dagen), read_products, read_inventory, read_locations, read_fulfillments,
read_merchant_managed_fulfillment_orders, read_assigned_fulfillment_orders,
read_third_party_fulfillment_orders, read_shipping, read_returns, read_draft_orders,
read_discounts`. SCHRIJVEN later: `write_orders` (refundCreate, orderCancel, orderUpdate,
orderEdit*), `write_returns`, `write_inventory`, `write_customers`,
`write_draft_orders`, `write_discounts`, `write_merchant_managed_fulfillment_orders` +
`write_fulfillments`.

### 1.3 Objecten, velden en mutaties

- **Customer:** `id, displayName, firstName, lastName, defaultEmailAddress{emailAddress},
  defaultPhoneNumber{phoneNumber}` (`email`/`phone` zijn deprecated), `amountSpent{amount
  currencyCode}, numberOfOrders, orders(first:), addresses, defaultAddress, tags, note,
  createdAt, lastOrder`. Zoeken: `customers(query:"email:x@y.nl")`, `phone:`,
  `last_name:`, `tag:`. Mutaties: `customerUpdate`, `tagsAdd`.
- **Order:** `name ("#1843"), createdAt, cancelledAt, cancelReason, closedAt,
  displayFinancialStatus, displayFulfillmentStatus, returnStatus, note, tags, email,
  phone, shippingAddress, billingAddress, totalPriceSet, lineItems{title sku quantity
  currentQuantity refundableQuantity variant{id title sku selectedOptions{name value}
  inventoryQuantity}}, fulfillments{…}, refunds{…}, returns{…}, events(first:)`.
  Zoeken: `orders(query:"name:#1843")`, `email:`, `status:`, `financial_status:`,
  `fulfillment_status:unshipped|partial|fulfilled`.
- **Fulfillment:** `status, displayStatus, trackingInfo{company number url},
  estimatedDeliveryAt, deliveredAt, inTransitAt, events{status happenedAt}`.
  `FulfillmentEventStatus`: `ATTEMPTED_DELIVERY, CARRIER_PICKED_UP, CONFIRMED, DELAYED,
  DELIVERED, FAILURE, IN_TRANSIT, LABEL_PRINTED, LABEL_PURCHASED, OUT_FOR_DELIVERY,
  READY_FOR_PICKUP`.
- **Return:** `id, name, status, createdAt, closedAt, requestApprovedAt, totalQuantity,
  returnLineItems, reverseFulfillmentOrders, refunds, exchangeLineItems, order`.
  `ReturnStatus`: `REQUESTED, OPEN, CLOSED, DECLINED, CANCELED`. Mutaties:
  `returnRequest`, `returnApproveRequest`, `returnDeclineRequest`, `returnCreate`,
  `returnProcess`, `returnClose`, `returnReopen`, `returnCancel`.
- **Refund:** `refundCreate(input: RefundInput{orderId, refundLineItems[{lineItemId
  quantity restockType locationId}], shipping{fullRefund|amount}, transactions[{parentId
  amount kind:REFUND gateway}], note, notify})`.
- **Annuleren:** `orderCancel(orderId, reason: CUSTOMER|PAYMENT|FRAUD|INVENTORY|STAFF|
  OTHER, restock: Boolean!, refund: Boolean!, notifyCustomer, staffNote, refundMethod)`
  → `Job` (pollen) + `orderCancelUserErrors`.
- **Adres/notitie/tags:** `orderUpdate(input:{id, shippingAddress{…}, note, tags, email})`.
  Regelwijzigingen via `orderEditBegin → orderEditAddVariant / orderEditSetQuantity →
  orderEditCommit`.
- **Tracking:** `fulfillmentTrackingInfoUpdate(fulfillmentId, trackingInfoInput{company
  number url}, notifyCustomer)`.
- Ook: `orderMarkAsPaid`, `draftOrderCreate`, `discountCodeBasicCreate`,
  `fulfillmentEventCreate`.

### 1.4 Voorbeeld-GraphQL

```graphql
# 1) Klant zoeken op e-mail/telefoon/naam met recente orders
query FindCustomer($q: String!) {
  customers(first: 5, query: $q) {
    nodes {
      id displayName firstName lastName
      defaultEmailAddress { emailAddress }
      defaultPhoneNumber { phoneNumber }
      amountSpent { amount currencyCode } numberOfOrders
      tags note createdAt
      defaultAddress { address1 zip city countryCodeV2 }
      orders(first: 10, sortKey: CREATED_AT, reverse: true) {
        nodes { id name createdAt displayFinancialStatus displayFulfillmentStatus returnStatus
                totalPriceSet { shopMoney { amount currencyCode } } }
      }
    }
  }
}
```

```graphql
# 2) Volledige order op naam ("#1843")
query OrderByName($q: String!) {                      # $q = "name:#1843"
  orders(first: 1, query: $q) {
    nodes {
      id name createdAt cancelledAt cancelReason closedAt
      displayFinancialStatus displayFulfillmentStatus returnStatus note tags
      customer { id displayName }
      shippingAddress { name address1 address2 zip city countryCodeV2 phone }
      lineItems(first: 50) { nodes {
        id title sku quantity currentQuantity refundableQuantity
        variant { id title sku inventoryQuantity selectedOptions { name value } }
      } }
      fulfillments(first: 10) {
        id status displayStatus estimatedDeliveryAt inTransitAt deliveredAt
        trackingInfo { company number url }
        events(first: 20) { nodes { status happenedAt } }
      }
      refunds { id createdAt note totalRefundedSet { shopMoney { amount } } }
      returns(first: 10) { nodes { id name status
        returnLineItems(first: 20) { nodes { ... on ReturnLineItem { quantity returnReason returnReasonNote } } }
        reverseFulfillmentOrders(first: 5) { nodes { id status } } } }
      events(first: 30) { nodes { id createdAt message } }
    }
  }
}
```

```graphql
# 3) Deelrefund van één regel + verzendkosten, restock, klant notificeren
mutation RefundOne($input: RefundInput!) {
  refundCreate(input: $input) @idempotent(key: "ticket-4711-refund-1") {
    refund { id totalRefundedSet { shopMoney { amount currencyCode } } }
    userErrors { field message }
  }
}
```

```graphql
# 4) Verzendadres wijzigen op onvervulde order; webhook registreren
mutation FixAddress($input: OrderInput!) {
  orderUpdate(input: $input) { order { id shippingAddress { address1 zip city } tags } userErrors { field message } }
}
mutation SubscribeOrders($topic: WebhookSubscriptionTopic!, $sub: WebhookSubscriptionInput!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: $sub) {
    webhookSubscription { id topic uri } userErrors { field message }
  }
}
```

### 1.5 Webhooks

- **Topics:** `ORDERS_CREATE`, `ORDERS_UPDATED`, `ORDERS_FULFILLED`, `ORDERS_CANCELLED`,
  `ORDERS_PAID`, `ORDERS_EDITED`, `FULFILLMENTS_CREATE`, `FULFILLMENTS_UPDATE`,
  `FULFILLMENT_EVENTS_CREATE`, `REFUNDS_CREATE`, `RETURNS_REQUEST / APPROVE / DECLINE /
  CANCEL / CLOSE / REOPEN / UPDATE / PROCESS`, `CUSTOMERS_CREATE / UPDATE / DELETE`.
- **Registreren:** (1) admin-UI *Settings → Notifications → Webhooks* (getekend met een
  winkelbreed secret op die pagina); (2) `webhookSubscriptionCreate` met het app-token
  (getekend met het client secret); (3) TOML-config in het Dev Dashboard. Voor één custom
  app is (2) of (3) het schoonst.
- **Verificatie:** header `X-Shopify-Hmac-SHA256` = base64(HMAC-SHA256(secret, raw body));
  vergelijk timing-safe; lees de raw body vóór JSON-parsing. Ook `X-Shopify-Topic`,
  `X-Shopify-Shop-Domain`, `X-Shopify-Webhook-Id` (dedupe). Antwoord binnen 5 s — in de
  wachtrij zetten, dan verwerken. 8 retries over 4 uur.
- **HTTPS verplicht**, localhost geblokkeerd — lokaal via `cloudflared tunnel` of ngrok.

### 1.6 Shopify Inbox, Flow, retouren, tracking

- **Shopify Inbox** heeft **geen Admin-API** (geen Conversation-object; community-thread
  van 15-09-2026 bevestigt dat). Buiten scope.
- **Shopify Flow → "Send HTTP request"**: alleen op Grow/Advanced/Plus; webhooks zijn
  gratis op elk plan, dus webhooks zijn primair.
- **Retouren:** native retouren (self-serve vanaf de orderstatuspagina, retourregels,
  ruilen, labels, refund-na-inspectie) via de `Return*`-mutaties en `returns/*`-webhooks.
  Derden: Loop, ReturnGO (gebruikt Sendcloud voor NL-labels), Sendcloud-retourportaal.
  Omdat die apps in Shopify's Return-objecten schrijven, kan onze inbox ze altijd lezen.
- **Tracking:** Shopify werkt `shipmentStatus`/fulfillment-events alleen automatisch bij
  voor *geïntegreerde* vervoerders (DHL en DPD generiek; **PostNL en GLS niet**). Voor NL:
  - **PostNL Shippingstatus API** (`/shipment/v2/status`, `apikey`-header; sleutel via
    Mijn PostNL Zakelijk → API beheren) — alleen zakelijke klanten.
  - **DHL eCommerce NL** `GET https://api-gw.dhlparcel.nl/track-trace?key=<trackercode>`
    (+ postcode voor details); events `DATA RECEIVED, UNDERWAY, IN DELIVERY, DELIVERED,
    EXCEPTION, PROBLEM`.
  - Aggregators 2026: 17TRACK geen gratis API-tier meer; AfterShip API alleen betaald
    (~$99/mnd); TrackingMore Pro ($74/mnd). Liever vervoerder-API's.

---

## 2. META (FACEBOOK + INSTAGRAM)

### 2.1 De twee routes

| | (a) Instagram API **met Facebook Login** (Messenger Platform) | (b) Instagram API **met Instagram Login** |
|---|---|---|
| Facebook-pagina gekoppeld aan IG | **Vereist** | Niet vereist |
| Host / token | `graph.facebook.com`, **Page access token** (verloopt nooit) | `graph.instagram.com`, Instagram User token (60 d, te verversen) |
| Messaging-scopes | `instagram_basic, instagram_manage_messages, pages_manage_metadata` (+ `pages_messaging` voor FB-DM's/private replies) | `instagram_business_basic, instagram_business_manage_messages` |
| Comment-scopes | `instagram_manage_comments, pages_read_engagement` | `instagram_business_manage_comments` |
| Facebook-pagina-comments/Messenger | Zelfde app, zelfde token (`pages_manage_engagement, pages_read_user_content, pages_read_engagement, pages_show_list, pages_messaging`) | Niet mogelijk |
| Ads, product-tagging | Ja | Nee |
| Human Agent (7 dagen) | Ja (feature-goedkeuring) | Ja (feature-goedkeuring) |

**Aanbeveling voor een kledingmerk met Facebook-pagina en ads: route (a).** Eén app,
één niet-verlopend Page-token, dekt Instagram-DM's, Instagram-comments, Facebook
Messenger en Facebook-pagina/ad-comments. Beide routes vereisen in de Instagram-app:
*Instellingen → Berichten en story-reacties → Berichtbeheer → Verbonden tools → "Toegang
tot berichten toestaan"*.

### 2.2 Setup en de review-vraag

1. `developers.facebook.com/apps/creation/` → naam + contact-e-mail → **use cases**:
   "Manage messaging and content on Instagram" en "Manage everything on your Page" →
   koppel de **business portfolio** die de pagina/IG-account bezit.
2. Webhooks-product: callback-URL (publiek HTTPS), **verify token** (zelf gekozen
   string); Meta stuurt `GET ?hub.mode=subscribe&hub.verify_token=…&hub.challenge=…` —
   echo `hub.challenge`. Elke POST draagt `X-Hub-Signature-256: sha256=<HMAC-SHA256(app
   secret, raw body)>`.
3. Velden abonneren: Page-object `messages, messaging_postbacks, message_echoes, feed,
   mention`; Instagram-object `messages, messaging_postbacks, message_reactions,
   messaging_seen, comments, mentions, live_comments`.
4. Tokens (2.5) en het *asset* aan de app koppelen:
   `POST /{PAGE_ID}/subscribed_apps?subscribed_fields=messages,messaging_postbacks,feed`.
5. App op **Live** zetten (privacybeleid-URL) — webhooks komen alleen in Live-modus.

**Toegangsniveaus (vaak verkeerd begrepen):**
- **Standard Access** krijgt elke Business-app automatisch, maar werkt alleen voor
  gebruikers met een rol op de app of in het bedrijf dat de app claimt. Dus: als de
  eigenaar admin van de app is en pagina/IG-account in de business portfolio zitten, kun
  je Live draaien voor de eigen accounts **zonder App Review** voor messaging en
  comment-moderatie.
- **Advanced Access** (accounts van derden) vereist App Review **en Business
  Verification**.
- **Uitzonderingen die ook voor eigen accounts gelden:** (1) de **Human Agent**-feature
  (7-dagen-venster) vereist App Review + Business Verification; (2) op route (b) zijn
  `comments`- en `live_comments`-webhooks gedocumenteerd als Advanced Access; (3) de
  Messenger-checklist zegt dat de app gereviewd moet zijn vóór gebruik door anderen dan
  mensen met een rol op de app. Praktisch: live onder Standard Access voor DM's/comments,
  en één App Review (screencast + business verification) voor **Human Agent**. Reken op
  1–3 weken [typisch, unverified].

### 2.3 Messaging-regels

- **24-uursvenster** na het laatste klantbericht. Daarbuiten falen antwoorden tenzij
  getagd `HUMAN_AGENT` (7 dagen, vereist de feature). Sinds **27-04-2026** geven de tags
  `CONFIRMED_EVENT_UPDATE`, `ACCOUNT_UPDATE`, `POST_PURCHASE_UPDATE` foutcode 100.
- **Echo's:** abonneer `message_echoes`; eigen uitgaande berichten (ook die via de
  Instagram-app of Business Suite) komen binnen met `is_echo: true` — gebruik ze om
  antwoorden van elders te spiegelen.
- **Handover:** "Meta no longer supports the Handover Protocol for Instagram; all
  businesses have been migrated to Conversation Routing." Met één eigen app niet nodig.
- **DM sturen:** route (a) `POST https://graph.facebook.com/v25.0/{PAGE_ID}/messages`,
  body `{"recipient":{"id":"<IGSID>"},"message":{"text":"…"}}`, optioneel
  `"messaging_type":"MESSAGE_TAG","tag":"HUMAN_AGENT"`.
- **Afzenderprofiel:** `GET /{IGSID}?fields=name,username,profile_pic,follower_count,
  is_user_follow_business,is_business_follow_user`. Geen e-mail/telefoon.
- **Rate limits per IG-account:** Send API 100 calls/s, Conversations API 2 calls/s,
  private replies 750/uur.

**Instagram-DM-webhook (`object` = `"instagram"`):**
```json
{
  "object": "instagram",
  "entry": [{
    "id": "17841400000000000",
    "time": 1758790000000,
    "messaging": [{
      "sender":    { "id": "1234567890123456" },
      "recipient": { "id": "17841400000000000" },
      "timestamp": 1758790000000,
      "message": {
        "mid": "aWdfZAG1faXRlbToxOklHTWVzc2FnZAUlEOjE3ODQ...",
        "text": "Hoi, is maat M nog op voorraad?",
        "attachments": [{ "type": "image", "payload": { "url": "https://lookaside.fbsbx.com/..." } }],
        "is_echo": false
      }
    }]
  }]
}
```
(Facebook Messenger-events zijn identiek met `"object":"page"`, `sender.id` = PSID.)

### 2.4 Comments

**Instagram** — webhookveld `comments`:
```json
{
  "object": "instagram",
  "entry": [{
    "id": "17841400000000000",
    "time": 1758790000,
    "changes": [{
      "field": "comments",
      "value": {
        "id": "17900000000000001",
        "from": { "id": "1234567890123456", "username": "anna_jansen" },
        "text": "Komt deze ook in beige?",
        "media": { "id": "17850000000000000", "media_product_type": "FEED" },
        "parent_id": "17900000000000000"
      }
    }]
  }]
}
```
Acties: antwoorden `POST /{IG_COMMENT_ID}/replies?message=…`; verbergen
`POST /{IG_COMMENT_ID}?hide=true|false`; verwijderen `DELETE /{IG_COMMENT_ID}`.
**Privé antwoord op een comment:** `POST /{PAGE_ID}/messages` met
`{"recipient":{"comment_id":"<id>"},"message":{"text":"…"}}` — één bericht per comment,
binnen 7 dagen.

**Facebook-pagina** — webhookveld `feed`, `item: "comment"`:
```json
{ "object": "page", "entry": [{ "id": "<PAGE_ID>", "time": 1758790000, "changes": [{
  "field": "feed",
  "value": { "item": "comment", "verb": "add",
    "comment_id": "123456789_987654321", "post_id": "123456789_111111111", "parent_id": "123456789_111111111",
    "from": { "id": "987654321", "name": "Anna Jansen" },
    "message": "Wanneer weer op voorraad?", "created_time": 1758790000 } }] }] }
```
Acties: antwoorden `POST /{comment-id}/comments?message=…`; verbergen
`POST /{comment-id}?is_hidden=true`; verwijderen `DELETE /{comment-id}`. Privé antwoord:
`POST /{PAGE_ID}/messages {"recipient":{"comment_id":…}}` (7 dagen). Ad-comments: ads
zijn pagina-posts; `feed`-webhooks bevatten ze voor de eigen pagina [deels unverified].

### 2.5 Tokens

- Route (a): kortlevend user-token → langlevend (60 d) via `GET /oauth/access_token?
  grant_type=fb_exchange_token…` → `GET /me/accounts` geeft **Page-tokens zonder
  vervaldatum**. Voor een server liever een **System User-token**: Business Settings →
  System Users → aanmaken → pagina + IG-asset + app toewijzen → **Generate New Token**.
- Route (b): 1-uurs token → 60 dagen via `ig_exchange_token` → wekelijks verversen.

---

## 3. TIKTOK

- **Directe berichten (organisch):** er is een officiële **Business Messaging API**
  (business-api.tiktok.com, v1.3), maar alleen voor "authorized Business Accounts" die de
  data-security-review hebben doorlopen en op de allowlist staan. In de praktijk krijgen
  messaging-platformen dat (SleekFlow, MessageGate; Gorgias/Zendesk [unverified]). Een
  klein merk met een eigen app wordt niet snel toegelaten.
- **Comments op eigen video's:** de TikTok API for Business (v1.3, scope "TikTok
  Accounts") heeft endpoints voor **eigen video's**: comments ophalen
  (`/business/comment/list/`), replies, antwoorden (`/business/comment/reply/`), liken,
  verbergen, verwijderen. Vereist: developer-app op business-api.tiktok.com, Business
  Account-autorisatie (OAuth) en sinds **20-03-2026** het **Accounts API Access
  Application Form**. Realistisch voor een merk (aanvraag, geen partnerprogramma), maar
  reken op een review. De consumer Display/Content Posting API heeft **geen**
  comment-endpoints; de Research API is academisch.
- **TikTok Shop:** live in Nederland sinds **15-06-2026**. Verkoopt het merk daar, dan is
  de **Customer Service API** (Partner Center; conversations, messages, send, webhooks)
  beschikbaar voor een eigen Partner Center-app met seller-autorisatie.
- **Conclusie:** zonder allowlist-status kunnen organische TikTok-DM's vandaag niet worden
  ingelezen. Realistisch pad: (1) Accounts-scope aanvragen en de comment-endpoints
  gebruiken; (2) bij TikTok Shop: Customer Service API; (3) organische DM's handmatig in
  de TikTok-app en als notitie in de inbox loggen. Niet scrapen (ToS-schending).

---

## 4. E-MAIL

### 4.1 `support@` ontvangen — opties

**(a) Google Workspace → Gmail API.** Twee modellen: OAuth "Internal"-app (geen
Google-verificatie), of — beter voor een server — **service-account met domain-wide
delegation** (Admin console → Security → API controls → Manage Domain Wide Delegation)
dat `support@` impersoneert. Scopes: `gmail.readonly`, `gmail.modify`, `gmail.send`,
`gmail.settings.basic`. Inlezen: `users.watch` + Pub/Sub-push, of simpeler: elke 30–60 s
`history.list` pollen. Antwoorden: `messages.send` met raw RFC 2822, `threadId`,
`In-Reply-To`, `References`, zelfde `Subject`. Versturen "als" `support@`: echte mailbox
impersoneren, of een geverifieerd **send-as**-alias op de gebruiker.

**(b) IMAP/SMTP generiek.** Werkt met wachtwoorden bij Nederlandse hosting (TransIP/
Hostnet/Strato): IMAP IDLE of 30 s pollen met `imaplib`/`imap-tools`, SMTP op 587.
**Microsoft 365:** Basic auth voor IMAP is sinds 2022/2023 uit; OAuth2 `XOAUTH2` nodig.
SMTP AUTH Basic wordt eind december 2026 standaard uitgezet.

**(c) Microsoft Graph (365).** `Mail.Read`/`Mail.ReadWrite`, `Mail.Send`; application
permissions met Application Access Policy; subscriptions max <7 dagen, verlengen via
PATCH.

**(d) Inbound-parse-diensten:** Postmark Inbound (Pro, vanaf ~$16,50/mnd; levert
`StrippedTextReply`), Resend Inbound (gratis tier 3.000/mnd), Mailgun Routes
(Foundation+), Cloudflare Email Routing + Email Workers (gratis; domein op Cloudflare
DNS; Worker kan de mail naar onze inbox POSTen).

**Uitgaand** in alle gevallen: via Google/365 (houdt "Verzonden" compleet) of een ESP;
publiceer **SPF**, **DKIM**, **DMARC** zodat antwoorden als `support@farmersatelier.nl`
aankomen.

**Aanbeveling — vraag de eigenaar waar de MX van `farmersatelier.nl` naartoe wijst**
(`dig MX farmersatelier.nl`):
- **Google Workspace** (`aspmx.l.google.com`): Gmail API, eerst pollen, later Pub/Sub.
- **Microsoft 365**: Graph application permissions + Access Policy + verlengjob.
- **Generieke hosting**: IMAP IDLE + SMTP (snelst), of doorsturen naar Resend/Cloudflare
  Email Workers.

### 4.2 Antwoorden parsen, threading, auto-replies, bounces

- **Quotes/handtekeningen strippen:** `mail-parser-reply` (ondersteunt **Nederlands**
  expliciet), `talon` als fallback, `email_reply_parser` (Engels-gericht). Ruwe body
  bewaren.
- **Threading:** primair `In-Reply-To`/`References` → onze opgeslagen `Message-ID`s;
  fallback onderwerp-token (`[#4711]`) en afzender+onderwerp binnen 7 dagen; sla onze
  Message-ID op bij elk uitgaand bericht.
- **Forwards:** `Fwd:`/`FW:`/`Doorst:`; originele afzender in de body of in een
  `message/rfc822`-bijlage.
- **Auto-replies:** geen ticket bij `Auto-Submitted: auto-replied|auto-generated`,
  `X-Auto-Response-Suppress`, `Precedence: bulk|auto_reply|junk`, `X-Autoreply`,
  `List-Id`. Nooit automatisch beantwoorden (loop-risico).
- **Bounces:** `From: MAILER-DAEMON@`/`postmaster@`, `multipart/report;
  report-type=delivery-status`, lege `Return-Path`; uitgaand bericht als mislukt markeren
  en aan de agent tonen.

---

## 5. PRAKTISCHE SAMENVATTING

| Kanaal | Officiële API | Ontvangen | Antwoorden | Review/goedkeuring | Setup | Eigenaar moet doen/leveren |
|---|---|---|---|---|---|---|
| Shopify (data + webhooks) | GraphQL Admin `2026-07` | Webhooks + queries | Mutaties | Geen voor custom app; PCD L1+L2 automatisch (Grow+) | ½–1 dag | App in Dev Dashboard, scopes kiezen, Client ID/secret geven |
| Instagram-DM's | Ja (route a of b) | `messages`-webhook | Send API, 24 u (+7 d met Human Agent) | Standard voor eigen account; **App Review + Business Verification voor Human Agent** | 1–2 dagen + 1–3 weken review | Business-portfolio-admin, pagina↔IG koppelen, "Toegang tot berichten toestaan", ons als app-admin, KvK-docs |
| Instagram-comments | Ja | `comments`-webhook | Reply/hide/delete/private reply | Standard voor eigen account | 1 dag | Zelfde |
| Facebook Messenger + comments | Ja (route a) | `messages`, `feed` | Send API, reply/hide/private reply | Standard voor eigen pagina | 1 dag | Pagina-admin, System User-token |
| TikTok-DM's (organisch) | Alleen allowlist | Nee | Nee | Allowlist/partner | n.v.t. | Handmatig; TikTok Business Center |
| TikTok-comments | Business API (Accounts-scope) | Ophalen/pollen | Reply/hide/delete | Accounts API Access Application Form | 1–2 dagen + review | Business Account, app autoriseren |
| TikTok Shop-chat | Customer Service API | Ja + webhooks | Ja | Partner Center-app | 2–3 dagen | Alleen bij verkoop op TikTok Shop NL |
| E-mail | Gmail API / Graph / IMAP / inbound-parse | Ja | Ja | Geen | ½–2 dagen | Mailhost noemen; admin-toegang; DNS voor SPF/DKIM/DMARC |
| Shopify Inbox-chat | Geen API | Nee | Nee | — | — | Apart houden of vervangen |

**Te verzamelen geheimen/config**

```
# Shopify
SHOPIFY_STORE_DOMAIN=farmersatelier.myshopify.com
SHOPIFY_API_VERSION=2026-07
SHOPIFY_CLIENT_ID= / SHOPIFY_CLIENT_SECRET=          # Dev Dashboard-app (client credentials → 24u-token)
SHOPIFY_ADMIN_TOKEN=shpat_…                          # alleen bij hergebruik van een legacy custom app
SHOPIFY_WEBHOOK_SECRET=
SHOPIFY_LOCATION_ID=gid://shopify/Location/…
# Meta
META_APP_ID= / META_APP_SECRET= / META_VERIFY_TOKEN=
META_PAGE_ID= / META_PAGE_ACCESS_TOKEN= / META_IG_ACCOUNT_ID= / META_GRAPH_VERSION=v25.0
# TikTok (indien goedgekeurd)
TIKTOK_APP_ID= / TIKTOK_APP_SECRET= / TIKTOK_BUSINESS_ID= / TIKTOK_ACCESS_TOKEN=
# E-mail (één van)
GMAIL_SERVICE_ACCOUNT_JSON= / GMAIL_IMPERSONATE=support@farmersatelier.nl
IMAP_HOST= / IMAP_USER= / IMAP_PASSWORD= / SMTP_HOST= / SMTP_USER= / SMTP_PASSWORD=
# Vervoerders / overig
POSTNL_API_KEY= / DHL_PARCEL_API_KEY=
ANTHROPIC_API_KEY=
PUBLIC_BASE_URL=https://inbox.farmersatelier.nl      # of cloudflared-URL in dev
```

---

## Geraadpleegde bronnen

Shopify: https://shopify.dev/docs/api/usage/versioning · https://shopify.dev/docs/api/admin-rest ·
https://shopify.dev/docs/apps/build/apis/graphql-admin/rate-limits ·
https://shopify.dev/docs/apps/launch/protected-customer-data ·
https://shopify.dev/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard ·
https://shopify.dev/docs/apps/build/dev-dashboard/get-api-access-tokens ·
https://help.shopify.com/en/manual/apps/app-types/custom-apps ·
https://community.shopify.dev/t/enable-protected-customer-data-access-for-a-custom-app-created-in-the-dev-dashboard-no-ui-option-available/35445 ·
https://shopify.dev/docs/api/admin-graphql/latest/objects/Order (en Customer, Fulfillment,
Return, ReturnStatus, FulfillmentEventStatus, orderUpdate, refundCreate, orderCancel,
returnCreate, fulfillmentTrackingInfoUpdate, webhookSubscriptionCreate) ·
https://shopify.dev/docs/api/webhooks/latest · https://shopify.dev/docs/apps/build/webhooks/verify-deliveries ·
https://help.shopify.com/en/manual/shopify-flow/reference/actions/send-http-request ·
https://help.shopify.com/en/manual/orders/refunds-returns/returns ·
https://help.shopify.com/en/manual/shipping/understanding-shipping/shipping-carriers ·
https://community.shopify.com/t/is-there-a-way-to-read-the-inbox-conversations-via-api-and-make-it-a-richer-support-avenue/682015

Vervoerders: https://developer.postnl.nl/integration-with-postnl/api-overview/send-and-track/shippingstatus-webservice/ ·
https://api-gw.dhlparcel.nl/docs/guide/chapters/05-track-and-trace.html ·
https://www.17track.com/en/pricing · https://www.aftership.com/pricing/tracking · https://www.trackingmore.com/pricing

Meta: https://developers.facebook.com/docs/instagram-platform/overview/ ·
https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/ (messaging-api,
private-replies, comment-moderation, business-login) ·
https://developers.facebook.com/docs/instagram-platform/webhooks ·
https://developers.facebook.com/docs/messenger-platform/instagram/get-started ·
https://developers.facebook.com/docs/messenger-platform/instagram/app-review/ ·
https://developers.facebook.com/docs/messenger-platform/changelog/ ·
https://developers.facebook.com/docs/graph-api/overview/access-levels/ ·
https://developers.facebook.com/docs/development/release/business-verification/ ·
https://developers.facebook.com/docs/features-reference/human-agent ·
https://developers.facebook.com/docs/graph-api/webhooks/reference/page/ ·
https://developers.facebook.com/docs/graph-api/reference/v24.0/comment ·
https://developers.facebook.com/docs/business-management-apis/system-users/install-apps-and-generate-tokens/

TikTok: https://business-api.tiktok.com/portal/docs/business-messaging-api/v1.3 ·
https://business-api.tiktok.com/portal/docs/direct-messages/v1.3 ·
https://business-api.tiktok.com/portal/docs/reply-to-a-comment/v1.3 ·
https://partner.tiktokshop.com/docv2/page/customer-service-api-overview ·
https://newsroom.tiktok.com/tiktok-shop-expands-across-europe?lang=en-150

E-mail: https://developers.google.com/workspace/gmail/api/guides/push ·
https://developers.google.com/workspace/gmail/api/guides/sending ·
https://developers.google.com/workspace/gmail/api/auth/scopes ·
https://developers.google.com/identity/protocols/oauth2/service-account ·
https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/deprecation-of-basic-authentication-exchange-online ·
https://learn.microsoft.com/en-us/graph/outlook-change-notifications-overview ·
https://postmarkapp.com/developer/webhooks/inbound-webhook · https://resend.com/docs/dashboard/receiving/introduction ·
https://developers.cloudflare.com/email-routing/email-workers/ · https://github.com/mailgun/talon ·
https://github.com/alfonsrv/mail-parser-reply
