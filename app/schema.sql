-- Farmers Atelier Support — databaseschema (SQLite)
-- Gespiegeld aan het Gorgias/Chatwoot-model: klanten met kanaal-identiteiten,
-- gesprekken (tickets) met berichten, een append-only events-log, AI-analyses en
-- concepten, acties met goedkeuring, orders-cache, kennisbank, rules en leerdata.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  email       TEXT UNIQUE,
  role        TEXT NOT NULL DEFAULT 'agent',   -- agent | admin
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS customers (
  id                  INTEGER PRIMARY KEY,
  name                TEXT,
  email               TEXT,
  phone               TEXT,
  shopify_customer_id TEXT,
  avatar_url          TEXT,
  tags                TEXT NOT NULL DEFAULT '[]',   -- JSON-lijst
  note                TEXT,
  total_spent         REAL NOT NULL DEFAULT 0,
  orders_count        INTEGER NOT NULL DEFAULT 0,
  language            TEXT,
  created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(lower(email));

-- Eén klant kan meerdere kanaal-identiteiten hebben (e-mailadres, Instagram-ID, PSID…).
CREATE TABLE IF NOT EXISTS customer_identities (
  id           INTEGER PRIMARY KEY,
  customer_id  INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  channel      TEXT NOT NULL,        -- email | instagram | facebook | tiktok | shopify
  external_id  TEXT NOT NULL,        -- e-mailadres, IGSID, PSID, tiktok user id, shopify gid
  handle       TEXT,                 -- @gebruikersnaam
  display_name TEXT,
  UNIQUE(channel, external_id)
);

CREATE TABLE IF NOT EXISTS conversations (
  id                       INTEGER PRIMARY KEY,
  customer_id              INTEGER REFERENCES customers(id),
  channel                  TEXT NOT NULL,   -- email | instagram | facebook | tiktok | shopify
  via                      TEXT NOT NULL,   -- email | dm | comment | contact_form | api | mention
  subject                  TEXT,
  status                   TEXT NOT NULL DEFAULT 'open',  -- open | snoozed | closed | spam
  priority                 TEXT NOT NULL DEFAULT 'normal', -- low | normal | high | critical
  intent                   TEXT,            -- bv. shipping.status
  sentiment                TEXT,            -- positive | neutral | negative
  language                 TEXT,
  ai_status                TEXT NOT NULL DEFAULT 'none',
  -- none | processing | analyzed | drafted | auto_answered | asked_info | handover | closed | ignored | error
  needs_human              INTEGER NOT NULL DEFAULT 0,
  needs_human_reason       TEXT,
  assignee_id              INTEGER REFERENCES users(id),
  order_name               TEXT,            -- "#1843"
  tags                     TEXT NOT NULL DEFAULT '[]',
  summary                  TEXT,
  external_thread_id       TEXT,            -- e-mail thread-id, IG-gesprek-id, comment-id
  external_ref             TEXT NOT NULL DEFAULT '{}', -- JSON: post_id, media_id, comment_id, permalink…
  snooze_until             TEXT,
  first_response_at        TEXT,
  last_message_at          TEXT,
  last_customer_message_at TEXT,
  closed_at                TEXT,
  created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_conv_status ON conversations(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_customer ON conversations(customer_id);
CREATE INDEX IF NOT EXISTS idx_conv_thread ON conversations(channel, external_thread_id);

CREATE TABLE IF NOT EXISTS messages (
  id              INTEGER PRIMARY KEY,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  direction       TEXT NOT NULL,      -- in | out
  kind            TEXT NOT NULL DEFAULT 'public',  -- public | note | system
  author_type     TEXT NOT NULL,      -- customer | agent | ai | rule | system
  author_id       INTEGER,
  author_name     TEXT,
  body_text       TEXT NOT NULL DEFAULT '',
  body_html       TEXT,
  attachments     TEXT NOT NULL DEFAULT '[]',  -- JSON [{name,url,content_type}]
  external_id     TEXT,               -- Message-ID, mid, comment-id
  source          TEXT NOT NULL DEFAULT '{}',  -- JSON: from/to/headers/raw ids
  status          TEXT NOT NULL DEFAULT 'sent', -- sent | pending | failed | received
  error           TEXT,
  draft_id        INTEGER,            -- als dit bericht uit een AI-concept kwam
  sent_at         TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_external ON messages(external_id) WHERE external_id IS NOT NULL;

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  body_text, content='messages', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, body_text) VALUES (new.id, new.body_text);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, body_text) VALUES ('delete', old.id, old.body_text);
END;

-- Append-only audittrail (zoals Gorgias' events).
CREATE TABLE IF NOT EXISTS events (
  id              INTEGER PRIMARY KEY,
  conversation_id INTEGER,
  customer_id     INTEGER,
  type            TEXT NOT NULL,      -- ticket-created, ticket-closed, message-created, ai-analyzed, rule-executed, action-approved…
  actor_type      TEXT NOT NULL DEFAULT 'system',  -- system | agent | ai | rule | customer
  actor_id        INTEGER,
  data            TEXT NOT NULL DEFAULT '{}',
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_events_conv ON events(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS ai_analyses (
  id                 INTEGER PRIMARY KEY,
  conversation_id    INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id         INTEGER,
  intent             TEXT NOT NULL,
  intent_confidence  REAL,
  secondary_intents  TEXT NOT NULL DEFAULT '[]',
  priority           TEXT NOT NULL,
  sentiment          TEXT NOT NULL,
  language           TEXT,
  needs_human        INTEGER NOT NULL DEFAULT 0,
  needs_human_reason TEXT,
  escalation_flags   TEXT NOT NULL DEFAULT '[]',   -- legal_threat, chargeback, abusive, human_requested, vip…
  missing_info       TEXT NOT NULL DEFAULT '[]',   -- order_number, photo, size, address…
  order_ref          TEXT,
  next_action        TEXT NOT NULL,     -- answer | ask_info | handover | close | snooze | ignore
  summary            TEXT,
  reasoning          TEXT,
  used_knowledge     TEXT NOT NULL DEFAULT '[]',
  model              TEXT,
  is_mock            INTEGER NOT NULL DEFAULT 0,
  raw                TEXT NOT NULL DEFAULT '{}',
  created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_conv ON ai_analyses(conversation_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_drafts (
  id              INTEGER PRIMARY KEY,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  analysis_id     INTEGER REFERENCES ai_analyses(id),
  body            TEXT NOT NULL,
  kind            TEXT NOT NULL DEFAULT 'answer',  -- answer | ask_info | auto
  status          TEXT NOT NULL DEFAULT 'pending', -- pending | sent | edited_sent | rejected | superseded | auto_sent
  sent_body       TEXT,
  edited          INTEGER NOT NULL DEFAULT 0,
  similarity      REAL,                -- 0..1 overeenkomst concept vs verstuurd
  verifier        TEXT NOT NULL DEFAULT '{}',  -- JSON: {ok, issues[], contains_promise…}
  used_knowledge  TEXT NOT NULL DEFAULT '[]',
  feedback        TEXT,                -- up | down
  feedback_reason TEXT,
  model           TEXT,
  is_mock         INTEGER NOT NULL DEFAULT 0,
  decided_by      INTEGER,
  decided_at      TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_drafts_conv ON ai_drafts(conversation_id, created_at DESC);

-- Acties die goedkeuring van een mens vereisen (annuleren, refund, adres, comment verbergen…).
CREATE TABLE IF NOT EXISTS pending_actions (
  id              INTEGER PRIMARY KEY,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  type            TEXT NOT NULL,      -- cancel_order | refund | address_change | hide_comment | create_return | tag_order | note_order
  description     TEXT NOT NULL,      -- leesbare zin: "Order #1843 annuleren en €69,95 terugstorten?"
  params          TEXT NOT NULL DEFAULT '{}',
  status          TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected | executed | failed
  result          TEXT,
  proposed_by     TEXT NOT NULL DEFAULT 'ai',
  decided_by      INTEGER,
  decided_at      TEXT,
  executed_at     TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_actions_status ON pending_actions(status, created_at);

-- Cache van Shopify-orders (wordt gevuld door de Shopify-client of de mock).
CREATE TABLE IF NOT EXISTS orders (
  id                 INTEGER PRIMARY KEY,
  shopify_id         TEXT UNIQUE,
  name               TEXT NOT NULL UNIQUE,    -- "#1843"
  customer_id        INTEGER REFERENCES customers(id),
  email              TEXT,
  created_at         TEXT,
  financial_status   TEXT,    -- PAID | PENDING | REFUNDED | PARTIALLY_REFUNDED | VOIDED
  fulfillment_status TEXT,    -- UNFULFILLED | FULFILLED | PARTIALLY_FULFILLED | IN_PROGRESS
  return_status      TEXT,    -- NO_RETURN | RETURN_REQUESTED | IN_PROGRESS | RETURNED
  total              REAL,
  currency           TEXT NOT NULL DEFAULT 'EUR',
  line_items         TEXT NOT NULL DEFAULT '[]',
  shipping_address   TEXT NOT NULL DEFAULT '{}',
  tracking           TEXT NOT NULL DEFAULT '{}',   -- {company, number, url, status, events[]}
  fulfillment        TEXT NOT NULL DEFAULT '{}',   -- externe fulfillment-status {stage, updated_at, events[]}
  refunds            TEXT NOT NULL DEFAULT '[]',
  returns            TEXT NOT NULL DEFAULT '[]',
  cancelled_at       TEXT,
  note               TEXT,
  tags               TEXT NOT NULL DEFAULT '[]',
  raw                TEXT NOT NULL DEFAULT '{}',
  synced_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(lower(email));
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);

CREATE TABLE IF NOT EXISTS products (
  id          INTEGER PRIMARY KEY,
  shopify_id  TEXT UNIQUE,
  title       TEXT NOT NULL,
  handle      TEXT,
  product_type TEXT,
  description TEXT,
  price       REAL,
  variants    TEXT NOT NULL DEFAULT '[]',  -- [{sku,size,color,inventory,price}]
  status      TEXT NOT NULL DEFAULT 'active',
  synced_at   TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_articles (
  id          INTEGER PRIMARY KEY,
  slug        TEXT NOT NULL UNIQUE,
  title       TEXT NOT NULL,
  category    TEXT,
  body        TEXT NOT NULL,
  is_complete INTEGER NOT NULL DEFAULT 1,  -- 0 als het bestand nog TODO's bevat
  source_file TEXT,
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
  title, body, content='knowledge_articles', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS kb_ai AFTER INSERT ON knowledge_articles BEGIN
  INSERT INTO knowledge_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS kb_ad AFTER DELETE ON knowledge_articles BEGIN
  INSERT INTO knowledge_fts(knowledge_fts, rowid, title, body) VALUES ('delete', old.id, old.title, old.body);
END;
CREATE TRIGGER IF NOT EXISTS kb_au AFTER UPDATE ON knowledge_articles BEGIN
  INSERT INTO knowledge_fts(knowledge_fts, rowid, title, body) VALUES ('delete', old.id, old.title, old.body);
  INSERT INTO knowledge_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;

CREATE TABLE IF NOT EXISTS rules (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  enabled     INTEGER NOT NULL DEFAULT 1,
  priority    INTEGER NOT NULL DEFAULT 100,   -- lager = eerder
  trigger     TEXT NOT NULL DEFAULT 'message_analyzed', -- message_analyzed | ticket_created | before_send
  conditions  TEXT NOT NULL DEFAULT '[]',     -- JSON [{field, op, value}]
  actions     TEXT NOT NULL DEFAULT '[]',     -- JSON [{type, value}]
  stop        INTEGER NOT NULL DEFAULT 0,     -- stop na deze rule
  hits        INTEGER NOT NULL DEFAULT 0,
  description TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS macros (
  id      INTEGER PRIMARY KEY,
  name    TEXT NOT NULL,
  body    TEXT NOT NULL,   -- met {{klant.voornaam}} {{order.naam}} enz.
  actions TEXT NOT NULL DEFAULT '[]'
);

-- Leerdata: per verstuurd antwoord wat de klant vroeg, wat AI dacht, wat wij stuurden.
CREATE TABLE IF NOT EXISTS learning_records (
  id                 INTEGER PRIMARY KEY,
  conversation_id    INTEGER NOT NULL,
  channel            TEXT,
  customer_question  TEXT,
  ai_intent          TEXT,
  ai_priority        TEXT,
  ai_sentiment       TEXT,
  ai_draft           TEXT,
  final_answer       TEXT,
  edited             INTEGER NOT NULL DEFAULT 0,
  similarity         REAL,
  diff_summary       TEXT,
  sent_by            TEXT,          -- agent | ai
  resolved           INTEGER,
  escalated          INTEGER NOT NULL DEFAULT 0,
  order_info         TEXT NOT NULL DEFAULT '{}',
  used_knowledge     TEXT NOT NULL DEFAULT '[]',
  feedback           TEXT,
  feedback_reason    TEXT,
  created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Ruwe inkomende webhooks: eerst opslaan (snel 200 teruggeven), dan verwerken.
CREATE TABLE IF NOT EXISTS inbound_queue (
  id          INTEGER PRIMARY KEY,
  source      TEXT NOT NULL,     -- meta | shopify | tiktok | email | mock
  external_id TEXT,
  payload     TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'queued', -- queued | done | failed | duplicate
  error       TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  processed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_inbound_external ON inbound_queue(source, external_id) WHERE external_id IS NOT NULL;

-- Externe fulfillment-events (van de fulfillmentpartij of vervoerder).
CREATE TABLE IF NOT EXISTS fulfillment_events (
  id          INTEGER PRIMARY KEY,
  order_name  TEXT NOT NULL,
  stage       TEXT NOT NULL,   -- received | picking | packed | shipped | in_transit | delivered | problem | return_in_transit | return_received
  carrier     TEXT,
  tracking    TEXT,
  detail      TEXT,
  occurred_at TEXT NOT NULL,
  raw         TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_fulfil_order ON fulfillment_events(order_name, occurred_at);
