/* Farmers Atelier — i-knopjes, sorteerbare tabellen en de Voorraad-tab.
   Apart van app.js gehouden: app.js gaat over de inbox, dit gaat over voorraad.
   Leunt op $, $$, esc, api en toast uit app.js, dat eerder geladen wordt. */
"use strict";

// ---------------------------------------------------------------------------
// i-knopjes met wolkjes  (dashboard-standaarden §1)
// ---------------------------------------------------------------------------
// Een title=-attribuut is niet genoeg: dat komt traag, is niet op te maken en
// valt weg in een tabel die horizontaal scrolt. Het wolkje hangt daarom in één
// vast venster boven de pagina. Muis erover toont het, klikken zet het vast.

function iknop(uitleg, kop, bron) {
  const kaal = (t) => esc(String(t ?? "").replace(/<[^>]+>/g, "").trim());
  return '<span class="doelwrap"><button class="ibol" type="button"' +
    ` data-kop="${kaal(kop)}" data-tekst="${kaal(uitleg)}" data-bron="${kaal(bron)}"` +
    ' aria-label="Uitleg">i</button></span>';
}

function wolkToon(knop) {
  const venster = document.getElementById("wolkvenster");
  const kop = knop.dataset.kop, tekst = knop.dataset.tekst, bron = knop.dataset.bron;
  venster.innerHTML = (kop ? `<span class="wfase">${kop}</span>` : "") +
    `<span class="wrij">${tekst || ""}</span>` +
    (bron ? `<span class="wbron">Bron: ${bron}</span>` : "");
  venster.classList.remove("hidden");
  const r = knop.getBoundingClientRect(), v = venster.getBoundingClientRect();
  let links = r.left + r.width / 2 - v.width / 2;
  links = Math.max(8, Math.min(links, window.innerWidth - v.width - 8));
  let boven = r.top - v.height - 8;
  if (boven < 8) boven = r.bottom + 8;          // past niet boven? dan eronder
  venster.style.left = links + "px";
  venster.style.top = boven + "px";
}

function wolkVerberg() {
  const v = document.getElementById("wolkvenster");
  if (!v.classList.contains("vast")) v.classList.add("hidden");
}

document.addEventListener("mouseover", (e) => {
  const knop = e.target.closest && e.target.closest(".ibol");
  if (knop && !document.getElementById("wolkvenster").classList.contains("vast")) wolkToon(knop);
});
document.addEventListener("mouseout", (e) => {
  if (e.target.closest && e.target.closest(".ibol")) wolkVerberg();
});
document.addEventListener("click", (e) => {
  const venster = document.getElementById("wolkvenster");
  const knop = e.target.closest && e.target.closest(".ibol");
  if (knop) {
    e.preventDefault(); e.stopPropagation();
    const zelfde = venster._knop === knop && venster.classList.contains("vast");
    $$(".ibol.vast").forEach((k) => k.classList.remove("vast"));
    venster.classList.remove("vast");
    if (zelfde) { venster.classList.add("hidden"); venster._knop = null; return; }
    venster._knop = knop; knop.classList.add("vast");
    wolkToon(knop); venster.classList.add("vast");
    return;
  }
  if (venster.classList.contains("vast") && !(e.target.closest && e.target.closest("#wolkvenster"))) {
    $$(".ibol.vast").forEach((k) => k.classList.remove("vast"));
    venster.classList.remove("vast"); venster.classList.add("hidden"); venster._knop = null;
  }
});

