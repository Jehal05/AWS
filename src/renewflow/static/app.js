// RenewFlow dashboard. No build step, no dependencies.
// Every dynamic value goes through the `html` tag, which escapes it. Message text comes from
// customers and models, so it is always treated as untrusted.

/* ------------------------------------------------------------------ helpers */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
class Raw { constructor(s) { this.s = s; } }
const raw = (s) => new Raw(s);
const fmt = (v) => {
  if (v instanceof Raw) return v.s;
  if (Array.isArray(v)) return v.map(fmt).join('');
  if (v == null || v === false) return '';
  return esc(v);
};
const html = (strings, ...vals) => raw(strings.reduce((out, s, i) => out + s + (i < vals.length ? fmt(vals[i]) : ''), ''));

/* ------------------------------------------------------------------ icons */
const ICONS = {
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  chat: '<path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-7l-4.5 3.5V16H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/>',
  bubble: '<path d="M12 4.5a7.5 7.5 0 1 0 3.9 13.9L20 19.5l-1.2-3.9A7.5 7.5 0 0 0 12 4.5z"/>',
  mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="M4 7.5l8 6 8-6"/>',
  sms: '<rect x="3.5" y="5" width="17" height="12" rx="2.5"/><path d="M8 17v3.5L12 17"/><path d="M8 11h.01M12 11h.01M16 11h.01"/>',
  user: '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c.6-3.6 3.4-5.5 7-5.5s6.4 1.9 7 5.5"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  checks: '<path d="M2.5 12.5L7 17l8-8.5"/><path d="M10 15.5l1.5 1.5L21 7.5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  shield: '<path d="M12 3.5l7 2.8v5.4c0 4.3-2.9 7.3-7 8.8-4.1-1.5-7-4.5-7-8.8V6.3l7-2.8z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
  ban: '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"/>',
  moon: '<path d="M20 14.2A8 8 0 0 1 9.8 4 8 8 0 1 0 20 14.2z"/>',
  play: '<path d="M8 5.5v13l10.5-6.5L8 5.5z"/>',
  reset: '<path d="M4.5 12a7.5 7.5 0 0 1 13-5.1L19.5 9"/><path d="M19.5 4.5V9H15"/><path d="M19.5 12a7.5 7.5 0 0 1-13 5.1L4.5 15"/><path d="M4.5 19.5V15H9"/>',
  send: '<path d="M4 11.5L20 4l-5.5 16-3-6.5L4 11.5z"/><path d="M11.5 13.5L20 4"/>',
  back: '<path d="M14.5 6l-6 6 6 6"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
  bolt: '<path d="M13 3.5L5.5 13.5H11l-1 7 7.5-10H12l1-7z"/>',
  radio: '<circle cx="12" cy="12" r="1.8"/><path d="M7.8 7.8a6 6 0 0 0 0 8.4M16.2 7.8a6 6 0 0 1 0 8.4M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/>',
  phone: '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 18h2"/>',
  open: '<path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4"/>',
  dot: '<circle cx="12" cy="12" r="4"/>',
};
const icon = (name, size = 18) => raw(`<svg class="ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`);
const LOGO = raw('<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M5 22L16 10l11 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="5" cy="22" r="3.5" fill="var(--whatsapp)"/><circle cx="16" cy="10" r="3.5" fill="var(--email)"/><circle cx="27" cy="20" r="3.5" fill="var(--sms)"/></svg>');

/* ------------------------------------------------------------------ vocabulary */
const CH = {
  whatsapp: { label: 'WhatsApp', icon: 'bubble' },
  email: { label: 'Email', icon: 'mail' },
  sms: { label: 'SMS', icon: 'sms' },
};
const STATUS = {
  not_contacted: { label: 'Not contacted', tone: 'mute', icon: 'dot' },
  contacted: { label: 'Awaiting reply', tone: 'info', icon: 'clock' },
  in_conversation: { label: 'In conversation', tone: 'info', icon: 'chat' },
  handoff: { label: 'With a person', tone: 'warn', icon: 'user' },
  renewed: { label: 'Renewed', tone: 'good', icon: 'check' },
  opted_out: { label: 'Opted out', tone: 'mute', icon: 'ban' },
};
const GUARD = {
  no_consent: 'No consent on file',
  quiet_hours: 'Quiet hours',
  rate_limit: 'Daily message limit',
  ungrounded_amount: 'Price not from a tool',
  prohibited_claim: 'Prohibited promise',
  too_long: 'Too long for the channel',
  channel_unavailable: 'Channel not enabled',
  unknown_customer: 'Unknown customer',
};
const KIND = { proactive: 'Opening message', quote: 'Quote', clarify: 'Clarifying question', handoff: 'Handoff notice', confirmation: 'Confirmation' };
const TRIGGER = { proactive: 'Started the conversation', inbound: 'Replied to the customer', opt_out: 'Handled an opt-out', opt_in: 'Welcomed the customer back', system: 'Sent a receipt' };
const OUTCOME = { contacted: ['Sent', 'good'], replied: ['Replied', 'good'], handoff: ['Handed over', 'warn'], scheduled: ['Scheduled', 'info'], blocked: ['Blocked', 'crit'], opted_out: ['Opted out', 'mute'], opted_in: ['Opted in', 'good'], awaiting_human: ['Paused', 'mute'], skipped: ['Skipped', 'mute'], error: ['Error', 'crit'], no_action: ['No action', 'mute'] };
const FILTERS = [['all', 'All'], ['not_contacted', 'New'], ['active', 'Active'], ['handoff', 'With a person'], ['renewed', 'Renewed'], ['opted_out', 'Opted out']];
const QUICK = [
  'Premium looks higher, can I split it?',
  'Please email me the details',
  'Ok, send me the payment link',
  'Why has my premium gone up?',
  'My claim was rejected. I want to speak to a person',
  'STOP',
];
const TITLES = {
  overview: ['Overview', 'Renewals due in the next 30 days'],
  conversations: ['Conversations', 'One thread per customer, across every channel'],
  handoffs: ['Handoffs', 'Conversations that need a person'],
  channels: ['Channels', 'Where each customer is most likely to answer'],
};

