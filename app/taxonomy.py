"""Intent-taxonomie, prioriteiten, sentiment en automatiseringsniveaus.

Gebaseerd op Gorgias' intentlijst en de vergelijking in docs/onderzoek/02 (§D), vertaald
naar wat Farmers Atelier echt krijgt. Elke intent heeft:
  - label (NL, voor de UI), group (voor de inbox-views)
  - required_info: wat de AI nodig heeft vóór ze kan antwoorden
  - default_level: hoe ver de AI standaard mag gaan (zie LEVELS)
  - default_priority
Het niveau per intent is in Instellingen aanpasbaar (tabel settings, key "level:<intent>").
"""

from __future__ import annotations

# Automatiseringsniveaus, oplopend. "Begin voorzichtig": standaard bijna alles op 'draft'.
LEVELS = {
    "analyze": "Niveau 1 — AI leest en categoriseert alleen",
    "draft": "Niveau 2 — AI maakt een conceptantwoord, wij versturen",
    "auto_reply": "Niveau 3 — AI mag zelf antwoorden bij veilige vragen",
    "action": "Niveau 4 — AI mag simpele acties voorstellen (met goedkeuring)",
    "workflow": "Niveau 5 — AI handelt complete workflows af",
}
LEVEL_ORDER = ["analyze", "draft", "auto_reply", "action", "workflow"]

PRIORITIES = ["low", "normal", "high", "critical"]
SENTIMENTS = ["positive", "neutral", "negative"]

# Vlaggen die altijd naar een mens leiden, ongeacht niveau.
ESCALATION_FLAGS = {
    "human_requested": "Klant vraagt om een mens",
    "legal_threat": "Juridische dreiging",
    "chargeback": "Chargeback / betaalgeschil",
    "abusive": "Beledigend of dreigend",
    "vip": "VIP-klant",
    "repeat_contact": "Meerdere keren contact over hetzelfde",
    "press_or_partner": "Pers / samenwerking",
}

