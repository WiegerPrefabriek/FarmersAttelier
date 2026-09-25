# OPENSTAANDE ZAKEN — wat ik nog van Wieger nodig heb

Alles hieronder is nodig om van "lokaal met nepdata" naar "echt gekoppeld" te gaan.
De app werkt nu al volledig met mock-data; niets hiervan blokkeert het testen van de
inbox, de AI-flow of het dashboard. Per onderwerp: wat, waarom, waar te vinden, wat te
doen, en wat je mij daarna stuurt. Stuur nooit wachtwoorden of sleutels via chat of
mail: zet ze in `.secrets.json` (staat in `.gitignore`) of in een wachtwoordmanager.

Volgorde van belang: **1 (AI-sleutel) → 2 (Shopify) → 3 (e-mail) → 4 (Meta) → 5
(kennisbank) → 6 (fulfillment) → 7 (TikTok) → 8 (GitHub) → 9 (Python-upgrade).**

---

## 1. ANTHROPIC (AI) — nodig om de echte AI aan te zetten

**Wat:** een API-sleutel van Anthropic (Claude).
**Waarom:** zonder sleutel draait de AI in mock-modus (trefwoorden + sjablonen). De echte
analyse en conceptantwoorden komen van Claude.
**Wat je doet:**
1. Ga naar https://console.anthropic.com en log in (of maak een account).
2. Klik links op **API Keys** → **Create Key** → naam "farmers-atelier-support".
3. Kopieer de sleutel (begint met `sk-ant-`). Je ziet hem maar één keer.
4. Zet hem in `.secrets.json` onder `"anthropic": {"api_key": "..."}` (zie
   `.secrets.json.example`), óf exporteer `ANTHROPIC_API_KEY` in je terminal.
5. Zet bij **Billing** een maandlimiet (bv. €50) zodat het nooit uit de hand loopt.
**Stuur mij daarna:** alleen "gedaan". Ik hoef de sleutel niet te zien.

---

## 2. SHOPIFY — klanten, orders, producten, voorraad lezen

**Wat:** een "custom app" op je Shopify-winkel met leesrechten, plus de winkel-URL.
**Waarom:** daarmee ziet de inbox naast elk gesprek de klant, orders, betaal- en
verzendstatus, tracking, retouren en refunds. Later ook acties (annuleren, refund).
**Let op:** sinds 1 januari 2026 maak je custom apps niet meer in de Shopify-admin maar
in het **Dev Dashboard**. Dit moet de **eigenaar** van de winkel doen (je broertje) of
iemand met de rechten "App development → Develop".
**Wat je doet:**
1. Ga naar https://dev.shopify.com/dashboard/ en log in met het account van de
   winkeleigenaar.
2. Klik **Apps** → **Create app** → **Start from Dev Dashboard** → naam
   "Farmers Atelier Support" → **Create**.
3. Tab **Versions** → bij **Scopes** vink aan:
   `read_customers, read_orders, read_all_orders, read_products, read_inventory,
   read_locations, read_fulfillments, read_merchant_managed_fulfillment_orders,
   read_assigned_fulfillment_orders, read_third_party_fulfillment_orders,
   read_shipping, read_returns, read_draft_orders, read_discounts`
   (later, voor acties: `write_orders, write_returns, write_customers`).
   Webhooks API version: `2026-07`. Klik **Release**.
4. Tab **Home** → **Install app** → kies de Farmers Atelier-winkel → **Install**.
5. Tab **Settings** → kopieer **Client ID** en **Client secret**.
6. Zet in `.secrets.json`:
   `"shopify": {"store_domain": "farmersatelier.myshopify.com", "client_id": "...",
   "client_secret": "..."}` (de app haalt daar zelf elke 24 uur een token mee op).
   Heb je nog een oude custom app van vóór 2026 met een `shpat_…`-token? Dan volstaat
   `"admin_token": "shpat_..."`.
7. Check het abonnement: voor klantgegevens (naam/adres/e-mail) via een custom app
   vereist Shopify het **Grow-plan of hoger**. Zit de winkel op Basic, laat het me weten.