/* ------------------------------------------------------------------ formatting */
const IST = 'Asia/Kolkata';
const inr = (n) => '₹' + new Intl.NumberFormat('en-IN').format(Math.round(n ?? 0));
const pct = (x, d = 0) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`);
const plural = (n, one, many) => (n === 1 ? one : many);
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : '');
const initials = (name) => name.split(' ').map((p) => p[0]).slice(0, 2).join('');
const timeFmt = new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: IST });
const dayFmt = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: IST });
const dayKeyFmt = new Intl.DateTimeFormat('en-CA', { timeZone: IST });
const dayKey = (d) => dayKeyFmt.format(d);
const clock = (iso) => timeFmt.format(new Date(iso)).replace(/\s/g, ' ');
function dayLabel(iso) {
  const d = new Date(iso);
  if (dayKey(d) === dayKey(new Date())) return 'Today';
  if (dayKey(d) === dayKey(new Date(Date.now() - 864e5))) return 'Yesterday';
  return dayFmt.format(d);
}
const when = (iso) => (dayKey(new Date(iso)) === dayKey(new Date()) ? clock(iso) : `${dayLabel(iso)}, ${clock(iso)}`);
const fmtMs = (ms) => (ms == null ? '—' : ms < 1 ? '<1 ms' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);
const dueLabel = (d) => (d < 0 ? 'Expired' : d === 0 ? 'Today' : d === 1 ? 'Tomorrow' : `${d} days`);
const longDate = (iso) => new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: IST }).format(new Date(iso + 'T00:00:00+05:30'));

const chLabel = (c) => html`<span class="ch ch-${c}">${icon(CH[c].icon, 15)}${CH[c].label}</span>`;
const statusChip = (s) => { const m = STATUS[s] || STATUS.not_contacted; return html`<span class="chip tone-${m.tone}">${icon(m.icon, 14)}${m.label}</span>`; };

/* ------------------------------------------------------------------ state + api */
const S = {
  route: { view: 'overview', id: null },
  meta: null, overview: null, customers: [], detail: null, handoffs: [],
  filter: 'all', q: '', side: 'details', simTab: null, mail: null, checkout: null,
  version: -1, busy: {}, readSent: new Set(), newIds: new Set(), knownIds: null,
  offline: false, intro: true,
};

async function api(path, opts) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = Array.isArray(j.detail) ? j.detail[0].msg : j.detail || msg; } catch (_) { /* keep status text */ }
    throw new Error(msg);
  }
  return res.json();
}
const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body ?? {}) });

async function refresh(force = false) {
  try {
    const { version } = await api('/api/version');
    if (!force && version === S.version && !S.offline) return;
    S.version = version;
    const jobs = [
      api('/api/meta').then((m) => (S.meta = m)),
      api('/api/overview').then((o) => (S.overview = o)),
      api('/api/customers').then((c) => (S.customers = c)),
      api('/api/handoffs').then((h) => (S.handoffs = h)),
    ];
    if (S.route.view === 'conversations' && S.route.id) {
      jobs.push(api(`/api/customers/${S.route.id}`).then((d) => (S.detail = d)).catch(() => (S.detail = null)));
    }
    await Promise.all(jobs);
    S.offline = false;
    ensureSelection();
  } catch (_) {
    S.offline = true;
  }
  paintAll();
}

/* ------------------------------------------------------------------ painting */
function paint(el, tpl) {
  hideTip();
  const keep = {};
  $$('[data-keep]', el).forEach((n) => { keep[n.dataset.keep] = { v: n.value, f: document.activeElement === n, s: n.selectionStart, e: n.selectionEnd }; });
  const scrolls = {};
  $$('[data-scroll]', el).forEach((n) => { scrolls[n.dataset.scroll] = { top: n.scrollTop, bottom: n.scrollHeight - n.scrollTop - n.clientHeight < 48 }; });
  const outer = el.scrollTop;
  el.innerHTML = tpl.s;
  $$('[data-keep]', el).forEach((n) => {
    const k = keep[n.dataset.keep];
    if (!k) return;
    n.value = k.v;
    if (k.f) { n.focus({ preventScroll: true }); try { n.setSelectionRange(k.s, k.e); } catch (_) { /* not a text field */ } }
  });
  $$('[data-scroll]', el).forEach((n) => {
    const s = scrolls[n.dataset.scroll];
    const stick = n.dataset.stick === 'bottom';
    n.scrollTop = !s ? (stick ? n.scrollHeight : 0) : stick && s.bottom ? n.scrollHeight : s.top;
  });
  el.scrollTop = outer;
}

function paintAll() {
  paintRail();
  paintTopbar();
  paintView();
}

function paintRail() {
  const open = S.overview?.kpis.open_handoffs ?? 0;
  const items = [['overview', 'grid', 'Overview'], ['conversations', 'chat', 'Conversations'], ['handoffs', 'user', 'Handoffs'], ['channels', 'radio', 'Channels']];
  const m = S.meta;
  paint($('#rail'), html`
    <a class="brand" href="#/overview" aria-label="RenewFlow home">${LOGO}<span>RenewFlow</span></a>
    ${items.map(([v, i, l]) => html`
      <button class="nav-item" data-action="nav" data-view="${v}" ${S.route.view === v ? raw('aria-current="page"') : ''}>
        ${icon(i, 20)}<span class="lbl">${l}</span>
        ${v === 'handoffs' && open ? html`<span class="badge" aria-label="${open} waiting">${open}</span>` : ''}
      </button>`)}
    ${m ? html`<div class="rail-foot"><b>${m.mode === 'local' ? 'Local mode' : 'AWS mode'}</b><br>Model: ${m.model}<br>Channels: ${m.channels.map((c) => CH[c].label + (m.simulated_channels.includes(c) ? ' (simulated)' : ' (live)')).join(', ')}</div>` : ''}`);
}

function paintTopbar() {
  const [title, sub] = TITLES[S.route.view];
  const quiet = S.meta?.quiet_hours === 'on';
  const dark = isDark();
  paint($('#topbar'), html`
    <div><h1>${title}</h1><p class="sub">${sub}</p></div>
    <div class="spacer"></div>
    <div class="group">
      ${S.offline ? html`<span class="chip tone-crit">${icon('info', 14)}Can't reach the server</span>` : ''}
      <span class="chip tone-mute" tabindex="0" data-tip="Every customer, policy and engagement record here is invented. In local mode nothing leaves this app.">${icon('info', 14)}Synthetic data</span>
      <button class="switch" role="switch" aria-checked="${String(quiet)}" data-action="quiet" data-tip="Proactive messages wait until 08:00 customer time. Turn off to demo at any hour. Replies are never held back."><span class="track"></span>Quiet hours</button>
      <button class="btn btn-quiet icon-btn" data-action="theme" aria-label="Switch to ${dark ? 'light' : 'dark'} theme" data-tip="Switch to ${dark ? 'light' : 'dark'} theme">${icon(dark ? 'sun' : 'moon')}</button>
      <button class="btn btn-quiet" data-action="reset">${icon('reset', 16)}Reset demo</button>
      <button class="btn btn-primary" data-action="cohort" ${S.busy.cohort ? raw('aria-busy="true" disabled') : ''}>${S.busy.cohort ? html`<span class="spin">${icon('reset', 16)}</span>Running` : html`${icon('play', 16)}Run simulation`}</button>
    </div>`);
}

function paintView() {
  const v = S.route.view;
  const tpl = v === 'overview' ? viewOverview() : v === 'conversations' ? viewConversations() : v === 'handoffs' ? viewHandoffs() : viewChannels();
  paint($('#view'), tpl);
  if (v === 'conversations') afterConversationsPaint();
  S.intro = false;
}

const loading = () => html`<div class="page"><div class="empty"><p class="t">Loading</p></div></div>`;

/* ------------------------------------------------------------------ overview */
function viewOverview() {
  const o = S.overview;
  if (!o) return loading();
  const k = o.kpis;
  const total = o.funnel[0].count || 1;
  const none = k.contacted === 0;
  const g = o.guardrails;
  const reasons = Object.entries(g.by_reason).sort((a, b) => b[1] - a[1]);
  return html`
  <div class="page ${S.intro ? 'intro' : ''}">
    <section class="strip" aria-label="Headline numbers">
      <div class="hero">
        <p class="label">Renewal rate</p>
        <p class="figure">${none ? '—' : pct(k.renewal_rate)}</p>
        <p class="note">${none ? 'Nothing has been sent yet.' : html`${k.renewed} of ${k.contacted} contacted ${plural(k.contacted, 'customer has', 'customers have')} renewed.`}</p>
      </div>
      <dl class="stats">
        <div class="stat"><dt>Revenue secured</dt><dd class="value">${inr(k.revenue_secured)}</dd><dd class="note">${k.renewed} renewed ${plural(k.renewed, 'policy', 'policies')}</dd></div>
        <div class="stat"><dt>Handled without a person</dt><dd class="value">${pct(k.handled_without_human)}</dd><dd class="note">${k.open_handoffs} waiting for a person</dd></div>
        <div class="stat"><dt>Median reply time</dt><dd class="value">${fmtMs(k.median_response_ms)}</dd><dd class="note">Assistant processing, ${S.meta?.model ?? ''}</dd></div>
        <div class="stat"><dt>Changed channel mid-chat</dt><dd class="value">${k.cross_channel_threads}</dd><dd class="note">Threads that moved between channels</dd></div>
      </dl>
    </section>

    ${none ? html`<div class="callout">
      <p><b>Nothing has been sent yet.</b> Open Priya Sharma's conversation to follow one renewal from the first message to payment, or run the simulation to fill this dashboard with 20 customers.</p>
      <button class="btn btn-primary" data-action="open-hero">${icon('chat', 16)}Open Priya's conversation</button>
      <button class="btn" data-action="cohort">${icon('play', 16)}Run simulation</button>
    </div>` : ''}

    <div class="cols">
      <section class="section" aria-labelledby="h-funnel">
        <h2 id="h-funnel">From due to renewed</h2>
        <p class="lede">Customers who reached each stage, out of ${o.funnel[0].count} policies due.</p>
        <ol class="funnel">
          ${o.funnel.map((s, i) => html`
            <li tabindex="0" style="--w:${(s.count / total) * 100}%;--i:${i}" data-tip="${s.label}: ${s.count} of ${o.funnel[0].count} (${pct(s.share)})">
              <span class="name">${s.label}</span>
              <span class="bar"><i></i></span>
              <span class="val">${s.count}<small>${pct(s.share)}</small></span>
            </li>`)}
        </ol>
      </section>

      <section class="section" aria-labelledby="h-safe">
        <h2 id="h-safe">What the guardrails did</h2>
        <p class="lede">Every message is checked for consent, quiet hours, length and prices before it leaves.</p>
        <ul class="ruled">
          <li>${icon('shield')}<div><p class="t">Messages blocked</p>
            ${reasons.length ? html`<ul class="reasons">${reasons.map(([r, n]) => html`<li><span>${GUARD[r] || r}</span><span>${n}</span></li>`)}</ul>` : html`<p class="d">Nothing blocked yet.</p>`}</div>
            <span class="n">${g.blocked_total}</span></li>
          <li>${icon('ban')}<div><p class="t">Opt-outs honoured</p><p class="d">Consent is revoked on every channel straight away.</p></div><span class="n">${k.opt_outs}</span></li>
          <li>${icon('user')}<div><p class="t">Waiting for a person</p><p class="d">Claims, complaints and requests for a colleague.</p></div><span class="n">${k.open_handoffs}</span></li>
          <li>${icon('clock')}<div><p class="t">Follow-ups scheduled</p><p class="d">For customers who have not replied yet.</p></div><span class="n">${k.followups_scheduled}</span></li>
        </ul>
      </section>
    </div>

    <div class="cols even">
      <section class="section stack" aria-labelledby="h-chan">
        <div>
          <h2 id="h-chan">How each channel is performing</h2>
          <p class="lede">The campaign so far, and the 90 days of history the channel scores learn from.</p>
          ${channelTable('This campaign', ['Sent', 'Read rate', 'Replies'], o.campaign_channels.map((c) => [c.channel, c.sent, c.read_rate, c.replies]), 'sent')}
        </div>
        ${channelTable('Last 90 days, before this campaign', ['Delivered', 'Read rate', 'Reply rate'], o.engagement_history.map((c) => [c.channel, c.delivered, c.read_rate, c.reply_rate]), 'history')}
      </section>

      <section class="section" aria-labelledby="h-feed">
        <h2 id="h-feed">Live activity</h2>
        <p class="lede">Newest first. Select an item to open the conversation.</p>
        ${o.activity.length ? html`<ul class="feed">${o.activity.map(feedItem)}</ul>` : html`<div class="empty"><p>Activity appears here as soon as the assistant sends or receives a message.</p></div>`}
      </section>
    </div>
  </div>`;
}

function channelTable(caption, heads, rows, kind) {
  return html`<table class="data">
    <caption>${caption}</caption>
    <thead><tr><th scope="col">Channel</th><th scope="col" class="r">${heads[0]}</th><th scope="col">${heads[1]}</th><th scope="col" class="r">${heads[2]}</th></tr></thead>
    <tbody>${rows.map(([c, n, rate, last]) => html`<tr>
      <th scope="row" style="font-weight:550">${chLabel(c)}</th>
      <td class="r">${n}</td>
      <td>${rate == null ? html`<span style="color:var(--ink-3)">No data</span>` : html`<div class="rate" data-tip="${CH[c].label} read rate: ${pct(rate, 1)}"><span class="meter"><i style="--w:${rate * 100}%;--c:var(--${c})"></i></span><b>${pct(rate)}</b></div>`}</td>
      <td class="r">${kind === 'history' ? pct(last) : last}</td>
    </tr>`)}</tbody></table>`;
}

function feedItem(a) {
  const icons = { message_out: 'bolt', message_in: 'chat', renewed: 'check', handoff: 'user', opt_out: 'ban', blocked: 'shield' };
  const via = CH[a.channel]?.label;
  const text = a.kind === 'message_out' ? `Assistant sent on ${via}: ${a.text}` : a.kind === 'message_in' ? `Replied on ${via}: ${a.text}` : a.text;
  return html`<li><button data-action="open-customer" data-id="${a.customer_id}">
    ${icon(icons[a.kind] || 'dot', 18)}
    <span><span class="who">${a.name}</span><br><span class="what">${text}</span></span>
    <time datetime="${a.ts}">${when(a.ts)}</time></button></li>`;
}

/* ------------------------------------------------------------------ conversations */
function ensureSelection() {
  if (S.route.view !== 'conversations' || S.route.id || !S.customers.length) return;
  if (window.matchMedia('(max-width: 760px)').matches) return;
  const id = S.meta?.hero_customer_id ?? S.customers[0].id;
  history.replaceState(null, '', `#/conversations/${id}`);
  S.route = parseHash();
  api(`/api/customers/${id}`).then((d) => { S.detail = d; paintView(); }).catch(() => {});
}

