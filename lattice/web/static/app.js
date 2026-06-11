'use strict';

// ── constants ─────────────────────────────────────────────────────────────

const KIND_ICON = {
  preference:     '♥',
  fact:           '◆',
  goal:           '◎',
  recommendation: '★',
  event:          '◷',
  decision:       '◈',
  habit:          '↻',
  reminder:       '◌',
  count:          '#',
};

const CIRCUMFERENCE = 2 * Math.PI * 10; // 62.83 — matches r=10 in SVG

const HISTORY_KEY = 'lattice-response-times';
const MAX_HISTORY = 6;

// ── state ─────────────────────────────────────────────────────────────────

let atomsById          = {};
let atomNumMap         = {};
let busy               = false;
let sessionQA          = []; // {question, answer} pairs accumulated this session (for Save Session)
let conversationHistory = []; // {question, answer} last N turns sent to /api/query for reformulation
let lastActivityAt     = Date.now();

// Stable session ID per page session — persists across reloads, reset on new tab
const sessionId = (() => {
  let id = sessionStorage.getItem('lattice-session-id');
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem('lattice-session-id', id);
  }
  return id;
})();

// ── DOM refs ──────────────────────────────────────────────────────────────

const form           = document.getElementById('query-form');
const input          = document.getElementById('question');
const submitBtn      = document.getElementById('submit');
const history        = document.getElementById('chat-history');
const atomsList      = document.getElementById('atoms-list');
const statusDot      = document.getElementById('status-dot');
const statusLbl      = document.getElementById('status-label');
const themeToggle    = document.getElementById('theme-toggle');
const scrollBtn      = document.getElementById('scroll-btn');
const memCount       = document.getElementById('memory-count');
const greetingEl     = document.getElementById('greeting');
const saveSessionBtn = document.getElementById('save-session');
const streakBadge    = document.getElementById('streak-badge');
const fileUpload     = document.getElementById('file-upload');
const uploadProgress = document.getElementById('upload-progress');

// ── theme ─────────────────────────────────────────────────────────────────

function isDark() {
  const saved = localStorage.getItem('lattice-theme');
  if (saved) return saved === 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function applyTheme(dark) {
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  themeToggle.textContent = dark ? '☀' : '☾';
  themeToggle.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
  localStorage.setItem('lattice-theme', dark ? 'dark' : 'light');
}

themeToggle.addEventListener('click', () => applyTheme(!isDark()));
applyTheme(isDark());

// ── greeting ──────────────────────────────────────────────────────────────

function initGreeting() {
  const h = new Date().getHours();
  const msg = h < 12 ? 'Good morning.' : h < 17 ? 'Good afternoon.' : 'Good evening.';
  greetingEl.textContent = msg;
}

// ── response time history (ETA) ───────────────────────────────────────────

function getHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
  catch { return []; }
}

function recordTime(ms) {
  const h = getHistory();
  h.push(ms);
  if (h.length > MAX_HISTORY) h.shift();
  localStorage.setItem(HISTORY_KEY, JSON.stringify(h));
}

function estimatedSeconds() {
  const h = getHistory();
  if (!h.length) return null;
  return h.reduce((a, b) => a + b, 0) / h.length / 1000;
}

// ── ring timer ────────────────────────────────────────────────────────────

function makeRingHTML() {
  return `
    <div class="ring-wrap">
      <svg class="ring indeterminate" viewBox="0 0 26 26">
        <circle class="ring-track"    cx="13" cy="13" r="10"/>
        <circle class="ring-progress" cx="13" cy="13" r="10"/>
      </svg>
    </div>`;
}

function startRing(turn) {
  const ring     = turn.querySelector('.ring');
  const progress = turn.querySelector('.ring-progress');
  const timerEl  = turn.querySelector('.loading-timer');
  const labelEl  = turn.querySelector('.loading-label');

  const est   = estimatedSeconds();
  const start = Date.now();

  if (est) {
    ring.classList.remove('indeterminate');
    progress.style.strokeDashoffset = CIRCUMFERENCE;
  }

  const interval = setInterval(() => {
    const elapsed = (Date.now() - start) / 1000;

    if (est) {
      const pct = Math.min(elapsed / est, 0.9);
      progress.style.strokeDashoffset = CIRCUMFERENCE * (1 - pct);
      const remaining = Math.max(0, Math.round(est - elapsed));
      timerEl.textContent = remaining > 0
        ? `${Math.round(elapsed)}s · ~${remaining}s remaining`
        : `${Math.round(elapsed)}s · almost done…`;
    } else {
      timerEl.textContent = `${Math.round(elapsed)}s`;
    }
  }, 200);

  return { interval, start, ring, progress, labelEl };
}

function stopRing({ interval, start, ring, progress }) {
  clearInterval(interval);
  recordTime(Date.now() - start);
  ring.classList.remove('indeterminate');
  ring.classList.add('done');
  progress.style.strokeDashoffset = 0;
}

