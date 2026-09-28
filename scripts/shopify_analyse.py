#!/usr/bin/env python3
"""Bouwt het analyserapport van de Shopify-winkel als PDF.

    ./.venv/bin/python scripts/shopify_analyse.py

Haalt de cijfers live uit Shopify en schrijft docs/shopify-analyse/Shopify-analyse.pdf.
Opnieuw draaien geeft een nieuw rapport met de stand van dat moment.

Opbouw: het rapport volgt het menu van de Shopify-beheerpagina van boven naar
beneden, zodat je het naast je scherm kunt leggen. Per onderdeel drie dingen:
wat het is, wat er bij Farmers Atelier in staat, en wat er beter kan.
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak,  # noqa: E402
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

from app.integrations import shopify  # noqa: E402

# Kleuren: rustig, één accent. Groen = goed, oranje = aandacht, rood = probleem.
GROEN = colors.HexColor("#2f5d3a")
ZACHTGROEN = colors.HexColor("#e6efe8")
ORANJE = colors.HexColor("#b7791f")
ZACHTORANJE = colors.HexColor("#fbf1dc")
ROOD = colors.HexColor("#b3261e")
ZACHTROOD = colors.HexColor("#fbe5e3")
GRIJS = colors.HexColor("#6b6f66")
LIJN = colors.HexColor("#d8d8d2")
PAPIER = colors.HexColor("#fbfbf9")

S = getSampleStyleSheet()
st_titel = ParagraphStyle("titel", parent=S["Title"], fontSize=26, leading=30,
                          textColor=GROEN, alignment=TA_LEFT, spaceAfter=4)
st_onder = ParagraphStyle("onder", parent=S["Normal"], fontSize=11, textColor=GRIJS, spaceAfter=18)
st_h1 = ParagraphStyle("h1", parent=S["Heading1"], fontSize=17, leading=21, textColor=GROEN,
                       spaceBefore=16, spaceAfter=2)
st_h2 = ParagraphStyle("h2", parent=S["Heading2"], fontSize=12.5, leading=16,
                       textColor=colors.HexColor("#1d1f1b"), spaceBefore=12, spaceAfter=3)
st_p = ParagraphStyle("p", parent=S["Normal"], fontSize=9.6, leading=14.2, spaceAfter=5)
st_klein = ParagraphStyle("klein", parent=st_p, fontSize=8.6, textColor=GRIJS, leading=12)
st_cel = ParagraphStyle("cel", parent=S["Normal"], fontSize=8.8, leading=12)
st_celvet = ParagraphStyle("celvet", parent=st_cel, fontName="Helvetica-Bold")


def kaart(tekst: str, soort: str = "info") -> Table:
    """Gekleurd blok voor een bevinding. Soort bepaalt de kleur en het kopje."""
    kop, achter, rand = {
        "goed": ("DIT GAAT GOED", ZACHTGROEN, GROEN),
        "let_op": ("LET OP", ZACHTORANJE, ORANJE),
        "probleem": ("DIT MOET GEREPAREERD", ZACHTROOD, ROOD),
        "info": ("IN HET KORT", colors.HexColor("#eef1ec"), GRIJS),
    }[soort]
    t = Table([[Paragraph(f'<font size="7.5" color="{rand.hexval()}"><b>{kop}</b></font>', st_cel)],
               [Paragraph(tekst, st_cel)]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), achter),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (0, 0), 6), ("BOTTOMPADDING", (0, 1), (0, 1), 7),
        ("TOPPADDING", (0, 1), (0, 1), 1), ("BOTTOMPADDING", (0, 0), (0, 0), 1),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, rand),
    ]))
    return t


def tabel(kop: list[str], rijen: list[list], breedtes=None) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", st_cel) for k in kop]]
    for r in rijen:
        data.append([c if isinstance(c, Paragraph) else Paragraph(str(c), st_cel) for c in r])
    t = Table(data, colWidths=breedtes or None, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1ec")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, GROEN),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, LIJN),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def menubalk(actief: str) -> Table:
    """Tekent het Shopify-menu na, met het besproken onderdeel gemarkeerd.

    Geen schermafbeelding maar een nabootsing: zo zie je meteen waar in het menu
    je moet zijn, zonder dat het rapport vol staat met plaatjes die bij elke
    Shopify-update verouderen.
    """
    items = ["Home", "Bestellingen", "Producten", "Klanten", "Groei", "Kortingen",
             "Content", "Markten", "Financiën", "Analytics", "Webshop", "Instellingen"]
    rijen = []
    for i in items:
        aan = i.lower() == actief.lower()
        rijen.append([Paragraph(
            f'<font color="{"#ffffff" if aan else "#4a4f46"}" size="7.8">'
            f'{"<b>" + i + "</b>" if aan else i}</font>', st_cel)])
    t = Table(rijen, colWidths=[30 * mm], hAlign="LEFT")
    stijl = [("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
             ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f1ee")),
             ("BOX", (0, 0), (-1, -1), 0.4, LIJN)]
    for n, i in enumerate(items):
        if i.lower() == actief.lower():
            stijl.append(("BACKGROUND", (0, n), (0, n), GROEN))
    t.setStyle(TableStyle(stijl))
    return t


def sectie(nr: str, titel: str, menu: str, wat: str) -> list:
    """Kop van een hoofdstuk, met het menu ernaast zodat je ziet waar je klikt."""
    links = [Paragraph(f'<font color="{GRIJS.hexval()}" size="8">{nr}</font>', st_p),
             Paragraph(titel, st_h1), Paragraph(wat, st_p)]
    t = Table([[links, menubalk(menu)]], colWidths=[130 * mm, 35 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (0, 0), 0),
                           ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    return [t, Spacer(1, 4)]


def cijferrij(paren: list[tuple[str, str]]) -> Table:
    """Rij met kerncijfers: groot getal, klein label eronder."""
    cellen = [[Paragraph(f'<font size="15"><b>{w}</b></font><br/>'
                         f'<font size="7.4" color="{GRIJS.hexval()}">{l}</font>', st_cel)
               for w, l in paren]]
    t = Table(cellen, colWidths=[165 * mm / len(paren)] * len(paren), hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPIER),
        ("BOX", (0, 0), (-1, -1), 0.4, LIJN),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LIJN),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


# ---------------------------------------------------------------------------
# Gegevens ophalen
# ---------------------------------------------------------------------------
def haal_op() -> dict:
    c = shopify.client()
    if not c.configured:
        raise SystemExit("Shopify is niet gekoppeld — vul 'shopify' in .secrets.json.")
    d = {}
    d["shop"] = c.graphql("""{ shop { name email myshopifyDomain currencyCode ianaTimezone
        taxesIncluded taxShipping weightUnit plan { displayName }
        primaryDomain { host sslEnabled } customerAccounts } }""")["shop"]
    d["tel"] = c.graphql("""{ productsCount { count } ordersCount { count }
        abandonedCheckoutsCount { count }
        klanten: customerSegmentMembers(first:1, query:"") { totalCount }
        abonnees: customerSegmentMembers(first:1, query:"email_subscription_status = 'SUBSCRIBED'") { totalCount }
        kopers: customerSegmentMembers(first:1, query:"number_of_orders > 0") { totalCount }
        actief: productsCount(query:"status:active") { count }
        concept: productsCount(query:"status:draft") { count }
        locations(first:10) { edges { node { name isActive } } } }""")
    d["kanalen"] = [e["node"]["name"] for e in
                    c.graphql("{ publications(first:20){ edges{ node{ name } } } }")["publications"]["edges"]]
    d["themas"] = [e["node"] for e in
                   c.graphql("{ themes(first:30){ edges{ node{ name role updatedAt } } } }")["themes"]["edges"]]
    d["paginas"] = [e["node"] for e in
                    c.graphql("{ pages(first:40){ edges{ node{ title isPublished } } } }")["pages"]["edges"]]
    d["kortingen"] = [e["node"]["codeDiscount"] for e in c.graphql(
        """{ codeDiscountNodes(first:50){ edges{ node{ codeDiscount{
             ... on DiscountCodeBasic { title status } ... on DiscountCodeBxgy { title status }
             ... on DiscountCodeFreeShipping { title status } } } } } }""")["codeDiscountNodes"]["edges"]]
    d["segmenten"] = [e["node"]["name"] for e in
                      c.graphql("{ segments(first:30){ edges{ node{ name } } } }")["segments"]["edges"]]
    d["webhooks"] = c.graphql("{ webhookSubscriptions(first:30){ edges{ node{ topic } } } }"
                              )["webhookSubscriptions"]["edges"]
    d["verzending"] = c.graphql("""{ deliveryProfiles(first:3){ edges{ node{ name
        profileLocationGroups { locationGroupZones(first:15){ edges{ node{
          zone { name } methodDefinitions(first:10){ edges{ node{ name active
            rateProvider { ... on DeliveryRateDefinition { price { amount } } } } } } } } } } } } } }"""
        )["deliveryProfiles"]["edges"]
    # Voorraad optellen over alle varianten
    tot = neg = n = 0
    cursor = None
    for _ in range(12):
        v = "first: 250" + (f', after: "{cursor}"' if cursor else "")
        r = c.graphql("{ productVariants(%s){ edges{ node{ inventoryQuantity } } "
                      "pageInfo{ hasNextPage endCursor } } }" % v)["productVariants"]
        for e in r["edges"]:
            q = e["node"].get("inventoryQuantity") or 0
            tot += q; n += 1
            if q < 0: neg += 1
        if not r["pageInfo"]["hasNextPage"]: break
        cursor = r["pageInfo"]["endCursor"]
    d["voorraad"] = {"totaal": tot, "varianten": n, "negatief": neg}
    return d


# ---------------------------------------------------------------------------
# Het rapport
# ---------------------------------------------------------------------------
def bouw(d: dict, pad: str) -> None:
    sh, t = d["shop"], d["tel"]
    v = d["voorraad"]
    verlopen = sum(1 for k in d["kortingen"] if (k or {}).get("status") == "EXPIRED")
    actieve_korting = sum(1 for k in d["kortingen"] if (k or {}).get("status") == "ACTIVE")
    live_thema = next((x["name"] for x in d["themas"] if x["role"] == "MAIN"), "onbekend")
    ongebruikt = sum(1 for x in d["themas"] if x["role"] == "UNPUBLISHED")
    concept_pag = [p["title"] for p in d["paginas"] if not p["isPublished"]]

    v_ = []
    A = v_.append

    # ---- omslag ----------------------------------------------------------
    A(Spacer(1, 30))
    A(Paragraph("Shopify van Farmers Atelier", st_titel))
    A(Paragraph(f"Wat er in staat, wat het doet en wat beter kan · {date.today().strftime('%d-%m-%Y')}", st_onder))
    A(cijferrij([(f"{t['productsCount']['count']}", "producten"),
                 (f"{t['klanten']['totalCount']:,}".replace(",", "."), "klanten"),
                 (f"{t['abonnees']['totalCount']:,}".replace(",", "."), "e-mailabonnees"),
                 (f"{len(d['themas'])}", "thema's")]))
    A(Spacer(1, 14))
    A(Paragraph("Hoe je dit leest", st_h2))
    A(Paragraph("Dit rapport loopt het menu van je Shopify-beheerpagina van boven naar beneden af. "
                "Elk hoofdstuk heeft rechts een klein menu waarin groen gemarkeerd staat waar je "
                "moet klikken. Per onderdeel lees je drie dingen: <b>wat het is</b>, <b>wat er bij "
                "jullie in staat</b>, en <b>wat er beter kan</b>.", st_p))
    A(Spacer(1, 6))
    A(kaart("Er zijn <b>drie dingen</b> die vóór de heropening geregeld moeten zijn, en die kosten "
            "je omzet of vertrouwen als je ze laat liggen:<br/><br/>"
            "<b>1.</b> Je e-maildomein is niet geauthenticeerd — bevestigingsmails en campagnes "
            "belanden bij Gmail en Outlook in de spam. Zie hoofdstuk 11.<br/>"
            f"<b>2.</b> De voorraadadministratie klopt niet: {v['negatief']} van de {v['varianten']} "
            f"varianten staan negatief, samen {v['totaal']} stuks. Zie hoofdstuk 3.<br/>"
            "<b>3.</b> Er staan geen webhooks: geen enkel systeem krijgt automatisch bericht als er "
            "een bestelling binnenkomt. Zie hoofdstuk 12.", "probleem"))
    A(PageBreak())

    # ---- 1 Home ----------------------------------------------------------
    v_ += sectie("HOOFDSTUK 1", "Home", "Home",
                 "Het eerste scherm na inloggen: een samenvatting van hoe de winkel draait, plus "
                 "tips van Shopify zelf.")
    A(Paragraph("Wat er bij jullie staat", st_h2))
    A(Paragraph("Bovenaan staan vier cijfers over de afgelopen periode: sessies, omzet, bestellingen "
                "en conversiepercentage. Bij jullie staan die allemaal diep in het rood "
                "(sessies −49%, omzet −97%, bestellingen −95%). Dat is <b>geen fout</b>: de winkel is "
                "sinds 9 juni gesloten, dus er komt niets binnen. Zodra jullie weer opengaan lopen "
                "deze cijfers vanzelf terug omhoog.", st_p))
    A(kaart("Trek tot de heropening geen conclusies uit dit scherm. Het vergelijkt met een periode "
            "waarin de winkel wél open was, dus alles staat negatief. Kijk liever naar hoofdstuk 10 "
            "(Analytics) waar je zelf de periode kunt kiezen.", "info"))
    A(Spacer(1, 8))
    A(Paragraph("Wat beter kan", st_h2))
    A(Paragraph("De tegels met tips van Shopify (reservebetaalmethode, Shopify Forms) zijn reclame "
                "voor hun eigen functies. Je mag ze wegklikken; ze zeggen niets over jullie winkel.", st_p))
    A(PageBreak())

    # ---- 2 Bestellingen --------------------------------------------------
    v_ += sectie("HOOFDSTUK 2", "Bestellingen", "Bestellingen",
                 "Alles wat klanten besteld hebben, plus de winkelwagentjes die nooit tot een "
                 "bestelling zijn gekomen.")
    A(cijferrij([(f"{t['ordersCount']['count']:,}".replace(",", "."), "bestellingen"),
                 (f"{t['abandonedCheckoutsCount']['count']}", "afgebroken checkouts"),
                 ("4", "openstaand"), ("0", "retouren geregistreerd")]))
    A(Spacer(1, 10))
    A(Paragraph("De subgroepen", st_h2))
    A(tabel(["Subgroep", "Wat het is", "Bij jullie"], [
        ["<b>Alle bestellingen</b>", "Elke bestelling met status, betaling en verzending.",
         "10.000+ (Shopify telt niet verder). Laatste: 9 juni 2026."],
        ["<b>Concepten</b>", "Bestellingen die je zelf aanmaakt, bijvoorbeeld voor een klant aan de telefoon "
         "of een factuur op rekening.", "Leeg."],
        ["<b>Afgebroken checkouts</b>", "Klanten die hun gegevens invulden maar niet afrekenden. Shopify kan "
         "ze automatisch een herinneringsmail sturen.", "0 — logisch, de winkel is dicht."],
        ["<b>Verzendlabels</b>", "Labels kopen en printen vanuit Shopify zelf.",
         "Niet in gebruik; verzending loopt via het magazijn."],
    ], [30 * mm, 70 * mm, 65 * mm]))
    A(Spacer(1, 8))
    A(kaart("<b>Afgebroken checkouts zijn straks je makkelijkste omzet.</b> Gemiddeld haakt 70% van de "
            "mensen af in de checkout. Een automatische herinnering na een paar uur haalt daar "
            "doorgaans 5 tot 10% van terug. Zet dit aan vóór de heropening — het staat bij "
            "Instellingen → Meldingen, of je regelt het via Klaviyo.", "let_op"))
    A(Spacer(1, 8))
    A(Paragraph("Retouren", st_h2))
    A(Paragraph("In Shopify staan <b>nul</b> retouren geregistreerd. Dat klopt niet met de "
                "werkelijkheid: er liggen circa 2.150 teruggekomen stuks in het magazijn. De "
                "retouren liepen via <b>Returnless</b>, een apart platform, en zijn nooit in Shopify "
                "verwerkt. Daardoor weet Shopify niet dat die artikelen weer op voorraad zijn — "
                "en dat is precies waarom de voorraadstanden negatief staan.", st_p))
    A(PageBreak())

    # ---- 3 Producten -----------------------------------------------------
    v_ += sectie("HOOFDSTUK 3", "Producten", "Producten",
                 "Je artikelen, de maten en kleuren daarvan, en hoeveel er van elk op voorraad ligt.")
    A(cijferrij([(f"{t['productsCount']['count']}", "producten"),
                 (f"{t['actief']['count']}", "actief"),
                 (f"{t['concept']['count']}", "concept"),
                 (f"{v['varianten']}", "varianten")]))
    A(Spacer(1, 10))
    A(Paragraph("De subgroepen", st_h2))
    A(tabel(["Subgroep", "Wat het is", "Bij jullie"], [
        ["<b>Alle producten</b>", "Elk artikel met foto's, prijs, beschrijving en varianten.",
         f"{t['productsCount']['count']} producten: {t['actief']['count']} actief, {t['concept']['count']} nog concept."],
        ["<b>Collecties</b>", "Groepen producten, bijvoorbeeld 'Longsleeves' of 'Sale'. Bepaalt wat "
         "klanten in het menu zien.", "In gebruik."],
        ["<b>Voorraad</b>", "Hoeveel er van elke maat ligt, per locatie.",
         f"<font color='#b3261e'><b>{v['negatief']} van {v['varianten']} varianten staat negatief</b></font>"],
        ["<b>Inkooporders</b>", "Bestellingen bij je leverancier bijhouden.", "Niet in gebruik."],
        ["<b>Overdrachten</b>", "Voorraad verplaatsen tussen locaties.", "Niet in gebruik."],
        ["<b>Cadeaubonnen</b>", "Digitale cadeaukaarten verkopen.", "Niet in gebruik."],
    ], [30 * mm, 70 * mm, 65 * mm]))
    A(Spacer(1, 8))
    A(kaart(f"<b>De voorraad klopt niet, en dat gaat je geld kosten.</b> Van de {v['varianten']} "
            f"varianten staan er {v['negatief']} op een negatief aantal, samen <b>{v['totaal']} stuks</b>. "
            "Negatieve voorraad betekent: er is meer verkocht dan er volgens Shopify lag. Er is nooit "
            "voorraad ingeboekt en nooit een retour teruggeboekt.<br/><br/>"
            "<b>Waarom dit erg is bij de heropening:</b> Shopify weet niet wat er ligt, dus je kunt niet "
            "vertrouwen op 'uitverkocht'. Je verkoopt dingen die er niet zijn, of je verkoopt niets "
            "terwijl er 40 stuks liggen.<br/><br/>"
            "<b>Wat je doet:</b> één fysieke telling per model en maat, die invoeren als beginvoorraad. "
            "Dat is een dag werk en daarna klopt alles.", "probleem"))
    A(Spacer(1, 8))
    A(Paragraph("Drie locaties", st_h2))
    A(Paragraph("Er staan drie voorraadlocaties actief: <b>Farmers Atelier NL Warehouse</b>, "
                "<b>FILLBOX</b> en <b>Shop location</b>. Met Innostock erbij worden dat er vier. "
                "Elke locatie die niet meer gebruikt wordt kun je beter uitzetten: anders kan Shopify "
                "voorraad toewijzen aan een magazijn waar niets ligt.", st_p))
    A(PageBreak())

    # ---- 4 Klanten -------------------------------------------------------
    v_ += sectie("HOOFDSTUK 4", "Klanten", "Klanten",
                 "Iedereen die ooit besteld heeft of zich heeft ingeschreven, en de groepen die je "
                 "daarvan kunt maken.")
    A(cijferrij([(f"{t['klanten']['totalCount']:,}".replace(",", "."), "klanten totaal"),
                 (f"{t['abonnees']['totalCount']:,}".replace(",", "."), "e-mailabonnees"),
                 (f"{t['kopers']['totalCount']:,}".replace(",", "."), "heeft ooit besteld"),
                 (f"{len(d['segmenten'])}", "segmenten")]))
    A(Spacer(1, 10))
    A(Paragraph("Wat dit betekent", st_h2))
    A(Paragraph(f"<b>{t['abonnees']['totalCount']:,}</b>".replace(",", ".") +
                " mensen hebben toestemming gegeven voor e-mail. Dat is jullie grootste bezit voor de "
                "heropening: een lijst waar je zonder advertentiekosten bij kunt. "
                f"Daarvan hebben er <b>{t['kopers']['totalCount']:,}</b>".replace(",", ".") +
                " ook echt besteld — die kennen het merk en de pasvorm al.", st_p))
    A(Spacer(1, 6))
    A(Paragraph("Segmenten", st_h2))
    A(Paragraph("Een segment is een groep klanten die aan een voorwaarde voldoet, bijvoorbeeld "
                "'heeft meer dan één keer gekocht'. Handig om een mail alleen naar de juiste mensen "
                "te sturen. Er staan er " + str(len(d["segmenten"])) + ", waaronder:", st_p))
    A(tabel(["Segment", "Wie daarin zitten"],
            [[s, ""] for s in d["segmenten"][:6]], [70 * mm, 95 * mm]))
    A(Spacer(1, 8))
    A(kaart("<b>Vier van de negen segmenten gaan over 'companies'</b> — zakelijke klanten. Die functie "
            "gebruiken jullie niet, en ze staan er dubbel in. Opruimen maakt het overzicht een stuk "
            "leesbaarder.<br/><br/>"
            "Wat je mist voor de heropening: een segment <b>'kocht in de laatste 12 maanden'</b>. Die "
            "mensen mailen levert het meeste op — ze kennen je nog.", "let_op"))
    A(PageBreak())

    # ---- 5 Groei & Kortingen --------------------------------------------
    v_ += sectie("HOOFDSTUK 5", "Groei en Kortingen", "Kortingen",
                 "Kortingscodes, acties en de marketingfuncties van Shopify zelf.")
    A(cijferrij([(f"{len(d['kortingen'])}", "kortingscodes"),
                 (f"{actieve_korting}", "actief"),
                 (f"{verlopen}", "verlopen"),
                 ("0", "lopende campagnes")]))
    A(Spacer(1, 10))
    A(Paragraph("Wat er bij jullie staat", st_h2))
    A(Paragraph(f"Er staan <b>{len(d['kortingen'])} kortingscodes</b>, en daarvan zijn er "
                f"<b>{verlopen} verlopen</b>. Namen als CHRISTMAS10, FARMERS10, WELCOMEFARMERS en "
                "een reeks persoonlijke codes (FOLKERT-FARM, Quinten-FARM, Robiencode) — "
                "waarschijnlijk voor influencers en vrienden.", st_p))
    A(Spacer(1, 6))
    A(kaart("<b>Verlopen codes werken niet meer, maar klanten proberen ze wel.</b> Staat er op een oude "
            "Instagram-post nog FARMERS10, dan krijgt iemand bij de heropening 'code ongeldig' te "
            "zien en haakt af. Dat is een klantenservicevraag die je kunt voorkomen.<br/><br/>"
            "<b>Wat je doet:</b> ruim op wat je nooit meer gebruikt, en maak één nieuwe welkomstcode "
            "voor de heropening. Codes die nog op oude posts staan kun je beter opnieuw activeren dan "
            "laten doodbloeden.", "let_op"))
    A(Spacer(1, 8))
    A(Paragraph("Groei", st_h2))
    A(Paragraph("Onder Groei zitten Shopify's eigen marketingfuncties: campagnes, automatiseringen en "
                "apps. Er lopen <b>geen campagnes</b>. Dat klopt, want de e-mailmarketing gaat via "
                "Klaviyo — zie hoofdstuk 12.", st_p))
    A(PageBreak())

    # ---- 6 Content -------------------------------------------------------
    v_ += sectie("HOOFDSTUK 6", "Content", "Content",
                 "Alle teksten, pagina's, blogs en bestanden die op de website staan.")
    A(cijferrij([(f"{len(d['paginas'])}", "pagina's"),
                 (f"{len(concept_pag)}", "niet gepubliceerd"),
                 ("1", "blog"), ("0", "blogartikelen")]))
    A(Spacer(1, 10))
    A(Paragraph("De subgroepen", st_h2))
    A(tabel(["Subgroep", "Wat het is", "Bij jullie"], [
        ["<b>Metavelden</b>", "Extra velden bij een product, bijvoorbeeld een maattabel of "
         "'model draagt maat M'.", "20 velden ingericht — netjes gedaan."],
        ["<b>Bestanden</b>", "Afbeeldingen, iconen en documenten die op de site gebruikt worden.",
         "In gebruik: productfoto's, maar ook losse iconen (verzending, betaling, klantenservice)."],
        ["<b>Menu's</b>", "De navigatie boven- en onderaan de site.", "Ingericht."],
        ["<b>Blogberichten</b>", "Artikelen voor nieuws of vindbaarheid in Google.",
         "1 blog ('News'), <b>0 artikelen</b>."],
    ], [30 * mm, 70 * mm, 65 * mm]))
    A(Spacer(1, 8))
    A(Paragraph("De pagina's", st_h2))
    A(Paragraph("Er staan " + str(len(d["paginas"])) + " pagina's. De belangrijkste voor de "
                "klantenservice zijn <b>Shipping &amp; Returnpolicy</b>, <b>FAQs</b>, <b>Contact us</b> "
                "en <b>Track your order</b>. Die bepalen hoeveel mensen jullie hoeven te mailen: "
                "hoe duidelijker die pagina's, hoe minder vragen.", st_p))
    A(Spacer(1, 4))
    A(tabel(["Nog niet gepubliceerd", "Wat dat betekent"],
            [[p, "Staat klaar maar is voor klanten niet zichtbaar"] for p in concept_pag] or
            [["geen", "alles staat online"]], [55 * mm, 110 * mm]))
    A(Spacer(1, 8))
    A(kaart("<b>Drie oude Black Friday-pagina's staan nog online</b> (Meta, TikTok en Klaviyo-versies). "
            "Die verwijzen naar een actie die voorbij is. Ze zijn nu onzichtbaar omdat de winkel dicht "
            "is, maar bij de heropening staan ze er weer — en Google heeft ze mogelijk geïndexeerd.<br/><br/>"
            "Ook goed om te weten: de <b>blog is leeg</b>. Voor vindbaarheid in Google is dat een gemiste "
            "kans, maar het is geen prioriteit voor de heropening.", "let_op"))
    A(PageBreak())

    # ---- 7 Markten en Financien -----------------------------------------
    v_ += sectie("HOOFDSTUK 7", "Markten en Financiën", "Markten",
                 "Naar welke landen je verkoopt, in welke valuta, en het geldverkeer.")
    A(Paragraph("Markten", st_h2))
    A(Paragraph("Hier stel je in naar welke landen je verkoopt en tegen welke prijzen. Jullie "
                "verkopen in <b>euro's</b>, met verzending naar Nederland, de EU, het Verenigd "
                "Koninkrijk, de VS, Canada en Australië.", st_p))
    A(Spacer(1, 6))
    A(Paragraph("Financiën", st_h2))
    A(Paragraph("Hier zie je wat er binnenkomt en wanneer het wordt uitbetaald, plus facturen van "
                "Shopify zelf. Het abonnement is <b>" + sh["plan"]["displayName"] + "</b>.", st_p))
    A(Spacer(1, 6))
    A(kaart("Het <b>Grow-abonnement</b> (circa $105 per maand) is precies wat nodig is om via een eigen "
            "app bij klantgegevens te kunnen. Op het goedkopere Basic zou het klantenservicesysteem "
            "wel de bestelling zien maar niet wie de klant is. Goede keuze dus — maar het loopt wel "
            "door terwijl de winkel dicht is.", "info"))
    A(PageBreak())

    # ---- 8 Verzending ----------------------------------------------------
    v_ += sectie("HOOFDSTUK 8", "Verzending en bezorging", "Instellingen",
                 "Wat verzending kost per land, en vanaf welk bedrag het gratis is. "
                 "Te vinden onder Instellingen → Verzending en bezorging.")
    zones = []
    for e in d["verzending"]:
        for g in e["node"]["profileLocationGroups"]:
            for z in g["locationGroupZones"]["edges"]:
                naam = z["node"]["zone"]["name"]
                tarieven = []
                for m in z["node"]["methodDefinitions"]["edges"]:
                    mn = m["node"]
                    p = ((mn.get("rateProvider") or {}).get("price") or {}).get("amount")
                    if p is not None:
                        tarieven.append(f"{mn['name']}: € {float(p):.2f}".replace(".", ","))
                zones.append([naam, "<br/>".join(tarieven) or "—"])
    A(tabel(["Zone", "Tarieven"], zones, [45 * mm, 120 * mm]))
    A(Spacer(1, 8))
    A(kaart("<b>Er staat overal 'Free Shipping' van € 0,00 naast het betaalde tarief.</b> Dat is "
            "waarschijnlijk bedoeld als 'gratis vanaf een bedrag', maar zoals het er nu staat kan een "
            "klant altijd gratis verzending kiezen — ook bij een bestelling van € 10.<br/><br/>"
            "<b>Controleer dit vóór de heropening.</b> Als er geen drempel onder zit, verstuur je elk "
            "pakket op eigen kosten. Bij PostNL is dat € 5,10 per zending, en dat gaat er direct van "
            "je marge af.", "probleem"))
    A(Spacer(1, 8))
    A(Paragraph("Ook opvallend: naar de <b>Verenigde Staten</b> rekenen jullie € 4,95, hetzelfde als "
                "binnen Nederland. Werkelijke verzending naar de VS kost een veelvoud daarvan. Dat "
                "was mogelijk een bewuste keuze om de drempel te verlagen, maar het is goed om te "
                "weten dat elke Amerikaanse bestelling geld kost in plaats van oplevert.", st_p))
    A(PageBreak())

    # ---- 9 Webshop en thema's -------------------------------------------
    v_ += sectie("HOOFDSTUK 9", "Webshop en thema's", "Webshop",
                 "De website zelf: de vormgeving, de indeling en welke versie live staat.")
    A(cijferrij([(f"{len(d['themas'])}", "thema's"), ("1", "live"),
                 (f"{ongebruikt}", "ongebruikt"), (f"{len(d['kanalen'])}", "verkoopkanalen")]))
    A(Spacer(1, 10))
    A(Paragraph("Wat er live staat", st_h2))
    A(Paragraph(f"Het gepubliceerde thema heet <b>{live_thema}</b>. Dat is wat klanten zien.", st_p))
    A(Spacer(1, 4))
    A(tabel(["Thema", "Rol", "Laatst gewijzigd"],
            [[x["name"][:40],
              "<b><font color='#2f5d3a'>LIVE</font></b>" if x["role"] == "MAIN" else x["role"].lower(),
              (x["updatedAt"] or "")[:10]] for x in d["themas"]], [75 * mm, 35 * mm, 55 * mm]))
    A(Spacer(1, 8))
    A(kaart(f"<b>Er staan {len(d['themas'])} thema's, waarvan er {ongebruikt} ongebruikt zijn.</b> "
            "Namen als 'JHGFJJ', 'Devlopment' (met tikfout) en zes keer 'Kopie van MAIN FARMERS "
            "ATELIER' zeggen niemand nog iets. Over een half jaar weet je niet meer welke waarvoor was, "
            "en dan durf je er geen een weg te gooien.<br/><br/>"
            "<b>Voorstel:</b> hernoemen volgens één vorm — <i>doel | datum</i>, bijvoorbeeld "
            "'Q4 heropening | 28 SEP'. Bewaar het live thema plus één reservekopie, en gooi de rest weg. "
            "Shopify bewaart geen geschiedenis van verwijderde thema's, dus download eerst een kopie.", "let_op"))
    A(Spacer(1, 8))
    A(Paragraph("Zo werken we aan de website", st_h2))
    A(Paragraph("Shopify kan precies wat je vroeg: je maakt een kopie van het live thema, werkt daarin, "
                "bekijkt het via een voorbeeldlink, en publiceert pas als alles klaar is. Het live thema "
                "blijft ondertussen ongemoeid, en terugzetten is één klik.", st_p))
    A(tabel(["Stap", "Wie", "Wat er gebeurt"], [
        ["1. Kopie maken", "Claude", "Het live thema wordt gedupliceerd met een duidelijke naam en datum."],
        ["2. Aanpassen", "Claude", "Alle wijzigingen gebeuren in die kopie. Klanten merken er niets van."],
        ["3. Bekijken", "Wieger", "Je krijgt een voorbeeldlink en kunt alles nalopen."],
        ["4. Publiceren", "<b>Wieger</b>", "Alleen jij zet hem live. Dat is de enige stap die klanten raakt."],
    ], [30 * mm, 25 * mm, 110 * mm]))
    A(PageBreak())

    # ---- 10 Analytics ----------------------------------------------------
    v_ += sectie("HOOFDSTUK 10", "Analytics", "Analytics",
                 "Rapporten over verkoop, bezoekers, producten en retouren.")
    A(Paragraph("Wat je hier kunt", st_h2))
    A(Paragraph("Shopify heeft tientallen kant-en-klare rapporten. De nuttigste voor jullie:", st_p))
    A(tabel(["Rapport", "Waarvoor", "Wat het bij jullie laat zien"], [
        ["Verkoop per product", "Welke modellen lopen en welke niet.",
         "34.695 stuks ooit verkocht, € 1.255.810 omzet."],
        ["Herroepen artikelen per product", "Wat er geretourneerd wordt en waarom.",
         "<font color='#b3261e'><b>Overal 0</b> — retouren zijn nooit in Shopify verwerkt</font>"],
        ["Sessies per verwijzer", "Waar bezoekers vandaan komen.", "Bruikbaar zodra de winkel weer open is."],
        ["Bestellingen in de tijd", "Hoe de verkoop loopt.", "Stopt abrupt op 9 juni 2026."],
    ], [42 * mm, 55 * mm, 68 * mm]))
    A(Spacer(1, 8))
    A(kaart("<b>Let op de periode.</b> Rapporten staan standaard op 'afgelopen 30 dagen' en dan is alles "
            "leeg, want de winkel is dicht. Zet de periode op een jaar of langer om iets zinnigs te zien. "
            "Dat kostte mij ook even: het retourrapport leek leeg tot ik de periode op 900 dagen zette — "
            "en toen bleek het écht overal nul te zijn.", "info"))
    A(PageBreak())

    # ---- 11 Instellingen -------------------------------------------------
    v_ += sectie("HOOFDSTUK 11", "Instellingen", "Instellingen",
                 "De motorkap: betalingen, checkout, belastingen, e-mail en gebruikers.")
    A(Paragraph("Wat er ingesteld staat", st_h2))
    A(tabel(["Instelling", "Bij jullie", "Oordeel"], [
        ["Winkelnaam", sh["name"], "goed"],
        ["Domein", sh["primaryDomain"]["host"] + (" (SSL aan)" if sh["primaryDomain"]["sslEnabled"] else ""), "goed"],
        ["Afzenderadres", sh["email"], "goed"],
        ["Valuta / tijdzone", sh["currencyCode"] + " · " + sh["ianaTimezone"], "goed"],
        ["Prijzen incl. btw", "ja" if sh["taxesIncluded"] else "nee",
         "goed — Nederlandse klanten verwachten dat"],
        ["Btw op verzending", "ja" if sh["taxShipping"] else "nee",
         "<font color='#b7791f'>controleren</font> — in NL hoort verzending meestal wél btw te dragen"],
        ["Klantaccounts", sh["customerAccounts"].lower(),
         "optioneel = klanten mogen bestellen zonder account. Goed voor de conversie."],
        ["Gewichtseenheid", sh["weightUnit"].lower(), "goed"],
    ], [42 * mm, 58 * mm, 65 * mm]))
    A(Spacer(1, 8))
    A(kaart("<b>Je e-maildomein is niet geauthenticeerd.</b> Bij Instellingen → Meldingen staat "
            "'Gedeauthenticeerd' en DMARC is niet ingesteld. Shopify verstuurt daardoor namens jullie "
            "vanaf een eigen adres (store+79370060104@shopifyemail.com) in plaats van "
            "farmersatelier.com.<br/><br/>"
            "<b>Waarom dit nu belangrijk is:</b> Gmail en Outlook zijn sinds 2024 streng voor wie veel "
            "mail stuurt. Zonder SPF, DKIM en DMARC belandt bulkmail in de spam of wordt hij geweigerd. "
            "Met 17.523 abonnees valt jullie heropeningsmail precies in die categorie.<br/><br/>"
            "<b>Wat je doet:</b> in Shopify bij Meldingen op 'Authenticeren' klikken; Shopify geeft dan "
            "de DNS-regels die bij de domeinbeheerder ingevoerd moeten worden. Een half uur werk, en het "
            "bepaalt of je heropeningsmail aankomt of niet.", "probleem"))
    A(PageBreak())

    # ---- 12 Apps en koppelingen -----------------------------------------
    v_ += sectie("HOOFDSTUK 12", "Apps en koppelingen", "Instellingen",
                 "Externe programma's die aan de winkel vastzitten.")
    A(tabel(["App", "Wat het doet", "Opmerking"], [
        ["<b>Klaviyo</b>", "E-mail- en sms-marketing.",
         "Hier zitten jullie 17.523 abonnees. Campagnes horen hier te blijven."],
        ["<b>Returnless</b>", "Retourportaal voor klanten.",
         "<font color='#b7791f'><b>Hier zit jullie retouradministratie</b></font> — niet in Shopify."],
        ["<b>Track by Loop</b>", "Track-and-trace-pagina ('waar is mijn bestelling').",
         "Geen retourplatform, ondanks de naam."],
        ["<b>GoedGepickt</b> en <b>Picqer</b>", "Magazijnsoftware — allebei.",
         "<font color='#b7791f'>Twee systemen naast elkaar; met Innostock erbij worden het er drie.</font>"],
        ["<b>Orderly Emails</b>", "Vormgeving van bevestigingsmails.", "Actief."],
        ["<b>TripleWhale</b>", "Analyse van advertenties en omzet.", "Actief."],
        ["<b>Farmers Atelier Support</b>", "Jullie eigen klantenservicesysteem.",
         "<font color='#2f5d3a'><b>Nieuw, gekoppeld op 28-09-2026</b></font>"],
    ], [38 * mm, 55 * mm, 72 * mm]))
    A(Spacer(1, 8))
    A(kaart("<b>Er staan geen webhooks.</b> Een webhook is een seintje dat Shopify automatisch geeft "
            "als er iets gebeurt — bijvoorbeeld 'er is een bestelling binnen'. Zonder webhooks moet elk "
            "systeem zelf blijven vragen of er nieuws is, wat traag en foutgevoelig is.<br/><br/>"
            "Voor het klantenservicesysteem betekent dit dat een nieuwe bestelling niet meteen "
            "binnenkomt. Dit kan ik instellen zodra jullie dat willen.", "let_op"))
    A(Spacer(1, 8))
    A(kaart("<b>Twee magazijnsystemen naast elkaar is vragen om problemen.</b> GoedGepickt en Picqer doen "
            "grotendeels hetzelfde, en met Innostock erbij worden het er drie. Zodra twee systemen "
            "dezelfde voorraad bijhouden, lopen ze uit elkaar — en dat is waarschijnlijk precies hoe "
            "die negatieve voorraadstanden zijn ontstaan.<br/><br/>"
            "<b>Vraag om te beantwoorden vóór de heropening:</b> welk systeem is straks de baas over de "
            "voorraad? Eén, en de rest eruit.", "probleem"))
    A(PageBreak())

    # ---- Samenvatting ----------------------------------------------------
    A(Paragraph("Wat er moet gebeuren", st_h1))
    A(Paragraph("Op volgorde van wat het meeste kost als je het laat liggen.", st_p))
    A(Spacer(1, 6))
    A(tabel(["#", "Wat", "Waarom het niet kan wachten", "Wie"], [
        ["1", "<b>E-maildomein authenticeren</b>",
         "Zonder SPF, DKIM en DMARC belandt je heropeningsmail naar 17.523 mensen in de spam.", "Wieger"],
        ["2", "<b>Voorraad fysiek tellen en invoeren</b>",
         f"{v['negatief']} varianten staan negatief. Je weet nu niet wat je kunt verkopen.", "Wieger"],
        ["3", "<b>Gratis verzending controleren</b>",
         "Staat nu overal op € 0,00 zonder zichtbare drempel. Elk pakket kost je dan geld.", "Wieger"],
        ["4", "<b>Kiezen welk magazijnsysteem de baas is</b>",
         "Drie systemen die dezelfde voorraad bijhouden lopen gegarandeerd uit elkaar.", "Wieger"],
        ["5", "<b>Returnless uitlezen</b>",
         "Daar staat wat er werkelijk aan retouren is teruggekomen.", "samen"],
        ["6", "<b>Webhooks instellen</b>",
         "Zodat een nieuwe bestelling meteen in de klantenservice staat.", "Claude"],
        ["7", "<b>Thema's opruimen en hernoemen</b>",
         f"{len(d['themas'])} thema's met namen als 'JHGFJJ'. Straks durft niemand meer iets weg te gooien.", "Claude"],
        ["8", "<b>Verlopen kortingscodes opruimen</b>",
         f"{verlopen} verlopen codes. Klanten proberen ze en krijgen een foutmelding.", "Claude"],
        ["9", "<b>Oude Black Friday-pagina's weghalen</b>",
         "Verwijzen naar een actie die voorbij is.", "Claude"],
        ["10", "<b>Afgebroken checkouts aanzetten</b>",
         "Gemiddeld haal je daar 5 tot 10% van terug. Gratis omzet.", "samen"],
    ], [8 * mm, 45 * mm, 92 * mm, 20 * mm]))
    A(Spacer(1, 10))
    A(kaart("Dit rapport is gemaakt op basis van de <b>live gegevens</b> uit Shopify, opgehaald via de "
            "koppeling van het klantenservicesysteem. Draai <i>scripts/shopify_analyse.py</i> opnieuw "
            "voor een verse stand.", "info"))

    # ---- bouwen ----------------------------------------------------------
    def voettekst(canv, doc_):
        canv.saveState()
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(GRIJS)
        canv.drawString(22 * mm, 12 * mm, f"Farmers Atelier · Shopify-analyse · {date.today().strftime('%d-%m-%Y')}")
        canv.drawRightString(188 * mm, 12 * mm, f"{doc_.page}")
        canv.setStrokeColor(LIJN)
        canv.line(22 * mm, 16 * mm, 188 * mm, 16 * mm)
        canv.restoreState()

    doc = BaseDocTemplate(pad, pagesize=A4, title="Shopify-analyse Farmers Atelier",
                          author="Farmers Atelier Support", leftMargin=22 * mm,
                          rightMargin=22 * mm, topMargin=18 * mm, bottomMargin=20 * mm)
    doc.addPageTemplates([PageTemplate(id="std", frames=[
        Frame(22 * mm, 20 * mm, 166 * mm, 257 * mm, id="f", leftPadding=0, rightPadding=0,
              topPadding=0, bottomPadding=0)], onPage=voettekst)])
    doc.build(v_)


def main() -> int:
    print("Gegevens ophalen uit Shopify…")
    d = haal_op()
    map_ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "shopify-analyse")
    os.makedirs(map_, exist_ok=True)
    pad = os.path.join(map_, "Shopify-analyse.pdf")
    bouw(d, pad)
    print(f"Klaar: {pad}")
    print(f"  {os.path.getsize(pad) // 1024} kB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
