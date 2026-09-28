"""E-mailkanaal voor Microsoft 365 / Outlook, via de Graph API.

De mail van Farmers Atelier loopt via Microsoft 365 (de MX-records van
farmersatelier.com wijzen naar `mail.protection.outlook.com`), dus niet via
Gmail en niet via een gewone IMAP-hoster. Daarom dit kanaal naast de bestaande
twee.

Twee manieren om in te loggen, beide ondersteund:

* **Applicatie** (`mode: "application"`) — de app logt als zichzelf in met een
  client secret en leest één vaste postbus. Geen gebruiker die opnieuw moet
  inloggen, dus dit is wat je wilt voor een supportbus die dag en nacht
  doorloopt. Vereist eenmalig toestemming van een beheerder van de tenant.
* **Gedelegeerd** (`mode: "delegated"`) — de app werkt namens één ingelogde
  gebruiker met een refresh-token. Geen beheerder nodig, maar het token
  verloopt en moet af en toe vernieuwd worden.

Wat er in `.secrets.json` onder `"microsoft"` hoort:

    {"tenant_id": "...", "client_id": "...", "client_secret": "...",
     "postbus": "support@farmersatelier.com", "mode": "application",
     "map": "Inbox", "refresh_token": ""}
"""

from __future__ import annotations

import time

import config
from app import db

try:
    import requests
except ImportError:  # zonder requests draait alles gewoon in mock-modus
    requests = None

GRAPH = "https://graph.microsoft.com/v1.0"
_TOKEN = {"value": None, "expires": 0.0}

# Hoeveel berichten we per ronde maximaal ophalen. Genoeg om een achterstand
# weg te werken, klein genoeg om niet in een limiet te lopen.
PER_RONDE = 50


def _conf() -> dict:
    return config.secret("microsoft") or {}


def configured() -> bool:
    m = _conf()
    if not requests or not m.get("tenant_id") or not m.get("client_id") or not m.get("postbus"):
        return False
    if (m.get("mode") or "application") == "application":
        return bool(m.get("client_secret"))
    return bool(m.get("refresh_token"))


def afzender() -> str:
    return _conf().get("postbus") or config.SUPPORT_EMAIL_FALLBACK