// ── utils ─────────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function relativeTime(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function kindIcon(kind) { return KIND_ICON[kind] || '·'; }

// ── markdown ──────────────────────────────────────────────────────────────

function renderMarkdown(text) {
  if (typeof marked === 'undefined') return `<p>${escHtml(text)}</p>`;
  marked.setOptions({ breaks: true, gfm: true });
  return marked.parse(text);
}

// ── citation numbering ────────────────────────────────────────────────────

function buildCitationIndex(atoms) {
  const byId = {}, ordered = [];
  let n = 1;
  atoms.forEach(a => {
    const key = a.atom_id || a.source_id;
    if (key && !(key in byId)) {
      byId[key] = n;
      if (a.src_key) byId[a.src_key] = n;
      n++;
      ordered.push(a);
    }
  });
  return { byId, ordered };
}

function plainCitations(answer, numMap) {
  return answer.replace(
    /\[src:([^\]]+)\]|\[([^\]]+)\]\[src:([^\]]+)\]/g,
    (_, bareId, label, labeledId) => {
      const id  = bareId || labeledId;
      const num = numMap[id];
      return num != null ? `[${num}]` : `[${label || id}]`;
    }
  );
}

function renderCitations(html, numMap) {
  // Bare [src:id] must be tried first — otherwise adjacent [src:a][src:b] gets
  // consumed as a single [label][src:id] match, dropping the first citation.
  return html.replace(
    /\[src:([^\]]+)\]|\[([^\]]+)\]\[src:([^\]]+)\]/g,
    (_, bareId, label, labeledId) => {
      const id  = bareId || labeledId;
      const num = numMap[id];
      const display = num != null ? num : (label || id);
      return `<a class="citation" data-src="${escHtml(id)}" href="#ref-${escHtml(id)}">[${display}]</a>`;
    }
  );
}

// ── citation ↔ reference linking ──────────────────────────────────────────

function bindCitationLinks(turn) {
  turn.querySelectorAll('.citation').forEach(cite => {
    cite.addEventListener('click', e => {
      e.preventDefault();
      const src   = cite.dataset.src;
      const refEl = turn.querySelector(`#ref-${CSS.escape(src)}`);
      if (!refEl) return;

      turn.querySelectorAll('.citation.highlighted, .ref-item.highlighted')
          .forEach(el => el.classList.remove('highlighted'));

      cite.classList.add('highlighted');
      refEl.classList.add('highlighted');
      refEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

      setTimeout(() => {
        cite.classList.remove('highlighted');
        refEl.classList.remove('highlighted');
      }, 2200);
    });
  });

  turn.querySelectorAll('.ref-item').forEach(refEl => {
    const src = refEl.id.replace(/^ref-/, '');
    refEl.addEventListener('mouseenter', () =>
      turn.querySelectorAll(`.citation[data-src="${CSS.escape(src)}"]`)
          .forEach(c => c.classList.add('highlighted')));
    refEl.addEventListener('mouseleave', () =>
      turn.querySelectorAll(`.citation[data-src="${CSS.escape(src)}"]`)
          .forEach(c => c.classList.remove('highlighted')));
  });
}

// ── sources section ───────────────────────────────────────────────────────

const _REDISCOVERY_DAYS = 30;

function _atomAgeDays(a) {
  if (!a.ingested_at) return null;
  const ms = Date.now() - new Date(a.ingested_at).getTime();
  return Math.floor(ms / 86400000);
}

function _channelLabel(sourceId) {
  if (!sourceId) return '';
  // URLs are shown as a clickable link separately — just label as "web"
  if (/^https?:\/\//.test(sourceId)) return 'web';
  // Strip file-type parser prefix (pdf:file.pdf → file.pdf)
  return sourceId.replace(/^(pdf|pptx|xlsx|xls|docx):/, '');
}

function _refAgeLabel(a) {
  const iso = a.ingested_at || a.observed_at;
  if (!iso) return '';
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days < 1) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 14) return `${days} days ago`;
  if (days < 60) return `${Math.round(days / 7)} weeks ago`;
  if (days < 365) return `${Math.round(days / 30)} months ago`;
  return `${Math.round(days / 365)}y ago`;
}

const _SKIP_KINDS = new Set(['document', 'conversation', 'chat', 'plain']);

