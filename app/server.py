"""HTTP-server: statische inbox, JSON-API, webhooks, SSE en achtergrondtaken.

Zelfde uitgangspunten als serve.py in de andere dashboards:
- serveert UITSLUITEND static/ (nooit de projectmap met .secrets.json);
- no-cache-headers, zodat een wijziging altijd direct zichtbaar is;
- weigert vreemde Host-headers (DNS-rebinding) zolang we op localhost draaien;
- webhooks slaan eerst op en antwoorden 200; een achtergrondthread verwerkt.
"""

from __future__ import annotations

import http.server
import json
import mimetypes
import os
import re
import socketserver
import sys
import threading
import time
import traceback
import urllib.parse

import config
from app import api, db, events, knowledge, pipeline, rules, service
from app.channels import email_gmail, email_imap, meta, shopify_webhooks, tiktok

ROUTES = [
    ("GET", r"^/api/bootstrap$", api.bootstrap),
    ("GET", r"^/api/conversations$", api.conversations),
    ("GET", r"^/api/conversations/(?P<id>\d+)$", api.conversation),
    ("POST", r"^/api/conversations/(?P<id>\d+)/reply$", api.reply),
    ("POST", r"^/api/conversations/(?P<id>\d+)/note$", api.note),
    ("POST", r"^/api/conversations/(?P<id>\d+)/assign$", api.assign),
    ("POST", r"^/api/conversations/(?P<id>\d+)/status$", api.status),
    ("POST", r"^/api/conversations/(?P<id>\d+)/priority$", api.priority),
    ("POST", r"^/api/conversations/(?P<id>\d+)/intent$", api.intent),
    ("POST", r"^/api/conversations/(?P<id>\d+)/escalate$", api.escalate),
    ("POST", r"^/api/conversations/(?P<id>\d+)/resolve-human$", api.resolve_human),
    ("POST", r"^/api/conversations/(?P<id>\d+)/tag$", api.tag),
    ("POST", r"^/api/conversations/(?P<id>\d+)/regenerate$", api.regenerate),
    ("POST", r"^/api/conversations/(?P<id>\d+)/actions$", api.propose_action),
    ("POST", r"^/api/conversations/(?P<id>\d+)/private-reply$", api.private_reply),
    ("POST", r"^/api/drafts/(?P<id>\d+)/feedback$", api.draft_feedback),
    ("POST", r"^/api/drafts/(?P<id>\d+)/reject$", api.draft_reject),
    ("GET", r"^/api/actions$", api.actions_list),
    ("POST", r"^/api/actions/(?P<id>\d+)/decide$", api.action_decide),
    ("GET", r"^/api/dashboard$", api.dashboard),
    ("GET", r"^/api/learning$", api.learning),
    ("POST", r"^/api/learning/analyze$", api.learning_analyze),
    ("GET", r"^/api/rules$", api.rules_list),
    ("POST", r"^/api/rules$", api.rules_save),
    ("POST", r"^/api/rules/(?P<id>\d+)$", api.rules_save),
    ("DELETE", r"^/api/rules/(?P<id>\d+)$", api.rules_delete),
    ("GET", r"^/api/knowledge$", api.knowledge_list),
    ("POST", r"^/api/knowledge/sync$", api.knowledge_sync),
    ("POST", r"^/api/knowledge/(?P<slug>[a-z0-9-]+)$", api.knowledge_save),
    ("POST", r"^/api/settings$", api.settings_save),
    ("GET", r"^/api/customers/(?P<id>\d+)$", api.customer),
    ("GET", r"^/api/orders/(?P<name>[^/]+)$", api.order),
    ("POST", r"^/api/simulate$", api.simulate),
    ("GET", r"^/api/integrations$", api.integrations_status),
    ("POST", r"^/api/fulfillment/event$", api.fulfillment_event),
]
_COMPILED = [(m, re.compile(p), f) for m, p, f in ROUTES]

