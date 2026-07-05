/* ================================================================
   RENEWLY — script.js
   GSAP page-load sequence · Graph node cycling · API wiring
   ================================================================ */

'use strict';

/* ----------------------------------------------------------------
   0. CONSTANTS
   ---------------------------------------------------------------- */
const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const GRAPH_CYCLE_MS = 2200; // ms per active node

/* ----------------------------------------------------------------
   1. GSAP SETUP
   ---------------------------------------------------------------- */
if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
  gsap.registerPlugin(ScrollTrigger);
}

/* ----------------------------------------------------------------
   2. DOM READY
   ---------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  initHeroAnimation();
  initGraphCycle();
  initLifecycleReveal();
  initAskInterface();
  loadItemsDashboard();
});

/* ----------------------------------------------------------------
   3. HERO PAGE-LOAD SEQUENCE
      Orchestrated: headline → sub → CTA → graph (under 800ms total)
   ---------------------------------------------------------------- */
function initHeroAnimation() {
  const heroText   = document.getElementById('hero-text');
  const heroVisual = document.getElementById('hero-visual');

  if (!heroText || !heroVisual) return;

  if (REDUCED_MOTION || typeof gsap === 'undefined') {
    // Accessibility: just ensure everything is visible
    heroText.style.opacity   = '1';
    heroVisual.style.opacity = '1';
    return;
  }

  // Set initial state BEFORE browser paints (avoids flash)
  gsap.set('#hero-headline', { opacity: 0, y: 26 });
  gsap.set('#hero-sub',      { opacity: 0, y: 20 });
  gsap.set('#hero-cta',      { opacity: 0, y: 14 });
  gsap.set(heroVisual,       { opacity: 0 });

  const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });

  tl.to('#hero-headline', { opacity: 1, y: 0, duration: 0.65 },  0.08)
    .to('#hero-sub',      { opacity: 1, y: 0, duration: 0.60 },  0.22)
    .to('#hero-cta',      { opacity: 1, y: 0, duration: 0.50 },  0.34)
    .to(heroVisual,       { opacity: 1,        duration: 0.75 },  0.42);
}

/* ----------------------------------------------------------------
   4. GRAPH NODE CYCLING
      One node becomes "active" (--recall fill + pulsing ring)
      every GRAPH_CYCLE_MS. Transitions are CSS (0.55s ease).
   ---------------------------------------------------------------- */
function initGraphCycle() {
  const nodes = Array.from(document.querySelectorAll('.graph-node'));
  if (!nodes.length) return;

  let activeIndex = 0;

  function activateNode(index) {
    nodes.forEach(n => n.classList.remove('active'));
    nodes[index].classList.add('active');
  }

  // Start immediately so the graph looks alive on first paint
  activateNode(0);

  if (REDUCED_MOTION) {
    // Reduced motion: keep one node highlighted but skip the pulse cycle
    return;
  }

  setInterval(() => {
    activeIndex = (activeIndex + 1) % nodes.length;
    activateNode(activeIndex);
  }, GRAPH_CYCLE_MS);
}

/* ----------------------------------------------------------------
   5. LIFECYCLE SCROLL REVEAL
      One staggered GSAP animation fires once when the grid
      enters the viewport. No other section gets scroll reveals.
   ---------------------------------------------------------------- */
function initLifecycleReveal() {
  if (typeof gsap === 'undefined' || typeof ScrollTrigger === 'undefined') return;

  const steps = document.querySelectorAll('.lifecycle-step');
  if (!steps.length) return;

  if (REDUCED_MOTION) {
    // Fade only — no translate
    gsap.from(steps, {
      opacity: 0,
      duration: 0.4,
      stagger: 0.1,
      scrollTrigger: { trigger: '#lifecycle-grid', start: 'top 82%', once: true },
    });
    return;
  }

  gsap.from(steps, {
    opacity: 0,
    y: 28,
    duration: 0.65,
    ease: 'power3.out',
    stagger: 0.13,
    scrollTrigger: {
      trigger: '#lifecycle-grid',
      start: 'top 78%',
      once: true,
    },
  });
}

/* ----------------------------------------------------------------
   6. ASK YOUR MEMORY — POST /query
   ---------------------------------------------------------------- */
function initAskInterface() {
  const form   = document.getElementById('ask-form');
  const input  = document.getElementById('ask-input');
  const btn    = document.getElementById('ask-btn');
  const thread = document.getElementById('ask-thread');

  if (!form || !input || !btn || !thread) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const question = input.value.trim();
    if (!question) return;

    // Lock UI while in flight
    input.disabled = true;
    btn.disabled   = true;

    // Echo user message + clear input
    appendMessage(thread, question, 'user');
    input.value = '';

    // Loading indicator
    const loadingEl = appendMessage(thread, '', 'loading');

    try {
      const res = await fetch('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });

      loadingEl.remove();

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        appendMessage(thread, err.detail || `Error ${res.status} — try again.`, 'ai');
      } else {
        const data = await res.json();
        appendMessage(thread, data.answer, 'ai');
      }
    } catch {
      loadingEl.remove();
      appendMessage(thread, 'Could not reach the server. Make sure Renewly is running.', 'ai');
    } finally {
      input.disabled = false;
      btn.disabled   = false;
      input.focus();
    }
  });
}

function appendMessage(thread, text, type) {
  const el = document.createElement('div');
  el.className = `ask-message ${type}`;

  if (type === 'loading') {
    el.innerHTML = '<span class="loading-dots" aria-label="Thinking">'
      + '<span></span><span></span><span></span>'
      + '</span>';
  } else {
    el.textContent = text;
  }

  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
  return el;
}