function renderReferences(orderedAtoms, numMap) {
  if (!orderedAtoms.length) return '';
  const collapsed = orderedAtoms.length > 3;
  const items = orderedAtoms.map((a, i) => {
    const refKey = a.src_key || a.atom_id || a.source_id || String(i + 1);
    const num = (numMap && numMap[refKey]) || (i + 1);
    const days = _atomAgeDays(a);
    const old = days != null && days >= _REDISCOVERY_DAYS;
    const oldClass = old ? ' rediscovery' : '';

    const raw = a.content || a.source_title || a.subject || '—';
    const preview = escHtml(raw.length > 90 ? raw.slice(0, 90) + '…' : raw);

    const isUrl = a.source_id && /^https?:\/\//.test(a.source_id);
    const srcLabel = escHtml(a.source_title || a.source_id || '');
    const srcLink = isUrl
      ? `<a class="ref-source-link" href="${escHtml(a.source_id)}" target="_blank" rel="noopener">${srcLabel}</a>`
      : '';

    const kindBadge = a.kind && !_SKIP_KINDS.has(a.kind)
      ? `<span class="ref-kind">${escHtml(a.kind)}</span>` : '';

    const channel = _channelLabel(a.source_id);
    const channelBadge = channel ? `<span class="ref-channel">${escHtml(channel)}</span>` : '';

    const age = _refAgeLabel(a);
    const ageSpan = age ? `<span class="ref-age-label${old ? ' is-old' : ''}">${escHtml(age)}</span>` : '';

    const atomId = escHtml(a.atom_id || '');
    const dismissBtn = atomId
      ? `<button class="ref-dismiss" title="Not relevant" data-atom-id="${atomId}">✕</button>`
      : '';

    return `
    <li class="ref-item${oldClass}" id="ref-${escHtml(refKey)}" data-atom-id="${atomId}">
      <span class="ref-num">[${num}]</span>
      <div class="ref-body">
        <span class="ref-preview">${preview}</span>
        ${srcLink ? `<span class="ref-source">${srcLink}</span>` : ''}
        <span class="ref-meta">${kindBadge}${channelBadge}${ageSpan}</span>
      </div>
      ${dismissBtn}
    </li>`;
  }).join('');

  const label = `${orderedAtoms.length} source${orderedAtoms.length > 1 ? 's' : ''}`;
  return `
    <div class="references">
      <div class="references-label">
        <button class="sources-toggle ${collapsed ? '' : 'open'}" aria-expanded="${!collapsed}">
          <i class="toggle-arrow">▸</i> ${label}
        </button>
      </div>
      <div class="ref-list-wrap ${collapsed ? '' : 'open'}">
        <ol class="ref-list">${items}</ol>
      </div>
    </div>`;
}

function bindSourcesToggle(turn) {
  const toggle = turn.querySelector('.sources-toggle');
  if (!toggle) return;
  const wrap = turn.querySelector('.ref-list-wrap');
  toggle.addEventListener('click', () => {
    const open = wrap.classList.toggle('open');
    toggle.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', open);
  });
}

function bindSourceDismiss(refsEl, turn) {
  refsEl.querySelectorAll('.ref-dismiss').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const atomId = btn.dataset.atomId;
      if (!atomId) return;
      btn.closest('.ref-item').classList.add('dismissed');
      btn.disabled = true;
      if (turn._dismissedIds) turn._dismissedIds.add(atomId);
    });
  });
}

// ── copy button ───────────────────────────────────────────────────────────

function bindCopyBtn(turn, plainText) {
  const btn = turn.querySelector('.copy-btn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(plainText);
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
    } catch (_) {}
  });
}

// ── daemon status ─────────────────────────────────────────────────────────

async function checkDaemonStatus() {
  try {
    const res = await fetch('/health', { signal: AbortSignal.timeout(2000) });
    if (res.ok) {
      statusDot.className = 'status-dot connected';
      statusLbl.textContent = 'Connected';
      return;
    }
  } catch (_) {}
  statusDot.className = 'status-dot disconnected';
  statusLbl.textContent = 'Daemon offline';
}

// ── recent atoms panel ────────────────────────────────────────────────────

async function loadRecentAtoms() {
  try {
    const res = await fetch('/api/atoms/recent?limit=50');
    if (!res.ok) return;
    const atoms = await res.json();
    renderAtomsList(atoms);
    if (memCount) memCount.textContent = atoms.length ? `· ${atoms.length}` : '';
    initSparks(atoms);
  } catch (_) {}
}

