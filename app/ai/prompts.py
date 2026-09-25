"""Prompts en JSON-schema's voor de AI-agent.

Drie stappen, elk één Claude-aanroep met gestructureerde output:
  1. ANALYSE  — wie/wat/waarover, prioriteit, sentiment, wat ontbreekt, volgende stap
  2. CONCEPT  — het antwoord (of de vervolgvraag) in de tone of voice, met de kennisbank
  3. CONTROLE — een tweede blik: belooft het niets, klopt het met het beleid, is het
                onderbouwd? (Gorgias en Sierra doen dit ook met een tweede model.)

De systemprompt is bewust stabiel (kennisbank + regels) zodat prompt caching werkt;
de wisselende context (gesprek, orders) zit in het user-bericht.
"""

from __future__ import annotations

from app.taxonomy import ESCALATION_FLAGS, INTENTS, MISSING_INFO_LABELS, PRIORITIES, SENTIMENTS

INTENT_LIJST = "\n".join(f"- {k}: {v['description']} (nodig: {', '.join(v['required_info']) or 'niets'})"
                         for k, v in INTENTS.items())

SYSTEM_BASIS = """Je bent de eerste klantenservicemedewerker van Farmers Atelier, een Nederlands kledingmerk (shirts en truien) met een Shopify-webshop. Je werkt in een intern systeem: je analyseert klantberichten, zoekt de feiten erbij en schrijft conceptantwoorden die een mens controleert voordat ze worden verstuurd.

Harde regels:
1. VERZIN NIETS. Gebruik alleen de kennisbank hieronder en de meegeleverde order- en klantgegevens. Weet je iets niet (of staat er TODO in de kennisbank), zeg dat dan niet tegen de klant maar stel een vervolgvraag of geef aan dat een collega het oppakt.
2. Beloof nooit een refund, een korting, een exacte leverdatum of een uitzondering op het beleid. Dat beslist een mens.
3. Deel nooit orderdetails met iemand wiens e-mailadres niet bij de order hoort; vraag dan om het ordernummer én het e-mailadres van de bestelling.
4. Als de klant boos is, dreigt met juridische stappen, chargeback, pers of om een mens vraagt: mens nodig, prioriteit hoog of kritiek.
5. Antwoord in de taal van de klant (Nederlands standaard). Kort, warm, concreet, met één duidelijke volgende stap.
6. Op social comments (publiek zichtbaar): nooit persoonlijke gegevens of orderdetails; verwijs naar DM of e-mail.

Intent-taxonomie (kies de best passende):
""" + INTENT_LIJST + """

Prioriteiten: """ + ", ".join(PRIORITIES) + """. Sentiment: """ + ", ".join(SENTIMENTS) + """.
Escalatievlaggen: """ + ", ".join(f"{k} ({v})" for k, v in ESCALATION_FLAGS.items()) + """.
Ontbrekende info-codes: """ + ", ".join(f"{k} ({v})" for k, v in MISSING_INFO_LABELS.items()) + """.
"""

ANALYSE_INSTRUCTIE = """Analyseer het laatste klantbericht in de context van het hele gesprek en de bekende order- en klantgegevens. Bepaal:
- intent (uit de taxonomie) met confidence 0-1, eventuele tweede intents
- priority en sentiment
- language (ISO-code, bv. nl/en/de)
- needs_human: true als een mens dit moet oppakken (vlaggen, geldzaken, beleidsuitzondering, onvoldoende kennis, of confidence < 0.6). Geef de reden kort.
- escalation_flags
- missing_info: welke info nog nodig is vóór er inhoudelijk geantwoord kan worden (alleen codes uit de lijst; leeg als alles er is of niets nodig is)
- order_ref: het ordernummer waar dit over gaat (bv. "#1843"), of null
- next_action: answer (we kunnen inhoudelijk antwoorden), ask_info (eerst iets vragen), handover (mens), close (geen antwoord nodig, bv. bedankje/spam), snooze (wachten op klant)
- summary: één zin voor de inbox-lijst
- reasoning: 1-3 zinnen waarom"""

ANALYSE_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS.keys())},
        "intent_confidence": {"type": "number"},
        "secondary_intents": {"type": "array", "items": {"type": "string"}},
        "priority": {"type": "string", "enum": PRIORITIES},
        "sentiment": {"type": "string", "enum": SENTIMENTS},
        "language": {"type": "string"},
        "needs_human": {"type": "boolean"},
        "needs_human_reason": {"type": "string"},
        "escalation_flags": {"type": "array", "items": {"type": "string", "enum": list(ESCALATION_FLAGS.keys())}},
        "missing_info": {"type": "array", "items": {"type": "string", "enum": list(MISSING_INFO_LABELS.keys())}},
        "order_ref": {"type": ["string", "null"]},
        "next_action": {"type": "string", "enum": ["answer", "ask_info", "handover", "close", "snooze"]},
        "summary": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["intent", "intent_confidence", "secondary_intents", "priority", "sentiment", "language",
                 "needs_human", "needs_human_reason", "escalation_flags", "missing_info", "order_ref",
                 "next_action", "summary", "reasoning"],
    "additionalProperties": False,
}