// ---------------------------------------------------------------------------
// Sorteerbare tabel (§2: boven 8 rijen sorteerbaar, hoog→laag én laag→hoog)
// ---------------------------------------------------------------------------
function maakSorteerbaar(tabel) {
  const koppen = $$("th.sorteer", tabel);
  koppen.forEach((th, i) => {
    th.onclick = () => {
      const oplopend = th.dataset.richting !== "op";
      koppen.forEach((k) => {
        k.classList.remove("actief"); delete k.dataset.richting;
        const p = k.querySelector(".pijl"); if (p) p.textContent = "↕";
      });
      th.classList.add("actief");
      th.dataset.richting = oplopend ? "op" : "af";
      const pijl = th.querySelector(".pijl"); if (pijl) pijl.textContent = oplopend ? "↑" : "↓";

      const body = tabel.querySelector("tbody");
      // Een model met zijn maatrijen eronder moet als één blok verhuizen,
      // anders raken de maten los van hun model.
      const blokken = [];
      $$("tbody > tr", tabel).forEach((tr) => {
        if (tr.classList.contains("maatrij")) {
          if (blokken.length) blokken[blokken.length - 1].kinderen.push(tr);
        } else if (!tr.classList.contains("totaal")) {
          blokken.push({ hoofd: tr, kinderen: [] });
        }
      });
      const waarde = (tr) => {
        const c = tr.children[i];
        if (!c) return "";
        const ruw = c.dataset.sort !== undefined ? c.dataset.sort : c.textContent.trim();
        const n = parseFloat(String(ruw).replace(/\./g, "").replace(",", ".").replace(/[^\d.-]/g, ""));
        return isNaN(n) ? String(ruw).toLowerCase() : n;
      };
      blokken.sort((a, b) => {
        const x = waarde(a.hoofd), y = waarde(b.hoofd);
        if (typeof x === "number" && typeof y === "number") return oplopend ? x - y : y - x;
        return oplopend ? String(x).localeCompare(String(y)) : String(y).localeCompare(String(x));
      });
      const totaal = tabel.querySelector("tbody > tr.totaal");
      blokken.forEach((b) => { body.appendChild(b.hoofd); b.kinderen.forEach((k) => body.appendChild(k)); });
      if (totaal) body.appendChild(totaal);
    };
  });
}

