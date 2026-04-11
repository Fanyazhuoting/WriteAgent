/* ═══════════════════════════════════════════
   WriteAgent — Frontend Logic
   ═══════════════════════════════════════════ */

const API = '/api/v1';
const POLL_MS = 3000;

// ─── Per-novel stores ─────────────────────────
const proseStore    = {};   // { [novelId]: string }       — accumulated prose
const settingsStore = {};   // { [novelId]: settings obj } — form state per novel

// ─── State ───────────────────────────────────
const state = {
  activeTab:     'writer',
  activeNovelId: null,
  novels:        [],
  sceneNumber:   0,
  simulation:    null,
  genStartTime:  0,
  isGenerating:  false,
  currentStage:  'world',
};

// ─── Helpers ─────────────────────────────────
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function setStatus(id, msg, type = '') {
  const el = $(id);
  if (!el) return;
  el.textContent = msg;
  el.className = `status-bar${type ? ' ' + type : ''}`;
}

// CJK-aware word count
function countWords(text) {
  if (!text || !text.trim()) return 0;
  const cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]/g) || []).length;
  const stripped = text.replace(/[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]/g, ' ');
  const latin = stripped.trim().split(/\s+/).filter(w => /\S/.test(w)).length;
  return cjk + latin;
}

// ─── Language Toggle ──────────────────────────

// Lock / unlock genre, style, and language inputs once a novel is started
function lockNovelSettings(locked) {
  $('genreInput').disabled = locked;
  $('styleInput').disabled = locked;
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.disabled = locked;
    btn.style.pointerEvents = locked ? 'none' : '';
    btn.style.opacity = locked ? '0.5' : '';
  });
  // Visual hint on the fields
  const hint = $('settingsLockedHint');
  if (hint) hint.style.display = locked ? 'block' : 'none';
}

function getSelectedLanguage() {
  const active = document.querySelector('.lang-btn.active');
  return active ? active.dataset.lang : 'English';
}

function setSelectedLanguage(lang) {
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });
}

document.querySelectorAll('.lang-btn').forEach(btn => {
  btn.addEventListener('click', () => setSelectedLanguage(btn.dataset.lang));
});

// ─── Per-novel Settings: save / restore ───────
function saveCurrentSettings() {
  if (!state.activeNovelId) return;
  settingsStore[state.activeNovelId] = {
    genre:    $('genreInput').value,
    style:    $('styleInput').value,
    brief:    $('sceneBriefInput').value,
    language: getSelectedLanguage(),
    chars:    collectCharacters(),
    rules:    collectRules(),
  };
}

function restoreSettings(id) {
  const s = settingsStore[id];

  // No saved settings → show empty form with one blank row each
  if (!s) {
    $('genreInput').value  = '';
    $('styleInput').value  = '';
    $('sceneBriefInput').value = '';
    $('briefCharCount').textContent = '0 chars';
    $('charsList').innerHTML = '';
    $('rulesList').innerHTML = '';
    _addCharEditRow();
    addRuleRow();
    return;
  }

  $('genreInput').value  = s.genre || '';
  $('styleInput').value  = s.style || '';
  $('sceneBriefInput').value = s.brief || '';
  setSelectedLanguage(s.language || 'English');
  $('briefCharCount').textContent = `${(s.brief || '').length} chars`;

  // Restore characters as cards
  $('charsList').innerHTML = '';
  (s.chars || []).forEach(c => {
    $('charsList').appendChild(buildCharCard(c.name, c.description || '', c.gender || 'unknown'));
  });
  if (!s.chars || s.chars.length === 0) _addCharEditRow();

  // Restore rules
  $('rulesList').innerHTML = '';
  (s.rules || []).forEach(r => addRuleRow(r.description, r.severity));
  if (!s.rules || s.rules.length === 0) addRuleRow();
}

// ─── Tab Navigation ───────────────────────────
function switchTab(name) {
  state.activeTab = name;
  document.querySelectorAll('.tab-link').forEach(el =>
    el.classList.toggle('active', el.dataset.tab === name)
  );
  document.querySelectorAll('.tab-content').forEach(el => {
    const isThis = el.id === `tab-${name}`;
    el.classList.toggle('hidden', !isThis);
    el.classList.toggle('active', isThis);
  });
  const rgBtn = $('refreshGraphBtn');
  if (name === 'worldgraph') rgBtn.classList.remove('hidden');
  else rgBtn.classList.add('hidden');

  if (state.activeNovelId) {
    if (name === 'worldgraph') loadGraph();
    if (name === 'process')    loadProcess();
    if (name === 'audit')      loadAudit();
  }
}

$('tabNav').addEventListener('click', e => {
  const link = e.target.closest('.tab-link');
  if (link) switchTab(link.dataset.tab);
});

// ─── Settings Lock ────────────────────────────
function lockNovelSettings(locked) {
  const panel = document.querySelector('.w-panel');
  if (panel) panel.classList.toggle('settings-locked', locked);
  $('startNovelBtn').disabled = locked;
  $('settingsLockedHint').style.display = locked ? 'block' : 'none';
}

// ─── Sidebar — Novel List ─────────────────────
function addNovel(id, name, sceneNum = 1) {
  if (state.novels.find(n => n.id === id)) return;
  state.novels.push({ id, name: name || `ID: ${id.slice(0, 8)}`, sceneNumber: sceneNum });
  renderNovelList();
}

function renderNovelList() {
  const list = $('novelList');
  list.innerHTML = '';
  state.novels.forEach(novel => {
    const el = document.createElement('div');
    el.className = 'novel-item' + (novel.id === state.activeNovelId ? ' active' : '');
    el.dataset.id = novel.id;
    el.innerHTML = `
      <svg class="novel-item-icon" width="12" height="15" viewBox="0 0 12 15" fill="none">
        <rect x="1" y="1" width="10" height="13" rx="2" stroke="currentColor" stroke-width="1.2"/>
        <path d="M3.5 5h5M3.5 8h3.5" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
      </svg>
      <span class="novel-item-name">${esc(novel.name)}</span>
      <button type="button" class="novel-rename-btn" title="Rename">✎</button>
      <button type="button" class="novel-delete-btn" title="Delete novel">🗑</button>
    `;
    el.querySelector('.novel-item-name').addEventListener('click', () => selectNovel(novel.id));
    el.querySelector('.novel-rename-btn').addEventListener('click', e => {
      e.stopPropagation();
      startRename(novel.id, el);
    });
    el.querySelector('.novel-delete-btn').addEventListener('click', e => {
      e.stopPropagation();
      deleteNovel(novel.id);
    });
    list.appendChild(el);
  });
}

function startRename(id, el) {
  const novel = state.novels.find(n => n.id === id);
  if (!novel) return;
  const nameSpan  = el.querySelector('.novel-item-name');
  const renameBtn = el.querySelector('.novel-rename-btn');
  nameSpan.style.display  = 'none';
  renameBtn.style.display = 'none';
  const input = document.createElement('input');
  input.type      = 'text';
  input.className = 'novel-rename-input';
  input.value     = novel.name;
  el.insertBefore(input, renameBtn);
  input.focus();
  input.select();
  const commit = () => {
    const newName = input.value.trim() || novel.name;
    novel.name = newName;
    el.removeChild(input);
    nameSpan.style.display  = '';
    renameBtn.style.display = '';
    renderNovelList();
  };
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { e.preventDefault(); el.removeChild(input); nameSpan.style.display = ''; renameBtn.style.display = ''; }
  });
  input.addEventListener('blur', commit);
}