function renderAtomsList(atoms) {
  if (!atoms.length) {
    atomsList.innerHTML = `
      <div class="atoms-empty">
        No memories yet.<br>Drop a file into<br><code>~/.lattice/inbox/</code>
      </div>`;
    return;
  }

  // Group by kind, preserving recency order within each group
  const kindOrder = ['preference', 'decision', 'fact', 'goal', 'event', 'habit', 'reminder', 'count'];
  const groups = {};
  for (const a of atoms) {
    const k = a.kind || 'fact';
    if (!groups[k]) groups[k] = [];
    groups[k].push(a);
  }

  // Sort groups: known kinds first in defined order, then unknowns alphabetically
  const sortedKinds = [
    ...kindOrder.filter(k => groups[k]),
    ...Object.keys(groups).filter(k => !kindOrder.includes(k)).sort(),
  ];

  // Preserve expanded state across re-renders
  const expanded = new Set(
    [...atomsList.querySelectorAll('.kind-group.open')].map(el => el.dataset.kind)
  );

  atomsList.innerHTML = sortedKinds.map(kind => {
    const items = groups[kind];
    const isOpen = expanded.size === 0 ? true : expanded.has(kind); // default all open on first render
    const rows = items.map(a => `
      <div class="atom-item">
        <div class="atom-subject">${escHtml(a.subject || '(no subject)')}</div>
        <div class="atom-time">${relativeTime(a.observed_at)}</div>
      </div>`).join('');
    return `
      <div class="kind-group ${isOpen ? 'open' : ''}" data-kind="${escHtml(kind)}">
        <button class="kind-header">
          <span class="kind-icon" data-kind="${escHtml(kind)}">${kindIcon(kind)}</span>
          <span class="kind-label">${escHtml(kind.charAt(0).toUpperCase() + kind.slice(1))}</span>
          <span class="kind-count">${items.length}</span>
          <span class="kind-arrow">▸</span>
        </button>
        <div class="kind-items">${rows}</div>
      </div>`;
  }).join('');

  // Bind toggles
  atomsList.querySelectorAll('.kind-header').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('.kind-group').classList.toggle('open');
    });
  });
}

// ── memory sparks ────────────────────────────────────────────────────────

let _ghostInterval = null;

function _sparkQuestion(atom) {
  const s = atom.subject || 'that';
  if (atom.kind === 'decision') return `What did I decide about ${s}?`;
  if (atom.kind === 'preference') return `What do I prefer about ${s}?`;
  return `Tell me about ${s}`;
}

function initSparks(atoms) {
  // Only affect empty state — stop if a conversation is active
  if (!history.querySelector('.empty-state')) return;

  const emptyState = history.querySelector('.empty-state');
  const existingSparks = emptyState.querySelector('.spark-cards');
  if (existingSparks) existingSparks.remove();

  if (!atoms.length) {
    // True empty state — no cards, no ghost
    input.setAttribute('placeholder', 'Ask your memory anything…');
    if (_ghostInterval) { clearInterval(_ghostInterval); _ghostInterval = null; }
    const emptyMsg = emptyState.querySelector('.empty-spark-msg');
    if (!emptyMsg) {
      const msg = document.createElement('p');
      msg.className = 'empty-spark-msg';
      msg.textContent = 'Your memory starts here. Save something worth keeping, then come back and ask about it.';
      emptyState.appendChild(msg);
    }
    return;
  }

  // Remove true-empty message if atoms now exist
  const emptyMsg = emptyState.querySelector('.empty-spark-msg');
  if (emptyMsg) emptyMsg.remove();

  // Warm welcome message — only inject once
  if (!emptyState.querySelector('.spark-welcome')) {
    const welcome = document.createElement('p');
    welcome.className = 'spark-welcome';
    welcome.textContent = 'What would you like to remember today?';
    emptyState.appendChild(welcome);
  }

  // Ghost queries — cycle every 3s
  const ghostQueries = atoms.slice(0, 4).map(_sparkQuestion);
  let ghostIdx = 0;
  input.setAttribute('placeholder', ghostQueries[0]);
  if (_ghostInterval) clearInterval(_ghostInterval);
  _ghostInterval = setInterval(() => {
    ghostIdx = (ghostIdx + 1) % ghostQueries.length;
    input.setAttribute('placeholder', ghostQueries[ghostIdx]);
  }, 3000);

  // Clicking placeholder area fills the input with the current ghost query
  input.addEventListener('focus', () => {
    if (!input.value) input.value = input.getAttribute('placeholder') === 'Ask anything…' ? '' : '';
  }, { once: true });

  // Spark cards — 3 cards from first 3 atoms
  const cardAtoms = atoms.slice(0, 3);
  const cards = cardAtoms.map(a => {
    const q = _sparkQuestion(a);
    const timeLabel = relativeTime(a.ingested_at || a.observed_at);
    const icon = kindIcon(a.kind);
    return `<button class="spark-card" data-question="${escHtml(q)}">
      <span class="spark-icon">${icon}</span>
      <span class="spark-question">${escHtml(q)}</span>
      <span class="spark-time">${escHtml(timeLabel)}</span>
    </button>`;
  }).join('');

  const wrap = document.createElement('div');
  wrap.className = 'spark-cards';
  wrap.innerHTML = cards;
  emptyState.appendChild(wrap);

  wrap.querySelectorAll('.spark-card').forEach(card => {
    card.addEventListener('click', () => {
      input.value = card.dataset.question;
      input.focus();
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
  });
}

// Hide sparks and ghost queries once conversation starts
function clearSparks() {
  if (_ghostInterval) { clearInterval(_ghostInterval); _ghostInterval = null; }
  input.setAttribute('placeholder', 'Ask anything…');
}

// ── scroll-to-bottom ──────────────────────────────────────────────────────

function initScrollBtn() {
  history.addEventListener('scroll', () => {
    const nearBottom = history.scrollHeight - history.scrollTop - history.clientHeight < 80;
    scrollBtn.classList.toggle('visible', !nearBottom && history.scrollHeight > history.clientHeight + 100);
  });
  scrollBtn.addEventListener('click', () =>
    history.scrollTo({ top: history.scrollHeight, behavior: 'smooth' }));
}

// ── chat turns ────────────────────────────────────────────────────────────

function appendTurn(question) {
  const turn = document.createElement('div');
  turn.className = 'turn';
  turn.innerHTML = `
    <span class="turn-time">${formatTime(new Date())}</span>
    <div class="question">${escHtml(question)}</div>
    <div class="answer-wrap">
      <div class="loading-indicator">
        ${makeRingHTML()}
        <div class="loading-text">
          <span class="loading-label">Searching memories…</span>
          <span class="loading-timer"></span>
        </div>
      </div>
      <div class="answer-toolbar" style="display:none">
        <button class="copy-btn">Copy</button>
      </div>
      <div class="answer streaming" style="display:none"></div>
      <div class="references-container"></div>
      <div class="feedback-row" style="display:none">
        <span class="feedback-label">Was this answer helpful?</span>
        <button class="feedback-btn" data-val="up">👍 Yes</button>
        <button class="feedback-btn" data-val="down">👎 No</button>
      </div>
      <div class="feedback-reasons" style="display:none">
        <span class="feedback-label">What went wrong?</span>
        <div class="reason-chips">
          <button class="reason-chip" data-reason="wrong_sources">Wrong sources pulled</button>
          <button class="reason-chip" data-reason="inaccurate">Answer is inaccurate</button>
          <button class="reason-chip" data-reason="incomplete">Incomplete answer</button>
          <button class="reason-chip" data-reason="off_topic">Off topic</button>
        </div>
      </div>
      <div class="error-msg" style="display:none"></div>
    </div>`;

  const empty = history.querySelector('.empty-state');
  if (empty) empty.remove();
  clearSparks();

  history.appendChild(turn);
  turn.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return turn;
}

// ── feedback ──────────────────────────────────────────────────────────────

function bindFeedback(turn, question, answer, atomIds) {
  const reasonsEl = turn.querySelector('.feedback-reasons');

  turn.querySelectorAll('.feedback-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const val = btn.dataset.val;
      turn.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('active-up', 'active-down'));
      btn.classList.add(val === 'up' ? 'active-up' : 'active-down');
      if (val === 'down') {
        reasonsEl.style.display = 'flex';
      } else {
        reasonsEl.style.display = 'none';
        turn.querySelector('.feedback-row .feedback-label').textContent = 'Thanks!';
        await postFeedback(question, answer, 'up', null, atomIds, turn._dismissedIds, turn._citationMap);
      }
    });
  });

  turn.querySelectorAll('.reason-chip').forEach(chip => {
    chip.addEventListener('click', async () => {
      turn.querySelectorAll('.reason-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      turn.querySelector('.feedback-row .feedback-label').textContent = 'Thanks for the feedback!';
      reasonsEl.style.display = 'none';
      await postFeedback(question, answer, 'down', chip.dataset.reason, atomIds, turn._dismissedIds, turn._citationMap);
    });
  });
}

