# Onderzoek 1 — Hoe Gorgias functioneel werkt

Doel: begrijpen wat Gorgias precies doet, van binnenkomend bericht tot gesloten ticket,
zodat we dezelfde mogelijkheden kunnen nabouwen voor Farmers Atelier (zonder de
functies die wij nooit gebruiken).

Bronnen: helpcenter.gorgias.com, developers.gorgias.com, updates.gorgias.com, gorgias.com
en secundaire bronnen (Macha, eesel, Ringly, reviews). Opgehaald 25-09-2026. Feiten uit
secundaire bronnen zijn zo gemarkeerd; niet-verifieerbare punten staan als [unverified].

---

## 1. Datamodel

**Objecten in de API.** `tickets`, `messages`, `customers`, `events`, `integrations`,
`widgets`, `macros`, `rules`, `tags`, `teams`, `users`, `views`, `custom-fields`
(ticket + klant), `satisfaction-surveys`, `jobs` (bulk), `files/upload`, `search`,
`statistics`.

**Ticket.** Velden: `channel` (email, chat, phone, sms, facebook, instagram, whatsapp,
api, help-center…), `via` (hoe binnengekomen: api, chat, contact_form, email,
facebook-messenger, facebook-mention, instagram…), `status` (`open` | `closed`; de UI
toont daarnaast snoozed/spam/trash via `snooze_datetime`, `spam`, `trashed_datetime`),
`priority` (`low` | `normal` | `high` | `critical`, standaard normal), `subject`,
`language`, `external_id`, `from_agent`, `customer{}`, `assignee_user`, `assignee_team`
(beide tegelijk mogelijk), `messages[]`, `tags[]`, `custom_fields[]`, `meta` (vrije JSON)
en tijdstempels `created/opened/closed/last_message/last_received_message/snooze/
trashed/updated_datetime`.

**Message.** `channel`, `via`, `from_agent` (bool), `public` (false = interne notitie),
`body_text`, `body_html`, `subject`, `source{type, from{name,address}, to[], cc[]}` met
`source.type` ∈ email, facebook, instagram-direct-message, whatsapp, sms, chat,
internal-note…; `sender{id,email,name}`, `receiver{}`, `external_id`, `attachments[]`,
`headers{}`, `meta`, en `sent/created/deleted/failed_datetime`, `last_sending_error`.

**Customer.** `name`, `email`, `channels[{type: email|phone|…, address}]`,
`integrations{}` (externe data per koppeling, bv. `integrations.shopify.customer`,
`.orders[]`), custom fields, notities. Meerdere kanaaladressen hangen aan één klant:
dát is het mechanisme voor kanaaloverstijgende identiteit.

**Event.** `id, context (uuid), type, object_type, object_id, user_id (null =
automatisch), data{}, created_datetime`. De lijst (~130 types) is een goed sjabloon voor
onze eigen auditlog: `ticket-created/updated/closed/reopened/assigned/unassigned/
snoozed/merged/split/tags-added/tags-removed/marked-spam/trashed/viewed/handed-over`,
`ticket-message-created/updated/deleted/failed`, `customer-created/updated/merged`,
`macro-applied`, `rule-executed`, `action-executed`,
`facebook-comment-created/hidden/unhidden/liked/deleted`, `satisfaction-survey-sent/
responded`, `user-mentioned`.

**Overig.** Tags (vrije strings, samenvoegbaar), Views (opgeslagen filters, gedeeld/privé,
in secties), Macro's (standaardantwoord + acties), Rules (WHEN/IF/THEN met
prioriteitsvolgorde), Integrations (kanaalkoppelingen en HTTP-integraties), Widgets
(zijbalksjablonen), Ticket Fields (dropdown met `::`-nesting, number, text, ja/nee;
optioneel / verplicht / voorwaardelijk verplicht vóór sluiten), Teams, Users.

