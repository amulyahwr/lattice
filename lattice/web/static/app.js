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
let sessionQA          = []; // {question, answer} pairs this session (kept for compat, auto-save owns persistence)
let conversationHistory = []; // {question, answer} last N turns sent to /api/query for reformulation
let lastActivityAt     = Date.now();
let journeyBranches    = []; // [{subject, queries: [{question, timeMs}]}] — built from today's queries

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
const statusDot      = document.getElementById('status-dot');
const statusLbl      = document.getElementById('status-label');
const themeToggle    = document.getElementById('theme-toggle');
const scrollBtn      = document.getElementById('scroll-btn');
const greetingEl     = document.getElementById('greeting');
const streakBadge    = document.getElementById('streak-badge');
const fileUpload     = document.getElementById('file-upload');
const uploadProgress = document.getElementById('upload-progress');
const openingStrip    = document.getElementById('opening-strip');
const journeyPanel    = document.getElementById('journey-panel');
const journeyTreeEl   = document.getElementById('journey-tree');
const journeyClearBtn = document.getElementById('journey-clear');
const autoSaveIndicator = document.getElementById('auto-save-indicator');

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

async function checkAutoSaveStatus() {
  try {
    const res = await fetch('/api/auto-save/status', { signal: AbortSignal.timeout(2000) });
    if (!res.ok) return;
    const { running } = await res.json();
    autoSaveIndicator.style.display = running ? 'inline-flex' : 'none';
  } catch (_) {
    autoSaveIndicator.style.display = 'none';
  }
}

// ── clear sparks on conversation start ────────────────────────────────────

