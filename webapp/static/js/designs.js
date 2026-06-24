// Saved-designs library: list, open/simulate/analyze, export, import, delete.

const tbody = document.querySelector('#designs-table tbody');

function exportLinks(id) {
  return ['json', 'flow', 'yaml']
    .map(fmt => `<a href="/api/designs/${id}/export?format=${fmt}">${fmt}</a>`)
    .join('/');
}

async function refresh() {
  const items = await api('GET', '/api/designs');
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="muted">No designs yet — build one in the Builder.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map(it => {
    const badge = it.valid === false ? '<span class="badge invalid">invalid</span>'
      : it.valid === true ? '<span class="badge valid">valid</span>' : '';
    const sim = it.valid === false ? '<span class="muted">Simulate</span>' : `<a href="/simulate/${it.id}">Simulate</a>`;
    const ana = it.valid === false ? '<span class="muted">Analyze</span>' : `<a href="/analyze/${it.id}">Analyze</a>`;
    const created = (it.created_at || '').replace('T', ' ');
    return `<tr>
      <td>${escapeHtml(it.name || it.id)}</td>
      <td class="muted">${escapeHtml(created)}</td>
      <td>${badge}</td>
      <td><a href="/builder/${it.id}">Open</a> · ${sim} · ${ana}
        · <span class="muted">export:</span> ${exportLinks(it.id)}
        · <a href="#" data-del="${it.id}">Delete</a></td>
    </tr>`;
  }).join('');

  tbody.querySelectorAll('[data-del]').forEach(a => {
    a.onclick = async (e) => {
      e.preventDefault();
      if (!confirm('Delete this design?')) return;
      await api('DELETE', '/api/designs/' + a.dataset.del);
      refresh();
    };
  });
}

document.getElementById('import-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/designs/import', { method: 'POST', body: fd });
  if (!res.ok) alert('Import failed: ' + (await res.text()));
  e.target.value = '';
  refresh();
});

refresh();