function filteredCustomers() {
  const q = S.q.trim().toLowerCase();
  const hero = S.meta?.hero_customer_id;
  const match = (c) => {
    if (S.filter === 'active' ? !['contacted', 'in_conversation'].includes(c.status) : S.filter !== 'all' && c.status !== S.filter) return false;
    return !q || `${c.name} ${c.product} ${c.asset}`.toLowerCase().includes(q);
  };
  return S.customers.filter(match).sort((a, b) => {
    if (a.id === hero) return -1;
    if (b.id === hero) return 1;
    if (a.last && b.last) return b.last.ts.localeCompare(a.last.ts);
    if (a.last || b.last) return a.last ? -1 : 1;
    return a.days_to_expiry - b.days_to_expiry || a.id - b.id;
  });
}

function filterCount(key) {
  return S.customers.filter((c) => (key === 'all' ? true : key === 'active' ? ['contacted', 'in_conversation'].includes(c.status) : c.status === key)).length;
}

function viewConversations() {
  const list = filteredCustomers();
  const d = S.detail && S.detail.customer.id === S.route.id ? S.detail : null;
  const hero = S.meta?.hero_customer_id;
  return html`
  <div class="conv ${S.route.id ? 'has-selection' : ''} ${S.side === 'play' || S.side === 'activity' ? 'show-side-on-wide' : ''}" id="conv">
    <section class="pane list" aria-label="Customers">
      <div class="pane-head">
        <label class="search">${icon('search', 16)}<input class="field" type="search" placeholder="Search customers" value="${S.q}" data-keep="q" data-input="search" aria-label="Search customers"></label>
        <div class="filters" role="group" aria-label="Filter by status">
          ${FILTERS.map(([k, l]) => html`<button data-action="filter" data-key="${k}" aria-pressed="${String(S.filter === k)}">${l}<span class="count">${filterCount(k)}</span></button>`)}
        </div>
      </div>
      <div class="pane-body" data-scroll="list">
        ${list.length ? html`<ul class="clist">${list.map((c) => html`<li><button class="cust" data-action="open-customer" data-id="${c.id}" ${c.id === S.route.id ? raw('aria-current="true"') : ''}>
          <span class="avatar" aria-hidden="true">${initials(c.name)}</span>
          <span style="min-width:0">
            <span class="row1"><span class="nm">${c.name}</span><span class="due">${dueLabel(c.days_to_expiry)}</span></span>
            <span class="prod" style="display:block">${c.product}</span>
            ${c.last ? html`<span class="last">${icon(CH[c.last.channel].icon, 14)}<span class="txt">${c.last.direction === 'out' ? 'Assistant: ' : ''}${c.last.text}</span></span>` : ''}
            <span class="st">${statusChip(c.status)}${c.id === hero ? html` <span class="chip plain">Demo customer</span>` : ''}</span>
          </span></button></li>`)}</ul>` : html`<p class="list-empty">No customers match. Try a different search or filter.</p>`}
      </div>
    </section>
    <section class="pane thread" aria-label="Conversation">${d ? threadPane(d) : html`<div class="empty center"><p class="t">Select a customer</p><p>Pick someone from the list to see their conversation across every channel.</p></div>`}</section>
    <aside class="pane side" aria-label="Customer details">${d ? sidePane(d) : ''}</aside>
  </div>`;
}