INTENTS = {
    # --- Verzending ---
    "shipping.status": dict(label="Waar is mijn bestelling?", group="verzending",
        required_info=["order_number"], default_level="draft", default_priority="normal",
        description="Klant vraagt naar de status of levertijd van een bestelling (WISMO)."),
    "shipping.delay": dict(label="Vertraging", group="verzending",
        required_info=["order_number"], default_level="draft", default_priority="normal",
        description="Bestelling is later dan beloofd of tracking staat stil."),
    "shipping.delivery_issue": dict(label="Bezorgprobleem", group="verzending",
        required_info=["order_number"], default_level="draft", default_priority="high",
        description="Afgeleverd maar niet ontvangen, kwijt, of pakket beschadigd aangekomen."),
    "shipping.address_change": dict(label="Adres wijzigen", group="orderproblemen",
        required_info=["order_number", "new_address"], default_level="draft", default_priority="high",
        description="Klant wil het bezorgadres wijzigen vóór verzending."),
    "shipping.policy": dict(label="Verzendkosten / -beleid", group="productvragen",
        required_info=[], default_level="draft", default_priority="low",
        description="Vraag over verzendkosten, landen, levertijd in het algemeen."),
    # --- Order ---
    "order.cancel": dict(label="Order annuleren", group="orderproblemen",
        required_info=["order_number"], default_level="draft", default_priority="high",
        description="Klant wil de bestelling annuleren."),
    "order.change": dict(label="Order wijzigen", group="orderproblemen",
        required_info=["order_number", "new_variant"], default_level="draft", default_priority="high",
        description="Klant wil maat/kleur/aantal wijzigen vóór verzending."),
    "order.wrong_item": dict(label="Verkeerd artikel ontvangen", group="orderproblemen",
        required_info=["order_number", "photo"], default_level="draft", default_priority="high",
        description="Klant ontving een ander artikel dan besteld."),
    "order.missing_item": dict(label="Artikel ontbreekt", group="orderproblemen",
        required_info=["order_number"], default_level="draft", default_priority="high",
        description="Er ontbreekt een artikel in het pakket."),
    "order.damaged": dict(label="Beschadigd artikel", group="orderproblemen",
        required_info=["order_number", "photo"], default_level="draft", default_priority="high",
        description="Artikel is beschadigd of defect."),
    "order.invoice": dict(label="Factuur", group="algemeen",
        required_info=["order_number"], default_level="draft", default_priority="low",
        description="Klant wil een factuur of bon."),
    # --- Retour / ruil / refund ---
    "return.request": dict(label="Retour aanvragen", group="retouren",
        required_info=["order_number", "items", "reason"], default_level="draft", default_priority="normal",
        description="Klant wil iets retourneren."),
    "return.status": dict(label="Retourstatus", group="retouren",
        required_info=["order_number"], default_level="draft", default_priority="normal",
        description="Is mijn retour aangekomen / wanneer krijg ik mijn geld?"),
    "return.policy": dict(label="Retourbeleid", group="retouren",
        required_info=[], default_level="draft", default_priority="low",
        description="Vraag over retourtermijn, voorwaarden of kosten."),
    "exchange.request": dict(label="Omruilen / verkeerde maat", group="retouren",
        required_info=["order_number", "items", "wanted_variant"], default_level="draft", default_priority="normal",
        description="Klant wil een andere maat of kleur."),
    "refund.request": dict(label="Refund aanvragen", group="retouren",
        required_info=["order_number", "reason"], default_level="analyze", default_priority="high",
        description="Klant wil geld terug (buiten de normale retourroute)."),
    "refund.status": dict(label="Refundstatus", group="retouren",
        required_info=["order_number"], default_level="draft", default_priority="normal",
        description="Refund is nog niet ontvangen."),
    # --- Product ---
    "product.question": dict(label="Productvraag", group="productvragen",
        required_info=[], default_level="draft", default_priority="low",
        description="Vraag over een product: pasvorm, details, wassen."),
    "product.material": dict(label="Materiaalvraag", group="productvragen",
        required_info=[], default_level="draft", default_priority="low",
        description="Waar is het van gemaakt, herkomst, duurzaamheid."),
    "product.size_advice": dict(label="Maatadvies", group="productvragen",
        required_info=["measurements_or_reference"], default_level="draft", default_priority="low",
        description="Welke maat moet ik nemen?"),
    "stock.request": dict(label="Voorraadvraag", group="productvragen",
        required_info=["product", "size"], default_level="draft", default_priority="low",
        description="Is/wanneer komt X (in maat Y) weer op voorraad?"),
    # --- Betaling / korting ---
    "discount.question": dict(label="Kortingsvraag", group="algemeen",
        required_info=[], default_level="draft", default_priority="low",
        description="Kortingscode werkt niet, korting ontbreekt, actie-vraag."),
    "payment.issue": dict(label="Betalingsprobleem", group="orderproblemen",
        required_info=["order_number"], default_level="analyze", default_priority="high",
        description="Betaling mislukt, dubbel afgeschreven, iDEAL/Klarna-vraag."),
    # --- Klacht / social / overig ---
    "feedback.complaint": dict(label="Klacht", group="klachten",
        required_info=[], default_level="analyze", default_priority="high",
        description="Klant is ontevreden over service, product of merk."),
    "feedback.compliment": dict(label="Compliment / review", group="social",
        required_info=[], default_level="draft", default_priority="low",
        description="Positieve reactie of review."),
    "social.comment": dict(label="Social comment (geen vraag)", group="social",
        required_info=[], default_level="analyze", default_priority="low",
        description="Comment zonder klantenservice-vraag (emoji, tag, reactie)."),
    "partnership": dict(label="Samenwerking / pers / B2B", group="algemeen",
        required_info=[], default_level="analyze", default_priority="low",
        description="Influencer, groothandel, pers, leverancier."),
    "other.question": dict(label="Algemene vraag", group="algemeen",
        required_info=[], default_level="draft", default_priority="normal",
        description="Vraag die nergens anders onder valt."),
    "other.thanks": dict(label="Bedankje / afsluiter", group="algemeen",
        required_info=[], default_level="analyze", default_priority="low",
        description="Bedankt, oké, top — geen antwoord nodig."),
    "spam": dict(label="Spam", group="algemeen",
        required_info=[], default_level="analyze", default_priority="low",
        description="Spam, phishing, auto-reply, nieuwsbrief."),
    "other": dict(label="Anders", group="algemeen",
        required_info=[], default_level="analyze", default_priority="normal",
        description="Onduidelijk; mens beoordeelt."),
}

GROUPS = {
    "verzending": "Verzending",
    "orderproblemen": "Orderproblemen",
    "retouren": "Retouren",
    "productvragen": "Productvragen",
    "klachten": "Klachten",
    "social": "Social",
    "algemeen": "Algemeen",
}

MISSING_INFO_LABELS = {
    "order_number": "ordernummer",
    "photo": "foto",
    "new_address": "nieuw adres",
    "new_variant": "gewenste maat/kleur",
    "wanted_variant": "gewenste maat/kleur",
    "items": "welke artikelen",
    "reason": "reden",
    "product": "welk product",
    "size": "welke maat",
    "measurements_or_reference": "maten of referentiemaat",
    "email": "e-mailadres van de bestelling",
}

CHANNELS = {
    "email": "E-mail",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "tiktok": "TikTok",
    "shopify": "Shopify",
}


def intent_label(intent: str | None) -> str:
    return INTENTS.get(intent or "", {}).get("label", intent or "—")


def intent_group(intent: str | None) -> str:
    return INTENTS.get(intent or "", {}).get("group", "algemeen")


def level_rank(level: str) -> int:
    return LEVEL_ORDER.index(level) if level in LEVEL_ORDER else 0
