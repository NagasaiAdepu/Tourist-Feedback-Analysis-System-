/* Warangal Tourist Review Insights: front end.
   The browser only displays results; all NLP and statistics run on the FastAPI server. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const COLORS = { positive: "#2f855a", neutral: "#94a3b8", negative: "#b7323f", brand: "#0f4c5c", accent: "#c8792b" };
const VISITOR_LABELS = { family: "Family", friends: "Friends", solo: "Solo", couple: "Couple",
  school_trip: "School trip", foreign_tourist: "Foreign tourist" };
const state = { meta: null, charts: {}, reviewOffset: 0, rating: 0 };
const PAGE = 15;

// ---------- Helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const stars = (n) => (n ? "★".repeat(n) + "☆".repeat(5 - n) : "");
const scoreClass = (v) => (v > 15 ? "pos" : v < -15 ? "neg" : "neu");
const signed = (v) => (v > 0 ? `+${v}` : `${v}`);
const fmtDate = (d) => (d ? new Date(d + "T00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "");

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const body = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    let msg = body?.detail ?? body;
    if (Array.isArray(msg)) msg = msg.map((e) => e.msg?.replace(/^Value error, /, "")).join("; ");
    else if (typeof msg === "object") msg = msg.message || JSON.stringify(msg);
    throw Object.assign(new Error(msg || `Request failed (${res.status})`), { body });
  }
  return body;
}

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  t.hidden = false;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => (t.hidden = true), 4000);
}

function chart(id, config) {
  if (!window.Chart) { $("#" + id).parentElement.innerHTML = '<p class="muted small">Charts need an internet connection (Chart.js CDN).</p>'; return; }
  state.charts[id]?.destroy();
  state.charts[id] = new Chart($("#" + id), config);
}

function sentimentBar(p, u, n) {
  const total = p + u + n || 1;
  return `<div class="bar" title="${p} positive · ${u} neutral · ${n} negative">
    <i class="p" style="width:${(p / total) * 100}%"></i><i class="u" style="width:${(u / total) * 100}%"></i><i class="n" style="width:${(n / total) * 100}%"></i></div>`;
}

function query(form) {
  const params = new URLSearchParams();
  for (const [k, v] of new FormData(form)) if (v) params.set(k, v);
  return params;
}

function heatColor(v) {
  if (v === undefined) return "#f4f5f7";
  const a = Math.min(Math.abs(v) / 100, 1) * 0.85 + 0.08;
  return v >= 0 ? `rgba(47,133,90,${a})` : `rgba(183,50,63,${a})`;
}

// ---------- Setup ----------
async function init() {
  if (window.Chart) {
    Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    Chart.defaults.color = "#5c6577";
  }
  state.meta = await api("/api/meta");
  for (const sel of $$("[data-attractions]"))
    sel.insertAdjacentHTML("beforeend", state.meta.attractions.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join(""));
  for (const sel of $$("[data-visitors]"))
    sel.insertAdjacentHTML("beforeend", state.meta.visitor_types.map((v) => `<option value="${v}">${VISITOR_LABELS[v]}</option>`).join(""));
  for (const sel of $$("[data-aspects]"))
    sel.insertAdjacentHTML("beforeend", state.meta.aspects.map((a) => `<option value="${a.key}">${esc(a.label)}</option>`).join(""));

  $("#dashFilters").addEventListener("change", loadDashboard);
  $("#dashFilters").addEventListener("reset", () => setTimeout(loadDashboard));
  $("#reviewFilters").addEventListener("input", debounce(() => { state.reviewOffset = 0; loadReviews(); }, 300));
  $("#reviewFilters").addEventListener("submit", (e) => e.preventDefault());
  setupAnalyzer();
  setupFeedback();
  setupUpload();
  window.addEventListener("hashchange", route);
  route();
}

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

function route() {
  const [path, search] = (location.hash.replace(/^#\//, "") || "dashboard").split("?");
  const [view, id] = path.split("/");
  if (view === "analyze" && search) {           // #/analyze?text=... opens the analyser pre-filled
    const text = new URLSearchParams(search).get("text");
    if (text) { $("#analyzeText").value = text.slice(0, 5000); setTimeout(runAnalysis); }
  }
  const name = view === "attractions" && id ? "attraction" : view;
  if (!$("#view-" + name)) { location.hash = "#/dashboard"; return; }
  $$(".view").forEach((v) => (v.hidden = v.id !== "view-" + name));
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  window.scrollTo(0, 0);
  const loaders = { dashboard: loadDashboard, attractions: loadAttractions, attraction: () => loadAttraction(id),
    reviews: loadReviews, model: loadModel };
  loaders[name]?.().catch((e) => toast(e.message, true));
}

// ---------- Dashboard ----------
async function loadDashboard() {
  const d = await api("/api/dashboard?" + query($("#dashFilters")));
  $("#dashKpis").innerHTML = [
    ["Reviews analysed", d.total_reviews.toLocaleString("en-IN"), "across " + d.attractions.length + " attractions"],
    ["Average rating", d.avg_rating ? d.avg_rating.toFixed(2) + " ★" : "–", "out of 5"],
    ["Positive reviews", d.percentages.positive + "%", `${d.percentages.negative}% negative · ${d.percentages.neutral}% neutral`],
    ["Net sentiment", `<span class="score ${scoreClass(d.net_score)}">${signed(d.net_score)}</span>`, "from −100 to +100"],
  ].map(([l, v, h]) => `<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div><div class="hint">${h}</div></div>`).join("");

  chart("chartDist", { type: "doughnut",
    data: { labels: ["Positive", "Neutral", "Negative"],
      datasets: [{ data: [d.distribution.positive, d.distribution.neutral, d.distribution.negative],
        backgroundColor: [COLORS.positive, COLORS.neutral, COLORS.negative], borderWidth: 0 }] },
    options: { maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom" } } } });

  chart("chartRank", { type: "bar",
    data: { labels: d.attractions.map((a) => a.name),
      datasets: [{ label: "Net sentiment", data: d.attractions.map((a) => a.net_score),
        backgroundColor: d.attractions.map((a) => (a.net_score >= 0 ? COLORS.positive : COLORS.negative)), borderRadius: 6 }] },
    options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { afterLabel: (c) => `${d.attractions[c.dataIndex].reviews} reviews · ${d.attractions[c.dataIndex].avg_rating ?? "–"} ★` } } },
      scales: { x: { min: -100, max: 100, grid: { color: "#eef0f3" } }, y: { grid: { display: false } } } } });

  chart("chartTrend", { type: "bar",
    data: { labels: d.monthly.map((m) => m.month),
      datasets: [
        ...["positive", "neutral", "negative"].map((s) => ({ type: "bar", label: s[0].toUpperCase() + s.slice(1),
          data: d.monthly.map((m) => m[s]), backgroundColor: COLORS[s], stack: "s", yAxisID: "y" })),
        { type: "line", label: "Net sentiment", data: d.monthly.map((m) => m.net_score), borderColor: COLORS.accent,
          backgroundColor: COLORS.accent, yAxisID: "y1", tension: 0.3, pointRadius: 2 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom" } },
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, title: { display: true, text: "Reviews" }, grid: { color: "#eef0f3" } },
        y1: { position: "right", min: -100, max: 100, grid: { display: false }, title: { display: true, text: "Net sentiment" } } } } });

  const aspects = d.aspects.filter((a) => a.mentions);
  chart("chartAspects", { type: "bar",
    data: { labels: aspects.map((a) => a.label),
      datasets: ["positive", "neutral", "negative"].map((s) => ({ label: s[0].toUpperCase() + s.slice(1),
        data: aspects.map((a) => a[s]), backgroundColor: COLORS[s], borderRadius: 4 })) },
    options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { position: "bottom" } },
      scales: { x: { stacked: true, grid: { color: "#eef0f3" } }, y: { stacked: true, grid: { display: false } } } } });

  renderCloud($("#kwPos"), d.keywords.positive);
  renderCloud($("#kwNeg"), d.keywords.negative);

  const keys = state.meta.aspects;
  $("#heatmap").innerHTML = d.heatmap.length ? `<table class="heat"><thead><tr><th>Attraction</th>${keys.map((a) => `<th class="rot">${esc(a.label)}</th>`).join("")}</tr></thead>
    <tbody>${d.heatmap.map((row) => `<tr><td><a href="#/attractions/${row.id}">${esc(row.name)}</a></td>${keys.map((a) => {
      const c = row.cells[a.key];
      return `<td class="cell" style="background:${heatColor(c?.net_score)};color:${c && Math.abs(c.net_score) > 45 ? "#fff" : "#1d2433"}"
        title="${c ? c.mentions + " mentions" : "No mentions"}">${c ? signed(c.net_score) : ""}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table>` : '<p class="empty">No data for these filters.</p>';

  $("#mismatches").innerHTML = d.mismatches.length ? `<div class="table-wrap"><table><thead><tr><th>Attraction</th><th>Rating</th><th>Text sentiment</th><th>Review</th></tr></thead><tbody>
    ${d.mismatches.map((m) => `<tr><td>${esc(m.attraction)}</td><td class="rating">${stars(m.rating)}</td><td><span class="badge ${m.sentiment}">${m.sentiment}</span></td><td>${esc(m.text)}</td></tr>`).join("")}
    </tbody></table></div>` : '<p class="muted">No mismatches found.</p>';
}

function renderCloud(el, items) {
  if (!items.length) { el.innerHTML = '<span class="muted small">Not enough reviews yet.</span>'; return; }
  const max = Math.max(...items.map((i) => i.count));
  el.innerHTML = items.map((i) => `<span style="font-size:${13 + (i.count / max) * 13}px" title="${i.count} reviews">${esc(i.term)}</span>`).join("");
}

// ---------- Attractions ----------
async function loadAttractions() {
  const d = await api("/api/dashboard");
  const stats = Object.fromEntries(d.attractions.map((a) => [a.id, a]));
  $("#attractionGrid").innerHTML = state.meta.attractions.map((a) => {
    const s = stats[a.id] || { reviews: 0, positive: 0, neutral: 0, negative: 0, net_score: 0 };
    return `<a class="card a-card" href="#/attractions/${a.id}">
      <span class="cat">${esc(a.category)}</span><h3>${esc(a.name)}</h3>
      <span class="muted small">${esc(a.location)}</span>
      <p class="small" style="margin:4px 0">${esc(a.description)}</p>
      ${sentimentBar(s.positive, s.neutral, s.negative)}
      <div class="row between small"><span>${s.reviews} reviews${s.avg_rating ? " · " + s.avg_rating + " ★" : ""}</span>
      <span class="score ${scoreClass(s.net_score)}">Net ${signed(s.net_score)}</span></div></a>`;
  }).join("");
}

async function loadAttraction(id) {
  const box = $("#attractionDetail");
  box.innerHTML = '<p class="muted">Loading…</p>';
  const d = await api(`/api/attractions/${id}/insights`);
  const a = d.attraction;
  const reviewCards = (list, s) => list.length ? list.map((r) => `<div class="review"><div class="review-head"><span class="badge ${s}">${s}</span>
      <span class="rating">${stars(r.rating)}</span><span>${fmtDate(r.visit_date)}</span><span>${VISITOR_LABELS[r.visitor_type] || ""}</span></div>
      <p>${esc(r.text)}</p></div>`).join("") : '<p class="muted">None yet.</p>';
  box.innerHTML = `
    <div class="card">
      <span class="chip">${esc(a.category)}</span> <span class="muted small">${esc(a.location)}</span>
      <h1 style="margin-top:6px">${esc(a.name)}</h1>
      <p class="muted">${esc(a.description)}</p>
      <p class="summary">${esc(d.summary)}</p>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="label">Reviews</div><div class="value">${d.total_reviews}</div></div>
      <div class="kpi"><div class="label">Average rating</div><div class="value">${d.avg_rating ?? "–"} ★</div></div>
      <div class="kpi"><div class="label">Net sentiment</div><div class="value score ${scoreClass(d.net_score)}">${signed(d.net_score)}</div><div class="hint">all reviews</div></div>
      <div class="kpi"><div class="label">Recent net sentiment</div><div class="value score ${scoreClass(d.recent_net_score)}">${signed(d.recent_net_score)}</div><div class="hint">latest 50 reviews</div></div>
    </div>
    <div class="grid two">
      <div class="card"><h3>Aspect breakdown</h3><p class="muted small">Share of positive, neutral and negative mentions</p>
        ${d.aspects.map((x) => `<div class="aspect-row"><span>${esc(x.label)}</span>${sentimentBar(x.positive, x.neutral, x.negative)}
          <span class="score ${scoreClass(x.net_score)}">${signed(x.net_score)}</span></div>`).join("") || '<p class="muted">No aspects mentioned yet.</p>'}
      </div>
      <div class="card"><h3>Action points for authorities</h3>
        ${d.issues.length ? d.issues.map((i) => `<div class="issue"><div class="row between"><b>${esc(i.label)}</b><span class="badge ${i.priority}">${i.priority} priority</span></div>
          <div class="small muted">${i.negative_pct}% of ${i.mentions} mentions are negative</div><div>${esc(i.recommendation)}</div></div>`).join("")
          : '<p class="muted">No major issues detected.</p>'}
        <h4>Strengths to promote</h4>
        ${d.strengths.length ? d.strengths.map((s) => `<div class="strength"><b>${esc(s.label)}</b> <span class="small">· ${s.positive_pct}% positive of ${s.mentions} mentions</span></div>`).join("")
          : '<p class="muted small">Not enough positive mentions yet.</p>'}
      </div>
    </div>
    <div class="grid two">
      <div class="card"><h3>Keywords</h3><h4 class="pos-text">Praised for</h4><div class="cloud" id="aKwPos"></div>
        <h4 class="neg-text">Complaints about</h4><div class="cloud" id="aKwNeg"></div></div>
      <div class="card"><h3>Most positive reviews</h3>${reviewCards(d.top_positive, "positive")}</div>
    </div>
    <div class="card"><h3>Most negative reviews</h3>${reviewCards(d.top_negative, "negative")}
      <a class="btn ghost small" href="#/reviews" onclick="setTimeout(()=>{const f=document.querySelector('#reviewFilters');f.attraction_id.value='${a.id}';f.dispatchEvent(new Event('input'))},50)">See all reviews</a></div>`;
  renderCloud($("#aKwPos"), d.keywords.positive);
  renderCloud($("#aKwNeg"), d.keywords.negative);
}

// ---------- Analyser ----------
const SAMPLES = [
  "The carvings at Ramappa are breathtaking and the guide explained the history well, but the road from Warangal is full of potholes.",
  "Bhadrakali temple was very crowded on Friday, we waited three hours in the queue and the toilets were dirty.",
  "Laknavaram hanging bridge at sunset was beautiful! Boating was well organised and affordable.",
  "Warangal Fort is neglected, garbage everywhere and no information boards. Very disappointing.",
];

function setupAnalyzer() {
  $("#samples").innerHTML = SAMPLES.map((s, i) => `<button class="chip" data-i="${i}">Example ${i + 1}</button>`).join("");
  $("#samples").addEventListener("click", (e) => {
    if (e.target.dataset.i === undefined) return;
    $("#analyzeText").value = SAMPLES[e.target.dataset.i];
    runAnalysis();
  });
  $("#analyzeBtn").addEventListener("click", runAnalysis);
}

async function runAnalysis() {
  const text = $("#analyzeText").value.trim();
  if (text.length < 3) return toast("Type a review first", true);
  const btn = $("#analyzeBtn");
  btn.disabled = true;
  try {
    const r = await api("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    $("#analyzeResult").innerHTML = renderAnalysis(text, r);
  } catch (e) { toast(e.message, true); } finally { btn.disabled = false; }
}

function highlight(text, words) {
  let html = esc(text);
  for (const w of words.filter((x) => Math.abs(x.valence) >= 0.5)) {
    const re = new RegExp(`\\b(${w.word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})\\b`, "gi");
    html = html.replace(re, `<mark class="${w.valence > 0 ? "pos" : "neg"}" title="valence ${w.valence}">$1</mark>`);
  }
  return html;
}

function renderAnalysis(text, r) {
  const s = r.sentiment;
  const probRow = (label, value, color) => `<div class="prob"><span>${label}</span><div class="bar"><i style="width:${value * 100}%;background:${color}"></i></div><span>${Math.round(value * 100)}%</span></div>`;
  return `
    <div class="card">
      <div class="result-head">
        <span class="badge ${s.label} big-label">${s.label}</span>
        <span class="muted">Confidence <b>${Math.round(s.confidence * 100)}%</b> · ML model: <b>${s.ml_label}</b> · VADER: <b>${s.vader_label}</b> (compound ${s.vader_compound})</span>
      </div>
      <div class="grid two" style="margin-top:14px">
        <div><h4>Hybrid probabilities</h4>${probRow("Positive", s.probabilities.positive, COLORS.positive)}${probRow("Neutral", s.probabilities.neutral, COLORS.neutral)}${probRow("Negative", s.probabilities.negative, COLORS.negative)}</div>
        <div><h4>Highlighted opinion words</h4><div class="highlighted">${highlight(text, r.highlights)}</div></div>
      </div>
    </div>
    <div class="card"><h3>Aspects mentioned</h3>
      ${r.aspects.length ? `<div class="grid three">${r.aspects.map((a) => `<div class="aspect-card"><div class="row between"><b>${esc(a.label)}</b><span class="badge ${a.sentiment}">${a.sentiment}</span></div>
        <div class="snippet">“${esc(a.snippet)}”</div></div>`).join("")}</div>` : '<p class="muted">No specific aspect detected.</p>'}
    </div>
    <div class="grid two">
      <div class="card"><h3>Keywords</h3>${r.keywords.map((k) => `<span class="chip">${esc(k)}</span>`).join("") || '<span class="muted">None</span>'}</div>
      <div class="card"><h3>Pre-processed text</h3><p class="muted small">Lower-cased, contractions expanded, stop words removed, lemmatised (${r.words} words, ${r.sentences} sentence${r.sentences === 1 ? "" : "s"})</p><code>${esc(r.preprocessed)}</code></div>
    </div>`;
}

// ---------- Feedback form ----------
function setupFeedback() {
  const box = $("#starInput");
  box.innerHTML = [1, 2, 3, 4, 5].map((n) => `<button type="button" class="star" data-n="${n}" aria-label="${n} star${n > 1 ? "s" : ""}">★</button>`).join("");
  box.addEventListener("click", (e) => {
    if (!e.target.dataset.n) return;
    state.rating = +e.target.dataset.n;
    $$(".star", box).forEach((s) => s.classList.toggle("on", +s.dataset.n <= state.rating));
  });
  const form = $("#feedbackForm");
  form.visit_date.max = new Date().toISOString().slice(0, 10);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.rating) return toast("Please choose a star rating", true);
    const f = Object.fromEntries(new FormData(form));
    const body = { attraction_id: +f.attraction_id, reviewer_name: f.reviewer_name || null, visitor_type: f.visitor_type,
      rating: state.rating, visit_date: f.visit_date || null, text: f.text };
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const r = await api("/api/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      toast("Thank you! Your feedback was saved.");
      $("#feedbackResult").innerHTML = `<h2 style="margin:10px 0">How we understood your feedback</h2>` + renderAnalysis(f.text, r.analysis);
      form.reset(); state.rating = 0; $$(".star").forEach((s) => s.classList.remove("on"));
    } catch (err) { toast(err.message, true); } finally { btn.disabled = false; }
  });
}

// ---------- Reviews ----------
async function loadReviews() {
  const params = query($("#reviewFilters"));
  params.set("limit", PAGE);
  params.set("offset", state.reviewOffset);
  const exportParams = new URLSearchParams(params);
  ["limit", "offset", "sort", "q"].forEach((k) => exportParams.delete(k));
  $("#exportLink").href = "/api/export.csv?" + exportParams;
  const d = await api("/api/reviews?" + params);
  $("#reviewCount").textContent = `${d.total.toLocaleString("en-IN")} review${d.total === 1 ? "" : "s"} found`;
  $("#reviewList").innerHTML = `<div class="card">${d.reviews.length ? d.reviews.map((r) => `
    <div class="review"><div class="review-head"><b>${esc(r.attraction)}</b><span class="badge ${r.sentiment}">${r.sentiment}</span>
      <span class="rating">${stars(r.rating)}</span><span>${fmtDate(r.visit_date)}</span><span>${esc(r.reviewer_name || "Anonymous")}${r.visitor_type ? " · " + VISITOR_LABELS[r.visitor_type] : ""}</span>
      <span class="small">${Math.round(r.confidence * 100)}% confidence</span>
      <button class="btn danger small" data-del="${r.id}" style="margin-left:auto">Delete</button></div>
      <p>${esc(r.text)}</p>
      <div>${r.aspects.map((a) => `<span class="chip ${a.sentiment}" title="${esc(a.snippet)}">${esc(state.meta.aspects.find((x) => x.key === a.aspect)?.label || a.aspect)}</span>`).join("")}</div>
    </div>`).join("") : '<p class="empty">No reviews match these filters.</p>'}</div>`;
  const pages = Math.ceil(d.total / PAGE), page = Math.floor(state.reviewOffset / PAGE) + 1;
  $("#pager").innerHTML = pages > 1 ? `<button class="btn ghost small" ${page === 1 ? "disabled" : ""} data-page="-1">← Previous</button>
    <span class="muted small">Page ${page} of ${pages}</span>
    <button class="btn ghost small" ${page === pages ? "disabled" : ""} data-page="1">Next →</button>` : "";
}

document.addEventListener("click", async (e) => {
  const del = e.target.dataset?.del;
  if (del) {
    if (!confirm("Delete this review permanently?")) return;
    try { await api(`/api/reviews/${del}`, { method: "DELETE" }); toast("Review deleted"); loadReviews(); }
    catch (err) { toast(err.message, true); }
  }
  const page = e.target.dataset?.page;
  if (page) { state.reviewOffset = Math.max(0, state.reviewOffset + +page * PAGE); loadReviews(); }
});

// ---------- Upload ----------
function setupUpload() {
  $("#templateBtn").addEventListener("click", () => {
    const csv = "attraction,rating,visit_date,visitor_type,reviewer_name,text\n" +
      'Ramappa Temple,5,2026-10-12,family,Ravi,"Amazing sculptures and very clean premises."\n' +
      'Warangal Fort,2,2026-10-20,friends,,"Beautiful gateways but garbage everywhere and no drinking water."\n';
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: "reviews_template.csv" });
    a.click();
    URL.revokeObjectURL(a.href);
  });
  $("#uploadBtn").addEventListener("click", async () => {
    const file = $("#csvFile").files[0];
    if (!file) return toast("Choose a CSV file first", true);
    const fd = new FormData();
    fd.append("file", file);
    const btn = $("#uploadBtn");
    btn.disabled = true;
    try {
      const r = await api("/api/reviews/upload", { method: "POST", body: fd });
      $("#uploadResult").innerHTML = `<div class="card"><h3>Imported ${r.imported} review${r.imported === 1 ? "" : "s"}</h3>
        <p><span class="badge positive">${r.sentiment.positive} positive</span> <span class="badge neutral">${r.sentiment.neutral} neutral</span> <span class="badge negative">${r.sentiment.negative} negative</span></p>
        ${r.skipped ? `<p class="error">${r.skipped} row${r.skipped === 1 ? " was" : "s were"} skipped:</p><ul>${r.errors.map((e) => `<li>Row ${e.row}: ${esc(e.error)}</li>`).join("")}</ul>` : ""}
        <a class="btn" href="#/dashboard">View dashboard</a></div>`;
      toast("Upload complete");
    } catch (err) {
      const errors = err.body?.detail?.errors;
      $("#uploadResult").innerHTML = `<div class="card"><p class="error">${esc(err.message)}</p>${errors ? `<ul>${errors.map((e) => `<li>Row ${e.row}: ${esc(e.error)}</li>`).join("")}</ul>` : ""}</div>`;
    } finally { btn.disabled = false; }
  });
}

// ---------- Model performance ----------
async function loadModel() {
  $("#pipelineCard").innerHTML = ["Review text", "Cleaning & contractions", "Tokenise", "Stop words (keep negations)", "Lemmatise",
    "TF-IDF (1–2 grams) → Logistic Regression", "VADER + tourism lexicon", "Hybrid 60 / 40", "Aspect & keyword extraction"]
    .map((s, i) => `${i ? '<span class="arrow">→</span>' : ""}<span class="step">${s}</span>`).join("");
  const d = await api("/api/model/evaluation");
  const names = { vader: "VADER (lexicon)", ml: "TF-IDF + Logistic Regression", hybrid: "Hybrid (60% ML + 40% VADER)" };
  const section = (set) => {
    const best = Object.entries(set.models).sort((a, b) => b[1].f1 - a[1].f1)[0][0];
    return `<div class="card"><h3>${esc(set.name)} <span class="muted small">(${set.size} reviews)</span></h3><p class="muted small">${esc(set.note)}</p>
      <div class="grid three">${Object.entries(set.models).map(([k, m]) => `<div class="aspect-card ${k === best ? "best" : ""}">
        <b>${names[k]}</b>${k === best ? ' <span class="chip">best F1</span>' : ""}
        <div class="row between" style="margin-top:6px"><div><div class="metric-big">${Math.round(m.accuracy * 100)}%</div><div class="small muted">accuracy</div></div>
        <div class="small">Precision ${m.precision}<br>Recall ${m.recall}<br><b>Macro F1 ${m.f1}</b></div></div>
        ${confusion(m.confusion_matrix, d.labels)}</div>`).join("")}</div></div>`;
  };
  $("#modelResult").innerHTML = section(d.handwritten) + section(d.corpus);
}

function confusion(cm, labels) {
  const max = Math.max(...cm.flat(), 1);
  const short = { negative: "Neg", neutral: "Neu", positive: "Pos" };
  return `<table class="cm" style="margin-top:10px"><tr><th class="small">true ↓ / pred →</th>${labels.map((l) => `<th class="small">${short[l]}</th>`).join("")}</tr>
    ${cm.map((row, i) => `<tr><th class="small">${short[labels[i]]}</th>${row.map((v, j) => `<td class="v" style="background:${i === j ? `rgba(15,76,92,${0.12 + (v / max) * 0.75})` : `rgba(183,50,63,${v ? 0.1 + (v / max) * 0.5 : 0.04})`};color:${i === j && v / max > 0.5 ? "#fff" : "#1d2433"}">${v}</td>`).join("")}</tr>`).join("")}</table>`;
}

init().catch((e) => toast("Could not start the app: " + e.message, true));