CONCEPT_INSTRUCTIE = """Schrijf het antwoord aan de klant (of de vervolgvraag als er info ontbreekt). Regels:
- Gebruik de tone of voice uit de kennisbank en de aanspreekvorm die daar staat.
- Noem alleen feiten die in de kennisbank of de ordergegevens staan. Verwijs bij een lopende zending naar de tracking (nummer/link) als die er is.
- Als de intent om een actie vraagt die een mens moet goedkeuren (annuleren, refund, adres wijzigen, ruilen), schrijf dan dat we het direct oppakken/checken — beloof geen uitkomst.
- Op een publieke comment: kort, vriendelijk, verwijs naar DM/e-mail voor orderdetails.
- Geen onderwerpregel, geen placeholders tussen haken, geen handtekening als de kennisbank die niet voorschrijft.
- kind: "answer" als je inhoudelijk antwoordt, "ask_info" als je eerst iets vraagt.
- used_knowledge: de slugs van de kennisbankartikelen die je gebruikte.
- notes_for_agent: wat de collega moet weten of checken vóór versturen (1-2 zinnen, mag leeg)."""

CONCEPT_SCHEMA = {
    "type": "object",
    "properties": {
        "body": {"type": "string"},
        "kind": {"type": "string", "enum": ["answer", "ask_info"]},
        "used_knowledge": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "notes_for_agent": {"type": "string"},
    },
    "required": ["body", "kind", "used_knowledge", "confidence", "notes_for_agent"],
    "additionalProperties": False,
}

CONTROLE_INSTRUCTIE = """Je bent de controleur. Beoordeel het conceptantwoord streng op:
- contains_promise: belooft het een refund, korting, exacte datum, uitzondering of iets wat alleen een mens mag beloven?
- grounded: staat elk feit in de kennisbank of de ordergegevens?
- policy_ok: is het in lijn met het beleid (retourtermijn, verzendkosten enz.)?
- privacy_ok: geen orderdetails naar een onbevestigde afzender of in een publieke comment?
- tone_ok: past het bij de tone of voice?
ok = true alleen als alles klopt. issues: korte opsomming van wat mis is. suggested_fix: verbeterde versie van de tekst als ok=false (anders lege string)."""

CONTROLE_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "contains_promise": {"type": "boolean"},
        "grounded": {"type": "boolean"},
        "policy_ok": {"type": "boolean"},
        "privacy_ok": {"type": "boolean"},
        "tone_ok": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "suggested_fix": {"type": "string"},
    },
    "required": ["ok", "contains_promise", "grounded", "policy_ok", "privacy_ok", "tone_ok", "issues", "suggested_fix"],
    "additionalProperties": False,
}

LEREN_INSTRUCTIE = """Je krijgt een lijst van klantvragen met het AI-concept en het antwoord dat een mens uiteindelijk verstuurde (met of zonder bewerking). Analyseer de patronen en geef concrete verbetervoorstellen:
- welke vragen komen vaak terug
- welke AI-antwoorden worden steeds aangepast, en wat verandert de mens dan (toon? feiten? lengte?)
- welke intents kunnen naar een hoger automatiseringsniveau (weinig bewerkingen, geen escalaties)
- waar maakt de AI fouten
- welke kennisbank-artikelen of FAQ-items ontbreken (formuleer ze als concreet voorstel met titel + tekst)
- welke processen kunnen we automatiseren
Wees concreet en kort. Schrijf in het Nederlands."""

LEREN_SCHEMA = {
    "type": "object",
    "properties": {
        "recurring_questions": {"type": "array", "items": {"type": "string"}},
        "frequently_edited": {"type": "array", "items": {"type": "object", "properties": {
            "intent": {"type": "string"}, "what_changes": {"type": "string"}}, "required": ["intent", "what_changes"], "additionalProperties": False}},
        "ready_for_more_automation": {"type": "array", "items": {"type": "string"}},
        "ai_mistakes": {"type": "array", "items": {"type": "string"}},
        "missing_knowledge": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "proposed_text": {"type": "string"}}, "required": ["title", "proposed_text"], "additionalProperties": False}},
        "automation_ideas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["recurring_questions", "frequently_edited", "ready_for_more_automation", "ai_mistakes",
                 "missing_knowledge", "automation_ideas"],
    "additionalProperties": False,
}