async function postFeedback(question, answer, rating, reason, atomIds, dismissedIds, citationMap) {
  try {
    await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        answer,
        rating,
        reason,
        atom_ids: atomIds || [],
        dismissed_atom_ids: dismissedIds ? [...dismissedIds] : [],
        citation_map: citationMap || {},
      }),
    });
  } catch (_) {}
}

// ── SSE streaming ─────────────────────────────────────────────────────────

async function ask(question) {
  const turn       = appendTurn(question);
  const loading    = turn.querySelector('.loading-indicator');
  const labelEl    = turn.querySelector('.loading-label');
  const toolbar    = turn.querySelector('.answer-toolbar');
  const answerEl   = turn.querySelector('.answer');
  const refsEl     = turn.querySelector('.references-container');
  const feedbackEl = turn.querySelector('.feedback-row');
  const errorEl    = turn.querySelector('.error-msg');

  let rawAnswer = '';
  let citIndex  = { byId: {}, ordered: [] };
  let cursorEl  = null;

  const timer = startRing(turn);

  try {
    lastActivityAt = Date.now();
    const resp = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        conversation_history: conversationHistory,
        session_id: sessionId,
      }),
    });
    if (!resp.ok) throw new Error(`Request failed: ${resp.status}`);

    answerEl.style.display = 'block';

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split('\n\n');
      buf = parts.pop();

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith('data: ')) continue;
        const evt = JSON.parse(line.slice(6));

        if (evt.type === 'atoms') {
          const count = (evt.atoms || []).length;
          labelEl.textContent = count
            ? `Found ${count} relevant memor${count === 1 ? 'y' : 'ies'}…`
            : 'Writing answer…';
          turn._atomCount = count;  // store for feedback threshold check
          citIndex  = buildCitationIndex(evt.atoms || []);
          atomsById  = {};
          atomNumMap = citIndex.byId;
          citIndex.ordered.forEach(a => { const k = a.atom_id || a.source_id; if (k) atomsById[k] = a; });

        } else if (evt.type === 'token') {
          if (loading.style.display !== 'none') {
            loading.style.display = 'none';
            toolbar.style.display = 'flex';
            stopRing(timer);
            // add typewriter cursor
            cursorEl = document.createElement('span');
            cursorEl.className = 'cursor';
            answerEl.appendChild(cursorEl);
          }
          rawAnswer += evt.text;
          // insert text before cursor
          if (cursorEl) {
            const textNode = document.createTextNode(evt.text);
            answerEl.insertBefore(textNode, cursorEl);
          } else {
            answerEl.textContent = rawAnswer;
          }
          turn.scrollIntoView({ behavior: 'smooth', block: 'end' });

        } else if (evt.type === 'citations_applied') {
          // remove cursor, render markdown + citations
          if (cursorEl) cursorEl.remove();

          // num_map comes from server (first-appearance order)
          const numMap = evt.num_map || {};

          const cited = renderCitations(evt.answer, numMap);
          answerEl.innerHTML = renderMarkdown(cited);
          answerEl.classList.remove('streaming');

          // Build citedAtoms in citation-number order from server num_map
          const keysByNum = Object.entries(numMap).sort((a, b) => a[1] - b[1]).map(e => e[0]);
          const citedAtoms = keysByNum
            .map(k => citIndex.ordered.find(a => a.src_key === k || a.atom_id === k || a.source_id === k))
            .filter(Boolean);

          // Build citation map (atom_id → citation number) and per-turn dismissed set
          const citationMap = {};
          keysByNum.forEach((k, idx) => {
            const atom = citedAtoms[idx];
            if (atom && atom.atom_id) citationMap[atom.atom_id] = String(idx + 1);
          });
          turn._citationMap = citationMap;
          turn._dismissedIds = new Set();

          refsEl.innerHTML = renderReferences(citedAtoms, numMap);
          bindSourceDismiss(refsEl, turn);
          if (evt.pii_protected) {
            const badge = document.createElement('span');
            badge.className = 'pii-badge';
            badge.textContent = '🔒 PII protected';
            answerEl.prepend(badge);
          }
          // Amber glow on inline citations for atoms ≥30 days old
          citedAtoms.forEach(a => {
            const days = _atomAgeDays(a);
            if (days == null || days < _REDISCOVERY_DAYS) return;
            const src = a.src_key || a.atom_id || a.source_id;
            if (!src) return;
            turn.querySelectorAll(`.citation[data-src="${CSS.escape(src)}"]`)
                .forEach(el => el.classList.add('rediscovery'));
          });
          feedbackEl.style.display = 'flex';
          const citedAtomIds = citedAtoms.map(a => a.atom_id).filter(Boolean);
          bindFeedback(turn, question, plainCitations(evt.answer, numMap), citedAtomIds);
          bindCitationLinks(turn);
          bindSourcesToggle(turn);
          bindCopyBtn(turn, evt.answer);
          loadRecentAtoms();
          loadUsageSummary({ checkMilestone: true });
          // Topic depth check for cited subjects
          const citedSubjects = [...new Set(citedAtoms.map(a => a.subject).filter(Boolean))];
          if (citedSubjects.length) checkTopicDepth(citedSubjects);
          sessionQA.push({ question, answer: evt.answer });
          conversationHistory.push({ question, answer: evt.answer });
          saveSessionBtn.disabled = false;

        } else if (evt.type === 'error') {
          if (cursorEl) cursorEl.remove();
          stopRing(timer);
          loading.style.display = 'none';
          errorEl.textContent = evt.message;
          errorEl.style.display = 'block';
        }
      }
    }
  } catch (err) {
    if (cursorEl) cursorEl.remove();
    stopRing(timer);
    loading.style.display = 'none';
    errorEl.textContent = err.message;
    errorEl.style.display = 'block';
  }
}

