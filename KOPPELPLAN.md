# Koppelplan — Meta, Shopify, TikTok en e-mail

Stand 27-09-2026. Werkwijze: Claude bestuurt Chrome en navigeert; **Wieger logt zelf in**
en drukt zelf op de knoppen die iets vastleggen (app aanmaken, rechten verlenen,
voorwaarden accepteren). Sleutels en tokens komen **niet** in de chat: Wieger plakt ze
rechtstreeks in `.secrets.json`, dat bestand staat in `.gitignore`.

---

## 0. Wat we vooraf hebben vastgesteld (27-09-2026)

Dit is gemeten, niet aangenomen.

| Wat | Bevinding |
|---|---|
| **Shopify-winkel** | `50037e-2.myshopify.com` — naam "FARMERS ATELIER", shop-id 79370060104 |
| **Webshop-adres** | **farmersatelier.com** (Shopify). Staat nu achter een wachtwoord (`/password`), dus nog niet publiek |
| **Lancering** | In de winkelcode staat een blok *"Size Guide + Get the look \| 01 OCT"* — er wordt gewerkt naar **1 oktober** |
| **farmersatelier.nl** | Een **andere** site, gebouwd op **Webnode** (geen Shopify). Dit is nu het publieke adres |
| **Mail .nl** | MX staat bij **ZXCS** (Nederlandse hoster) → gewone mailbox, dus **IMAP/SMTP** — *geen Gmail* |
| **Mail .com** | MX staat bij **Microsoft 365** (`farmersatelier-com.mail.protection.outlook.com`) |
| **Meta** | In Wiegers eigen Business Manager zit **geen** Farmers Atelier-portfolio (wel Stikss, Veloro, Zuvéra, De Prefabriek). De pagina en Instagram horen bij het Farmers-account |
| **Shopify-account Wieger** | Bevat alleen de **opgezegde** Zuvéra-winkel. Farmers Atelier staat op een ander account |

**Gevolg:** bij elke dienst logt Wieger in met het **Farmers Atelier-account**, niet met
zijn eigen. Waar hij geen eigenaar is, moet zijn broertje hem toegang geven.

**Let op de datum.** Als de winkel op 1 oktober opengaat, komen er vanaf dat moment
klantvragen binnen. Shopify en e-mail zijn dan het belangrijkst; Meta en TikTok hebben
een wachttijd en kunnen daarna nog aankomen.

---

## 1. Volgorde, en waarom

Niet op belangrijkheid, maar op **wachttijd**: wat weken duurt, zetten we eerst in gang.

```
VANDAAG STARTEN (loopt op de achtergrond door)
  A. Meta: Business Verification aanvragen        → 1 à 3 weken wachten
  B. TikTok: Accounts API aanvragen               → onbekende wachttijd, vaak 1 à 2 weken

DAARNA, IN ÉÉN MIDDAG TE DOEN
  C. Anthropic-sleutel                            → 5 minuten, en de AI werkt echt
  D. Shopify lezen                                → 20 minuten
  E. E-mail                                       → 30 minuten, afhankelijk van de keuze

ALS DE AANVRAGEN ZIJN GOEDGEKEURD
  F. Meta afmaken (token + webhooks)
  G. TikTok afmaken
```

---

## 2. Per koppeling

### A. Meta — Instagram en Facebook

**Wat het oplevert:** Instagram-DM's, Instagram-comments, Facebook Messenger en
Facebook-comments komen binnen in de inbox, en je antwoordt vanuit hetzelfde scherm
terug via hetzelfde kanaal.

**Eerst controleren (Wieger, in de Instagram-app van Farmers Atelier):**
1. Is het een **professioneel account** (Business of Creator)? Zo niet: Instellingen →
   Accounttype → overschakelen.
2. Is het **gekoppeld aan de Facebook-pagina**? Instellingen → Accountcentrum.
3. Instellingen → Berichten → Berichtbeheer → Verbonden tools →
   **"Toegang tot berichten toestaan" AAN**. Zonder dit komt er geen enkel bericht binnen.

**Dan, in Chrome (Claude navigeert, Wieger logt in en klikt):**
1. Inloggen op `business.facebook.com` met het Farmers Atelier-account.
2. Business portfolio voor Farmers Atelier openen (of aanmaken als die er niet is).
3. **Business Verification starten** — hiervoor is een **KvK-uittreksel** nodig.
   *Dit is de stap met de wachttijd; daarom eerst.*
4. `developers.facebook.com/apps` → app "Farmers Atelier Support" aanmaken.
5. System User aanmaken met een token dat niet verloopt, met de rechten voor berichten
   en comments.
6. Webhooks: hiervoor is een publiek adres nodig. Claude start `cloudflared`
   (tunnel naar deze laptop) en geeft de URL; Wieger plakt die in de app.

**Waarom Business Verification nodig is:** zonder verificatie mag je een klant alleen
binnen **24 uur** na zijn bericht antwoorden. Met verificatie wordt dat **7 dagen**
(het "Human Agent"-venster). Zonder dat venster kun je een vraag van gisteravond
vanmiddag niet meer beantwoorden.

**Wat Wieger nodig heeft:** inloggegevens Farmers Atelier Facebook/Instagram (beheerder
van de pagina), en een KvK-uittreksel.

---

### B. TikTok — wat wel en niet kan

**Eerlijk vooraf: DM's kunnen niet.** TikTok's Business Messaging API is alleen voor
partners op uitnodiging. Organische TikTok-DM's beantwoord je in de TikTok-app zelf.

