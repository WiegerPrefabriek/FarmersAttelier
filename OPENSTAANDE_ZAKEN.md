# OPENSTAANDE ZAKEN

Stand **27-09-2026, eind van de dag**. Dit is de lijst om morgen mee verder te gaan.
Bovenaan wat af is, daaronder wat er nog moet, op volgorde van wat het meeste
oplevert. Sleutels horen in `.secrets.json` (staat in `.gitignore`) — nooit in de
chat, nooit in een mail.

---

## Wat af is

| Onderdeel | Stand |
|---|---|
| **Project draait lokaal** | `http://localhost:8800/` — startknop op het bureaublad |
| **Anthropic (AI)** | ✅ werkt, modus `claude` — geen trefwoorden meer |
| **Nepdata** | ✅ weg. Inbox is leeg tot er echte post binnenkomt. Regels en kennisbank staan er nog |
| **Shopify-app** | ✅ aangemaakt én geïnstalleerd op de winkel, met lees- en schrijfrechten |
| **Entra-app (Outlook)** | ✅ aangemaakt, rechten toegevoegd — mist nog twee handelingen, zie §1 |
| **Voorraad-tab** | ✅ `http://localhost:8800/#voorraad` — 1.146 stuks, 126 modellen, 474 retouren, kostenmodel |
| **Artikelen-Excel** | ✅ ingelezen: 570 varianten over 126 modellen |
| **Innostock-tarieven** | ✅ vastgelegd, kostenmodel rekent ermee |

**Gemeten feiten die het onthouden waard zijn**

* Shopify-winkel: `50037e-2.myshopify.com`, domein **farmersatelier.com**, abonnement **Grow**.
  Staat nu achter een wachtwoord; in de winkelcode zit een blok met **01 OCT**.
* `farmersatelier.nl` is een **andere** site (Webnode), met mail bij ZXCS.
* Klantenservice-mailbox: **info@farmersatelier.com** (Microsoft 365).
* Entra tenant-id `b203019e-fc74-4f44-9c2f-eb4dfc77aadc`, app-id `e783da0e-d496-4c3b-b1e8-0b2992d27103`.

---

## 1. OUTLOOK afmaken — twee handelingen (5 minuten)

De app-registratie staat er, de rechten `Mail.ReadWrite` en `Mail.Send` zijn
toegevoegd. Wat nog moet:

**a. Beheerderstoestemming verlenen.** In Entra → *Farmers Atelier Support* →
**API-machtigingen** staat achter beide rechten "Niet toegekend". Klik op
**"Beheerderstoestemming verlenen voor farmersatelier"** en bevestig. Zonder dit
mag de app niets, ook al staan de rechten er.

**b. Een clientgeheim maken.** Zelfde app → **Certificaten en geheimen** →
*Clientgeheimen* → **Nieuw clientgeheim** → omschrijving "farmers-atelier-support",
geldigheid 24 maanden → **Toevoegen**. Kopieer meteen de **Waarde** (niet de
Geheim-id) — die is daarna niet meer te zien. Plak hem in `.secrets.json` onder
`"microsoft"` → `"client_secret"`.

Daarna testen met:

```bash
cd ~/Desktop/FARMERS-ATELIER && ./.venv/bin/python -c "from app.channels import email_microsoft as m; print(m.test())"
```

**Let op — de app mag nu bij álle postbussen.** `Mail.ReadWrite` als
toepassingsrecht geldt tenant-breed; dat is hoe Microsoft het aanbiedt, er is geen
vinkje voor één postbus. Te beperken tot alleen `info@farmersatelier.com` met een
*Application Access Policy* in Exchange Online (PowerShell, ~10 regels). Zolang dat
niet staat kan de app in principe ook Folkerts eigen postvak lezen. Ons programma
doet dat niet — het kijkt alleen naar de postbus in `.secrets.json` — maar het
récht is er wel. Aanrader om dit op korte termijn te regelen.

---

## 2. SHOPIFY afmaken — één handeling (1 minuut)

Het **clientgeheim** ontbreekt nog. Dev Dashboard → *Farmers Atelier Support* →
**Overzicht** → rechts bij **Inloggegevens** → **Klantgeheim** kopiëren → plakken in
`.secrets.json` onder `"shopify"` → `"client_secret"`.

Winkeldomein en client-id staan er al in. Daarna test:

```bash
curl -sS http://localhost:8800/api/integrations/test -H "X-User-Id: 1"
```

**Wat daarna meteen kan:** producten, voorraad, orders, klanten en retouren
ophalen; de retouren per artikel en maat in de Voorraad-tab; en het tweede
dashboard met omzetcijfers.

**Wat Shopify geweigerd heeft:** `read_all_orders` — het recht op orders ouder dan
60 dagen. Dat moet apart bij Shopify aangevraagd worden. Voor klantenservice is 60
dagen meestal genoeg; voor een jaaroverzicht in het dashboard niet.

---

## 3. RETOUREN per artikel en maat