// ── keyboard shortcuts ────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { input.value = ''; input.focus(); }
});

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) form.requestSubmit();
});

// ── form submit ───────────────────────────────────────────────────────────

form.addEventListener('submit', async e => {
  e.preventDefault();
  if (busy) return;
  const question = input.value.trim();
  if (!question) return;
  busy = true;
  submitBtn.disabled = true;
  input.value = '';
  await ask(question);
  busy = false;
  submitBtn.disabled = false;
  input.focus();
});

// ── usage streak + milestones ─────────────────────────────────────────────

const _MILESTONES = {
  1:  "First recall. Good start.",
  7:  "A week in. Lattice is starting to know you.",
  14: null, // built dynamically with atom count
  30: "30 days. You've built something here. Try going a week without it — you'll know it's working.",
};

function _milestoneKey(day) { return `lattice_milestone_shown_${day}`; }

function showMilestoneCard(streak, atomCount) {
  if (!_MILESTONES.hasOwnProperty(streak)) return;
  if (localStorage.getItem(_milestoneKey(streak))) return;
  localStorage.setItem(_milestoneKey(streak), '1');

  let msg = _MILESTONES[streak];
  if (streak === 14) {
    msg = `Two weeks of asking and remembering. You have ${atomCount} things stored — this is becoming real.`;
  }

  const card = document.createElement('div');
  card.className = 'milestone-card';
  card.innerHTML = `
    <span class="milestone-msg">${escHtml(msg)}</span>
    <button class="milestone-dismiss" aria-label="Dismiss">✕</button>`;
  card.querySelector('.milestone-dismiss').addEventListener('click', () => card.remove());

  // Insert before the first turn, or at top of history
  const firstTurn = history.querySelector('.turn');
  if (firstTurn) history.insertBefore(card, firstTurn);
  else history.appendChild(card);

  // Cube particle burst — one per session
  if (!sessionStorage.getItem('lattice_burst_done')) {
    sessionStorage.setItem('lattice_burst_done', '1');
    const cube = document.querySelector('.logo-cube');
    if (cube) {
      cube.classList.add('milestone-burst');
      setTimeout(() => cube.classList.remove('milestone-burst'), 900);
    }
  }
}