function deleteNovel(id) {
  const novel = state.novels.find(n => n.id === id);
  if (!novel) return;
  if (!confirm(`Delete "${novel.name}"?\n\nThis removes it from this session. Generated prose will be lost.`)) return;
  // Remove from stores
  delete proseStore[id];
  delete settingsStore[id];
  state.novels = state.novels.filter(n => n.id !== id);
  if (state.activeNovelId === id) {
    // Switch to another novel or reset
    const next = state.novels[state.novels.length - 1];
    if (next) {
      state.activeNovelId = null; // force selectNovel to proceed
      selectNovel(next.id);
    } else {
      resetToNewNovel();
    }
  } else {
    renderNovelList();
  }
}

// Fix 2: save current settings, then restore new novel's settings
function selectNovel(id) {
  if (id === state.activeNovelId) return;

  // Persist form state of the outgoing novel
  saveCurrentSettings();

  state.activeNovelId = id;
  state.sceneNumber   = 0;

  const novel = state.novels.find(n => n.id === id);
  $('novelIdText').textContent = `Novel ID: ${id.slice(0, 6)}…`;
  $('sceneBadge').textContent  = `S${novel?.sceneNumber ?? 1}`;

  renderNovelList();

  // Restore this novel's form + prose, then lock settings
  restoreSettings(id);
  lockNovelSettings(true);
  updateProseDisplay();
  setStatus('startStatus', '', '');

  if (state.activeTab === 'worldgraph') loadGraph();
  if (state.activeTab === 'process')    loadProcess();
  if (state.activeTab === 'audit')      loadAudit();
}

$('copyNovelId').addEventListener('click', () => {
  if (state.activeNovelId) navigator.clipboard.writeText(state.activeNovelId).catch(() => {});
});

// Fix 1 + 4: New Novel resets writer AND clears all other tabs
function clearOtherTabs() {
  // World graph
  if (typeof gEl !== 'undefined' && gEl) gEl.selectAll('*').remove();
  $('focusCard').classList.add('hidden');
  $('graphEmpty').style.display = 'flex';
  // Process & Audit
  $('xaiTimeline').innerHTML = '<div class="empty-state">Select a novel to view agent reasoning.</div>';
  $('auditTable').innerHTML     = '<div class="empty-state">Select a novel to view the audit trail.</div>';
}

function resetToNewNovel() {
  // Save outgoing novel
  saveCurrentSettings();

  state.activeNovelId = null;
  state.sceneNumber   = 0;

  // Header
  $('novelIdText').textContent = 'Novel ID: —';
  $('sceneBadge').textContent  = 'S1';

  // Form fields
  $('genreInput').value        = '';
  $('styleInput').value        = '';
  $('sceneBriefInput').value   = '';
  $('briefCharCount').textContent = '0 chars';
  setSelectedLanguage('English');
  $('charsList').innerHTML     = '';
  $('rulesList').innerHTML     = '';
  _addCharEditRow();
  addRuleRow();

  // Clear statuses
  setStatus('startStatus',  '', '');
  setStatus('injectStatus', '', '');

  // Pipeline hidden
  showPipeline(false);

  // Unlock settings for new novel
  lockNovelSettings(false);

  // Clear prose display
  updateProseDisplay();

  // Clear graph + table tabs
  clearOtherTabs();

  // Highlight nothing in sidebar
  renderNovelList();

  switchTab('writer');
}

$('newNovelBtn').addEventListener('click', resetToNewNovel);

// ─── Character Card System ─────────────────────
const GENDER_LABELS = { male: 'Male', female: 'Female', unknown: 'Unknown' };
const GENDER_COLORS = { male: '#60a5fa', female: '#f472b6', unknown: '#94a3b8' };

function buildCharCard(name, desc, gender = 'unknown') {
  const card = document.createElement('div');
  card.className      = 'char-card';
  card.dataset.name   = name;
  card.dataset.desc   = desc;
  card.dataset.gender = gender;
  const initial    = name.charAt(0).toUpperCase();
  const gLabel     = GENDER_LABELS[gender] || '不详';
  const gColor     = GENDER_COLORS[gender] || '#94a3b8';
  card.innerHTML = `
    <div class="char-card-avatar" style="background:${gColor}22;border-color:${gColor}44">${esc(initial)}</div>
    <div class="char-card-body">
      <div class="char-card-name">${esc(name)} <span style="font-size:10px;color:${gColor};font-weight:500;margin-left:4px">${gLabel}</span></div>
      <div class="char-card-desc">${esc(desc || 'No description')}</div>
    </div>
    <div class="char-card-actions">
      <button type="button" class="char-card-edit" title="Edit">✎</button>
      <button type="button" class="char-card-del"  title="Remove">×</button>
    </div>
  `;
  card.querySelector('.char-card-edit').addEventListener('click', () => {
    const editRow = buildCharEditRow(name, desc, gender);
    card.parentElement.replaceChild(editRow, card);
    editRow.querySelector('.char-name').focus();
  });
  card.querySelector('.char-card-del').addEventListener('click', () => {
    card.parentElement && card.parentElement.removeChild(card);
  });
  return card;
}

function buildCharEditRow(name = '', desc = '', gender = 'unknown') {
  const row = document.createElement('div');
  row.className = 'entity-row';
  row.innerHTML = `
    <div class="entity-row-fields">
      <div class="entity-field">
        <span class="entity-field-label">Character Name</span>
        <input type="text" class="entity-input char-name" placeholder="e.g. Elena Thorne" value="${esc(name)}">
      </div>
      <div class="entity-row-fields-inline" style="margin-top:6px;gap:8px">
        <div class="entity-field entity-field-grow">
          <span class="entity-field-label">Description / Role</span>
          <input type="text" class="entity-input char-desc" placeholder="e.g. A disgraced lawyer, calm under pressure" value="${esc(desc)}">
        </div>
        <div class="entity-field entity-field-fixed">
          <span class="entity-field-label">Gender</span>
          <select class="severity-select char-gender">
            <option value="male"${gender === 'male' ? ' selected' : ''}>Male</option>
            <option value="female"${gender === 'female' ? ' selected' : ''}>Female</option>
            <option value="unknown"${gender === 'unknown' ? ' selected' : ''}>Unknown</option>
          </select>
        </div>
      </div>
    </div>
    <button type="button" class="btn-remove-entity" title="Remove">×</button>
  `;
  const saveOnEnter = e => {
    if (e.key === 'Enter') { e.preventDefault(); saveCharRow(row); }
  };
  row.querySelector('.char-name').addEventListener('keydown', saveOnEnter);
  row.querySelector('.char-desc').addEventListener('keydown', saveOnEnter);
  row.querySelector('.btn-remove-entity').addEventListener('click', () => {
    row.parentElement && row.parentElement.removeChild(row);
  });
  return row;
}

function saveCharRow(row) {
  const name   = row.querySelector('.char-name')?.value.trim();
  const desc   = row.querySelector('.char-desc')?.value.trim() || '';
  const gender = row.querySelector('.char-gender')?.value || 'unknown';
  if (!name) {
    row.parentElement && row.parentElement.removeChild(row);
    return;
  }
  const card = buildCharCard(name, desc, gender);
  row.parentElement.replaceChild(card, row);
}

// Internal: add a raw edit row without saving existing rows
function _addCharEditRow(name = '', desc = '', gender = 'unknown') {
  const row = buildCharEditRow(name, desc, gender);
  $('charsList').appendChild(row);
  return row;
}

// Public: clicking "Add Character" — save open edit rows first, then open new
function addCharRow() {
  // Save any currently-open edit rows
  Array.from($('charsList').querySelectorAll('.entity-row')).forEach(saveCharRow);
  // Add fresh edit row
  const row = _addCharEditRow();
  row.querySelector('.char-name').focus();
}

