// Visual builder: drag-to-connect, percent/ratio link editing, live per-department status,
// a persistent working draft (survives navigation), and undo/redo.

const DRAFT_KEY = 'staffing:builder:draft';
const UNITS_KEY = 'staffing:builder:units';

function builderStyle() {
  const style = cyStyle();
  style.find(r => r.selector === 'edge').style['label'] = 'data(label)';  // formatted % / ratio
  return style;
}

const cy = cytoscape({
  container: document.getElementById('cy'),
  style: builderStyle(),
  wheelSensitivity: 0.2, minZoom: 0.2, maxZoom: 2.5,
});
const eh = cy.edgehandles({ snap: true, snapThreshold: 18, hoverDelay: 100,
  edgeParams: () => ({ data: { ratio: 1 } }) });

const el = (x) => document.getElementById(x);
const tInput = el('set-t'), sInput = el('set-s'), nameInput = el('design-name');
const inspector = el('inspector'), diagnosticsEl = el('diagnostics');
const statusEl = el('status-list'), saveMsg = el('save-msg'), draftNote = el('draft-note');

let counter = 0;
let units = localStorage.getItem(UNITS_KEY) || 'percent';
let history = [], hindex = -1, applying = false;

const saveDraftSoon = debounce(saveDraft, 300);
const autoValidate = debounce(validate, 500);

// ---------------------------------------------------------------- labels & units
function setEdgeLabel(edge) { edge.data('label', ratioLabel(num(edge.data('ratio')), units)); }
function relabelEdges() { cy.edges().forEach(setEdgeLabel); }

document.querySelectorAll('input[name="units"]').forEach(r => {
  r.checked = r.value === units;
  r.addEventListener('change', () => {
    units = r.value; localStorage.setItem(UNITS_KEY, units);
    relabelEdges();
    const sel = cy.$('edge:selected'); if (sel.length) showEdgeInspector(sel[0]);
  });
});

// ---------------------------------------------------------------- node / edge ops
function uniqueName(base) {
  const names = new Set(cy.nodes().map(n => n.data('name')));
  if (!names.has(base)) return base;
  let i = 2; while (names.has(`${base} ${i}`)) i++; return `${base} ${i}`;
}

function addDept() {
  const k = cy.nodes().length;
  cy.add({ group: 'nodes',
    data: { id: 'n' + (++counter), name: uniqueName('Department'), makespan: 1, demand: 0, congestion: 0, buffer: '' },
    position: { x: 90 + (k % 5) * 150, y: 100 + Math.floor(k / 5) * 110 } });
  commit();
}

cy.on('ehcomplete', (evt, source, target, added) => {
  const dup = cy.edges().filter(e => e.id() !== added.id()
    && e.source().id() === source.id() && e.target().id() === target.id());
  if (dup.length) { added.remove(); cy.$(':selected').unselect(); dup.select(); return; }
  added.data('ratio', 1); setEdgeLabel(added); added.select();
  commit();
});

el('add-dept').onclick = addDept;
el('delete-sel').onclick = () => { if (cy.$(':selected').length) { cy.$(':selected').remove(); clearInspector(); commit(); } };

// ---------------------------------------------------------------- inspector
function field(label, key, val, numeric) {
  return `<label>${label}<input data-key="${key}" type="${numeric ? 'number' : 'text'}" `
    + `${numeric ? 'step="any"' : ''} value="${val ?? ''}"></label>`;
}

function showNodeInspector(node) {
  const d = node.data();
  inspector.innerHTML = '<h4>Department</h4>'
    + field('Name', 'name', d.name)
    + field('Makespan (time / unit)', 'makespan', d.makespan, true)
    + field('Demand (units / period)', 'demand', d.demand, true)
    + field('Congestion β', 'congestion', d.congestion, true)
    + field('Buffer (max backlog, blank = none)', 'buffer', d.buffer, true);
  inspector.querySelectorAll('input').forEach(inp => {
    inp.addEventListener('input', () => { node.data(inp.dataset.key, inp.value); saveDraftSoon(); autoValidate(); });
    inp.addEventListener('change', commit);
  });
}