function afterConversationsPaint() {
  const conv = $('#conv');
  if (conv) conv.classList.toggle('show-side', S.showSide === true);
  const d = S.detail;
  if (!d || S.side !== 'play') return;
  // The customer "opens" their chat: record reads for messages they can see.
  const tab = currentSimTab();
  if (tab === 'email') return;
  d.messages.filter((m) => m.direction === 'out' && m.channel === tab && !m.read && !S.readSent.has(m.id)).forEach((m) => {
    S.readSent.add(m.id);
    post('/api/simulator/read', { message_id: m.id }).catch(() => {});
  });
}

function threadPane(d) {
  const c = d.customer;
  const p = d.policy;
  const msgs = d.messages;
  const first = c.name.split(' ')[0];
  const banner = d.status === 'handoff' ? html`<div class="banner">${icon('user')}<p><b>A person owns this conversation.</b> The assistant is paused. ${d.handoff?.summary ?? ''} <a href="#/handoffs">Open handoffs</a></p></div>`
    : d.status === 'opted_out' ? html`<div class="banner">${icon('ban')}<p><b>${first} opted out.</b> Consent is revoked on every channel and no further messages will be sent.</p></div>`
    : d.status === 'renewed' ? html`<div class="banner">${icon('check')}<p><b>Renewed</b> on the ${p.renewed_plan} plan for ${inr(p.renewed_amount)}.</p></div>` : '';
  const rec = d.channels.recommended;
  return html`
    <header class="thread-head">
      <button class="btn btn-quiet icon-btn back" data-action="back" aria-label="Back to customers">${icon('back')}</button>
      <div class="who">
        <h2>${c.name} ${statusChip(d.status)}</h2>
        <p class="meta">${p.product}, ${p.asset}</p>
      </div>
      ${d.status === 'not_contacted' ? html`<button class="btn btn-primary" data-action="start" data-policy="${p.id}" ${S.busy.start ? raw('aria-busy="true" disabled') : ''}>${icon('bolt', 16)}Start renewal</button>` : ''}
      <button class="btn" data-action="side" data-tab="play">${icon('phone', 16)}Play as ${first}</button>
    </header>
    ${banner}
    <div class="pane-body" data-scroll="thread" data-stick="bottom">
      ${msgs.length ? html`<div class="messages">${threadBody(d)}</div>` : html`<div class="empty center">
        <p class="t">No conversation yet</p>
        <p>${rec ? html`The assistant will start on <b>${CH[rec].label}</b> (${d.channels.confidence} confidence) because that is where ${first} has engaged most. ` : ''}It checks consent and quiet hours before anything is sent.</p>
        ${d.status === 'not_contacted' ? html`<button class="btn btn-primary" data-action="start" data-policy="${p.id}">${icon('bolt', 16)}Start renewal</button>` : ''}</div>`}
    </div>`;
}

function threadBody(d) {
  const segs = [];
  d.messages.forEach((m) => {
    const last = segs[segs.length - 1];
    if (last && last.channel === m.channel) last.items.push(m); else segs.push({ channel: m.channel, items: [m] });
  });
  let prevDay = null;
  return segs.map((seg, i) => html`
    <div class="seg ch-${seg.channel}">
      <span class="marker"><span class="dotc"></span>${CH[seg.channel].icon && icon(CH[seg.channel].icon, 15)}${i === 0 ? 'Started on' : 'Continued on'} ${CH[seg.channel].label}</span>
      ${seg.items.map((m) => {
        const key = dayKey(new Date(m.created_at));
        const sep = key !== prevDay ? html`<div class="day">${dayLabel(m.created_at)}</div>` : '';
        prevDay = key;
        return html`${sep}${messageView(m, d)}`;
      })}
    </div>`);
}