function clearSparks() {
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
      <div class="answer-annotations" style="display:none"></div>
      <div class="curiosity-chips-row" style="display:none"></div>
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
  const reasonsEl  = turn.querySelector('.feedback-reasons');
  const feedbackRow = turn.querySelector('.feedback-row');

  function _lockFeedback(msg) {
    // Replace the row with a single quiet "Thanks" line — no repeated votes
    feedbackRow.innerHTML = `<span class="feedback-label">${msg}</span>`;
  }

  turn.querySelectorAll('.feedback-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const val = btn.dataset.val;
      if (val === 'down') {
        turn.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('active-up', 'active-down'));
        btn.classList.add('active-down');
        reasonsEl.style.display = 'flex';
      } else {
        await postFeedback(question, answer, 'up', null, atomIds, turn._dismissedIds, turn._citationMap);
        _lockFeedback('Thanks!');
      }
    });
  });

  turn.querySelectorAll('.reason-chip').forEach(chip => {
    chip.addEventListener('click', async () => {
      await postFeedback(question, answer, 'down', chip.dataset.reason, atomIds, turn._dismissedIds, turn._citationMap);
      _lockFeedback('Thanks for the feedback!');
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

  let rawAnswer     = '';
  let citIndex      = { byId: {}, ordered: [] };
  let cursorEl      = null;
  let contextReset  = false;  // set from atoms event, used in citations_applied
  let queryTopic    = null;   // server-computed topic label for journey tree

  const timer = startRing(turn);

  _journeyPollActive = true;
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

        if (evt.type === 'captured') {
          if (cursorEl) cursorEl.remove();
          stopRing(timer);
          loading.style.display = 'none';
          const n = (evt.atoms_new || 0) + (evt.atoms_updated || 0);
          answerEl.textContent = n > 0
            ? `Saved${evt.atoms_updated ? ' (updated)' : ''}. ${n} memor${n === 1 ? 'y' : 'ies'} stored.`
            : 'Already in memory — nothing new to add.';
          answerEl.style.display = 'block';
          break;

        } else if (evt.type === 'atoms') {
          // Topic shift → silently reset multi-turn context
          contextReset = evt.context_reset || false;
          queryTopic   = evt.query_topic || null;
          if (contextReset) conversationHistory = [];
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
          loadUsageSummary({ checkMilestone: true });
          // Topic depth check for cited subjects
          const citedSubjects = [...new Set(citedAtoms.map(a => a.subject).filter(Boolean))];
          sessionQA.push({ question, answer: evt.answer });
          conversationHistory.push({ question, answer: evt.answer });

          // Remove curiosity chips from previous turn (only show on most recent)
          history.querySelectorAll('.curiosity-chips-row').forEach(el => {
            if (el.closest('.turn') !== turn) { el.style.display = 'none'; el.innerHTML = ''; }
          });

          // Rediscovery timestamp — quiet annotation below answer
          const annotationsEl = turn.querySelector('.answer-annotations');
          const oldestDays = citedAtoms.reduce((mx, a) => {
            const d = _atomAgeDays(a);
            return (d != null && d > (mx ?? -1)) ? d : mx;
          }, null);
          if (oldestDays != null && oldestDays >= _REDISCOVERY_DAYS) {
            const line = document.createElement('span');
            line.className = 'answer-annotation rediscovery-note';
            line.textContent = `You first saved this ${oldestDays} day${oldestDays === 1 ? '' : 's'} ago.`;
            annotationsEl.appendChild(line);
          }

          // Topic depth inline note (replaces card)
          _checkTopicDepthInline(citedSubjects, annotationsEl);

          if (annotationsEl.children.length) annotationsEl.style.display = 'block';

          // Curiosity chips
          if (citedSubjects.length) {
            const chipsEl = turn.querySelector('.curiosity-chips-row');
            loadCuriosityChips(citedSubjects, chipsEl);
          }

          // Journey tree update
          updateJourneyTree(question, citedSubjects, contextReset, queryTopic);

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
  } finally {
    _journeyPollActive = false;
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

// Returns milestone message string (once per streak day), or null. No card created.
function _getMilestoneMsg(streak, atomCount) {
  if (!_MILESTONES.hasOwnProperty(streak)) return null;
  if (localStorage.getItem(_milestoneKey(streak))) return null;
  localStorage.setItem(_milestoneKey(streak), '1');
  // Cube particle burst on milestone
  if (!sessionStorage.getItem('lattice_burst_done')) {
    sessionStorage.setItem('lattice_burst_done', '1');
    const cube = document.querySelector('.logo-cube');
    if (cube) {
      cube.classList.add('milestone-burst');
      setTimeout(() => cube.classList.remove('milestone-burst'), 900);
    }
  }
  if (streak === 14) {
    return `Two weeks of asking and remembering. You have ${atomCount} things stored — this is becoming real.`;
  }
  return _MILESTONES[streak];
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
    // Milestone moments are now absorbed into the opening strip, not shown as inline cards.
  } catch {
    // silently ignore — streak is non-critical
  }
}

// ── weekly report ─────────────────────────────────────────────────────────

function _isoWeek(d) {
  const jan4 = new Date(d.getFullYear(), 0, 4);
  const weekNum = Math.ceil(((d - jan4) / 86400000 + jan4.getDay() + 1) / 7);
  return `${d.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

// Returns a summary line for this week, or null. Absorbed into opening strip.
async function _getWeeklyReportLine() {
  try {
    const now = new Date();
    if (now.getDay() !== 1) return null; // Monday only
    const weekKey = `lattice_weekly_report_${_isoWeek(now)}`;
    if (localStorage.getItem(weekKey)) return null;

    const resp = await fetch('/api/usage/weekly');
    if (!resp.ok) return null;
    const data = await resp.json();
    if (data.streak < 7) return null; // only after first full week

    localStorage.setItem(weekKey, '1');
    const parts = [`${data.atoms_this_week} saved · ${data.recalls_this_week} questions`];
    if (data.top_topic) parts.push(`Most: ${data.top_topic}`);
    return `This week — ${parts.join(' · ')}`;
  } catch {
    return null;
  }
}

// ── topic depth ───────────────────────────────────────────────────────────

const _DEPTH_THRESHOLDS = [
  [20, "This is one of the things you know best."],
  [10, "You've thought about this a lot."],
  [5,  "That's a topic you know well."],
];

// Inline version: appends a quiet annotation line to annotationsEl (no card).
async function _checkTopicDepthInline(subjects, annotationsEl) {
  for (const subject of subjects) {
    if (!subject) continue;
    const storageKey = `lattice_topic_depth_${subject.toLowerCase().replace(/\s+/g, '_')}`;
    if (localStorage.getItem(storageKey)) continue;
    try {
      const resp = await fetch(`/api/topic/depth?subject=${encodeURIComponent(subject)}`);
      if (!resp.ok) continue;
      const { count } = await resp.json();
      const hit = _DEPTH_THRESHOLDS.find(([t]) => count >= t);
      if (!hit) continue;
      localStorage.setItem(storageKey, String(hit[0]));
      const line = document.createElement('span');
      line.className = 'answer-annotation topic-depth-note';
      line.innerHTML = `You've saved ${count} things about <em>${escHtml(subject)}</em>. ${escHtml(hit[1])}`;
      annotationsEl.appendChild(line);
      annotationsEl.style.display = 'block';
    } catch {
      // non-critical
    }
  }
}

// ── opening strip ─────────────────────────────────────────────────────────

async function loadOpeningStrip() {
  try {
    const [summaryResp, todayResp] = await Promise.all([
      fetch('/api/usage/summary'),
      fetch('/api/chat/today'),  // all channels — one continuous journey
    ]);
    if (!summaryResp.ok) return;
    const summary = await summaryResp.json();
    const todayTurns = todayResp.ok ? await todayResp.json() : [];

    const streak    = summary.streak || 0;
    const atomCount = summary.atom_count || 0;
    const parts     = [];

    // Milestone (once per day)
    const milestoneMsg = _getMilestoneMsg(streak, atomCount);
    if (milestoneMsg) {
      parts.push(`<span class="os-milestone">${escHtml(milestoneMsg)}</span>`);
    }

    // Weekly report (Monday)
    const weekLine = await _getWeeklyReportLine();
    if (weekLine) {
      parts.push(`<span class="os-weekly">${escHtml(weekLine)}</span>`);
    }

    // Stat strip
    const statParts = [];
    if (streak > 0) statParts.push(`${streak} day${streak === 1 ? '' : 's'} deep`);
    if (atomCount > 0) statParts.push(`${atomCount} things saved`);
    if (statParts.length) {
      parts.push(`<span class="os-stats">${escHtml(statParts.join(' · '))}</span>`);
    }

    // Build journey branches first (same logic as loadJourneyToday) so opening strip
    // topics come from branch subjects — not raw atom subjects which can differ
    // (e.g. "Amulya Gupta" from atom vs "Amulya" from query extraction).
    _buildJourneyFromTurns(todayTurns);

    // Topics = the journey branch subjects, most recent first (branches ordered by first-seen)
    const seenTopics = [...journeyBranches].reverse().map(b => b.subject).slice(0, 3);
    if (seenTopics.length) {
      const chips = seenTopics.map(t =>
        `<button class="os-topic-chip" data-q="${escHtml('Tell me about ' + t)}">${escHtml(t)}</button>`
      ).join('');
      parts.push(`<span class="os-topics">You've been thinking about: ${chips}</span>`);
    }

    // Last question from any channel, any day — helps orient on return / channel switch
    try {
      const recentResp = await fetch('/api/chat/recent?limit=1');
      if (recentResp.ok) {
        const recent = await recentResp.json();
        const lastQ = recent.length ? (recent[recent.length - 1].question || '') : '';
        if (lastQ) {
          const short = lastQ.length > 70 ? lastQ.slice(0, 70) + '…' : lastQ;
          parts.push(`<span class="os-last">Last: <button class="os-last-q" data-q="${escHtml(lastQ)}">${escHtml(short)}</button></span>`);
        }
      }
    } catch {
      // non-critical
    }

    if (!parts.length) return;

    openingStrip.innerHTML = parts.join('');
    openingStrip.style.display = 'block';

    // Topic chip + last question click → pre-fill input (no auto-submit)
    openingStrip.querySelectorAll('.os-topic-chip, .os-last-q').forEach(btn => {
      btn.addEventListener('click', () => {
        input.value = btn.dataset.q;
        input.focus();
        openingStrip.style.display = 'none';
      });
    });
  } catch {
    // non-critical
  }
}

// Hide opening strip on first keystroke
input.addEventListener('input', () => {
  if (openingStrip.style.display !== 'none') openingStrip.style.display = 'none';
}, { once: true });

// ── curiosity chips ───────────────────────────────────────────────────────

async function loadCuriosityChips(subjects, chipsEl) {
  try {
    const subjectsParam = subjects.map(encodeURIComponent).join(',');
    const resp = await fetch(`/api/atoms/related?subjects=${subjectsParam}&limit=3`);
    if (!resp.ok) return;
    const related = await resp.json();
    if (!related.length) return;

    const label = document.createElement('span');
    label.className = 'curiosity-label';
    label.textContent = 'You also know about:';
    chipsEl.appendChild(label);

    related.forEach(subj => {
      const chip = document.createElement('button');
      chip.className = 'curiosity-chip';
      chip.textContent = subj;
      chip.addEventListener('click', () => {
        input.value = `Tell me about ${subj}`;
        input.focus();
      });
      chipsEl.appendChild(chip);
    });
    chipsEl.style.display = 'flex';
  } catch {
    // non-critical
  }
}

// ── journey tree ──────────────────────────────────────────────────────────

function _timeAgo(ms) {
  const sec = Math.round((Date.now() - ms) / 1000);
  if (sec < 60)  return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  return `${Math.round(sec / 3600)}h ago`;
}


function _renderJourneyTree() {
  if (!journeyBranches.length) {
    journeyPanel.style.display = 'none';
    return;
  }
  journeyPanel.style.display = 'block';
  journeyTreeEl.innerHTML = journeyBranches.map(branch => {
    const leaves = branch.queries.map(q =>
      `<button class="journey-leaf" title="${escHtml(q.question)}" data-q="${escHtml(q.question)}">
        <span class="journey-leaf-text">${escHtml(q.question.length > 40 ? q.question.slice(0, 40) + '…' : q.question)}</span>
        <span class="journey-leaf-time">${_timeAgo(q.timeMs)}</span>
      </button>`
    ).join('');
    return `<div class="journey-branch">
      <button class="journey-branch-label" data-q="${escHtml('Tell me about ' + branch.subject)}">● ${escHtml(branch.subject)}</button>
      <div class="journey-leaves">${leaves}</div>
    </div>`;
  }).join('');

  journeyTreeEl.querySelectorAll('.journey-branch-label, .journey-leaf').forEach(btn => {
    btn.addEventListener('click', () => {
      input.value = btn.dataset.q;
      input.focus();
    });
  });
}

function updateJourneyTree(question, subjects, contextReset = false, queryTopic = null) {
  const timeMs = Date.now();

  // Follow-up (no topic shift): always append to the current (last) branch
  if (!contextReset && journeyBranches.length > 0) {
    journeyBranches[journeyBranches.length - 1].queries.push({ question, timeMs });
    _renderJourneyTree();
    return;
  }

  // New topic: use server-computed query_topic, fall back to first cited subject
  const label = queryTopic || (subjects.length ? subjects[0] : null);
  if (!label) return;

  // If the extracted label contains an existing branch name (e.g. "Amulyas' email" → "Amulya"),
  // fold into that branch rather than creating a duplicate.
  const labelLower = label.toLowerCase().trim();
  const overlap = journeyBranches.find(b => labelLower.includes(b.subject.toLowerCase().trim()));
  if (overlap) {
    overlap.queries.push({ question, timeMs });
    _renderJourneyTree();
    return;
  }

  journeyBranches.push({ subject: label, queries: [{ question, timeMs }] });
  _renderJourneyTree();
}

function _buildJourneyFromTurns(turns) {
  journeyBranches = [];
  for (const r of turns) {
    const question     = r.question || '';
    const subjects     = r.subjects || [];
    const timeMs       = new Date(r.ts).getTime();
    const contextReset = r.context_reset !== undefined ? r.context_reset : null;

    const queryTopicStored = r.query_topic || null;
    const isFollowUp = contextReset === false ||
      (contextReset === null && !queryTopicStored && journeyBranches.length > 0);

    if (isFollowUp && journeyBranches.length > 0) {
      if (!queryTopicStored) {
        // genuine follow-up with no topic override — merge into current branch
        journeyBranches[journeyBranches.length - 1].queries.push({ question, timeMs });
        continue;
      }
      // Has a topic — only merge if it matches the current branch; otherwise fall through
      const curBranch = journeyBranches[journeyBranches.length - 1];
      const topicLower = queryTopicStored.toLowerCase().trim();
      const curLower = curBranch.subject.toLowerCase().trim();
      if (topicLower.includes(curLower) || curLower.includes(topicLower)) {
        curBranch.queries.push({ question, timeMs });
        continue;
      }
      // Topic doesn't match current branch — fall through to find or create correct branch
    }

    const label = queryTopicStored || (subjects.length ? subjects[0] : null);
    if (!label) continue;

    const labelLower = label.toLowerCase().trim();
    const overlap = journeyBranches.find(b => labelLower.includes(b.subject.toLowerCase().trim()));
    if (overlap) {
      overlap.queries.push({ question, timeMs });
    } else {
      journeyBranches.push({ subject: label, queries: [{ question, timeMs }] });
    }
  }
  _renderJourneyTree();
}

async function loadJourneyToday() {
  try {
    const resp = await fetch('/api/chat/today');
    if (!resp.ok) return;
    _buildJourneyFromTurns(await resp.json());
  } catch {
    // non-critical
  }
}

// Poll for cross-channel turns (e.g. Telegram) written while web UI is open.
// Only rebuilds journey when turn count increases; skips during active SSE stream.
let _journeyPollKnownCount = 0;
let _journeyPollActive = false; // set true while SSE stream is running

function _startJourneyPoll() {
  setInterval(async () => {
    if (_journeyPollActive) return;
    try {
      const resp = await fetch('/api/chat/today');
      if (!resp.ok) return;
      const turns = await resp.json();
      if (turns.length > _journeyPollKnownCount) {
        _journeyPollKnownCount = turns.length;
        _buildJourneyFromTurns(turns);
      }
    } catch {
      // non-critical
    }
  }, 30000); // 30s
}


// ── journey clear ─────────────────────────────────────────────────────────

journeyClearBtn.addEventListener('click', async () => {
  try {
    const resp = await fetch('/api/chat/clear-today', { method: 'POST' });
    if (!resp.ok) return;
    journeyBranches = [];
    conversationHistory = [];
    _journeyPollKnownCount = 0;
    _renderJourneyTree();
    // Refresh opening strip so topics + last-Q reflect cleared state
    openingStrip.style.display = 'none';
    openingStrip.innerHTML = '';
    await loadOpeningStrip();
  } catch (_) {}
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
    if (anySuccess) loadJourneyToday();
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
loadUsageSummary();
loadOpeningStrip().then(async () => {
  // Seed poll count from current turn count so first tick only fires on new turns
  try {
    const r = await fetch('/api/chat/today');
    if (r.ok) _journeyPollKnownCount = (await r.json()).length;
  } catch {}
  _startJourneyPoll();
});
loadConversationHistory();
setInterval(checkDaemonStatus, 30000);
setInterval(checkAutoSaveStatus, 5000);

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
