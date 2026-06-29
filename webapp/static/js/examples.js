// Examples gallery: list bundled examples and "open a copy" into the builder as a fresh draft.

const DRAFT_KEY = 'staffing:builder:draft';
const gallery = document.getElementById('examples');

function draftHasWork() {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY));
    return !!(d && d.doc && d.doc.departments && d.doc.departments.length > 1);
  } catch (e) { return false; }
}

async function openCopy(id) {
  if (draftHasWork() && !confirm('Open this example? It will replace your current builder draft.')) return;
  const doc = await api('GET', '/api/examples/' + id);
  delete doc.created_at;
  delete doc.valid;
  // Seed the builder's working draft (a fresh, unsaved copy) and go to the builder.
  localStorage.setItem(DRAFT_KEY, JSON.stringify({ sourceId: null, doc }));
  location.href = '/builder';
}

async function init() {
  const items = await api('GET', '/api/examples');
  if (!items.length) { gallery.innerHTML = '<p class="muted">No examples found.</p>'; return; }
  gallery.innerHTML = items.map(it => `
    <div class="card example">
      <h3>${escapeHtml(it.name)}</h3>
      <p class="muted">${escapeHtml(it.description || '')}</p>
      <button class="primary" data-id="${escapeHtml(it.id)}">Open a copy</button>
    </div>`).join('');
  gallery.querySelectorAll('button[data-id]').forEach(b => { b.onclick = () => openCopy(b.dataset.id); });
}

init();