TOEGESTANE_HOSTS = {f"127.0.0.1:{config.POORT}", f"localhost:{config.POORT}", f"[::1]:{config.POORT}"}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "FarmersAtelierSupport/0.1"

    def log_message(self, fmt, *args):  # rustiger log
        if "/events" in (args[0] if args else ""):
            return
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # --- helpers ---------------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))

    def _raw_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _host_ok(self) -> bool:
        if config.BIND != "127.0.0.1":
            return True
        return (self.headers.get("Host") or "") in TOEGESTANE_HOSTS

    def _user_id(self) -> int | None:
        try:
            return int(self.headers.get("X-User-Id") or 1)
        except ValueError:
            return 1

    # --- routing ---------------------------------------------------------------
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str):
        url = urllib.parse.urlsplit(self.path)
        pad = url.path
        params = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        if pad.startswith("/webhooks/"):
            return self._webhook(method, pad, params)
        if not self._host_ok():
            return self._send(421, b"Misdirected request", "text/plain")
        if pad == "/events" and method == "GET":
            return self._sse()
        if pad.startswith("/api/"):
            return self._api(method, pad, params)
        if method == "GET":
            return self._static(pad)
        self._send(404, b"Not found", "text/plain")

    def _csrf_ok(self) -> bool:
        """Schrijfverzoeken alleen vanaf onze eigen pagina: JSON-Content-Type (dwingt een
        CORS-preflight af die we niet beantwoorden) én geen cross-site Sec-Fetch-Site."""
        ct = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ct != "application/json":
            return False
        sfs = (self.headers.get("Sec-Fetch-Site") or "").lower()
        return sfs in ("", "same-origin", "none")

    def _api(self, method: str, pad: str, params: dict):
        for m, rx, fn in _COMPILED:
            mt = rx.match(pad)
            if m == method and mt:
                body = {}
                if method in ("POST", "DELETE"):
                    if not self._csrf_ok():
                        return self._json(403, {"error": "verzoek moet application/json zijn en van deze pagina komen"})
                    raw = self._raw_body()
                    if raw:
                        try:
                            body = json.loads(raw.decode("utf-8"))
                        except ValueError:
                            return self._json(400, {"error": "ongeldige JSON"})
                try:
                    params = dict(params, **mt.groupdict())
                    return self._json(200, fn(params, body, self._user_id()))
                except api.ApiError as fout:
                    return self._json(fout.status, {"error": str(fout)})
                except (KeyError, ValueError) as fout:
                    return self._json(400, {"error": str(fout)})
                except Exception as fout:  # noqa: BLE001
                    traceback.print_exc()
                    return self._json(500, {"error": f"{type(fout).__name__}: {fout}"})
        self._json(404, {"error": "onbekend pad"})

    def _static(self, pad: str):
        if pad in ("/", ""):
            pad = "/index.html"
        veilig = os.path.normpath(pad).lstrip("/")
        bestand = os.path.join(config.STATIC_DIR, veilig)
        if not bestand.startswith(config.STATIC_DIR + os.sep) or not os.path.isfile(bestand):
            return self._send(404, b"Not found", "text/plain")
        ctype = mimetypes.guess_type(bestand)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(bestand, "rb") as f:
            self._send(200, f.read(), ctype)

    def _sse(self):
        q = events.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(b": verbonden\n\n")
            self.wfile.flush()
            while True:
                try:
                    data = q.get(timeout=20)
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                except Exception:  # queue.Empty → keepalive
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            events.unsubscribe(q)

    # --- webhooks ----------------------------------------------------------------
    def _webhook(self, method: str, pad: str, params: dict):
        # Zonder geheim (nog niet gekoppeld) accepteren we webhooks alleen lokaal — nooit via een tunnel.
        geheim = {"/webhooks/meta": config.secret("meta", "app_secret"),
                  "/webhooks/shopify": config.secret("shopify", "webhook_secret") or config.secret("shopify", "client_secret"),
                  "/webhooks/fulfillment": config.secret("fulfillment", "webhook_token")}.get(pad)
        if not geheim and not self._host_ok() and method == "POST":
            return self._send(403, b"webhook-geheim ontbreekt; alleen lokaal testen toegestaan", "text/plain")
        if pad == "/webhooks/meta":
            if method == "GET":
                challenge = meta.verify_challenge(params)
                if challenge is None:
                    return self._send(403, b"verify token klopt niet", "text/plain")
                return self._send(200, challenge.encode(), "text/plain")
            raw = self._raw_body()
            if not meta.verify_signature(raw, self.headers.get("X-Hub-Signature-256")):
                return self._send(403, b"handtekening klopt niet", "text/plain")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except ValueError:
                return self._send(400, b"geen JSON", "text/plain")
            pipeline.enqueue("meta", payload)
            return self._send(200, b"EVENT_RECEIVED", "text/plain")
        if pad == "/webhooks/shopify" and method == "POST":
            raw = self._raw_body()
            if not shopify_webhooks.verify_signature(raw, self.headers.get("X-Shopify-Hmac-SHA256")):
                return self._send(401, b"hmac klopt niet", "text/plain")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except ValueError:
                return self._send(400, b"geen JSON", "text/plain")
            pipeline.enqueue("shopify", {"topic": self.headers.get("X-Shopify-Topic"), "payload": payload},
                             external_id=self.headers.get("X-Shopify-Webhook-Id"))
            return self._send(200, b"ok", "text/plain")
        if pad == "/webhooks/fulfillment" and method == "POST":
            raw = self._raw_body()
            token = config.secret("fulfillment", "webhook_token")
            if token and self.headers.get("X-Webhook-Token") != token:
                return self._send(401, b"token klopt niet", "text/plain")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except ValueError:
                return self._send(400, b"geen JSON", "text/plain")
            pipeline.enqueue("fulfillment", payload)
            return self._send(200, b"ok", "text/plain")
        self._send(404, b"Not found", "text/plain")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _fulfillment_payload(payload: dict) -> list:
    from app.integrations import fulfillment
    fulfillment.record_event(payload["order_name"], payload["stage"], payload.get("occurred_at") or db.now(),
                             carrier=payload.get("carrier"), tracking=payload.get("tracking"), detail=payload.get("detail"), raw=payload)
    return []