def _access_token() -> str:
    """Haalt een token op en houdt het vast tot het bijna verloopt."""
    if _TOKEN["value"] and time.time() < _TOKEN["expires"] - 60:
        return _TOKEN["value"]
    m = _conf()
    url = f"https://login.microsoftonline.com/{m['tenant_id']}/oauth2/v2.0/token"
    if (m.get("mode") or "application") == "application":
        data = {"client_id": m["client_id"], "client_secret": m["client_secret"],
                "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"}
    else:
        data = {"client_id": m["client_id"], "client_secret": m.get("client_secret", ""),
                "refresh_token": m["refresh_token"], "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send offline_access"}
    r = requests.post(url, data=data, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Microsoft-token ophalen mislukt ({r.status_code}): {r.text[:300]}")
    uit = r.json()
    _TOKEN["value"] = uit["access_token"]
    _TOKEN["expires"] = time.time() + int(uit.get("expires_in", 3600))
    return _TOKEN["value"]


def _basis() -> str:
    """Het pad naar de postbus. Bij applicatie-toegang moet die expliciet genoemd."""
    m = _conf()
    if (m.get("mode") or "application") == "application":
        return f"users/{m['postbus']}"
    return "me"


def _get(pad: str, **params) -> dict:
    r = requests.get(f"{GRAPH}/{pad}", params=params,
                     headers={"Authorization": f"Bearer {_access_token()}"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Graph GET {pad}: {r.status_code} {r.text[:300]}")
    return r.json()


def _post(pad: str, body: dict) -> dict:
    r = requests.post(f"{GRAPH}/{pad}", json=body,
                      headers={"Authorization": f"Bearer {_access_token()}"}, timeout=30)
    if r.status_code not in (200, 201, 202, 204):
        raise RuntimeError(f"Graph POST {pad}: {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


def _adres(veld: dict | None) -> tuple[str, str]:
    e = (veld or {}).get("emailAddress") or {}
    return (e.get("address") or "").lower(), e.get("name") or ""


def test() -> dict:
    """Kijkt of de koppeling werkt, zonder iets te verwerken.

    Vraagt bewust de mailmap op en niet het gebruikersprofiel: `GET users/{adres}`
    valt onder User.Read.All / Directory.Read.All, en die rechten hebben we niet en
    willen we ook niet. Mail.ReadWrite geeft toegang tot de post, niet tot de
    adreslijst. Op het profiel testen gaf daarom een 403 terwijl de koppeling zelf
    prima werkte.
    """
    if not configured():
        return {"ok": False, "reden": "niet ingesteld: vul 'microsoft' in .secrets.json"}
    try:
        n = _get(f"{_basis()}/mailFolders/{_conf().get('map', 'Inbox')}",
                 **{"$select": "displayName,totalItemCount,unreadItemCount"})
        return {"ok": True, "postbus": afzender(), "map": n.get("displayName"),
                "berichten": n.get("totalItemCount"), "ongelezen": n.get("unreadItemCount")}
    except Exception as e:  # noqa: BLE001 — de tekst moet leesbaar in het dashboard
        return {"ok": False, "reden": str(e)[:400]}


def fetch_new(sinds: str | None = None, maximaal: int = PER_RONDE) -> list[dict]:
    """Nieuwe berichten uit de postbus, als inbound-dicts voor de pipeline.

    Onthoudt zelf tot waar het gekomen is in de instelling `ms_laatste_ts`, zodat
    een herstart niet de hele mailbox opnieuw inleest.
    """
    if not configured():
        return []
    m = _conf()
    grens = sinds or db.setting("ms_laatste_ts") or ""
    params = {
        "$top": str(maximaal),
        "$orderby": "receivedDateTime asc",
        "$select": "id,conversationId,internetMessageId,subject,bodyPreview,body,from,toRecipients,receivedDateTime,isDraft",
    }
    if grens:
        params["$filter"] = f"receivedDateTime gt {grens}"

    data = _get(f"{_basis()}/mailFolders/{m.get('map', 'Inbox')}/messages", **params)
    uit, nieuwste = [], grens
    ons = afzender().lower()

    for b in data.get("value", []):
        if b.get("isDraft"):
            continue
        van_adres, van_naam = _adres(b.get("from"))
        if van_adres == ons:
            continue                      # ons eigen verzonden bericht, geen klantvraag
        inhoud = (b.get("body") or {}).get("content") or b.get("bodyPreview") or ""
        soort = ((b.get("body") or {}).get("contentType") or "text").lower()
        if soort == "html":
            from app.channels.email_common import html_to_text
            inhoud = html_to_text(inhoud)
        from app.channels.email_common import strip_quotes
        uit.append({
            "channel": "email",
            "external_id": b.get("internetMessageId") or b.get("id"),
            "thread_id": b.get("conversationId"),
            "from_email": van_adres,
            "from_name": van_naam,
            "subject": b.get("subject") or "(geen onderwerp)",
            "body": strip_quotes(inhoud).strip(),
            "received_at": b.get("receivedDateTime"),
            "raw_id": b.get("id"),
        })
        if (b.get("receivedDateTime") or "") > (nieuwste or ""):
            nieuwste = b["receivedDateTime"]

    if nieuwste and nieuwste != grens:
        db.set_setting("ms_laatste_ts", nieuwste)
    return uit


def _zoek_bericht_id(internet_id: str) -> str | None:
    """Van het internetMessageId naar het interne id dat Graph nodig heeft."""
    try:
        gevonden = _get(f"{_basis()}/messages",
                        **{"$filter": f"internetMessageId eq '{internet_id}'",
                           "$select": "id", "$top": "1"})
        rijen = gevonden.get("value") or []
        return rijen[0]["id"] if rijen else None
    except Exception:  # noqa: BLE001
        return None


def maak_concept(in_reply_to: str, body: str) -> dict:
    """Zet een antwoord als CONCEPT in Outlook, zonder het te versturen.

    Dit is de veilige tussenvorm: het concept staat bij Folkert in Outlook in de
    map Concepten, in dezelfde draad als de vraag van de klant, met geadresseerde
    en onderwerp al ingevuld. Hij leest het na, past aan wat hij wil en drukt zelf
    op Verzenden. Er gaat langs deze weg nooit iets vanzelf de deur uit.
    """
    if not configured():
        return {"ok": False, "reden": "Microsoft niet ingesteld"}
    bericht_id = _zoek_bericht_id(in_reply_to)
    if not bericht_id:
        return {"ok": False, "reden": f"oorspronkelijk bericht niet gevonden ({in_reply_to})"}
    try:
        concept = _post(f"{_basis()}/messages/{bericht_id}/createReply", {})
        concept_id = concept.get("id")
        if not concept_id:
            return {"ok": False, "reden": "Graph gaf geen concept terug"}
        # De tekst er los in zetten: createReply zet alleen de geciteerde
        # oorspronkelijke mail klaar, nog zonder ons antwoord erboven.
        r = requests.patch(f"{GRAPH}/{_basis()}/messages/{concept_id}",
                           json={"body": {"contentType": "Text", "content": body}},
                           headers={"Authorization": f"Bearer {_access_token()}"}, timeout=30)
        if r.status_code not in (200, 201):
            return {"ok": False, "reden": f"tekst plaatsen mislukt ({r.status_code}): {r.text[:200]}"}
        return {"ok": True, "concept_id": concept_id,
                "web_link": (r.json() or {}).get("webLink")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reden": str(e)[:300]}


def send(naar: str, onderwerp: str, body: str, in_reply_to: str | None = None,
         references: str | None = None, thread_id: str | None = None) -> dict:
    """Stuurt een antwoord. Beantwoordt het originele bericht als dat bekend is,
    zodat het bij de klant in dezelfde draad blijft staan."""
    if not configured():
        return {"ok": False, "reden": "Microsoft niet ingesteld"}

    tekst = {"contentType": "Text", "content": body}
    if in_reply_to:
        # Graph wil het interne id van het bericht; dat zoeken we op via het
        # internetMessageId dat wij bewaard hebben.
        try:
            gevonden = _get(f"{_basis()}/messages",
                            **{"$filter": f"internetMessageId eq '{in_reply_to}'", "$select": "id", "$top": "1"})
            rijen = gevonden.get("value") or []
            if rijen:
                _post(f"{_basis()}/messages/{rijen[0]['id']}/reply", {"message": {"body": tekst}})
                return {"ok": True, "via": "reply"}
        except Exception:  # noqa: BLE001 — lukt het niet, dan als los bericht
            pass

    _post(f"{_basis()}/sendMail", {
        "message": {"subject": onderwerp, "body": tekst,
                    "toRecipients": [{"emailAddress": {"address": naar}}]},
        "saveToSentItems": True,
    })
    return {"ok": True, "via": "sendMail"}
