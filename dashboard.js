/* ===== UNbound Fellow Dashboard logic ===== */
(function () {
  'use strict';

  /* ---------- View switching ---------- */
  window.showView = function (name) {
    document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
    document.querySelectorAll('.sb-nav .nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === name));
    const sb = document.getElementById('sidebar');
    if (sb) sb.classList.remove('open');
    var main = document.querySelector('.main');
    if (main) main.scrollTop = 0;
    window.scrollTo(0, 0);
    if (name === 'overview') animateProgress();
    if (name === 'meetings') buildMeetingGrids();
    if (location.hash.slice(1) !== name) history.replaceState(null, '', '#' + name);
  };

  /* ---------- Overview: phase track + progress ---------- */
  var PHASES = [
    { nm: 'Orbit of Ideas', ph: 'Empathize', state: 'done' },
    { nm: 'Launch Sequence', ph: 'Ideate', state: 'current' },
    { nm: 'Mission Build', ph: 'Prototype', state: '' },
    { nm: 'Trajectory', ph: 'Test', state: '' },
    { nm: 'Touchdown', ph: 'Impact', state: '' }
  ];
  function renderPhases() {
    var t = document.getElementById('phaseTrack');
    if (!t) return;
    t.innerHTML = PHASES.map(function (p) {
      return '<div class="phase-step ' + p.state + '"><div class="bar"></div><div class="nm">' + p.nm + '</div><div class="ph">' + p.ph + '</div></div>';
    }).join('');
  }
  function animateProgress() {
    var el = document.getElementById('ovProgress');
    if (!el) return;
    el.style.width = '0';
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { el.style.width = el.dataset.pct + '%'; });
    });
  }

  /* ---------- Tasks ---------- */
  var TASK_KEY = 'unbound_dash_tasks_v1';
  var ICONS = {
    health: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    edu: '<path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
    deck: '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
    survey: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    budget: '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    cal: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>'
  };
  var SEED = [
    { id: 't1', scope: 'team', src: 'unbound', icon: 'survey', color: '#00B4D8', title: 'Submit Community Needs Assessment', desc: 'Upload your completed empathy-interview synthesis to the cohort folder.', status: 'pending' },
    { id: 't2', scope: 'team', src: 'unbound', icon: 'deck', color: '#7c5cff', title: 'Prototype Pitch Deck (v1)', desc: 'Draft the 6-slide prototype pitch using the UNbound template.', status: 'pending' },
    { id: 't3', scope: 'team', src: 'unbound', icon: 'budget', color: '#1f9d57', title: 'Draft Project Budget', desc: 'Outline projected costs and funding sources for the build phase.', status: 'complete' },
    { id: 't4', scope: 'you', src: 'unbound', icon: 'edu', color: '#e0772b', title: 'Complete Design-Thinking Module 3', desc: 'Watch the Ideation lesson and submit your reflection.', status: 'pending' },
    { id: 't5', scope: 'you', src: 'unbound', icon: 'health', color: '#C5192D', title: 'Map Your SDG Targets', desc: 'Select the specific UN targets your project will measure against.', status: 'pending' },
    { id: 't6', scope: 'you', src: 'unbound', icon: 'cal', color: '#0A97D9', title: 'Book Mentor 1:1', desc: 'Schedule your phase check-in with mentor Diego N.', status: 'complete' }
  ];
  var tasks = load();
  function load() {
    try {
      var raw = localStorage.getItem(TASK_KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) {}
    return JSON.parse(JSON.stringify(SEED));
  }
  function save() { try { localStorage.setItem(TASK_KEY, JSON.stringify(tasks)); } catch (e) {} }

  window.setStatus = function (id, val) {
    var t = tasks.find(function (x) { return x.id === id; });
    if (t) { t.status = val; save(); renderTasks(); }
  };
  window.delTask = function (id) {
    tasks = tasks.filter(function (x) { return x.id !== id; });
    save(); renderTasks();
  };
  window.addTask = function (scope) {
    var input = document.getElementById(scope === 'team' ? 'addTeamInput' : 'addYouInput');
    var v = (input.value || '').trim();
    if (!v) return;
    tasks.push({ id: 'u' + Date.now(), scope: scope, src: 'self', title: v, status: 'pending' });
    input.value = '';
    save(); renderTasks();
  };

  function statusSelect(t) {
    return '<select class="status-select ' + t.status + '" onchange="setStatus(\'' + t.id + '\', this.value)">' +
      '<option value="pending"' + (t.status === 'pending' ? ' selected' : '') + '>Pending</option>' +
      '<option value="complete"' + (t.status === 'complete' ? ' selected' : '') + '>Complete</option>' +
      '</select>';
  }
  function delBtn(t) {
    return '<button class="task-del" title="Delete" onclick="delTask(\'' + t.id + '\')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>';
  }
  function unboundBadge() {
    return '<div class="task-badge"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>Assigned by UNbound</div>';
  }
  function cardHTML(t) {
    if (t.src === 'unbound') {
      return '<div class="task-card">' +
        '<div class="task-thumb" style="background:' + t.color + '"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICONS[t.icon] + '</svg></div>' +
        '<div class="task-main">' + unboundBadge() + '<div class="task-h">' + esc(t.title) + '</div><div class="task-d">' + esc(t.desc || '') + '</div></div>' +
        '<div class="task-actions">' + statusSelect(t) + '</div></div>';
    }
    return '<div class="task-card self">' +
      '<div class="task-main"><div class="task-h">' + esc(t.title) + '</div></div>' +
      '<div class="task-actions">' + statusSelect(t) + delBtn(t) + '</div></div>';
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  function renderTasks() {
    var scopes = ['team', 'you'];
    scopes.forEach(function (sc) {
      var list = document.getElementById(sc === 'team' ? 'teamList' : 'youList');
      if (!list) return;
      var active = tasks.filter(function (t) { return t.scope === sc && t.status !== 'complete'; });
      // container (unbound) tasks first, then self
      active.sort(function (a, b) { return (a.src === 'unbound' ? 0 : 1) - (b.src === 'unbound' ? 0 : 1); });
      list.innerHTML = active.length ? active.map(cardHTML).join('') :
        '<div class="task-empty">No open tasks here — nice work!</div>';
      var cnt = document.getElementById(sc === 'team' ? 'teamCount' : 'youCount');
      if (cnt) cnt.textContent = active.length + ' open';
    });
    // completed
    var comp = tasks.filter(function (t) { return t.status === 'complete'; });
    var cl = document.getElementById('completedList');
    if (cl) {
      cl.innerHTML = comp.length ? comp.map(function (t) {
        var scopeTag = '<span style="font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-faint);font-weight:600">' + (t.scope === 'team' ? 'Team' : 'Personal') + '</span>';
        if (t.src === 'unbound') {
          return '<div class="task-card"><div class="task-thumb" style="background:' + t.color + '"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICONS[t.icon] + '</svg></div>' +
            '<div class="task-main">' + scopeTag + '<div class="task-h">' + esc(t.title) + '</div><div class="task-d">' + esc(t.desc || '') + '</div></div>' +
            '<div class="task-actions">' + statusSelect(t) + '</div></div>';
        }
        return '<div class="task-card self"><div class="task-main">' + scopeTag + '<div class="task-h">' + esc(t.title) + '</div></div><div class="task-actions">' + statusSelect(t) + delBtn(t) + '</div></div>';
      }).join('') : '<div class="task-empty">Nothing completed yet. Mark a task complete to see it here.</div>';
    }
    var cc = document.getElementById('compCount');
    if (cc) cc.textContent = comp.length + ' done';
    // overview stat counts
    var open = tasks.filter(function (t) { return t.status !== 'complete'; }).length;
    var done = comp.length;
    var o = document.getElementById('ovOpenTasks'); if (o) o.textContent = open;
    var d = document.getElementById('ovDoneTasks'); if (d) d.textContent = done;
  }

  window.toggleCompleted = function () {
    var main = document.getElementById('tasksMain');
    var comp = document.getElementById('tasksCompleted');
    var btn = document.getElementById('completedToggle');
    var showing = comp.style.display !== 'none';
    if (showing) {
      comp.style.display = 'none'; main.style.display = '';
      btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> View Completed Tasks';
    } else {
      comp.style.display = ''; main.style.display = 'none';
      btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg> Back to Active Tasks';
    }
  };

  /* ---------- Docs ---------- */
  var DOCS = [
    { name: 'Fellowship Handbook', link: 'docs.google.com/…', by: 'UNbound', desc: 'Everything you need: timeline, expectations, and rubrics.' },
    { name: 'Project Proposal Template', link: 'docs.google.com/…', by: 'UNbound', desc: 'Copy this and place it in your team folder before Phase 2.' },
    { name: 'SDG Target Reference', link: 'un.org/sdgs', by: 'UNbound', desc: 'Official indicators for all 17 Sustainable Development Goals.' },
    { name: 'Pitch Deck Template', link: 'figma.com/…', by: 'UNbound', desc: 'Branded slides for your Launch Sequence presentation.' },
    { name: 'Budget Workbook', link: 'docs.google.com/…', by: 'Lukah V.', desc: 'Track projected costs, funding, and reimbursements.' }
  ];
  function renderDocs() {
    var tb = document.getElementById('docsBody');
    if (!tb) return;
    tb.innerHTML = DOCS.map(function (d) {
      var initials = d.by === 'UNbound' ? 'U' : d.by.split(' ').map(function (w) { return w[0]; }).join('').slice(0, 2);
      return '<tr>' +
        '<td><div class="doc-name"><span class="doc-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span>' + esc(d.name) + '</div></td>' +
        '<td><span class="doc-link"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>' + esc(d.link) + '</span></td>' +
        '<td><span class="doc-by"><span class="av">' + esc(initials) + '</span>' + esc(d.by) + '</span></td>' +
        '<td class="doc-desc">' + esc(d.desc) + '</td></tr>';
    }).join('');
  }

  /* ---------- Meeting Hub (When2Meet style) ---------- */
  var DAYS = [['Sun', 'May 31'], ['Mon', 'Jun 1'], ['Tue', 'Jun 2'], ['Wed', 'Jun 3'], ['Thu', 'Jun 4'], ['Fri', 'Jun 5'], ['Sat', 'Jun 6']];
  var HOURS = ['9 AM', '10 AM', '11 AM', '12 PM', '1 PM', '2 PM', '3 PM', '4 PM', '5 PM'];
  var MH_KEY = 'unbound_dash_avail_v1';
  var avail = loadAvail();
  var built = false;
  function loadAvail() { try { var r = localStorage.getItem(MH_KEY); if (r) return JSON.parse(r); } catch (e) {} return {}; }
  function saveAvail() { try { localStorage.setItem(MH_KEY, JSON.stringify(avail)); } catch (e) {} }
  // deterministic pseudo group counts (out of 5 other members)
  function groupCount(d, h) { var n = (d * 7 + h * 3 + 2) % 6; return n; }

  function buildMeetingGrids() {
    if (built) return; built = true;
    var my = document.getElementById('myGrid');
    var gp = document.getElementById('groupGrid');
    if (!my || !gp) return;
    var cols = '64px repeat(7, 1fr)';
    [my, gp].forEach(function (g) { g.style.gridTemplateColumns = cols; });

    function header(g) {
      var h = '<div class="corner"></div>';
      DAYS.forEach(function (d) { h += '<div class="dayhdr">' + d[0] + '<small>' + d[1] + '</small></div>'; });
      return h;
    }
    var myHTML = header(my), gpHTML = header(gp);
    for (var hi = 0; hi < HOURS.length; hi++) {
      myHTML += '<div class="timelbl">' + HOURS[hi] + '</div>';
      gpHTML += '<div class="timelbl">' + HOURS[hi] + '</div>';
      for (var di = 0; di < 7; di++) {
        var key = di + '_' + hi;
        var on = avail[key] ? ' av' : '';
        myHTML += '<div class="cell' + on + '" data-key="' + key + '"></div>';
        var cnt = groupCount(di, hi);
        var op = cnt / 5;
        var bg = cnt === 0 ? 'var(--bg)' : 'rgba(0,180,216,' + (0.18 + op * 0.72).toFixed(2) + ')';
        gpHTML += '<div class="cell" title="' + cnt + '/5 free" style="background:' + bg + '"></div>';
      }
    }
    my.innerHTML = myHTML; gp.innerHTML = gpHTML;

    // click + drag to toggle
    var dragging = false, setTo = true;
    function apply(cell) {
      var k = cell.dataset.key; if (!k) return;
      if (setTo) { avail[k] = 1; cell.classList.add('av'); }
      else { delete avail[k]; cell.classList.remove('av'); }
    }
    my.addEventListener('mousedown', function (e) {
      var c = e.target.closest('.cell'); if (!c) return;
      dragging = true; setTo = !c.classList.contains('av'); apply(c); e.preventDefault();
    });
    my.addEventListener('mouseover', function (e) {
      if (!dragging) return; var c = e.target.closest('.cell'); if (c) apply(c);
    });
    document.addEventListener('mouseup', function () { if (dragging) { dragging = false; saveAvail(); } });
  }

  /* ---------- Milestones ---------- */
  var BADGES = [
    { earned: true, color: '#00B4D8', t: 'Liftoff', d: 'Joined the Fellowship and set up your team.', icon: '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>' },
    { earned: true, color: '#7c5cff', t: 'Empathy Explorer', d: 'Completed 5 community empathy interviews.', icon: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>' },
    { earned: true, color: '#1f9d57', t: 'Goal Setter', d: 'Selected and mapped your project SDGs.', icon: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>' },
    { earned: true, color: '#e0772b', t: 'Team Player', d: 'Logged availability and synced with your cohort.', icon: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/>' },
    { earned: false, color: '#0A97D9', t: 'Builder', d: 'Ship your first project prototype.', prog: 40, icon: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>' },
    { earned: false, color: '#C5192D', t: 'Storyteller', d: 'Deliver your Launch Sequence pitch.', prog: 15, icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' },
    { earned: false, color: '#DD1367', t: 'Changemaker', d: 'Reach 100 people with your project.', prog: 0, icon: '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>' },
    { earned: false, color: '#FCC30B', t: 'Mentor Magnet', d: 'Complete all mentor 1:1 check-ins.', prog: 50, icon: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>' },
    { earned: false, color: '#19486A', t: 'Touchdown', d: 'Graduate the Fellowship.', prog: 0, icon: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>' }
  ];
  function renderBadges() {
    var g = document.getElementById('badgeGrid');
    if (!g) return;
    g.innerHTML = BADGES.map(function (b) {
      var medal = '<div class="medal" style="background:' + (b.earned ? b.color : '') + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + b.icon + '</svg></div>';
      var foot = b.earned ? '<div class="earned-tag">✓ Earned</div>'
        : (b.prog ? '<div class="prog"><i style="width:' + b.prog + '%"></i></div><div class="lock-tag">' + b.prog + '% complete</div>'
          : '<div class="lock-tag">🔒 Locked</div>');
      return '<div class="badge ' + (b.earned ? 'earned' : 'locked') + '">' + medal +
        '<div class="bt">' + b.t + '</div><div class="bd">' + b.d + '</div>' + foot + '</div>';
    }).join('');
  }

  /* ---------- Init ---------- */
  renderPhases();
  renderTasks();
  renderDocs();
  renderBadges();
  var initial = (location.hash || '#overview').slice(1);
  if (!document.getElementById('view-' + initial)) initial = 'overview';
  showView(initial);
})();
