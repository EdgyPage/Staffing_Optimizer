// Analysis page: staffing split, feasibility, SHORT/OK/SLACK gaps, and basis vectors.

const id = window.DESIGN_ID;
const el = (x) => document.getElementById(x);
el('sim-link').href = '/simulate/' + id;

function card(label, value) {
  return `<div class="card"><div class="big">${value}</div><div class="lbl">${label}</div></div>`;
}

async function init() {
  let a;
  try {
    a = await api('GET', '/api/analysis/' + id);
  } catch (err) {
    const detail = err.data && err.data.detail;
    const msg = (detail && detail.message) || 'design is not valid';
    el('invalid').style.display = 'block';
    el('invalid').textContent = 'Cannot analyze: ' + msg + '. Fix it in the Builder.';
    return;
  }

  const f = a.feasibility;
  el('cards').innerHTML = [
    card('Required FTE', f.required_fte.toFixed(1)),
    card('Headcount', f.headcount == null ? '—' : f.headcount),
    card('Utilization', f.utilization == null ? '—' : (100 * f.utilization).toFixed(0) + '%'),
    card('Feasible', f.feasible == null ? '—' : (f.feasible ? 'YES' : 'SHORT ' + f.shortfall_fte.toFixed(1))),
  ].join('');

  document.querySelector('#gaps tbody').innerHTML = a.names.map((n, i) => {
    const g = a.gaps[i];
    const sign = g.gap_fte >= 0 ? '+' : '';
    return `<tr><td>${escapeHtml(n)}</td><td>${a.throughput[i].toFixed(0)}</td>
      <td>${a.required_fte[i].toFixed(2)}</td><td>${(100 * a.split[i]).toFixed(1)}</td>
      <td>${a.suggested[i].toFixed(2)}</td><td>${sign}${g.gap_fte.toFixed(2)}</td>
      <td class="status-${g.status}">${g.status}</td></tr>`;
  }).join('');

  const roots = a.basis.roots;
  el('basis').innerHTML =
    '<thead><tr><th>Department</th>' + roots.map(r => `<th>${escapeHtml(r)}</th>`).join('') + '</tr></thead><tbody>'
    + a.names.map((n, i) => `<tr><td>${escapeHtml(n)}</td>`
        + roots.map((r, j) => `<td>${a.basis.matrix[i][j].toFixed(4)}</td>`).join('') + '</tr>').join('')
    + '</tbody>';
}

init();
