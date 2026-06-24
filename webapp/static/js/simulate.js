// Simulation page: render the (read-only) diagram, run the sim, and play it back step by step.

const id = window.DESIGN_ID;
const PALETTE = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                 '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'];

const el = (x) => document.getElementById(x);
el('analyze-link').href = '/analyze/' + id;

let cy, backlogChart, makespanChart;
let series = null, frame = 0, playing = false, timer = null, globalMax = 1;

function toElements(doc, graph) {
  const roots = new Set(graph.roots);
  const rework = new Set(graph.edges.filter(e => e.is_rework).map(e => e.from + '' + e.to));
  const nodes = doc.departments.map(d => ({
    data: { id: d.name, name: d.name },
    classes: roots.has(d.name) ? 'root' : '',
    position: d.x != null ? { x: d.x, y: d.y } : undefined,
  }));
  const edges = doc.flows.map((f, i) => ({
    data: { id: 'e' + i, source: f.from, target: f.to, ratio: f.ratio },
    classes: rework.has(f.from + '' + f.to) ? 'rework' : '',
  }));
  return [...nodes, ...edges];
}

async function init() {
  const doc = await api('GET', '/api/designs/' + id);
  el('title').textContent = 'Simulate · ' + (doc.name || id);
  const v = await api('POST', '/api/validate', doc);
  const preset = doc.departments.every(d => d.x == null)
    ? { name: 'breadthfirst', directed: true, spacingFactor: 1.3 } : { name: 'preset' };
  cy = cytoscape({ container: el('cy'), style: cyStyle(), elements: toElements(doc, v.graph), layout: preset });
  cy.fit(null, 30);
  cy.userPanningEnabled(true); cy.boxSelectionEnabled(false); cy.autolock(true);
  if (!v.ok) {
    el('invalid').style.display = 'block';
    el('invalid').innerHTML = 'This design is not valid, so it cannot run — fix it in the Builder.<br>'
      + v.diagnostics.filter(d => d.severity === 'error').map(d => escapeHtml(d.message)).join('<br>');
    el('run').disabled = true;
  }
}

function makeChart(canvasId, title) {
  return new Chart(el(canvasId), {
    type: 'line',
    data: { labels: [], datasets: series.names.map((n, i) => ({
      label: n, data: [], borderColor: PALETTE[i % PALETTE.length], borderWidth: 1.5, pointRadius: 0, fill: false })) },
    options: { animation: false, responsive: true, interaction: { mode: 'nearest' },
      plugins: { title: { display: true, text: title }, legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
      scales: { x: { title: { display: true, text: 'period' } } } },
  });
}

function setupCharts() {
  if (backlogChart) backlogChart.destroy();
  if (makespanChart) makespanChart.destroy();
  backlogChart = makeChart('backlog-chart', 'Backlog (units)');
  makespanChart = makeChart('makespan-chart', 'Effective makespan (time/unit)');
}

function updateChart(chart, labels, data, upto) {
  chart.data.labels = labels;
  chart.data.datasets.forEach((ds, i) => { ds.data = data.slice(0, upto).map(row => row[i]); });
  chart.update();
}

function renderFrame() {
  const upto = frame + 1;
  const labels = series.times.slice(0, upto).map(t => t.toFixed(1));
  updateChart(backlogChart, labels, series.backlog, upto);
  updateChart(makespanChart, labels, series.effective_makespan, upto);
  series.names.forEach((n, i) => {
    cy.getElementById(n).style('background-color', heatColor(series.backlog[frame][i] / globalMax));
  });
  el('cursor').value = frame;
  el('tlabel').textContent = `t = ${series.times[frame].toFixed(2)}  (${frame + 1}/${series.times.length})`;
}

function step(delta) {
  if (!series) return;
  frame = Math.max(0, Math.min(series.times.length - 1, frame + delta));
  renderFrame();
}

function togglePlay() {
  if (!series) return;
  playing = !playing;
  el('play').textContent = playing ? '⏸ Pause' : '▶ Play';
  if (!playing) { clearInterval(timer); return; }
  timer = setInterval(() => {
    if (frame >= series.times.length - 1) { togglePlay(); return; }
    step(1);
  }, 60);
}

async function run() {
  const params = {
    staffing: el('staffing').value, scale: num(el('scale').value),
    dt: num(el('dt').value), horizon: num(el('horizon').value), backpressure_band: num(el('band').value),
  };
  el('status').textContent = 'running…';
  try {
    series = await api('POST', '/api/simulate/' + id, params);
  } catch (err) {
    el('status').textContent = 'simulate failed: ' + JSON.stringify(err.data);
    return;
  }
  globalMax = Math.max(1, ...series.backlog.map(row => Math.max(...row)));
  setupCharts();
  el('cursor').max = series.times.length - 1;
  frame = 0;
  renderFrame();
  const verdict = series.diverging.length ? ('diverging at: ' + series.diverging.join(', ')) : 'all stable';
  el('status').textContent = `${series.times.length} frames · ${verdict}`;
}

el('run').onclick = run;
el('step-fwd').onclick = () => step(1);
el('step-back').onclick = () => step(-1);
el('play').onclick = togglePlay;
el('cursor').oninput = (e) => { frame = num(e.target.value); if (series) renderFrame(); };

init();