function showEdgeInspector(edge) {
  const isPct = units === 'percent';
  const ratio = num(edge.data('ratio'));
  const max = isPct ? 150 : 1.5, step = isPct ? 5 : 0.05;
  const disp = (r) => isPct ? Math.round(r * 100) : round3(r);
  inspector.innerHTML =
    `<h4>Flow: ${escapeHtml(edge.source().data('name'))} → ${escapeHtml(edge.target().data('name'))}</h4>`
    + `<label>Ratio (${isPct ? '%' : '0–1'})<input id="ratio-num" type="number" min="0" step="${step}" value="${disp(ratio)}"></label>`
    + `<input id="ratio-range" type="range" min="0" max="${max}" step="${step}" value="${Math.min(disp(ratio), max)}">`
    + `<p class="muted">Drag past 100% / 1.0 for fan-out (work multiplication).</p>`;
  const numEl = el('ratio-num'), rangeEl = el('ratio-range');
  const apply = (raw, commitNow) => {
    let r = isPct ? num(raw) / 100 : num(raw);
    if (r < 0) r = 0;
    edge.data('ratio', r); setEdgeLabel(edge);
    numEl.value = disp(r); rangeEl.value = Math.min(disp(r), max);
    if (commitNow) commit(); else { saveDraftSoon(); autoValidate(); }
  };
  numEl.addEventListener('input', () => apply(numEl.value, false));
  numEl.addEventListener('change', () => apply(numEl.value, true));
  rangeEl.addEventListener('input', () => apply(rangeEl.value, false));
  rangeEl.addEventListener('change', () => apply(rangeEl.value, true));  // commit on release
}

function clearInspector() {
  inspector.innerHTML = '<p class="muted">Select a node or link to edit. Drag node-to-node to connect.</p>';
}

cy.on('select', 'node', (e) => showNodeInspector(e.target));
cy.on('select', 'edge', (e) => showEdgeInspector(e.target));
cy.on('unselect', () => { if (cy.$(':selected').length === 0) clearInspector(); });
cy.on('dragfree', 'node', commit);

// ---------------------------------------------------------------- doc <-> canvas
function buildDoc() {
  const departments = cy.nodes().map(n => {
    const d = n.data(), p = n.position();
    return { name: d.name, makespan: num(d.makespan), demand: num(d.demand), congestion: num(d.congestion),
      buffer: (d.buffer === '' || d.buffer == null) ? null : num(d.buffer), x: Math.round(p.x), y: Math.round(p.y) };
  });
  const flows = cy.edges().map(e => ({ from: e.source().data('name'), to: e.target().data('name'), ratio: num(e.data('ratio')) }));
  return { name: nameInput.value || 'design',
    settings: { time_per_employee: num(tInput.value), headcount: sInput.value === '' ? null : num(sInput.value) },
    departments, flows };
}

function applyDoc(doc) {
  applying = true;
  nameInput.value = doc.name || '';
  tInput.value = (doc.settings && doc.settings.time_per_employee) ?? 480;
  sInput.value = (doc.settings && doc.settings.headcount != null) ? doc.settings.headcount : '';
  cy.elements().remove();
  const idByName = {};
  (doc.departments || []).forEach((d, i) => {
    idByName[d.name] = 'n' + (++counter);
    cy.add({ group: 'nodes',
      data: { id: idByName[d.name], name: d.name, makespan: d.makespan, demand: d.demand,
        congestion: d.congestion, buffer: d.buffer == null ? '' : d.buffer },
      position: { x: d.x ?? (90 + (i % 5) * 150), y: d.y ?? (100 + Math.floor(i / 5) * 110) } });
  });
  (doc.flows || []).forEach(f => {
    const e = cy.add({ group: 'edges', data: { id: 'e' + (++counter), source: idByName[f.from], target: idByName[f.to], ratio: f.ratio } });
    setEdgeLabel(e);
  });
  if ((doc.departments || []).length && doc.departments.every(d => d.x == null)) {
    cy.layout({ name: 'breadthfirst', directed: true, spacingFactor: 1.3 }).run();
  }
  cy.fit(null, 40);
  applying = false;
  clearInspector();
}

// ---------------------------------------------------------------- history (undo/redo)
function commit() {
  if (applying) return;
  const json = JSON.stringify(buildDoc());
  if (history[hindex] === json) return;
  history = history.slice(0, hindex + 1);
  history.push(json); hindex++;
  if (history.length > 200) { history.shift(); hindex--; }
  saveDraftSoon(); autoValidate(); updateUndoButtons();
}
function undo() { if (hindex > 0) { hindex--; applyDoc(JSON.parse(history[hindex])); saveDraftSoon(); autoValidate(); updateUndoButtons(); } }
function redo() { if (hindex < history.length - 1) { hindex++; applyDoc(JSON.parse(history[hindex])); saveDraftSoon(); autoValidate(); updateUndoButtons(); } }
function updateUndoButtons() { el('undo').disabled = hindex <= 0; el('redo').disabled = hindex >= history.length - 1; }