Je vroeg om een uitklapbaar overzicht: type artikel → maat → aantal. Dat staat er
qua opbouw al (de Voorraad-tab doet dit voor de voorraad), maar de **inhoud van de
retouren ontbreekt**: de Excel geeft per retour alleen een trackingnummer, niet wat
erin zat. 474 pakketten, 0 artikelen bekend.

Twee manieren om dat alsnog te vullen, in deze volgorde:

1. **Shopify-retouren ophalen** (zodra §2 klaar is). Als de retouren daar
   geregistreerd zijn, staan de artikelen en maten er gewoon in — dan is het klaar.
2. **De mail uitspitten** als Shopify het niet weet. Alle retourmails in
   `info@farmersatelier.com` tot en met 2026 doorlopen en er artikelen en maten uit
   halen. Jij gaf aan: alles ná 2026 hoort bij de nieuwe store en moet er buiten
   blijven. Dit kan pas als §1 klaar is.

---

## 4. META — Instagram en Facebook

Nog niet aan begonnen. Belangrijkste punt: **Business Verification duurt 1 à 3
weken**, dus dat is het eerste dat in gang moet. Zonder verificatie mag je een klant
maar 24 uur na zijn bericht antwoorden; met verificatie 7 dagen.

Vooraf controleren in de Instagram-app van Farmers Atelier:
* professioneel account (Business of Creator)?
* gekoppeld aan de Facebook-pagina?
* Instellingen → Berichten → Berichtbeheer → Verbonden tools →
  **"Toegang tot berichten toestaan" AAN** — zonder dit komt er geen enkel bericht binnen.

Nodig: KvK-uittreksel, en inloggen met het Facebook-account dat **beheerder** is van
de Farmers Atelier-pagina. Jouw eigen Business Manager bevat Stikss, Veloro, Zuvéra
en De Prefabriek — geen Farmers Atelier.

---

## 5. TIKTOK

**DM's kunnen niet.** De Business Messaging API van TikTok is alleen voor partners
op uitnodiging; dat is geen instelling die we kunnen aanzetten. Die berichten
beantwoord je in de app zelf.

**Comments kunnen wel**: ophalen, beantwoorden en verbergen, na goedkeuring van een
*Accounts API Access*-aanvraag. Account moet een Business Account zijn.

Openstaande vraag: **verkoopt Farmers Atelier via TikTok Shop?** Zo ja, dan kan de
Shop-chat wél gekoppeld worden, via een heel ander kanaal (Partner Center).

---

## 6. KENNISBANK — dit kun jij zelf, zonder mij

Tien bestanden in `kb/` staan nog vol `TODO`. Wat leeg blijft gebruikt de AI niet:
dan zegt hij "dat weet ik niet" en zet het ticket naar jou door. Hij verzint niets,
maar hij kan ook niets zeggen.

`retourbeleid.md` · `verzendbeleid.md` · `maten.md` · `producten.md` ·
`betaalmethoden.md` · `kortingen.md` · `faq.md` · `tone-of-voice.md` ·
`bedrijfsinfo.md` · `retourinstructies.md`

Dit is waarschijnlijk het punt met de meeste opbrengst per bestede minuut: hoe
voller de kennisbank, hoe meer de AI zelfstandig afhandelt.

---

## 7. FULFILLMENT — Innostock

De offerte is verwerkt in het kostenmodel. Drie dingen staan er nog niet in, en die
moeten met Philip Rijswijk besproken:

* **Aantal pallets, aantal sku's en maandelijkse orders** staan in de offerte op
  "n.t.b.". Zonder die aantallen is de maandelijkse opslagpost niet vast te stellen.
* **Afgekeurde retouren**: terugsturen of vernietigen? En naar welke retourlocatie?
* **Niet in de offerte**: het opnieuw fotograferen of hertaggen van retouren die als
  tweede kans verkocht worden.

Nog te regelen: hebben ze een **API of webhooks** voor orderstatus en retourstatus?
Dan kunnen we picking/packed/shipped live in de inbox tonen.

---

## 8. Kleinere punten

* **Python 3.12** — alles draait nu op 3.9. Werkt, maar de nieuwste Anthropic-SDK
  vereist 3.10+. Niet urgent.
* **Repo staat publiek** op `github.com/WiegerPrefabriek/FarmersAttelier`. Geheimen
  staan er niet in (gecontroleerd), maar de code en de kennisbank zijn openbaar
  leesbaar. Privé zetten kan alleen een beheerder van dat GitHub-account; ik heb
  schrijfrechten maar geen beheerrechten.
* **1 oktober** — als de winkel dan opengaat komen er klantvragen binnen. Shopify en
  Outlook zijn dan het belangrijkst; Meta en TikTok kunnen daarna.

---

## Kortste weg naar een werkend geheel

1. Beheerderstoestemming in Entra + clientgeheim → **Outlook leest mee**
2. Shopify-clientgeheim → **orders en klanten naast elk gesprek**
3. Kennisbank vullen → **AI gaat zelfstandig antwoorden**
4. Meta Business Verification starten → **loopt op de achtergrond**

Stap 1 en 2 kosten samen tien minuten en zetten het grootste deel aan.