// ---------------------------------------------------------------------------
// Voorraad-tab
// ---------------------------------------------------------------------------
const eur = (n) => "€ " + Number(n || 0).toLocaleString("nl-NL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const getal = (n) => Number(n || 0).toLocaleString("nl-NL");
// Nul is een streepje, geen 0 — niets is niet nul (§2).
const cel = (n) => (n === null || n === undefined) ? '<span class="faint">–</span>' : (n === 0 ? "–" : getal(n));

let VOORRAAD = null;

async function renderVoorraad() {
  const el = $("#tab-voorraad");
  el.innerHTML = '<p class="muted">Laden…</p>';
  try { VOORRAAD = await api("/api/voorraad"); }
  catch (e) { el.innerHTML = `<p class="muted">Kon de voorraad niet laden: ${esc(e.message)}</p>`; return; }
  tekenVoorraad();
}

function tekenVoorraad() {
  const el = $("#tab-voorraad");
  const a = VOORRAAD.artikelen, r = VOORRAAD.retouren, k = VOORRAAD.kosten;
  const bronA = a.bron || "Excel", bronK = k.bron || "Innostock-offerte";

  // De drop: wat er werkelijk ligt en wat het waard is. Staat bovenaan, want dat
  // is het cijfer waar het om draait; de Excel-telling staat eronder als controle.
  const d = VOORRAAD.drop || {};
  const dropblok = !d.beschikbaar ? "" : `<div class="vk">
    <h3>Wat er ligt en wat het waard is
      ${iknop("Opgave van Wieger, peildatum " + (d.peildatum || "") + ". Dit zijn RETOUREN: teruggekomen bestellingen die opnieuw verkocht gaan worden. Geen nieuwe voorraad en geen restant van een inkooporder.", "Dropwaarde", d.bron || "opgave")}</h3>
    <div class="tabelbak"><table class="dtab"><thead><tr><th>Groep</th><th class="num">Aantal</th>
      <th class="num">Stukprijs</th><th class="num">Waarde</th></tr></thead><tbody>
      ${(d.regels || []).map((r) => `<tr><td>${esc(r.groep)}<div class="faint">${esc(r.toelichting || "")}</div></td>
        <td class="num">${getal(r.aantal)}</td><td class="num">${eur(r.stukprijs_eur)}</td>
        <td class="num">${eur(r.waarde_eur)}</td></tr>`).join("")}
      <tr class="totaal"><td>Totale dropwaarde</td><td class="num">${getal(d.totaal_stuks)}</td>
        <td></td><td class="num">${eur(d.totaal_waarde_eur)}</td></tr>
    </tbody></table></div>
    <div class="waarschuw" style="margin-top:12px"><b>De Excel telt anders.</b>
      Daarin staan ${getal((d.telling_excel || {}).shirts)} shirts en géén aantallen voor truien —
      een verschil van ${getal(d.regels[0].aantal - (d.telling_excel || {}).shirts)} stuks, plus de
      ${getal(d.regels[1].aantal)} truien die er helemaal niet in staan. De opgave hierboven is leidend;
      de tabellen hieronder komen uit de Excel en zijn dus onvolledig.
      <div style="margin-top:6px">De voorraadstanden in <b>Shopify</b> zijn evenmin bruikbaar: die staan
      op veel varianten negatief, omdat er meer verkocht is dan geregistreerd stond.</div></div>
  </div>`;

  const onbekend = a.varianten_zonder_voorraadgetal;
  const waarschuwing = onbekend ? `<div class="waarschuw"><b>Let op:</b> van ${getal(onbekend)} van de
    ${getal(a.totaal_varianten)} varianten staat géén voorraadgetal in de Excel — dat zijn de truien en
    de accessoires. Die tellen dus <b>niet</b> mee in het totaal hieronder. Zodra Shopify gekoppeld is
    komt de voorraad daarvandaan en klopt dit vanzelf.</div>` : "";

  const kpis = `<div class="vkpi">
      <div class="kaart"><div class="v">${getal((VOORRAAD.drop || {}).totaal_stuks || a.totaal_voorraad)}</div><div class="l">Stuks (retouren)
        ${iknop("Opgave van Wieger: circa 1.750 shirts en 400 truien, allemaal retouren. De Excel telt maar 1146 shirts en kent geen truien, dus die is onvolledig. De voorraad in Shopify staat negatief en is onbruikbaar.", "Stuks op voorraad", "opgave Wieger")}</div></div>
      <div class="kaart"><div class="v">${eur((VOORRAAD.drop || {}).totaal_waarde_eur || 0)}</div><div class="l">Dropwaarde
        ${iknop("Shirts tegen 25 euro en truien tegen 50 euro per stuk. Dit is verkoopwaarde, niet wat het opbrengt: van elk verkocht stuk gaat nog ruim 11 euro af aan fulfilment.", "Dropwaarde", "opgave Wieger")}</div></div>
      <div class="kaart"><div class="v">${getal(a.totaal_varianten)}</div><div class="l">Varianten
        ${iknop("Elke combinatie van model, kleur en maat telt als één variant. Bijna vijf maten per model gemiddeld.", "Varianten", bronA)}</div></div>
      <div class="kaart"><div class="v">${getal(r.aantal_zendingen)}</div><div class="l">Retourzendingen terug
        ${iknop("Het aantal unieke trackingnummers op het tabblad 'Gescande retouren': zoveel pakketten zijn er fysiek teruggekomen en gescand. Niet het aantal artikelen — in één pakket kunnen meerdere stuks zitten.", "Retourzendingen", bronA)}</div></div>
      <div class="kaart"><div class="v">${k.beschikbaar ? eur(k.per_stuk_ex_btw) : "–"}</div><div class="l">Kosten per retour
        ${iknop("Wat het kost om één teruggekomen artikel weer verkoopklaar te hebben en opnieuw te versturen: retourverwerking, inslag, opslag, pick & pack, verpakking en verzendlabel. Exclusief btw.", "Kosten per retour", bronK)}</div></div>
    </div>`;

  const groepen = Object.entries(a.per_groep).sort((x, y) => (y[1].voorraad || 0) - (x[1].voorraad || 0));
  const groeptabel = `<div class="vk"><h3>Per productgroep
      ${iknop("De drie tabbladen uit de Excel. Een streepje betekent dat er geen voorraadgetal is ingevuld — dat is iets anders dan nul op voorraad.", "Per productgroep", bronA)}</h3>
    <div class="tabelbak"><table class="dtab"><thead><tr><th>Groep</th><th class="num">Modellen</th>
      <th class="num">Varianten</th><th class="num">Op voorraad</th></tr></thead><tbody>
      ${groepen.map(([naam, g]) => `<tr${g.voorraad === null ? ' class="leegrij"' : ""}><td>${esc(naam)}</td>
        <td class="num">${cel(g.modellen)}</td><td class="num">${cel(g.varianten)}</td>
        <td class="num">${cel(g.voorraad)}</td></tr>`).join("")}
      <tr class="totaal"><td>Totaal</td>
        <td class="num">${getal(groepen.reduce((s, g) => s + g[1].modellen, 0))}</td>
        <td class="num">${getal(a.totaal_varianten)}</td><td class="num">${getal(a.totaal_voorraad)}</td></tr>
    </tbody></table></div></div>`;

  const maatwaarden = Object.values(a.per_maat);
  const maxMaat = maatwaarden.length ? Math.max.apply(null, maatwaarden) : 1;
  const maattabel = `<div class="vk"><h3>Per maat
      ${iknop("Alle voorraad opgeteld per maat, over alle modellen heen. Hiermee zie je of je scheef in je maten zit: veel M en L betekent dat de randmaten het eerst uitverkocht zijn.", "Per maat", bronA)}</h3>
    <div class="tabelbak"><table class="dtab"><thead><tr><th>Maat</th><th class="num">Stuks</th>
      <th class="num">Aandeel</th><th>Verdeling</th></tr></thead><tbody>
      ${Object.keys(a.per_maat).map((m) => {
        const n = a.per_maat[m];
        return `<tr><td>${esc(m)}</td><td class="num">${cel(n)}</td>
          <td class="num">${(n / a.totaal_voorraad * 100).toFixed(1).replace(".", ",")}%</td>
          <td><span class="balkje"><i style="width:${(n / maxMaat * 100).toFixed(1)}%"></i></span></td></tr>`;
      }).join("")}
      <tr class="totaal"><td>Totaal</td><td class="num">${getal(a.totaal_voorraad)}</td>
        <td class="num">100%</td><td></td></tr>
    </tbody></table></div></div>`;

  const rijen = a.modellen.map((m, i) => {
    const naam = m.kleur ? `${m.model} — ${m.kleur}` : m.model;
    const hoofd = `<tr class="klik" data-model="${i}">
      <td><span class="pijltje" data-pijl="${i}">›</span> ${esc(naam)}</td><td>${esc(m.groep)}</td>
      <td class="num" data-sort="${m.varianten}">${m.varianten}</td>
      <td class="num" data-sort="${m.voorraad === null ? -1 : m.voorraad}">${cel(m.voorraad)}</td></tr>`;
    const kinderen = m.maten.map((mt) => `<tr class="maatrij hidden" data-kind="${i}">
      <td>${esc(mt.maat || "onbekend")}</td><td class="faint">${esc(mt.sku || "")}</td><td></td>
      <td class="num">${cel(mt.voorraad)}</td></tr>`).join("");
    return hoofd + kinderen;
  }).join("");

  const modeltabel = `<div class="vk"><h3>Modellen
      ${iknop("Elk model met zijn kleur. Klik op een regel om de maten eronder uit te klappen; dan zie je per maat hoeveel er liggen. De kolomkoppen zijn sorteerbaar, hoog naar laag en andersom.", "Modellen", bronA)}</h3>
    <div class="instelrij"><button class="small" id="v-allesopen">Alles uitklappen</button>
      <button class="small" id="v-allesdicht">Alles inklappen</button>
      <span class="faint">${a.modellen.length} modellen</span></div>
    <div class="tabelbak"><table class="dtab" id="v-modellen"><thead><tr>
      <th class="sorteer">Model <span class="pijl">↕</span></th>
      <th class="sorteer">Groep <span class="pijl">↕</span></th>
      <th class="sorteer num">Maten <span class="pijl">↕</span></th>
      <th class="sorteer num actief" data-richting="af">Op voorraad <span class="pijl">↓</span></th>
    </tr></thead><tbody>${rijen}</tbody></table></div></div>`;

  const verv = Object.keys(r.per_vervoerder).map((v) => [v, r.per_vervoerder[v]]).sort((x, y) => y[1] - x[1]);
  const retourblok = `<div class="vk"><h3>Retouren die binnen zijn
      ${iknop("Elke regel op het tabblad 'Gescande retouren' is één teruggekomen pakket dat bij binnenkomst gescand is. Alle nummers zijn uniek, dus er zit geen dubbeling in.", "Retouren binnen", bronA)}</h3>
    <div class="waarschuw">Van deze ${getal(r.aantal_zendingen)} retouren is <b>alleen het trackingnummer</b>
      bekend. Welk artikel en welke maat erin zat staat niet in de Excel — dat komt uit Shopify zodra de
      koppeling werkt. Pas dan kan deze tab per model en maat tonen wat er terugligt.</div>
    <div class="tabelbak"><table class="dtab"><thead><tr><th>Vervoerder</th><th class="num">Zendingen</th>
      <th class="num">Aandeel</th></tr></thead><tbody>
      ${verv.map((v) => `<tr><td>${esc(v[0])}</td><td class="num">${getal(v[1])}</td>
        <td class="num">${(v[1] / r.aantal_zendingen * 100).toFixed(1).replace(".", ",")}%</td></tr>`).join("")}
      <tr class="totaal"><td>Totaal</td><td class="num">${getal(r.aantal_zendingen)}</td>
        <td class="num">100%</td></tr>
    </tbody></table></div></div>`;

  const kostenblok = !k.beschikbaar ? "" : `<div class="vk">
    <h3>Wat kost het om een retour opnieuw te verkopen?
      ${iknop("Alle bedragen komen uit de offerte van Innostock. Exclusief btw; overal geldt 21%. De opslagpost hangt af van hoe lang het artikel blijft liggen — dat stel je hieronder zelf in.", "Kostenmodel", bronK)}</h3>
    <div class="instelrij">
      <label>Weken opslag <input type="number" id="k-weken" min="0" max="104" value="${k.aannames.weken_opslag}">
        ${iknop("Hoe lang het artikel in het magazijn ligt voordat het opnieuw verkocht wordt. Elke week kost € 0,15 per sku-locatie. Blijft iets een jaar liggen, dan is dat € 7,80 aan opslag alleen.", "Weken opslag", bronK)}</label>
      <label>Verzendland <select id="k-land"><option value="NL">Nederland</option><option value="BE">België</option>
        <option value="DE">Duitsland</option><option value="FR">Frankrijk</option></select>
        ${iknop("Bepaalt welk verzendlabel gerekend wordt. Nederland via PostNL is het goedkoopst; Frankrijk via GLS is ruim twee keer zo duur.", "Verzendland", bronK)}</label>
      <label>Aantal <input type="number" id="k-aantal" min="1" max="10000" value="${k.aantal || r.aantal_zendingen}">
        ${iknop("Voor hoeveel stuks je het totaal wilt zien. Standaard het aantal retourzendingen dat binnen is.", "Aantal", bronK)}</label>
    </div>
    <div id="k-uitkomst">${tekenKosten(k)}</div></div>`;

  el.innerHTML = `<h2 style="margin:0 0 4px">Voorraad en retouren</h2>
    <p class="muted" style="margin:0 0 16px">Wat ligt er, wat kwam er terug, en wat kost het om dat opnieuw te verkopen.</p>
    ${dropblok}${waarschuwing}${kpis}${groeptabel}${maattabel}${modeltabel}${retourblok}${kostenblok}
    <p class="herkomst">Artikelen en retourscans: ${esc(bronA)} · Tarieven: ${esc(bronK)}</p>`;

  $$("#v-modellen tr.klik").forEach((tr) => {
    tr.onclick = () => {
      const i = tr.dataset.model;
      const open = $(`[data-pijl="${i}"]`).classList.toggle("open");
      $$(`#v-modellen tr[data-kind="${i}"]`).forEach((k) => k.classList.toggle("hidden", !open));
    };
  });
  $("#v-allesopen").onclick = () => {
    $$("#v-modellen tr.maatrij").forEach((k) => k.classList.remove("hidden"));
    $$("#v-modellen .pijltje").forEach((p) => p.classList.add("open"));
  };
  $("#v-allesdicht").onclick = () => {
    $$("#v-modellen tr.maatrij").forEach((k) => k.classList.add("hidden"));
    $$("#v-modellen .pijltje").forEach((p) => p.classList.remove("open"));
  };
  maakSorteerbaar($("#v-modellen"));

  const herbereken = async () => {
    try {
      const n = await api("/api/voorraad/kosten?weken=" + $("#k-weken").value +
        "&land=" + $("#k-land").value + "&aantal=" + $("#k-aantal").value);
      $("#k-uitkomst").innerHTML = tekenKosten(n);
    } catch (e) { toast("Herberekenen mislukt: " + e.message, true); }
  };
  ["k-weken", "k-land", "k-aantal"].forEach((id) => { const n = $("#" + id); if (n) n.onchange = herbereken; });
}

function tekenKosten(k) {
  const o = k.opsplitsing || {}, bronK = k.bron || "Innostock-offerte";
  return `<div class="tabelbak"><table class="dtab"><thead><tr><th>Post</th><th>Wat het is</th>
      <th class="num">Per stuk</th></tr></thead><tbody>
      ${k.posten.map((p) => `<tr><td>${esc(p.post)}</td><td class="faint">${esc(p.uitleg || "")}</td>
        <td class="num">${eur(p.bedrag)}</td></tr>`).join("")}
      <tr class="totaal"><td>Per stuk, exclusief btw</td><td></td><td class="num">${eur(k.per_stuk_ex_btw)}</td></tr>
      <tr><td class="faint">Per stuk, inclusief ${k.btw_percentage}% btw</td><td></td>
        <td class="num faint">${eur(k.per_stuk_incl_btw)}</td></tr>
    </tbody></table></div>
    <div class="vkpi" style="margin-top:14px">
      <div class="kaart zacht"><div class="v">${eur(o.binnenkomst)}</div><div class="l">Binnenkomst
        ${iknop("Retourverwerking en inslag samen: uitpakken, controleren en terugleggen. Deze kosten maak je hoe dan ook, ook als het artikel nooit meer verkocht wordt.", "Binnenkomst", bronK)}</div></div>
      <div class="kaart zacht"><div class="v">${eur(o.liggen)}</div><div class="l">Liggen (${k.aannames.weken_opslag} wk)
        ${iknop("Opslag per sku-locatie per week. Dit is de enige post die oploopt met de tijd — hoe langer iets blijft liggen, hoe duurder het wordt om het alsnog te verkopen.", "Opslag", bronK)}</div></div>
      <div class="kaart zacht"><div class="v">${eur(o.opnieuw_versturen)}</div><div class="l">Opnieuw versturen
        ${iknop("Pick & pack, verpakking en verzendlabel. Deze kosten maak je pas als het artikel daadwerkelijk opnieuw verkocht wordt.", "Opnieuw versturen", bronK)}</div></div>
      ${k.aantal ? `<div class="kaart"><div class="v">${eur(k.totaal_ex_btw)}</div>
        <div class="l">Totaal voor ${getal(k.aantal)} stuks
        ${iknop("Het bedrag per stuk maal het aantal. Exclusief btw: die kun je als ondernemer terugvragen, dus dit is wat je werkelijk kwijt bent.", "Totaal", bronK)}</div></div>` : ""}
    </div>
    ${(k.open_punten || []).length ? `<div class="waarschuw" style="margin-top:12px">
      <b>Nog niet vastgelegd in de offerte:</b><ul style="margin:6px 0 0 18px;padding:0">
      ${k.open_punten.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>` : ""}`;
}
