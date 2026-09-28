"""Klaviyo aansturen vanuit dit dashboard.

De werkverdeling: wij schrijven hier de inhoud en bepalen wie hem krijgt, Klaviyo
doet het versturen. Dat is bewust zo. Klaviyo regelt afmeldlinks, bounces,
spamklachten en de registratie van wie zich heeft afgemeld — dat is wettelijk
verplicht (AVG en de Telecommunicatiewet), foutgevoelig, en je wilt het niet zelf
bouwen voor een lijst van 17.000 adressen.

Wat dit bestand doet:

* een sjabloon aanmaken of bijwerken in Klaviyo vanuit de tekst die hier staat;
* een campagne klaarzetten op een lijst of segment;
* de ontvangers tellen voordat er iets verstuurd wordt;
* de campagne naar Klaviyo sturen **als concept**.

Wat dit bestand NIET doet: verzenden. `verstuur()` bestaat niet. Een campagne
naar 17.000 mensen sturen is onomkeerbaar; dat gebeurt met een menselijke klik in
Klaviyo zelf, waar ook de laatste controle op afmeldlinks en weergave zit.

In `.secrets.json` onder `"klaviyo"`:

    {"private_key": "pk_...", "public_key": "", "revisie": "2024-10-15"}

De private key maak je in Klaviyo onder Settings → API keys. Geef hem alleen de
rechten Campaigns, Templates, Lists en Segments — read en write.
"""

from __future__ import annotations

import config

try:
    import requests
except ImportError:
    requests = None

API = "https://a.klaviyo.com/api"
# Klaviyo versioneert zijn API per datum; die moet mee in elke aanroep.
REVISIE = "2024-10-15"


def _conf() -> dict:
    return config.secret("klaviyo") or {}


def configured() -> bool:
    return bool(requests and _conf().get("private_key"))


def _kop() -> dict:
    return {
        "Authorization": f"Klaviyo-API-Key {_conf()['private_key']}",
        "revision": _conf().get("revisie") or REVISIE,
        "accept": "application/vnd.api+json",
        "content-type": "application/vnd.api+json",
    }


def _get(pad: str, **params) -> dict:
    r = requests.get(f"{API}/{pad}", params=params, headers=_kop(), timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Klaviyo GET {pad}: {r.status_code} {r.text[:300]}")
    return r.json()


def _post(pad: str, body: dict) -> dict:
    r = requests.post(f"{API}/{pad}", json=body, headers=_kop(), timeout=30)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"Klaviyo POST {pad}: {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


def test() -> dict:
    """Komen we binnen, en wat staat er klaar?"""
    if not configured():
        return {"ok": False, "reden": "niet ingesteld: vul 'klaviyo' in .secrets.json"}
    try:
        lijsten = _get("lists", **{"page[size]": "50"}).get("data", [])
        return {"ok": True,
                "lijsten": [{"id": l["id"], "naam": l["attributes"].get("name")} for l in lijsten],
                "aantal_lijsten": len(lijsten)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reden": str(e)[:400]}


def lijsten() -> list[dict]:
    if not configured():
        return []
    uit = []
    for l in _get("lists", **{"page[size]": "100"}).get("data", []):
        uit.append({"id": l["id"], "naam": l["attributes"].get("name"),
                    "aangemaakt": l["attributes"].get("created")})
    return uit


def segmenten() -> list[dict]:
    if not configured():
        return []
    uit = []
    for s in _get("segments", **{"page[size]": "100"}).get("data", []):
        uit.append({"id": s["id"], "naam": s["attributes"].get("name")})
    return uit


def aantal_profielen(lijst_id: str) -> int | None:
    """Hoeveel mensen zitten er in deze lijst? Nodig om te weten wat je aanricht."""
    if not configured():
        return None
    try:
        d = _get(f"lists/{lijst_id}", **{"additional-fields[list]": "profile_count"})
        return (d.get("data", {}).get("attributes", {}) or {}).get("profile_count")
    except Exception:  # noqa: BLE001
        return None


def sjabloon_aanmaken(naam: str, html: str, tekst: str = "") -> dict:
    """Zet de inhoud als sjabloon in Klaviyo. Verstuurt niets."""
    if not configured():
        return {"ok": False, "reden": "Klaviyo niet ingesteld"}
    body = {"data": {"type": "template", "attributes": {
        "name": naam, "editor_type": "CODE", "html": html, "text": tekst or None}}}
    d = _post("templates", body)
    return {"ok": True, "template_id": d.get("data", {}).get("id"), "naam": naam}


def campagne_klaarzetten(naam: str, onderwerp: str, template_id: str,
                         lijst_id: str, afzender_naam: str = "Farmers Atelier",
                         afzender_adres: str | None = None) -> dict:
    """Maakt een campagne in Klaviyo als CONCEPT.

    Klaviyo zet een nieuwe campagne standaard op 'draft'. Er wordt hier bewust
    geen verzendmoment gezet en geen verzendopdracht gegeven: dat doet een mens,
    in Klaviyo, na een laatste blik op de weergave en de afmeldlink.
    """
    if not configured():
        return {"ok": False, "reden": "Klaviyo niet ingesteld"}
    afzender = afzender_adres or config.secret("klaviyo", "afzender") or "info@farmersatelier.com"
    body = {"data": {"type": "campaign", "attributes": {
        "name": naam,
        "audiences": {"included": [lijst_id], "excluded": []},
        "campaign-messages": {"data": [{
            "type": "campaign-message",
            "attributes": {
                "definition": {
                    "channel": "email",
                    "label": naam,
                    "content": {"subject": onderwerp,
                                "from_email": afzender,
                                "from_label": afzender_naam},
                    "render_options": {"shorten_links": True,
                                       "add_org_prefix": True,
                                       "add_info_link": True,
                                       "add_opt_out_language": True},
                },
            },
        }]},
    }}}
    d = _post("campaigns", body)
    campagne_id = d.get("data", {}).get("id")

    # Sjabloon aan het bericht hangen. Zonder deze stap is de campagne leeg.
    try:
        berichten = (d.get("data", {}).get("relationships", {})
                     .get("campaign-messages", {}).get("data", []))
        if berichten and template_id:
            _post(f"campaign-message-assign-template",
                  {"data": {"type": "campaign-message", "id": berichten[0]["id"],
                            "relationships": {"template": {"data": {"type": "template",
                                                                    "id": template_id}}}}})
    except Exception as e:  # noqa: BLE001
        return {"ok": True, "campagne_id": campagne_id,
                "waarschuwing": f"campagne staat klaar maar het sjabloon koppelen mislukte: {str(e)[:200]}"}

    return {"ok": True, "campagne_id": campagne_id, "status": "concept",
            "let_op": "Staat als concept in Klaviyo. Verzenden doe je daar, met de hand."}
