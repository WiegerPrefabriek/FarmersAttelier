"""De AI-agent: analyse, concept, controle en leer-analyse.

Twee implementaties achter dezelfde functies:
- `ClaudeAgent`  — echte aanroepen naar Claude (gestructureerde JSON-output, prompt
                   caching op de kennisbank). Actief zodra er een API-sleutel is.
- `MockAgent`    — trefwoorden + sjablonen. Geen netwerk. Zorgt dat de hele app lokaal
                   werkt en dat de mock-data realistisch is. Elke uitkomst is gemarkeerd
                   met is_mock=1 zodat je in de UI ziet dat het geen echte AI was.

`get_agent()` kiest op basis van de instelling `ai_mode` (auto | claude | mock).
"""

from __future__ import annotations

import json
import re

import config
from app import db, knowledge
from app.ai import prompts
from app.taxonomy import INTENTS, MISSING_INFO_LABELS


# ----------------------------------------------------------------------------------
# Gedeelde contextopbouw
# ----------------------------------------------------------------------------------

def build_context_text(conversation: dict, messages: list[dict], customer: dict | None,
                       orders: list[dict], order: dict | None, fulfillment: dict | None) -> str:
    """De wisselende context als leesbare tekst voor het user-bericht."""
    from app.integrations.shopify import status_summary
    regels = [f"KANAAL: {conversation.get('channel')} via {conversation.get('via')}"]
    if conversation.get("subject"):
        regels.append(f"ONDERWERP: {conversation['subject']}")
    if conversation.get("via") == "comment":
        regels.append("LET OP: dit is een PUBLIEKE comment; antwoord is voor iedereen zichtbaar.")
    if customer:
        regels.append(f"KLANT: {customer.get('name') or 'onbekend'} <{customer.get('email') or 'geen e-mail bekend'}>, "
                      f"{customer.get('orders_count') or 0} eerdere orders, €{(customer.get('total_spent') or 0):.2f} besteed, "
                      f"tags {db.loads(customer.get('tags'), []) if isinstance(customer.get('tags'), str) else customer.get('tags') or []}")
    else:
        regels.append("KLANT: niet herkend in Shopify (geen e-mailmatch).")
    if order:
        regels.append("GEKOPPELDE ORDER: " + status_summary(order))
        for li in order.get("line_items") or []:
            regels.append(f"  - {li.get('quantity')}x {li.get('title')} {li.get('size') or li.get('variant_title') or ''} (€{li.get('price', 0):.2f})")
        tr = order.get("tracking") or {}
        if tr.get("url"):
            regels.append(f"  tracking-url: {tr['url']}")
        if tr.get("estimated_delivery"):
            regels.append(f"  verwachte levering: {tr['estimated_delivery']}")
        adres = order.get("shipping_address") or {}
        if adres:
            regels.append(f"  verzendadres: {adres.get('address1', '')}, {adres.get('zip', '')} {adres.get('city', '')}")
        regels.append(f"  besteld op: {order.get('created_at')}")
    if fulfillment:
        regels.append(f"FULFILLMENT: {fulfillment.get('label')} (bron {fulfillment.get('source')}, bijgewerkt {fulfillment.get('updated_at')})")
    andere = [o for o in orders if not order or o["name"] != order["name"]]
    if andere:
        regels.append("ANDERE ORDERS VAN DEZE KLANT: " + " | ".join(status_summary(o) for o in andere[:5]))
    regels.append("")
    regels.append("GESPREK (oud → nieuw):")
    for m in messages[-12:]:
        wie = {"customer": "KLANT", "agent": "MEDEWERKER", "ai": "AI", "rule": "SYSTEEM", "system": "SYSTEEM"}.get(m.get("author_type"), "?")
        if m.get("kind") == "note":
            wie = "INTERNE NOTITIE"
        bijl = f" [bijlagen: {len(db.loads(m.get('attachments'), []))}]" if db.loads(m.get("attachments"), []) else ""
        regels.append(f"[{wie}] {m.get('body_text', '').strip()}{bijl}")
    return "\n".join(regels)


# ----------------------------------------------------------------------------------
# Claude
# ----------------------------------------------------------------------------------