**Stuur mij daarna:** de `myshopify.com`-domeinnaam en "gedaan". Plus: welk Shopify-plan.

---

## 3. E-MAIL — support@ in de inbox

**Wat:** het centrale klantenservice-adres en waar de mail van farmersatelier.nl draait.
**Waarom:** alle mails moeten in het systeem komen en antwoorden moeten als normale
mail vanuit Farmers Atelier vertrekken; antwoorden van de klant komen in hetzelfde
gesprek terug.
**Wat je doet (eerst uitzoeken):**
1. Welk adres wordt het? Voorstel: `support@farmersatelier.nl`. Bestaat het al?
2. Waar draait de mail? Kijk in het DNS of hosting-paneel van farmersatelier.nl naar de
   **MX-records**, of vraag het je broertje:
   - `aspmx.l.google.com` → **Google Workspace** (makkelijkst: Gmail API, net als je
     inkoopsysteem)
   - `*.mail.protection.outlook.com` → **Microsoft 365**
   - iets anders (TransIP, Hostnet, Strato, Mijndomein…) → **gewone hosting** (IMAP/SMTP)
3. Bij **Google Workspace**: net als bij `gmail_koppelen.py`: Google Cloud-project →
   Gmail API aan → OAuth-client (Desktop) → JSON downloaden als `gmail_client.json` in
   de projectmap → `./.venv/bin/python scripts/gmail_koppelen.py` → inloggen met het
   support-account. Scopes: lezen + versturen.
4. Bij **gewone hosting**: IMAP-server, poort, gebruikersnaam en wachtwoord van de
   mailbox + SMTP-server en poort. Zet ze in `.secrets.json` onder `"imap"` en `"smtp"`.
5. Bij **Microsoft 365**: laat het weten, dan bouw ik de Graph-koppeling (vereist
   admin-toestemming in Entra).
**Stuur mij daarna:** het adres, welke van de drie het is, en "gedaan".

---

## 4. META — Instagram en Facebook (DM's én comments)

**Wat:** een Meta-developer-app gekoppeld aan de Facebook-pagina en het Instagram-
account van Farmers Atelier, plus een token.
**Waarom:** daarmee komen Instagram-DM's, Instagram-comments, Facebook Messenger en
Facebook-comments binnen en kunnen we vanuit de inbox antwoorden, comments verbergen en
privé reageren op een comment.
**Belangrijk vooraf:**
- Het Instagram-account moet een **professioneel account** (Business of Creator) zijn
  en **gekoppeld aan de Facebook-pagina** (Instagram-app → Instellingen → Accountcentrum).
- In de Instagram-app: **Instellingen → Berichten en story-reacties → Berichtbeheer →
  Verbonden tools → "Toegang tot berichten toestaan" AAN**.
- Voor antwoorden ná 24 uur (het "Human Agent"-venster van 7 dagen) is een **App Review
  + Business Verification** bij Meta nodig (KvK-uittreksel). Dat duurt 1–3 weken; start
  het meteen.
**Wat je doet:**
1. Ga naar https://developers.facebook.com/apps/ en log in met het Facebook-account dat
   **beheerder** is van de Farmers Atelier-pagina.
2. **Create app** → naam "Farmers Atelier Support" → kies de use cases **"Manage
   messaging and content on Instagram"** en **"Manage everything on your Page"** →
   koppel de **business portfolio** (Business Manager) van Farmers Atelier → Create.
3. In het app-dashboard: **App settings → Basic**: kopieer **App ID** en **App Secret**.
   Vul een privacybeleid-URL in (mag de pagina van de webshop zijn).
4. **Business Settings** (business.facebook.com/settings) → **Users → System Users** →
   **Add** → naam "support-inbox", rol Admin → **Add Assets**: de Facebook-pagina (Full
   control) en het Instagram-account → **Generate New Token** → kies de app → vink aan:
   `pages_messaging, pages_manage_metadata, pages_read_engagement,
   pages_manage_engagement, pages_read_user_content, pages_show_list,
   instagram_basic, instagram_manage_messages, instagram_manage_comments` →
   Generate → kopieer het token (verloopt niet).