const PAY_RE = /https?:\/\/[^\s]+\/pay\/([\w-]+)/g;
function bodyHtml(text, linkFn) {
  let out = ''; let last = 0;
  for (const m of text.matchAll(PAY_RE)) { out += esc(text.slice(last, m.index)) + linkFn(m[1]).s; last = m.index + m[0].length; }
  return raw(out + esc(text.slice(last)));
}

function messageView(m, d) {
  const out = m.direction === 'out';
  const who = out ? 'Assistant' : d.customer.name.split(' ')[0];
  const isNew = S.newIds.has(m.id);
  const link = () => html`<span class="linkchip">${icon('open', 14)}Payment link</span>`;
  const body = bodyHtml(m.body, link);
  return html`<article class="msg ${out ? 'out' : 'in'} ${isNew ? 'is-new' : ''}">
    ${m.channel === 'email' && m.subject ? html`<div class="letter"><div class="subj">${m.subject}</div><div class="body">${body}</div></div>` : html`<div class="bubble">${body}</div>`}
    <div class="byline"><b>${who}</b><time datetime="${m.created_at}">${clock(m.created_at)}</time>
      ${out && KIND[m.kind] ? html`<span class="kind">${KIND[m.kind]}</span>` : ''}
      ${out ? html`<span class="receipt ${m.read ? 'is-read' : ''}">${icon(m.read ? 'checks' : 'check', 15)}${m.read ? 'Read' : 'Delivered'}</span>` : ''}
      ${out && m.clicked ? html`<span class="receipt is-read">${icon('open', 14)}Link opened</span>` : ''}
    </div></article>`;
}

function sidePane(d) {
  const tabs = [['details', 'Details'], ['activity', 'Activity'], ['play', 'Play as customer']];
  return html`
    <button class="btn btn-quiet side-back" data-action="side-close">${icon('back', 16)}Back to conversation</button>
    <div class="side-tabs" role="tablist">${tabs.map(([k, l]) => html`<button role="tab" aria-selected="${String(S.side === k)}" data-action="side" data-tab="${k}">${l}</button>`)}</div>
    <div class="pane-body" data-scroll="side-${S.side}"><div class="side-body">
      ${S.side === 'details' ? detailsTab(d) : S.side === 'activity' ? activityTab(d) : playTab(d)}
    </div></div>`;
}

function detailsTab(d) {
  const p = d.policy; const c = d.customer; const ch = d.channels;
  const maxReason = Math.max(...p.increase_reasons.map((r) => r.amount), 1);
  const top = ch.ranking.find((r) => r.channel === ch.recommended);
  const first = c.name.split(' ')[0];
  return html`
    <section>
      <h3>Policy</h3>
      <div class="premium"><span class="big">${inr(p.premium_new)}</span><span class="delta">${p.delta ? html`up ${inr(p.delta)} from ${inr(p.premium_prev)} last year` : 'unchanged from last year'}</span></div>
      <dl class="kv">
        <div><dt>Policy number</dt><dd>${p.policy_number}</dd></div>
        <div><dt>Expires</dt><dd>${longDate(p.expiry_date)}, ${p.days_to_expiry < 0 ? 'expired' : `in ${p.days_to_expiry} ${plural(p.days_to_expiry, 'day', 'days')}`}</dd></div>
        <div><dt>Cover</dt><dd>${inr(p.sum_insured)}</dd></div>
        ${p.ncb_percent ? html`<div><dt>No-claim bonus</dt><dd>${p.ncb_percent}%</dd></div>` : ''}
      </dl>
      ${p.increase_reasons.length && p.delta ? html`<ul class="why" aria-label="Why the premium changed">${p.increase_reasons.map((r) => html`<li><span>${r.label}</span><b>+${inr(r.amount)}</b><span class="m"><i style="--w:${(r.amount / maxReason) * 100}%"></i></span></li>`)}</ul>` : ''}
    </section>
    <section>
      <h3>Best channel</h3>
      ${ch.recommended ? html`<div class="pick">${icon('radio')}<p><b>${CH[ch.recommended].label}</b>, ${ch.confidence} confidence. ${top ? top.reasons.slice(0, 3).join('. ') + '.' : ''}${ch.quiet_hours.active ? html` It is ${ch.quiet_hours.local_time} for ${first}, so a new conversation waits until ${ch.quiet_hours.window.split('–')[0]}.` : ''}</p></div>` : html`<div class="pick">${icon('ban')}<p>${first} has not given consent on any enabled channel, so the assistant cannot start a conversation.</p></div>`}
      <div class="scores">${ch.ranking.map((r) => html`<div class="score ${r.eligible ? '' : 'off'}" tabindex="0" data-tip="${r.reasons.join('. ')}">
        ${chLabel(r.channel)}<span class="meter"><i style="--w:${r.score * 100}%;--c:var(--${r.channel})"></i></span><b>${Math.round(r.score * 100)}</b></div>`)}</div>
      <div class="consents">${ch.ranking.map((r) => html`<span class="chip tone-${r.consent ? 'good' : 'mute'}">${icon(r.consent ? 'check' : 'ban', 14)}${CH[r.channel].label} ${r.consent ? 'opted in' : 'no consent'}${r.enabled ? '' : ' (off)'}</span>`)}</div>
    </section>
    <section>
      <h3>Contact</h3>
      <dl class="kv"><div><dt>Email</dt><dd>${c.email}</dd></div><div><dt>Phone</dt><dd>${c.phone}</dd></div><div><dt>Language</dt><dd>${c.language.toUpperCase()}</dd></div><div><dt>Time zone</dt><dd>${c.timezone}</dd></div><div><dt>Behaviour profile</dt><dd>${c.segment.replace(/_/g, ' ')}</dd></div></dl>
    </section>
    ${d.followups.length ? html`<section><h3>Follow-ups</h3><ul class="reasons">${d.followups.map((f) => html`<li><span>${f.note}</span><span>${when(f.due_at)}</span></li>`)}</ul></section>` : ''}`;
}

const TOOLS = {
  next_best_channel: ['Picked the best channel', 'radio', (r) => (r.recommended ? `${CH[r.recommended].label}, ${r.confidence} confidence${r.quiet_hours?.active ? ', quiet hours active' : ''}` : 'No channel with consent')],
  lookup_policy: ['Looked up the policy', 'search', (r) => (r.ok ? `Premium ${inr(r.premium_new)}, expires in ${r.days_to_expiry} days` : r.error)],
  generate_quote: ['Priced a payment plan', 'bolt', (r) => (r.ok ? `${cap(r.plan)}: ${r.installments === 1 ? inr(r.total) : `${r.installments} × ${inr(r.per_installment)}`}, total ${inr(r.total)}` : r.error)],
  send_message: [null, 'send', (r) => (r.ok ? 'Delivered' : `Blocked: ${GUARD[r.blocked_by] || r.error}`)],
  schedule_followup: ['Scheduled a follow-up', 'clock', (r) => (r.ok ? `Due ${when(r.due_at)}` : r.error)],
  handoff_to_human: ['Handed over to a person', 'user', (r) => (r.ok ? 'Queued with a summary' : r.error)],
};

