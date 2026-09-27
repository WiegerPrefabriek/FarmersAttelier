/* Farmers Atelier · Customer Service — inbox-frontend (vanilla JS, geen build-stap). */
"use strict";

// ---------------------------------------------------------------------------
// Hulpjes
// ---------------------------------------------------------------------------
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nl = (s) => esc(s).replace(/\n/g, "<br>");
const linkify = (s) => esc(s).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noreferrer">$1</a>').replace(/\n/g, "<br>");

const state = {
  boot: null, user: Number(localStorage.getItem("fa_user") || 1), tab: "inbox",
  view: localStorage.getItem("fa_view") || "alle", q: "", list: [], counts: {}, current: null, currentId: null,
  noteMode: false, listTimer: null,
};

async function api(pad, body, method) {
  const opts = { method: method || (body ? "POST" : "GET"), headers: { "X-User-Id": String(state.user) } };
  if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(pad, opts);
  let data = {};
  try { data = await r.json(); } catch (e) { data = { error: "geen JSON" }; }
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast" + (err ? " err" : "");
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.add("hidden"), err ? 5000 : 2500);
}

function modal(html, onMount) {
  const m = $("#modal"), c = $("#modal-card");
  c.innerHTML = html; m.classList.remove("hidden");
  $$("[data-close]", c).forEach((b) => b.onclick = closeModal);
  if (onMount) onMount(c);
}
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

function ago(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z"), diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "nu"; if (diff < 3600) return Math.round(diff / 60) + " min"; if (diff < 86400) return Math.round(diff / 3600) + " u";
  if (diff < 7 * 86400) return Math.round(diff / 86400) + " d";
  return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short" });
}
function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleString("nl-NL", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
}
const euro = (n) => "€" + Number(n || 0).toFixed(2).replace(".", ",");
const intentLabel = (k) => (state.boot?.intents[k]?.label) || k || "—";
const CHAN = { email: "E-mail", instagram: "Instagram", facebook: "Facebook", tiktok: "TikTok", shopify: "Shopify" };
const CHAN_LETTER = { email: "@", instagram: "I", facebook: "f", tiktok: "T", shopify: "S" };
const PRIO = { low: "Laag", normal: "Normaal", high: "Hoog", critical: "Kritiek" };
const SENT = { positive: "Positief", neutral: "Neutraal", negative: "Negatief" };
const AISTAT = { none: "—", processing: "AI bezig…", analyzed: "AI geanalyseerd", drafted: "AI-concept klaar", asked_info: "AI vraagt info",
  auto_answered: "AI beantwoord", handover: "Mens nodig", closed: "AI gesloten", ignored: "AI genegeerd", error: "AI-fout", draft_sent: "Concept verstuurd", answered_by_human: "Door mens beantwoord" };
const FIN = { PAID: "Betaald", PENDING: "In behandeling", REFUNDED: "Terugbetaald", PARTIALLY_REFUNDED: "Deels terugbetaald", VOIDED: "Geannuleerd", AUTHORIZED: "Geautoriseerd" };
const FUL = { FULFILLED: "Verzonden", UNFULFILLED: "Niet verzonden", PARTIALLY_FULFILLED: "Deels verzonden", IN_PROGRESS: "In behandeling", ON_HOLD: "On hold" };
const RET = { NO_RETURN: null, RETURN_REQUESTED: "Retour aangevraagd", IN_PROGRESS: "Retour onderweg", RETURNED: "Retour ontvangen" };

function avatar(c) {
  const naam = c.customer_name || c.name || "?";
  const init = naam.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  return `<div class="avatar">${c.avatar_url ? `<img src="${esc(c.avatar_url)}" alt="">` : esc(init)}<span class="chan ${esc(c.channel)}">${CHAN_LETTER[c.channel] || "?"}</span></div>`;
}

// ---------------------------------------------------------------------------
// Bootstrap, tabs, users, live
// ---------------------------------------------------------------------------
async function boot() {
  state.boot = await api("/api/bootstrap");
  state.counts = state.boot.counts;
  const us = $("#user-select");
  us.innerHTML = state.boot.users.map((u) => `<option value="${u.id}" ${u.id === state.user ? "selected" : ""}>${esc(u.name)}</option>`).join("");
  us.onchange = () => { state.user = Number(us.value); localStorage.setItem("fa_user", us.value); loadList(); if (state.currentId) openConversation(state.currentId); };
  const b = $("#ai-badge"); b.textContent = state.boot.agent_mode === "claude" ? "AI: Claude" : "AI: mock (geen sleutel)";
  b.className = "badge " + state.boot.agent_mode;
  renderViews();
  loadList();
  connectLive();
}

$("#tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  showTab(b.dataset.tab);
});
const TABS = ["inbox", "dashboard", "voorraad", "leren", "regels", "kennis", "instellingen"];

function showTab(tab, viaAdres) {
  if (!TABS.includes(tab)) tab = "inbox";
  state.tab = tab;
  $$("#tabs button").forEach((x) => x.classList.toggle("active", x.dataset.tab === tab));
  $$(".tab").forEach((x) => x.classList.toggle("active", x.id === "tab-" + tab));
  // Het adres meeschrijven, zodat elke tab een eigen link heeft die je kunt
  // bewaren of doorsturen. Komt de wissel juist ván het adres (terugknop), dan
  // niet nog eens terugschrijven.
  if (!viaAdres) {
    const nieuw = tab === "inbox" ? location.pathname : location.pathname + "#" + tab;
    if (location.pathname + location.hash !== nieuw) history.pushState({ tab }, "", nieuw);
  }
  ({ dashboard: renderDashboard, voorraad: renderVoorraad, leren: renderLeren, regels: renderRegels, kennis: renderKennis, instellingen: renderInstellingen })[tab]?.();
}

// Terug- en vooruitknop van de browser laten de tabs volgen.
window.addEventListener("popstate", () => showTab((location.hash || "#inbox").slice(1), true));

function connectLive() {
  const dot = $("#live-dot");
  const es = new EventSource("/events");
  es.onopen = () => dot.classList.add("on");
  es.onerror = () => dot.classList.remove("on");
  es.onmessage = (ev) => {
    let d = {}; try { d = JSON.parse(ev.data); } catch (e) { return; }
    clearTimeout(state.listTimer); state.listTimer = setTimeout(loadList, 400);
    if (d.conversation_id && d.conversation_id === state.currentId) {
      if (d.event === "ai-processing") { const t = $("#ai-status-inline"); if (t) t.textContent = "AI bezig…"; }
      else openConversation(state.currentId, true);
    }
    if (d.event === "message-created" && d.data?.new_ticket) toast("Nieuw gesprek binnengekomen");
  };
}

// ---------------------------------------------------------------------------
// Views + lijst
// ---------------------------------------------------------------------------
const VIEWS = [
  ["Inbox", [["alle", "Alle"], ["nieuw", "Nieuw"], ["mijn", "Mijn tickets"], ["ai_bezig", "AI bezig"], ["ai_opgelost", "AI opgelost"], ["mens_nodig", "Mens nodig"], ["high", "High priority"], ["goedkeuring", "Goedkeuring nodig"]]],
  ["Categorie", [["groep:retouren", "Retouren"], ["groep:verzending", "Verzending"], ["groep:orderproblemen", "Orderproblemen"], ["groep:productvragen", "Productvragen"], ["groep:klachten", "Klachten"], ["social", "Social"]]],
  ["Kanaal", [["kanaal:email", "E-mail"], ["kanaal:instagram", "Instagram"], ["kanaal:facebook", "Facebook"], ["kanaal:tiktok", "TikTok"]]],
  ["Overig", [["snoozed", "Gesnoozed"], ["afgehandeld", "Afgehandeld"], ["spam", "Spam"]]],
];
function renderViews() {
  const c = state.counts || {};
  // Smal scherm: dezelfde views als dropdown boven de lijst.
  let sel = $("#view-select");
  if (!sel) { sel = document.createElement("select"); sel.id = "view-select"; sel.className = "view-select"; $(".list-head").before(sel); sel.onchange = () => { state.view = sel.value; localStorage.setItem("fa_view", state.view); renderViews(); loadList(); }; }
  sel.innerHTML = VIEWS.map(([kop, items]) => `<optgroup label="${kop}">` + items.map(([k, l]) => `<option value="${k}" ${state.view === k ? "selected" : ""}>${l}${c[k] != null && c[k] !== "" ? " (" + c[k] + ")" : ""}</option>`).join("") + "</optgroup>").join("");
  $("#views").innerHTML = VIEWS.map(([kop, items]) => `<h4>${kop}</h4>` + items.map(([k, l]) => {
    const n = c[k] ?? (k.startsWith("kanaal:") ? "" : 0);
    const hot = (k === "mens_nodig" || k === "high" || k === "goedkeuring") && n > 0;
    return `<div class="view ${state.view === k ? "active" : ""} ${hot ? "hot" : ""}" data-view="${k}"><span>${l}</span>${n !== "" ? `<span class="count">${n}</span>` : ""}</div>`;
  }).join("")).join("");
  $$("#views .view").forEach((v) => v.onclick = () => { state.view = v.dataset.view; localStorage.setItem("fa_view", state.view); renderViews(); loadList(); });
}

