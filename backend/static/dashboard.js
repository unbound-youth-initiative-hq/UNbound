/* ===== UNbound Fellow Dashboard Complete JS ===== */
document.addEventListener('DOMContentLoaded', () => {
  'use strict';

  /* ---------- CSRF Token Helper ---------- */
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  const csrftoken = getCookie('csrftoken');

  /* ---------- Persisted dashboard accent ---------- */
  const accentChoices = Array.from(document.querySelectorAll('[data-accent-choice]'));
  const accentStatus = document.getElementById('accentSaveStatus');
  const accentModal = document.getElementById('dashboardPreferencesModal');
  const validAccents = ['ocean', 'sky', 'coral', 'violet', 'mint', 'forest', 'rose', 'amber'];

  function setAccentPalette(palette) {
    if (!validAccents.includes(palette)) return;
    document.body.dataset.accent = palette;
    accentChoices.forEach(choice => {
      choice.setAttribute('aria-pressed', String(choice.dataset.accentChoice === palette));
    });
  }

  function closeAccentModal() {
    if (!accentModal) return;
    accentModal.classList.remove('active');
    accentModal.setAttribute('aria-hidden', 'true');
  }

  setAccentPalette(document.body.dataset.accent || 'ocean');

  const openAccentButton = document.getElementById('openDashboardPreferences');
  const closeAccentButton = document.getElementById('closeDashboardPreferences');
  if (openAccentButton && accentModal) {
    openAccentButton.addEventListener('click', () => {
      const sidebar = document.getElementById('sidebar');
      if (sidebar) sidebar.classList.remove('open');
      accentModal.classList.add('active');
      accentModal.setAttribute('aria-hidden', 'false');
      const selected = accentModal.querySelector('[aria-pressed="true"]');
      if (selected) selected.focus();
    });
  }
  if (closeAccentButton) closeAccentButton.addEventListener('click', closeAccentModal);
  if (accentModal) {
    accentModal.addEventListener('click', event => {
      if (event.target === accentModal) closeAccentModal();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && accentModal.classList.contains('active')) closeAccentModal();
    });
  }

  accentChoices.forEach(choice => {
    choice.addEventListener('click', () => {
      const palette = choice.dataset.accentChoice;
      const previousPalette = document.body.dataset.accent || 'ocean';
      if (!validAccents.includes(palette) || palette === previousPalette) return;

      setAccentPalette(palette);
      if (accentStatus) accentStatus.textContent = 'Saving your color…';
      accentChoices.forEach(button => { button.disabled = true; });

      fetch('/api/dashboard/preferences/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
        body: JSON.stringify({ accent_palette: palette })
      })
        .then(response => response.json().then(data => ({ response, data })))
        .then(({ response, data }) => {
          if (!response.ok || data.status !== 'success') throw new Error(data.detail || 'Unable to save preference.');
          if (accentStatus) accentStatus.textContent = 'Color saved to your profile.';
        })
        .catch(() => {
          setAccentPalette(previousPalette);
          if (accentStatus) accentStatus.textContent = 'Could not save the color. Your previous choice was restored.';
        })
        .finally(() => accentChoices.forEach(button => { button.disabled = false; }));
    });
  });

  /* ---------- Navigation / View Switcher ---------- */
  window.showView = function (name) {
    document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
    document.querySelectorAll('.sb-nav .nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === name));
    const sb = document.getElementById('sidebar');
    if (sb) sb.classList.remove('open');

    if (name === 'overview') {
      refreshWorkspace();
    } else if (name === 'drive') {
      loadPersonalFiles();
      loadSharedFiles();
    } else if (name === 'tasks') {
      loadTasks();
    } else if (name === 'calendar') {
      loadCalendar('calendarEvents');
    } else if (name === 'meetings') {
      loadCalendar('calendarEvents');
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
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          const fnEl = document.getElementById('dashFirstName');
          const cNameEl = document.getElementById('dashCohortName');
          const cPhaseEl = document.getElementById('dashCurrentPhase');
          const projEl = document.getElementById('dashProjectName');
          const bannerPhaseEl = document.getElementById('dashBannerPhase');
          const chapterEl = document.getElementById('dashChapter');

          if (fnEl) fnEl.textContent = data.first_name;
          if (cNameEl) cNameEl.textContent = data.cohort_name;
          if (cPhaseEl) cPhaseEl.textContent = data.current_phase;
          if (projEl) projEl.textContent = data.project_name;
          if (bannerPhaseEl) bannerPhaseEl.textContent = data.current_phase;
          if (chapterEl) chapterEl.textContent = data.chapter;

          document.getElementById('dashOpenTasks').textContent = data.stats.open_tasks;
          document.getElementById('dashCompletedTasks').textContent = data.stats.completed_tasks;
          document.getElementById('dashBadgesEarned').textContent = data.stats.earned_badges;
          document.getElementById('dashBadgesTotal').textContent = data.stats.total_badges;
          document.getElementById('dashLevelName').textContent = data.stats.level_name;
          document.getElementById('dashCompletionPct').textContent = `${data.stats.completion_pct}%`;
          document.getElementById('dashCompletionFill').style.width = `${data.stats.completion_pct}%`;

          // Render Google Profile Pictures
          renderTeamAvatars(data.team_members);

          // Render Cohort's Selected UN Goals (SDGs)
          renderSdgPills(data.sdgs);

          // Highlight Active Phase Step
          highlightPhaseStep(data.current_phase);

          // Render Next Up Calendar Events
          loadNextUpEvents();
        }
      });
  }

  function renderSdgPills(sdgs) {
    const container = document.getElementById('dashSdgPills');
    if (!container) return;

    if (!sdgs || sdgs.length === 0) {
      container.innerHTML = `<div class="empty-state">No SDGs selected for this cohort yet. Click "Edit SDGs" to choose goals.</div>`;
      return;
    }

    container.innerHTML = sdgs.map(s => `
      <div class="sdg-pill" style="--sdg-color: ${s.color || '#00B4D8'};">
        <span class="sdg-num">${s.code}</span> ${s.name}
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
      .then(res => res.json())
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
             style="--picker-color: ${s.color || '#00B4D8'};" 
             data-code="${s.code}">
          <span class="sdg-picker-num">${s.code}</span>
          <span class="sdg-picker-name">${s.name}</span>
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
      .then(res => res.json())
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
      container.innerHTML = `<div class="team-avatar-circle">F</div>`;
      return;
    }

    const maxDisplay = 4;
    const visible = members.slice(0, maxDisplay);
    const remaining = members.length - maxDisplay;

    let html = visible.map(m => {
      if (m.picture) {
        return `<div class="team-avatar-circle" title="${m.name} (${m.role})">
                  <img src="${m.picture}" alt="${m.name}" referrerpolicy="no-referrer" />
                </div>`;
      } else {
        return `<div class="team-avatar-circle" title="${m.name} (${m.role})">${m.initials}</div>`;
      }
    }).join('');

    if (remaining > 0) {
      html += `<div class="team-avatar-circle more-circle" title="${remaining} more team members">+${remaining}</div>`;
    }

    container.innerHTML = html;
  }

  function highlightPhaseStep(currentPhase) {
    const steps = document.querySelectorAll('.phase-step');
    let reachedActive = false;

    steps.forEach(step => {
      const pName = step.getAttribute('data-phase');
      if (pName.toLowerCase() === currentPhase.toLowerCase()) {
        step.className = 'phase-step active';
        reachedActive = true;
      } else if (!reachedActive) {
        step.className = 'phase-step completed';
      } else {
        step.className = 'phase-step';
      }
    });
  }

  function requestCalendarEvents(range = null) {
    let url = '/api/google/calendar/';
    if (range) {
      const params = new URLSearchParams({ time_min: range.timeMin, time_max: range.timeMax });
      url += `?${params.toString()}`;
    }

    return fetch(url)
      .then(response => response.json().then(data => ({ response, data })))
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
    const listEl = document.getElementById('dashNextUpList');
    if (!listEl) return;
    setCalendarMessage(listEl, 'Loading upcoming events…', 'loading');

    requestCalendarEvents()
      .then(events => renderCalendarEvents(listEl, events, true))
      .catch(error => setCalendarMessage(listEl, error.message || 'Could not load calendar events.', 'error'));
  }

  window.loadCalendar = function (targetId = 'calendarEvents') {
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
      .then(res => res.json())
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
    if (taskGroup.length === 0) {
      containerEl.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
      return;
    }

    containerEl.innerHTML = taskGroup.map(t => {
      const iconClass = t.icon || (t.scope === 'team' ? 'fa-pen-to-square' : 'fa-check');
      const boxColor = t.color || (t.scope === 'team' ? '#00B4D8' : '#e0a009');
      const isUnbound = t.source === 'unbound';

      return `
        <div class="proto-task-card ${t.status === 'complete' ? 'completed' : ''}">
          <div class="proto-task-icon-box" style="background-color: ${boxColor};">
            <i class="fa-solid ${iconClass}"></i>
          </div>
          <div class="proto-task-content">
            ${isUnbound ? `<div class="source-badge"><i class="fa-solid fa-globe"></i> ASSIGNED BY UNBOUND</div>` : ''}
            <div class="proto-task-title">${t.title}</div>
            ${t.description ? `<div class="proto-task-desc">${t.description}</div>` : ''}
            ${t.availability_request_id || (t.title && t.title.toLowerCase().includes('when2meet')) ? `
              <button class="btn btn-ghost btn-open-w2m-task" type="button" onclick="openWhenToMeet(${t.availability_request_id || ''})">
                <i class="fa-solid fa-calendar-check" style="color: var(--accent);"></i> Open When to Meet
              </button>
            ` : ''}
          </div>
          <div class="proto-task-actions">
            <select class="status-select-pill ${t.status}" onchange="updateTaskStatus(${t.id}, this.value)">
              <option value="pending" ${t.status === 'pending' ? 'selected' : ''}>Pending</option>
              <option value="in_progress" ${t.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
              <option value="complete" ${t.status === 'complete' ? 'selected' : ''}>Completed</option>
            </select>
            <button class="task-delete" title="Delete Task" onclick="deleteTask(${t.id})">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      `;
    }).join('');
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
      .then(res => res.json())
      .then(() => {
        loadTasks();
      })
      .catch(() => alert('Failed to update task status.'));
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

  const teamForm = document.getElementById('teamTaskForm');
  if (teamForm) {
    teamForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const input = document.getElementById('inputTeamTaskTitle');
      const title = input.value.trim();
      if (!title) return;

      fetch('/api/tasks/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrftoken
        },
        body: JSON.stringify({ title, scope: 'team', icon: 'fa-pen-to-square', color: '#00B4D8' })
      })
        .then(res => res.json())
        .then(() => {
          input.value = '';
          loadTasks();
        });
    });
  }

  const personalForm = document.getElementById('personalTaskForm');
  if (personalForm) {
    personalForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const input = document.getElementById('inputPersonalTaskTitle');
      const title = input.value.trim();
      if (!title) return;

      fetch('/api/tasks/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrftoken
        },
        body: JSON.stringify({ title, scope: 'personal', icon: 'fa-user-check', color: '#e0a009' })
      })
        .then(res => res.json())
        .then(() => {
          input.value = '';
          loadTasks();
        });
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
          <a href="${file.webViewLink || '#'}" target="_blank" class="file-name" title="${file.name}">
            ${file.name}
          </a>
          <span class="file-meta">
            ${isFolder ? 'Folder' : ownerName} • Modified ${modified}
          </span>
        </div>
      </div>
      <div class="file-actions">
        ${isFolder && isPersonal ? `<button class="btn btn-sm btn-ghost btn-subfolder" data-folder-id="${file.id}" data-folder-name="${file.name}"><i class="fa-solid fa-folder-open"></i> Open</button>` : ''}
        <a href="${file.webViewLink || '#'}" target="_blank" class="btn btn-sm btn-ghost" title="Open in Google Drive">
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
    if (!personalFileList) return;
    personalFileList.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Fetching personal files...</div>`;

    let url = '/api/google-drive/personal-files/';
    if (folderId) {
      url += `?folder_id=${encodeURIComponent(folderId)}`;
    }

    fetch(url)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success' || data.connected) {
          if (data.selected_folder_name) {
            personalFolderStatus.innerHTML = `<i class="fa-solid fa-folder"></i> ${data.selected_folder_name}`;
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
    if (!sharedFileList) return;
    sharedFileList.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Fetching shared workspace files...</div>`;

    fetch('/api/google-drive/shared-files/')
      .then(res => res.json())
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
    if (!folderSelectList) return;
    folderSelectList.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Fetching your Drive folders...</div>`;

    fetch('/api/google-drive/folders/')
      .then(res => res.json())
      .then(data => {
        folderSelectList.innerHTML = '';
        if ((data.status === 'success' || data.connected) && data.folders && data.folders.length > 0) {
          data.folders.forEach(folder => {
            const div = document.createElement('div');
            div.className = 'folder-select-item';
            div.innerHTML = `
              <div class="folder-select-info">
                <i class="fa-solid fa-folder"></i>
                <span>${folder.name}</span>
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
    fetch('/api/google-drive/set-folder/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify({ folder_id: folderId, folder_name: folderName })
    })
      .then(res => res.json())
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
        <span class="breadcrumb-item active"><i class="fa-solid fa-folder-open"></i> ${folderName}</span>
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

  /* ---------- Meeting Hub Controller (When to Meet) ---------- */
  let activeMeetingRequests = [];
  let currentRequestId = null;
  let currentRequestData = null;
  let currentDates = [];
  let currentStartHour = 9;
  let currentEndHour = 18;
  let availabilityConflictCache = { key: null, events: [] };
  let availabilityConflictPending = null;
  let userSlotsMap = {};
  let isMouseDown = false;
  let dragTargetState = null;

  window.openWhenToMeet = function (requestId = null) {
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
      .then(res => res.json())
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
      .catch(() => {
        loadUserAvailabilityGrid();
        loadGroupAvailabilityGrid();
      });
  }

  function renderRequestBanner() {
    if (!currentRequestData) return;
    const req = currentRequestData;

    const titleEl = document.getElementById('w2mRequestTitle');
    const descEl = document.getElementById('w2mRequestDesc');
    const rangeEl = document.getElementById('w2mDateRange');
    const deadlineWrap = document.getElementById('w2mDeadlineWrap');
    const deadlineEl = document.getElementById('w2mDeadline');
    const statusPill = document.getElementById('w2mStatusPill');
    const targetCohort = document.getElementById('w2mTargetCohort');

    if (titleEl) titleEl.textContent = req.title || 'When to Meet Request';
    if (descEl) descEl.textContent = req.description || 'Mark your availability below to coordinate our next team milestone.';
    if (rangeEl) rangeEl.textContent = `${formatShortDate(req.start_date)} – ${formatShortDate(req.end_date)}`;

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
          <option value="${r.id}" ${r.id === currentRequestId ? 'selected' : ''}>
            ${r.title} (${formatShortDate(r.start_date)} - ${formatShortDate(r.end_date)})
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

    let url = '/api/meetings/';
    if (currentRequestId) {
      url += `?request_id=${currentRequestId}`;
    }

    fetch(url)
      .then(res => res.json())
      .then(data => {
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
      .catch(() => {
        renderUserGrid();
      });
  }

  function renderAvailabilityWeeks(dates, startHour, endHour, renderCell) {
    const weeks = [];
    for (let index = 0; index < dates.length; index += 7) {
      weeks.push(dates.slice(index, index + 7));
    }

    return weeks.map((week, weekIndex) => {
      const first = week[0];
      const last = week[week.length - 1];
      let html = `
        <div class="availability-week-block">
          <div class="availability-week-heading">${first.monthName} ${first.dayNum} – ${last.monthName} ${last.dayNum}</div>
          <div class="availability-grid-container" style="grid-template-columns: 52px repeat(${week.length}, minmax(42px, 1fr));">
            <div class="grid-header-cell"></div>
      `;

      week.forEach(date => {
        html += `
          <div class="grid-header-cell ${date.isToday ? 'today-header' : ''}">
            <div class="grid-header-day">${date.dayName} ${date.isToday ? '•' : ''}</div>
            <div class="grid-header-date">${date.monthName} ${date.dayNum}</div>
          </div>
        `;
      });

      for (let hour = startHour; hour < endHour; hour++) {
        const hourLabel = hour > 12 ? `${hour - 12} PM` : (hour === 12 ? '12 PM' : `${hour} AM`);
        html += `<div class="grid-time-label">${hourLabel}</div>`;
        week.forEach(date => { html += renderCell(date, hour); });
      }

      html += `</div></div>`;
      return html;
    }).join('');
  }

  function renderUserGrid() {
    const gridEl = document.getElementById('myAvailabilityGrid');
    if (!gridEl) return;

    const dates = (currentDates && currentDates.length > 0) ? currentDates : getFallbackWeekDayDates();
    const startH = currentStartHour || 9;
    const endH = currentEndHour || 18;

    gridEl.innerHTML = renderAvailabilityWeeks(dates, startH, endH, (date, hour) => {
      const slotKey = date.date ? `${date.date}_${hour}` : `${date.dayOfWeek}_${hour}`;
      const isAvail = !!userSlotsMap[slotKey];
      return `
        <div class="grid-cell ${isAvail ? 'active' : ''} ${date.isToday ? 'today-cell' : ''}"
             data-date="${date.date || ''}" data-day="${date.dayOfWeek}" data-hour="${hour}"></div>
      `;
    });

    attachGridEvents();
    loadAvailabilityConflictEvents(dates);
  }

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
        cell.setAttribute('aria-label', `Availability slot ${cell.dataset.date} at ${cell.dataset.hour}:00 conflicts with ${titles.join(', ')}`);
      } else {
        cell.removeAttribute('title');
        cell.removeAttribute('aria-label');
      }
    });
  }

  function loadAvailabilityConflictEvents(dates) {
    const validDates = dates.filter(date => date.date);
    const key = makeAvailabilityConflictKey(validDates);
    if (!key) return;
    const timeZone = getAvailabilityTimezone();
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

  function attachGridEvents() {
    const cells = document.querySelectorAll('#myAvailabilityGrid .grid-cell');

    cells.forEach(cell => {
      cell.addEventListener('mousedown', (e) => {
        e.preventDefault();
        isMouseDown = true;
        const date = cell.dataset.date;
        const day = cell.dataset.day;
        const hour = cell.dataset.hour;
        const currentState = cell.classList.contains('active');
        dragTargetState = !currentState;
        toggleCellState(cell, date, day, hour, dragTargetState);
      });

      cell.addEventListener('mouseenter', () => {
        if (isMouseDown) {
          const date = cell.dataset.date;
          const day = cell.dataset.day;
          const hour = cell.dataset.hour;
          toggleCellState(cell, date, day, hour, dragTargetState);
        }
      });
    });

    window.addEventListener('mouseup', () => {
      if (isMouseDown) {
        isMouseDown = false;
        saveUserAvailability();
      }
    });
  }

  function toggleCellState(cell, date, day, hour, newState) {
    cell.classList.toggle('active', newState);
    if (date) {
      userSlotsMap[`${date}_${hour}`] = newState;
    } else {
      userSlotsMap[`${day}_${hour}`] = newState;
    }
  }

  function saveUserAvailability(showToast = false) {
    const dates = (currentDates && currentDates.length > 0) ? currentDates : getFallbackWeekDayDates();
    const startH = currentStartHour || 9;
    const endH = currentEndHour || 18;

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

    fetch('/api/meetings/bulk-save/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify(payload)
    })
      .then(res => res.json())
      .then(data => {
        loadGroupAvailabilityGrid();

        const hasActive = Object.values(userSlotsMap).some(Boolean);
        const statusPill = document.getElementById('w2mStatusPill');
        if (statusPill && hasActive) {
          statusPill.textContent = '✓ Submitted';
          statusPill.className = 'w2m-status-pill completed';
        }

        const toast = document.getElementById('w2mSaveToast');
        if (toast) {
          toast.style.display = 'inline-flex';
          toast.innerHTML = `<i class="fa-solid fa-circle-check"></i> Saved & Task Updated!`;
          setTimeout(() => {
            toast.style.display = 'none';
          }, 2600);
        }
      });
  }

  function loadGroupAvailabilityGrid() {
    const gridEl = document.getElementById('groupAvailabilityGrid');
    if (!gridEl) return;

    const tz = document.getElementById('tzSelect')?.value || 'America/Monterrey';
    let url = `/api/meetings/group-availability/?timezone=${encodeURIComponent(tz)}`;
    if (currentRequestId) {
      url += `&request_id=${currentRequestId}`;
    }

    fetch(url)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          if (data.dates && data.dates.length > 0) {
            currentDates = data.dates;
          }
          if (data.start_hour) currentStartHour = data.start_hour;
          if (data.end_hour) currentEndHour = data.end_hour;

          renderGroupGrid(data.matrix, data.total_members);
          renderUserGrid();
        }
      });
  }

  function renderGroupGrid(matrix, totalMembers) {
    const gridEl = document.getElementById('groupAvailabilityGrid');
    if (!gridEl) return;

    const dates = (currentDates && currentDates.length > 0) ? currentDates : getFallbackWeekDayDates();
    const startH = currentStartHour || 9;
    const endH = currentEndHour || 18;

    const matrixMap = {};
    (Array.isArray(matrix) ? matrix : []).forEach(m => {
      const key = m.date ? `${m.date}_${m.hour}` : `${m.day_of_week}_${m.hour}`;
      matrixMap[key] = m;
    });

    const accentRgb = getComputedStyle(document.body).getPropertyValue('--accent-rgb').trim() || '0, 180, 216';
    gridEl.innerHTML = renderAvailabilityWeeks(dates, startH, endH, (date, hour) => {
      const slotKey = date.date ? `${date.date}_${hour}` : `${date.dayOfWeek}_${hour}`;
      const info = matrixMap[slotKey] || { available_count: 0, available_members: [] };
      const count = info.available_count;
      const ratio = totalMembers > 0 ? count / totalMembers : 0;

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
          <div class="grid-cell-tooltip">${tooltipText}</div>
        </div>
      `;
    });
  }

  const btnSyncCalendar = document.getElementById('btnSyncGoogleCalendar');
  if (btnSyncCalendar) {
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
        .then(res => res.json())
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
  if (tzSelect) {
    tzSelect.addEventListener('change', () => loadMeetingHub(currentRequestId));
  }

  /* ---------- Milestones & Achievements Controller ---------- */
  function loadBadges() {
    const gridEl = document.getElementById('badgesGrid');
    if (!gridEl) return;

    gridEl.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading milestones...</div>`;

    fetch('/api/badges/')
      .then(res => res.json())
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
          if (fillEl) fillEl.style.width = `${pct}%`;

          if (!data.badges || data.badges.length === 0) {
            gridEl.innerHTML = `<div class="empty-state">No milestones found.</div>`;
            return;
          }

          gridEl.innerHTML = data.badges.map(b => {
            if (b.earned) {
              return `
                <div class="badge-card earned">
                  <div class="badge-icon-rail">
                    <div class="badge-icon-circle" style="background-color: ${b.color || '#00B4D8'};">
                      <i class="fa-solid ${b.icon_class || 'fa-award'}"></i>
                    </div>
                  </div>
                  <div class="badge-copy">
                    <div class="badge-title">${b.name}</div>
                    <div class="badge-desc">${b.description}</div>
                  </div>
                  <div class="badge-progress-column"><div class="badge-status-pill earned"><i class="fa-solid fa-check"></i> EARNED</div></div>
                </div>
              `;
            } else if (b.progress > 0) {
              return `
                <div class="badge-card unearned">
                  <div class="badge-icon-rail">
                    <div class="badge-icon-circle">
                      <i class="fa-solid ${b.icon_class || 'fa-award'}"></i>
                    </div>
                  </div>
                  <div class="badge-copy">
                    <div class="badge-title">${b.name}</div>
                    <div class="badge-desc">${b.description}</div>
                  </div>
                  <div class="badge-progress-column">
                    <div class="badge-progress-wrap">
                      <div class="badge-progress-bar">
                        <div class="badge-progress-fill" style="width: ${b.progress}%;"></div>
                      </div>
                      <div class="badge-progress-text">${b.progress}% COMPLETE</div>
                    </div>
                  </div>
                </div>
              `;
            } else {
              return `
                <div class="badge-card unearned">
                  <div class="badge-icon-rail">
                    <div class="badge-icon-circle">
                      <i class="fa-solid ${b.icon_class || 'fa-award'}"></i>
                    </div>
                  </div>
                  <div class="badge-copy">
                    <div class="badge-title">${b.name}</div>
                    <div class="badge-desc">${b.description}</div>
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
  refreshWorkspace();
});
