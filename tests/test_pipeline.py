"""Tests voor de kern: klant herkennen, gesprek threaden, mock-AI, rules, acties, e-mailparser,
Meta-webhookparser. Draaien met:  ./.venv/bin/python -m unittest -v
Elke test gebruikt een eigen tijdelijke database.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

# VÓÓR het importeren van config: geen enkele test mag naar buiten praten. Zonder
# deze vlag leest config gewoon .secrets.json, en verstuurde de suite echte mail
# vanuit de postbus van Farmers Atelier (gebeurd op 28-09-2026).
os.environ["FA_TESTMODUS"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

assert not config.load_secrets(), "testmodus staat niet aan: tests zouden echt kunnen versturen"
assert not config.integratie_status()["microsoft"], "Outlook is bereikbaar in een test"


_TMP = tempfile.mkdtemp()
config.DB_PATH = os.path.join(_TMP, "test.db")

from app import db, knowledge, pipeline, rules, service  # noqa: E402
from app.channels import email_common, meta  # noqa: E402
from app.integrations import shopify  # noqa: E402


class Basis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(config.DB_PATH):
            os.remove(config.DB_PATH)
        db.init_db()
        rules.seed_defaults()
        knowledge.sync_from_disk()
        db.set_setting("ai_mode", "mock")
        cls.klant = db.insert("customers", {"name": "Sophie Jansen", "email": "sophie@test.nl", "orders_count": 1, "total_spent": 69.95})
        shopify.upsert_order({"shopify_id": "gid://shopify/Order/1", "name": "#1843", "email": "sophie@test.nl", "created_at": "2026-09-20T10:00:00Z",
                              "financial_status": "PAID", "fulfillment_status": "FULFILLED", "return_status": "NO_RETURN", "total": 69.95, "currency": "EUR",
                              "line_items": [{"title": "Essential Tee", "size": "M", "quantity": 1, "price": 34.95}, {"title": "Essential Tee", "size": "L", "quantity": 1, "price": 34.95}],
                              "shipping_address": {}, "tracking": {"company": "DHL", "number": "JVGL123", "url": "https://dhl.test/JVGL123", "status": "IN_TRANSIT", "events": []},
                              "refunds": [], "returns": [], "cancelled_at": None, "note": None, "tags": [], "raw": {}, "synced_at": db.now()}, customer_id=cls.klant)

    def _mail(self, tekst, email="sophie@test.nl", naam="Sophie Jansen", thread=None, mid=None, subject="Vraag"):
        return pipeline.ingest({"channel": "email", "via": "email", "external_message_id": mid, "external_thread_id": thread,
                                "sender": {"channel": "email", "external_id": email, "name": naam, "email": email},
                                "subject": subject, "text": tekst, "attachments": [], "external_ref": {}})


class TestPipeline(Basis):
    def test_wismo_met_ordernummer_maakt_concept(self):
        r = self._mail("Waar blijft mijn bestelling #1843?", thread="t1")
        conv = db.one("SELECT * FROM conversations WHERE id = ?", (r["conversation_id"],))
        self.assertEqual(conv["customer_id"], self.klant)
        self.assertEqual(conv["intent"], "shipping.status")
        self.assertEqual(conv["order_name"], "#1843")
        self.assertEqual(conv["ai_status"], "drafted")
        draft = db.one("SELECT * FROM ai_drafts WHERE conversation_id = ? AND status = 'pending'", (conv["id"],))
        self.assertIn("JVGL123", draft["body"])
        self.assertIn("wismo", db.loads(conv["tags"]))

    def test_onbekende_klant_zonder_order_vraagt_info(self):
        r = self._mail("Waar blijft mijn pakket?", email="nieuw@test.nl", naam="Nieuwe Klant", thread="t2")
        conv = db.one("SELECT * FROM conversations WHERE id = ?", (r["conversation_id"],))
        an = db.one("SELECT * FROM ai_analyses WHERE conversation_id = ?", (conv["id"],))
        self.assertIn("order_number", db.loads(an["missing_info"]))
        self.assertEqual(conv["ai_status"], "asked_info")
        draft = db.one("SELECT * FROM ai_drafts WHERE conversation_id = ?", (conv["id"],))
        self.assertEqual(draft["kind"], "ask_info")

    def test_dreiging_wordt_kritiek_en_mens(self):
        r = self._mail("Ik schakel mijn advocaat in als dit niet wordt opgelost. Kutbedrijf.", thread="t3")
        conv = db.one("SELECT * FROM conversations WHERE id = ?", (r["conversation_id"],))
        self.assertEqual(conv["priority"], "critical")
        self.assertEqual(conv["needs_human"], 1)
        self.assertEqual(conv["ai_status"], "handover")
        notitie = db.one("SELECT * FROM messages WHERE conversation_id = ? AND kind = 'note'", (conv["id"],))
        self.assertIsNotNone(notitie)

    def test_bedankje_sluit_zonder_antwoord(self):
        r = self._mail("Bedankt, helemaal goed zo!", thread="t4")
        conv = db.one("SELECT * FROM conversations WHERE id = ?", (r["conversation_id"],))
        self.assertEqual(conv["status"], "closed")
        self.assertEqual(conv["intent"], "other.thanks")

    def test_spam_wordt_spam(self):
        r = self._mail("Guaranteed backlinks and SEO services, unsubscribe here", email="spam@x.com", naam="Spam", thread="t5")
        conv = db.one("SELECT * FROM conversations WHERE id = ?", (r["conversation_id"],))
        self.assertEqual(conv["status"], "spam")

    def test_zelfde_thread_komt_in_zelfde_gesprek_en_heropent(self):
        r1 = self._mail("Vraag over mijn bestelling", thread="t6", mid="m1")
        service.set_status(r1["conversation_id"], "closed", 1)
        r2 = self._mail("Het is #1843", thread="t6", mid="m2")
        self.assertEqual(r1["conversation_id"], r2["conversation_id"])
        conv = db.one("SELECT status FROM conversations WHERE id = ?", (r1["conversation_id"],))
        self.assertEqual(conv["status"], "open")
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND direction = 'in'", (r1["conversation_id"],)), 2)

    def test_duplicaat_op_external_id(self):
        self._mail("Hallo", thread="t7", mid="dup-1")
        r = self._mail("Hallo", thread="t7", mid="dup-1")
        self.assertTrue(r["duplicate"])

    def test_nieuwe_email_thread_is_nieuw_gesprek(self):
        r1 = self._mail("Vraag A", thread="t8a")
        r2 = self._mail("Vraag B", thread="t8b")
        self.assertNotEqual(r1["conversation_id"], r2["conversation_id"])

    def test_publieke_comment_krijgt_geen_orderdetails(self):
        r = pipeline.ingest({"channel": "instagram", "via": "comment", "external_message_id": "c1", "external_thread_id": "c1",
                             "sender": {"channel": "instagram", "external_id": "ig-999", "handle": "sophiej_", "name": "sophiej_"},
                             "text": "Waar blijft mijn bestelling #1843?? al 2 weken", "attachments": [], "external_ref": {"comment_id": "c1"}})
        draft = db.one("SELECT * FROM ai_drafts WHERE conversation_id = ?", (r["conversation_id"],))
        self.assertNotIn("JVGL123", draft["body"])
        self.assertIn("DM", draft["body"])

    def test_versturen_maakt_leerrecord_en_meet_bewerking(self):
        r = self._mail("Waar blijft #1843?", thread="t9")
        draft = db.one("SELECT * FROM ai_drafts WHERE conversation_id = ? AND status = 'pending'", (r["conversation_id"],))
        service.send_reply(r["conversation_id"], draft["body"] + "\n\nPS: fijne dag!", user_id=1, draft_id=draft["id"])
        d2 = db.one("SELECT status, edited, similarity FROM ai_drafts WHERE id = ?", (draft["id"],))
        self.assertEqual(d2["status"], "edited_sent")
        self.assertEqual(d2["edited"], 1)
        rec = db.one("SELECT * FROM learning_records WHERE conversation_id = ?", (r["conversation_id"],))
        self.assertEqual(rec["ai_intent"], "shipping.status")
        self.assertEqual(rec["edited"], 1)
        conv = db.one("SELECT first_response_at FROM conversations WHERE id = ?", (r["conversation_id"],))
        self.assertIsNotNone(conv["first_response_at"])

    def test_actie_goedkeuren_voert_mock_uit(self):
        r = self._mail("Ik wil #1843 annuleren", thread="t10")
        aid = service.propose_action(r["conversation_id"], "cancel_order", {"order_name": "#1843", "refund": True}, "Order #1843 annuleren?")
        uit = service.decide_action(aid, True, 1)
        self.assertEqual(uit["status"], "executed")
        self.assertIsNotNone(shopify.get_order("#1843", refresh=False)["cancelled_at"])

    def test_rules_engine_condities(self):
        ctx = {"intent": "feedback.complaint", "sentiment": "negative", "escalation_flags": [], "customer_orders_count": 1}
        uit = rules.evaluate("message_analyzed", ctx)
        self.assertIn("Klacht + negatief → hoge prioriteit, mens nodig", uit["fired"])
        self.assertEqual(uit["set"]["priority"], "high")
        self.assertTrue(uit["needs_human"])

    def test_niveau_instelling_beperkt(self):
        db.set_setting("level:shipping.policy", "analyze")
        self.assertEqual(pipeline.effective_level("shipping.policy", None), "analyze")
        self.assertEqual(pipeline.effective_level("shipping.status", "analyze"), "analyze")
        self.assertEqual(pipeline.effective_level("shipping.status", None), "draft")


class TestReviewFixes(Basis):
    def test_zoeken_op_een_teken_crasht_niet(self):
        from app import api
        for q in ("#", "a", "1", "#18"):
            uit = api.conversations({"view": "alle", "q": q}, {}, 1)
            self.assertIn("items", uit)

    def test_dm_van_lang_geleden_heropent_oud_ticket_niet(self):
        def dm(mid):
            return pipeline.ingest({"channel": "instagram", "via": "dm", "external_message_id": mid, "external_thread_id": "psid-42",
                                    "sender": {"channel": "instagram", "external_id": "psid-42", "handle": "oud", "name": "oud"},
                                    "text": "Hoi, is maat M er nog?", "attachments": [], "external_ref": {}}, process=False)
        r1 = dm("dm-old-1")
        db.update("conversations", r1["conversation_id"], {"status": "closed", "closed_at": "2025-01-01T00:00:00Z"})
        r2 = dm("dm-old-2")
        self.assertNotEqual(r1["conversation_id"], r2["conversation_id"])
        r3 = dm("dm-old-3")
        self.assertEqual(r2["conversation_id"], r3["conversation_id"])

    def test_email_antwoord_via_in_reply_to_komt_in_zelfde_gesprek(self):
        r1 = self._mail("Vraag over #1843", thread="thr-A", mid="<a1@klant>")
        d = db.one("SELECT id, body FROM ai_drafts WHERE conversation_id = ? AND status = 'pending'", (r1["conversation_id"],))
        service.send_reply(r1["conversation_id"], d["body"], user_id=1, draft_id=d["id"])
        ons_id = db.one("SELECT external_id FROM messages WHERE conversation_id = ? AND direction = 'out' ORDER BY id DESC LIMIT 1", (r1["conversation_id"],))["external_id"]
        r2 = pipeline.ingest({"channel": "email", "via": "email", "external_message_id": "<a2@klant>", "external_thread_id": "<a2@klant>",
                              "sender": {"channel": "email", "external_id": "sophie@test.nl", "name": "Sophie", "email": "sophie@test.nl"},
                              "subject": "Re: Vraag", "text": "Dank!", "attachments": [], "external_ref": {"in_reply_to": ons_id, "references": ""}}, process=False)
        self.assertEqual(r1["conversation_id"], r2["conversation_id"])

    def test_contains_any_met_losse_string_en_none(self):
        self.assertTrue(rules._cmp("contains_any", ["abusive"], "abusive"))
        self.assertFalse(rules._cmp("contains_any", ["abusive"], None))
        self.assertFalse(rules._cmp("in", "refund.request", "refund"))

    def test_dubbel_goedkeuren_voert_een_keer_uit(self):
        r = self._mail("Annuleer #1843 aub", thread="thr-B")
        aid = service.propose_action(r["conversation_id"], "tag_order", {"order_name": "#1843", "tags": ["test"]}, "Taggen?")
        self.assertEqual(service.decide_action(aid, True, 1)["status"], "executed")
        with self.assertRaises(ValueError):
            service.decide_action(aid, True, 2)

    def test_html_mail_escapet(self):
        m = email_common.build_reply("support@fa.nl", "k@k.nl", "Re", "maat <M> & meer")
        html = m.get_body(preferencelist=("html",)).get_content()
        self.assertIn("maat &lt;M&gt; &amp; meer", html)


class TestParsers(unittest.TestCase):
    def test_email_quotes_gestript_en_autoreply_genegeerd(self):
        raw = (b"From: Sophie <sophie@test.nl>\r\nTo: support@farmersatelier.nl\r\nSubject: Re: Bestelling\r\nMessage-ID: <abc@test>\r\n"
               b"Date: Thu, 25 Sep 2026 10:00:00 +0200\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
               b"Het is #1843\r\n\r\nOp wo 24 sep 2026 om 12:00 schreef Farmers Atelier <support@farmersatelier.nl>:\r\n> Kun je je ordernummer sturen?\r\n")
        inb = email_common.parse_rfc822(raw)
        self.assertEqual(inb["text"], "Het is #1843")
        self.assertEqual(inb["sender"]["email"], "sophie@test.nl")
        auto = raw.replace(b"Subject:", b"Auto-Submitted: auto-replied\r\nSubject:")
        self.assertIsNone(email_common.parse_rfc822(auto))

    def test_ordernummers_uit_tekst(self):
        self.assertEqual(shopify.find_order_refs("order 1843 en #1844, ordernummer: 1845"), ["#1843", "#1844", "#1845"])

    def test_meta_webhook_dm_en_comment(self):
        dm = meta.parse_webhook(meta.voorbeeld_payload_ig_dm())
        self.assertEqual(len(dm), 1)
        self.assertEqual(dm[0]["channel"], "instagram")
        self.assertEqual(dm[0]["via"], "dm")
        self.assertEqual(dm[0]["sender"]["external_id"], "1234567890123456")
        comment = meta.parse_webhook({"object": "instagram", "entry": [{"id": "1", "time": 1, "changes": [{"field": "comments", "value": {
            "id": "c9", "from": {"id": "u1", "username": "anna"}, "text": "Komt deze in beige?", "media": {"id": "m1"}}}]}]})
        self.assertEqual(comment[0]["via"], "comment")
        self.assertEqual(comment[0]["external_ref"]["comment_id"], "c9")
        fb = meta.parse_webhook({"object": "page", "entry": [{"id": "p1", "time": 1, "changes": [{"field": "feed", "value": {
            "item": "comment", "verb": "add", "comment_id": "p1_9", "post_id": "p1_1", "parent_id": "p1_1", "from": {"id": "u2", "name": "Anna"}, "message": "Hoi"}}]}]})
        self.assertEqual(fb[0]["channel"], "facebook")
        self.assertEqual(fb[0]["external_thread_id"], "p1_9")


if __name__ == "__main__":
    unittest.main()


class TestNepshopStand(Basis):
    """De tijdelijke stand voor bestellingen die niet van ons zijn.

    Het gevaar zit niet in het antwoord zelf maar in wie het krijgt: een echte
    klant die te horen krijgt dat zijn bestelling niet van ons is, is een klant
    die we kwijt zijn. Vandaar deze tests op de grens.
    """

    def setUp(self):
        from app import nepshop
        self.nepshop = nepshop
        db.set_setting("nepshop_modus", True)

    def tearDown(self):
        db.set_setting("nepshop_modus", False)

    def test_uit_betekent_nooit(self):
        db.set_setting("nepshop_modus", False)
        self.assertFalse(self.nepshop.beoordeel("return.request", "99999")["van_toepassing"])

    def test_viercijferig_nummer_is_niet_van_ons(self):
        # #1008 en #1010 kwamen in de mailbox voorbij; geen van beide staat in
        # Shopify. Onze nummers zijn vijfcijferig (14541 t/m 19350).
        for nr in ("#1008", "#1010"):
            self.assertTrue(self.nepshop.beoordeel("return.request", nr)["van_toepassing"], nr)

    def test_nummer_uit_onze_reeks_gaat_naar_een_mens(self):
        # 19144 bestaat wél: Marvin Born, 1 februari, EUR 279,80. Zonder Shopify
        # kunnen we dat niet nagaan, en dan is een mens aan zet — nooit het
        # standaardantwoord, want dan sturen we een echte klant weg.
        uit = self.nepshop.beoordeel("return.request", "19144")
        self.assertFalse(uit["van_toepassing"])
        self.assertTrue(uit["mens_nodig"])

    def test_nummer_boven_ons_hoogste_is_niet_van_ons(self):
        # Onze laatste bestelling is 19350. Alles daarboven kan niet bestaan.
        self.assertTrue(self.nepshop.beoordeel("return.request", "22000")["van_toepassing"])

    def test_productvraag_valt_erbuiten(self):
        self.assertFalse(self.nepshop.beoordeel("product.question", "19144")["van_toepassing"])

    def test_zonder_ordernummer_wel(self):
        self.assertTrue(self.nepshop.beoordeel("refund.request", None)["van_toepassing"])

    def test_antwoord_gebruikt_de_voornaam(self):
        tekst = self.nepshop.antwoord_voor("Marvin Born")
        self.assertIn("Hoi Marvin", tekst)
        self.assertIn("Fraudehelpdesk", tekst)
        self.assertNotIn("{voornaam}", tekst)
