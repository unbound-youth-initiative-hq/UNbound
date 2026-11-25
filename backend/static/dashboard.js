/* ===== UNbound Fellow Dashboard Complete JS ===== */
document.addEventListener('DOMContentLoaded', () => {
  'use strict';
  const googleIntegrationsEnabled = document.body.dataset.googleIntegrationsEnabled === 'true';
  document.querySelectorAll('[data-dashboard-notice]').forEach(notice => {
    let timer;
    let dismissed = false;
    const dismiss = () => {
      if (dismissed) return;
      dismissed = true;
      clearTimeout(timer);
      notice.classList.add('is-dismissing');
      setTimeout(() => notice.remove(), 250);
    };
    notice.querySelector('[data-dismiss-notice]')?.addEventListener('click', dismiss);
    const schedule = () => {
      clearTimeout(timer);
      if (notice.hasAttribute('data-auto-dismiss') && !dismissed) timer = setTimeout(dismiss, 3000);
    };
    notice.addEventListener('mouseenter', () => clearTimeout(timer));
    notice.addEventListener('mouseleave', schedule);
    notice.addEventListener('focusin', () => clearTimeout(timer));
    notice.addEventListener('focusout', schedule);
    schedule();
  });
  const { escapeHtml, safeUrl, safeColor, safeIcon, taskIconForeground, percentage, recordId, readJsonResponse, taskCardsMarkup, phaseRoadmapMarkup, formatTaskTime, adjacentAvailabilitySlot, availabilityDateBands } = window.UNboundUI;

  /* The portal's CSRF secret belongs to its session, independently of Admin. */
  const csrftoken = document.querySelector('meta[name="csrf-token"]')?.content || '';

  /* ---------- Mobile navigation drawer ---------- */
  const sidebar = document.getElementById('sidebar');
  const main = document.querySelector('.main');
  const menuTrigger = document.querySelector('.mobile-menu-fab');
  const menuClose = document.querySelector('.sidebar-mobile-close');
  const menuScrim = document.querySelector('.sidebar-scrim');
  const mobileLayout = window.matchMedia('(max-width: 900px)');

  function setDrawer(open, returnFocus = false) {
    const expanded = mobileLayout.matches && open;
    const wasOpen = sidebar.classList.contains('open');
    const focusInSidebar = sidebar.contains(document.activeElement);
    sidebar.classList.toggle('open', expanded);
    document.body.classList.toggle('mobile-menu-open', expanded);
    menuTrigger.setAttribute('aria-expanded', String(expanded));
    menuScrim.hidden = !expanded;
    if (expanded) {
      sidebar.inert = false;
      sidebar.setAttribute('role', 'dialog');
      sidebar.setAttribute('aria-modal', 'true');
      sidebar.setAttribute('aria-label', 'Dashboard menu');
      menuClose.focus();
    } else {
      main.inert = false;
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
      sidebar.removeAttribute('aria-label');
      if (mobileLayout.matches && (returnFocus || (!wasOpen && focusInSidebar))) menuTrigger.focus();
      if (!mobileLayout.matches && wasOpen) (sidebar.querySelector('[aria-current]') || sidebar.querySelector('a')).focus();
      sidebar.inert = mobileLayout.matches;
    }
    main.inert = expanded;
  }

  menuTrigger.addEventListener('click', () => setDrawer(true));
  menuClose.addEventListener('click', () => setDrawer(false, true));
  menuScrim.addEventListener('click', () => setDrawer(false, true));
  mobileLayout.addEventListener('change', () => setDrawer(false));
  sidebar.addEventListener('keydown', event => {
    if (!sidebar.classList.contains('open')) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      setDrawer(false, true);
    } else if (event.key === 'Tab') {
      const controls = Array.from(sidebar.querySelectorAll('a[href], button:not([disabled])'))
        .filter(control => control.getClientRects().length);
      const end = event.shiftKey ? controls[0] : controls.at(-1);
      if (document.activeElement === end) {
        event.preventDefault();
        (event.shiftKey ? controls.at(-1) : controls[0]).focus();
      }
    }
  });
  setDrawer(false);

  /* ---------- Persisted dashboard accent ---------- */
  const accentChoices = Array.from(document.querySelectorAll('[data-accent-choice]'));
  const accentStatus = document.getElementById('accentSaveStatus');
  const accentModal = document.getElementById('dashboardPreferencesModal');
  const validAccents = ['ocean', 'sky', 'coral', 'violet', 'mint', 'forest', 'rose', 'amber'];
  const accentChoiceGroup = document.querySelector('.accent-palette-options');
  let savingAccent = false;

  function setAccentPalette(palette) {
    if (!validAccents.includes(palette)) return;
    document.body.dataset.accent = palette;
    accentChoices.forEach(choice => {
      choice.setAttribute('aria-pressed', String(choice.dataset.accentChoice === palette));
    });
  }

  setAccentPalette(document.body.dataset.accent || 'ocean');

  const openAccentButton = document.getElementById('openDashboardPreferences');
  const closeAccentButton = document.getElementById('closeDashboardPreferences');
  if (openAccentButton && accentModal) {
    openAccentButton.addEventListener('click', () => {
      if (accentModal.open) return;
      if (mobileLayout.matches) setDrawer(false, true);
      accentModal.showModal();
      document.body.classList.add('settings-open');
      const selected = accentModal.querySelector('[aria-pressed="true"]');
      if (selected) selected.focus();
    });
    closeAccentButton.addEventListener('click', () => accentModal.close());
    accentModal.addEventListener('click', event => {
      if (event.target !== accentModal) return;
      const bounds = accentModal.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom) accentModal.close();
    });
    accentModal.addEventListener('close', () => {
      document.body.classList.remove('settings-open');
      (mobileLayout.matches ? menuTrigger : openAccentButton).focus();
    });
  }

  accentChoices.forEach(choice => {
    choice.addEventListener('click', () => {
      const palette = choice.dataset.accentChoice;
      const previousPalette = document.body.dataset.accent || 'ocean';
      if (savingAccent || !validAccents.includes(palette) || palette === previousPalette) return;

      setAccentPalette(palette);
      if (accentStatus) accentStatus.textContent = 'Saving your color…';
      savingAccent = true;
      accentChoiceGroup.setAttribute('aria-busy', 'true');

      fetch('/api/dashboard/preferences/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
        body: JSON.stringify({ accent_palette: palette })
      })
        .then(response => readJsonResponse(response).then(data => ({ response, data })))
        .then(({ response, data }) => {
          if (!response.ok || data.status !== 'success') throw new Error(data.detail || 'Unable to save preference.');
          if (accentStatus) accentStatus.textContent = 'Color saved to your profile.';
        })
        .catch(() => {
          setAccentPalette(previousPalette);
          if (accentStatus) accentStatus.textContent = 'Could not save the color. Your previous choice was restored.';
        })
        .finally(() => {
          savingAccent = false;
          accentChoiceGroup.removeAttribute('aria-busy');
        });
    });
  });

  /* ---------- Navigation / View Switcher ---------- */
  window.showView = function (name, moveFocus = true) {
    if (!googleIntegrationsEnabled && name === 'calendar') name = 'overview';
    const next = document.getElementById('view-' + name);
    if (!next) return;
    const changedView = !next.classList.contains('active');
    setDrawer(false);
    document.querySelectorAll('.view').forEach(view => view.classList.toggle('active', view === next));
    document.querySelectorAll('.sb-nav [data-view]').forEach(button => {
      const current = button.dataset.view === name;
      button.classList.toggle('active', current);
      if (current) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    if (moveFocus) {
      if (changedView) {
        if (mobileLayout.matches) window.scrollTo(0, 0);
        else main.scrollTop = 0;
      }
      const heading = next.querySelector('h1');
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
    }

    if (name === 'overview') {
      refreshWorkspace();
    } else if (name === 'drive' && googleIntegrationsEnabled) {
      loadPersonalFiles();
      loadSharedFiles();
    } else if (name === 'tasks') {
      loadTasks();
    } else if (name === 'calendar') {
      if (googleIntegrationsEnabled) loadCalendar('calendarEvents');
    } else if (name === 'meetings') {
      if (googleIntegrationsEnabled) loadCalendar('calendarEvents');
      loadMeetingHub();
    } else if (name === 'badges') {
      loadBadges();
    }
  };

  /* ---------- Workspace Overview API Loaders ---------- */
  window.refreshWorkspace = function () {
    loadDashboardOverview();
  };

  function loadDashboardOverview() {
    fetch('/api/dashboard/overview/')
      .then(readJsonResponse)
      .then(data => {
        if (data.status === 'success') {
          const statusEl = document.getElementById('dashboardLoadStatus');
          if (statusEl) statusEl.textContent = '';
          const fnEl = document.getElementById('dashFirstName');
          const cNameEl = document.getElementById('dashCohortName');
          const cPhaseEl = document.getElementById('dashCurrentPhase');
          const projEl = document.getElementById('dashProjectName');
          const bannerPhaseEl = document.getElementById('dashBannerPhase');
          const chapterEl = document.getElementById('dashChapter');

          if (fnEl) fnEl.textContent = data.first_name || 'Fellow';
          if (cNameEl) cNameEl.textContent = data.cohort_name || 'No cohort assigned';
          if (cPhaseEl) cPhaseEl.textContent = data.current_phase || 'Not assigned';
          if (projEl) projEl.textContent = data.project_name || 'No project assigned yet';
          if (bannerPhaseEl) bannerPhaseEl.textContent = data.current_phase || 'Not assigned';
          if (chapterEl) chapterEl.textContent = data.chapter || 'Not assigned';

          document.getElementById('dashOpenTasks').textContent = data.stats.open_tasks;
          document.getElementById('dashCompletedTasks').textContent = data.stats.completed_tasks;
          document.getElementById('dashBadgesEarned').textContent = data.stats.earned_badges;
          document.getElementById('dashBadgesTotal').textContent = data.stats.total_badges;
          document.getElementById('dashLevelName').textContent = data.stats.level_name;
          document.getElementById('dashCompletionPct').textContent = `${percentage(data.stats.completion_pct)}%`;
          document.getElementById('dashCompletionFill').style.width = `${percentage(data.stats.completion_pct)}%`;

          // Render Google Profile Pictures
          renderTeamAvatars(data.team_members);

          // Render Cohort's Selected UN Goals (SDGs)
          renderSdgPills(data.sdgs);

          // Highlight Active Phase Step
          renderPhases(data.phases, data.current_phase);

          renderDeadlines(data.deadlines);
          loadNextUpEvents();
        }
      })
      .catch(error => {
        const message = document.getElementById('dashboardLoadStatus');
        if (message) message.textContent = error.message || 'Unable to load your workspace. Please refresh.';
      });
  }

  function renderDeadlines(deadlines) {
    const list = document.getElementById('dashDeadlines');
    if (!list || !deadlines) return;
    const rows = [
      ...deadlines.overdue.map(task => ({ ...task, label: 'Overdue', overdue: true })),
      ...deadlines.upcoming.map(task => ({
        ...task,
        label: task.due_date === deadlines.today ? 'Due today' : 'Due',
      })),
    ];
    list.innerHTML = rows.length ? rows.map(task => {
      const date = task.label === 'Due today' ? '' : ' · ' + escapeHtml(formatShortDate(task.due_date));
      const time = task.due_time ? ' · ' + formatTaskTime(task.due_time) : '';
      return '<div class="nextup-item"><div class="nextup-info">' +
        '<div class="nextup-title">' + escapeHtml(task.title) + '</div>' +
        '<div class="nextup-meta' + (task.overdue ? ' deadline-overdue' : '') + '">' +
        task.label + date + time + '</div></div></div>';
    }).join('') + '<button class="btn btn-ghost btn-sm" type="button" onclick="showView(\'tasks\')">Open Tasks</button>'
      : '<p class="empty-state">No upcoming or overdue task deadlines.</p>';
  }

  function renderSdgPills(sdgs) {
    const container = document.getElementById('dashSdgPills');
    if (!container) return;

    if (!sdgs || sdgs.length === 0) {
      container.innerHTML = `<div class="empty-state">No SDGs selected for this cohort yet. Click "Edit SDGs" to choose goals.</div>`;
      return;
    }

    container.innerHTML = sdgs.map(s => `
      <div class="sdg-pill" style="--sdg-color: ${safeColor(s.color)};">
        <span class="sdg-num">${escapeHtml(s.code)}</span> ${escapeHtml(s.name)}
      </div>
    `).join('');
  }

  /* ---------- SDG Selector Controller ---------- */
  const sdgModal = document.getElementById('sdgModal');
  const btnOpenSdgModal = document.getElementById('btnOpenSdgModal');
  const btnCloseSdgModal = document.getElementById('btnCloseSdgModal');
  const btnCancelSdgModal = document.getElementById('btnCancelSdgModal');
  const btnSaveSdgs = document.getElementById('btnSaveSdgs');
  const sdgPickerGrid = document.getElementById('sdgPickerGrid');
  const sdgSelectedCount = document.getElementById('sdgSelectedCount');

  let localSdgSelection = new Set();

  function openSdgModal() {
    if (sdgModal) sdgModal.classList.add('active');
    loadSdgPickerList();
  }

  function closeSdgModal() {
    if (sdgModal) sdgModal.classList.remove('active');
  }

  function loadSdgPickerList() {
    if (!sdgPickerGrid) return;
    sdgPickerGrid.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Fetching UN goals...</div>`;

    fetch('/api/cohort/sdgs/')
      .then(readJsonResponse)
      .then(data => {
        if (data.status === 'success' && data.sdgs) {
          localSdgSelection.clear();
          data.sdgs.forEach(s => {
            if (s.selected) localSdgSelection.add(s.code);
          });
          renderSdgPickerItems(data.sdgs);
        } else {
          sdgPickerGrid.innerHTML = `<div class="error-state">Unable to load UN goals.</div>`;
        }
      })
      .catch(() => {
        sdgPickerGrid.innerHTML = `<div class="error-state">Error loading UN goals.</div>`;
      });
  }

  function renderSdgPickerItems(allSdgs) {
    if (!sdgPickerGrid) return;

    sdgPickerGrid.innerHTML = allSdgs.map(s => {
      const isSel = localSdgSelection.has(s.code);
      return `
        <div class="sdg-picker-item ${isSel ? 'selected' : ''}"
             style="--picker-color: ${safeColor(s.color)};"
             data-code="${escapeHtml(s.code)}">
          <span class="sdg-picker-num">${escapeHtml(s.code)}</span>
          <span class="sdg-picker-name">${escapeHtml(s.name)}</span>
          <i class="fa-solid fa-circle-check sdg-check-icon"></i>
        </div>
      `;
    }).join('');

    updateSdgCountLabel();

    sdgPickerGrid.querySelectorAll('.sdg-picker-item').forEach(item => {
      item.addEventListener('click', () => {
        const code = parseInt(item.dataset.code, 10);
        if (localSdgSelection.has(code)) {
          localSdgSelection.delete(code);
          item.classList.remove('selected');
        } else {
          localSdgSelection.add(code);
          item.classList.add('selected');
        }
        updateSdgCountLabel();
      });
    });
  }

  function updateSdgCountLabel() {
    if (sdgSelectedCount) {
      sdgSelectedCount.textContent = `${localSdgSelection.size} selected`;
    }
  }

  function saveSdgSelection() {
    if (!btnSaveSdgs) return;
    btnSaveSdgs.disabled = true;
    btnSaveSdgs.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Saving...`;

    fetch('/api/cohort/sdgs/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify({ sdg_codes: Array.from(localSdgSelection) })
    })
      .then(readJsonResponse)
      .then(data => {
        btnSaveSdgs.disabled = false;
        btnSaveSdgs.innerHTML = `Save SDGs`;
        if (data.status === 'success') {
          closeSdgModal();
          renderSdgPills(data.sdgs);
        } else {
          alert('Error updating SDGs: ' + (data.detail || 'Unknown error'));
        }
      })
      .catch(() => {
        btnSaveSdgs.disabled = false;
        btnSaveSdgs.innerHTML = `Save SDGs`;
        alert('Failed to save SDGs selection.');
      });
  }

  if (btnOpenSdgModal) btnOpenSdgModal.addEventListener('click', openSdgModal);
  if (btnCloseSdgModal) btnCloseSdgModal.addEventListener('click', closeSdgModal);
  if (btnCancelSdgModal) btnCancelSdgModal.addEventListener('click', closeSdgModal);
  if (btnSaveSdgs) btnSaveSdgs.addEventListener('click', saveSdgSelection);

  function renderTeamAvatars(members) {
    const container = document.getElementById('dashTeamAvatars');
    if (!container) return;

    if (!members || members.length === 0) {
      container.innerHTML = '<span class="empty-state">No team assigned yet.</span>';
      return;
    }

    const maxDisplay = 4;
    const visible = members.slice(0, maxDisplay);
    const remaining = members.length - maxDisplay;

    let html = visible.map(m => {
      if (m.picture) {
        return `<div class="team-avatar-circle" title="${escapeHtml(m.name)} (${escapeHtml(m.role)})">
                  <img src="${escapeHtml(safeUrl(m.picture, ''))}" alt="${escapeHtml(m.name)}" referrerpolicy="no-referrer" />
                </div>`;
      } else {
        return `<div class="team-avatar-circle" title="${escapeHtml(m.name)} (${escapeHtml(m.role)})">${escapeHtml(m.initials)}</div>`;
      }
    }).join('');

    if (remaining > 0) {
      html += `<div class="team-avatar-circle more-circle" title="${remaining} more team members">+${remaining}</div>`;
    }

    container.innerHTML = html;
  }

  function renderPhases(phases, currentPhase) {
    const container = document.getElementById('phaseRoadmap');
    if (container) container.innerHTML = phaseRoadmapMarkup(phases, currentPhase);
  }

  function requestCalendarEvents(range = null) {
    if (!googleIntegrationsEnabled) return Promise.resolve([]);
    let url = '/api/google/calendar/';
    if (range) {
      const params = new URLSearchParams({ time_min: range.timeMin, time_max: range.timeMax });
      url += `?${params.toString()}`;
    }

    return fetch(url)
      .then(response => readJsonResponse(response).then(data => ({ response, data })))
      .then(({ response, data }) => {
        if (!response.ok || data.connected === false) {
          throw new Error(data.detail || 'Unable to load Google Calendar events.');
        }
        const events = Array.isArray(data.events) ? data.events : [];
        const seenIds = new Set();
        const seenAllDayEvents = new Set();
        return events.filter(event => {
          if (event.id && seenIds.has(event.id)) return false;
          if (event.id) seenIds.add(event.id);

          // Google can expose the same all-day event as separate records with
          // different IDs or metadata. Deduplicate what the user actually sees.
          if (event.start && event.start.date) {
            const displayDate = parseCalendarEventDate(event);
            const dateKey = displayDate
              ? `${displayDate.getFullYear()}-${String(displayDate.getMonth() + 1).padStart(2, '0')}-${String(displayDate.getDate()).padStart(2, '0')}`
              : event.start.date;
            const titleKey = String(event.summary || '').normalize('NFKC').trim().toLocaleLowerCase().replace(/\s+/g, ' ');
            const duplicateKey = `${dateKey}|${titleKey}`;
            if (seenAllDayEvents.has(duplicateKey)) return false;
            seenAllDayEvents.add(duplicateKey);
          }
          return true;
        });
      });
  }

  function parseCalendarEventDate(event) {
    const start = event && event.start;
    if (!start) return null;

    let date;
    if (start.dateTime) {
      date = new Date(start.dateTime);
    } else if (start.date) {
      const [year, month, day] = start.date.split('-').map(Number);
      date = new Date(year, month - 1, day, 12);
    }
    return date && !Number.isNaN(date.getTime()) ? date : null;
  }

  function setCalendarMessage(container, message, kind = 'empty') {
    container.replaceChildren();
    const state = document.createElement('div');
    state.className = kind === 'error' ? 'error-state' : kind === 'loading' ? 'loading' : 'empty-state';
    state.textContent = message;
    container.appendChild(state);
  }

  function buildCalendarEventItem(event, compact = false) {
    const date = parseCalendarEventDate(event);
    if (!date) return null;

    const item = document.createElement('div');
    item.className = compact ? 'nextup-item' : 'event-item';

    const dateBox = document.createElement('div');
    dateBox.className = compact ? 'nextup-date-box' : 'event-date';
    const month = document.createElement('span');
    month.textContent = date.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
    const day = document.createElement('span');
    day.textContent = String(date.getDate());
    dateBox.append(month, day);

    const info = document.createElement('div');
    info.className = compact ? 'nextup-info' : 'event-main';
    const title = document.createElement('div');
    title.className = compact ? 'nextup-title' : 'item-title';
    title.textContent = event.summary || 'Untitled event';
    const meta = document.createElement('div');
    meta.className = compact ? 'nextup-meta' : 'item-meta';
    const time = event.start && event.start.dateTime
      ? date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
      : 'All day';
    meta.textContent = [time, event.location].filter(Boolean).join(' · ');
    info.append(title, meta);
    item.append(dateBox, info);

    if (!compact && event.htmlLink) {
      try {
        const linkUrl = new URL(event.htmlLink);
        if (linkUrl.protocol === 'https:' && (linkUrl.hostname === 'google.com' || linkUrl.hostname.endsWith('.google.com'))) {
          const link = document.createElement('a');
          link.className = 'open-link';
          link.href = linkUrl.href;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = 'Open';
          item.appendChild(link);
        }
      } catch (_) {
        // Ignore malformed calendar links while keeping the event visible.
      }
    }
    return item;
  }

  function renderCalendarEvents(container, events, compact = false) {
    container.replaceChildren();
    const seenAllDayDisplayKeys = new Set();
    const validEvents = events
      .map(event => ({ event, date: parseCalendarEventDate(event) }))
      .filter(item => item.date)
      .sort((a, b) => a.date - b.date)
      .filter(({ event, date }) => {
        if (!event.start || !event.start.date) return true;
        const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
        const titleKey = String(event.summary || '').normalize('NFKC').trim().toLocaleLowerCase().replace(/\s+/g, ' ');
        const duplicateKey = `${dateKey}|${titleKey}`;
        if (seenAllDayDisplayKeys.has(duplicateKey)) return false;
        seenAllDayDisplayKeys.add(duplicateKey);
        return true;
      });

    if (!validEvents.length) {
      setCalendarMessage(container, 'No upcoming events found in your primary Google Calendar.');
      return;
    }

    validEvents.slice(0, compact ? 2 : 10).forEach(({ event }) => {
      const item = buildCalendarEventItem(event, compact);
      if (item) container.appendChild(item);
    });
  }

  function loadNextUpEvents() {
    if (!googleIntegrationsEnabled) return;
    const listEl = document.getElementById('dashNextUpList');
    if (!listEl) return;
    setCalendarMessage(listEl, 'Loading upcoming events…', 'loading');

    requestCalendarEvents()
      .then(events => renderCalendarEvents(listEl, events, true))
      .catch(error => setCalendarMessage(listEl, error.message || 'Could not load calendar events.', 'error'));
  }

  window.loadCalendar = function (targetId = 'calendarEvents') {
    if (!googleIntegrationsEnabled) return;
    const listEl = document.getElementById(targetId);
    if (!listEl) return;
    setCalendarMessage(listEl, 'Loading calendar events…', 'loading');

    requestCalendarEvents()
      .then(events => renderCalendarEvents(listEl, events))
      .catch(error => setCalendarMessage(listEl, error.message || 'Could not load calendar events. Try refreshing.', 'error'));
  };

  /* ---------- Tasks Controller ---------- */
  let showCompletedTasks = false;

  window.loadTasks = function () {
    const teamTasksList = document.getElementById('teamTasksList');
    const personalTasksList = document.getElementById('personalTasksList');
    const teamPill = document.getElementById('teamTaskCountPill');
    const personalPill = document.getElementById('personalTaskCountPill');

    if (teamTasksList) teamTasksList.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading team tasks...</div>`;
    if (personalTasksList) personalTasksList.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading personal tasks...</div>`;

    fetch('/api/tasks/')
      .then(readJsonResponse)
      .then(data => {
        const tasks = Array.isArray(data) ? data : (data.results || []);

        const filteredTasks = tasks.filter(t => showCompletedTasks ? (t.status === 'complete') : (t.status !== 'complete'));
        const teamTasks = filteredTasks.filter(t => t.scope === 'team');
        const personalTasks = filteredTasks.filter(t => t.scope === 'personal');

        const teamOpenCount = tasks.filter(t => t.scope === 'team' && t.status !== 'complete').length;
        const personalOpenCount = tasks.filter(t => t.scope === 'personal' && t.status !== 'complete').length;

        if (teamPill) teamPill.textContent = `${teamOpenCount} open`;
        if (personalPill) personalPill.textContent = `${personalOpenCount} open`;

        renderTaskCardsGroup(teamTasksList, teamTasks, 'No team tasks match this filter.');
        renderTaskCardsGroup(personalTasksList, personalTasks, 'No personal tasks match this filter.');
      })
      .catch(() => {
        if (teamTasksList) teamTasksList.innerHTML = `<div class="error-state">Error loading team tasks.</div>`;
        if (personalTasksList) personalTasksList.innerHTML = `<div class="error-state">Error loading personal tasks.</div>`;
      });
  };

  function renderTaskCardsGroup(containerEl, taskGroup, emptyMessage) {
    if (!containerEl) return;
    containerEl.innerHTML = taskCardsMarkup(taskGroup, emptyMessage);
  }

  window.updateTaskStatus = function (taskId, status) {
    fetch(`/api/tasks/${taskId}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify({ status })
    })
      .then(readJsonResponse)
      .then(() => {
        loadTasks();
      })
      .catch(error => { alert(error.message || 'Failed to update task status.'); loadTasks(); });
  };

  window.deleteTask = function (taskId) {
    if (!confirm('Are you sure you want to delete this task?')) return;
    fetch(`/api/tasks/${taskId}/`, {
      method: 'DELETE',
      headers: {
        'X-CSRFToken': csrftoken
      }
    })
      .then(res => {
        if (res.ok || res.status === 204) {
          loadTasks();
        } else {
          alert('Failed to delete task.');
        }
      })
      .catch(() => alert('Failed to delete task.'));
  };

  function taskDeadlineFields(form) {
    const date = form.elements.due_date;
    const time = form.elements.due_time;
    const syncTime = () => {
      time.disabled = !date.value;
      if (time.disabled) time.value = '';
    };
    date.addEventListener('input', syncTime);
    return {
      values: () => ({ due_date: date.value || null, due_time: time.value || null }),
      set: (dueDate, dueTime) => {
        date.value = dueDate || '';
        time.value = dueTime || '';
        syncTime();
      },
    };
  }

  function taskAppearanceFields(form) {
    const { icon, color } = form.elements;
    const preview = form.querySelector('.task-appearance-preview');
    const update = () => {
      preview.style.backgroundColor = color.value;
      preview.style.color = taskIconForeground(color.value);
      preview.firstElementChild.className = 'fa-solid ' + safeIcon(icon.value);
    };
    icon.addEventListener('change', update);
    color.addEventListener('input', update);
    update();
    return { update, values: () => ({ icon: icon.value, color: color.value }) };
  }

  function saveTask(url, method, data) {
    return fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
      body: JSON.stringify(data),
    }).then(readJsonResponse);
  }

  document.querySelectorAll('[data-task-scope]').forEach(form => {
    const deadline = taskDeadlineFields(form);
    const appearance = taskAppearanceFields(form);
    const feedback = form.querySelector('.form-feedback');
    const submit = form.querySelector('[type="submit"]');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const title = form.elements.title.value.trim();
      if (!title || submit.disabled) return;
      feedback.textContent = '';
      submit.disabled = true;
      try {
        await saveTask('/api/tasks/', 'POST', { title, scope: form.dataset.taskScope, ...deadline.values(), ...appearance.values() });
        form.reset();
        appearance.update();
        deadline.set(null, null);
        form.querySelector('details').open = false;
        loadTasks();
      } catch (error) {
        feedback.textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    });
  });

  const deadlineDialog = document.getElementById('taskDeadlineDialog');
  if (deadlineDialog) {
    const form = document.getElementById('taskDeadlineForm');
    const deadline = taskDeadlineFields(form);
    const appearance = taskAppearanceFields(form);
    const feedback = form.querySelector('.form-feedback');
    const submit = form.querySelector('[type="submit"]');
    const cancel = form.querySelector('[type="button"]');

    document.getElementById('view-tasks').addEventListener('click', event => {
      const button = event.target.closest('[data-task-deadline-id]');
      if (!button) return;
      form.dataset.taskId = button.dataset.taskDeadlineId;
      document.getElementById('taskDeadlineTitle').textContent = button.dataset.taskTitle;
      deadline.set(button.dataset.dueDate, button.dataset.dueTime);
      const icon = form.elements.icon;
      icon.querySelector('[data-legacy]')?.remove();
      if (![...icon.options].some(option => option.value === button.dataset.icon)) {
        const option = new Option('Current icon', button.dataset.icon);
        option.dataset.legacy = 'true';
        icon.add(option);
      }
      icon.value = button.dataset.icon;
      form.elements.color.value = button.dataset.color;
      appearance.update();
      feedback.textContent = '';
      deadlineDialog.showModal();
    });
    cancel.addEventListener('click', () => deadlineDialog.close());
    deadlineDialog.addEventListener('cancel', event => {
      if (submit.disabled) event.preventDefault();
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (submit.disabled) return;
      const id = recordId(form.dataset.taskId);
      if (!id) return;
      feedback.textContent = '';
      submit.disabled = cancel.disabled = true;
      try {
        await saveTask(`/api/tasks/${id}/`, 'PATCH', { ...deadline.values(), ...appearance.values() });
        deadlineDialog.close();
        loadTasks();
      } catch (error) {
        feedback.textContent = error.message;
      } finally {
        submit.disabled = cancel.disabled = false;
      }
    });
  }

  const btnToggleComp = document.getElementById('btnToggleCompletedTasks');
  if (btnToggleComp) {
    btnToggleComp.addEventListener('click', () => {
      showCompletedTasks = !showCompletedTasks;
      document.getElementById('lblToggleTasks').textContent = showCompletedTasks ? 'Show Open Tasks' : 'View Completed Tasks';
      loadTasks();
    });
  }

  /* ---------- Google Drive Controller ---------- */
  const personalFileList = document.getElementById('personalFileList');
  const sharedFileList = document.getElementById('sharedFileList');
  const personalFolderStatus = document.getElementById('personalFolderStatus');
  const personalBreadcrumbs = document.getElementById('personalBreadcrumbs');

  const folderModal = document.getElementById('folderModal');
  const btnOpenFolderModal = document.getElementById('btnOpenFolderModal');
  const btnCloseFolderModal = document.getElementById('btnCloseFolderModal');
  const btnCancelModal = document.getElementById('btnCancelModal');

  const btnRefreshPersonal = document.getElementById('btnRefreshPersonal');
  const btnRefreshShared = document.getElementById('btnRefreshShared');

  const folderSelectList = document.getElementById('folderSelectList');
  const inputFolderLink = document.getElementById('inputFolderLink');
  const btnSaveCustomFolder = document.getElementById('btnSaveCustomFolder');
  const btnUnlinkFolder = document.getElementById('btnUnlinkFolder');

  const tabButtons = document.querySelectorAll('.modal-tabs .tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  let currentNavFolderId = null;

  function getFileIconClass(mimeType) {
    if (!mimeType) return 'fa-file file-generic';
    if (mimeType.includes('folder')) return 'fa-folder file-folder';
    if (mimeType.includes('document')) return 'fa-file-word file-doc';
    if (mimeType.includes('spreadsheet')) return 'fa-file-excel file-sheet';
    if (mimeType.includes('presentation')) return 'fa-file-powerpoint file-slide';
    if (mimeType.includes('pdf')) return 'fa-file-pdf file-pdf';
    if (mimeType.includes('image')) return 'fa-file-image file-image';
    if (mimeType.includes('video')) return 'fa-file-video file-video';
    return 'fa-file file-generic';
  }

  function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function renderFileItem(file, isPersonal = true) {
    const isFolder = file.mimeType === 'application/vnd.google-apps.folder';
    const iconClass = getFileIconClass(file.mimeType);
    const modified = formatDate(file.modifiedTime);
    const ownerName = file.owners && file.owners.length > 0 ? file.owners[0].displayName : 'Shared';

    const item = document.createElement('div');
    item.className = `file-item ${isFolder ? 'folder-item' : ''}`;

    item.innerHTML = `
      <div class="file-info">
        <i class="fa-solid ${iconClass}"></i>
        <div class="file-text">
          <a href="${escapeHtml(safeUrl(file.webViewLink))}" target="_blank" rel="noopener noreferrer" class="file-name" title="${escapeHtml(file.name)}">
            ${escapeHtml(file.name)}
          </a>
          <span class="file-meta">
            ${escapeHtml(isFolder ? 'Folder' : ownerName)} • Modified ${escapeHtml(modified)}
          </span>
        </div>
      </div>
      <div class="file-actions">
        ${isFolder && isPersonal ? `<button class="btn btn-sm btn-ghost btn-subfolder" data-folder-id="${escapeHtml(file.id)}" data-folder-name="${escapeHtml(file.name)}"><i class="fa-solid fa-folder-open"></i> Open</button>` : ''}
        <a href="${escapeHtml(safeUrl(file.webViewLink))}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-ghost" title="Open in Google Drive">
          <i class="fa-solid fa-arrow-up-right-from-square"></i>
        </a>
      </div>
    `;

    if (isFolder && isPersonal) {
      const btnOpen = item.querySelector('.btn-subfolder');
      if (btnOpen) {
        btnOpen.addEventListener('click', (e) => {
          e.preventDefault();
          navigateToFolder(file.id, file.name);
        });
      }
    }

    return item;
  }

  function loadPersonalFiles(folderId = null) {
    if (!googleIntegrationsEnabled) return;
    if (!personalFileList) return;
    personalFileList.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Fetching personal files...</div>`;

    let url = '/api/google-drive/personal-files/';
    if (folderId) {
      url += `?folder_id=${encodeURIComponent(folderId)}`;
    }

    fetch(url)
      .then(readJsonResponse)
      .then(data => {
        if (data.status === 'success' || data.connected) {
          if (data.selected_folder_name) {
            personalFolderStatus.innerHTML = `<i class="fa-solid fa-folder"></i> ${escapeHtml(data.selected_folder_name)}`;
          } else {
            personalFolderStatus.innerHTML = `<i class="fa-solid fa-clock-rotate-left"></i> Recent Files (No folder linked)`;
          }

          personalFileList.innerHTML = '';
          if (!data.files || data.files.length === 0) {
            personalFileList.innerHTML = `<div class="empty-state"><p>No files found in this location.</p></div>`;
            return;
          }

          data.files.forEach(file => {
            personalFileList.appendChild(renderFileItem(file, true));
          });
        } else {
          personalFileList.innerHTML = `<div class="error-state">Unable to load personal files.</div>`;
        }
      })
      .catch(() => {
        personalFileList.innerHTML = `<div class="error-state">Error connecting to Google Drive.</div>`;
      });
  }

  function loadSharedFiles() {
    if (!googleIntegrationsEnabled) return;
    if (!sharedFileList) return;
    sharedFileList.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Fetching shared workspace files...</div>`;

    fetch('/api/google-drive/shared-files/')
      .then(readJsonResponse)
      .then(data => {
        sharedFileList.innerHTML = '';
        if (data.status === 'success' || data.connected) {
          if (!data.files || data.files.length === 0) {
            sharedFileList.innerHTML = `<div class="empty-state"><p>No official shared documents available at this time.</p></div>`;
            return;
          }

          data.files.forEach(file => {
            sharedFileList.appendChild(renderFileItem(file, false));
          });
        } else {
          sharedFileList.innerHTML = `<div class="error-state">Unable to load shared workspace files.</div>`;
        }
      })
      .catch(() => {
        sharedFileList.innerHTML = `<div class="error-state">Error loading shared files.</div>`;
      });
  }

  function loadUserFolders() {
    if (!googleIntegrationsEnabled) return;
    if (!folderSelectList) return;
    folderSelectList.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Fetching your Drive folders...</div>`;

    fetch('/api/google-drive/folders/')
      .then(readJsonResponse)
      .then(data => {
        folderSelectList.innerHTML = '';
        if ((data.status === 'success' || data.connected) && data.folders && data.folders.length > 0) {
          data.folders.forEach(folder => {
            const div = document.createElement('div');
            div.className = 'folder-select-item';
            div.innerHTML = `
              <div class="folder-select-info">
                <i class="fa-solid fa-folder"></i>
                <span>${escapeHtml(folder.name)}</span>
              </div>
              <button class="btn btn-sm btn-primary select-folder-btn">Select</button>
            `;

            div.querySelector('.select-folder-btn').addEventListener('click', () => {
              saveSelectedFolder(folder.id, folder.name);
            });

            folderSelectList.appendChild(div);
          });
        } else {
          folderSelectList.innerHTML = `<div class="empty-state"><p>No Google Drive folders found. You can paste a folder link in the next tab.</p></div>`;
        }
      })
      .catch(() => {
        folderSelectList.innerHTML = `<div class="error-state">Error loading folders.</div>`;
      });
  }

  function saveSelectedFolder(folderId, folderName = '') {
    if (!googleIntegrationsEnabled) return;
    fetch('/api/google-drive/set-folder/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify({ folder_id: folderId, folder_name: folderName })
    })
      .then(readJsonResponse)
      .then(data => {
        if (data.status === 'success') {
          closeFolderModal();
          currentNavFolderId = null;
          if (personalBreadcrumbs) personalBreadcrumbs.style.display = 'none';
          loadPersonalFiles();
        } else {
          alert('Error linking folder: ' + (data.message || 'Unknown error'));
        }
      })
      .catch(() => {
        alert('Failed to save folder selection.');
      });
  }

  function navigateToFolder(folderId, folderName) {
    currentNavFolderId = folderId;
    if (personalBreadcrumbs) {
      personalBreadcrumbs.style.display = 'flex';
      personalBreadcrumbs.innerHTML = `
        <span class="breadcrumb-item" id="bcRoot"><i class="fa-solid fa-house"></i> Main Folder</span>
        <span class="breadcrumb-separator"><i class="fa-solid fa-chevron-right"></i></span>
        <span class="breadcrumb-item active"><i class="fa-solid fa-folder-open"></i> ${escapeHtml(folderName)}</span>
      `;
      document.getElementById('bcRoot').addEventListener('click', () => {
        currentNavFolderId = null;
        personalBreadcrumbs.style.display = 'none';
        loadPersonalFiles();
      });
    }

    loadPersonalFiles(folderId);
  }

  function openFolderModal() {
    if (folderModal) folderModal.classList.add('active');
    loadUserFolders();
  }

  function closeFolderModal() {
    if (folderModal) folderModal.classList.remove('active');
  }

  if (btnOpenFolderModal) btnOpenFolderModal.addEventListener('click', openFolderModal);
  if (btnCloseFolderModal) btnCloseFolderModal.addEventListener('click', closeFolderModal);
  if (btnCancelModal) btnCancelModal.addEventListener('click', closeFolderModal);

  if (btnRefreshPersonal) btnRefreshPersonal.addEventListener('click', () => loadPersonalFiles(currentNavFolderId));
  if (btnRefreshShared) btnRefreshShared.addEventListener('click', loadSharedFiles);

  if (btnSaveCustomFolder) {
    btnSaveCustomFolder.addEventListener('click', () => {
      const val = inputFolderLink.value.trim();
      if (!val) {
        alert('Please enter a Google Drive folder link or ID.');
        return;
      }
      saveSelectedFolder(val);
    });
  }

  if (btnUnlinkFolder) {
    btnUnlinkFolder.addEventListener('click', () => {
      if (confirm('Are you sure you want to unlink your personal folder?')) {
        saveSelectedFolder('');
      }
    });
  }

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const target = btn.getAttribute('data-tab');
      const targetEl = document.getElementById(target);
      if (targetEl) targetEl.classList.add('active');
    });
  });

  /* ---------- Meeting Hub Controller (WhenBound) ---------- */
  let activeMeetingRequests = [];
  let currentRequestId = null;
  let currentRequestData = null;
  let currentDates = [];
  let currentStartHour = 9;
  let currentEndHour = 18;
  let availabilityConflictCache = { key: null, events: [] };
  let availabilityConflictPending = null;
  let userSlotsMap = {};
  let paintingAvailability = false;
  let skipMouseClick = false;
  let dragTargetState = null;
  let availabilitySaveQueue = Promise.resolve();
  let availabilityEditVersion = 0;
  let availabilityLoadedFor = null;
  let availabilityDayCapacity = 7;
  let groupAvailability = null;
  const availabilityGrid = document.getElementById('myAvailabilityGrid');
  const availabilitySaveStatus = document.getElementById('w2mSaveToast');

  window.openWhenBound = function (requestId = null) {
    showView('meetings');
    loadMeetingHub(requestId);
  };

  function formatShortDate(dateStr) {
    if (!dateStr) return '';
    const parts = dateStr.split('-');
    if (parts.length !== 3) return dateStr;
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const m = months[parseInt(parts[1], 10) - 1];
    return `${m} ${parseInt(parts[2], 10)}`;
  }

  function getFallbackWeekDayDates() {
    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);

    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const todayDateStr = now.toDateString();
    const weekDates = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(yesterday);
      d.setDate(yesterday.getDate() + i);

      const isToday = d.toDateString() === todayDateStr;
      const dayOfWeekIdx = d.getDay();
      const pad = n => (n < 10 ? '0' + n : n);
      const isoDate = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

      weekDates.push({
        date: isoDate,
        dayName: days[dayOfWeekIdx],
        monthName: months[d.getMonth()],
        dayNum: d.getDate(),
        dayIdx: i,
        dayOfWeek: dayOfWeekIdx,
        isToday: isToday
      });
    }
    return weekDates;
  }

  function loadMeetingHub(preferredRequestId = null) {
    fetch('/api/meetings/requests/')
      .then(readJsonResponse)
      .then(data => {
        const bannerEl = document.getElementById('w2mRequestBanner');
        const emptyEl = document.getElementById('w2mEmptyState');
        const controlsEl = document.getElementById('meetingControlsBar');
        const twoColEl = document.querySelector('.meeting-two-column-layout');

        if (data.status === 'success' && data.requests && data.requests.length > 0) {
          activeMeetingRequests = data.requests;

          if (preferredRequestId && activeMeetingRequests.some(r => r.id === preferredRequestId)) {
            currentRequestId = preferredRequestId;
          } else if (!currentRequestId || !activeMeetingRequests.some(r => r.id === currentRequestId)) {
            currentRequestId = activeMeetingRequests[0].id;
          }
          currentRequestData = activeMeetingRequests.find(r => r.id === currentRequestId) || activeMeetingRequests[0];

          if (bannerEl) bannerEl.style.display = 'block';
          if (emptyEl) emptyEl.style.display = 'none';
          if (controlsEl) controlsEl.style.display = 'flex';
          if (twoColEl) twoColEl.style.display = 'grid';

          renderRequestBanner();
          loadUserAvailabilityGrid();
          loadGroupAvailabilityGrid();
          resizeAvailabilityCalendars();
        } else {
          activeMeetingRequests = [];
          currentRequestId = null;
          currentRequestData = null;

          if (bannerEl) bannerEl.style.display = 'none';
          if (emptyEl) emptyEl.style.display = 'block';
          if (controlsEl) controlsEl.style.display = 'none';
          if (twoColEl) twoColEl.style.display = 'none';
        }
      })
      .catch(error => {
        const empty = document.getElementById('w2mEmptyState');
        if (empty) { empty.style.display = 'block'; empty.textContent = error.message || 'Unable to load meeting requests. Please refresh.'; }
      });
  }

  function pollDateLabel(request) {
    const first = formatShortDate(request.start_date);
    if (request.start_date === request.end_date) return first;
    const range = `${first} – ${formatShortDate(request.end_date)}`;
    return request.selected_dates?.length ? `${request.selected_dates.length} dates · ${range}` : range;
  }

  function renderRequestBanner() {
    if (!currentRequestData) return;
    const req = currentRequestData;
    currentStartHour = Number(req.start_hour);
    currentEndHour = Number(req.end_hour);
    currentDates = req.display_days;

    const titleEl = document.getElementById('w2mRequestTitle');
    const descEl = document.getElementById('w2mRequestDesc');
    const rangeEl = document.getElementById('w2mDateRange');
    const deadlineWrap = document.getElementById('w2mDeadlineWrap');
    const deadlineEl = document.getElementById('w2mDeadline');
    const statusPill = document.getElementById('w2mStatusPill');
    const targetCohort = document.getElementById('w2mTargetCohort');

    if (titleEl) titleEl.textContent = req.title || 'WhenBound Request';
    if (descEl) descEl.textContent = req.description || 'Mark your availability below to coordinate our next team milestone.';
    if (rangeEl) rangeEl.textContent = pollDateLabel(req);

    if (deadlineWrap && deadlineEl) {
      if (req.deadline) {
        deadlineWrap.style.display = 'inline-flex';
        deadlineEl.textContent = formatShortDate(req.deadline);
      } else {
        deadlineWrap.style.display = 'none';
      }
    }

    if (targetCohort) {
      targetCohort.textContent = req.assign_to_all ? 'All Cohorts' : (req.cohort ? `Cohort` : 'Your Cohort');
    }

    if (statusPill) {
      if (req.is_completed) {
        statusPill.textContent = '✓ Submitted';
        statusPill.className = 'w2m-status-pill completed';
      } else {
        statusPill.textContent = 'Pending';
        statusPill.className = 'w2m-status-pill';
      }
    }

    const selectorWrap = document.getElementById('w2mSelectorWrap');
    const selectEl = document.getElementById('w2mSelectRequest');
    if (selectorWrap && selectEl) {
      if (activeMeetingRequests.length > 1) {
        selectorWrap.style.display = 'flex';
        selectEl.innerHTML = activeMeetingRequests.map(r => `
          <option value="${recordId(r.id) || ''}" ${r.id === currentRequestId ? 'selected' : ''}>
            ${escapeHtml(r.title)} (${escapeHtml(pollDateLabel(r))})
          </option>
        `).join('');

        selectEl.onchange = (e) => {
          const newId = parseInt(e.target.value, 10);
          if (newId && newId !== currentRequestId) {
            currentRequestId = newId;
            currentRequestData = activeMeetingRequests.find(r => r.id === currentRequestId);
            renderRequestBanner();
            loadUserAvailabilityGrid();
            loadGroupAvailabilityGrid();
          }
        };
      } else {
        selectorWrap.style.display = 'none';
      }
    }
  }

  function loadUserAvailabilityGrid() {
    const gridEl = document.getElementById('myAvailabilityGrid');
    if (!gridEl) return;

    availabilityLoadedFor = null;
    availabilitySaveStatus.textContent = '';
    availabilitySaveStatus.classList.remove('is-error');
    gridEl.textContent = 'Loading your availability…';
    const requestedId = currentRequestId;
    const editVersion = availabilityEditVersion;
    let url = '/api/meetings/';
    if (currentRequestId) {
      url += `?request_id=${currentRequestId}`;
    }

    fetch(url)
      .then(readJsonResponse)
      .then(data => {
        if (requestedId !== currentRequestId || editVersion !== availabilityEditVersion) return;
        availabilityLoadedFor = requestedId;
        userSlotsMap = {};
        const slots = Array.isArray(data) ? data : (data.results || []);
        slots.forEach(s => {
          if (s.date) {
            userSlotsMap[`${s.date}_${s.hour}`] = s.is_available;
          } else {
            userSlotsMap[`${s.day_of_week}_${s.hour}`] = s.is_available;
          }
        });
        renderUserGrid();
      })
      .catch(error => {
        if (requestedId === currentRequestId) { gridEl.textContent = error.message || 'Could not load availability. Please refresh.'; }
      });
  }

  function renderAvailabilityBands(dates, startHour, endHour, renderCell) {
    const bands = availabilityDateBands(dates, availabilityDayCapacity);
    const dayColumns = Math.max(...bands.map(band => band.length));
    return bands.map(band => {
      const first = band[0];
      const last = band.at(-1);
      const firstDate = `${first.monthName} ${first.dayNum}`;
      const dateRange = first === last ? firstDate : `${firstDate} – ${last.monthName} ${last.dayNum}`;
      let html = `
        <div class="availability-date-band">
          <div class="availability-band-heading">${escapeHtml(dateRange)}</div>
          <div class="availability-grid-container" style="--availability-date-columns: ${dayColumns};">
            <div class="grid-header-cell"></div>
      `;

      band.forEach(date => {
        html += `
          <div class="grid-header-cell${date.isToday ? ' today-header" aria-current="date' : ''}">
            <div class="grid-header-day">${escapeHtml(date.dayName)}${date.isToday ? ' <span aria-hidden="true">•</span>' : ''}</div>
            <div class="grid-header-date">${escapeHtml(date.monthName)} ${escapeHtml(date.dayNum)}</div>
          </div>
        `;
      });

      for (let hour = startHour; hour < endHour; hour++) {
        const hourLabel = first.hours?.[hour - startHour] || String(hour);
        html += `<div class="grid-time-label">${escapeHtml(hourLabel)}</div>`;
        band.forEach(date => { html += renderCell(date, hour); });
      }

      html += `</div></div>`;
      return html;
    }).join('');
  }

  function renderUserGrid() {
    const gridEl = availabilityGrid;
    if (!gridEl) return;

    const dates = (currentDates && currentDates.length > 0) ? currentDates : getFallbackWeekDayDates();
    const startH = currentStartHour ?? 9;
    const endH = currentEndHour ?? 18;

    const activeElement = document.activeElement;
    const focusedSlot = gridEl.contains(activeElement) && activeElement.matches('[data-slot]');
    const previousSlot = focusedSlot ? activeElement : gridEl.querySelector('[data-slot][tabindex="0"]');
    gridEl.innerHTML = renderAvailabilityBands(dates, startH, endH, (date, hour) => {
      const slotKey = date.date ? `${date.date}_${hour}` : `${date.dayOfWeek}_${hour}`;
      const isAvail = !!userSlotsMap[slotKey];
      const day = dates.indexOf(date);
      const localHour = date.hours?.[hour - startH] || `${hour}:00`;
      const label = `${date.dayName}, ${date.monthName} ${date.dayNum}, ${localHour}`;
      return `
        <button type="button" class="grid-cell ${isAvail ? 'active' : ''} ${date.isToday ? 'today-cell' : ''}"
                data-slot data-day-index="${day}" data-slot-label="${escapeHtml(label)}"
                data-date="${escapeHtml(date.date || '')}" data-day="${escapeHtml(date.dayOfWeek)}" data-hour="${hour}"
                aria-label="${escapeHtml(label)}" aria-pressed="${isAvail}" tabindex="${day === 0 && hour === startH ? 0 : -1}"></button>
      `;
    });
    if (previousSlot) {
      const { dayIndex, hour } = previousSlot.dataset;
      const slot = gridEl.querySelector(`[data-slot][data-day-index="${dayIndex}"][data-hour="${hour}"]`);
      if (slot) {
        setSlotTabStop(slot);
        if (focusedSlot) slot.focus({ preventScroll: true });
      }
    }
    loadAvailabilityConflictEvents(dates);
  }

  function resizeAvailabilityCalendars() {
    const width = availabilityGrid.clientWidth;
    if (!width || paintingAvailability) return;
    const sizes = getComputedStyle(availabilityGrid);
    const timeWidth = parseFloat(sizes.getPropertyValue('--availability-time-width'));
    const dayWidth = parseFloat(sizes.getPropertyValue('--availability-day-min'));
    const gap = parseFloat(sizes.getPropertyValue('--availability-column-gap'));
    const capacity = Math.max(1, Math.min(7, Math.floor((width - timeWidth) / (dayWidth + gap))));
    if (capacity === availabilityDayCapacity) return;
    availabilityDayCapacity = capacity;
    if (currentRequestId && availabilityLoadedFor === currentRequestId) renderUserGrid();
    if (groupAvailability?.requestId === currentRequestId) {
      renderGroupGrid(groupAvailability.matrix, groupAvailability.totalMembers);
    }
  }
  new ResizeObserver(resizeAvailabilityCalendars).observe(availabilityGrid);

  function getAvailabilityTimezone() {
    return document.getElementById('tzSelect')?.value || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  }

  function makeAvailabilityConflictKey(dates) {
    const validDates = dates.filter(date => date.date);
    if (!validDates.length) return null;
    return `${currentRequestId || 'availability'}:${validDates[0].date}:${validDates[validDates.length - 1].date}:${getAvailabilityTimezone()}`;
  }

  function shiftIsoDate(dateString, days) {
    const date = new Date(`${dateString}T00:00:00Z`);
    date.setUTCDate(date.getUTCDate() + days);
    return date.toISOString();
  }

  function zonedDateAndMinute(instant, timeZone) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).formatToParts(instant);
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return {
      date: `${values.year}-${values.month}-${values.day}`,
      minute: Number(values.hour) * 60 + Number(values.minute)
    };
  }

  function eventConflictsWithSlot(event, slotDate, hour, timeZone) {
    if (event.transparency === 'transparent' || !event.start) return false;
    if (event.start.date) {
      const lastIncludedDate = event.end?.date || shiftIsoDate(event.start.date, 1).slice(0, 10);
      return slotDate >= event.start.date && slotDate < lastIncludedDate;
    }
    if (!event.start.dateTime) return false;

    try {
      const startInstant = new Date(event.start.dateTime);
      const endInstant = event.end?.dateTime ? new Date(event.end.dateTime) : new Date(startInstant.getTime() + 60 * 60 * 1000);
      if (Number.isNaN(startInstant.getTime()) || Number.isNaN(endInstant.getTime())) return false;
      const start = zonedDateAndMinute(startInstant, timeZone);
      const end = zonedDateAndMinute(endInstant, timeZone);
      const slotStart = hour * 60;
      const slotEnd = slotStart + 60;

      if (start.date === end.date) {
        return slotDate === start.date && start.minute < slotEnd && end.minute > slotStart;
      }
      if (slotDate > start.date && slotDate < end.date) return true;
      if (slotDate === start.date) return start.minute < slotEnd;
      if (slotDate === end.date) return end.minute > slotStart;
    } catch (_) {
      return false;
    }
    return false;
  }

  function applyAvailabilityConflictHighlights(events, dates, timeZone) {
    const gridEl = document.getElementById('myAvailabilityGrid');
    if (!gridEl) return;

    gridEl.querySelectorAll('.grid-cell').forEach(cell => {
      const conflicts = events.filter(event => eventConflictsWithSlot(
        event, cell.dataset.date, Number(cell.dataset.hour), timeZone
      ));
      cell.classList.toggle('calendar-conflict', conflicts.length > 0);
      if (conflicts.length) {
        const titles = [...new Set(conflicts.map(event => event.summary || 'Calendar event'))];
        cell.title = `Calendar conflict: ${titles.join('; ')}`;
        cell.setAttribute('aria-label', `${cell.dataset.slotLabel}. Conflicts with ${titles.join(', ')}`);
      } else {
        cell.removeAttribute('title');
        cell.setAttribute('aria-label', cell.dataset.slotLabel);
      }
    });
  }

  function loadAvailabilityConflictEvents(dates) {
    if (!googleIntegrationsEnabled) return;
    const validDates = dates.filter(date => date.date);
    const key = makeAvailabilityConflictKey(validDates);
    if (!key) return;
    const timeZone = 'America/Monterrey';
    const statusEl = document.getElementById('calendarConflictStatus');

    if (availabilityConflictCache.key === key) {
      applyAvailabilityConflictHighlights(availabilityConflictCache.events, validDates, timeZone);
      if (statusEl) statusEl.textContent = '';
      return;
    }

    if (availabilityConflictPending && availabilityConflictPending.key === key) return;

    const firstDate = validDates[0].date;
    const lastDate = validDates[validDates.length - 1].date;
    const request = {
      timeMin: shiftIsoDate(firstDate, -1),
      timeMax: shiftIsoDate(lastDate, 2)
    };
    if (statusEl) statusEl.textContent = '';

    const promise = requestCalendarEvents(request)
      .then(events => ({ events, error: null }))
      .catch(error => ({ events: [], error }));
    availabilityConflictPending = { key, promise };

    promise.then(result => {
      if (availabilityConflictPending && availabilityConflictPending.key === key) {
        availabilityConflictPending = null;
        if (!result.error) availabilityConflictCache = { key, events: result.events };
      }

      if (makeAvailabilityConflictKey(currentDates) !== key) return;
      if (result.error) {
        if (statusEl) statusEl.textContent = `Calendar conflict check failed: ${result.error.message}`;
        return;
      }
      if (statusEl) statusEl.textContent = '';
      applyAvailabilityConflictHighlights(result.events, validDates, timeZone);
    });
  }

  function setSlotTabStop(cell) {
    const previous = availabilityGrid.querySelector('[data-slot][tabindex="0"]');
    if (previous && previous !== cell) previous.tabIndex = -1;
    cell.tabIndex = 0;
  }

  function toggleCellState(cell, newState) {
    if ((cell.getAttribute('aria-pressed') === 'true') === newState) return;
    const { date, day, hour } = cell.dataset;
    availabilityEditVersion++;
    cell.classList.toggle('active', newState);
    cell.setAttribute('aria-pressed', String(newState));
    userSlotsMap[`${date || day}_${hour}`] = newState;
  }

  availabilityGrid.addEventListener('focusin', event => {
    if (event.target.matches('[data-slot]')) setSlotTabStop(event.target);
  });
  availabilityGrid.addEventListener('keydown', event => {
    const cell = event.target.closest('[data-slot]');
    if (!cell) return;
    const dates = currentDates.length ? currentDates : getFallbackWeekDayDates();
    const target = adjacentAvailabilitySlot(
      event.key, Number(cell.dataset.dayIndex), Number(cell.dataset.hour),
      dates.length, currentStartHour ?? 9, currentEndHour ?? 18
    );
    if (!target) return;
    event.preventDefault();
    availabilityGrid.querySelector(
      `[data-slot][data-day-index="${target.day}"][data-hour="${target.hour}"]`
    )?.focus();
  });
  availabilityGrid.addEventListener('pointerdown', event => {
    skipMouseClick = false;
    const cell = event.target.closest('[data-slot]');
    if (!cell || event.pointerType !== 'mouse' || event.button !== 0) return;
    paintingAvailability = true;
    skipMouseClick = true;
    dragTargetState = cell.getAttribute('aria-pressed') !== 'true';
    toggleCellState(cell, dragTargetState);
  });
  availabilityGrid.addEventListener('pointerover', event => {
    const cell = event.target.closest('[data-slot]');
    if (paintingAvailability && cell && event.pointerType === 'mouse') toggleCellState(cell, dragTargetState);
  });
  availabilityGrid.addEventListener('click', event => {
    const cell = event.target.closest('[data-slot]');
    // Mouse clicks were handled during drag. Keyboard and touch use native activation.
    if (!cell || (event.detail > 0 && skipMouseClick)) return;
    setSlotTabStop(cell);
    toggleCellState(cell, cell.getAttribute('aria-pressed') !== 'true');
    saveUserAvailability();
  });
  function finishAvailabilityStroke() {
    if (!paintingAvailability) return;
    paintingAvailability = false;
    saveUserAvailability();
    resizeAvailabilityCalendars();
  }
  window.addEventListener('pointerup', finishAvailabilityStroke);
  window.addEventListener('pointercancel', finishAvailabilityStroke);

  function saveUserAvailability(showToast = false) {
    if (!currentRequestId || availabilityLoadedFor !== currentRequestId) return;
    const savedRequestId = currentRequestId;
    const savedVersion = availabilityEditVersion;
    const dates = (currentDates && currentDates.length > 0) ? currentDates : getFallbackWeekDayDates();
    const startH = currentStartHour ?? 9;
    const endH = currentEndHour ?? 18;

    const slots = [];
    dates.forEach(d => {
      for (let h = startH; h < endH; h++) {
        const slotKey = d.date ? `${d.date}_${h}` : `${d.dayOfWeek}_${h}`;
        slots.push({
          date: d.date || null,
          day_of_week: d.dayOfWeek,
          hour: h,
          is_available: !!userSlotsMap[slotKey]
        });
      }
    });

    const payload = { slots };
    if (currentRequestId) {
      payload.request_id = currentRequestId;
    }

    availabilitySaveStatus.classList.remove('is-error');
    availabilitySaveStatus.textContent = 'Saving…';
    availabilitySaveQueue = availabilitySaveQueue.catch(() => {}).then(() => fetch('/api/meetings/bulk-save/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
      body: JSON.stringify(payload)
    })).then(readJsonResponse).then(data => {
      if (savedRequestId !== currentRequestId || savedVersion !== availabilityEditVersion) return;
      if (data.is_completed !== true) throw new Error('The server did not confirm your submission. Please try again.');
      if (currentRequestData) currentRequestData.is_completed = true;
      const statusPill = document.getElementById('w2mStatusPill');
      if (statusPill) { statusPill.textContent = '✓ Submitted'; statusPill.className = 'w2m-status-pill completed'; }
      availabilitySaveStatus.textContent = 'Saved';
      loadGroupAvailabilityGrid();
    }).catch(error => {
      if (savedRequestId !== currentRequestId || savedVersion !== availabilityEditVersion) return;
      availabilitySaveStatus.classList.add('is-error');
      availabilitySaveStatus.textContent = `${error.message || 'Unable to save.'} Select Save to retry.`;
      const statusPill = document.getElementById('w2mStatusPill');
      if (statusPill) { statusPill.textContent = 'Unsaved changes'; statusPill.className = 'w2m-status-pill'; }
    });
    return availabilitySaveQueue;
  }

  function loadGroupAvailabilityGrid() {
    const gridEl = document.getElementById('groupAvailabilityGrid');
    if (!gridEl) return;

    const requestedId = currentRequestId;
    if (groupAvailability?.requestId !== requestedId) {
      groupAvailability = null;
      gridEl.textContent = 'Loading group availability…';
    }
    const tz = document.getElementById('tzSelect')?.value || 'America/Monterrey';
    let url = `/api/meetings/group-availability/?timezone=${encodeURIComponent(tz)}`;
    if (currentRequestId) {
      url += `&request_id=${currentRequestId}`;
    }

    fetch(url)
      .then(readJsonResponse)
      .then(data => {
        if (requestedId !== currentRequestId) return;
        if (data.status === 'success') {
          if (data.start_hour !== undefined) currentStartHour = data.start_hour;
          if (data.end_hour !== undefined) currentEndHour = data.end_hour;

          groupAvailability = { requestId: requestedId, matrix: data.matrix, totalMembers: data.total_members };
          renderGroupGrid(data.matrix, data.total_members);
        }
      }).catch(error => {
        if (requestedId === currentRequestId) {
          groupAvailability = null;
          gridEl.textContent = error.message || 'Could not load group availability.';
        }
      });
  }

  function renderGroupGrid(matrix, totalMembers) {
    const gridEl = document.getElementById('groupAvailabilityGrid');
    if (!gridEl) return;

    const dates = (currentDates && currentDates.length > 0) ? currentDates : getFallbackWeekDayDates();
    const startH = currentStartHour ?? 9;
    const endH = currentEndHour ?? 18;

    const matrixMap = {};
    (Array.isArray(matrix) ? matrix : []).forEach(m => {
      const key = m.date ? `${m.date}_${m.hour}` : `${m.day_of_week}_${m.hour}`;
      matrixMap[key] = m;
    });

    const rawAccent = getComputedStyle(document.body).getPropertyValue('--accent-rgb').trim();
    const accentRgb = /^\d{1,3},\s*\d{1,3},\s*\d{1,3}$/.test(rawAccent) ? rawAccent : '0, 180, 216';
    gridEl.innerHTML = renderAvailabilityBands(dates, startH, endH, (date, hour) => {
      const slotKey = date.date ? `${date.date}_${hour}` : `${date.dayOfWeek}_${hour}`;
      const info = matrixMap[slotKey] || { available_count: 0, available_members: [] };
      const count = Math.max(0, Number(info.available_count) || 0);
      const ratio = totalMembers > 0 ? Math.min(1, count / totalMembers) : 0;

      let alpha = 0.05;
      if (ratio > 0) alpha = 0.25 + 0.75 * ratio;
      const bgStyle = `background-color: rgba(${accentRgb}, ${alpha.toFixed(2)});`;
      const textStyle = ratio > 0.5 ? 'color: #ffffff;' : 'color: var(--ink);';
      const isGroupEvent = !!info.group_event;

      let tooltipText = `${count} of ${totalMembers} free`;
      if (info.available_members && info.available_members.length > 0) {
        tooltipText += `: ${info.available_members.join(', ')}`;
      }
      if (isGroupEvent) tooltipText += ` | Event: ${info.group_event}`;

      return `
        <div class="grid-cell group-cell ${isGroupEvent ? 'group-event-cell' : ''} ${date.isToday ? 'today-cell' : ''}"
             style="${bgStyle} ${textStyle}">
          ${count > 0 ? count : ''}
          <div class="grid-cell-tooltip">${escapeHtml(tooltipText)}</div>
        </div>
      `;
    });
  }

  const btnSyncCalendar = document.getElementById('btnSyncGoogleCalendar');
  if (btnSyncCalendar && googleIntegrationsEnabled) {
    btnSyncCalendar.addEventListener('click', () => {
      const tz = document.getElementById('tzSelect')?.value || 'America/Monterrey';
      btnSyncCalendar.disabled = true;
      btnSyncCalendar.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Syncing...`;

      const payload = { timezone: tz };
      if (currentRequestId) {
        payload.request_id = currentRequestId;
      }

      fetch('/api/meetings/sync-google/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrftoken
        },
        body: JSON.stringify(payload)
      })
        .then(readJsonResponse)
        .then(data => {
          btnSyncCalendar.disabled = false;
          btnSyncCalendar.innerHTML = `<i class="fa-brands fa-google"></i> Sync with Google Calendar`;
          if (data.connected && data.status === 'success') {
            loadMeetingHub(currentRequestId);
          } else {
            alert(data.detail || 'Failed to sync calendar.');
          }
        })
        .catch(() => {
          btnSyncCalendar.disabled = false;
          btnSyncCalendar.innerHTML = `<i class="fa-brands fa-google"></i> Sync with Google Calendar`;
          alert('Error syncing with Google Calendar.');
        });
    });
  }

  const btnSubmitAvail = document.getElementById('btnSubmitAvailability');
  if (btnSubmitAvail) {
    btnSubmitAvail.addEventListener('click', () => {
      saveUserAvailability(true);
    });
  }

  const btnClearMy = document.getElementById('btnClearMyAvailability');
  if (btnClearMy) {
    btnClearMy.addEventListener('click', () => {
      if (availabilityLoadedFor !== currentRequestId) return;
      availabilityEditVersion++;
      userSlotsMap = {};
      renderUserGrid();
      saveUserAvailability();
    });
  }

  const btnRefreshGroup = document.getElementById('btnRefreshGroupAvailability');
  if (btnRefreshGroup) {
    btnRefreshGroup.addEventListener('click', () => loadGroupAvailabilityGrid());
  }

  const tzSelect = document.getElementById('tzSelect');
  const settingsTimezone = document.getElementById('settingsTimezone');
  const timezoneControls = [tzSelect, settingsTimezone].filter(Boolean);
  const timezoneFeedback = [
    document.getElementById('meetingTimezoneStatus'),
    document.getElementById('settingsTimezoneStatus'),
  ].filter(Boolean);
  let meetingTimezone = tzSelect?.value || settingsTimezone?.value || 'America/Monterrey';

  timezoneControls.forEach(control => {
    control.addEventListener('change', async () => {
      const selected = control.value;
      timezoneControls.forEach(select => { select.disabled = true; });
      timezoneFeedback.forEach(status => { status.textContent = 'Saving meeting time zone…'; });
      try {
        const response = await fetch('/api/dashboard/preferences/', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
          body: JSON.stringify({ meeting_timezone: selected }),
        });
        const data = await readJsonResponse(response);
        meetingTimezone = data.meeting_timezone;
        document.querySelectorAll('[data-meeting-time]').forEach(element => {
          const options = {
            month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
            timeZone: meetingTimezone, timeZoneName: 'short',
          };
          if (element.dataset.meetingTime !== 'short') options.weekday = 'short';
          element.textContent = new Intl.DateTimeFormat('en-US', options).format(new Date(element.dateTime));
        });
        timezoneFeedback.forEach(status => { status.textContent = 'Meeting time zone saved.'; });
      } catch (error) {
        timezoneFeedback.forEach(status => { status.textContent = error.message; });
      } finally {
        timezoneControls.forEach(select => {
          select.value = meetingTimezone;
          select.disabled = false;
        });
      }
      if (document.getElementById('view-meetings')?.classList.contains('active')) {
        loadMeetingHub(currentRequestId);
      }
    });
  });

  /* ---------- Milestones & Achievements Controller ---------- */
  function loadBadges() {
    const gridEl = document.getElementById('badgesGrid');
    if (!gridEl) return;

    gridEl.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading milestones...</div>`;

    fetch('/api/badges/')
      .then(readJsonResponse)
      .then(data => {
        if (data.status === 'success') {
          const numEl = document.getElementById('bannerRingNumber');
          const totalEl = document.getElementById('bannerRingTotal');
          const titleEl = document.getElementById('bannerLevelTitle');
          const subEl = document.getElementById('bannerLevelSub');
          const fillEl = document.getElementById('bannerProgressFill');

          if (numEl) numEl.textContent = data.earned_count;
          if (totalEl) totalEl.textContent = data.total_count;
          if (titleEl) titleEl.textContent = data.level_title;
          if (subEl) subEl.textContent = `You've earned ${data.earned_count} badges and ${data.xp_points} XP. Complete milestones to unlock new ranks.`;

          const pct = data.total_count > 0 ? Math.round((data.earned_count / data.total_count) * 100) : 0;
          if (fillEl) {
            fillEl.style.width = `${pct}%`;
            document.getElementById('milestoneProgress').setAttribute('aria-valuenow', String(pct));
          }

          if (!data.badges || data.badges.length === 0) {
            gridEl.innerHTML = `<div class="empty-state">No milestones found.</div>`;
            return;
          }

          gridEl.innerHTML = data.badges.map(b => {
            let iconMarkup = `<i class="fa-solid ${safeIcon(b.icon_class)}"></i>`;
            if (b.has_custom_icon && recordId(b.id)) {
              iconMarkup = `<img src="/dashboard/badges/${b.id}/icon.png" alt="">`;
            } else if (/^[a-z-]+$/.test(b.artwork || '')) {
              iconMarkup = `<span class="badge-art badge-art-${b.artwork}" aria-hidden="true"></span>`;
            }
            if (b.earned) {
              return `
                <div class="badge-card earned">
                  <div class="badge-icon-rail">
                    <div class="badge-icon-circle" style="background-color: ${safeColor(b.color)};">
                      ${iconMarkup}
                    </div>
                  </div>
                  <div class="badge-copy">
                    <div class="badge-title">${escapeHtml(b.name)}</div>
                    <div class="badge-desc">${escapeHtml(b.description)}</div>
                  </div>
                  <div class="badge-progress-column"><div class="badge-status-pill earned"><i class="fa-solid fa-check"></i> EARNED</div></div>
                </div>
              `;
            } else if (b.progress > 0) {
              return `
                <div class="badge-card unearned">
                  <div class="badge-icon-rail">
                    <div class="badge-icon-circle">
                      ${iconMarkup}
                    </div>
                  </div>
                  <div class="badge-copy">
                    <div class="badge-title">${escapeHtml(b.name)}</div>
                    <div class="badge-desc">${escapeHtml(b.description)}</div>
                  </div>
                  <div class="badge-progress-column">
                    <div class="badge-progress-wrap">
                      <div class="badge-progress-bar">
                        <div class="badge-progress-fill" style="width: ${percentage(b.progress)}%;"></div>
                      </div>
                      <div class="badge-progress-text">${percentage(b.progress)}% COMPLETE</div>
                    </div>
                  </div>
                </div>
              `;
            } else {
              return `
                <div class="badge-card unearned">
                  <div class="badge-icon-rail">
                    <div class="badge-icon-circle">
                      ${iconMarkup}
                    </div>
                  </div>
                  <div class="badge-copy">
                    <div class="badge-title">${escapeHtml(b.name)}</div>
                    <div class="badge-desc">${escapeHtml(b.description)}</div>
                  </div>
                  <div class="badge-progress-column"><div class="badge-status-pill locked"><i class="fa-solid fa-lock"></i> LOCKED</div></div>
                </div>
              `;
            }
          }).join('');
        } else {
          gridEl.innerHTML = `<div class="error-state">Unable to load milestones.</div>`;
        }
      })
      .catch(() => {
        gridEl.innerHTML = `<div class="error-state">Error loading milestones.</div>`;
      });
  }

  /* Initial Load on Page Startup */
  if (document.getElementById('view-drive')?.classList.contains('active')) {
    window.showView('drive', false);
  } else {
    refreshWorkspace();
  }
});