function activityTab(d) {
  if (!d.trace.length) return html`<div class="empty"><p class="t">No activity yet</p><p>Every step the assistant takes is recorded here: which tools it called, what they returned, and what a guardrail stopped.</p></div>`;
  return html`<section><h3>What the assistant did</h3>${[...d.trace].reverse().map((r) => {
    const [oLabel, tone] = OUTCOME[r.outcome] || [r.outcome, 'mute'];
    return html`<div class="run">
      <header><span class="t">${TRIGGER[r.trigger] || r.trigger}</span><span class="chip tone-${tone}">${oLabel}</span><span class="ms">${fmtMs(r.duration_ms)}, ${when(r.started_at)}</span></header>
      ${r.tool_calls.length ? html`<div class="calls">${r.tool_calls.map((c) => {
        const t = TOOLS[c.name] || [c.name, 'dot', () => '']; const bad = !c.ok;
        const label = t[0] || `Sent ${CH[c.args.channel]?.label ?? ''} message`;
        return html`<div class="call ${bad ? 'bad' : ''}">${icon(bad ? 'shield' : t[1])}<div><p class="t">${label}</p><p class="s">${t[2](c.result)}</p></div>
          <details><summary>Raw call</summary><pre>${JSON.stringify({ arguments: c.args, result: c.result }, null, 2)}</pre></details></div>`;
      })}</div>` : ''}
      ${r.summary ? html`<p class="sum">${r.summary}</p>` : ''}</div>`;
  })}</section>`;
}

/* ---- customer device simulator */
function currentSimTab() {
  const chans = S.meta?.channels || [];
  if (chans.includes(S.simTab)) return S.simTab;
  // Default to the channel the conversation is currently on, so a reply lands where the customer is.
  const last = S.detail?.messages.at(-1)?.channel;
  return chans.includes(last) ? last : chans[0];
}

function playTab(d) {
  const chans = S.meta.channels;
  const tab = currentSimTab();
  const first = d.customer.name.split(' ')[0];
  return html`
    <section>
      <h3>Play as ${first}</h3>
      <p style="color:var(--ink-3);font-size:13.5px;margin:-4px 0 14px">This is ${first}'s side of the conversation. Messages you send here go through the real assistant, guardrails and event log.</p>
      <div class="device-tabs" role="tablist">${chans.map((c) => html`<button role="tab" aria-selected="${String(tab === c)}" data-action="simtab" data-tab="${c}"><span class="ch ch-${c}" style="color:inherit">${icon(CH[c].icon, 15)}</span>${CH[c].label}</button>`)}</div>
      ${tab === 'email' ? emailDevice(d, first) : chatDevice(d, tab, first)}
    </section>`;
}

const quickButtons = () => html`<div class="quick">${QUICK.map((q) => html`<button type="button" data-action="quick" data-text="${q}">${q}</button>`)}</div>`;

function chatDevice(d, tab, first) {
  const msgs = d.messages.filter((m) => m.channel === tab);
  const link = (token) => html`<button class="paybtn" data-action="checkout" data-token="${token}">Renew securely</button>`;
  return html`<div class="device">
    <header><span class="avatar" aria-hidden="true">RF</span><div><b>Renewals desk</b><small>Automated assistant, ${CH[tab].label}</small></div></header>
    <div class="screen" data-scroll="screen-${tab}" data-stick="bottom">
      <span class="note">${msgs.length ? `${CH[tab].label} conversation with ${first}` : `Nothing on ${CH[tab].label} yet`}</span>
      ${msgs.map((m) => html`<div class="dm ${m.direction === 'in' ? 'me' : ''} ${S.newIds.has(m.id) ? 'is-new' : ''}">${bodyHtml(m.body, link)}<time>${clock(m.created_at)}</time></div>`)}
    </div>
    <div class="device-foot">
      ${quickButtons()}
      <form class="composer" data-form="chat" data-channel="${tab}"><input data-keep="chat-${tab}" name="text" placeholder="Message as ${first}" autocomplete="off" aria-label="Message as ${first}" maxlength="2000"><button class="btn btn-primary icon-btn" aria-label="Send" style="border-radius:50%">${icon('send', 17)}</button></form>
    </div>
    ${S.checkout ? checkoutSheet(d) : ''}
  </div>`;
}

function emailDevice(d, first) {
  const mails = d.messages.filter((m) => m.channel === 'email');
  const open = S.mail ? mails.find((m) => m.id === S.mail) : null;
  const link = (token) => html`<button class="paybtn" data-action="checkout" data-token="${token}">Renew securely</button>`;
  return html`<div class="device">
    <header>${open ? html`<button class="btn btn-quiet icon-btn" data-action="mail-back" aria-label="Back to inbox">${icon('back')}</button>` : ''}<div><b>${open ? 'Message' : 'Inbox'}</b><small>${esc(first)}'s email</small></div></header>
    <div class="screen" style="padding:0" data-scroll="screen-email">
      ${open ? html`<div class="mail-open"><h4>${open.direction === 'out' ? open.subject || 'Message from Renewals desk' : 'You replied'}</h4>
        <p style="color:var(--ink-3);font-size:13px">${open.direction === 'out' ? 'From Renewals desk' : `From ${esc(first)}`}, ${when(open.created_at)}</p>
        <div class="body">${bodyHtml(open.body, link)}</div></div>`
      : mails.length ? html`<ul class="inbox">${[...mails].reverse().map((m) => html`<li><button data-action="open-mail" data-id="${m.id}"><span class="s">${m.direction === 'out' && !m.read ? html`<span class="unread" aria-label="Unread"></span>` : ''}${m.direction === 'out' ? m.subject || 'Message from Renewals desk' : 'Re: your reply'}</span><span class="p">${m.body.replace(/\s+/g, ' ')}</span></button></li>`)}</ul>`
      : html`<div class="empty center" style="padding:40px 20px"><p class="t">Inbox is empty</p><p>Nothing has been emailed to ${esc(first)} yet.</p></div>`}
    </div>
    <div class="device-foot">
      ${quickButtons()}
      <form class="composer stacked" data-form="chat" data-channel="email"><textarea data-keep="chat-email" name="text" placeholder="Reply by email as ${esc(first)}" aria-label="Reply by email" maxlength="2000"></textarea><button class="btn btn-primary">${icon('send', 16)}Send reply</button></form>
    </div>
    ${S.checkout ? checkoutSheet(d) : ''}
  </div>`;
}

function checkoutSheet(d) {
  const q = d.quotes.find((x) => x.token === S.checkout);
  if (!q) return '';
  const amount = q.installments === 1 ? inr(q.total) : `${q.installments} × ${inr(q.per_installment)}`;
  return html`<div class="checkout" role="dialog" aria-label="Demo checkout"><h4>Renew your policy</h4>
    <p class="amt">${amount}</p><p>${cap(q.plan)} plan, total ${inr(q.total)}</p>
    <button class="btn btn-primary" data-action="pay" data-token="${q.token}" ${S.busy.pay ? raw('disabled aria-busy="true"') : ''}>Pay now (demo)</button>
    <button class="btn btn-quiet" data-action="checkout-cancel">Cancel</button><small>Demonstration only. No real payment is taken.</small></div>`;
}