function collectCharacters() {
  const results = [];
  $('charsList').querySelectorAll('.char-card').forEach(card => {
    const name   = (card.dataset.name   || '').trim();
    const gender = card.dataset.gender  || 'unknown';
    if (name) results.push({ name, description: (card.dataset.desc || '').trim(), gender });
  });
  $('charsList').querySelectorAll('.entity-row').forEach(row => {
    const name   = (row.querySelector('.char-name')?.value  || '').trim();
    const desc   = (row.querySelector('.char-desc')?.value  || '').trim();
    const gender = row.querySelector('.char-gender')?.value || 'unknown';
    if (name) results.push({ name, description: desc, gender });
  });
  return results;
}

$('addCharBtn').addEventListener('click', () => addCharRow());

// ─── World Rule Rows ──────────────────────────
function addRuleRow(desc = '', severity = 'soft') {
  const container = $('rulesList');
  const row = document.createElement('div');
  row.className = 'entity-row';
  row.innerHTML = `
    <div class="entity-row-fields-inline">
      <div class="entity-field entity-field-grow">
        <span class="entity-field-label">Description</span>
        <input type="text" class="entity-input rule-desc" placeholder="e.g. Magic requires rare crystals" value="${esc(desc)}">
      </div>
      <div class="entity-field entity-field-fixed">
        <span class="entity-field-label">Severity</span>
        <select class="severity-select rule-severity">
          <option value="soft"${severity === 'soft'     ? ' selected' : ''}>Soft</option>
          <option value="hard"${severity === 'hard'     ? ' selected' : ''}>Hard</option>
          <option value="absolute"${severity === 'absolute' ? ' selected' : ''}>Absolute</option>
        </select>
      </div>
    </div>
    <button type="button" class="btn-remove-entity" title="Remove">×</button>
  `;
  row.querySelector('.btn-remove-entity').addEventListener('click', () => {
    if (container.children.length > 1) container.removeChild(row);
  });
  container.appendChild(row);
}

function collectRules() {
  return Array.from($('rulesList').querySelectorAll('.entity-row')).map(row => ({
    description: (row.querySelector('.rule-desc')?.value || '').trim(),
    severity:     row.querySelector('.rule-severity')?.value || 'soft',
  })).filter(r => r.description);
}

$('addRuleBtn').addEventListener('click', () => addRuleRow());

// ─── Scene Brief Char Count ───────────────────
$('sceneBriefInput').addEventListener('input', function() {
  $('briefCharCount').textContent = `${this.value.length} chars`;
});

// (Inject panel is always visible — no toggle needed)

// ─── Novel API ────────────────────────────────
async function apiStartNovel(genre, style, firstBrief, outputLanguage, chars, rules) {
  const resp = await fetch(`${API}/novel/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      genre:               genre  || 'Fantasy',
      style_guide:         style  || 'Third-person limited',
      first_scene_brief:   firstBrief || ' ',
      output_language:     outputLanguage || 'English',
      initial_characters:  chars,
      initial_world_rules: rules,
    }),
  });
  if (!resp.ok) {
    const raw = await resp.text();
    let detail = raw;
    try { detail = JSON.parse(raw)?.detail || raw; } catch {}
    throw new Error(`HTTP ${resp.status}: ${detail}`);
  }
  return resp.json();
}

// ─── Start Novel ─────────────────────────────
$('startNovelBtn').addEventListener('click', async () => {
  const genre      = $('genreInput').value.trim();
  const style      = $('styleInput').value.trim();
  const firstBrief = $('sceneBriefInput').value.trim();
  const language   = getSelectedLanguage();
  const chars      = collectCharacters();
  const rules      = collectRules();

  if (!firstBrief && chars.length === 0) {
    setStatus('startStatus', 'Enter a scene brief or add characters to begin.', 'error');
    return;
  }

  const btn = $('startNovelBtn');
  btn.disabled = true;
  setStatus('startStatus', 'Creating novel…', 'loading');

  try {
    const data = await apiStartNovel(
      genre || 'Fantasy',
      style || 'Third-person limited',
      firstBrief,
      language,
      chars,
      rules,
    );
    const novelName = chars[0]?.name
      ? `${chars[0].name}'s Story`
      : (firstBrief.split(/\s+/).slice(0, 4).join(' ') + '…');

    // Pre-populate settings store so restoreSettings shows the right values
    settingsStore[data.novel_id] = { genre, style, brief: firstBrief, language, chars, rules };

    addNovel(data.novel_id, novelName, 1);
    selectNovel(data.novel_id);
    // Button stays disabled via lockNovelSettings(true) inside selectNovel
    setStatus('startStatus', `Novel started — ID: ${data.novel_id.slice(0, 8)}…`, 'success');
  } catch (err) {
    setStatus('startStatus', `Error: ${err.message}`, 'error');
    btn.disabled = false; // Re-enable only on failure
  }
});

// ─── Agent Pipeline ───────────────────────────
const STAGES    = ['world', 'char', 'plot', 'logic', 'narr'];
const STAGE_MS  = { world: 0, char: 12000, plot: 28000, logic: 52000, narr: 82000 };
const STAGE_LABELS = {
  world: 'Building world context…',
  char:  'Loading character memories…',
  plot:  'Drafting scene narrative…',
  logic: 'Checking consistency…',
  narr:  'Polishing final prose…',
};

function showPipeline(show) {
  $('agentPipeline').classList.toggle('hidden', !show);
}

function setPipelineState(currentStage) {
  state.currentStage = currentStage;
  const currentIdx = STAGES.indexOf(currentStage);
  STAGES.forEach((s, i) => {
    const el = $(`stage-${s}`);
    if (!el) return;
    el.className = 'p-stage ' + (i < currentIdx ? 'done' : i === currentIdx ? 'active' : 'pending');
  });
  document.querySelectorAll('.p-connector').forEach(conn => {
    const idx = parseInt(conn.dataset.idx, 10);
    conn.className = 'p-connector ' + (idx < currentIdx ? 'done' : idx === currentIdx ? 'loading' : 'pending');
  });
  $('pipelineStatus').textContent = STAGE_LABELS[currentStage] || 'Processing…';
  updateProcessLiveBanner();
}

function setPipelineAllDone() {
  STAGES.forEach(s => { const el = $(`stage-${s}`); if (el) el.className = 'p-stage done'; });
  document.querySelectorAll('.p-connector').forEach(c => { c.className = 'p-connector done'; });
  $('pipelineStatus').textContent = 'Scene generation complete!';
}

function updateProcessLiveBanner(customLabel) {
  const banner = $('processLiveBanner');
  if (!banner) return;
  if (!state.isGenerating) {
    banner.classList.add('hidden');
    return;
  }
  banner.classList.remove('hidden');
  const label = customLabel || STAGE_LABELS[state.currentStage] || 'Processing…';
  const lbl = $('plbStageLabel');
  if (lbl) lbl.textContent = label;
  const idx = STAGES.indexOf(state.currentStage);
  banner.querySelectorAll('.plb-s').forEach((el, i) => {
    el.classList.toggle('active', i === idx);
    el.classList.toggle('done', i < idx);
  });
}

function getStageFromElapsed(ms) {
  for (let i = STAGES.length - 1; i >= 0; i--) {
    if (ms >= STAGE_MS[STAGES[i]]) return STAGES[i];
  }
  return 'world';
}