el('undo').onclick = undo;
el('redo').onclick = redo;
document.addEventListener('keydown', (e) => {
  const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
  if (typing || !(e.ctrlKey || e.metaKey)) return;
  const key = e.key.toLowerCase();
  if (key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
  else if (key === 'y' || (key === 'z' && e.shiftKey)) { e.preventDefault(); redo(); }
});

// ---------------------------------------------------------------- draft persistence
function saveDraft() {
  localStorage.setItem(DRAFT_KEY, JSON.stringify({ sourceId: window.DESIGN_ID ?? null, doc: buildDoc() }));
}
function readDraft() { try { return JSON.parse(localStorage.getItem(DRAFT_KEY)); } catch { return null; } }
function showDraftNote(restored) {
  draftNote.innerHTML = restored
    ? 'Restored unsaved draft. <a href="#" id="discard-draft">Discard</a>'
    : '';
  const dd = el('discard-draft');
  if (dd) dd.onclick = async (e) => { e.preventDefault(); await discardDraft(); };
}
async function discardDraft() {
  localStorage.removeItem(DRAFT_KEY);
  const target = window.DESIGN_ID ?? null;
  if (target) await loadDesign(target); else applyDoc(starterDoc());
  resetHistory(); showDraftNote(false); autoValidate();
}

// ---------------------------------------------------------------- validate / status / save
function applyGraphStyles(graph) {
  const roots = new Set(graph.roots);
  cy.nodes().forEach(n => n[roots.has(n.data('name')) ? 'addClass' : 'removeClass']('root'));
  const rework = new Set(graph.edges.filter(e => e.is_rework).map(e => e.from + '' + e.to));
  cy.edges().forEach(e => {
    const key = e.source().data('name') + '' + e.target().data('name');
    e[rework.has(key) ? 'addClass' : 'removeClass']('rework');
  });
}

function renderStatus(nodes) {
  if (!nodes || !nodes.length) { statusEl.innerHTML = '<p class="muted">Add departments to see status.</p>'; return; }
  statusEl.innerHTML = nodes.map(n => {
    const pct = Math.round((n.outflow || 0) * 100);
    const note = (n.notes && n.notes.length) ? n.notes.join(', ') : `${pct}% out`;
    const badge = n.status === 'warn' ? '<span class="badge invalid">!</span>' : '<span class="badge valid">ok</span>';
    return `<div class="statusrow">${badge} <b>${escapeHtml(n.id)}</b> <span class="muted">${escapeHtml(note)}</span></div>`;
  }).join('');
}

async function validate() {
  try {
    const r = await api('POST', '/api/validate', buildDoc());
    applyGraphStyles(r.graph);
    renderStatus(r.graph.nodes);
    const banner = r.ok ? '<div class="ok-banner">Design is mathematically sound.</div>' : '';
    const wrap = document.createElement('div'); renderDiagnostics(wrap, r.diagnostics);
    diagnosticsEl.innerHTML = banner; diagnosticsEl.appendChild(wrap);
    return r.ok;
  } catch (err) {
    diagnosticsEl.innerHTML = `<div class="diag error">validation failed: ${escapeHtml(JSON.stringify(err.data))}</div>`;
    return false;
  }
}

async function save() {
  try {
    const r = await api('POST', '/api/designs', buildDoc());
    window.DESIGN_ID = r.id;
    saveDraft();  // re-key the draft to the new design id so reopening restores it
    window.history.replaceState(null, '', '/builder/' + r.id);
    saveMsg.innerHTML = `Saved <b>${escapeHtml(r.id)}</b>${r.ok ? '' : ' — invalid, fix before running'} · `
      + `<a href="/designs">library</a> · <a href="/simulate/${r.id}">simulate</a>`;
    renderDiagnostics(diagnosticsEl, r.diagnostics);
  } catch (err) {
    saveMsg.innerHTML = `<span class="diag error">save failed: ${escapeHtml(JSON.stringify(err.data))}</span>`;
  }
}

el('validate-btn').onclick = validate;
el('save-btn').onclick = save;

// ---------------------------------------------------------------- init
function starterDoc() {
  return { name: '', settings: { time_per_employee: 480, headcount: 50 },
    departments: [{ name: 'Department', makespan: 1, demand: 0, congestion: 0, buffer: null, x: 140, y: 140 }], flows: [] };
}
function resetHistory() { history = [JSON.stringify(buildDoc())]; hindex = 0; updateUndoButtons(); }

async function loadDesign(id) { applyDoc(await api('GET', '/api/designs/' + id)); }

async function init() {
  const target = window.DESIGN_ID ?? null;
  const draft = readDraft();
  if (draft && (draft.sourceId ?? null) === target) {
    applyDoc(draft.doc); showDraftNote(true);
  } else if (target) {
    await loadDesign(target); showDraftNote(false);
  } else {
    applyDoc(starterDoc()); showDraftNote(false);
  }
  resetHistory();
  validate();
}

init();