/* ------------------------------------------------------------------ handoffs */
function viewHandoffs() {
  const open = S.handoffs.filter((h) => h.status === 'open');
  const done = S.handoffs.filter((h) => h.status !== 'open');
  const card = (h) => html`<article class="hcard ${h.status === 'open' ? '' : 'resolved'}">
    <header><h3>${h.customer_name}</h3>${h.status === 'open' ? html`<span class="chip tone-warn">${icon('user', 14)}Waiting for a person</span>` : html`<span class="chip tone-good">${icon('check', 14)}Resolved</span>`}<time class="num" style="color:var(--ink-3);font-size:13px" datetime="${h.created_at}">${when(h.created_at)}</time></header>
    <p class="reason">${h.reason}</p>
    <p class="summary">${h.summary}</p>
    ${h.status === 'open' ? html`<div class="row"><div class="grow"><label for="note-${h.id}">Resolution note</label><input id="note-${h.id}" class="field plain" data-keep="note-${h.id}" placeholder="What did you do for the customer?" maxlength="500"></div>
      <button class="btn btn-primary" data-action="resolve" data-id="${h.id}">${icon('check', 16)}Mark resolved</button>
      <button class="btn" data-action="open-customer" data-id="${h.customer_id}">Open conversation</button></div>`
      : html`<p style="color:var(--ink-3);font-size:13.5px">${h.resolution_note ? `Note: ${h.resolution_note}` : 'Resolved without a note.'}</p>`}
  </article>`;
  return html`<div class="page" style="max-width:920px">
    <section class="section"><h2>Waiting for a person</h2><p class="lede">The assistant stops replying on a thread the moment it is handed over, so a colleague can pick it up with the full context.</p>
      ${open.length ? html`<div class="cards">${open.map(card)}</div>` : html`<div class="empty"><p class="t">Nothing is waiting</p><p>Claims, complaints, disputes and requests for a colleague appear here with a summary. Try replying to Priya with "My claim was rejected" from the customer's phone.</p></div>`}</section>
    ${done.length ? html`<section class="section"><h2>Resolved</h2><p class="lede">Kept for the audit trail.</p><div class="cards">${done.map(card)}</div></section>` : ''}
  </div>`;
}

/* ------------------------------------------------------------------ channels */
function viewChannels() {
  const rows = S.customers;
  if (!rows.length || !S.overview) return loading();
  const enabled = S.meta.channels;
  const counts = Object.fromEntries(enabled.map((c) => [c, rows.filter((r) => r.best_channel === c).length]));
  const none = rows.filter((r) => !r.best_channel).length;
  const total = rows.length;
  const hist = S.overview.engagement_history;
  const conf = { high: 'High', medium: 'Medium', low: 'Low', none: '—' };
  return html`<div class="page">
    <div class="cols even">
      <section class="section">
        <h2>Best channel across customers</h2>
        <p class="lede">Each customer is placed on the channel they are most likely to answer, using their last 90 days of engagement and what they have consented to.</p>
        <div class="mixbar" role="img" aria-label="${enabled.map((c) => `${CH[c].label} ${counts[c]}`).join(', ')}">${enabled.filter((c) => counts[c]).map((c) => html`<span style="width:${(counts[c] / total) * 100}%;--c:var(--${c})" data-tip="${CH[c].label}: ${counts[c]} of ${total} customers"></span>`)}</div>
        <div class="legend">${enabled.map((c) => html`<span><i class="sw sw-${c}"></i>${CH[c].label} ${counts[c]}</span>`)}${none ? html`<span><i class="sw" style="background:var(--slate)"></i>No consented channel ${none}</span>` : ''}</div>
      </section>
      <section class="section">
        <h2>How the score works</h2>
        <p class="lede">A transparent score, not a black box. Select a channel on any customer to see its reasons.</p>
        <ul class="how">
          <li>${icon('clock')}<p><b>Recent behaviour counts more.</b> Engagement loses half its weight every 30 days.</p></li>
          <li>${icon('shield')}<p><b>Small samples are cautious.</b> Rates are pulled towards a neutral prior, so one lucky read does not look like a habit.</p></li>
          <li>${icon('ban')}<p><b>Consent comes first.</b> A channel without consent is never recommended, however well it scores.</p></li>
        </ul>
      </section>
    </div>
    <section class="section">
      <h2>What the scores learn from</h2>
      <p class="lede">Engagement across all customers in the 90 days before this campaign.</p>
      ${channelTable('Engagement history', ['Delivered', 'Read rate', 'Reply rate'], hist.map((c) => [c.channel, c.delivered, c.read_rate, c.reply_rate]), 'history')}
    </section>
    <section class="section">
      <h2>Every customer</h2>
      <p class="lede">Select a row to open the conversation.</p>
      <div class="tbl-scroll" tabindex="0" aria-label="Customers and their best channel"><table class="data"><thead><tr><th scope="col">Customer</th><th scope="col">Policy</th><th scope="col">Best channel</th><th scope="col">Confidence</th><th scope="col" class="r">Expires in</th></tr></thead>
        <tbody>${rows.map((r) => html`<tr data-action="open-customer" data-id="${r.id}"><th scope="row" style="font-weight:600;text-align:left">${r.name}</th><td>${r.product}</td><td>${r.best_channel ? chLabel(r.best_channel) : html`<span style="color:var(--ink-3)">None</span>`}</td><td>${conf[r.confidence]}</td><td class="r">${dueLabel(r.days_to_expiry)}</td></tr>`)}</tbody></table></div>
    </section>
  </div>`;
}

/* ------------------------------------------------------------------ interaction */
const isDark = () => (document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches);

function toast(message, tone = '') {
  const el = document.createElement('div');
  el.className = `toast ${tone}`;
  el.textContent = message;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), 3200);
}

function confirmDialog({ title, body, confirm }) {
  return new Promise((resolve) => {
    const dlg = $('#dialog');
    dlg.innerHTML = html`<form method="dialog"><h2>${title}</h2><p>${body}</p><div class="actions"><button class="btn" value="cancel">Cancel</button><button class="btn btn-primary" value="ok" autofocus>${confirm}</button></div></form>`.s;
    dlg.addEventListener('close', () => resolve(dlg.returnValue === 'ok'), { once: true });
    dlg.showModal();
  });
}

const tip = () => $('#tip');
function showTip(el) {
  const text = el.dataset.tip;
  if (!text) return;
  const t = tip();
  t.textContent = text;
  t.hidden = false;
  const r = el.getBoundingClientRect();
  const w = t.offsetWidth; const h = t.offsetHeight;
  let x = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
  let y = r.bottom + 8;
  if (y + h > window.innerHeight - 8) y = r.top - h - 8;
  t.style.left = `${x}px`;
  t.style.top = `${Math.max(8, y)}px`;
}
function hideTip() { const t = tip(); if (t) t.hidden = true; }

const actions = {
  nav: (el) => { location.hash = `#/${el.dataset.view}`; },
  'open-customer': (el) => { S.mail = null; S.checkout = null; S.showSide = false; location.hash = `#/conversations/${el.dataset.id}`; },
  'open-hero': () => { location.hash = `#/conversations/${S.meta?.hero_customer_id ?? 1}`; },
  back: () => { S.showSide = false; history.pushState(null, '', '#/conversations'); S.route = parseHash(); S.detail = null; paintAll(); },
  filter: (el) => { S.filter = el.dataset.key; paintView(); },
  side: (el) => { S.side = el.dataset.tab; S.showSide = true; S.mail = null; S.checkout = null; paintView(); },
  'side-close': () => { S.showSide = false; paintView(); },
  simtab: (el) => { S.simTab = el.dataset.tab; S.mail = null; S.checkout = null; paintView(); },
  quick: (el) => sendCustomer(el.dataset.text, currentSimTab()),
  'open-mail': (el) => {
    S.mail = Number(el.dataset.id);
    const m = S.detail?.messages.find((x) => x.id === S.mail);
    if (m && m.direction === 'out' && !m.read && !S.readSent.has(m.id)) { S.readSent.add(m.id); post('/api/simulator/read', { message_id: m.id }).catch(() => {}); }
    paintView();
  },
  'mail-back': () => { S.mail = null; paintView(); },
  checkout: (el) => { S.checkout = el.dataset.token; paintView(); },
  'checkout-cancel': () => { S.checkout = null; paintView(); },
  theme: () => {
    const next = isDark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('renewflow-theme', next); } catch (_) { /* private mode */ }
    paintTopbar();
  },
  quiet: async () => {
    const next = S.meta.quiet_hours === 'on' ? 'off' : 'on';
    S.meta = await post('/api/settings', { quiet_hours: next });
    toast(next === 'on' ? 'Quiet hours on: new conversations wait until 08:00' : 'Quiet hours off: the assistant can start conversations at any hour');
    paintTopbar();
  },
  start: async (el) => {
    S.busy.start = true; paintView();
    try { const r = await post(`/api/renewals/${el.dataset.policy}/start`); toast(r.outcome === 'scheduled' ? 'Quiet hours are on, so the first message is scheduled for later' : r.outcome === 'contacted' ? 'Renewal message sent' : `Outcome: ${r.outcome}`); }
    catch (e) { toast(e.message, 'bad'); }
    S.busy.start = false; await refresh(true);
  },
  pay: async (el) => {
    S.busy.pay = true; paintView();
    try { await post('/api/simulator/pay', { token: el.dataset.token }); S.checkout = null; toast('Payment received. The policy is renewed.'); }
    catch (e) { toast(e.message, 'bad'); }
    S.busy.pay = false; await refresh(true);
  },
  resolve: async (el) => {
    const note = $(`[data-keep="note-${el.dataset.id}"]`)?.value ?? '';
    try { await post(`/api/handoffs/${el.dataset.id}/resolve`, { note }); toast('Marked as resolved. The assistant can reply again.'); }
    catch (e) { toast(e.message, 'bad'); }
    await refresh(true);
  },
  cohort: async () => {
    if (S.busy.cohort) return;
    S.busy.cohort = true; paintTopbar();
    try {
      const r = await post('/api/simulator/cohort', { count: 20 });
      toast(r.customers ? `Simulated ${r.customers} customers through the real assistant` : 'Everyone has already been contacted. Reset the demo to run again.');
    } catch (e) { toast(e.message, 'bad'); }
    S.busy.cohort = false; await refresh(true);
  },
  reset: async () => {
    if (!(await confirmDialog({ title: 'Reset the demo?', body: 'This clears every conversation and re-creates the 40 synthetic customers.', confirm: 'Reset demo' }))) return;
    try { await post('/api/reset'); S.readSent.clear(); S.knownIds = null; S.mail = null; S.checkout = null; S.detail = null; S.intro = true; toast('Demo reset'); }
    catch (e) { toast(e.message, 'bad'); }
    await refresh(true);
  },
};