// ─── Generate Scene ───────────────────────────
$('generateSceneBtn').addEventListener('click', async () => {
  if (!state.activeNovelId) {
    setStatus('startStatus', 'Please click "Start Novel" first.', 'error');
    return;
  }

  // Capture novelId locally — protects against async race if user switches novels
  const novelId = state.activeNovelId;
  const brief   = $('sceneBriefInput').value.trim();
  const btn     = $('generateSceneBtn');

  btn.disabled    = true;
  btn.textContent = '✦ Generating…';

  state.genStartTime = Date.now();
  state.isGenerating = true;
  showPipeline(true);
  setPipelineState('world');

  try {
    const kickoff = await fetch(`${API}/novel/${novelId}/scene/next`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ scene_brief: brief }),
    });
    if (!kickoff.ok) {
      const errText = await kickoff.text().catch(() => '');
      throw new Error(`HTTP ${kickoff.status}${errText ? ': ' + errText : ''}`);
    }

    // Poll until done
    const deadline = Date.now() + 600_000;
    while (Date.now() < deadline) {
      await sleep(POLL_MS);

      const elapsed = Date.now() - state.genStartTime;
      setPipelineState(getStageFromElapsed(elapsed));

      const poll = await fetch(`${API}/novel/${novelId}/scene/generation_status`);
      if (!poll.ok) throw new Error(`Poll failed: HTTP ${poll.status}`);
      const job  = await poll.json();

      if (job.status === 'error') throw new Error(job.error || 'Generation failed');

      // Show conflict state on LOGIC stage when negotiation is active
      if (job.status === 'generating' && job.has_conflict && job.negotiation_round > 0) {
        const logicEl = $('stage-logic');
        if (logicEl) logicEl.className = 'p-stage conflict';
        const conflictLabel = `Conflict detected — negotiating (round ${job.negotiation_round})…`;
        $('pipelineStatus').textContent = conflictLabel;
        state.currentStage = 'logic';
        updateProcessLiveBanner(conflictLabel);
      }

      if (job.status === 'done') {
        setPipelineAllDone();
        const result = job.result;

        // Append prose for this novel
        const sep  = '\n\n' + '─'.repeat(60) + '\n\n';
        const prev = proseStore[novelId] || '';
        proseStore[novelId] = prev ? prev + sep + result.final_prose : result.final_prose;

        // Update scene number for this novel
        const novel = state.novels.find(n => n.id === novelId);
        if (novel) novel.sceneNumber = result.scene_number;

        // Only update display if the user is still looking at this novel
        if (state.activeNovelId === novelId) {
          state.sceneNumber = result.scene_number;
          $('sceneBadge').textContent = `S${result.scene_number}`;
          updateProseDisplay();
          // Clear scene brief input
          $('sceneBriefInput').value = '';
          $('briefCharCount').textContent = '0 chars';
          // Scroll to top of the newest scene
          setTimeout(() => scrollToSceneTop(result.scene_number), 120);
          // Show conflict banner if contradictions weren't resolved
          if (result.contradictions_found > 0) {
            showConflictBanner(result.contradictions_found, result.negotiation_rounds);
          } else {
            $('conflictBanner').classList.add('hidden');
          }
          setStatus('startStatus',
            `Scene ${result.scene_number} complete — contradictions: ${result.contradictions_found}, negotiations: ${result.negotiation_rounds}`,
            'success');
        }

        setTimeout(() => showPipeline(false), 3000);
        if (state.activeTab === 'worldgraph') setTimeout(loadGraph, 500);
        if (state.activeTab === 'process') setTimeout(loadProcess, 800);
        break;
      }
    }
  } catch (err) {
    if (state.activeNovelId === novelId) {
      setStatus('startStatus', `Error: ${err.message}`, 'error');
    }
    showPipeline(false);
  } finally {
    state.isGenerating = false;
    updateProcessLiveBanner();
    btn.disabled = false;
    btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M5.5 1l1.1 3.3H10l-2.7 2 1 3.1L5.5 7.5 3.2 9.4l1-3.1L1.5 4.3H4.4z" fill="currentColor"/></svg> Distill Prose`;
  }
});

// ─── Prose Display ────────────────────────────
function updateProseDisplay() {
  const empty    = $('proseEmpty');
  const book     = $('proseBook');
  const scenes   = $('proseScenes');
  const epigraph = $('proseEpigraph');
  const prose    = state.activeNovelId ? (proseStore[state.activeNovelId] || '') : '';

  if (!prose) {
    empty.style.display = 'flex';
    book.classList.add('hidden');
    $('proseSceneName').textContent   = 'No scene yet';
    $('wordCountDisplay').textContent = '0 words total';
    return;
  }

  empty.style.display = 'none';
  book.classList.remove('hidden');

  const parts = prose.split(/\n\n─{30,}\n\n/);
  const wc    = countWords(prose);
  $('wordCountDisplay').textContent = `${wc.toLocaleString()} words total`;
  $('proseSceneName').textContent   = `${parts.length} Scene${parts.length !== 1 ? 's' : ''}`;

  const latest = parts[parts.length - 1].trim();
  const firstSentence = latest.match(/[^.!?]+[.!?]/)?.[0]?.trim() ?? '';
  epigraph.textContent = firstSentence ? `"${firstSentence}"` : '';

  scenes.innerHTML = '';
  // Build dropdown items
  const dropdown = $('sceneDropdown');
  if (dropdown) {
    dropdown.innerHTML = '';
    parts.forEach((_, idx) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'scene-dropdown-item' + (idx === parts.length - 1 ? ' active' : '');
      btn.textContent = `Scene ${idx + 1}`;
      btn.addEventListener('click', e => {
        e.stopPropagation();
        dropdown.classList.add('hidden');
        scrollToSceneTop(idx + 1);
      });
      dropdown.appendChild(btn);
    });
  }

  parts.forEach((part, idx) => {
    const trimmed = part.trim();
    if (!trimmed) return;
    const sceneEl = document.createElement('div');
    sceneEl.className = 'prose-scene';
    sceneEl.id = `prose-scene-${idx + 1}`;
    const marker = document.createElement('div');
    marker.className = 'prose-scene-marker';
    marker.textContent = `Scene ${idx + 1}`;
    sceneEl.appendChild(marker);
    trimmed.split(/\n{2,}/).filter(p => p.trim()).forEach((p, pi) => {
      const para = document.createElement('p');
      para.className = 'prose-para' + (pi === 0 ? ' drop-cap' : '');
      para.textContent = p.trim();
      sceneEl.appendChild(para);
    });
    scenes.appendChild(sceneEl);
  });
}