HANDLERS = {
    "meta": meta.parse_webhook,
    "shopify": lambda p: shopify_webhooks.handle(p.get("topic"), p.get("payload") or {}),
    "fulfillment": _fulfillment_payload,
}


def achtergrond():
    """Elke 30 s: wachtrij verwerken, e-mail/TikTok pollen, snoozes laten aflopen."""
    while True:
        try:
            pipeline.drain_queue(HANDLERS)
            for fetch in (email_gmail.fetch_new, email_imap.fetch_new, tiktok.fetch_new):
                try:
                    for inbound in fetch():
                        pipeline.ingest(inbound)
                except Exception as fout:  # noqa: BLE001
                    print(f"   ! pollen {fetch.__module__}: {fout}", flush=True)
            service.unsnooze_due()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(30)


def lek_check() -> None:
    """Weigert te starten als een secret in de statische bestanden is beland."""
    geheimen = config.load_secrets()
    waarden = []

    def verzamel(x):
        if isinstance(x, dict):
            for v in x.values():
                verzamel(v)
        elif isinstance(x, str) and len(x) >= 12:
            waarden.append(x)
    verzamel(geheimen)
    for naam in os.listdir(config.STATIC_DIR):
        pad = os.path.join(config.STATIC_DIR, naam)
        if os.path.isfile(pad):
            with open(pad, encoding="utf-8", errors="ignore") as f:
                inhoud = f.read()
            for w in waarden:
                if w in inhoud:
                    raise SystemExit(f"LEK: een geheim staat in static/{naam}. Gestopt.")


def main() -> None:
    db.init_db()
    rules.seed_defaults()
    knowledge.sync_from_disk()
    lek_check()
    status = config.integratie_status()
    from app.ai import agent as ai
    print(f"Farmers Atelier Support — http://{config.BIND}:{config.POORT}/")
    print("   AI-modus:      " + ai.agent_mode() + ("" if status["anthropic"] else "  (geen ANTHROPIC_API_KEY → mock)"))
    for k, v in status.items():
        if k != "anthropic":
            print(f"   {k:12s} {'gekoppeld' if v else 'mock / niet gekoppeld'}")
    if not db.scalar("SELECT COUNT(*) FROM conversations"):
        print("   Nog geen gesprekken. Mock-data: ./.venv/bin/python mock/generate.py")
    threading.Thread(target=achtergrond, daemon=True, name="achtergrond").start()
    with Server((config.BIND, config.POORT), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nGestopt.")


if __name__ == "__main__":
    main()
