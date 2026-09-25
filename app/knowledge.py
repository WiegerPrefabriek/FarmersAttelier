"""Kennisbank: Markdown-bestanden in kb/ → tabel knowledge_articles (+ FTS5-zoeken).

Elk bestand: optionele eerste regel `# Titel`, verder vrije tekst. Bevat een bestand nog
`TODO`, dan geldt het als onvolledig: de AI ziet dat en mag er niet op bouwen — ze stelt
dan een vraag of zet het ticket door, in plaats van iets te verzinnen.
"""

from __future__ import annotations

import os
import re

import config
from app import db

CATEGORIE_UIT_SLUG = {
    "retourbeleid": "retouren", "verzendbeleid": "verzending", "maten": "producten",
    "producten": "producten", "betaalmethoden": "betaling", "kortingen": "betaling",
    "faq": "faq", "tone-of-voice": "toon", "bedrijfsinfo": "algemeen",
    "retourinstructies": "retouren",
}


def sync_from_disk() -> dict:
    """Leest kb/*.md en werkt de tabel bij. Geeft {slug: is_complete} terug."""
    resultaat = {}
    if not os.path.isdir(config.KB_DIR):
        return resultaat
    gezien = set()
    for naam in sorted(os.listdir(config.KB_DIR)):
        if not naam.endswith(".md"):
            continue
        slug = naam[:-3]
        pad = os.path.join(config.KB_DIR, naam)
        with open(pad, encoding="utf-8") as f:
            tekst = f.read()
        titel = slug.replace("-", " ").capitalize()
        m = re.match(r"^#\s+(.+)$", tekst.strip().split("\n", 1)[0])
        if m:
            titel = m.group(1).strip()
        compleet = 0 if re.search(r"\bTODO\b", tekst) else 1
        bestaand = db.one("SELECT id FROM knowledge_articles WHERE slug = ?", (slug,))
        waarden = dict(slug=slug, title=titel, category=CATEGORIE_UIT_SLUG.get(slug, "algemeen"),
                       body=tekst, is_complete=compleet, source_file=naam, updated_at=db.now())
        if bestaand:
            db.update("knowledge_articles", bestaand["id"], waarden)
        else:
            db.insert("knowledge_articles", waarden)
        gezien.add(slug)
        resultaat[slug] = bool(compleet)
    return resultaat


def all_articles() -> list[dict]:
    return db.rows("SELECT id, slug, title, category, body, is_complete, updated_at FROM knowledge_articles ORDER BY slug")


def search(vraag: str, limit: int = 4) -> list[dict]:
    """FTS5-zoekopdracht; valt terug op alles als de query niets oplevert."""
    woorden = [w for w in re.findall(r"[a-zA-Z0-9À-ÿ]{3,}", vraag.lower())]
    if not woorden:
        return []
    query = " OR ".join(f'"{w}"' for w in woorden[:12])
    try:
        return db.rows(
            "SELECT a.id, a.slug, a.title, a.category, a.body, a.is_complete "
            "FROM knowledge_fts f JOIN knowledge_articles a ON a.id = f.rowid "
            "WHERE knowledge_fts MATCH ? ORDER BY bm25(knowledge_fts) LIMIT ?", (query, limit))
    except Exception:  # noqa: BLE001 — een rare query mag de pipeline niet stoppen
        return []


def as_prompt_block(max_chars: int = 40_000) -> str:
    """Hele kennisbank als één tekstblok voor de systemprompt (klein genoeg om te cachen)."""
    delen = []
    for a in all_articles():
        kop = f"### {a['title']} ({a['slug']})"
        if not a["is_complete"]:
            kop += " — LET OP: onvolledig, bevat TODO's; gebruik alleen wat concreet is ingevuld"
        delen.append(kop + "\n" + a["body"].strip())
    tekst = "\n\n".join(delen)
    return tekst[:max_chars]


def article_status() -> list[dict]:
    """Voor het dashboard: welke artikelen zijn nog onvolledig."""
    return [dict(slug=a["slug"], title=a["title"], complete=bool(a["is_complete"])) for a in all_articles()]
