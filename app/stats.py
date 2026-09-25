"""Dashboardcijfers. Elk cijfer heeft een ⓘ-uitleg in INFO (titel, formule, uitleg),
zodat je elk getal kunt narekenen — vaste eis voor alle dashboards.
"""

from __future__ import annotations

import datetime as dt
import statistics

from app import db
from app.taxonomy import CHANNELS, GROUPS, intent_group, intent_label

INFO = {
    "nieuw_vandaag": dict(titel="Nieuwe vragen vandaag", formule="COUNT(conversations WHERE created_at >= vandaag 00:00)",
                          uitleg="Aantal gesprekken (tickets) dat vandaag is aangemaakt, alle kanalen samen."),
    "open": dict(titel="Open", formule="COUNT(conversations WHERE status = 'open')",
                 uitleg="Gesprekken die nog niet gesloten, gesnoozed of spam zijn."),
    "ai_afgehandeld_vandaag": dict(titel="Door AI afgehandeld vandaag",
                                   formule="COUNT(vandaag gesloten door AI) + COUNT(vandaag automatisch beantwoord) + COUNT(AI-concepten vandaag ongewijzigd verstuurd)",
                                   uitleg="Tickets waar geen mens iets aan hoefde te veranderen: automatisch gesloten (bedankje/spam), automatisch beantwoord, of concept 1-op-1 verstuurd."),
    "mens_nodig": dict(titel="Mens nodig", formule="COUNT(conversations WHERE status='open' AND needs_human=1)",
                       uitleg="Open gesprekken die de AI of een regel expliciet aan een mens heeft overgedragen."),
    "high_priority": dict(titel="High priority", formule="COUNT(open WHERE priority IN ('high','critical'))",
                          uitleg="Open gesprekken met prioriteit high of critical."),
    "responstijd": dict(titel="Gemiddelde eerste responstijd (7 dagen)", formule="MEDIAAN(first_response_at − created_at) over gesprekken van de laatste 7 dagen met een antwoord",
                        uitleg="Mediaan in minuten, klokuren (niet alleen werkuren). Automatische antwoorden tellen mee, interne notities niet."),
    "per_kanaal": dict(titel="Vragen per kanaal (7 dagen)", formule="COUNT(conversations GROUP BY channel) laatste 7 dagen", uitleg="Waar komen de vragen vandaan."),
    "per_categorie": dict(titel="Vragen per categorie (7 dagen)", formule="COUNT(conversations GROUP BY intent) laatste 7 dagen",
                          uitleg="De categorie is die van de laatste AI-analyse, eventueel gecorrigeerd door een medewerker."),
    "ai_acceptatie": dict(titel="AI-concepten direct goedgekeurd", formule="COUNT(drafts status='sent') / COUNT(drafts status IN ('sent','edited_sent','rejected'))",
                          uitleg="Aandeel conceptantwoorden dat zonder wijziging is verstuurd. Hoe hoger, hoe eerder een categorie naar automatisch antwoorden kan."),
    "ai_aangepast": dict(titel="AI-concepten aangepast", formule="COUNT(drafts status='edited_sent')",
                         uitleg="Concepten die een medewerker heeft bewerkt vóór versturen. Deze worden gebruikt om de AI te verbeteren (tab Leren)."),
    "backlog": dict(titel="Backlog per leeftijd", formule="Open gesprekken gegroepeerd op (nu − last_customer_message_at)",
                    uitleg="Hoe lang wacht de klant al op ons laatste antwoord."),
}


def _vandaag() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT00:00:00")