/* ----------------------------------------------------------------
   7. ITEMS DASHBOARD — GET /list
   ---------------------------------------------------------------- */
async function loadItemsDashboard() {
  const list      = document.getElementById('items-list');
  const loadingEl = document.getElementById('items-loading');

  if (!list) return;

  try {
    const res = await fetch('/list');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const items = await res.json();

    if (loadingEl) loadingEl.remove();

    // Filter sentinel / empty names (tombstone artefacts)
    const renderable = items.filter(
      item => item.name && item.name.trim() && item.name !== '(Cancelled Item)' && item.item_id
    );

    if (!renderable.length) {
      list.innerHTML = '<p class="items-empty">No items stored yet. Add a subscription or warranty to get started.</p>';
      return;
    }

    list.innerHTML = ''; // clear loading state
    renderable.forEach(item => list.appendChild(buildItemRow(item)));

  } catch (err) {
    if (loadingEl) loadingEl.remove();
    list.innerHTML = '<p class="items-empty">Could not load items — make sure Renewly is running.</p>';
    console.error('[Renewly] Failed to load /list:', err);
  }
}

function buildItemRow(item) {
  const isCancelled = (item.status || '').toLowerCase() === 'cancelled';
  const isUrgent    = checkUrgency(item.key_date);
  const dateLabel   = humanDate(item.key_date);
  const priceLabel  = item.price != null ? `$${parseFloat(item.price).toFixed(2)}` : '—';
  const category    = (item.category || 'other').replace(/_/g, ' ');

  const row = document.createElement('div');
  row.className = `item-row${isCancelled ? ' item-cancelled' : ''}`;
  row.setAttribute('role', 'listitem');

  row.innerHTML = `
    <div>
      <span class="item-name">${esc(item.name)}</span>
      ${item.vendor ? `<span class="item-vendor">${esc(item.vendor)}</span>` : ''}
    </div>
    <span class="item-category">${esc(category)}</span>
    <span class="item-date${isUrgent ? ' urgent' : ''}" title="${esc(item.key_date)}">${dateLabel}</span>
    <span class="item-price">${priceLabel}</span>
    <div class="item-actions" data-item-id="${esc(item.item_id)}">
      <button class="feedback-btn" data-signal="too_early"  title="Remind me earlier">Too early</button>
      <button class="feedback-btn" data-signal="just_right" title="The timing was right">Just right</button>
      <button class="feedback-btn" data-signal="too_late"   title="Remind me later">Too late</button>
    </div>
  `;

  // Wire feedback buttons — POST /feedback
  row.querySelectorAll('.feedback-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const itemId = row.querySelector('.item-actions').dataset.itemId;
      sendFeedback(itemId, btn.dataset.signal, btn, row);
    });
  });

  return row;
}

/* ----------------------------------------------------------------
   8. FEEDBACK — POST /feedback
   ---------------------------------------------------------------- */
async function sendFeedback(itemId, signal, clickedBtn, row) {
  const allBtns = row.querySelectorAll('.feedback-btn');
  allBtns.forEach(b => { b.disabled = true; });

  try {
    const res = await fetch('/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId, signal }),
    });

    if (res.ok || res.status === 204) {
      // Mark the chosen signal as confirmed, re-enable others
      clickedBtn.classList.add('sent');
      clickedBtn.textContent = '✓ ' + clickedBtn.textContent.replace('✓ ', '');
      allBtns.forEach(b => { if (b !== clickedBtn) b.disabled = false; });
    } else {
      allBtns.forEach(b => { b.disabled = false; });
    }
  } catch {
    allBtns.forEach(b => { b.disabled = false; });
  }
}

/* ----------------------------------------------------------------
   9. UTILITY — date formatting & urgency
   ---------------------------------------------------------------- */
function humanDate(keyDate) {
  if (!keyDate) return '—';
  try {
    // Parse as local date (key_date is YYYY-MM-DD, no timezone)
    const [y, m, d] = keyDate.split('-').map(Number);
    const target = new Date(y, m - 1, d);
    const today  = new Date();
    today.setHours(0, 0, 0, 0);

    const diffMs   = target - today;
    const diffDays = Math.round(diffMs / 86_400_000);

    if (diffDays < -365)  return `Expired ${Math.abs(diffDays)} days ago`;
    if (diffDays < -1)    return `Expired ${Math.abs(diffDays)} days ago`;
    if (diffDays === -1)  return 'Expired yesterday';
    if (diffDays === 0)   return 'Expires today';
    if (diffDays === 1)   return 'Expires tomorrow';
    if (diffDays <= 14)   return `Renews in ${diffDays} days`;
    if (diffDays <= 60)   return `Renews in ${diffDays} days`;

    // Longer horizon — show a readable date
    const opts = { month: 'short', day: 'numeric', year: 'numeric' };
    return `Renews ${target.toLocaleDateString('en-US', opts)}`;
  } catch {
    return keyDate;
  }
}

function checkUrgency(keyDate) {
  if (!keyDate) return false;
  try {
    const [y, m, d] = keyDate.split('-').map(Number);
    const target = new Date(y, m - 1, d);
    const today  = new Date();
    today.setHours(0, 0, 0, 0);
    const diffDays = Math.round((target - today) / 86_400_000);
    return diffDays >= 0 && diffDays <= 7;
  } catch {
    return false;
  }
}

/* Minimal HTML escape — prevent XSS in dynamically built rows */
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
