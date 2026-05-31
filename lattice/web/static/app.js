'use strict';

// ── constants ─────────────────────────────────────────────────────────────

const KIND_ICON = {
  preference:     '♥',
  fact:           '◆',
  goal:           '◎',
  recommendation: '★',
  event:          '◷',
};

const CIRCUMFERENCE = 2 * Math.PI * 10; // 62.83 — matches r=10 in SVG

const HISTORY_KEY = 'lattice-response-times';
const MAX_HISTORY = 6;

// ── state ─────────────────────────────────────────────────────────────────

let atomsById  = {};
let atomNumMap = {};
let busy       = false;

// ── DOM refs ──────────────────────────────────────────────────────────────

const form        = document.getElementById('query-form');
const input       = document.getElementById('question');
const submitBtn   = document.getElementById('submit');
const history     = document.getElementById('chat-history');
const atomsList   = document.getElementById('atoms-list');
const statusDot   = document.getElementById('status-dot');
const statusLbl   = document.getElementById('status-label');
const themeToggle = document.getElementById('theme-toggle');
const scrollBtn   = document.getElementById('scroll-btn');
const memCount    = document.getElementById('memory-count');
const greetingEl  = document.getElementById('greeting');

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
    if (a.source_id && !(a.source_id in byId)) {
      byId[a.source_id] = n++;
      ordered.push(a);
    }
  });
  return { byId, ordered };
}

function renderCitations(html, numMap) {
  // run after markdown — replace citation markers in rendered HTML text nodes
  return html.replace(
    /\[([^\]]+)\]\[src:([^\]]+)\]|\[src:([^\]]+)\]/g,
    (_, label, id1, id2) => {
      const id  = id1 || id2;
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

function renderReferences(orderedAtoms) {
  if (!orderedAtoms.length) return '';
  const collapsed = orderedAtoms.length > 3;
  const items = orderedAtoms.map((a, i) => `
    <li class="ref-item" id="ref-${escHtml(a.source_id || String(i+1))}">
      <span class="ref-num">[${i + 1}]</span>
      <span class="ref-source">${escHtml(a.source_title || a.source_id || '—')}</span>
    </li>`).join('');

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
  atomsList.innerHTML = atoms.slice(0, 20).map(a => `
    <div class="atom-item">
      <div class="atom-subject">${escHtml(a.subject || '(no subject)')}</div>
      <div class="atom-meta">
        <span class="atom-kind" data-kind="${escHtml(a.kind || 'fact')}">${kindIcon(a.kind)} ${escHtml(a.kind || 'fact')}</span>
        <span class="atom-time">${relativeTime(a.observed_at)}</span>
      </div>
    </div>`).join('');
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

  history.appendChild(turn);
  turn.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return turn;
}

// ── feedback ──────────────────────────────────────────────────────────────

function bindFeedback(turn, question, answer) {
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
        await postFeedback(question, answer, 'up', null);
      }
    });
  });

  turn.querySelectorAll('.reason-chip').forEach(chip => {
    chip.addEventListener('click', async () => {
      turn.querySelectorAll('.reason-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      turn.querySelector('.feedback-row .feedback-label').textContent = 'Thanks for the feedback!';
      reasonsEl.style.display = 'none';
      await postFeedback(question, answer, 'down', chip.dataset.reason);
    });
  });
}

async function postFeedback(question, answer, rating, reason) {
  try {
    await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, answer, rating, reason }),
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
    const resp = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
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
          citIndex  = buildCitationIndex(evt.atoms || []);
          atomsById  = {};
          atomNumMap = citIndex.byId;
          citIndex.ordered.forEach(a => { if (a.source_id) atomsById[a.source_id] = a; });

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
          const md = renderMarkdown(evt.answer);
          answerEl.innerHTML = renderCitations(md, citIndex.byId);
          answerEl.classList.remove('streaming');
          refsEl.innerHTML = renderReferences(citIndex.ordered);
          feedbackEl.style.display = 'flex';
          bindFeedback(turn, question, evt.answer);
          bindCitationLinks(turn);
          bindSourcesToggle(turn);
          bindCopyBtn(turn, evt.answer);
          loadRecentAtoms();

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

// ── init ──────────────────────────────────────────────────────────────────

initGreeting();
initScrollBtn();
checkDaemonStatus();
loadRecentAtoms();
setInterval(loadRecentAtoms, 15000);
setInterval(checkDaemonStatus, 30000);
input.focus();