let searchTimer;
$("#search").addEventListener("input", (e) => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.q = e.target.value.trim(); loadList(); }, 250); });

async function loadList() {
  if (state.view === "goedkeuring") return loadActionsList();
  try {
    const d = await api(`/api/conversations?view=${encodeURIComponent(state.view)}&q=${encodeURIComponent(state.q)}`);
    state.list = d.items; state.counts = d.counts; renderViews(); renderList();
  } catch (e) { toast("Lijst laden mislukt: " + e.message, true); }
}

function renderList() {
  const el = $("#conv-list");
  if (!state.list.length) { el.innerHTML = `<div class="empty">Niets in deze weergave</div>`; return; }
  el.innerHTML = state.list.map((c) => {
    const pills = [];
    if (c.priority !== "normal") pills.push(`<span class="pill prio-${c.priority}">${PRIO[c.priority]}</span>`);
    if (c.intent) pills.push(`<span class="pill">${esc(intentLabel(c.intent))}</span>`);
    if (c.sentiment && c.sentiment !== "neutral") pills.push(`<span class="pill sent-${c.sentiment}">${SENT[c.sentiment]}</span>`);
    if (c.needs_human) pills.push(`<span class="pill human">Mens nodig</span>`);
    else if (c.ai_status && c.ai_status !== "none") pills.push(`<span class="pill ai">${AISTAT[c.ai_status] || c.ai_status}</span>`);
    if (c.n_actions) pills.push(`<span class="pill action">${c.n_actions} goedkeuring</span>`);
    if (c.order_name) pills.push(`<span class="pill order">${esc(c.order_name)}</span>`);
    if (c.status !== "open") pills.push(`<span class="pill status-${c.status}">${c.status === "closed" ? "Gesloten" : c.status === "snoozed" ? "Gesnoozed" : "Spam"}</span>`);
    const prev = (c.last_author === "customer" ? "" : "↩ ") + (c.last_body || "");
    return `<div class="conv ${c.id === state.currentId ? "active" : ""}" data-id="${c.id}">${avatar(c)}<div>
      <div class="conv-top"><span class="conv-name">${esc(c.customer_name || "Onbekend")}</span><span class="conv-time">${ago(c.last_message_at)}</span></div>
      <div class="conv-subject">${esc(c.subject || "(geen onderwerp)")}</div>
      <div class="conv-preview">${esc(prev)}</div>
      <div class="conv-meta">${pills.join("")}</div></div></div>`;
  }).join("");
  $$("#conv-list .conv").forEach((x) => x.onclick = () => openConversation(Number(x.dataset.id)));
}

async function loadActionsList() {
  const d = await api("/api/actions?status=pending");
  state.counts = (await api("/api/bootstrap")).counts; renderViews();
  const el = $("#conv-list");
  el.innerHTML = d.items.length ? d.items.map((a) => `<div class="conv" data-id="${a.conversation_id}"><div class="avatar">!</div><div>
      <div class="conv-top"><span class="conv-name">${esc(a.customer_name || "?")}</span><span class="conv-time">${ago(a.created_at)}</span></div>
      <div class="conv-subject">${esc(a.description)}</div><div class="conv-meta"><span class="pill action">Wacht op goedkeuring</span><span class="pill">${esc(CHAN[a.channel])}</span></div></div></div>`).join("")
    : `<div class="empty">Geen acties die goedkeuring nodig hebben</div>`;
  $$("#conv-list .conv").forEach((x) => x.onclick = () => openConversation(Number(x.dataset.id)));
}

// ---------------------------------------------------------------------------
// Gesprek
// ---------------------------------------------------------------------------
async function openConversation(id, silent) {
  state.currentId = id;
  $("#tab-inbox").classList.add("has-conv");
  $$("#conv-list .conv").forEach((x) => x.classList.toggle("active", Number(x.dataset.id) === id));
  try {
    const d = await api(`/api/conversations/${id}`);
    // Bij een live-update (silent) mag een half getypt antwoord nooit verloren gaan.
    const oud = $("#composer-text");
    const typed = silent && oud && id === state.current?.conversation?.id ? oud.value : null;
    const wasFocused = silent && document.activeElement === oud;
    const cursor = wasFocused ? oud.selectionStart : null;
    state.current = d; renderThread(d); renderSide(d);
    const nieuw = $("#composer-text");
    if (typed !== null && nieuw && typed.trim() && typed !== nieuw.value && !state.noteMode) {
      nieuw.value = typed;
      if (wasFocused) { nieuw.focus(); try { nieuw.setSelectionRange(cursor, cursor); } catch (e) { /* ok */ } }
    } else if (wasFocused && nieuw) nieuw.focus();
  } catch (e) { toast("Gesprek laden mislukt: " + e.message, true); }
}