async function sendCustomer(text, channel) {
  const d = S.detail;
  if (!d || !text.trim()) return;
  try {
    const r = await post('/api/simulator/reply', { customer_id: d.customer.id, channel, text: text.trim() });
    if (r.outcome === 'awaiting_human') toast('A person owns this conversation, so the assistant stays quiet.');
    else if (r.outcome === 'opted_out') toast('Unsubscribed. No further messages will be sent.');
    else if (r.outcome === 'handoff') toast('Handed over to a person.');
  } catch (e) { toast(e.message, 'bad'); }
  const box = $(`[data-keep="chat-${channel}"]`);
  if (box) box.value = '';
  await refresh(true);
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el || el.disabled) return;
  const fn = actions[el.dataset.action];
  if (fn) { e.preventDefault(); fn(el, e); }
});
document.addEventListener('keydown', (e) => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-action]')) { e.preventDefault(); actions[e.target.dataset.action](e.target); }
});
document.addEventListener('submit', (e) => {
  const form = e.target.closest('[data-form="chat"]');
  if (!form) return;
  e.preventDefault();
  sendCustomer(new FormData(form).get('text') || '', form.dataset.channel);
});
document.addEventListener('input', (e) => {
  if (e.target.dataset.input === 'search') { S.q = e.target.value; paintView(); }
});
document.addEventListener('pointerover', (e) => { const t = e.target.closest?.('[data-tip]'); if (t) showTip(t); });
document.addEventListener('pointerout', (e) => { if (e.target.closest?.('[data-tip]')) hideTip(); });
document.addEventListener('focusin', (e) => { const t = e.target.closest?.('[data-tip]'); if (t) showTip(t); });
document.addEventListener('focusout', hideTip);
document.addEventListener('scroll', hideTip, true);

/* ------------------------------------------------------------------ routing + boot */
function parseHash() {
  const [view = 'overview', id] = location.hash.replace(/^#\/?/, '').split('/');
  const known = ['overview', 'conversations', 'handoffs', 'channels'];
  return { view: known.includes(view) ? view : 'overview', id: id ? Number(id) || null : null };
}
window.addEventListener('hashchange', () => {
  const prev = S.route;
  S.route = parseHash();
  if (prev.id !== S.route.id) { S.detail = null; S.mail = null; S.checkout = null; S.simTab = null; }
  refresh(true);
});

// Track which messages are new so they can ease in once, without re-animating on every poll.
function trackNewMessages() {
  const ids = new Set((S.detail?.messages || []).map((m) => m.id));
  if (S.knownIds && S.detail && S.knownIds.cust === S.detail.customer.id) {
    S.newIds = new Set([...ids].filter((id) => !S.knownIds.ids.has(id)));
  } else S.newIds = new Set();
  S.knownIds = S.detail ? { cust: S.detail.customer.id, ids } : null;
}
const _paintView = paintView;
// eslint-disable-next-line no-func-assign
paintView = function paintViewTracked() { trackNewMessages(); _paintView(); };

S.route = parseHash();
refresh(true);
setInterval(() => { if (!document.hidden) refresh(); }, 1500);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(true); });
