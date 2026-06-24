// Visual builder: drag department nodes, draw flow edges, edit params, validate, and save.

const cy = cytoscape({
  container: document.getElementById('cy'),
  style: cyStyle(),
  wheelSensitivity: 0.2,
  minZoom: 0.2, maxZoom: 2.5,
});

const tInput = document.getElementById('set-t');
const sInput = document.getElementById('set-s');
const nameInput = document.getElementById('design-name');
const inspector = document.getElementById('inspector');
const diagnosticsEl = document.getElementById('diagnostics');
const saveMsg = document.getElementById('save-msg');

let counter = 0;
let linkMode = false;
let linkSource = null;

function uniqueName(base) {
  const names = new Set(cy.nodes().map(n => n.data('name')));
  if (!names.has(base)) return base;
  let i = 2;
  while (names.has(`${base} ${i}`)) i++;
  return `${base} ${i}`;
}

function addDept() {
  const id = 'n' + (++counter);
  const k = cy.nodes().length;
  cy.add({
    group: 'nodes',
    data: { id, name: uniqueName('Department'), makespan: 1, demand: 0, congestion: 0, buffer: '' },
    position: { x: 80 + (k % 5) * 150, y: 90 + Math.floor(k / 5) * 110 },
  });
}

function addEdge(src, tgt) {
  const dup = cy.edges().filter(e => e.source().id() === src.id() && e.target().id() === tgt.id());
  if (dup.length) { cy.$(':selected').unselect(); dup.select(); return; }
  cy.add({ group: 'edges', data: { id: 'e' + (++counter), source: src.id(), target: tgt.id(), ratio: 1 } });
}

// ---- inspector ----
function field(label, key, val, numeric) {
  const type = numeric ? 'number' : 'text';
  const step = numeric ? 'step="any"' : '';
  return `<label>${label}<input data-key="${key}" type="${type}" ${step} value="${val ?? ''}"></label>`;
}

function bindInputs(el, target) {
  el.querySelectorAll('input').forEach(inp => {
    inp.addEventListener('input', () => target.data(inp.dataset.key, inp.value));
  });
}

function showNodeInspector(node) {
  const d = node.data();
  inspector.innerHTML = '<h4>Department</h4>'
    + field('Name', 'name', d.name)
    + field('Makespan (time / unit)', 'makespan', d.makespan, true)
    + field('Demand (units / period)', 'demand', d.demand, true)
    + field('Congestion β', 'congestion', d.congestion, true)
    + field('Buffer (max backlog, blank = none)', 'buffer', d.buffer, true);
  bindInputs(inspector, node);
}

function showEdgeInspector(edge) {
  inspector.innerHTML = `<h4>Flow: ${escapeHtml(edge.source().data('name'))} → ${escapeHtml(edge.target().data('name'))}</h4>`
    + field('Ratio (fraction of source output)', 'ratio', edge.data('ratio'), true);
  bindInputs(inspector, edge);
}

function clearInspector() {
  inspector.innerHTML = '<p class="muted">Select a node or edge to edit its parameters.</p>';
}

// ---- doc <-> canvas ----
function buildDoc() {
  const departments = cy.nodes().map(n => {
    const d = n.data(), p = n.position();
    return {
      name: d.name, makespan: num(d.makespan), demand: num(d.demand), congestion: num(d.congestion),
      buffer: (d.buffer === '' || d.buffer == null) ? null : num(d.buffer),
      x: Math.round(p.x), y: Math.round(p.y),
    };
  });
  const flows = cy.edges().map(e => ({
    from: e.source().data('name'), to: e.target().data('name'), ratio: num(e.data('ratio')),
  }));
  return {
    name: nameInput.value || 'design',
    settings: { time_per_employee: num(tInput.value), headcount: sInput.value === '' ? null : num(sInput.value) },
    departments, flows,
  };
}

function applyGraphStyles(graph) {
  const roots = new Set(graph.roots);
  cy.nodes().forEach(n => n[roots.has(n.data('name')) ? 'addClass' : 'removeClass']('root'));
  const rework = new Set(graph.edges.filter(e => e.is_rework).map(e => e.from + '' + e.to));
  cy.edges().forEach(e => {
    const key = e.source().data('name') + '' + e.target().data('name');
    e[rework.has(key) ? 'addClass' : 'removeClass']('rework');
  });
}

