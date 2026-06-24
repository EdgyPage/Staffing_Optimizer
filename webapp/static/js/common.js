// Shared helpers: a tiny fetch wrapper and DOM utilities used by every page.

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
  if (!res.ok) throw { status: res.status, data };
  return data;
}

function num(v) { const n = parseFloat(v); return Number.isNaN(n) ? 0 : n; }

function round3(v) { return Math.round(v * 1000) / 1000; }

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// Format a stored ratio (0..1) for display in the current units.
function ratioLabel(ratio, units) {
  return units === 'percent' ? Math.round(ratio * 100) + '%' : String(round3(ratio));
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function renderDiagnostics(el, diags) {
  if (!diags || !diags.length) { el.innerHTML = ''; return; }
  el.innerHTML = diags.map(d => {
    const where = d.line ? `line ${d.line}: ` : '';
    return `<div class="diag ${d.severity}">${escapeHtml(where + d.message)}</div>`;
  }).join('');
}

// Build the standard read-only Cytoscape style (shared by builder + simulate).
function cyStyle() {
  return [
    { selector: 'node', style: {
        'label': 'data(name)', 'text-valign': 'center', 'text-halign': 'center',
        'shape': 'round-rectangle', 'background-color': '#eef2f7', 'border-color': '#2c3e50',
        'border-width': 1, 'width': 'label', 'height': 'label', 'padding': '12px', 'font-size': 12 } },
    { selector: 'node.root', style: { 'background-color': '#d9f0d9', 'border-color': '#2ca02c' } },
    { selector: 'node.bad', style: { 'border-color': '#d62728', 'border-width': 3 } },
    { selector: 'node:selected', style: { 'border-color': '#1f77b4', 'border-width': 3 } },
    { selector: 'edge', style: {
        'label': 'data(ratio)', 'curve-style': 'bezier', 'target-arrow-shape': 'triangle',
        'width': 2, 'line-color': '#888', 'target-arrow-color': '#888', 'font-size': 10,
        'text-background-color': '#fff', 'text-background-opacity': 0.85 } },
    { selector: 'edge.rework', style: {
        'line-color': '#d62728', 'target-arrow-color': '#d62728', 'line-style': 'dashed' } },
    { selector: 'edge:selected', style: { 'line-color': '#1f77b4', 'target-arrow-color': '#1f77b4', 'width': 4 } },
  ];
}

// Map a 0..1 fraction to a green->amber->red fill (used to shade backlog).
function heatColor(frac) {
  frac = Math.max(0, Math.min(1, frac));
  const stops = [[217, 240, 217], [255, 230, 150], [214, 39, 40]];
  const seg = frac < 0.5 ? 0 : 1;
  const t = frac < 0.5 ? frac / 0.5 : (frac - 0.5) / 0.5;
  const a = stops[seg], b = stops[seg + 1];
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