function renderThread(d) {
  const c = d.conversation, an = d.analysis, draft = d.draft, users = state.boot.users;
  const pane = $("#thread-pane");
  const isComment = c.via === "comment";
  const aiCard = an ? `<div class="ai-card ${c.needs_human ? "human" : ""}">
      <h4>AI-analyse ${an.is_mock ? '<span class="pill">mock</span>' : `<span class="pill ai">${esc(an.model || "")}</span>`} <span class="faint">${fmtDate(an.created_at)}</span></h4>
      <div class="ai-grid">
        <div><b>Categorie</b>${esc(intentLabel(an.intent))} <span class="faint">${Math.round((an.intent_confidence || 0) * 100)}%</span></div>
        <div><b>Prioriteit</b><span class="pill prio-${c.priority}">${PRIO[c.priority]}</span></div>
        <div><b>Sentiment</b><span class="pill sent-${an.sentiment}">${SENT[an.sentiment] || an.sentiment}</span></div>
        <div><b>Taal</b>${esc(an.language || "?")}</div>
        <div><b>Volgende stap</b>${{ answer: "AI kan antwoorden", ask_info: "Eerst info vragen", handover: "Mens nodig", close: "Sluiten, geen antwoord nodig", snooze: "Wachten op klant" }[an.next_action] || an.next_action}</div>
        <div><b>Niveau</b>${esc(d.level || "—")}</div>
        ${an.missing_info?.length ? `<div><b>Ontbreekt</b>${an.missing_info.map((m) => esc(state.boot.missing_info[m] || m)).join(", ")}</div>` : ""}
        ${an.escalation_flags?.length ? `<div><b>Vlaggen</b>${an.escalation_flags.map((f) => `<span class="pill human">${esc(state.boot.escalation_flags[f] || f)}</span>`).join(" ")}</div>` : ""}
        ${an.order_ref ? `<div><b>Order</b>${esc(an.order_ref)}</div>` : ""}
      </div>
      ${c.needs_human ? `<div class="ai-summary"><b style="color:var(--danger)">Mens nodig:</b> ${esc(c.needs_human_reason || an.needs_human_reason || "")}</div>` : ""}
      <div class="ai-summary">${esc(an.summary || "")}</div>
      <div class="ai-reason">${esc(an.reasoning || "")}</div>
    </div>` : `<div class="ai-card"><h4>AI-analyse</h4><div class="muted">Nog niet geanalyseerd. <button class="small" id="btn-analyze">Nu analyseren</button></div></div>`;

  const actions = (d.actions || []).map((a) => `<div class="action-card ${a.status}">
      <b>${esc(a.description)}</b>
      ${a.status === "pending" ? `<button class="primary small" data-act="${a.id}" data-approve="1">Goedkeuren</button><button class="small" data-act="${a.id}" data-approve="0">Afwijzen</button>`
        : `<span class="pill">${{ executed: "Uitgevoerd", approved: "Goedgekeurd", rejected: "Afgewezen", failed: "Mislukt" }[a.status]}${a.result ? " · " + esc(String(a.result).slice(0, 80)) : ""}</span>`}
    </div>`).join("");

  const msgs = d.messages.map((m) => {
    const cls = m.kind === "note" ? "note" : m.kind === "system" ? "system" : (m.direction === "in" ? "in" : "out " + (m.author_type === "ai" ? "ai" : ""));
    const wie = m.kind === "note" ? `Interne notitie · ${esc(m.author_name || m.author_type)}` : m.direction === "in" ? esc(m.author_name || "Klant") : esc(m.author_name || (m.author_type === "ai" ? "AI" : "Medewerker"));
    const att = (m.attachments || []).map((a) => `<span class="attach">📎 ${esc(a.name || a.content_type || "bijlage")}</span>`).join(" ");
    const st = m.status === "failed" ? ` <span class="pill human">niet verzonden: ${esc(m.error || "")}</span>` : m.source?.mock ? ` <span class="pill">mock verzonden</span>` : "";
    return `<div class="msg ${cls} ${m.status === "failed" ? "failed" : ""}"><div class="msg-meta"><span>${wie}</span><span>${fmtDate(m.sent_at || m.created_at)}</span>${st}</div>${linkify(m.body_text)}${att ? "<div>" + att + "</div>" : ""}</div>`;
  }).join("");

  const verifier = draft?.verifier || {};
  const vHtml = draft ? (verifier.ok === false ? `<div class="verifier bad">⚠ Controle: ${(verifier.issues || []).map(esc).join(" · ") || "let op"}</div>` : `<div class="verifier ok">✓ Controle: geen beloftes, onderbouwd, beleid ok</div>`) : "";
  const composerHead = draft ? `<span>AI-concept ${draft.kind === "ask_info" ? "(vervolgvraag)" : ""} ${draft.is_mock ? '<span class="pill">mock</span>' : ""}${draft.used_knowledge?.length ? ` · kennis: ${draft.used_knowledge.map(esc).join(", ")}` : ""}</span>
      <span class="draft-tools"><button class="ghost small" id="fb-up" title="Goed concept">👍</button><button class="ghost small" id="fb-down" title="Slecht concept">👎</button><button class="ghost small" id="btn-reject">Concept weg</button></span>`
    : `<span>${c.needs_human ? "Mens nodig — schrijf zelf een antwoord of vraag de AI om een concept" : "Geen AI-concept"}</span>`;

  pane.innerHTML = `
    <div class="thread-head">
      <div class="thread-title"><button class="ghost small btn-back" id="btn-back">← Lijst</button>${esc(c.subject || "(geen onderwerp)")} <span class="pill">${CHAN[c.channel]} · ${c.via}</span>
        ${c.status !== "open" ? `<span class="pill status-${c.status}">${c.status === "closed" ? "Gesloten" : c.status === "snoozed" ? "Gesnoozed tot " + fmtDate(c.snooze_until) : "Spam"}</span>` : ""}
        ${(c.tags || []).map((t) => `<span class="pill tag">${esc(t)} <span data-untag="${esc(t)}" style="cursor:pointer">×</span></span>`).join("")}
        <button class="ghost small" id="btn-tag">+ tag</button></div>
      <div class="thread-sub"><span>#${c.id}</span><span>aangemaakt ${fmtDate(c.created_at)}</span><span id="ai-status-inline">${AISTAT[c.ai_status] || ""}</span>
        <span>Categorie: <select id="sel-intent">${Object.entries(state.boot.intents).map(([k, v]) => `<option value="${k}" ${k === c.intent ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select></span>
        <span>Prioriteit: <select id="sel-prio">${Object.entries(PRIO).map(([k, v]) => `<option value="${k}" ${k === c.priority ? "selected" : ""}>${v}</option>`).join("")}</select></span>
        <span>Toegewezen: <select id="sel-assign"><option value="">niemand</option>${users.map((u) => `<option value="${u.id}" ${u.id === c.assignee_id ? "selected" : ""}>${esc(u.name)}</option>`).join("")}</select></span>
      </div>
      <div class="thread-actions">
        <button class="small" id="btn-regen">✨ AI opnieuw</button>
        <button class="small" id="btn-escalate">⚑ Escaleren</button>
        ${c.needs_human ? `<button class="small" id="btn-resolve-human">✓ Ik pak dit op</button>` : ""}
        <button class="small" id="btn-snooze">⏰ Snoozen</button>
        ${c.status === "open" ? `<button class="small" id="btn-close">Sluiten</button>` : `<button class="small" id="btn-reopen">Heropenen</button>`}
        ${c.status !== "spam" ? `<button class="small ghost" id="btn-spam">Spam</button>` : ""}
        ${isComment ? `<button class="small" id="btn-private">✉ Privé antwoorden (DM)</button><button class="small" id="btn-hide">🙈 Comment verbergen</button>` : ""}
        ${c.order_name ? `<button class="small" id="btn-action">⚙ Actie op ${esc(c.order_name)}…</button>` : ""}
      </div>
    </div>
    <div class="thread-body" id="thread-body">${aiCard}${actions}${msgs}</div>
    <div class="composer ${state.noteMode ? "note-mode" : ""}" id="composer">
      ${vHtml}
      <div class="composer-head">${state.noteMode ? "<span>Interne notitie (klant ziet dit niet)</span>" : composerHead}
        <span><button class="ghost small" id="btn-note-toggle">${state.noteMode ? "← Terug naar antwoord" : "Interne notitie"}</button></span></div>
      <textarea id="composer-text" placeholder="${state.noteMode ? "Notitie voor collega's…" : "Schrijf een antwoord…"}">${esc(state.noteMode ? "" : (draft?.body || ""))}</textarea>
      <div class="composer-foot">
        ${state.noteMode ? `<button class="primary" id="btn-send-note">Notitie opslaan</button>` :
          `<button class="primary" id="btn-send">Versturen</button><button id="btn-send-close">Versturen & sluiten</button>
           ${draft ? `<span class="faint">Bewerk de tekst gerust; wij leren van je aanpassingen.</span>` : ""}`}
        <span class="faint" style="margin-left:auto">${isComment ? "Publiek antwoord op de comment" : "Antwoord gaat via " + CHAN[c.channel] + (state.boot.integrations[c.channel === "email" ? "gmail" : c.channel === "tiktok" ? "tiktok" : c.channel === "shopify" ? "gmail" : "meta"] ? "" : " (mock: niet gekoppeld)")}</span>
      </div>
    </div>`;
  const body = $("#thread-body"); body.scrollTop = body.scrollHeight;
  bindThread(d, draft);
}

function bindThread(d, draft) {
  const id = d.conversation.id, c = d.conversation;
  const send = async (close) => {
    const txt = $("#composer-text").value.trim(); if (!txt) return toast("Leeg antwoord", true);
    try { await api(`/api/conversations/${id}/reply`, { body: txt, draft_id: draft?.id || null, close }); toast(close ? "Verstuurd en gesloten" : "Verstuurd"); openConversation(id); }
    catch (e) { toast("Versturen mislukt: " + e.message, true); }
  };
  $("#btn-send")?.addEventListener("click", () => send(false));
  $("#btn-send-close")?.addEventListener("click", () => send(true));
  $("#btn-send-note")?.addEventListener("click", async () => {
    const txt = $("#composer-text").value.trim(); if (!txt) return;
    await api(`/api/conversations/${id}/note`, { body: txt }); state.noteMode = false; openConversation(id);
  });
  $("#btn-note-toggle").onclick = () => { state.noteMode = !state.noteMode; renderThread(d); };
  $("#btn-back").onclick = () => { $("#tab-inbox").classList.remove("has-conv"); };
  $("#composer-text").addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") (state.noteMode ? $("#btn-send-note") : $("#btn-send"))?.click(); });
  $("#btn-regen").onclick = async () => { $("#btn-regen").disabled = true; toast("AI maakt een nieuw concept…"); try { await api(`/api/conversations/${id}/regenerate`, {}); openConversation(id); } catch (e) { toast(e.message, true); } };
  $("#btn-analyze")?.addEventListener("click", () => $("#btn-regen").click());
  $("#btn-escalate").onclick = () => modal(`<h3>Escaleren</h3><div class="form-row"><label>Reden</label><input type="text" id="m-reason" placeholder="Waarom moet een mens dit doen?"></div>
      <div class="form-row"><label>Toewijzen aan</label><select id="m-assignee"><option value="">niemand</option>${state.boot.users.map((u) => `<option value="${u.id}">${esc(u.name)}</option>`).join("")}</select></div>
      <div class="modal-foot"><button data-close>Annuleren</button><button class="primary" id="m-ok">Escaleren</button></div>`, (m) => {
    $("#m-ok", m).onclick = async () => { await api(`/api/conversations/${id}/escalate`, { reason: $("#m-reason", m).value, assignee_id: Number($("#m-assignee", m).value) || null }); closeModal(); openConversation(id); };
  });
  $("#btn-resolve-human")?.addEventListener("click", async () => { await api(`/api/conversations/${id}/resolve-human`, {}); openConversation(id); });
  $("#btn-snooze").onclick = () => modal(`<h3>Snoozen</h3><p class="muted">Het gesprek verdwijnt uit de inbox en komt automatisch terug (of eerder als de klant reageert).</p>
      <div class="form-row"><label>Duur</label><select id="m-hours"><option value="1">1 uur</option><option value="4">4 uur</option><option value="24" selected>1 dag</option><option value="72">3 dagen</option><option value="168">1 week</option></select></div>
      <div class="modal-foot"><button data-close>Annuleren</button><button class="primary" id="m-ok">Snoozen</button></div>`, (m) => {
    $("#m-ok", m).onclick = async () => { await api(`/api/conversations/${id}/status`, { status: "snoozed", snooze_hours: Number($("#m-hours", m).value) }); closeModal(); loadList(); openConversation(id); };
  });
  $("#btn-close")?.addEventListener("click", async () => { await api(`/api/conversations/${id}/status`, { status: "closed" }); toast("Gesloten"); loadList(); openConversation(id); });
  $("#btn-reopen")?.addEventListener("click", async () => { await api(`/api/conversations/${id}/status`, { status: "open" }); loadList(); openConversation(id); });
  $("#btn-spam")?.addEventListener("click", async () => { if (!confirm("Als spam markeren?")) return; await api(`/api/conversations/${id}/status`, { status: "spam" }); loadList(); openConversation(id); });
  $("#sel-intent").onchange = async (e) => { await api(`/api/conversations/${id}/intent`, { intent: e.target.value }); toast("Categorie aangepast (de AI leert hiervan)"); loadList(); };
  $("#sel-prio").onchange = async (e) => { await api(`/api/conversations/${id}/priority`, { priority: e.target.value }); loadList(); openConversation(id, true); };
  $("#sel-assign").onchange = async (e) => { await api(`/api/conversations/${id}/assign`, { assignee_id: Number(e.target.value) || null }); loadList(); };
  $("#btn-tag").onclick = async () => { const t = prompt("Tag:"); if (t) { await api(`/api/conversations/${id}/tag`, { tag: t }); openConversation(id); } };
  $$("[data-untag]").forEach((x) => x.onclick = async () => { await api(`/api/conversations/${id}/tag`, { tag: x.dataset.untag, remove: true }); openConversation(id); });
  $$("[data-act]").forEach((b) => b.onclick = async () => {
    b.disabled = true;
    try { const r = await api(`/api/actions/${b.dataset.act}/decide`, { approve: b.dataset.approve === "1" }); toast(r.status === "executed" ? "Uitgevoerd" : r.status === "rejected" ? "Afgewezen" : "Mislukt: " + (r.error || "")); }
    catch (e) { toast(e.message, true); }
    openConversation(id); loadList();
  });
  $("#fb-up")?.addEventListener("click", async () => { await api(`/api/drafts/${draft.id}/feedback`, { feedback: "up" }); toast("Bedankt, opgeslagen"); });
  $("#fb-down")?.addEventListener("click", () => modal(`<h3>Wat is er mis met dit concept?</h3>
      <div class="form-row"><label>Reden</label><select id="m-r"><option value="feiten">Feiten kloppen niet</option><option value="toon">Toon klopt niet</option><option value="beleid">Beleid/kennis ontbreekt</option><option value="te lang">Te lang</option><option value="anders">Anders</option></select></div>
      <div class="modal-foot"><button data-close>Annuleren</button><button class="primary" id="m-ok">Opslaan</button></div>`, (m) => {
    $("#m-ok", m).onclick = async () => { await api(`/api/drafts/${draft.id}/feedback`, { feedback: "down", reason: $("#m-r", m).value }); closeModal(); toast("Feedback opgeslagen"); };
  }));
  $("#btn-reject")?.addEventListener("click", async () => { await api(`/api/drafts/${draft.id}/reject`, {}); openConversation(id); });
  $("#btn-private")?.addEventListener("click", () => modal(`<h3>Privé antwoorden via DM</h3><p class="muted">De klant krijgt een DM als reactie op de comment (kan binnen 7 dagen, één bericht).</p>
      <textarea id="m-body" rows="5">Hoi! Stuur ons even je ordernummer, dan zoeken we het direct voor je uit.</textarea>
      <div class="modal-foot"><button data-close>Annuleren</button><button class="primary" id="m-ok">Versturen</button></div>`, (m) => {
    $("#m-ok", m).onclick = async () => { try { await api(`/api/conversations/${id}/private-reply`, { body: $("#m-body", m).value }); closeModal(); toast("DM verstuurd"); openConversation(id); } catch (e) { toast(e.message, true); } };
  }));
  $("#btn-hide")?.addEventListener("click", async () => { await api(`/api/conversations/${id}/actions`, { type: "hide_comment", params: { hide: true } }); toast("Voorgesteld: comment verbergen — keur goed in het gesprek"); openConversation(id); });
  $("#btn-action")?.addEventListener("click", () => actionModal(d));
}

function actionModal(d) {
  const c = d.conversation, o = d.order;
  modal(`<h3>Actie op ${esc(c.order_name)}</h3><p class="muted">De actie wordt eerst als voorstel in het gesprek gezet en pas uitgevoerd na goedkeuring.</p>
    <div class="form-row"><label>Actie</label><select id="m-type"><option value="cancel_order">Order annuleren (+ terugbetalen)</option><option value="refund">Bedrag terugbetalen</option><option value="address_change">Verzendadres wijzigen</option><option value="tag_order">Order taggen</option></select></div>
    <div id="m-fields"></div>
    <div class="modal-foot"><button data-close>Annuleren</button><button class="primary" id="m-ok">Voorstel toevoegen</button></div>`, (m) => {
    const f = $("#m-fields", m), t = $("#m-type", m);
    const render = () => {
      f.innerHTML = { cancel_order: `<div class="form-row"><label>Terugbetalen</label><select id="m-refund"><option value="1">Ja, ${euro(o?.total)}</option><option value="0">Nee</option></select></div>`,
        refund: `<div class="form-row"><label>Bedrag</label><input type="number" step="0.01" id="m-amount" value="${o ? o.total : 0}"></div><div class="form-row"><label>Reden</label><input type="text" id="m-note"></div>`,
        address_change: `<div class="form-row"><label>Straat + nr</label><input type="text" id="m-a1" value="${esc(o?.shipping_address?.address1 || "")}"></div><div class="form-row"><label>Postcode</label><input type="text" id="m-zip" value="${esc(o?.shipping_address?.zip || "")}"></div><div class="form-row"><label>Plaats</label><input type="text" id="m-city" value="${esc(o?.shipping_address?.city || "")}"></div>`,
        tag_order: `<div class="form-row"><label>Tags</label><input type="text" id="m-tags" placeholder="bv. klacht, opnieuw-verzonden"></div>` }[t.value];
    };
    t.onchange = render; render();
    $("#m-ok", m).onclick = async () => {
      const type = t.value, params = { order_name: c.order_name };
      if (type === "cancel_order") { params.refund = $("#m-refund", m).value === "1"; params.restock = true; }
      if (type === "refund") { params.amount = Number($("#m-amount", m).value); params.note = $("#m-note", m).value; }
      if (type === "address_change") params.address = { address1: $("#m-a1", m).value, zip: $("#m-zip", m).value, city: $("#m-city", m).value, country: "NL" };
      if (type === "tag_order") params.tags = $("#m-tags", m).value.split(",").map((s) => s.trim()).filter(Boolean);
      await api(`/api/conversations/${c.id}/actions`, { type, params }); closeModal(); openConversation(c.id); loadList();
    };
  });
}

// ---------------------------------------------------------------------------
// Zijbalk: klant + Shopify + fulfillment + historie
// ---------------------------------------------------------------------------
function renderSide(d) {
  const k = d.customer, o = d.order, ful = d.fulfillment;
  const pane = $("#side-pane");
  const orderCard = (x, current) => {
    const tr = x.tracking || {};
    return `<div class="order-card ${current ? "current" : ""}" data-order="${esc(x.name)}">
      <div class="order-head"><span>${esc(x.name)}</span><span>${euro(x.total)}</span></div>
      <div class="faint">${fmtDate(x.created_at)}</div>
      <div class="order-items">${(x.line_items || []).map((li) => `${li.quantity}× ${esc(li.title)}${li.size ? " – " + esc(li.size) : ""}${li.color ? " " + esc(li.color) : ""}`).join("<br>")}</div>
      <div class="status-line">
        <span class="pill ${x.financial_status === "PAID" ? "sent-positive" : x.financial_status?.includes("REFUND") ? "order" : "prio-high"}">${FIN[x.financial_status] || x.financial_status || "?"}</span>
        <span class="pill ${x.fulfillment_status === "FULFILLED" ? "sent-positive" : ""}">${FUL[x.fulfillment_status] || x.fulfillment_status || "?"}</span>
        ${RET[x.return_status] ? `<span class="pill order">${RET[x.return_status]}</span>` : ""}
        ${x.cancelled_at ? `<span class="pill human">Geannuleerd</span>` : ""}
      </div>
      ${tr.number ? `<div class="kv"><b>${esc(tr.company || "Vervoerder")}</b><span>${esc((tr.status || "").replace(/_/g, " ").toLowerCase())}</span><b>Tracking</b><span>${tr.url ? `<a href="${esc(tr.url)}" target="_blank" rel="noreferrer">${esc(tr.number)}</a>` : esc(tr.number)}</span>${tr.estimated_delivery ? `<b>Verwacht</b><span>${esc(String(tr.estimated_delivery).slice(0, 10))}</span>` : ""}</div>` : ""}
      ${(x.refunds || []).length ? `<div class="faint">Refunds: ${x.refunds.map((r) => euro(r.amount) + " (" + String(r.at || "").slice(0, 10) + ")").join(", ")}</div>` : ""}
      ${x._email_mismatch ? `<div class="mismatch">⚠ Dit ordernummer hoort bij een ander e-mailadres dan de afzender. Deel geen details vóór je de identiteit hebt gecheckt.</div>` : ""}
    </div>`;
  };
  const tl = ful && ful.events?.length ? `<ul class="timeline">${ful.events.slice(-8).map((e, i, arr) => `<li class="${i === arr.length - 1 ? "now" : ""}"><b>${esc(e.label || e.stage)}</b> <span class="faint">${fmtDate(e.occurred_at || e.at)}</span>${e.detail && e.detail !== e.label ? ` <span class="faint">${esc(e.detail)}</span>` : ""}</li>`).join("")}</ul>` : "";

  pane.innerHTML = `
    <div class="card">
      <h4>Klant ${k ? `<a href="#" id="lnk-cust" class="faint">alle gesprekken</a>` : ""}</h4>
      ${k ? `<div class="cust-name">${esc(k.name || "Onbekend")}</div>
        <div class="kv">${k.email ? `<b>E-mail</b><span>${esc(k.email)}</span>` : ""}${k.phone ? `<b>Telefoon</b><span>${esc(k.phone)}</span>` : ""}
        ${(d.identities || []).filter((i) => i.channel !== "email").map((i) => `<b>${CHAN[i.channel]}</b><span>@${esc(i.handle || i.external_id)}</span>`).join("")}
        <b>Orders</b><span>${k.orders_count || (d.orders || []).length}</span><b>Besteed</b><span>${euro(k.total_spent || (d.orders || []).reduce((s, x) => s + (x.total || 0), 0))}</span>
        ${(k.tags || []).length ? `<b>Tags</b><span>${k.tags.map((t) => `<span class="pill tag">${esc(t)}</span>`).join(" ")}</span>` : ""}</div>
        ${k.note ? `<div class="faint" style="margin-top:6px">${esc(k.note)}</div>` : ""}` : `<div class="muted">Niet herkend in Shopify. Vraag om het e-mailadres van de bestelling.</div>`}
    </div>
    <div class="card">
      <h4>Shopify ${state.boot.integrations.shopify ? "" : '<span class="pill">mock-data</span>'}</h4>
      ${o ? orderCard(o, true) : `<div class="muted">Geen order gekoppeld${d.order_refs?.length ? " (genoemd: " + d.order_refs.map(esc).join(", ") + ", niet gevonden)" : ""}.</div>`}
      ${ful ? `<div style="margin-top:8px"><b class="faint">Fulfillment</b> <span class="pill ${ful.stage === "problem" ? "human" : ful.stage === "delivered" ? "sent-positive" : "order"}">${esc(ful.label)}</span> <span class="faint">${ful.source === "fulfillment" ? "fulfillmentpartij" : "afgeleid uit Shopify"}</span>${tl}</div>` : ""}
      ${(d.orders || []).filter((x) => !o || x.name !== o.name).length ? `<h4 style="margin-top:12px">Eerdere orders</h4>${d.orders.filter((x) => !o || x.name !== o.name).slice(0, 5).map((x) => orderCard(x, false)).join("")}` : ""}
    </div>
    ${(d.previous_conversations || []).length ? `<div class="card"><h4>Eerdere gesprekken</h4><ul class="linklist">${d.previous_conversations.map((p) => `<li data-conv="${p.id}"><span class="pill">${CHAN[p.channel]}</span> ${esc(p.subject || "")} <span class="faint">${ago(p.created_at)} · ${p.status}</span></li>`).join("")}</ul></div>` : ""}
    ${(d.knowledge_hits || []).length ? `<div class="card"><h4>Relevante kennis</h4><ul class="linklist">${d.knowledge_hits.map((h) => `<li data-kb="${esc(h.slug)}"><span class="dot ${h.complete ? "ok" : "todo"}"></span> ${esc(h.title)}${h.complete ? "" : ' <span class="faint">(nog TODO)</span>'}</li>`).join("")}</ul></div>` : ""}
    <div class="card"><h4>Logboek <button class="ghost small" id="btn-events">toon</button></h4><div class="events hidden" id="events">${(d.events || []).map((e) => `<div>${fmtDate(e.created_at)} · <b>${esc(e.type)}</b> <span class="faint">${esc(e.actor_type)}</span>${e.data?.rules ? " · " + esc(e.data.rules.join(", ")) : ""}${e.data?.error ? " · " + esc(e.data.error) : ""}</div>`).join("")}</div></div>`;
  $("#btn-events").onclick = () => $("#events").classList.toggle("hidden");
  $$("[data-conv]", pane).forEach((x) => x.onclick = () => openConversation(Number(x.dataset.conv)));
  $$("[data-kb]", pane).forEach((x) => x.onclick = () => { showTab("kennis"); setTimeout(() => $(`.kb-item[data-slug="${x.dataset.kb}"]`)?.click(), 200); });
  $("#lnk-cust")?.addEventListener("click", (e) => { e.preventDefault(); $("#search").value = k.email || k.name; state.q = k.email || k.name; state.view = "alle"; renderViews(); loadList(); });
  $$("[data-order]", pane).forEach((x) => x.ondblclick = async () => { const r = await api(`/api/orders/${encodeURIComponent(x.dataset.order)}`); modal(`<h3>${esc(r.order.name)}</h3><pre class="mono" style="white-space:pre-wrap">${esc(JSON.stringify(r.order, null, 2))}</pre><div class="modal-foot"><button data-close>Sluiten</button></div>`); });
}

// ---------------------------------------------------------------------------
// Testbericht
// ---------------------------------------------------------------------------
$("#btn-test").onclick = () => modal(`<h3>Testbericht laten binnenkomen</h3><p class="muted">Doet alsof een klant iets stuurt; loopt door de hele pipeline (klant → order → AI → regels → concept).</p>
  <div class="form-row"><label>Kanaal</label><select id="m-ch"><option value="email">E-mail</option><option value="instagram">Instagram DM</option><option value="instagram:comment">Instagram comment</option><option value="facebook">Facebook Messenger</option><option value="facebook:comment">Facebook comment</option><option value="tiktok:comment">TikTok comment</option></select></div>
  <div class="form-row"><label>Naam</label><input type="text" id="m-name" value="Sophie Jansen"></div>
  <div class="form-row"><label>E-mail</label><input type="text" id="m-email" value="sophie.jansen@voorbeeld.nl"></div>
  <div class="form-row"><label>Onderwerp</label><input type="text" id="m-subj" value="Waar blijft mijn bestelling?"></div>
  <div class="form-row"><label>Bericht</label><textarea id="m-text" rows="4">Hoi, waar blijft mijn bestelling #1801? Ik heb nog niets ontvangen.</textarea></div>
  <div class="modal-foot"><button data-close>Annuleren</button><button class="primary" id="m-ok">Versturen</button></div>`, (m) => {
  $("#m-ok", m).onclick = async () => {
    const [channel, via] = $("#m-ch", m).value.split(":");
    $("#m-ok", m).disabled = true;
    try {
      const r = await api("/api/simulate", { channel, via: via || (channel === "email" ? "email" : "dm"), name: $("#m-name", m).value, email: channel === "email" ? $("#m-email", m).value : null, subject: $("#m-subj", m).value, text: $("#m-text", m).value });
      closeModal(); toast("Binnengekomen en verwerkt"); loadList(); if (r.conversation_id) openConversation(r.conversation_id);
    } catch (e) { toast(e.message, true); $("#m-ok", m).disabled = false; }
  };
});

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
async function renderDashboard() {
  const el = $("#tab-dashboard"); el.innerHTML = `<div class="empty">Laden…</div>`;
  const d = await api("/api/dashboard"), k = d.kpis, I = d.info;
  const kpi = (key, v, extra, cls) => `<div class="kpi ${cls || ""}"><button class="info-btn" data-info="${key}">i</button><div class="v">${v ?? "—"}</div><div class="l">${esc(I[key]?.titel || key)}${extra ? ` <span class="faint">${extra}</span>` : ""}</div></div>`;
  const maxK = Math.max(1, ...Object.values(d.per_kanaal));
  const maxDag = Math.max(1, ...d.per_dag.map((x) => Math.max(x.nieuw, x.gesloten)));
  el.innerHTML = `<h2>Vandaag</h2><p class="lead">${new Date().toLocaleDateString("nl-NL", { weekday: "long", day: "numeric", month: "long" })} · alle cijfers hebben een ⓘ met de formule</p>
    <div class="kpis">${kpi("nieuw_vandaag", k.nieuw_vandaag)}${kpi("open", k.open)}${kpi("ai_afgehandeld_vandaag", k.ai_afgehandeld_vandaag, "", "good")}${kpi("mens_nodig", k.mens_nodig, "", k.mens_nodig ? "hot" : "")}${kpi("high_priority", k.high_priority, "", k.high_priority ? "warn" : "")}
      ${kpi("responstijd", k.responstijd_min != null ? (k.responstijd_min >= 60 ? (k.responstijd_min / 60).toFixed(1) + " u" : k.responstijd_min + " min") : "—")}${kpi("ai_acceptatie", k.ai_acceptatie_pct != null ? k.ai_acceptatie_pct + "%" : "—", `van ${k.ai_concepten_totaal}`)}${kpi("ai_aangepast", k.ai_aangepast)}</div>
    <div class="grid2">
      <div class="panel"><h3>ACTIE NODIG <span class="pill human">${d.actie_nodig.length}</span></h3>
        ${d.actie_nodig.length ? d.actie_nodig.slice(0, 25).map((a) => `<div class="actie" data-conv="${a.conversation_id}"><span class="type ${a.type}">${{ mens_nodig: "Mens nodig", goedkeuring: "Goedkeuren", prioriteit: "Prioriteit", verzendfout: "Verzendfout" }[a.type]}</span><span><b>${esc(a.titel)}</b><br><span class="faint">${esc(a.klant || "")} · ${esc(a.reden)}</span></span><span class="faint">${ago(a.sinds)}</span></div>`).join("") : `<div class="muted">Niets — alles is opgepakt 🎉</div>`}
      </div>
      <div>
        <div class="panel"><h3>Per kanaal (7 dagen) <button class="info-btn" style="position:static" data-info="per_kanaal">i</button></h3>${Object.entries(d.per_kanaal).map(([n, v]) => `<div class="bar-row"><span>${esc(n)}</span><span><span class="bar" style="width:${Math.round(100 * v / maxK)}%"></span></span><span class="num">${v}</span></div>`).join("") || '<div class="muted">Nog geen data</div>'}</div>
        <div class="panel"><h3>Nieuw vs gesloten per dag (14 dagen)</h3><div class="sparkbars">${d.per_dag.map((x) => `<div style="height:${Math.round(100 * x.nieuw / maxDag)}%" title="${x.dag}: ${x.nieuw} nieuw, ${x.gesloten} gesloten"><span>${x.nieuw || ""}</span></div>`).join("")}</div><div class="spark-labels">${d.per_dag.map((x) => `<div>${x.dag.slice(8)}</div>`).join("")}</div></div>
        <div class="panel"><h3>Backlog per leeftijd <button class="info-btn" style="position:static" data-info="backlog">i</button></h3>${Object.entries(d.backlog).map(([n, v]) => `<div class="bar-row"><span>${n}</span><span><span class="bar" style="width:${Math.round(100 * v / Math.max(1, ...Object.values(d.backlog)))}%;background:${n.startsWith(">") ? "var(--danger)" : n.startsWith("1-3") ? "var(--warn)" : "var(--accent)"}"></span></span><span class="num">${v}</span></div>`).join("")}</div>
      </div>
    </div>
    <div class="panel"><h3>Per categorie (7 dagen) <button class="info-btn" style="position:static" data-info="per_categorie">i</button></h3>
      <table class="t"><thead><tr><th>Categorie</th><th>Groep</th><th class="num">Aantal</th></tr></thead><tbody>${d.per_categorie.map((c) => `<tr class="click" data-view="groep:${esc(state.boot.intents[c.intent]?.group || "algemeen")}"><td>${esc(c.label)}</td><td class="muted">${esc(c.group)}</td><td class="num">${c.n}</td></tr>`).join("")}</tbody></table></div>`;
  $$("[data-info]", el).forEach((b) => b.onclick = () => { const i = I[b.dataset.info]; modal(`<h3>${esc(i.titel)}</h3><p><b>Formule</b><br><code class="mono">${esc(i.formule)}</code></p><p>${esc(i.uitleg)}</p><div class="modal-foot"><button data-close>Sluiten</button></div>`); });
  $$("[data-conv]", el).forEach((x) => x.onclick = () => { showTab("inbox"); openConversation(Number(x.dataset.conv)); });
  $$("tr[data-view]", el).forEach((x) => x.onclick = () => { state.view = x.dataset.view; showTab("inbox"); renderViews(); loadList(); });
}

// ---------------------------------------------------------------------------
// Leren
// ---------------------------------------------------------------------------
async function renderLeren() {
  const el = $("#tab-leren"); el.innerHTML = `<div class="empty">Laden…</div>`;
  const d = await api("/api/learning");
  const la = d.laatste_analyse;
  el.innerHTML = `<h2>Leren van onze correcties</h2><p class="lead">Elk verstuurd antwoord wordt vergeleken met het AI-concept. Zo zien we welke categorieën klaar zijn voor meer automatisering en waar de AI nog fouten maakt.</p>
    <div class="grid2">
      <div class="panel"><h3>Per categorie</h3><table class="t"><thead><tr><th>Categorie</th><th class="num">Antwoorden</th><th class="num">Aangepast</th><th class="num">Overeenkomst</th><th class="num">Escalaties</th><th>Status</th></tr></thead><tbody>
        ${d.per_intent.map((p) => `<tr><td>${esc(p.label)}</td><td class="num">${p.n}</td><td class="num">${p.edit_pct}%</td><td class="num">${p.gem_similarity != null ? Math.round(p.gem_similarity * 100) + "%" : "—"}</td><td class="num">${p.escalated}</td><td>${p.klaar_voor_auto ? '<span class="pill sent-positive">klaar voor auto-antwoord</span>' : p.n < 5 ? '<span class="pill">te weinig data</span>' : '<span class="pill prio-high">nog controleren</span>'}</td></tr>`).join("") || "<tr><td colspan=6 class='muted'>Nog geen data</td></tr>"}</tbody></table>
        <div class="faint" style="margin-top:8px">Feedback op concepten: 👍 ${d.feedback.up || 0} · 👎 ${d.feedback.down || 0}</div></div>
      <div class="panel"><h3>AI-analyse van de correcties <button class="primary small" id="btn-analyze-learn">Analyseer nu</button></h3>
        <div id="learn-out">${la ? renderLearnOut(la) : '<div class="muted">Nog niet uitgevoerd. Klik op "Analyseer nu" (met Claude: echte analyse; mock: alleen tellingen).</div>'}</div></div>
    </div>
    <div class="panel"><h3>Laatste antwoorden: concept vs verstuurd</h3>
      ${d.records.slice(0, 30).map((r) => `<div style="padding:10px 0;border-bottom:1px solid var(--line)"><div style="display:flex;gap:8px;align-items:center;margin-bottom:6px"><span class="pill">${esc(CHAN[r.channel] || r.channel)}</span><span class="pill">${esc(intentLabel(r.ai_intent))}</span>${r.edited ? `<span class="pill prio-high">aangepast (${esc(r.diff_summary)})</span>` : r.ai_draft ? '<span class="pill sent-positive">ongewijzigd verstuurd</span>' : '<span class="pill">zonder concept</span>'}${r.feedback ? `<span class="pill">${r.feedback === "up" ? "👍" : "👎 " + esc(r.feedback_reason || "")}</span>` : ""}<span class="faint" style="margin-left:auto">${fmtDate(r.created_at)}</span></div>
        <div class="faint" style="margin-bottom:6px"><b>Klant:</b> ${esc((r.customer_question || "").slice(0, 200))}</div>
        <div class="diff"><div><b class="faint">AI-concept</b><br>${nl(r.ai_draft || "—")}</div><div><b class="faint">Verstuurd (${esc(r.sent_by)})</b><br>${nl(r.final_answer || "")}</div></div></div>`).join("") || '<div class="muted">Nog geen antwoorden verstuurd.</div>'}
    </div>`;
  $("#btn-analyze-learn").onclick = async (e) => { e.target.disabled = true; e.target.textContent = "Bezig…"; try { const r = await api("/api/learning/analyze", {}); $("#learn-out").innerHTML = renderLearnOut(r); } catch (err) { toast(err.message, true); } e.target.disabled = false; e.target.textContent = "Analyseer nu"; };
}
function renderLearnOut(a) {
  const lijst = (arr) => arr?.length ? `<ul>${arr.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : '<div class="faint">—</div>';
  return `<div class="faint">${a.is_mock ? "Mock-analyse (tellingen)" : "Claude"} · ${fmtDate(a.generated_at)}</div>
    <p><b>Vaak terugkerende vragen</b>${lijst(a.recurring_questions)}</p>
    <p><b>Vaak aangepast</b>${a.frequently_edited?.length ? `<ul>${a.frequently_edited.map((x) => `<li><b>${esc(intentLabel(x.intent))}:</b> ${esc(x.what_changes)}</li>`).join("")}</ul>` : '<div class="faint">—</div>'}</p>
    <p><b>Klaar voor meer automatisering</b>${lijst(a.ready_for_more_automation?.map(intentLabel))}</p>
    <p><b>Waar de AI fouten maakt</b>${lijst(a.ai_mistakes)}</p>
    <p><b>Ontbrekende kennis (voorstellen)</b>${a.missing_knowledge?.length ? `<ul>${a.missing_knowledge.map((x) => `<li><b>${esc(x.title)}</b><br><span class="faint">${esc(x.proposed_text)}</span></li>`).join("")}</ul>` : '<div class="faint">—</div>'}</p>
    <p><b>Automatiseringsideeën</b>${lijst(a.automation_ideas)}</p>`;
}

// ---------------------------------------------------------------------------
// Regels
// ---------------------------------------------------------------------------
async function renderRegels() {
  const el = $("#tab-regels"); el.innerHTML = `<div class="empty">Laden…</div>`;
  const d = await api("/api/rules");
  const opt = (arr, v, labels) => arr.map((x) => `<option value="${esc(x)}" ${x === v ? "selected" : ""}>${esc(labels?.[x] || x)}</option>`).join("");
  // Een lijst met één element krijgt een slotkomma, zodat hij bij opslaan weer een lijst wordt.
  const valStr = (v) => Array.isArray(v) ? (v.length === 1 ? v[0] + "," : v.join(", ")) : (v === true ? "ja" : v === false ? "nee" : (v ?? ""));
  const ruleHtml = (r) => `<div class="rule" data-id="${r.id || ""}"><div class="rule-head"><button class="switch ${r.enabled ? "on" : ""}" data-toggle title="Aan/uit"></button><b>${esc(r.name)}</b><span class="faint">${r.hits || 0}× gevuurd · volgorde ${r.priority}</span><button class="ghost small" data-open>bewerken</button></div>
    <div class="rule-body">
      <div class="form-row"><label>Naam</label><input type="text" data-f="name" value="${esc(r.name)}"></div>
      <div class="form-row"><label>Uitleg</label><input type="text" data-f="description" value="${esc(r.description || "")}"></div>
      <div class="form-row"><label>Volgorde</label><input type="number" data-f="priority" value="${r.priority}" style="width:90px"></div>
      <div style="margin:8px 0 4px"><b>ALS</b> <span class="faint">(alle voorwaarden moeten kloppen)</span></div>
      <div data-conds>${(r.conditions || []).map((c) => condRow(c)).join("")}</div><button class="small" data-add-cond>+ voorwaarde</button>
      <div style="margin:8px 0 4px"><b>DAN</b></div>
      <div data-acts>${(r.actions || []).map((a) => actRow(a)).join("")}</div><button class="small" data-add-act>+ actie</button>
      <div class="modal-foot"><button class="danger small" data-del>Verwijderen</button><button class="primary small" data-save>Opslaan</button></div>
    </div></div>`;
  const condRow = (c) => `<div class="rule-row"><select data-c="field">${opt(d.fields, c.field)}</select><select data-c="op">${opt(d.ops, c.op || "is")}</select><input type="text" data-c="value" value="${esc(valStr(c.value))}" placeholder="waarde (lijst met komma's)"><button class="ghost small" data-rm>×</button></div>`;
  const actRow = (a) => `<div class="rule-row act"><select data-a="type">${opt(d.action_types, a.type)}</select><input type="text" data-a="value" value="${esc(valStr(a.value))}" placeholder="waarde"><button class="ghost small" data-rm>×</button></div>`;
  el.innerHTML = `<h2>Regels</h2><p class="lead">ALS (voorwaarden) DAN (acties). Regels draaien na elke AI-analyse, op volgorde. Velden: intent, sentiment, priority, channel, escalation_flags, order_found, tracking_available, customer_orders_count… Acties: set_priority, needs_human, allow_ai (max. niveau), add_tag, close, mark_spam…</p>
    <button class="primary" id="btn-new-rule">+ Nieuwe regel</button><div id="rules" style="margin-top:12px">${d.items.map(ruleHtml).join("")}</div>`;
  const bind = (rule) => {
    const id = rule.dataset.id;
    $("[data-open]", rule).onclick = () => rule.classList.toggle("open");
    $("[data-toggle]", rule).onclick = async (e) => { e.target.classList.toggle("on"); if (id) await api(`/api/rules/${id}`, { enabled: e.target.classList.contains("on") ? 1 : 0 }); };
    $("[data-add-cond]", rule).onclick = () => { $("[data-conds]", rule).insertAdjacentHTML("beforeend", condRow({ field: "intent", op: "is", value: "" })); bindRm(rule); };
    $("[data-add-act]", rule).onclick = () => { $("[data-acts]", rule).insertAdjacentHTML("beforeend", actRow({ type: "add_tag", value: "" })); bindRm(rule); };
    $("[data-save]", rule).onclick = async () => {
      const parse = (s, op) => { const t = s.trim(); if (t === "ja" || t === "true") return true; if (t === "nee" || t === "false") return false; if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t); if (t.includes(",") || ["in", "not_in", "contains_any"].includes(op)) return t.split(",").map((x) => x.trim()).filter(Boolean); return t; };
      const body = { name: $("[data-f=name]", rule).value, description: $("[data-f=description]", rule).value, priority: Number($("[data-f=priority]", rule).value),
        conditions: $$("[data-conds] .rule-row", rule).map((row) => ({ field: $("[data-c=field]", row).value, op: $("[data-c=op]", row).value, value: parse($("[data-c=value]", row).value, $("[data-c=op]", row).value) })),
        actions: $$("[data-acts] .rule-row", rule).map((row) => ({ type: $("[data-a=type]", row).value, value: parse($("[data-a=value]", row).value) })) };
      await api(id ? `/api/rules/${id}` : "/api/rules", body); toast("Regel opgeslagen"); renderRegels();
    };
    $("[data-del]", rule).onclick = async () => { if (!id) return rule.remove(); if (confirm("Regel verwijderen?")) { await api(`/api/rules/${id}`, null, "DELETE"); renderRegels(); } };
    bindRm(rule);
  };
  const bindRm = (rule) => $$("[data-rm]", rule).forEach((b) => b.onclick = () => b.parentElement.remove());
  $$("#rules .rule").forEach(bind);
  $("#btn-new-rule").onclick = () => { $("#rules").insertAdjacentHTML("afterbegin", ruleHtml({ name: "Nieuwe regel", enabled: 1, priority: 100, conditions: [{ field: "intent", op: "is", value: "" }], actions: [{ type: "add_tag", value: "" }] })); const r = $("#rules .rule"); r.classList.add("open"); bind(r); };
}

// ---------------------------------------------------------------------------
// Kennisbank
// ---------------------------------------------------------------------------
async function renderKennis(selectSlug) {
  const el = $("#tab-kennis");
  const d = await api("/api/knowledge");
  el.innerHTML = `<h2>Kennisbank</h2><p class="lead">Wat de AI mag weten en gebruiken. Bestanden staan in <code>kb/</code>; bewerken kan hier of in een editor. Staat er nog <b>TODO</b> in, dan gebruikt de AI dat artikel niet als bron.</p>
    <div class="kb-list"><div class="panel">${d.items.map((a) => `<div class="kb-item" data-slug="${esc(a.slug)}"><span>${esc(a.title)}</span><span class="dot ${a.is_complete ? "ok" : "todo"}" title="${a.is_complete ? "compleet" : "bevat TODO"}"></span></div>`).join("")}</div>
    <div class="panel" id="kb-editor"><div class="muted">Kies een artikel</div></div></div>`;
  const open = (slug) => {
    const a = d.items.find((x) => x.slug === slug); if (!a) return;
    $$(".kb-item", el).forEach((x) => x.classList.toggle("active", x.dataset.slug === slug));
    $("#kb-editor").innerHTML = `<h3>${esc(a.title)} <span class="faint">kb/${esc(a.slug)}.md</span></h3><textarea id="kb-text" rows="24">${esc(a.body)}</textarea><div class="modal-foot"><span class="faint" style="margin-right:auto">bijgewerkt ${fmtDate(a.updated_at)}</span><button class="primary" id="kb-save">Opslaan</button></div>`;
    $("#kb-save").onclick = async () => { await api(`/api/knowledge/${slug}`, { body: $("#kb-text").value }); toast("Opgeslagen"); renderKennis(slug); };
  };
  $$(".kb-item", el).forEach((x) => x.onclick = () => open(x.dataset.slug));
  if (selectSlug) open(selectSlug);
}

// ---------------------------------------------------------------------------
// Instellingen
// ---------------------------------------------------------------------------
async function renderInstellingen() {
  const el = $("#tab-instellingen");
  const b = await api("/api/bootstrap"), st = await api("/api/integrations");
  state.boot = b;
  const lvl = b.level_order;
  el.innerHTML = `<h2>Instellingen</h2><p class="lead">Hoe ver mag de AI gaan, per categorie. Begin voorzichtig: "concept" betekent dat wij altijd op Versturen klikken.</p>
    <div class="grid2"><div class="panel"><h3>Automatiseringsniveau per categorie</h3>
      ${lvl.map((l) => `<div class="faint">${esc(b.levels[l])}</div>`).join("")}
      <div style="margin-top:10px">${Object.entries(b.intents).map(([k, v]) => `<div class="level-row"><span>${esc(v.label)}</span><span class="faint">${esc(v.description)}</span><select data-level="${k}">${lvl.map((l) => `<option value="${l}" ${b.intent_levels[k] === l ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>`).join("")}</div>
      <div class="modal-foot"><button class="primary" id="save-levels">Niveaus opslaan</button></div></div>
    <div>
      <div class="panel"><h3>AI</h3>
        <div class="form-row"><label>Modus</label><select id="s-mode"><option value="auto" ${b.settings.ai_mode === "auto" ? "selected" : ""}>Automatisch (Claude als er een sleutel is)</option><option value="claude" ${b.settings.ai_mode === "claude" ? "selected" : ""}>Claude</option><option value="mock" ${b.settings.ai_mode === "mock" ? "selected" : ""}>Mock (geen kosten)</option></select></div>
        <div class="form-row"><label>Nu actief</label><span class="pill ${b.agent_mode}">${b.agent_mode}</span></div>
        <div class="form-row"><label>Max. niveau (globaal)</label><select id="s-global">${lvl.map((l) => `<option value="${l}" ${b.settings.global_max_level === l ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
        <div class="form-row"><label>Auto-versturen</label><label><input type="checkbox" id="s-auto" ${b.settings.auto_send_enabled ? "checked" : ""}> AI mag zelf versturen bij niveau 3+ én goedgekeurde controle</label></div>
        <div class="form-row"><label>Tone of voice</label><textarea id="s-tone" rows="3">${esc(b.settings.tone || "")}</textarea></div>
        <div class="modal-foot"><button class="primary" id="save-ai">Opslaan</button></div></div>
      <div class="panel"><h3>Koppelingen</h3>
        ${Object.entries(st.integrations).map(([k, v]) => `<div class="integ"><span class="dot ${v ? "ok" : "todo"}"></span><b>${esc({ anthropic: "Anthropic (AI)", shopify: "Shopify", gmail: "E-mail (Gmail)", meta: "Meta (Instagram/Facebook)", tiktok: "TikTok", fulfillment: "Fulfillment" }[k] || k)}</b><span class="faint">${v ? "gekoppeld" : "niet gekoppeld → mock-modus, zie OPENSTAANDE_ZAKEN.md"}</span></div>`).join("")}
        <div class="faint" style="margin-top:8px">Database ${st.db_mb} MB · wachtrij ${esc(JSON.stringify(st.queue))}</div></div>
      <div class="panel"><h3>Kennisbank-status</h3>${st.knowledge.map((k) => `<div class="integ"><span class="dot ${k.complete ? "ok" : "todo"}"></span>${esc(k.title)}<span class="faint">${k.complete ? "compleet" : "nog TODO's"}</span></div>`).join("")}</div>
    </div></div>`;
  $("#save-levels").onclick = async () => { const levels = {}; $$("[data-level]", el).forEach((s) => levels[s.dataset.level] = s.value); await api("/api/settings", { intent_levels: levels }); toast("Niveaus opgeslagen"); };
  $("#save-ai").onclick = async () => { await api("/api/settings", { ai_mode: $("#s-mode").value, global_max_level: $("#s-global").value, auto_send_enabled: $("#s-auto").checked, tone: $("#s-tone").value }); toast("Opgeslagen"); boot(); renderInstellingen(); };
}

// ---------------------------------------------------------------------------
// Versleepbare kolommen
// ---------------------------------------------------------------------------
// Elke verticale lijn in de inbox is een .splitter-kolom in het grid. Slepen zet de breedte
// als inline variabele op #tab-inbox, wat sterker is dan de media-query. Dubbelklikken haalt
// de inline waarde weg, zodat de standaard uit style.css weer geldt.
const KOLOMMEN = {
  views: { var: "--kol-views", min: 140, standaard: 200 },
  lijst: { var: "--kol-lijst", min: 250, standaard: 340 },
  zij:   { var: "--kol-zij",   min: 250, standaard: 340, omgekeerd: true },
};
const MIN_GESPREK = 320;   // het gesprek in het midden moet leesbaar blijven

function kolomBreedtes() {
  const s = getComputedStyle($("#tab-inbox"));
  const lees = (naam) => parseFloat(s.getPropertyValue(naam)) || 0;
  return { views: lees("--kol-views"), lijst: lees("--kol-lijst"), zij: lees("--kol-zij"), lijn: lees("--kol-lijn") };
}

function zetKolom(kol, px) {
  const def = KOLOMMEN[kol], vak = $("#tab-inbox"), b = kolomBreedtes();
  // Hoeveel ruimte is er over als deze kolom groeit? Het gesprek mag niet onder MIN_GESPREK.
  const anderen = Object.keys(KOLOMMEN).filter((k) => k !== kol && $(`.splitter[data-kol="${k}"]`)?.offsetParent)
    .reduce((t, k) => t + b[k], 0);
  const max = vak.clientWidth - anderen - 3 * b.lijn - MIN_GESPREK;
  const breedte = Math.round(Math.max(def.min, Math.min(px, Math.max(def.min, max))));
  vak.style.setProperty(def.var, breedte + "px");
  return breedte;
}

function bewaarKolommen() {
  const vak = $("#tab-inbox"), uit = {};
  for (const [kol, def] of Object.entries(KOLOMMEN)) {
    const v = vak.style.getPropertyValue(def.var);
    if (v) uit[kol] = parseFloat(v);
  }
  localStorage.setItem("fa_kolommen", JSON.stringify(uit));
}

function initSplitters() {
  try {
    const bewaard = JSON.parse(localStorage.getItem("fa_kolommen") || "{}");
    for (const [kol, px] of Object.entries(bewaard)) if (KOLOMMEN[kol] && px > 0) zetKolom(kol, px);
  } catch (e) { /* onleesbaar opgeslagen waarde: standaardbreedtes */ }

  $$(".splitter").forEach((sp) => {
    const kol = sp.dataset.kol, def = KOLOMMEN[kol];
    if (!def) return;

    sp.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const startX = e.clientX, startBreedte = kolomBreedtes()[kol];
      sp.setPointerCapture(e.pointerId);
      sp.classList.add("bezig"); document.body.classList.add("sleept");

      const beweeg = (ev) => {
        const delta = ev.clientX - startX;
        zetKolom(kol, startBreedte + (def.omgekeerd ? -delta : delta));
      };
      const stop = () => {
        sp.removeEventListener("pointermove", beweeg);
        sp.removeEventListener("pointerup", stop);
        sp.removeEventListener("pointercancel", stop);
        sp.classList.remove("bezig"); document.body.classList.remove("sleept");
        bewaarKolommen();
      };
      sp.addEventListener("pointermove", beweeg);
      sp.addEventListener("pointerup", stop);
      sp.addEventListener("pointercancel", stop);
    });

    sp.addEventListener("dblclick", () => {
      $("#tab-inbox").style.removeProperty(def.var);
      bewaarKolommen();
      toast("Standaardbreedte hersteld");
    });
  });
}

// ---------------------------------------------------------------------------
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
  if (e.target.matches("input, textarea, select")) return;
  if (state.tab !== "inbox" || !state.list.length) return;
  const idx = state.list.findIndex((c) => c.id === state.currentId);
  if (e.key === "j" || e.key === "ArrowDown") { const n = state.list[Math.min(idx + 1, state.list.length - 1)]; if (n) openConversation(n.id); }
  if (e.key === "k" || e.key === "ArrowUp") { const n = state.list[Math.max(idx - 1, 0)]; if (n) openConversation(n.id); }
  if (e.key === "r" && state.currentId) { $("#composer-text")?.focus(); e.preventDefault(); }
  if (e.key === "c" && state.currentId) $("#btn-close")?.click();
});

initSplitters();
boot()
  // Staat er een tab in het adres (#voorraad), open die dan meteen — zo werkt
  // een doorgestuurde link naar één tab ook echt.
  .then(() => { const h = (location.hash || "").slice(1); if (h && h !== "inbox") showTab(h, true); })
  .catch((e) => { toast("Opstarten mislukt: " + e.message, true); console.error(e); });
