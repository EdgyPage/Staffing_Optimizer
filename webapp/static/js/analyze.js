// Analyze page: steady-state staffing (the inverse solve) + capacity at a given staffing (forward).

const id = window.DESIGN_ID;
const el = (x) => document.getElementById(x);
el('sim-link').href = '/simulate/' + id;
let A = null;

function card(label, value) {
  return `<div class="card"><div class="big">${value}</div><div class="lbl">${label}</div></div>`;
}

function renderSteadyState() {
  const f = A.feasibility;
  el('cards').innerHTML = [
    card('Required FTE', f.required_fte.toFixed(1)),
    card('Headcount', f.headcount == null ? '—' : f.headcount),
    card('Utilization', f.utilization == null ? '—' : (100 * f.utilization).toFixed(0) + '%'),
    card('Feasible', f.feasible == null ? '—' : (f.feasible ? 'YES' : 'SHORT ' + f.shortfall_fte.toFixed(1))),
  ].join('');

  document.querySelector('#gaps tbody').innerHTML = A.names.map((n, i) => {
    const g = A.gaps[i];
    const sign = g.gap_fte >= 0 ? '+' : '';
    return `<tr><td>${escapeHtml(n)}</td><td>${A.throughput[i].toFixed(0)}</td>
      <td>${A.required_fte[i].toFixed(2)}</td><td>${(100 * A.split[i]).toFixed(1)}</td>
      <td>${A.suggested[i].toFixed(2)}</td><td>${sign}${g.gap_fte.toFixed(2)}</td>
      <td class="status-${g.status}">${g.status}</td></tr>`;
  }).join('');

  const roots = A.basis.roots;
  el('basis').innerHTML =
    '<thead><tr><th>Department</th>' + roots.map(r => `<th>${escapeHtml(r)}</th>`).join('') + '</tr></thead><tbody>'
    + A.names.map((n, i) => `<tr><td>${escapeHtml(n)}</td>`
        + roots.map((r, j) => `<td>${A.basis.matrix[i][j].toFixed(4)}</td>`).join('') + '</tr>').join('')
    + '</tbody>';
}

function buildCapacity() {
  document.querySelector('#capacity tbody').innerHTML = A.names.map((n, i) => `
    <tr>
      <td>${escapeHtml(n)}</td>
      <td><input class="cap-in" data-i="${i}" type="number" min="0" step="0.5" value="${round3(A.suggested[i])}"></td>
      <td id="cap-${i}"></td><td>${A.throughput[i].toFixed(0)}</td>
      <td id="util-${i}"></td><td id="st-${i}"></td>
    </tr>`).join('');
  document.querySelectorAll('.cap-in').forEach(inp => inp.addEventListener('input', recomputeCapacity));
  recomputeCapacity();
}

function recomputeCapacity() {
  const t = A.time_per_employee;
  let worst = -1, worstU = -Infinity;
  A.names.forEach((n, i) => {
    const staffing = num(document.querySelector(`.cap-in[data-i="${i}"]`).value);
    const cap = A.makespan[i] > 0 ? staffing * t / A.makespan[i] : 0;
    const util = cap > 0 ? A.throughput[i] / cap : Infinity;
    if (util > worstU) { worstU = util; worst = i; }
    el('cap-' + i).textContent = cap.toFixed(0);
    el('util-' + i).textContent = isFinite(util) ? (100 * util).toFixed(0) + '%' : '∞';
    el('st-' + i).innerHTML = util > 1.0001
      ? '<span class="status-SHORT">OVER</span>' : '<span class="status-OK">ok</span>';
  });
  el('bottleneck').innerHTML = worst < 0 ? ''
    : `Bottleneck: <b>${escapeHtml(A.names[worst])}</b> at `
      + `${isFinite(worstU) ? (100 * worstU).toFixed(0) + '%' : '∞'} utilization`
      + (worstU > 1.0001 ? ' — over capacity.' : '.');
}

async function init() {
  try {
    A = await api('GET', '/api/analysis/' + id);
  } catch (err) {
    const detail = err.data && err.data.detail;
    el('invalid').style.display = 'block';
    el('invalid').textContent = 'Cannot analyze: ' + ((detail && detail.message) || 'design is not valid')
      + '. Fix it in the Builder.';
    return;
  }
  renderSteadyState();
  buildCapacity();
}

init();