// ─── Scene Navigation ─────────────────────────
function scrollToSceneTop(num) {
  const el = document.getElementById(`prose-scene-${num}`);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

$('proseScenesLabel').addEventListener('click', e => {
  const dropdown = $('sceneDropdown');
  if (!dropdown || dropdown.children.length === 0) return;
  // Don't toggle if clicking a dropdown item (handled by its own listener)
  if (e.target.closest('.scene-dropdown-item')) return;
  dropdown.classList.toggle('hidden');
});

// Close dropdown when clicking outside
document.addEventListener('click', e => {
  if (!e.target.closest('#proseScenesLabel')) {
    const dropdown = $('sceneDropdown');
    if (dropdown) dropdown.classList.add('hidden');
  }
});

// ─── Conflict Banner ──────────────────────────
function showConflictBanner(contradictions, negotiationRounds) {
  const banner = $('conflictBanner');
  const desc   = $('conflictBannerDesc');
  if (!banner) return;
  desc.innerHTML =
    `${contradictions} contradiction${contradictions !== 1 ? 's' : ''} found — ` +
    `agents negotiated for ${negotiationRounds} round${negotiationRounds !== 1 ? 's' : ''} ` +
    `without full resolution. The best available draft was used. ` +
    `<button type="button" class="conflict-banner-link" id="conflictBannerLink">View in Process tab →</button>`;
  banner.classList.remove('hidden');
  // Re-bind link (innerHTML replaced it)
  const link = $('conflictBannerLink');
  if (link) link.addEventListener('click', () => switchTab('process'));
}

$('conflictBannerDismiss').addEventListener('click', () => {
  $('conflictBanner').classList.add('hidden');
});
$('conflictBannerLink').addEventListener('click', () => switchTab('process'));

// ─── Copy & Download ──────────────────────────
$('copyProseBtn').addEventListener('click', () => {
  const prose = state.activeNovelId ? (proseStore[state.activeNovelId] || '') : '';
  if (!prose) return;
  navigator.clipboard.writeText(prose).then(() => {
    const btn = $('copyProseBtn');
    const orig = btn.innerHTML;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 7l3.5 3.5L12 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg> COPIED!`;
    setTimeout(() => { btn.innerHTML = orig; }, 2000);
  }).catch(() => {});
});

$('downloadProseBtn').addEventListener('click', () => {
  const prose = state.activeNovelId ? (proseStore[state.activeNovelId] || '') : '';
  if (!prose) return;
  const blob = new Blob([prose], { type: 'text/plain;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = `writeagent_novel_${(state.activeNovelId || 'draft').slice(0, 8)}.txt`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// ─── Inject Event ─────────────────────────────
$('injectEventBtn').addEventListener('click', async () => {
  if (!state.activeNovelId) {
    setStatus('injectStatus', 'Start a novel first.', 'error');
    return;
  }
  const event = $('injectEventInput').value.trim();
  if (!event) { setStatus('injectStatus', 'Enter an event to inject.', 'error'); return; }

  $('injectEventBtn').disabled = true;
  setStatus('injectStatus', 'Injecting…', 'loading');
  try {
    const payload = { event };
    const resp = await fetch(`${API}/novel/${state.activeNovelId}/inject`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${resp.status}`);
    }
    setStatus('injectStatus', `Injected: "${event.slice(0, 70)}…"`, 'success');
    $('injectEventInput').value = '';
  } catch (err) {
    setStatus('injectStatus', `Error: ${err.message}`, 'error');
  } finally {
    $('injectEventBtn').disabled = false;
  }
});

// ─── Resize Handle ────────────────────────────
(function initResizeHandle() {
  const handle = $('resizeHandle');
  const left   = $('writerLeft');
  let dragging = false, startX = 0, startW = 0;
  handle.addEventListener('mousedown', e => {
    dragging = true; startX = e.clientX; startW = left.getBoundingClientRect().width;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const newW = Math.max(280, Math.min(startW + e.clientX - startX, window.innerWidth * 0.7));
    left.style.width = `${newW}px`;
  });
  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
})();

// ─── World Graph ──────────────────────────────
let svgEl, gEl, zoomBehavior;

const COLOR = {
  character:  '#ff4d6d',
  location:   '#4cc9f0',
  world_rule: '#94a3b8',
};

function initGraph() {
  svgEl = d3.select('#graphSvg');
  gEl   = svgEl.append('g');
  zoomBehavior = d3.zoom().scaleExtent([0.05, 12])
    .on('zoom', ev => gEl.attr('transform', ev.transform));
  svgEl.call(zoomBehavior);
  $('btnZoomIn').addEventListener('click',    () => svgEl.transition().duration(300).call(zoomBehavior.scaleBy, 1.35));
  $('btnZoomOut').addEventListener('click',   () => svgEl.transition().duration(300).call(zoomBehavior.scaleBy, 0.74));
  $('btnResetZoom').addEventListener('click', () => svgEl.transition().duration(400).call(zoomBehavior.transform, d3.zoomIdentity));
  $('fcClose').addEventListener('click',      () => $('focusCard').classList.add('hidden'));
  $('refreshGraphBtn').addEventListener('click', () => { if (state.activeNovelId) loadGraph(); });
  $('fcViewStory').addEventListener('click', () => switchTab('worldgraph'));
}