def _dagen_terug(n: int) -> str:
    return (dt.datetime.utcnow() - dt.timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%S")


def dashboard() -> dict:
    vandaag, week = _vandaag(), _dagen_terug(7)
    nieuw = db.scalar("SELECT COUNT(*) FROM conversations WHERE created_at >= ?", (vandaag,))
    open_ = db.scalar("SELECT COUNT(*) FROM conversations WHERE status = 'open'")
    ai_closed = db.scalar("SELECT COUNT(*) FROM events WHERE type IN ('ticket-closed','ticket-marked-spam') AND actor_type = 'ai' AND created_at >= ?", (vandaag,))
    ai_auto = db.scalar("SELECT COUNT(*) FROM ai_drafts WHERE status = 'auto_sent' AND decided_at >= ?", (vandaag,))
    ai_sent = db.scalar("SELECT COUNT(*) FROM ai_drafts WHERE status = 'sent' AND decided_at >= ?", (vandaag,))
    mens = db.scalar("SELECT COUNT(*) FROM conversations WHERE status = 'open' AND needs_human = 1")
    high = db.scalar("SELECT COUNT(*) FROM conversations WHERE status = 'open' AND priority IN ('high','critical')")
    # responstijd
    rijen = db.rows("SELECT created_at, first_response_at FROM conversations WHERE created_at >= ? AND first_response_at IS NOT NULL", (week,))
    minuten = []
    for r in rijen:
        a, b = db.parse_ts(r["created_at"]), db.parse_ts(r["first_response_at"])
        if a and b and b >= a:
            minuten.append((b - a).total_seconds() / 60)
    responstijd = round(statistics.median(minuten)) if minuten else None
    per_kanaal = {CHANNELS.get(r["channel"], r["channel"]): r["n"] for r in
                  db.rows("SELECT channel, COUNT(*) n FROM conversations WHERE created_at >= ? GROUP BY channel ORDER BY n DESC", (week,))}
    per_categorie = [{"intent": r["intent"], "label": intent_label(r["intent"]), "group": GROUPS.get(intent_group(r["intent"]), "Algemeen"), "n": r["n"]} for r in
                     db.rows("SELECT intent, COUNT(*) n FROM conversations WHERE created_at >= ? AND intent IS NOT NULL GROUP BY intent ORDER BY n DESC", (week,))]
    d_sent = db.scalar("SELECT COUNT(*) FROM ai_drafts WHERE status = 'sent'")
    d_edit = db.scalar("SELECT COUNT(*) FROM ai_drafts WHERE status = 'edited_sent'")
    d_rej = db.scalar("SELECT COUNT(*) FROM ai_drafts WHERE status = 'rejected'")
    d_tot = d_sent + d_edit + d_rej
    # backlog
    nu = dt.datetime.utcnow()
    backlog = {"< 1 uur": 0, "1-4 uur": 0, "4-24 uur": 0, "1-3 dagen": 0, "> 3 dagen": 0}
    for r in db.rows("SELECT last_customer_message_at, last_message_at FROM conversations WHERE status = 'open'"):
        t = db.parse_ts(r["last_customer_message_at"] or r["last_message_at"])
        if not t:
            continue
        uren = (nu - t).total_seconds() / 3600
        sleutel = "< 1 uur" if uren < 1 else "1-4 uur" if uren < 4 else "4-24 uur" if uren < 24 else "1-3 dagen" if uren < 72 else "> 3 dagen"
        backlog[sleutel] += 1
    return {
        "kpis": {
            "nieuw_vandaag": nieuw, "open": open_, "ai_afgehandeld_vandaag": ai_closed + ai_auto + ai_sent,
            "mens_nodig": mens, "high_priority": high, "responstijd_min": responstijd,
            "ai_acceptatie_pct": round(100 * d_sent / d_tot) if d_tot else None, "ai_aangepast": d_edit,
            "ai_concepten_totaal": d_tot,
        },
        "per_kanaal": per_kanaal, "per_categorie": per_categorie, "backlog": backlog,
        "actie_nodig": actie_nodig(), "info": INFO,
        "per_dag": per_dag(14),
    }


def per_dag(n: int) -> list[dict]:
    start = (dt.datetime.utcnow() - dt.timedelta(days=n - 1)).strftime("%Y-%m-%d")
    nieuw = {r["d"]: r["n"] for r in db.rows("SELECT substr(created_at,1,10) d, COUNT(*) n FROM conversations WHERE created_at >= ? GROUP BY d", (start,))}
    gesloten = {r["d"]: r["n"] for r in db.rows("SELECT substr(closed_at,1,10) d, COUNT(*) n FROM conversations WHERE closed_at >= ? GROUP BY d", (start,))}
    uit = []
    for i in range(n):
        d = (dt.datetime.utcnow() - dt.timedelta(days=n - 1 - i)).strftime("%Y-%m-%d")
        uit.append({"dag": d, "nieuw": nieuw.get(d, 0), "gesloten": gesloten.get(d, 0)})
    return uit


def actie_nodig() -> list[dict]:
    """De lijst 'ACTIE NODIG': alles waar wij zelf iets moeten doen, op volgorde van urgentie."""
    uit = []
    prio_rang = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    for r in db.rows("SELECT c.id, c.subject, c.priority, c.needs_human_reason, c.channel, c.intent, c.last_customer_message_at, k.name "
                     "FROM conversations c LEFT JOIN customers k ON k.id = c.customer_id "
                     "WHERE c.status = 'open' AND (c.needs_human = 1 OR c.priority IN ('high','critical')) ORDER BY c.last_customer_message_at"):
        uit.append({"type": "mens_nodig" if r["needs_human_reason"] else "prioriteit", "conversation_id": r["id"],
                    "titel": r["subject"] or "(geen onderwerp)", "klant": r["name"], "kanaal": r["channel"],
                    "reden": r["needs_human_reason"] or f"Prioriteit {r['priority']}", "prioriteit": r["priority"],
                    "sinds": r["last_customer_message_at"], "rang": prio_rang.get(r["priority"], 2)})
    for a in db.rows("SELECT a.id, a.conversation_id, a.description, a.type, a.created_at, c.priority FROM pending_actions a "
                     "JOIN conversations c ON c.id = a.conversation_id WHERE a.status = 'pending' ORDER BY a.created_at"):
        uit.append({"type": "goedkeuring", "conversation_id": a["conversation_id"], "action_id": a["id"],
                    "titel": a["description"], "reden": "Wacht op jouw goedkeuring", "prioriteit": a["priority"],
                    "sinds": a["created_at"], "rang": 0})
    for m in db.rows("SELECT m.id, m.conversation_id, m.error, m.created_at, c.subject FROM messages m JOIN conversations c ON c.id = m.conversation_id "
                     "WHERE m.status = 'failed' AND c.status = 'open' ORDER BY m.created_at DESC LIMIT 20"):
        uit.append({"type": "verzendfout", "conversation_id": m["conversation_id"], "titel": m["subject"],
                    "reden": f"Antwoord niet verzonden: {m['error']}", "prioriteit": "high", "sinds": m["created_at"], "rang": 0})
    uit.sort(key=lambda x: (x["rang"], x["sinds"] or ""))
    return uit


def learning_overview() -> dict:
    rec = db.rows("SELECT * FROM learning_records ORDER BY created_at DESC LIMIT 200")
    per_intent: dict[str, dict] = {}
    for r in rec:
        k = r["ai_intent"] or "?"
        p = per_intent.setdefault(k, {"intent": k, "label": intent_label(k), "n": 0, "edited": 0, "escalated": 0, "sim": []})
        p["n"] += 1
        p["edited"] += 1 if r["edited"] else 0
        p["escalated"] += 1 if r["escalated"] else 0
        if r["similarity"] is not None:
            p["sim"].append(r["similarity"])
    tabel = []
    for p in per_intent.values():
        p["gem_similarity"] = round(sum(p["sim"]) / len(p["sim"]), 2) if p["sim"] else None
        p["edit_pct"] = round(100 * p["edited"] / p["n"]) if p["n"] else 0
        p["klaar_voor_auto"] = p["n"] >= 5 and p["edit_pct"] <= 20 and p["escalated"] == 0
        del p["sim"]
        tabel.append(p)
    tabel.sort(key=lambda x: -x["n"])
    feedback = db.rows("SELECT feedback, COUNT(*) n FROM ai_drafts WHERE feedback IS NOT NULL GROUP BY feedback")
    return {"records": [dict(r, order_info=db.loads(r["order_info"], {}), used_knowledge=db.loads(r["used_knowledge"], [])) for r in rec[:60]],
            "per_intent": tabel, "feedback": {f["feedback"]: f["n"] for f in feedback},
            "laatste_analyse": db.setting("learning_analysis")}


def view_counts(user_id: int | None) -> dict:
    q = lambda sql, p=(): db.scalar(sql, p)  # noqa: E731
    return {
        "alle": q("SELECT COUNT(*) FROM conversations WHERE status IN ('open','snoozed')"),
        "nieuw": q("SELECT COUNT(*) FROM conversations WHERE status = 'open' AND first_response_at IS NULL"),
        "mijn": q("SELECT COUNT(*) FROM conversations WHERE status = 'open' AND assignee_id = ?", (user_id,)),
        "ai_bezig": q("SELECT COUNT(*) FROM conversations WHERE status = 'open' AND ai_status IN ('processing','drafted','asked_info')"),
        "ai_opgelost": q("SELECT COUNT(*) FROM conversations WHERE ai_status IN ('auto_answered','closed') AND status IN ('closed','spam')"),
        "mens_nodig": q("SELECT COUNT(*) FROM conversations WHERE status = 'open' AND needs_human = 1"),
        "high": q("SELECT COUNT(*) FROM conversations WHERE status = 'open' AND priority IN ('high','critical')"),
        "goedkeuring": q("SELECT COUNT(*) FROM pending_actions WHERE status = 'pending'"),
        "snoozed": q("SELECT COUNT(*) FROM conversations WHERE status = 'snoozed'"),
        "afgehandeld": q("SELECT COUNT(*) FROM conversations WHERE status = 'closed'"),
        "spam": q("SELECT COUNT(*) FROM conversations WHERE status = 'spam'"),
        **{f"groep:{g}": q("SELECT COUNT(*) FROM conversations WHERE status = 'open' AND intent IN (%s)" %
                           ",".join("?" * len(ints)), tuple(ints)) if ints else 0
           for g, ints in _intents_per_groep().items()},
        "social": q("SELECT COUNT(*) FROM conversations WHERE status = 'open' AND channel IN ('instagram','facebook','tiktok')"),
    }


def _intents_per_groep() -> dict[str, list[str]]:
    from app.taxonomy import INTENTS
    uit: dict[str, list[str]] = {}
    for k, v in INTENTS.items():
        uit.setdefault(v["group"], []).append(k)
    return uit