class ClaudeAgent:
    name = "claude"

    def __init__(self):
        import anthropic
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=config.anthropic_key())
        self.model = config.AI_MODEL

    def _system(self) -> list[dict]:
        toon = db.setting("tone", "")
        kb = knowledge.as_prompt_block()
        return [{"type": "text",
                 "text": prompts.SYSTEM_BASIS + f"\nTone of voice (instelling): {toon}\n\n## KENNISBANK\n{kb}",
                 "cache_control": {"type": "ephemeral"}}]

    def _call(self, instructie: str, context: str, schema: dict, effort: str = "low", max_tokens: int = 4000) -> dict:
        a = self._anthropic
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=max_tokens, system=self._system(),
                messages=[{"role": "user", "content": instructie + "\n\n---\n" + context}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            )
        except a.RateLimitError as fout:
            raise RuntimeError(f"Claude rate limit: {fout}") from fout
        except a.AuthenticationError as fout:
            raise RuntimeError("Claude: ongeldige API-sleutel") from fout
        except a.APIStatusError as fout:
            raise RuntimeError(f"Claude API {fout.status_code}: {fout.message}") from fout
        except a.APIConnectionError as fout:
            raise RuntimeError(f"Claude: geen verbinding ({fout})") from fout
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude weigerde dit bericht te verwerken")
        tekst = next((b.text for b in resp.content if b.type == "text"), "{}")
        data = json.loads(tekst)
        data["_usage"] = {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens,
                          "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0)}
        return data

    def analyze(self, conversation, messages, customer, orders, order, fulfillment) -> dict:
        ctx = build_context_text(conversation, messages, customer, orders, order, fulfillment)
        data = self._call(prompts.ANALYSE_INSTRUCTIE, ctx, prompts.ANALYSE_SCHEMA, effort="low", max_tokens=2000)
        data.update(model=self.model, is_mock=0)
        return data

    def draft(self, conversation, messages, customer, orders, order, fulfillment, analysis) -> dict:
        ctx = build_context_text(conversation, messages, customer, orders, order, fulfillment)
        ctx += "\n\nANALYSE: " + json.dumps({k: analysis.get(k) for k in ("intent", "missing_info", "next_action", "summary", "language")}, ensure_ascii=False)
        data = self._call(prompts.CONCEPT_INSTRUCTIE, ctx, prompts.CONCEPT_SCHEMA, effort="medium", max_tokens=3000)
        data.update(model=self.model, is_mock=0)
        return data

    def verify(self, conversation, messages, customer, order, draft_body: str, analysis) -> dict:
        ctx = build_context_text(conversation, messages, customer, [], order, None)
        ctx += "\n\nCONCEPTANTWOORD:\n" + draft_body
        data = self._call(prompts.CONTROLE_INSTRUCTIE, ctx, prompts.CONTROLE_SCHEMA, effort="low", max_tokens=2000)
        data.update(model=self.model, is_mock=0)
        return data

    def learn(self, records: list[dict]) -> dict:
        regels = []
        for r in records[:80]:
            regels.append(json.dumps({"intent": r.get("ai_intent"), "kanaal": r.get("channel"),
                                      "vraag": (r.get("customer_question") or "")[:400],
                                      "ai_concept": (r.get("ai_draft") or "")[:500],
                                      "verstuurd": (r.get("final_answer") or "")[:500],
                                      "aangepast": bool(r.get("edited")), "escalatie": bool(r.get("escalated")),
                                      "feedback": r.get("feedback")}, ensure_ascii=False))
        data = self._call(prompts.LEREN_INSTRUCTIE, "\n".join(regels), prompts.LEREN_SCHEMA, effort="medium", max_tokens=6000)
        data.update(model=self.model, is_mock=0)
        return data


# ----------------------------------------------------------------------------------
# Mock
# ----------------------------------------------------------------------------------

_KW = [
    # (intent, [trefwoorden])  — volgorde = voorrang bij gelijke score
    ("spam", ["unsubscribe", "seo services", "crypto", "bitcoin", "guaranteed traffic", "backlinks", "loan offer", "winnaar", "you have won", "lottery"]),
    ("partnership", ["samenwerking", "collab", "influencer", "pr package", "groothandel", "wholesale", "pers ", "interview", "sponsor", "ambassadeur", "affiliate"]),
    ("shipping.policy", ["verzendkosten", "verzenden jullie", "levertijd naar", "naar belgië", "naar duitsland", "shipping cost", "ship to", "verzending naar", "gratis verzending", "afhalen", "ophalen", "verzenden naar"]),
    ("shipping.address_change", ["adres wijzigen", "verkeerd adres", "ander adres", "adres aanpassen", "change address", "wrong address", "verhuisd", "huisnummer"]),
    ("order.cancel", ["annuleren", "annuleer", "cancel", "afzeggen", "bestelling terugtrekken"]),
    ("order.change", ["maat wijzigen", "andere maat bestellen", "wijzigen naar", "change my order", "aanpassen naar maat", "kleur wijzigen"]),
    ("shipping.delivery_issue", ["niet ontvangen", "nooit aangekomen", "staat op bezorgd", "kwijt", "verdwenen", "not received", "never arrived", "marked as delivered", "buren", "pakket weg", "verloren"]),
    ("shipping.delay", ["vertraging", "te laat", "duurt lang", "al twee weken", "al drie weken", "wacht al", "delayed", "taking so long", "nog steeds niets", "staat stil", "geen update"]),
    ("shipping.status", ["waar blijft", "waar is mijn", "status van mijn bestelling", "wanneer komt", "track", "verzonden", "where is my order", "shipped yet", "levertijd van mijn", "bezorgd worden", "onderweg", "bestelnummer", "verzendbevestiging"]),
    ("order.damaged", ["beschadigd", "kapot", "gat in", "scheur", "vlek", "damaged", "broken", "defect", "naad los", "los gelaten"]),
    ("order.wrong_item", ["verkeerd artikel", "verkeerde kleur", "ander product", "wrong item", "niet wat ik besteld", "verkeerd product", "verkeerde trui", "verkeerd shirt", "klopt niet"]),
    ("order.missing_item", ["ontbreekt", "mist", "missing", "niet in het pakket", "maar één", "incompleet", "ontbrak"]),
    ("return.status", ["retour aangekomen", "retour ontvangen", "mijn retour", "return arrived", "retour verstuurd", "retourpakket", "status retour"]),
    ("refund.status", ["nog geen geld", "geld terug ontvangen", "refund nog niet", "terugbetaling", "waar blijft mijn geld", "refund not received", "wanneer krijg ik mijn geld", "teruggestort"]),
    ("refund.request", ["geld terug", "refund", "terugbetalen", "money back", "chargeback", "schadevergoeding", "compensatie"]),
    ("exchange.request", ["omruilen", "ruilen", "andere maat", "te klein", "te groot", "exchange", "size up", "size down", "verkeerde maat besteld", "past niet"]),
    ("return.policy", ["retourbeleid", "mag ik retourneren", "hoe lang retour", "retourtermijn", "return policy", "kan ik terugsturen", "retourkosten", "gratis retour"]),
    ("return.request", ["retour", "terugsturen", "return", "retourneren", "retourlabel", "wil ik terug"]),
    ("payment.issue", ["betaling mislukt", "dubbel afgeschreven", "twee keer betaald", "ideal", "klarna", "payment failed", "charged twice", "betaald maar", "betaling niet"]),
    ("discount.question", ["kortingscode", "korting", "discount", "code werkt niet", "actie", "sale", "promo", "coupon", "studentenkorting"]),
    ("product.size_advice", ["welke maat", "maatadvies", "valt groot", "valt klein", "which size", "lengte", "1.80", "1,80", "borstomvang", "maat m of l", "maat s of m", "twijfel tussen"]),
    ("product.material", ["materiaal", "katoen", "wol", "stof", "material", "cotton", "gemaakt van", "duurzaam", "waar geproduceerd", "biologisch", "organic"]),
    ("stock.request", ["voorraad", "uitverkocht", "weer beschikbaar", "restock", "back in stock", "komt terug", "wanneer weer", "sold out", "nog leverbaar", "in stock"]),
    ("product.question", ["wassen", "krimpt", "past bij", "hoe zit", "pasvorm", "kleur in het echt", "wash", "shrink", "fit", "oversized", "capuchon", "zakken"]),
    ("order.invoice", ["factuur", "invoice", "bon", "btw", "receipt"]),
    ("feedback.complaint", ["klacht", "slecht", "teleurgesteld", "belachelijk", "waardeloos", "kutbedrijf", "oplichters", "schandalig", "complaint", "terrible", "worst", "nooit meer", "onacceptabel", "boos"]),
    ("feedback.compliment", ["geweldig", "super blij", "prachtig", "love it", "amazing", "top kwaliteit", "heel mooi", "fan van", "compliment", "dankjewel voor", "helemaal blij"]),
    ("other.thanks", ["bedankt", "dank je", "dankjewel", "thanks", "thank you", "top, ", "helemaal goed", "oké dank", "fijn, dank", "super, dank"]),
]
_FLAGS = {
    "legal_threat": ["advocaat", "juridische stappen", "rechtszaak", "consumentenbond", "lawyer", "legal action", "sue", "geschillencommissie", "aangifte"],
    "chargeback": ["chargeback", "terugboeken via de bank", "bank inschakelen", "creditcardmaatschappij", "dispute"],
    "abusive": ["kutbedrijf", "oplichters", "klootzak", "idioten", "scam", "fuck", "tyfus", "kanker"],
    "human_requested": ["echt persoon", "een mens", "medewerker spreken", "geen bot", "iemand bellen", "bel mij", "real person", "speak to someone", "human"],
    "press_or_partner": ["journalist", "pers ", "redactie", "interview"],
}
_NEG = ["niet blij", "teleurgesteld", "slecht", "belachelijk", "boos", "waardeloos", "frustrerend", "onacceptabel", "schandalig", "kwaad", "irritant", "jammer", "helaas", "vervelend", "terrible", "awful", "disappointed", "annoyed", "angry", "unacceptable", "kutbedrijf", "oplichters", "nooit meer"]
_POS = ["blij", "geweldig", "super", "top", "prachtig", "mooi", "dank", "fijn", "love", "amazing", "great", "perfect", "happy"]
_EN = ["the ", " my ", "order", "please", "hello", "hi ", "where", "when", "i ", "can ", "return", "size", "thanks", "you "]


class MockAgent:
    name = "mock"

    @staticmethod
    def _lang(tekst: str) -> str:
        t = " " + tekst.lower() + " "
        nl = sum(t.count(w) for w in [" de ", " het ", " een ", " ik ", " mijn ", " bestelling", " graag ", " nog ", " niet ", " kan ", " hoi", " hallo", " maat "])
        en = sum(t.count(w) for w in _EN)
        return "en" if en > nl + 1 else "nl"

    def analyze(self, conversation, messages, customer, orders, order, fulfillment) -> dict:
        klant_msgs = [m for m in messages if m.get("author_type") == "customer" and m.get("kind") == "public"]
        laatste = klant_msgs[-1] if klant_msgs else (messages[-1] if messages else {})
        tekst = (laatste.get("body_text") or "")
        alles = " ".join(m.get("body_text") or "" for m in klant_msgs) or tekst
        t = alles.lower()
        scores = {}
        for intent, woorden in _KW:
            s = sum(1 for w in woorden if w in t)
            if s:
                scores[intent] = s
        # Ordernummer in de tekst ondersteunt WISMO/retour-achtige intents
        from app.integrations.shopify import find_order_refs
        refs = find_order_refs(alles)
        intent = max(scores, key=lambda k: (scores[k], -[i for i, _ in _KW].index(k))) if scores else \
            ("social.comment" if conversation.get("via") == "comment" and len(t) < 60 else "other.question")
        if intent == "social.comment" and "?" in t:
            intent = "product.question"
        flags = [f for f, woorden in _FLAGS.items() if any(w in t for w in woorden)]
        if "abusive" in flags and intent not in ("order.damaged", "order.wrong_item", "order.missing_item", "shipping.delivery_issue"):
            intent = "feedback.complaint"  # scheldende klant: de klacht is het onderwerp, niet de vraag erachter
        conf = min(0.95, 0.55 + 0.15 * scores.get(intent, 0)) if scores else 0.4
        secundair = [k for k in sorted(scores, key=scores.get, reverse=True) if k != intent][:2]
        neg = sum(1 for w in _NEG if w in t)
        pos = sum(1 for w in _POS if w in t)
        sentiment = "negative" if neg > pos else ("positive" if pos > neg else "neutral")
        if intent == "feedback.complaint":
            sentiment = "negative"
        meta = INTENTS.get(intent, INTENTS["other"])
        prio = meta["default_priority"]
        if flags and any(f in flags for f in ("legal_threat", "chargeback", "abusive")):
            prio = "critical"
        elif sentiment == "negative" and prio == "normal":
            prio = "high"
        # Ontbrekende info
        missing = []
        for code in meta["required_info"]:
            if code == "order_number" and (refs or order):
                continue
            if code == "photo" and any(db.loads(m.get("attachments"), []) for m in klant_msgs):
                continue
            if code in ("items", "reason", "product", "size", "wanted_variant", "new_variant", "new_address", "measurements_or_reference"):
                # in mock: aannemen dat het ontbreekt als het bericht kort is
                if len(t) > 140:
                    continue
            missing.append(code)
        if order is None and refs:
            missing = [m for m in missing if m != "order_number"]
            if "email" not in missing and customer is None:
                missing.append("email")
        needs_human = bool(flags) or intent in ("refund.request", "payment.issue", "feedback.complaint", "partnership", "other")
        reden = ""
        if flags:
            reden = "Escalatievlag: " + ", ".join(flags)
        elif intent in ("refund.request", "payment.issue"):
            reden = "Geldzaken beslist een mens"
        elif intent == "feedback.complaint":
            reden = "Klacht — persoonlijke reactie gewenst"
        elif intent == "partnership":
            reden = "Zakelijk verzoek"
        elif intent == "other":
            reden = "Onduidelijke vraag"
        if intent in ("spam", "other.thanks", "social.comment"):
            next_action = "close"
        elif needs_human and flags:
            next_action = "handover"
        elif missing:
            next_action = "ask_info"
        elif needs_human:
            next_action = "handover"
        else:
            next_action = "answer"
        samenvatting = tekst.strip().replace("\n", " ")[:110]
        return {
            "intent": intent, "intent_confidence": round(conf, 2), "secondary_intents": secundair,
            "priority": prio, "sentiment": sentiment, "language": self._lang(alles),
            "needs_human": needs_human, "needs_human_reason": reden, "escalation_flags": flags,
            "missing_info": missing, "order_ref": (order or {}).get("name") or (refs[0] if refs else None),
            "next_action": next_action, "summary": samenvatting or meta["label"],
            "reasoning": f"Mock-classificatie op trefwoorden (score {scores.get(intent, 0)}); geen echte AI.",
            "model": "mock", "is_mock": 1,
        }

    def draft(self, conversation, messages, customer, orders, order, fulfillment, analysis) -> dict:
        naam = (customer or {}).get("name") or ""
        voornaam = naam.split(" ")[0] if naam else ""
        aanhef = f"Hoi {voornaam}," if voornaam else "Hoi,"
        en = analysis.get("language") == "en"
        if en:
            aanhef = f"Hi {voornaam}," if voornaam else "Hi,"
        intent = analysis.get("intent")
        missing = analysis.get("missing_info") or []
        publiek = conversation.get("via") == "comment"
        kb_slugs = []
        tr = (order or {}).get("tracking") or {}
        stage = (fulfillment or {}).get("label")

        if publiek and intent in ("shipping.status", "shipping.delay", "shipping.delivery_issue", "order.cancel", "return.request", "exchange.request", "refund.status", "refund.request", "order.damaged", "order.wrong_item", "order.missing_item"):
            body = ("Thanks for reaching out! Please send us a DM or email support@farmersatelier.nl with your order number, then we'll sort it out right away. 🙌"
                    if en else "Vervelend dat dit zo loopt! Stuur ons even een DM of een mail naar support@farmersatelier.nl met je ordernummer, dan pakken we het meteen voor je op. 🙌")
            return dict(body=body, kind="ask_info", used_knowledge=["bedrijfsinfo"], confidence=0.7,
                        notes_for_agent="Publieke comment: geen orderdetails delen.", model="mock", is_mock=1)

        if missing:
            vraag = ", ".join(MISSING_INFO_LABELS.get(m, m) for m in missing)
            if intent in ("order.damaged", "order.wrong_item", "order.missing_item"):
                body = f"{aanhef}\n\nWat vervelend, dat lossen we natuurlijk op. Kun je je {vraag} sturen? Dan regelen we direct een oplossing.\n\nGroet,\nFarmers Atelier"
            elif intent in ("shipping.status", "shipping.delay", "shipping.delivery_issue", "return.status", "refund.status", "order.cancel", "shipping.address_change"):
                body = f"{aanhef}\n\nDat zoek ik direct voor je uit. Kun je je {vraag} even doorsturen? Dan kijk ik het meteen na.\n\nGroet,\nFarmers Atelier"
            else:
                body = f"{aanhef}\n\nGoede vraag! Om je goed te helpen heb ik nog je {vraag} nodig. Kun je dat even sturen?\n\nGroet,\nFarmers Atelier"
            if en:
                body = f"{aanhef}\n\nHappy to help! Could you send us your {vraag}? Then we'll look into it straight away.\n\nBest,\nFarmers Atelier"
            return dict(body=body, kind="ask_info", used_knowledge=[], confidence=0.75,
                        notes_for_agent="", model="mock", is_mock=1)

        if intent in ("shipping.status", "shipping.delay") and order:
            kb_slugs = ["verzendbeleid"]
            if tr.get("status") == "DELIVERED" or (fulfillment or {}).get("stage") == "delivered":
                body = f"{aanhef}\n\nVolgens de vervoerder is je bestelling {order['name']} bezorgd" + (f" ({tr.get('company')})" if tr.get("company") else "") + ". Heb je hem niet ontvangen? Check even bij de buren of het afhaalpunt; anders horen we het graag, dan starten we een onderzoek bij de vervoerder.\n\nGroet,\nFarmers Atelier"
            elif tr.get("number"):
                body = f"{aanhef}\n\nJe bestelling {order['name']} is onderweg" + (f" met {tr.get('company')}" if tr.get("company") else "") + f". Status: {stage or 'onderweg'}. Je volgt hem hier: {tr.get('url') or tr.get('number')}" + (f"\nVerwachte levering: {tr.get('estimated_delivery')[:10]}." if tr.get("estimated_delivery") else "") + "\n\nGroet,\nFarmers Atelier"
            elif order.get("cancelled_at"):
                body = f"{aanhef}\n\nBestelling {order['name']} is geannuleerd. Is dat niet de bedoeling? Laat het even weten.\n\nGroet,\nFarmers Atelier"
            else:
                body = f"{aanhef}\n\nJe bestelling {order['name']} is bij ons binnen en wordt klaargemaakt voor verzending ({stage or 'in behandeling'}). Zodra hij de deur uit is, krijg je automatisch een mail met track & trace.\n\nGroet,\nFarmers Atelier"
            if en:
                body = f"{aanhef}\n\nYour order {order['name']} status: {stage or order.get('fulfillment_status')}." + (f" Track it here: {tr.get('url') or tr.get('number')}" if tr.get("number") else " You'll get a tracking email as soon as it ships.") + "\n\nBest,\nFarmers Atelier"
        elif intent == "shipping.delivery_issue" and order:
            kb_slugs = ["verzendbeleid"]
            body = f"{aanhef}\n\nWat vervelend dat je pakket ({order['name']}) niet is aangekomen terwijl het op bezorgd staat. Wil je even checken bij de buren en het afhaalpunt? Als het er morgen nog niet is, starten wij een onderzoek bij {tr.get('company') or 'de vervoerder'} en zorgen we dat je niet met lege handen staat.\n\nGroet,\nFarmers Atelier"
        elif intent in ("return.request", "return.policy"):
            kb_slugs = ["retourbeleid", "retourinstructies"]
            body = f"{aanhef}\n\nRetourneren kan zeker. [Retourtermijn en stappen uit de kennisbank — nog in te vullen door Wieger.] Stuur je pakket goed verpakt terug; zodra we het ontvangen hebben, verwerken we de terugbetaling.\n\nGroet,\nFarmers Atelier"
        elif intent == "return.status" and order:
            kb_slugs = ["retourbeleid"]
            rs = order.get("return_status") or "NO_RETURN"
            body = f"{aanhef}\n\nIk heb je retour van {order['name']} erbij gepakt: status {rs.replace('_', ' ').lower()}. " + ("Zodra het pakket bij ons binnen is, verwerken we de terugbetaling en krijg je daar een mail van." if rs != "RETURNED" else "Het pakket is ontvangen; de terugbetaling is in gang gezet.") + "\n\nGroet,\nFarmers Atelier"
        elif intent == "exchange.request":
            kb_slugs = ["retourbeleid", "maten"]
            body = f"{aanhef}\n\nGeen probleem, een andere maat regelen we. Laat even weten welke maat je wilt; dan checken we de voorraad en sturen we je de stappen om te ruilen.\n\nGroet,\nFarmers Atelier"
        elif intent == "refund.status" and order:
            kb_slugs = ["betaalmethoden"]
            refunds = order.get("refunds") or []
            body = f"{aanhef}\n\n" + (f"De terugbetaling van €{refunds[-1].get('amount', 0):.2f} voor {order['name']} is op {str(refunds[-1].get('at'))[:10]} verwerkt. Afhankelijk van je bank duurt het 2-5 werkdagen voordat je het ziet." if refunds else f"Ik zie nog geen verwerkte terugbetaling voor {order['name']}; ik laat een collega dit direct nakijken en je hoort snel van ons.") + "\n\nGroet,\nFarmers Atelier"
        elif intent == "order.cancel" and order:
            body = f"{aanhef}\n\nIk heb je verzoek om {order['name']} te annuleren ontvangen. " + ("De bestelling is nog niet verzonden, dus we pakken dit direct op en bevestigen je de annulering zo snel mogelijk." if (order.get("fulfillment_status") or "").upper() != "FULFILLED" else "De bestelling is helaas al verzonden; je kunt hem na ontvangst gewoon retourneren, dan krijg je het bedrag terug.") + "\n\nGroet,\nFarmers Atelier"
        elif intent == "shipping.address_change" and order:
            body = f"{aanhef}\n\nDank voor je bericht. " + ("We passen het adres van {o} aan voordat hij de deur uit gaat en bevestigen dat zo.".format(o=order['name']) if (order.get("fulfillment_status") or "").upper() != "FULFILLED" else f"Bestelling {order['name']} is helaas al onderweg naar het oude adres; via de trackinglink kun je vaak nog een ander bezorgmoment of afhaalpunt kiezen.") + "\n\nGroet,\nFarmers Atelier"
        elif intent in ("order.damaged", "order.wrong_item", "order.missing_item"):
            body = f"{aanhef}\n\nWat vervelend, sorry daarvoor! Dank voor de foto en je ordernummer. We pakken dit direct op en komen zo snel mogelijk met een oplossing bij je terug.\n\nGroet,\nFarmers Atelier"
        elif intent == "product.size_advice":
            kb_slugs = ["maten"]
            body = f"{aanhef}\n\nGoede vraag! [Maatadvies op basis van de maattabel — nog in te vullen door Wieger.] Twijfel je tussen twee maten? Dan raden we meestal de grootste aan; ruilen kan altijd.\n\nGroet,\nFarmers Atelier"
        elif intent == "stock.request":
            kb_slugs = ["producten"]
            body = f"{aanhef}\n\nLeuk dat je 'm wilt! Ik check de voorraad en laat je zo snel mogelijk weten of en wanneer die maat weer beschikbaar is.\n\nGroet,\nFarmers Atelier"
        elif intent in ("product.question", "product.material"):
            kb_slugs = ["producten"]
            body = f"{aanhef}\n\nGoede vraag! [Antwoord uit de productinformatie — nog in te vullen door Wieger.]\n\nGroet,\nFarmers Atelier"
        elif intent == "shipping.policy":
            kb_slugs = ["verzendbeleid"]
            body = f"{aanhef}\n\n[Verzendkosten en levertijd uit het verzendbeleid — nog in te vullen door Wieger.]\n\nGroet,\nFarmers Atelier"
        elif intent == "discount.question":
            kb_slugs = ["kortingen"]
            body = f"{aanhef}\n\nDank voor je bericht! [Kortingsregels uit de kennisbank — nog in te vullen door Wieger.] Werkt een code niet? Stuur hem even door, dan kijk ik wat er misgaat.\n\nGroet,\nFarmers Atelier"
        elif intent == "order.invoice" and order:
            body = f"{aanhef}\n\nDe factuur van {order['name']} sturen we je zo toe per mail.\n\nGroet,\nFarmers Atelier"
        elif intent == "feedback.complaint":
            body = f"{aanhef}\n\nWat vervelend dat het zo is gelopen, en sorry daarvoor. Dit is niet hoe we het willen. Ik pak het persoonlijk op en kom vandaag nog bij je terug met een oplossing.\n\nGroet,\nFarmers Atelier"
        elif intent == "feedback.compliment":
            body = "Wat leuk om te horen, dankjewel! 🙌" if publiek else f"{aanhef}\n\nWat leuk om te horen, dankjewel! Daar doen we het voor.\n\nGroet,\nFarmers Atelier"
        elif intent == "partnership":
            body = f"{aanhef}\n\nDank voor je bericht en je interesse in Farmers Atelier. Ik geef het door aan de juiste persoon; die neemt contact met je op.\n\nGroet,\nFarmers Atelier"
        else:
            body = f"{aanhef}\n\nDank voor je bericht! Ik pak het op en kom zo snel mogelijk bij je terug.\n\nGroet,\nFarmers Atelier"
        if en and "Best,\nFarmers Atelier" not in body:
            body = body.replace("Groet,\nFarmers Atelier", "Best,\nFarmers Atelier")
        return dict(body=body, kind="answer", used_knowledge=kb_slugs, confidence=0.6,
                    notes_for_agent=("Kennisbank nog onvolledig voor dit onderwerp." if any("[" in body for _ in [0]) else ""),
                    model="mock", is_mock=1)

    def verify(self, conversation, messages, customer, order, draft_body: str, analysis) -> dict:
        t = draft_body.lower()
        promise = any(w in t for w in ["garandeer", "gegarandeerd", "krijg je je geld terug", "storten we terug", "korting van", "% korting", "gratis", "morgen in huis", "vandaag nog bezorgd", "we refund", "guaranteed"])
        placeholder = "[" in draft_body and "]" in draft_body
        publiek = conversation.get("via") == "comment"
        privacy_ok = not (publiek and any(w in t for w in ["#", "adres", "€", "tracking"]))
        issues = []
        if promise:
            issues.append("Bevat mogelijk een belofte (refund/korting/datum).")
        if placeholder:
            issues.append("Bevat een placeholder tussen haken: kennisbank nog onvolledig.")
        if not privacy_ok:
            issues.append("Orderdetails in een publieke comment.")
        return dict(ok=not issues, contains_promise=promise, grounded=not placeholder, policy_ok=True,
                    privacy_ok=privacy_ok, tone_ok=True, issues=issues, suggested_fix="", model="mock", is_mock=1)

    def learn(self, records: list[dict]) -> dict:
        from collections import Counter
        per_intent = Counter(r.get("ai_intent") for r in records)
        edited = Counter(r.get("ai_intent") for r in records if r.get("edited"))
        esc = Counter(r.get("ai_intent") for r in records if r.get("escalated"))
        vaak = [f"{k}: {v}x" for k, v in per_intent.most_common(6)]
        aangepast = [{"intent": k, "what_changes": f"{v} van {per_intent[k]} concepten aangepast (mock: inhoud niet geanalyseerd)"} for k, v in edited.most_common(5)]
        klaar = [k for k, v in per_intent.items() if v >= 5 and edited[k] / v < 0.2 and esc[k] == 0]
        return dict(recurring_questions=vaak, frequently_edited=aangepast, ready_for_more_automation=klaar,
                    ai_mistakes=["Mock-modus: zet een Anthropic API-sleutel om echte analyse te krijgen."],
                    missing_knowledge=[{"title": s["title"], "proposed_text": "Nog in te vullen in kb/" + s["slug"] + ".md"}
                                       for s in knowledge.article_status() if not s["complete"]][:5],
                    automation_ideas=["Orderstatus-vragen met tracking automatisch beantwoorden zodra de acceptatie > 90 % is."],
                    model="mock", is_mock=1)


# ----------------------------------------------------------------------------------

_AGENT = None
_AGENT_MODE = None


def get_agent():
    """Kiest Claude als er een sleutel is (en ai_mode niet 'mock'), anders de mock."""
    global _AGENT, _AGENT_MODE
    mode = db.setting("ai_mode", "auto")
    wil_claude = mode == "claude" or (mode == "auto" and config.anthropic_key())
    if wil_claude and _AGENT_MODE != "claude":
        try:
            _AGENT, _AGENT_MODE = ClaudeAgent(), "claude"
        except Exception as fout:  # noqa: BLE001
            print(f"   ! Claude niet beschikbaar ({fout}); mock-modus", flush=True)
            _AGENT, _AGENT_MODE = MockAgent(), "mock"
    elif not wil_claude and _AGENT_MODE != "mock":
        _AGENT, _AGENT_MODE = MockAgent(), "mock"
    return _AGENT


def agent_mode() -> str:
    return get_agent().name


def similarity(a: str, b: str) -> float:
    """Overeenkomst 0..1 tussen concept en verstuurde tekst (voor de leerdata)."""
    import difflib
    return round(difflib.SequenceMatcher(None, (a or "").strip(), (b or "").strip()).ratio(), 3)


def diff_summary(a: str, b: str) -> str:
    import difflib
    sm = difflib.SequenceMatcher(None, (a or "").split(), (b or "").split())
    toegevoegd = verwijderd = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            verwijderd += i2 - i1
        if tag in ("replace", "insert"):
            toegevoegd += j2 - j1
    if not toegevoegd and not verwijderd:
        return "ongewijzigd"
    return f"{verwijderd} woorden weg, {toegevoegd} woorden erbij"