async function loadGraph() {
  if (!state.activeNovelId) return;
  $('graphEmpty').style.display = 'none';
  gEl.selectAll('*').remove();
  $('focusCard').classList.add('hidden');
  gEl.append('text')
    .attr('x', document.getElementById('graphWorkspace').clientWidth / 2)
    .attr('y', document.getElementById('graphWorkspace').clientHeight / 2)
    .attr('text-anchor', 'middle').attr('fill', '#64748b')
    .attr('font-family', 'Inter, sans-serif').attr('font-size', '14px')
    .text('Loading graph…');
  try {
    const resp = await fetch(`${API}/entities/${state.activeNovelId}/graph`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    gEl.selectAll('*').remove();
    if (!data.nodes || data.nodes.length === 0) { $('graphEmpty').style.display = 'flex'; return; }
    renderGraph(data);
  } catch (err) {
    gEl.selectAll('*').remove();
    $('graphEmpty').innerHTML = `<p>Error loading graph: ${esc(err.message)}</p>`;
    $('graphEmpty').style.display = 'flex';
  }
}

function renderGraph({ nodes, edges }) {
  const ws = document.getElementById('graphWorkspace');
  const W = ws.clientWidth, H = ws.clientHeight;
  const connCount = {};
  edges.forEach(e => {
    connCount[e.from] = (connCount[e.from] || 0) + 1;
    connCount[e.to]   = (connCount[e.to]   || 0) + 1;
  });
  const idxOf = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
  const links = edges
    .filter(e => idxOf[e.from] !== undefined && idxOf[e.to] !== undefined)
    .map(e => ({ source: idxOf[e.from], target: idxOf[e.to], label: e.label || 'mentions' }));
  const rScale = d3.scaleSqrt()
    .domain([0, Math.max(...nodes.map(n => connCount[n.id] || 0), 1)])
    .range([14, 42]);

  if (state.simulation) state.simulation.stop();
  state.simulation = d3.forceSimulation(nodes)
    .force('link',      d3.forceLink(links).distance(140).strength(0.4))
    .force('charge',    d3.forceManyBody().strength(-280))
    .force('center',    d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(d => rScale(connCount[d.id] || 0) + 10));

  const linkSel = gEl.append('g').selectAll('line').data(links).join('line').attr('class', 'graph-link');
  const linkLabelSel = gEl.append('g').selectAll('text').data(links).join('text')
    .attr('class', 'graph-link-label').text(d => d.label);
  const nodeSel = gEl.append('g').selectAll('g').data(nodes).join('g').attr('class', 'graph-node')
    .call(d3.drag()
      .on('start', (ev, d) => { if (!ev.active) state.simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag',  (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
      .on('end',   (ev, d) => { if (!ev.active) state.simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    )
    .on('click', (ev, d) => {
      ev.stopPropagation();
      nodeSel.classed('selected', nd => nd.id === d.id);
      showFocusCard(d, connCount[d.id] || 0);
    });
  svgEl.on('click', () => { nodeSel.classed('selected', false); $('focusCard').classList.add('hidden'); });
  nodeSel.append('circle')
    .attr('r', d => rScale(connCount[d.id] || 0))
    .attr('fill', d => COLOR[d.group] || '#888').attr('fill-opacity', 0.85)
    .attr('stroke', d => COLOR[d.group] || '#888').attr('stroke-width', 2).attr('stroke-opacity', 0.35);
  nodeSel.append('text')
    .text(d => d.label)
    .attr('dy', d => rScale(connCount[d.id] || 0) + 14)
    .attr('text-anchor', 'middle').attr('font-size', '10px').attr('font-weight', '600');
  state.simulation.on('tick', () => {
    linkSel
      .attr('x1', d => nodes[d.source.index ?? d.source]?.x ?? 0)
      .attr('y1', d => nodes[d.source.index ?? d.source]?.y ?? 0)
      .attr('x2', d => nodes[d.target.index ?? d.target]?.x ?? 0)
      .attr('y2', d => nodes[d.target.index ?? d.target]?.y ?? 0);
    linkLabelSel
      .attr('x', d => ((nodes[d.source.index ?? d.source]?.x ?? 0) + (nodes[d.target.index ?? d.target]?.x ?? 0)) / 2)
      .attr('y', d => ((nodes[d.source.index ?? d.source]?.y ?? 0) + (nodes[d.target.index ?? d.target]?.y ?? 0)) / 2);
    nodeSel.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });
}

async function showFocusCard(node, connections) {
  const typeKey   = node.group || 'character';
  const typeLabel = typeKey.replace('_', ' ');
  $('fcType').textContent = typeLabel.charAt(0).toUpperCase() + typeLabel.slice(1);
  $('fcType').className   = `entity-type-badge ${typeKey}`;
  $('fcName').textContent = node.label;
  $('fcDesc').textContent = 'Loading…';
  $('fcMentions').textContent    = '…';
  $('fcConnections').textContent = connections;
  $('focusCard').classList.remove('hidden');
  try {
    const resp = await fetch(`${API}/entities/${state.activeNovelId}/${node.id}`);
    if (resp.ok) {
      const entity = await resp.json();
      $('fcDesc').textContent     = entity.description || 'No description available.';
      $('fcMentions').textContent = (entity.version || 1) + connections * 5;
    } else throw new Error();
  } catch {
    $('fcDesc').textContent     = 'No description available.';
    $('fcMentions').textContent = connections * 5;
  }
}

// ─── Conflicts ────────────────────────────────
function fmtTimestamp(ts) {
  if (!ts) return '—';
  try {
    const normalized = ts.replace(/(\.\d{3})\d+/, '$1');
    const d = new Date(normalized);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString(undefined, { year:'numeric', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit' });
  } catch { return ts; }
}

function formatContradictions(contradictions, fallbackProposal) {
  if (!contradictions || contradictions.length === 0) {
    return esc(fallbackProposal || '—');
  }
  return contradictions.map(c => {
    const field    = c.field    || c.entity || '?';
    const stored   = c.stored_value || c.expected || '?';
    const draft    = c.new_value    || c.actual   || '?';
    const severity = c.severity || '';
    const badge = severity === 'critical'
      ? `<span style="color:#f87171;font-size:11px;font-weight:600">[CRITICAL]</span>`
      : severity
        ? `<span style="color:#fbbf24;font-size:11px">[${severity.toUpperCase()}]</span>`
        : '';
    return `<div style="margin-bottom:6px">${badge} <strong>${esc(field)}</strong>: 数据库值为 "<em>${esc(stored)}</em>"，草稿中为 "<em>${esc(draft)}</em>"</div>`;
  }).join('');
}

// ─── Process Tab — XAI Decision Chain ────────────────────────────────────────

async function loadProcess() {
  if (!state.activeNovelId) return;
  updateProcessLiveBanner();
  const timeline = $('xaiTimeline');
  timeline.innerHTML = '<div class="loading-row"><span class="spinner"></span>Loading…</div>';
  try {
    const resp = await fetch(`${API}/novel/${state.activeNovelId}/scene/process`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (!data || !data.steps || data.steps.length === 0) {
      timeline.innerHTML = '<div class="empty-state">No process data yet — generate a scene first.</div>';
      return;
    }
    timeline.innerHTML = buildXAITimeline(data);
    timeline.querySelectorAll('.xai-card-header').forEach(hdr => {
      hdr.addEventListener('click', () => hdr.closest('.xai-card').classList.toggle('open'));
    });
    // Show/hide negotiation panel
    const neg = data.negotiation || {};
    const negPanel = $('xaiNegPanel');
    if (neg.rounds > 0) {
      negPanel.style.display = '';
      $('xaiNegSubtitle').textContent =
        `${neg.rounds} round(s) — ${neg.resolved ? 'Resolved' : 'Unresolved'}`;
      $('xaiNegContent').innerHTML = buildNegotiationPanel(neg);
    } else {
      negPanel.style.display = 'none';
    }
  } catch (err) {
    $('xaiTimeline').innerHTML = `<div class="empty-state">Error: ${esc(err.message)}</div>`;
  }
}
$('refreshProcessBtn').addEventListener('click', loadProcess);

function buildXAITimeline(data) {
  const summary = data.pipeline_summary || {};
  const sceneNum = data.scene_number || '?';

  const summaryHtml = `
    <div class="xai-scene-header">
      <span class="xai-scene-label">Scene ${esc(String(sceneNum))}</span>
      ${summary.had_contradiction
        ? '<span class="xai-scene-pill xai-scene-pill--conflict">Conflict Detected</span>'
        : '<span class="xai-scene-pill xai-scene-pill--clean">No Conflicts</span>'}
      ${summary.negotiation_rounds > 0
        ? `<span class="xai-scene-pill xai-scene-pill--neg">${summary.negotiation_rounds} Negotiation Round(s)</span>`
        : ''}
    </div>`;

  const nodesHtml = data.steps.map(
    (step, idx) => buildXAINode(step, idx, data.steps.length)
  ).join('');

  return summaryHtml + nodesHtml;
}

function buildXAINode(step, idx, total) {
  const isLast = idx === total - 1;
  const seqNum  = String(idx + 1).padStart(2, '0');
  const statusLabel = { done: 'Done', ok: 'Clear', conflict: 'Conflict', inactive: 'Inactive' }[step.status] || step.status;
  const cardBody = buildXAICardBody(step);

  return `
    <div class="xai-node">
      <div class="xai-connector">
        <div class="xai-dot xai-dot--${esc(step.status)}">
          <span class="xai-dot-seq">${seqNum}</span>
        </div>
        ${!isLast ? '<div class="xai-line"></div>' : ''}
      </div>
      <div class="xai-card">
        <div class="xai-card-header">
          <div class="xai-card-title-row">
            <span class="xai-card-name">${esc(step.label)}</span>
            <span class="xai-status-pill xai-status-pill--${esc(step.status)}">${statusLabel}</span>
            <span class="xai-card-chevron">›</span>
          </div>
          <p class="xai-card-summary">${esc(step.summary)}</p>
        </div>
        <div class="xai-card-body">${cardBody}</div>
      </div>
    </div>`;
}

function buildXAICardBody(step) {
  const r = step.reasoning || {};
  const influences = step.influences || [];
  const rationale = r.decision_rationale || '';

  const whyHtml = rationale
    ? `<div class="xai-why-block">
        <div class="xai-why-label">WHY — this agent's decision rationale</div>
        <p class="xai-rationale">"${esc(rationale)}"</p>
        ${buildReasoningTags(step.agent_id, r)}
        ${buildInfluenceBadges(influences)}
       </div>`
    : `<div class="xai-why-block xai-why-block--empty">
        <div class="xai-why-label">WHY — this agent's decision rationale</div>
        <p class="xai-rationale xai-rationale--unavailable">Reasoning data not available — regenerate this scene to see AI explanations.</p>
       </div>`;

  const renderer = xaiDetailRenderers[step.agent_id];
  const detailsHtml = renderer ? renderer(step.details || {}) : '';
  const whatHtml = detailsHtml
    ? `<details class="xai-details-block">
        <summary>Technical Details — Inputs &amp; Outputs</summary>
        ${detailsHtml}
       </details>`
    : '';

  return whyHtml + whatHtml;
}

function buildReasoningTags(agentId, r) {
  const tags = [];
  if (agentId === 'worldbuilding_agent') {
    (r.rules_applied || []).slice(0, 4).forEach(rule =>
      tags.push({ text: rule, cls: 'rule' }));
    (r.constraints_identified || []).slice(0, 2).forEach(c =>
      tags.push({ text: c, cls: 'constraint' }));
  } else if (agentId === 'character_agent') {
    (r.state_changes || []).slice(0, 3).forEach(sc =>
      tags.push({ text: `${sc.character}: ${sc.change}`, cls: 'change' }));
  } else if (agentId === 'plot_agent') {
    (r.narrative_choices || []).slice(0, 3).forEach(nc =>
      tags.push({ text: nc, cls: 'choice' }));
  } else if (agentId === 'consistency_checker') {
    if (r.confidence) tags.push({ text: `Confidence: ${r.confidence}`, cls: 'confidence' });
    (r.checks_performed || []).forEach(chk => tags.push({ text: chk, cls: 'check' }));
  } else if (agentId === 'narrative_output_agent') {
    (r.style_choices || []).slice(0, 3).forEach(sc =>
      tags.push({ text: sc, cls: 'style' }));
  }
  if (tags.length === 0) return '';
  return `<div class="xai-tag-row">${tags.map(t =>
    `<span class="xai-tag xai-tag--${t.cls}">${esc(String(t.text).slice(0, 80))}</span>`
  ).join('')}</div>`;
}

function buildInfluenceBadges(influences) {
  if (!influences || influences.length === 0) return '';
  const names = {
    worldbuilding_agent: 'WorldbuildingAgent',
    character_agent: 'CharacterAgent',
    plot_agent: 'PlotAgent',
    consistency_checker: 'ConsistencyChecker',
    narrative_output_agent: 'NarrativeOutputAgent',
  };
  return `<div class="xai-influence-row">
    <span class="xai-influence-label">Informs:</span>
    ${influences.map(inf =>
      `<span class="xai-influence-badge">${esc(names[inf] || inf)}</span>`
    ).join('')}
  </div>`;
}

// Per-agent technical detail renderers (WHAT block)
const xaiDetailRenderers = {
  worldbuilding_agent(d) {
    const parts = [];
    if (d.retrieved_entities && d.retrieved_entities.length > 0) {
      const rows = d.retrieved_entities.map(e =>
        `<div class="proc-entity-row">
          <span class="proc-entity-type">${esc(e.type)}</span>
          <span class="proc-entity-name">${esc(e.name)}</span>
          <span class="proc-entity-desc">${esc(e.summary)}</span>
         </div>`).join('');
      parts.push(`<div class="proc-detail-section"><div class="proc-detail-label">Retrieved Entities</div><div class="proc-entity-list">${rows}</div></div>`);
    }
    if (d.world_rules_preview) {
      parts.push(`<div class="proc-detail-section"><div class="proc-detail-label">World Rules Context</div><pre class="proc-pre">${esc(d.world_rules_preview)}</pre></div>`);
    }
    return parts.join('');
  },
  character_agent(d) {
    if (!d.character_states) return '';
    const chars = Object.entries(d.character_states);
    if (chars.length === 0) return '';
    const rows = chars.map(([name, st]) =>
      `<div class="proc-entity-row">
        <span class="proc-entity-name" style="min-width:120px">${esc(name)}</span>
        <span class="proc-entity-desc">${esc(String(st).slice(0, 150))}</span>
       </div>`).join('');
    return `<div class="proc-detail-section"><div class="proc-detail-label">Character States</div><div class="proc-entity-list">${rows}</div></div>`;
  },
  plot_agent(d) {
    const parts = [];
    if (d.plot_events && d.plot_events.length > 0) {
      const evList = d.plot_events.map(ev => `<li>${esc(String(ev).slice(0, 160))}</li>`).join('');
      parts.push(`<div class="proc-detail-section"><div class="proc-detail-label">Plot Events</div><ul class="proc-list">${evList}</ul></div>`);
    }
    if (d.raw_draft_preview) {
      parts.push(`<div class="proc-detail-section"><div class="proc-detail-label">Raw Draft Preview</div><pre class="proc-pre">${esc(d.raw_draft_preview)}</pre></div>`);
    }
    return parts.join('');
  },
  consistency_checker(d) {
    if (!d.contradictions) return `<em style="color:var(--text-faint)">No detail data available.</em>`;
    if (d.contradictions.length === 0) {
      return `<div class="proc-detail-section"><em style="color:var(--text-faint)">No contradictions found.</em></div>`;
    }
    const items = d.contradictions.map(buildContradictionCard).join('');
    return `<div class="proc-detail-section"><div class="proc-detail-label">Contradictions Found</div>${items}</div>`;
  },
  narrative_output_agent(d) {
    if (!d.final_prose_preview) return '';
    return `<div class="proc-detail-section"><div class="proc-detail-label">Final Prose Preview</div><pre class="proc-pre">${esc(d.final_prose_preview)}</pre></div>`;
  },
};

function buildContradictionCard(c) {
  const field    = c.field || '';
  const stored   = c.stored_value || '';
  const inDraft  = c.new_value || '';
  const severity = c.severity || 'minor';
  const explanation = c.explanation || '';
  const source   = c.source === 'pre_scan' ? 'Code Pre-scan' : 'LLM';

  const parts = field.split('.');
  let subject = '';
  if (parts[0] === 'character' && parts.length >= 3) {
    subject = `<strong>${esc(parts[1])}</strong> — ${esc(parts.slice(2).join('.'))}`;
  } else if (parts[0] === 'world_rule') {
    subject = `World rule: <strong>${esc(parts.slice(1).join('.'))}</strong>`;
  } else {
    subject = `<strong>${esc(field)}</strong>`;
  }

  const sevLabel = severity === 'critical' ? 'CRITICAL' : 'MINOR';

  return `
    <div class="xai-contradiction-card xai-contra--${esc(severity)}">
      <div class="xai-contra-header">
        <span class="xai-contra-severity xai-contra-severity--${esc(severity)}">${sevLabel}</span>
        <span class="xai-contra-field">${subject}</span>
        <span class="xai-contra-source">Detected by ${esc(source)}</span>
      </div>
      <div class="xai-contra-body">
        <div class="xai-contra-col xai-contra-col--stored">
          <div class="xai-contra-col-label">Established Fact</div>
          <div class="xai-contra-value">"${esc(stored)}"</div>
        </div>
        <div class="xai-contra-divider">≠</div>
        <div class="xai-contra-col xai-contra-col--draft">
          <div class="xai-contra-col-label">Draft Contradiction</div>
          <div class="xai-contra-value">"${esc(inDraft)}"</div>
        </div>
      </div>
      ${explanation
        ? `<div class="xai-contra-explanation">${esc(explanation)}</div>`
        : ''}
    </div>`;
}

function buildNegotiationPanel(neg) {
  if (!neg.log || neg.log.length === 0) {
    return '<div class="empty-state" style="margin:12px">No negotiation entries.</div>';
  }

  const bubblesHtml = neg.log.map(entry => {
    const agent  = entry.agent || (entry.participants ? entry.participants[0] : '?');
    const isChecker = agent === 'consistency_checker';
    const isReviser = agent === 'revision_agent';
    const bubbleCls = isChecker
      ? 'xai-neg-bubble--checker'
      : isReviser ? 'xai-neg-bubble--reviser' : 'xai-neg-bubble--other';
    const avatarTxt = isChecker ? 'CC' : isReviser ? 'RA' : esc(agent.substring(0, 2).toUpperCase());
    const agentLabel = isChecker ? 'ConsistencyChecker' : isReviser ? 'RevisionAgent' : esc(agent);
    const roundLabel = entry.round_number !== undefined ? `Round ${entry.round_number}` : '';

    let msgBody = '';
    if (isChecker && entry.round_number === 0) {
      const n = entry.contradictions_found ?? (entry.contradictions || []).length;
      msgBody = n > 0
        ? `Detected ${n} contradiction(s). Triggering negotiation.`
        : 'No contradictions detected. Scene is consistent.';
    } else if (isReviser) {
      const before = entry.contradictions_before ?? (entry.contradictions || []).length;
      const afterList = Array.isArray(entry.contradictions_after) ? entry.contradictions_after : [];
      const after  = entry.contradictions_found ?? afterList.length;
      const changes = entry.changes_made || [];
      msgBody = `Revised draft (${before} → ${after} contradiction(s) remaining).`;
      if (changes.length > 0) {
        msgBody += ` <span class="xai-neg-changes">${changes.map(ch => esc(ch)).join(' · ')}</span>`;
      }
    } else if (isChecker && (entry.round_number || 0) > 0) {
      const afterList = Array.isArray(entry.contradictions_after) ? entry.contradictions_after : [];
      const found = entry.contradictions_found ?? afterList.length;
      msgBody = found === 0
        ? 'Re-checked revised draft. 0 contradictions found.'
        : `Re-checked revised draft. ${found} contradiction(s) remain.`;
      if (entry.resolution === 'resolved') {
        msgBody += ' <span class="xai-neg-resolved-badge">Resolved</span>';
      }
    } else {
      msgBody = esc(entry.resolution || entry.action || 'Processed');
    }

    return `
      <div class="xai-neg-bubble ${bubbleCls}">
        <div class="xai-neg-avatar">${avatarTxt}</div>
        <div class="xai-neg-msg-block">
          <div class="xai-neg-meta">
            <span class="xai-neg-agent-name">${agentLabel}</span>
            ${roundLabel ? `<span class="xai-neg-round-label">${roundLabel}</span>` : ''}
          </div>
          <div class="xai-neg-msg">${msgBody}</div>
        </div>
      </div>`;
  }).join('');

  const resolutionHtml = neg.resolved
    ? `<div class="xai-neg-result xai-neg-result--resolved">All contradictions resolved.</div>`
    : `<div class="xai-neg-result xai-neg-result--unresolved">Contradictions could not be fully resolved — best available draft was used.</div>`;

  return bubblesHtml + resolutionHtml;
}

// ─── Audit ────────────────────────────────────
let _auditOffset = 0;

function buildAuditCard(e) {
  const cardId = `audit-card-${e.log_id}`;
  const agentName = e.agent_id || 'unknown_agent';
  const sceneNum  = e.scene_number || 0;
  const timestamp = fmtTimestamp(e.timestamp);
  const promptTokens = e.prompt_tokens || 0;
  const completionTokens = e.completion_tokens || 0;
  const duration = e.duration_ms || 0;
  const preview = e.output_preview || '';
  
  // Format the prompt and output for display
  // They might be JSON strings or plain text
  const formatContent = (val) => {
    if (!val) return '<i>(empty)</i>';
    try {
      // Try to pretty-print if it's JSON
      const parsed = typeof val === 'string' ? JSON.parse(val) : val;
      return esc(JSON.stringify(parsed, null, 2));
    } catch (err) {
      return esc(val);
    }
  };

  const promptHtml = formatContent(e.prompt);
  const outputHtml = formatContent(e.output || preview);

  return `
    <div class="audit-card" id="${cardId}">
      <div class="audit-card-header" onclick="toggleAuditCard('${cardId}')">
        <div class="audit-chevron">›</div>
        <div class="audit-card-main">
          <div class="audit-agent-badge">${esc(agentName)}</div>
          <div class="audit-scene-tag">Scene ${sceneNum}</div>
          <div class="audit-preview">${esc(preview.slice(0, 80))}...</div>
        </div>
        <div class="audit-meta">
          <div class="audit-stat" title="Prompt Tokens">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><rect x="1" y="1" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1"/></svg>
            ${promptTokens}
          </div>
          <div class="audit-stat" title="Completion Tokens">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><rect x="1" y="1" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1"/><path d="M3 3h4M3 5h4M3 7h2" stroke="currentColor" stroke-width="1"/></svg>
            ${completionTokens}
          </div>
          <div class="audit-stat" title="Duration">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><circle cx="5" cy="5" r="4" stroke="currentColor" stroke-width="1"/><path d="M5 2.5V5l1.5 1.5" stroke="currentColor" stroke-width="1"/></svg>
            ${duration}ms
          </div>
          <div class="audit-stat" style="opacity:0.6">${timestamp}</div>
        </div>
      </div>
      <div class="audit-card-body">
        <div class="audit-detail-grid">
          <div class="audit-detail-box">
            <div class="audit-detail-label">Prompt (Input)</div>
            <pre class="audit-detail-content prompt">${promptHtml}</pre>
          </div>
          <div class="audit-detail-box">
            <div class="audit-detail-label">Response (Output)</div>
            <pre class="audit-detail-content output">${outputHtml}</pre>
          </div>
        </div>
      </div>
    </div>
  `;
}

window.toggleAuditCard = (id) => {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('open');
};

async function loadAudit(offset = 0) {
  if (!state.activeNovelId) return;
  _auditOffset = offset;
  const wrap     = $('auditTable');
  const pagDiv   = $('auditPagination');
  wrap.innerHTML = '<div class="loading-row"><span class="spinner"></span>Loading…</div>';
  pagDiv.classList.add('hidden');
  const limit    = parseInt($('auditLimit').value, 10) || 20;
  const fromDisk = $('auditFromDisk').checked;
  try {
    const resp = await fetch(
      `${API}/audit/${state.activeNovelId}?limit=${limit}&offset=${offset}&order=desc&from_disk=${fromDisk}`
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const items = Array.isArray(data) ? data : (data.items || []);
    const total = Array.isArray(data) ? items.length : (data.total ?? items.length);
    
    if (!items || items.length === 0) {
      wrap.innerHTML = '<div class="empty-state">No audit entries yet.</div>';
      return;
    }

    wrap.innerHTML = `<div class="audit-cards-list">${items.map(e => buildAuditCard(e)).join('')}</div>`;
    renderAuditPagination(total, offset, limit);
  } catch (err) {
    wrap.innerHTML = `<div class="empty-state">Error: ${esc(err.message)}</div>`;
  }
}

function renderAuditPagination(total, offset, limit) {
  const pagDiv = $('auditPagination');
  if (total <= limit) { pagDiv.classList.add('hidden'); return; }
  const page  = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  pagDiv.classList.remove('hidden');
  pagDiv.innerHTML = `
    <button type="button" class="page-btn" id="pagePrev" ${offset === 0 ? 'disabled' : ''}>← Prev</button>
    <span class="page-info">Page ${page} / ${pages} &nbsp;·&nbsp; ${total} entries</span>
    <button type="button" class="page-btn" id="pageNext" ${offset + limit >= total ? 'disabled' : ''}>Next →</button>
  `;
  pagDiv.querySelector('#pagePrev')?.addEventListener('click', () => loadAudit(Math.max(0, offset - limit)));
  pagDiv.querySelector('#pageNext')?.addEventListener('click', () => loadAudit(offset + limit));
}

$('refreshAuditBtn').addEventListener('click', () => loadAudit(0));
$('auditLimit').addEventListener('change',    () => { if (state.activeTab === 'audit' && state.activeNovelId) loadAudit(0); });
$('auditFromDisk').addEventListener('change', () => { if (state.activeTab === 'audit' && state.activeNovelId) loadAudit(0); });

// ─── Table Builder ────────────────────────────
function buildTable(headers, rows, rawHtml = []) {
  const ths = headers.map(h => `<th>${esc(h)}</th>`).join('');
  const trs = rows.map(row =>
    `<tr>${row.map((cell, i) => `<td>${rawHtml[i] ? cell : esc(String(cell))}</td>`).join('')}</tr>`
  ).join('');
  return `<table class="data-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
}

// ─── Init ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  _addCharEditRow();
  addRuleRow();
  initGraph();
  switchTab('writer');
});