**Klanten samenvoegen.** Shopify-klanten worden gematcht op **e-mail eerst, dan
telefoonnummer uit het standaard verzendadres**. Social-identiteiten (IG/FB-ID's) maken
aparte klantrecords; Gorgias toont een **automatische merge-suggestie** als het twee
profielen dezelfde persoon acht, en agents kunnen handmatig samenvoegen door te zoeken op
ordernummer, e-mail, telefoon of naam en per veld te kiezen wat blijft. Samenvoegen is in
principe onomkeerbaar. Advies: eerst in Shopify samenvoegen, dan in Gorgias. De exacte
heuristiek voor suggesties is niet gedocumenteerd [unverified].

**Ticketstatus en levenscyclus.** Werkstatussen: **Open, Closed, Snoozed** (plus Spam en
Trash). Een klantantwoord op een gesloten ticket **heropent** het; komt het antwoord
**10+ dagen** na sluiting (e-mail), dan **splitst** Gorgias automatisch naar een nieuw
ticket, in beide tijdlijnen gelinkt (metrics/CSAT van het origineel blijven). Social DM/
chat/WhatsApp/SMS gebruiken een venster van **3 dagen**. Snooze: 1u/3u/6u/1d/3d/1w/
custom; snoozed tickets tonen een aftelbadge en heropenen bij verlopen (rule-trigger
beschikbaar). Toewijzing = team en/of persoon; "Unassigned" is standaard. Sneltoetsen:
r reply, m macro, c close, o reopen, # delete.

## 2. Kanaalflows van begin tot eind

### E-mail
Drie koppelmethodes: **Gmail OAuth**, **Outlook/Microsoft 365 OAuth** of **automatisch
doorsturen** naar `jouwnaam@gorgias.io`. OAuth wordt aanbevolen onder ~500 mails/dag.
Uitgaande mail via OAuth loopt via de Gmail/Outlook-API (komt dus in "Verzonden"); er is
een schakelaar "Send emails via Gorgias email delivery platform" zodra het domein met
SPF + DKIM is geverifieerd (enige optie bij doorsturen). Agents kiezen het from-adres per
antwoord als er meerdere zijn. Handtekeningen per e-mailintegratie (niet per agent) met
`current_user`-variabelen. Twee jaar historie importeerbaar. Antwoorden vanuit Gmail zelf
verschijnen wel in het ticket maar sluiten het niet. Threading gebruikt provider-threading
en tijdvensters; **geen bewijs dat Gorgias een ticket-ID in de onderwerpregel zet** — het
10-dagen-splitmechanisme plus headers lijkt de methode [header-details unverified]. Agents
kunnen de gequote thread bewerken vóór versturen. Outlook-regels voor doorsturen zijn
"niet betrouwbaar". Contactformulier-mails via Outlook belanden in spam tenzij gewhitelist.

### Instagram (DM's, comments, mentions)
Gekoppeld via de Facebook-app: vereist IG Business/Creator-account gekoppeld aan een
Facebook-pagina en een admin-login. Je kiest welke activiteit tickets maakt: **DM's,
story-mentions, story-replies, post-comments, ad-comments, mentions in captions/
comments**.
- **DM's**: één ticket per gesprek; een antwoord **3+ dagen** na het laatste bericht maakt
  een nieuw ticket (historie blijft in de klanttijdlijn). Meta-venster: **7 dagen** voor
  menselijke agents ("7 dagen voor agents, 24 uur voor AI") en **maar één uitgaand
  bericht totdat de klant antwoordt**. Limieten: 1.000 tekens, alleen afbeeldingen, tekst
  en bijlage niet in één bericht; geen reacties; verwijderde berichten worden ook in
  Gorgias ingetrokken; links/emoji-only/herhaalde tekst kunnen door IG als spam worden
  gezien; stories niet te renderen (story-mention komt als botbericht met link, 24 u
  geldig). DM-tickets zijn niet samen te voegen met andere DM-tickets. Gorgias kan geen
  DM's beginnen. Geen IG-historie-import.
- **Comments**: **één ticket per top-level comment** (posts en ads). Acties: publiek
  antwoorden, **verbergen** (alleen zichtbaar voor de schrijver), liken, naar post springen,
  **privé antwoorden** (maakt nieuw DM-ticket; alleen binnen 7 dagen). Reacties-op-reacties
  worden geïmporteerd maar zijn niet te beantwoorden; ad-comments alleen top-level; een op
  Instagram verwijderde comment werkt het ticket niet bij; geen antwoorden tijdens Live.
  Verwijderen als actie op IG niet gevonden in de docs [unverified].
- **Mentions**: ticket bij vermelding van je handle in caption, comment of story.
- AI Agent op IG/Messenger is in bèta.

### Facebook Messenger en comments
Messenger: zelfde 7-dagen/3-dagen-regels, limiet 2.000 tekens (lange antwoorden worden
gesplitst). Comments op pagina-posts, ads en aanbevelingen maken elk een ticket in het
kanaal "Facebook Comment"; acties: antwoorden, verbergen, liken, privé antwoorden. Rules
hebben acties **Hide Facebook comment** en **Like Facebook comment**. Een alleen-gelikete
comment is niet factureerbaar. 30 dagen Facebook-historie importeerbaar als gesloten tickets.

### TikTok
Gorgias ondersteunt **alleen TikTok Shop** (VS, Engels): koper-verkoper-chat gekoppeld
aan orders, plus een orderzijbalk met tracking en retour/refundstatus. **Organische
TikTok-DM's en videocomments worden NIET ondersteund.** Details: tickets via het
API-kanaal, max 2.000 tekens, afbeeldingen ≤10 MB, MP4 ≤100 MB, geen audio, links niet
klikbaar aan TikTok-kant, geen uitgaande initiatie, sluiten niet gesynchroniseerd,
inkomende berichten eenzijdig naar Engels vertaald.

### Shopify-chatwidget / contactformulier / helpcenter
Chat via "Quick install" (theme app embed) of snippet/GTM; online/offline-modus,
openingstijden, e-mail-capture, taaldetectie, huisstijl, chat in checkout, verbergen per
pagina. Chattickets heropenen binnen 3 dagen; chatgesprekken sluiten automatisch na 10
minuten inactiviteit (met AI). Contactformulier vereist naam, onderwerp, e-mail, bericht;
onderwerpopties zijn configureerbaar en kunnen rules sturen; bijlagen; maakt ticket met
kanaal `help-center`. Helpcenter: meertalig (~15 talen), categorieën/artikelen met SEO,
eigen domein, ingebedde chat en een **Order Management-portaal** (track/retour/annuleren/
probleem melden) met **6-cijferige eenmalige code via e-mail of SMS**.

### WhatsApp / SMS (kort)
WhatsApp: 24-uursvenster, daarbuiten alleen door Meta goedgekeurde tekst-templates;
3-dagen-heropenvenster; media; AI Agent in bèta. SMS: betaalde add-on (VS/CA, VK).

## 3. De Shopify-zijbalk

**Getoond (configureerbaar via drag-and-drop):** naam/e-mail/telefoon/adres, locatie en
tijdzone, Shopify-tags, lifetime spend, aantal orders, klantnotities (tweezijdig
gesynchroniseerd), metafields, en per order: nummer, datum, betaalstatus,
fulfillmentstatus, regels met realtime voorraad, totalen, kortingen, verzendadres,
trackingnummer/-status, refunds, ordernotities/tags, draft orders ("D#"). Widgets van
derden (Loop Returns: datum, status, artikelen, redenen, tracking; Recharge; Yotpo; eigen
HTTP-widgets) staan eronder.

**Agent-acties:** Order aanmaken; Order dupliceren (standaard 100 % korting + €0
verzending); Annuleren (aantallen/verzending/bedrag om te refunden, reden, restock,
notificatie); Refund (aantallen standaard 0 zodat niets per ongeluk terug in voorraad
gaat; eigen bedrag; notificeren; één gateway; geen giftcard-orders); Order bewerken (niet
gearchiveerd, niet >60 dagen oud, zelfde valuta); Draft order; Verzendadres bewerken;
Productlinks/-kaarten invoegen; Klant- en ordertags (gesynchroniseerd); Eenmalige
kortingscodes en giftcards (via macro-acties). Retouren zijn niet native — Loop/ReturnGO-
widgets tonen status en linken naar het portaal.

## 4. AI Agent (en de oudere Automate-add-on)

**Pipeline (volgens Gorgias):** (1) bericht evalueren en veiligheidscheck (phishing/spam/
dreigingen; uitgesloten onderwerpen); (2) bronnen kiezen: kennisbronnen, acties van
gekoppelde apps, sales playbooks, parallelle taken terwijl de klant op de hoogte blijft;
(3) antwoord genereren in de ingestelde toon en kanaalopmaak; **elk antwoord gaat door
een interne QA-stap door een tweede model en wordt alleen verstuurd boven een
confidence-drempel**, anders overdracht. Rules draaien eerst, daarna AI Agent.

**Kennisbronnen:** Guidance (≤100; beleidsdocumenten in gewone taal, niet klantgericht,
gaat vóór helpcenter-artikelen), helpcenter-artikelen, automatisch gecrawlde website
(omgezet naar Q&A-snippets), losse URL's, geüploade PDF/DOCX/PPTX/XLSX,
Shopify-productcatalogus (titel, omschrijving, afbeelding, varianten; alleen actieve,
gepubliceerde producten) en Shopify-order/klantdata. Afbeeldingen in kennis worden niet
gelezen.

**Skills (model 2026):** skill = ingebouwde **intent-triggers** (elke intent hoort bij
max. één skill) + **instructies** (≤30.000 tekens, WHEN/IF/THEN-stijl, één actie per stap,
"geef elk pad een afronding") + ingebedde **acties** + schakelaar voor aanvullende kennis.
Skills worden geschreven, getest in een Playground (niet gefactureerd), ingeschakeld,
geversioneerd en per skill gemeten (volume, succes, CSAT, overdracht).

**Acties (Shopify):** Order annuleren, Verzendadres bewerken, Artikel verwijderen,
Artikel vervangen (één wissel), Gratis opnieuw sturen (dupliceren), Ordernotitie —
**allemaal alleen op onvervulde orders**, met expliciete klantbevestiging vóór uitvoering.
Expliciet níet automatisch: bijbetaling bij duurdere vervanging, herberekening btw/
verzending bij adreswijziging, meervoudige wissels, annulering doorzetten naar een 3PL.
Andere connectors: Loop, Recharge/Skio, ShipStation/ShipBob/ShipHero/ShipMonk, custom
HTTP-acties. Tags: `ai_executed_action`, `ai_failed_action`.

**Overdracht:** ingebouwde, niet-uitschakelbare triggers (boosheid/frustratie, expliciet
om een mens vragen, zelfbeschadiging, dreigingen, juridische dreigingen, financiële
accountgegevens, lage confidence, geen relevante kennis) + geconfigureerde
overdrachtsonderwerpen + rule-sjabloon "Prevent AI Agent from answering" (tag `ai_ignore`,
per afzender, tag of zin). Globale schakelaar of de klant over de overdracht wordt
geïnformeerd. Overgedragen tickets krijgen `ai_handover`.

**Auto-sluiten/snoozen zonder antwoord:** sluit (`ai_close`) bij bedankjes, spam,
auto-replies/bounces, nieuwsbrieven, phishing-achtige tekst, buiten scope; snoozet
(`ai_snooze`) bij een kale "Hoi", als het zelf info vroeg, of als de klant uitstelt.
Levenscyclus-tags: `ai_processing, ai_answered, ai_snooze, ai_close, ai_handover,
ai_ignore`, met standaard view-groep "AI Agent" (All / Processing / Snooze / Close /
Handover / Ignore / To review).

**Toon, naam, taal:** Friendly / Professional / Sophisticated / Custom (≤5.000 tekens);
hernoembaar; detecteert de taal van de klant en antwoordt daarin, of vaste taal.

**Ontbrekende info en vision:** Guidance/skills instrueren om ordernummer of foto's te
vragen; Vision leest foto's voor schade/ontbrekende artikelen, haalt ordernummers uit
screenshots en herkent producten (e-mail, chat, IG/Messenger, WhatsApp; niet SMS).

**WISMO-flow (Gorgias' eigen guidance-sjabloon):** order vinden (via klantmatch of nummer
vragen) → als tracking bestaat: trackinglink sturen → anders ETA berekenen uit
verzendmethode → status benoemen (processing/shipped/delivered) → bij vertraging excuses
en nieuwe schatting → vermiste/verkeerd getrackte pakketten escaleren. Aangevuld door het
oudere rule-sjabloon: <20 dagen & tracking → auto-antwoord met link en sluiten; <6 dagen
& geen tracking → "in behandeling" en sluiten; >5 dagen & geen tracking → tag urgent/
not-shipped, geen antwoord; geen order → om details vragen.

**Automate (ex "Automation Add-on"):** Flows (meerstaps klik-Q&A op chat/helpcenter/
contactformulier, ≤6 opties per stap, HTTP-request-stappen met JSONPath), Order
Management (track/retour/annuleren/probleem melden; retour/annulering zijn **verzoeken**
die een agent goedkeurt met macro-acties tenzij Loop), Article Recommendations (alleen
chat; uitgefaseerd voor Shopify na 30-01-2026), Quick Responses (gestopt).

**Prijzen:** helpdesk-plannen per **beantwoord ticket** (ruwweg Starter $10/50, Basic
$60/300, Pro $360/2.000, Advanced $900/5.000 per maand; ~$0,36–0,40 overage — cijfers van
derden), nooit per seat. Factureerbaar = minstens één bericht verstuurd vanuit Gorgias
(mens, AI of rule). AI Agent per **automated interaction** (~$0,90–1,00; soms $1,50
overage): een ticket volledig door AI afgehandeld waarbij **binnen 72 uur geen mens nodig
was** (een "dankjewel" telt niet als onderbreking). Beide kunnen op één ticket gelden.

## 5. Intent- en sentimentdetectie

Draait op elk **klantbericht** (niet op interne notities of API-berichten), meerdere
intents per bericht mogelijk, leeg bij lage confidence; intents zijn handmatig te
bewerken, sentiment niet. Talen: 16 voor de klassieke intents (waaronder Nederlands).

**Klassieke intentlijst (23, nog gedocumenteerd voor rules):** Discount/Request,
Exchange/Request, Exchange/Status, Order/Cancel, Order/Change, Order/Damaged,
Order/Wrong, Feedback, Other/No-Reply, Other/Question, Other/Thanks, Product/Question,
Product/Recommendation, Stock/Request, Refund/Request, Refund/Status, Return/Request,
Return/Status, Shipping/Change, Shipping/Delivery-Issue, Shipping/Policy,
Shipping/Status, Subscription/Cancel, Subscription/Change.

**Nieuwere AI-Agent-taxonomie (40+ intents, 15 categorieën):** Account (Deletion, Login,
Registration, Update, Other), Exchange, Feedback, Marketing, Order (Cancel, Damaged,
Edit, Missing Item, Payment, Replacement, Refund, Status, Wrong Item, Other), Product,
Promotion & Discount, Return, Shipping, Subscription, Warranty, Wholesale, Other.
Opgeslagen in een beheerd ticketveld "AI Intent".

**Sentiment:** basisdoc: Positive / Negative / Neutral; changelog toont het huidige model
als Positive, Negative, Urgent (verving "need-human"), Threatening (hernoemd van
"menacing"), Promoter (zeer positief). Rules gebruiken "Message Sentiments" en "Message
Intents" als condities; het sjabloon "Identify intents and sentiments" tagt tickets zodat
Views erop kunnen filteren (views filteren niet direct op intent, alleen op tags/velden).

## 6. Rules-engine en macro's

**Structuur:** WHEN (trigger) → IF/AND/OR (condities) → THEN (acties) → optioneel ELSE;
rules hebben een prioriteitsvolgorde en de pipeline logt `rule-executed`-events.
- Triggers: Ticket Created, Ticket Updated, Ticket Assigned To User, Ticket Snooze Delay
  Ends, New Message In Ticket, Satisfaction Survey Responded.
- Condities: Message (bijlagen, body bevat/begint/eindigt/is, kanaal, datum, from agent,
  integratie, intents, public, via, ontvanger, afzender, sentiments), Ticket (assignee,
  kanaal, datum, taal, laatste bericht, prioriteit, heropend, CSAT, status, onderwerp,
  tags, custom fields, via), Customer (e-mail, custom fields), Shopify laatste order
  (datum, betaalstatus, fulfillmentstatus, tags, totaal, laatste fulfillment-datum/
  verzendstatus/tracking, verzendland), Shopify-klant (aanmaakdatum, aantal orders, tags,
  totaal besteed), metafields, Instagram-profiel (volgt elkaar, aantal volgers, username,
  geverifieerd), self-service (order-management-flow, winkel).
- Acties: E-mail sturen, Klant antwoorden, Interne notitie, Macro toepassen, Tags
  toevoegen/verwijderen/resetten, Onderwerp, Status, Prioriteit, Ticketveld, Klantveld,
  Snoozen, Agent toewijzen, Team toewijzen, Verdelen over teams (round-robin), Ticket
  verwijderen, Facebook-comment verbergen/liken, Uitsluiten van auto-merge/CSAT.
- Sjabloonvoorbeelden: VIP-tag ($1000+ of 3 orders), kantoortijd-tag, orderstatus-
  auto-antwoord, autoresponder, buiten-kantoortijd, pre-orderstatus, retourportaal-link,
  annuleringsverduidelijking, Instagram-giveaway auto-sluiten (geen vraagwoorden),
  niet-support IG-comments auto-sluiten, auto-toewijzen per kanaal.

**Macro's:** standaardantwoord + acties, ingevoegd met `m`, variabelen via dropdown,
Jinja-achtige templating met filters. Variabelen: `{{ticket.id}}`, `{{ticket.subject}}`,
`{{ticket.customer.firstname}}`, `{{current_user.firstname}}`,
`{{ticket.customer.integrations.shopify.orders[0].name/total_price/
line_items[0].title/fulfillments[0].tracking_url}}`, en HTTP-integratiedata. Macro-
acties: tags, status/prioriteit/onderwerp, toewijzen, snoozen, interne notitie, velden,
doorsturen, bijlagen, HTTP-hook; Shopify: annuleren, dupliceren, refund (verzending/
deels), adres bewerken, giftcard; Recharge. Acties worden pas uitgevoerd bij versturen,
zijn te previewen/bewerken, gelogd als events; een mislukte actie heropent het ticket.

## 7. Views / inbox

Standaardviews: Assigned to me, Unassigned, All, Snoozed, Closed, Trash, Spam. Gedeelde
views (max 500) en privé-views (≤20 per agent), in secties. Een view = filter + operator +
waarde op elk ticketattribuut, met kolommen per view en live tellers; een ticket kan in
meerdere views staan. Agent-workflow: collision-banner "Also viewing", interne notities
met @mentions, snooze, tags, verplichte velden vóór sluiten, merge (bron verwijderd,
berichten chronologisch ineengevlochten; niet omkeerbaar), **auto-merge** (open tickets
van dezelfde klant binnen N ≤180 dagen; uitsluiting via rule/macro) en auto-split
(10 dagen e-mail / 3 dagen messaging). CSAT-enquête na sluiten. Klacht: geen
"oudste eerst" als standaardsortering.

## 8. Helpcenter / kennis

Helpcenter = categorieën + artikelen, meertalig, SEO, eigen domein, contactformulier,
chat, Order Management-portaal, optioneel AI-gegenereerde artikelen. Guidance gaat vóór
artikelen; Skills gaan vóór beide bij gematchte intents als hun kennis-schakelaar uit
staat. **Opportunities** (bèta) mint overgedragen/onopgeloste gesprekken en stelt "vul
kennisgat" en "los conflict op" voor, ter goedkeuring.

## 9. Rapportage

Dashboards: Overview (CSAT, FRT, RT, open/gesloten, handle time, piekuren), Support
Performance (agentproductiviteit, one-touch, volume per kanaal), Agents, Tickets/
Insights (velden, tags, macro's, intents), Channels, Tags, Satisfaction, Revenue (Shopify;
conversie, omzet uit support), AI Agent (automatiseringsgraad, automated interactions,
bespaarde kosten/tijd, overdrachten, FRT-daling; per onderwerp succes, CSAT en
"verbeterpotentieel"), Live (realtime wachtrij), Flows drop-off, Auto QA (AI-scoring op
oplossing, communicatie, taal, accuraatheid, efficiëntie, brand voice). Definities:
FRT = eerste klantbericht → eerste agentantwoord; RT = eerste bericht → gesloten;
one-touch = gesloten met één antwoord. Lagere plannen: 90 dagen historie (secundair).

## 10. Leerlussen

Geen autonoom leren uit productiedata. Signalen: duim omhoog/omlaag op elke gebruikte
kennisbron (verhoogt/verlaagt prioriteit), Bad/Okay/Good-gespreksbeoordeling, "Show
reasoning", inline bewerken van Guidance/artikelen vanuit de AI Feedback-tab, "Use in
similar requests" bij ontbrekende kennis, een "To review"-view, Opportunities,
per-skill-metrics. Agent-bewerkingen van AI-concepten zijn níet gedocumenteerd als
trainingssignaal [unverified].

## 11. Bekende zwaktes om te verslaan

- **Prijsvolatiliteit**: per ticket + per resolution, dubbel factureren van één ticket,
  overage; "success tax" bij salespieken; CSM zonder bericht weggehaald.
- **AI-kwaliteit**: "klinkt generiek", "niet echt te trainen", hallucinaties, regressie
  gemeld jan-2026; complexe setup van rules/kennislagen.
- **Support**: geen livechat voor Gorgias' eigen support, 48 uur antwoordtijd.
- **Productgaten**: rapportagediepte, 90 dagen retentie, geen "oudste eerst", live cart
  weggehaald, zwakke meertaligheid, "buggy", trage feature-ontwikkeling.
- **Kanaalgaten die wij kunnen benutten**: geen organische TikTok-DM's/comments; IG
  reply-op-reply onmogelijk (Meta-limiet, ook voor ons); IG-DM-tickets niet samen te
  voegen; tekst+bijlage gesplitst op IG/WhatsApp; geen uitgaande DM's.

## 12. Publieke API en webhooks (vorm om te spiegelen)

Basis `https://<subdomain>.gorgias.com/api/`, JSON, Basic auth of OAuth2; 40 req/20 s;
cursor-paginering. Resources: `/customers` (+`/merge`), `/tickets` (+`/messages`,
`/tags`), `/messages`, `/tags`, `/macros`, `/rules`, `/integrations`, `/widgets`,
`/teams`, `/users`, `/views`, `/events`, `/satisfaction-surveys`, `/custom-fields`,
`/jobs`, `/upload`, `/search`, `/statistics`.

**Een extern kanaal inschieten:** klant aanmaken/vinden met `channels[{type, address}]`,
dan `POST /api/tickets` met `channel`, `via:"api"`, een bericht met `source{type,
from{address}, to[]}`, `from_agent:false`, `body_text/html`, `external_id`. Uitgaand: een
**HTTP-integratie** (`type:"http"`, `http{url, method, headers, triggers{ticket-created,
ticket-updated, ticket-message-created…}}`) met Jinja-templates over ticket/bericht/klant.
Levering: 5 s timeout, tot 3 retries (10/20/40 s), automatisch uit na 500 opeenvolgende
fouten. Zijbalkwidgets zijn declaratieve JSON-bomen (`type: card|text|list|date`, `path`
in het HTTP-antwoord).

**Minimale spiegel voor ons:** `customers{channels[]}`, `tickets`, `messages{source, via,
public, from_agent}`, `events` (append-only), `tags`, `views`, `macros`,
`rules{trigger, conditions, actions, priority}`, `integrations`, plus webhook-topics
`ticket.created/updated/closed/handed_over`, `message.created/failed`,
`customer.created/updated/merged`.

---

## Wat we hieruit overnemen voor Farmers Atelier

1. Datamodel 1-op-1 spiegelen: customers met kanaal-identiteiten, conversations (tickets)
   met `channel`/`via`/`status`/`priority`, messages met `public`/`from_agent`/`source`,
   een append-only events-tabel als audittrail, tags, views (opgeslagen filters), macro's
   en rules.
2. Statusmodel: open / snoozed / closed (+ spam), heropenen bij klantantwoord, auto-split
   na 10 dagen (e-mail) of 3 dagen (social).
3. Klantmatching: e-mail eerst, dan telefoon; social-ID's als aparte identiteiten met
   merge-suggestie.
4. Zijbalk: precies de velden uit §3, plus acties met goedkeuring.
5. AI-pipeline: veiligheidscheck → bronnen (guidance, FAQ, catalogus, orderdata) →
   antwoord in toon en kanaalopmaak → **tweede-model-QA met confidence-drempel** →
   versturen of overdragen. Intent-taxonomie uit §5, sentiment met "urgent" en
   "threatening" als aparte waarden.
6. AI-levenscyclus-tags (`ai_answered`, `ai_snooze`, `ai_close`, `ai_handover`,
   `ai_ignore`) en bijbehorende views.
7. Rules: WHEN/IF/THEN met dezelfde triggers, condities en acties (subset).
8. Niet nabouwen: helpcenter-website, chatwidget, WhatsApp/SMS/voice, TikTok Shop,
   revenue-rapportage, Flows, Auto QA.