**Wat wel kan:** comments op je eigen video's ophalen, beantwoorden en verbergen.

**Stappen:**
1. Is het TikTok-account een **Business Account**? Zo niet: TikTok-app → Instellingen →
   Account → overschakelen.
2. `business-api.tiktok.com/portal` → inloggen met het Farmers-account → **Create app**.
3. "TikTok Accounts" aanvinken en het **Accounts API Access-formulier** invullen.
   Doel: eigen klantenservice op eigen comments.
4. Wachten op goedkeuring.

**Vraag aan Wieger:** verkoopt Farmers Atelier ook via **TikTok Shop**? Dan kan de
Shop-chat wél gekoppeld worden — dat loopt via een heel ander kanaal (Partner Center).

---

### C. Shopify — orders, klanten, tracking

**Wat het oplevert:** naast elk gesprek staat direct de klant, de order, wat er betaald
is, of het verzonden is, het trackingnummer en eerdere bestellingen. Niemand hoeft
Shopify nog apart te openen.

**Twee dingen om vooraf uit te zoeken:**
1. **Wie is eigenaar van de winkel?** Waarschijnlijk het broertje. Aanmaken van een app
   kan alleen de eigenaar, of iemand met het recht "App development → Develop".
2. **Welk abonnement?** Voor klantgegevens (naam, adres, e-mail) via een eigen app eist
   Shopify het **Grow-plan of hoger**. Op Basic krijgen we de order wel te zien, maar de
   klantgegevens niet. Dit moet gecontroleerd worden vóórdat we bouwen.

**Stappen:**
1. Inloggen op `dev.shopify.com/dashboard` met het account van de winkeleigenaar.
2. **Create app** → "Farmers Atelier Support".
3. Alleen **leesrechten** aanvinken (orders, klanten, producten, voorraad, fulfillment,
   verzending, retouren). Schrijfrechten komen later, pas als het lezen werkt.
4. Installeren op de Farmers Atelier-winkel.
5. Client ID en secret → Wieger plakt ze zelf in `.secrets.json`.

**Bewust read-only in deze ronde.** Annuleren en terugbetalen zijn onomkeerbaar; die
rechten vragen we pas aan als de rest werkt en de goedkeuringsknop getest is.

---

### D. E-mail — en waarom "Gmail" hier niet vanzelf spreekt

De mail van **farmersatelier.nl loopt niet via Gmail** maar via ZXCS. De **.com** loopt
via Microsoft 365. Er is dus een keuze te maken. Drie mogelijkheden:

| Keuze | Hoe | Voor- en nadeel |
|---|---|---|
| **1. Los Gmail-adres** als supportbus, bv. `farmersatelier.support@gmail.com` | Google Cloud-project + Gmail API, precies zoals de productiecontrolelijst | Snel op te zetten en goed te automatiseren. Nadeel: klanten zien een gmail-adres, dat oogt minder professioneel. Op te lossen door vanaf een eigen adres te versturen |
| **2. `support@farmersatelier.nl`** bij ZXCS | IMAP + SMTP met de wachtwoorden van die mailbox | Eigen adres, professioneel. Nadeel: wachtwoord in `.secrets.json`, en IMAP is trager en brozer dan een API |
| **3. `support@farmersatelier.com`** bij Microsoft 365 | Microsoft Graph API | Netste oplossing als de winkel op .com draait, en de mail hoort bij de webshop. Nadeel: een beheerder moet toestemming geven in Entra, en ik moet die koppeling nog bouwen |

**Aanbeveling: optie 3**, want de webshop draait op .com en de klant krijgt dan post van
hetzelfde merk waar hij besteld heeft. Duurt iets langer om te bouwen dan optie 1.

**Vraag aan Wieger:** welk adres wordt het klantenservice-adres, en bestaat het al?

---

### E. Anthropic-sleutel (staat los, maar is de snelste winst)

Nu draait de AI op trefwoorden. Met een sleutel van `console.anthropic.com` gaat hij
echt lezen, categoriseren en antwoorden schrijven. Vijf minuten werk, en pas dan zie je
waar het systeem eigenlijk voor bedoeld is. Zet er meteen een maandlimiet op.

---

## 3. Afspraken over veiligheid

- **Inloggen doet Wieger zelf.** Claude typt nooit een wachtwoord.
- **Tokens en sleutels komen niet in de chat en niet op het scherm in beeld.** Wieger
  plakt ze rechtstreeks in `.secrets.json`. Claude hoeft ze niet te zien om te kunnen
  testen — de app zegt zelf of de koppeling werkt.
- **Claude drukt niet op knoppen die iets vastleggen** zonder te vragen: een app
  aanmaken, rechten verlenen, voorwaarden accepteren, iets op Live zetten. Claude
  navigeert ernaartoe, wijst aan wat er moet gebeuren, en Wieger bevestigt.
- **Shopify blijft deze ronde read-only.** Geen enkele actie kan een order of een
  terugbetaling veranderen.

---

## 4. Wat ik van Wieger nodig heb om te beginnen

1. **Inloggen** met het Farmers Atelier-account bij: Meta, Shopify, TikTok, en de mail.
2. **Shopify:** is je broertje eigenaar, en welk abonnement heeft de winkel?
3. **E-mail:** welk adres wordt het supportadres — .nl, .com, of een los Gmail-adres?
4. **Instagram:** is het een zakelijk account en hangt het aan de Facebook-pagina?
5. **TikTok:** bestaat het account al, is het zakelijk, en zit er TikTok Shop op?
6. **KvK-uittreksel** bij de hand voor de Meta-verificatie.