5. Zoek de **Page ID** (Facebook-pagina → Over/Info → onderaan "Pagina-ID") en het
   **Instagram-account-ID** (staat in Business Settings → Instagram-accounts).
6. Zet in `.secrets.json`: `"meta": {"app_id", "app_secret", "page_id",
   "page_access_token", "ig_account_id", "verify_token": "<zelf een lang willekeurig
   woord verzinnen>"}`.
7. **Webhooks** (doe ik samen met jou, want er is een publieke URL nodig): ik start
   `cloudflared`, geef je een URL, jij plakt die in de app onder **Webhooks → Page en
   Instagram** met het verify-token, en vinkt de velden `messages, messaging_postbacks,
   message_echoes, feed` (Page) en `messages, comments, mentions` (Instagram) aan.
8. Zet de app op **Live** (schakelaar bovenaan).
9. Start **Business Verification** (App dashboard → Settings → Basic → Business
   Verification) en dien daarna een **App Review** in voor **Human Agent**
   (Messenger → Features). Ik lever de screencast-tekst aan.
**Stuur mij daarna:** Page ID, Instagram-account-ID (geen tokens via chat) en "gedaan",
plus of Business Verification is gestart.

---

## 5. KENNISBANK — wat de AI moet weten

**Wat:** de feiten die de AI mag gebruiken. Zonder deze info zegt de AI "dat weet ik
niet" en zet het ticket door naar jou (ze verzint niets).
**Waar:** map `kb/`. Elk onderwerp is een Markdown-bestand; ik heb ze aangemaakt met
placeholders en `TODO`-regels. Vul in wat je weet, verwijder wat niet klopt.
**Wat ik nodig heb (kort en concreet):**
- `retourbeleid.md`: retourtermijn (14/30 dagen?), voorwaarden (ongedragen, label),
  wie betaalt retourverzending, hoe (portaal/link/mail), hoe snel refund, ruilen mogelijk?
- `verzendbeleid.md`: vervoerder(s), verzendkosten NL/BE/EU, gratis vanaf, levertijd,
  verzenddagen, track & trace, wat bij "afgeleverd maar niet ontvangen"
- `maten.md`: maattabel per product (borstomvang/lengte per maat), valt het groot/klein
- `producten.md`: de shirts en truien: namen, kleuren, materiaal, wasvoorschrift,
  productie/herkomst, prijs
- `betaalmethoden.md`: iDEAL, creditcard, Klarna, PayPal…; wat bij mislukte betaling
- `kortingen.md`: lopende acties, regels (combineren?), studentenkorting, nieuwsbrief
- `faq.md`: de 15 meest gestelde vragen met antwoorden
- `tone-of-voice.md`: je/u, hoe informeel, ondertekening, wat nooit zeggen
- `bedrijfsinfo.md`: adres, KvK, openingstijden klantenservice, wie is wie
**Stuur mij daarna:** niets, gewoon de bestanden invullen en committen (of mailen als
platte tekst en ik zet het erin).

---

## 6. FULFILLMENT — de externe partij

**Wat:** wie het is en of ze een API hebben.
**Waarom:** de AI wil "picking / packed / shipped / retour ontvangen" kunnen zien. Nu
werkt het met een adapter die dit uit Shopify-fulfillments afleidt plus mock-data.
**Wat je doet:**
1. Naam van de fulfillmentpartij en hun software (bv. Monta, Active Ants, Picqer,
   Sendcloud, ShipBob…).
2. Vraag hen: "Hebben jullie een API of webhooks voor orderstatus en retourstatus, en
   kunnen jullie ons een API-sleutel en documentatielink geven?"
3. Welke vervoerder(s) gebruiken ze (PostNL, DHL, DPD)? Voor PostNL/DHL kan ik direct
   tracking ophalen als er een zakelijke API-sleutel is.