async function validate() {
  const doc = buildDoc();
  try {
    const r = await api('POST', '/api/validate', doc);
    applyGraphStyles(r.graph);
    const banner = r.ok ? '<div class="ok-banner">Design is mathematically sound.</div>' : '';
    diagnosticsEl.innerHTML = banner;
    const wrap = document.createElement('div');
    renderDiagnostics(wrap, r.diagnostics);
    diagnosticsEl.appendChild(wrap);
    return r.ok;
  } catch (err) {
    diagnosticsEl.innerHTML = `<div class="diag error">validation failed: ${escapeHtml(JSON.stringify(err.data))}</div>`;
    return false;
  }
}

async function save() {
  const doc = buildDoc();
  try {
    const r = await api('POST', '/api/designs', doc);
    window.DESIGN_ID = r.id;
    history.replaceState(null, '', '/builder/' + r.id);
    const note = r.ok ? '' : ' — invalid, fix before running';
    saveMsg.innerHTML = `Saved <b>${escapeHtml(r.id)}</b>${note} · `
      + `<a href="/designs">library</a> · <a href="/simulate/${r.id}">simulate</a>`;
    renderDiagnostics(diagnosticsEl, r.diagnostics);
  } catch (err) {
    saveMsg.innerHTML = `<span class="diag error">save failed: ${escapeHtml(JSON.stringify(err.data))}</span>`;
  }
}

async function loadDesign(id) {
  const doc = await api('GET', '/api/designs/' + id);
  nameInput.value = doc.name || '';
  tInput.value = (doc.settings && doc.settings.time_per_employee) ?? 480;
  sInput.value = (doc.settings && doc.settings.headcount != null) ? doc.settings.headcount : '';
  cy.elements().remove();
  const idByName = {};
  doc.departments.forEach((d, i) => {
    const id2 = 'n' + (++counter);
    idByName[d.name] = id2;
    cy.add({
      group: 'nodes',
      data: { id: id2, name: d.name, makespan: d.makespan, demand: d.demand, congestion: d.congestion,
              buffer: d.buffer == null ? '' : d.buffer },
      position: { x: d.x ?? (80 + (i % 5) * 150), y: d.y ?? (90 + Math.floor(i / 5) * 110) },
    });
  });
  doc.flows.forEach(f => cy.add({
    group: 'edges', data: { id: 'e' + (++counter), source: idByName[f.from], target: idByName[f.to], ratio: f.ratio },
  }));
  if (doc.departments.every(d => d.x == null)) {
    cy.layout({ name: 'breadthfirst', directed: true, spacingFactor: 1.3 }).run();
  }
  cy.fit(null, 40);
  validate();
}

// ---- events ----
document.getElementById('add-dept').onclick = addDept;
document.getElementById('delete-sel').onclick = () => { cy.$(':selected').remove(); clearInspector(); };
document.getElementById('validate-btn').onclick = validate;
document.getElementById('save-btn').onclick = save;
document.getElementById('link-mode').onclick = (e) => {
  linkMode = !linkMode; linkSource = null;
  e.target.classList.toggle('active', linkMode);
  cy.nodes().removeClass('bad');
};

cy.on('tap', 'node', (evt) => {
  if (!linkMode) return;
  const node = evt.target;
  if (!linkSource) { linkSource = node; node.addClass('bad'); }
  else { if (linkSource.id() !== node.id()) addEdge(linkSource, node);
         linkSource.removeClass('bad'); linkSource = null; linkMode = false;
         document.getElementById('link-mode').classList.remove('active'); }
});
cy.on('select', 'node', (e) => { if (!linkMode) showNodeInspector(e.target); });
cy.on('select', 'edge', (e) => showEdgeInspector(e.target));
cy.on('unselect', () => { if (cy.$(':selected').length === 0) clearInspector(); });

// ---- init ----
if (window.DESIGN_ID) {
  loadDesign(window.DESIGN_ID);
} else {
  addDept();
}