async function loadConversationHistory() {
  try {
    const resp = await fetch(`/api/chat/recent?session_id=${encodeURIComponent(sessionId)}&limit=2`);
    if (!resp.ok) return;
    const turns = await resp.json();
    if (Array.isArray(turns) && turns.length) {
      conversationHistory = turns;
    }
  } catch {}
}

async function loadUsageSummary({ checkMilestone = false } = {}) {
  try {
    const resp = await fetch('/api/usage/summary');
    if (!resp.ok) return;
    const data = await resp.json();
    const streak = data.streak || 0;
    const grace = data.grace_day_active || false;
    const atomCount = data.atom_count || 0;

    if (streak === 0 && !grace) {
      streakBadge.textContent = '';
      streakBadge.style.display = 'none';
    } else {
      let label;
      if (streak >= 30) label = `${streak} days deep 🎯`;
      else if (streak === 1) label = `1 day deep`;
      else label = `${streak} days deep`;
      if (grace) label += ' · rest day';
      streakBadge.textContent = label;
      streakBadge.title = 'Consecutive days you\'ve recalled something. Goal: 30 days deep.';
      streakBadge.style.display = 'flex';
    }

    // Only show milestone card after a real query — not on page load
    if (checkMilestone && streak > 0) showMilestoneCard(streak, atomCount);
  } catch {
    // silently ignore — streak is non-critical
  }
}

// ── weekly report ─────────────────────────────────────────────────────────