**Stuur mij daarna:** naam partij, documentatielink, en de sleutel in `.secrets.json`
onder `"fulfillment"`.

---

## 7. TIKTOK — wat kan wel en niet

**Wat kan niet (nu):** organische TikTok-DM's inlezen. TikTok's Business Messaging API is
alleen voor toegelaten partners (allowlist). Die DM's beantwoord je in de TikTok-app;
in de inbox kun je er een notitie van maken.
**Wat kan wel:** comments op je eigen video's ophalen, beantwoorden en verbergen via de
TikTok API for Business, na een aanvraag ("Accounts API Access Application Form").
**Wat je doet (als je dit wilt):**
1. Is het TikTok-account een **Business Account**? (TikTok-app → Instellingen → Account →
   Overschakelen naar Business Account.)
2. Ga naar https://business-api.tiktok.com/portal/ → log in → **Create app** → vink
   "TikTok Accounts" aan → vul het Accounts API Access-formulier in (doel: eigen
   klantenservice op eigen comments).
3. Na goedkeuring: autoriseer het Farmers Atelier-account en zet `app_id`, `app_secret`
   en het token in `.secrets.json` onder `"tiktok"`.
4. Verkoopt Farmers Atelier op **TikTok Shop**? Dan kan de Shop-chat wél gekoppeld
   worden (Partner Center-app). Laat het weten.
**Stuur mij daarna:** of je dit wilt, of het account Business is, en de status van de
aanvraag.

---

## 8. GITHUB — de code op jouw account

**Wat:** een lege privé-repository op GitHub.
**Waarom:** ik kan via SSH pushen als `WiegerPrefabriek`, maar een repository aanmaken
kan alleen via de website (er is geen `gh` op deze Mac).
**Wat je doet:**
1. Ga naar https://github.com/new (ingelogd als WiegerPrefabriek).
2. Repository name: `farmers-atelier-support`. **Private**. Géén README, géén
   .gitignore, géén licentie aanvinken (die staan al in de map).
3. Klik **Create repository**.
**Stuur mij daarna:** "gedaan" — dan push ik. Of doe het zelf vanuit de projectmap:

```bash
git push -u origin main
```

(De remote `origin` staat al ingesteld op `git@github.com:WiegerPrefabriek/farmers-atelier-support.git`;
de eerste push op 25-09-2026 mislukte omdat de repository nog niet bestond. Alles staat
lokaal gecommit op branch `main`.)

Op de andere laptop daarna:
```bash
git clone git@github.com:WiegerPrefabriek/farmers-atelier-support.git
cd farmers-atelier-support
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python mock/generate.py
./.venv/bin/python run.py
```

---

## 9. PYTHON-UPGRADE (aanbevolen, niet urgent)

**Wat:** Python 3.12 naast de systeem-Python 3.9.
**Waarom:** de nieuwste `anthropic`-SDK (1.x) en veel bibliotheken vereisen ≥3.10. Alles
werkt nu op 3.9 met een iets oudere SDK, maar op termijn lopen we vast.
**Wat je doet:** download de macOS-installer van https://www.python.org/downloads/
(3.12.x), installeer (vraagt je Mac-wachtwoord), en laat het me weten. Ik maak dan de
`.venv` opnieuw aan met 3.12.

---

## Checklist

- [ ] 1. Anthropic API-sleutel in `.secrets.json`
- [ ] 2. Shopify custom app (Dev Dashboard) + client id/secret + plan-niveau
- [ ] 3. E-mail: adres + provider (Google / Microsoft / hosting) + koppeling
- [ ] 4. Meta-app + System User-token + Page ID + IG-ID + webhooks + Business Verification
- [ ] 5. Kennisbank-bestanden in `kb/` ingevuld
- [ ] 6. Fulfillmentpartij + API
- [ ] 7. TikTok Business Account + Accounts API-aanvraag (optioneel)
- [ ] 8. GitHub-repo `farmers-atelier-support` aangemaakt
- [ ] 9. Python 3.12 geïnstalleerd (optioneel)
