/* Deployer — small UI helpers (no deps) */
(function () {
  // ---- Toasts ----
  function ensureToastWrap() {
    let w = document.querySelector('.toast-wrap');
    if (!w) {
      w = document.createElement('div');
      w.className = 'toast-wrap';
      document.body.appendChild(w);
    }
    return w;
  }
  window.toast = function (title, opts) {
    opts = opts || {};
    const t = document.createElement('div');
    t.className = 'toast ' + (opts.kind || '');
    t.innerHTML =
      '<div><strong></strong>' +
      (opts.detail ? '<small></small>' : '') +
      '</div>';
    t.querySelector('strong').textContent = title;
    if (opts.detail) t.querySelector('small').textContent = opts.detail;
    ensureToastWrap().appendChild(t);
    setTimeout(function () {
      t.style.transition = 'opacity 0.3s';
      t.style.opacity = '0';
      setTimeout(function () { t.remove(); }, 320);
    }, opts.timeout || 3500);
  };

  // Convert server-rendered .flash divs into toasts on load.
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-flash]').forEach(function (el) {
      window.toast(el.textContent.trim(), { kind: el.dataset.flash });
      el.remove();
    });
  });

  // ---- Drag & drop upload ----
  document.addEventListener('DOMContentLoaded', function () {
    const dz = document.querySelector('[data-dropzone]');
    if (!dz) return;
    const input = dz.querySelector('input[type=file]');
    const chosen = dz.querySelector('[data-file-chosen]');

    // Clicking the label natively opens the file picker — don't add a JS click
    // handler too, or the picker can open twice on some browsers.

    function setDrag(on) {
      return function (e) {
        e.preventDefault();
        e.stopPropagation();
        dz.classList.toggle('drag', on);
      };
    }
    dz.addEventListener('dragenter', setDrag(true));
    dz.addEventListener('dragover',  setDrag(true));
    dz.addEventListener('dragleave', setDrag(false));
    dz.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      dz.classList.remove('drag');
      const files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length) {
        try { input.files = files; } catch (_) { /* readonly in some browsers */ }
        showChosen(files[0]);
      }
    });
    input.addEventListener('change', function () {
      showChosen(input.files && input.files[0]);
    });

    function showChosen(file) {
      if (!chosen) return;
      if (!file) { chosen.textContent = ''; return; }
      const kb = file.size / 1024;
      const size = kb >= 1024
        ? (kb / 1024).toFixed(2) + ' MB'
        : kb.toFixed(1) + ' KB';
      chosen.textContent = file.name + ' · ' + size;
    }

    // Block the browser from opening the file when dropped outside the zone.
    ['dragover', 'drop'].forEach(function (ev) {
      window.addEventListener(ev, function (e) {
        if (!dz.contains(e.target)) e.preventDefault();
      });
    });
  });

  // ---- Copy-to-clipboard for snippets ----
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-copy]');
    if (!btn) return;
    const target = document.querySelector(btn.dataset.copy);
    if (!target) return;
    const text = target.innerText || target.textContent;
    navigator.clipboard.writeText(text).then(function () {
      const original = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(function () { btn.textContent = original; }, 1500);
    });
  });

  // ---- Snippet generator (form HTML) ----
  document.addEventListener('input', function (e) {
    if (!e.target.matches('[data-snippet-input]')) return;
    const root = e.target.closest('[data-snippet-root]');
    if (root) updateSnippet(root);
  });
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-snippet-root]').forEach(updateSnippet);
  });
  function updateSnippet(root) {
    const site = root.dataset.site;
    const formName = root.querySelector('[name=form_name]').value || 'contact';
    const fieldsRaw = root.querySelector('[name=fields]').value || 'email, message';
    const fields = fieldsRaw.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    const action = '/submit/' + site + '/' + formName;
    const lines = [];
    lines.push('<form action="' + action + '" method="POST">');
    fields.forEach(function (f) {
      const type = /email/i.test(f) ? 'email' : (/password/i.test(f) ? 'password' : 'text');
      lines.push('  <label>' + cap(f) + '<input type="' + type + '" name="' + f + '" required></label>');
    });
    lines.push('  <button type="submit">Send</button>');
    lines.push('</form>');
    root.querySelector('[data-snippet-out]').textContent = lines.join('\n');
  }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  // ---- Live polling for site detail page ----
  document.addEventListener('DOMContentLoaded', function () {
    const root = document.querySelector('[data-live-root]');
    if (!root) return;
    const site = root.dataset.site;
    const knownForms = {};
    const knownDatasets = {};

    // Seed from server-rendered counts so the first poll is silent.
    root.querySelectorAll('[data-form-block]').forEach(function (block) {
      const t = block.querySelector('[data-form-total]');
      knownForms[block.dataset.formBlock] = t ? parseInt(t.textContent, 10) || 0 : 0;
    });
    root.querySelectorAll('[data-dataset-block]').forEach(function (block) {
      const r = block.querySelector('[data-dataset-rev]');
      knownDatasets[block.dataset.datasetBlock] = r ? parseInt(r.textContent, 10) || 0 : 0;
    });

    async function tick() {
      let state;
      try {
        const r = await fetch('/api/sites/' + encodeURIComponent(site) + '/state',
                              { cache: 'no-store' });
        if (!r.ok) return;
        state = await r.json();
      } catch (e) { return; }
      markUpdated();

      // Forms — added/removed → reload (DOM scaffolding differs).
      const seenForms = new Set();
      let totalSubs = 0;
      for (const f of (state.forms || [])) {
        totalSubs += f.total;
        seenForms.add(f.name);
        if (!(f.name in knownForms)) { location.reload(); return; }
        if (knownForms[f.name] !== f.total) {
          await refreshForm(f.name, f.total);
          knownForms[f.name] = f.total;
        }
      }
      for (const name of Object.keys(knownForms)) {
        if (!seenForms.has(name)) { location.reload(); return; }
      }

      // Datasets — added/removed → reload; rev change → refresh.
      const seenDatasets = new Set();
      let totalItems = 0;
      for (const d of (state.datasets || [])) {
        totalItems += d.total;
        seenDatasets.add(d.name);
        if (!(d.name in knownDatasets)) { location.reload(); return; }
        if (knownDatasets[d.name] !== d.rev) {
          await refreshDataset(d.name, d.total, d.rev);
          knownDatasets[d.name] = d.rev;
        }
      }
      for (const name of Object.keys(knownDatasets)) {
        if (!seenDatasets.has(name)) { location.reload(); return; }
      }

      updateStats(state.forms.length, totalSubs, totalItems);
    }

    async function refreshForm(name, newTotal) {
      const r = await fetch('/api/sites/' + encodeURIComponent(site)
                          + '/forms/' + encodeURIComponent(name) + '/submissions',
                          { cache: 'no-store' });
      if (!r.ok) return;
      const data = await r.json();
      const block = root.querySelector('[data-form-block="' + cssEsc(name) + '"]');
      if (!block) { location.reload(); return; }
      const totalEl = block.querySelector('[data-form-total]');
      if (totalEl) totalEl.textContent = newTotal;
      renderTable(block.querySelector('[data-table-wrap]'), data.columns, data.rows,
                  function (row, i) { return (row._ts || '') + '|' + i; });
      window.toast('New submission · ' + name, { kind: 'ok' });
    }

    async function refreshDataset(name, newTotal, newRev) {
      const r = await fetch('/api/sites/' + encodeURIComponent(site)
                          + '/datasets/' + encodeURIComponent(name),
                          { cache: 'no-store' });
      if (!r.ok) return;
      const data = await r.json();
      const block = root.querySelector('[data-dataset-block="' + cssEsc(name) + '"]');
      if (!block) { location.reload(); return; }
      const totalEl = block.querySelector('[data-dataset-total]');
      const revEl   = block.querySelector('[data-dataset-rev]');
      if (totalEl) totalEl.textContent = newTotal;
      if (revEl)   revEl.textContent   = newRev;
      renderTable(block.querySelector('[data-dataset-table-wrap]'), data.columns, data.rows,
                  function (row) { return row.id; });
      window.toast('Dataset updated · ' + name, { kind: 'ok' });
    }

    function renderTable(wrap, columns, rows, keyOf) {
      if (!wrap) return;
      if (!rows.length) {
        wrap.innerHTML = '<div style="padding:18px; color:var(--text-muted);">No rows yet.</div>';
        return;
      }
      const existing = wrap.querySelector('table');
      const existingKeys = new Set();
      if (existing) {
        existing.querySelectorAll('tbody tr').forEach(function (tr) {
          existingKeys.add(tr.dataset.rowKey);
        });
      }
      const head = '<tr>' + columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
      const body = rows.map(function (row, i) {
        const key = String(keyOf(row, i));
        const isNew = existing && !existingKeys.has(key);
        const cells = columns.map(function (c) {
          const isMeta = c.charAt(0) === '_' || c === 'id';
          const cls = isMeta ? ' class="muted"' : '';
          return '<td' + cls + '>' + esc(row[c] == null ? '' : String(row[c])) + '</td>';
        }).join('');
        return '<tr data-row-key="' + esc(key) + '"' + (isNew ? ' class="flash-new"' : '') + '>' + cells + '</tr>';
      }).join('');
      wrap.innerHTML = '<table class="data">' +
        '<thead>' + head + '</thead><tbody>' + body + '</tbody></table>';
    }

    function updateStats(formsCount, subsCount, itemsCount) {
      const tiles = {
        forms: formsCount,
        submissions: subsCount,
        'dataset-items': itemsCount,
      };
      Object.keys(tiles).forEach(function (k) {
        const el = document.querySelector('[data-stat="' + k + '"]');
        if (el && tiles[k] !== undefined) el.textContent = tiles[k];
      });
    }

    function markUpdated() {
      const el = document.querySelector('[data-updated]');
      if (el) el.textContent = new Date().toLocaleTimeString();
    }

    function esc(s) {
      return String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }
    function cssEsc(s) { return s.replace(/(["\\])/g, '\\$1'); }

    setInterval(tick, 3000);
    tick();
  });

  // ---- Test-form panel: toggle + submit ----
  document.addEventListener('click', function (e) {
    const toggle = e.target.closest('[data-toggle-test]');
    if (toggle) {
      const name = toggle.dataset.toggleTest;
      const panel = document.querySelector('[data-test-panel="' + name.replace(/(["\\])/g, '\\$1') + '"]');
      if (panel) panel.hidden = !panel.hidden;
      return;
    }
    const addRow = e.target.closest('[data-add-test-row]');
    if (addRow) {
      const form = addRow.closest('form');
      const idx = form.querySelectorAll('.test-row').length - 1;
      const row = document.createElement('div');
      row.className = 'test-row';
      row.innerHTML =
        '<input name="__field_' + idx + '_k" placeholder="field name">' +
        '<input name="__field_' + idx + '_v" placeholder="value">';
      form.insertBefore(row, addRow.parentElement);
      return;
    }
    const addTestForm = e.target.closest('[data-add-test-form]');
    if (addTestForm) {
      const root = document.querySelector('[data-live-root]');
      const site = root && root.dataset.site;
      if (!site) return;
      // Submit a single starter row to the "contact" form so the section appears.
      fetch('/submit/' + encodeURIComponent(site) + '/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: 'hello@example.com', message: 'Hello from Deployer!' })
      }).then(function () { setTimeout(function () { location.reload(); }, 400); });
    }
  });

  document.addEventListener('submit', function (e) {
    const form = e.target.closest('[data-test-form]');
    if (!form) return;
    e.preventDefault();
    const site = form.dataset.site;
    const name = form.dataset.form;
    const rows = form.querySelectorAll('.test-row');
    const payload = {};
    rows.forEach(function (r) {
      const inputs = r.querySelectorAll('input');
      if (inputs.length === 2 && inputs[0].value.trim()) {
        payload[inputs[0].value.trim()] = inputs[1].value;
      }
    });
    if (!Object.keys(payload).length) {
      window.toast('Add at least one field', { kind: 'error' });
      return;
    }
    fetch('/submit/' + encodeURIComponent(site) + '/' + encodeURIComponent(name), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) {
      if (r.ok) window.toast('Test submission sent', { kind: 'ok' });
      else window.toast('Submission failed (' + r.status + ')', { kind: 'error' });
    }).catch(function () {
      window.toast('Network error', { kind: 'error' });
    });
  });
})();