function _isoWeek(d) {
  // Returns "YYYY-Www" for a given Date
  const jan4 = new Date(d.getFullYear(), 0, 4);
  const weekNum = Math.ceil(((d - jan4) / 86400000 + jan4.getDay() + 1) / 7);
  return `${d.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

async function loadWeeklyReport() {
  try {
    const now = new Date();
    if (now.getDay() !== 1) return; // Monday only
    const weekKey = `lattice_weekly_report_${_isoWeek(now)}`;
    if (localStorage.getItem(weekKey)) return;

    const resp = await fetch('/api/usage/weekly');
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.streak < 7) return; // only after first full week

    localStorage.setItem(weekKey, '1');

    const topicLine = data.top_topic ? `Most on your mind: ${data.top_topic}` : '';
    const newLine = data.new_topics?.length ? `Something new: ${data.new_topics[0]}` : '';
    const streakLine = data.streak ? `${data.streak} days deep.` : '';
    const body = [
      `${data.atoms_this_week} things saved · ${data.recalls_this_week} questions asked · ${data.topics_this_week} topics`,
      topicLine, newLine, streakLine,
    ].filter(Boolean).join('\n');

    const card = document.createElement('div');
    card.className = 'milestone-card weekly-report-card';
    card.innerHTML = `
      <div class="weekly-report-body">
        <div class="weekly-report-title">This week</div>
        <div class="weekly-report-lines">${escHtml(body).replace(/\n/g, '<br>')}</div>
      </div>
      <button class="milestone-dismiss" aria-label="Dismiss">✕</button>`;
    card.querySelector('.milestone-dismiss').addEventListener('click', () => card.remove());

    const emptyState = history.querySelector('.empty-state');
    if (emptyState) emptyState.insertAdjacentElement('afterend', card);
    else history.prepend(card);
  } catch {
    // non-critical
  }
}

// ── topic depth ───────────────────────────────────────────────────────────

const _DEPTH_THRESHOLDS = [
  [20, "This is one of the things you know best."],
  [10, "You've thought about this a lot."],
  [5,  "That's a topic you know well."],
];

async function checkTopicDepth(subjects) {
  for (const subject of subjects) {
    if (!subject) continue;
    const key = `lattice_topic_depth_${subject.toLowerCase().replace(/\s+/g, '_')}`;
    if (localStorage.getItem(key)) continue;

    try {
      const resp = await fetch(`/api/topic/depth?subject=${encodeURIComponent(subject)}`);
      if (!resp.ok) continue;
      const { count } = await resp.json();
      const hit = _DEPTH_THRESHOLDS.find(([t]) => count >= t);
      if (!hit) continue;
      localStorage.setItem(key, String(hit[0]));

      const card = document.createElement('div');
      card.className = 'milestone-card topic-depth-card';
      card.innerHTML = `
        <span class="milestone-msg">You've saved ${count} things about <em>${escHtml(subject)}</em>. ${escHtml(hit[1])}</span>
        <button class="milestone-dismiss" aria-label="Dismiss">✕</button>`;
      card.querySelector('.milestone-dismiss').addEventListener('click', () => card.remove());
      history.appendChild(card);
    } catch {
      // non-critical
    }
  }
}

// ── save session ──────────────────────────────────────────────────────────

saveSessionBtn.addEventListener('click', async () => {
  if (!sessionQA.length) return;
  saveSessionBtn.disabled = true;
  saveSessionBtn.textContent = 'Saving…';

  const chunk = sessionQA
    .map(({ question, answer }) => `user: ${question}\nassistant: ${answer}`)
    .join('\n\n');

  try {
    const resp = await fetch('/api/ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: chunk, source_id: 'web' }),
    });
    if (!resp.ok) throw new Error('ingest failed');
    sessionQA = [];
    saveSessionBtn.textContent = '✓ Saved';
    setTimeout(() => {
      saveSessionBtn.textContent = 'Save session';
      saveSessionBtn.disabled = true; // re-disable until next Q&A
    }, 2000);
  } catch {
    saveSessionBtn.textContent = 'Save session';
    saveSessionBtn.disabled = false;
  }
});

// ── file upload ───────────────────────────────────────────────────────────

fileUpload.addEventListener('change', async () => {
  const files = Array.from(fileUpload.files);
  if (!files.length) return;
  fileUpload.value = '';

  const label = document.querySelector('.upload-btn');
  label.classList.add('uploading');
  uploadProgress.classList.add('active');

  const prevPlaceholder = input.getAttribute('placeholder');
  const fileWord = files.length === 1 ? files[0].name : `${files.length} files`;
  input.setAttribute('placeholder', `Reading ${fileWord}…`);
  input.disabled = true;

  function showToast(msg, isError = false, duration = 5000) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = 'upload-toast' + (isError ? ' upload-toast-error' : '');
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
  }

  function buildMsg(fname, data) {
    const added   = data.atoms_new || 0;
    const updated = data.atoms_updated || 0;
    const s = n => n !== 1 ? 's' : '';
    if (added === 0 && updated === 0) {
      return `${fname} — already knew all of this. Nothing new.`;
    }
    if (added && updated) {
      return `${fname} — ${added} new idea${s(added)} picked up, ${updated} refreshed. Your memory grew ✓`;
    }
    if (added) {
      return `${fname} — ${added} new idea${s(added)} saved to your memory ✓`;
    }
    return `${fname} — ${updated} thing${s(updated)} refreshed with newer info ✓`;
  }

  async function uploadOne(file) {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch('/api/ingest-file', { method: 'POST', body: formData });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || 'Upload failed');
    return { file, data };
  }

  try {
    const results = await Promise.allSettled(files.map(uploadOne));
    let anySuccess = false;
    for (const r of results) {
      if (r.status === 'fulfilled') {
        showToast(buildMsg(r.value.file.name, r.value.data));
        anySuccess = true;
      } else {
        showToast(`${r.reason?.file?.name || 'File'} — ${r.reason?.message || 'upload failed'}`, true);
      }
    }
    if (anySuccess) loadRecentAtoms();
  } catch {
    showToast('Upload failed — daemon may be offline.', true, 4000);
  } finally {
    label.classList.remove('uploading');
    uploadProgress.classList.remove('active');
    input.disabled = false;
    input.setAttribute('placeholder', prevPlaceholder || 'Ask anything…');
  }
});

// ── init ──────────────────────────────────────────────────────────────────

initGreeting();
initScrollBtn();
checkDaemonStatus();
loadRecentAtoms();
loadUsageSummary();
loadWeeklyReport();
loadConversationHistory();
setInterval(loadRecentAtoms, 15000);
setInterval(checkDaemonStatus, 30000);

// Reset conversation history after 30 min of inactivity
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    if (Date.now() - lastActivityAt > 30 * 60 * 1000) {
      conversationHistory = [];
    }
    lastActivityAt = Date.now();
  }
});

input.focus();
