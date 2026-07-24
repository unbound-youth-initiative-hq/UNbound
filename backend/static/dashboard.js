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

  function loadNextUpEvents() {
    const listEl = document.getElementById('dashNextUpList');
    if (!listEl) return;

    fetch('/api/google/calendar/')
      .then(res => res.json())
      .then(data => {
        if (data.connected && data.events && data.events.length > 0) {
          listEl.innerHTML = data.events.slice(0, 2).map(ev => {
            const startDate = ev.start.dateTime || ev.start.date;
            const d = new Date(startDate);
            const month = d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
            const day = d.getDate();
            const timeStr = ev.start.dateTime ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'All Day';

            return `
              <div class="nextup-item">
                <div class="nextup-date-box">${month}<br/>${day}</div>
                <div class="nextup-info">
                  <div class="nextup-title">${ev.summary || 'Cohort Sync'}</div>
                  <div class="nextup-meta">${timeStr} ${ev.location ? '• ' + ev.location : ''}</div>
                </div>
              </div>
            `;
          }).join('');
        } else {
          listEl.innerHTML = `
            <div class="nextup-item">
              <div class="nextup-date-box">JUN<br/>14</div>
              <div class="nextup-info">
                <div class="nextup-title">Cohort Sync — Prototype Review</div>
                <div class="nextup-meta">Sat · 4:00 PM CT · Zoom</div>
              </div>
            </div>
            <div class="nextup-item">
              <div class="nextup-date-box">JUN<br/>18</div>
              <div class="nextup-info">
                <div class="nextup-title">Mentor 1:1 — Diego N.</div>
                <div class="nextup-meta">Wed · 6:30 PM CT</div>
              </div>
            </div>
          `;
        }
      })
      .catch(() => {
        listEl.innerHTML = `
          <div class="nextup-item">
            <div class="nextup-date-box">JUN<br/>14</div>
            <div class="nextup-info">
              <div class="nextup-title">Cohort Sync — Prototype Review</div>
              <div class="nextup-meta">Sat · 4:00 PM CT · Zoom</div>
            </div>
          </div>
        `;
      });
  }

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

  /* ---------- Meeting Hub Controller ---------- */
  let userSlotsMap = {};
  let isMouseDown = false;
  let dragTargetState = null;

  function getWeekDayDates() {
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

      weekDates.push({
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

  function loadMeetingHub() {
    loadUserAvailabilityGrid();
    loadGroupAvailabilityGrid();
  }

  function loadUserAvailabilityGrid() {
    const gridEl = document.getElementById('myAvailabilityGrid');
    if (!gridEl) return;

    fetch('/api/meetings/')
      .then(res => res.json())
      .then(data => {
        userSlotsMap = {};
        const slots = Array.isArray(data) ? data : (data.results || []);
        slots.forEach(s => {
          userSlotsMap[`${s.day_of_week}_${s.hour}`] = s.is_available;
        });
        renderUserGrid();
      })
      .catch(() => {
        renderUserGrid();
      });
  }

  function renderUserGrid() {
    const gridEl = document.getElementById('myAvailabilityGrid');
    if (!gridEl) return;

    const weekDates = getWeekDayDates();
    let html = `<div class="availability-grid-container">`;

    html += `<div class="grid-header-cell"></div>`;
    weekDates.forEach(d => {
      html += `
        <div class="grid-header-cell ${d.isToday ? 'today-header' : ''}">
          <div class="grid-header-day">${d.dayName} ${d.isToday ? '•' : ''}</div>
          <div class="grid-header-date">${d.monthName} ${d.dayNum}</div>
        </div>
      `;
    });

    for (let h = 9; h <= 17; h++) {
      const hourLabel = h > 12 ? `${h - 12} PM` : (h === 12 ? '12 PM' : `${h} AM`);
      html += `<div class="grid-time-label">${hourLabel}</div>`;

      weekDates.forEach(d => {
        const isAvail = !!userSlotsMap[`${d.dayOfWeek}_${h}`];
        html += `
          <div class="grid-cell ${isAvail ? 'active' : ''} ${d.isToday ? 'today-cell' : ''}" 
               data-day="${d.dayOfWeek}" 
               data-hour="${h}">
          </div>
        `;
      });
    }

    html += `</div>`;
    gridEl.innerHTML = html;

    attachGridEvents();
  }

  function attachGridEvents() {
    const cells = document.querySelectorAll('#myAvailabilityGrid .grid-cell');

    cells.forEach(cell => {
      cell.addEventListener('mousedown', (e) => {
        e.preventDefault();
        isMouseDown = true;
        const day = cell.dataset.day;
        const hour = cell.dataset.hour;
        const currentState = cell.classList.contains('active');
        dragTargetState = !currentState;
        toggleCellState(cell, day, hour, dragTargetState);
      });

      cell.addEventListener('mouseenter', () => {
        if (isMouseDown) {
          const day = cell.dataset.day;
          const hour = cell.dataset.hour;
          toggleCellState(cell, day, hour, dragTargetState);
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

  function toggleCellState(cell, day, hour, newState) {
    cell.classList.toggle('active', newState);
    userSlotsMap[`${day}_${hour}`] = newState;
  }

  function saveUserAvailability() {
    const slots = [];
    for (let d = 0; d < 7; d++) {
      for (let h = 9; h <= 17; h++) {
        slots.push({
          day_of_week: d,
          hour: h,
          is_available: !!userSlotsMap[`${d}_${h}`]
        });
      }
    }

    fetch('/api/meetings/bulk-save/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify({ slots })
    })
      .then(res => res.json())
      .then(() => {
        loadGroupAvailabilityGrid();
      });
  }

  function loadGroupAvailabilityGrid() {
    const gridEl = document.getElementById('groupAvailabilityGrid');
    if (!gridEl) return;

    const tz = document.getElementById('tzSelect')?.value || 'America/Monterrey';

    fetch(`/api/meetings/group-availability/?timezone=${encodeURIComponent(tz)}`)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          renderGroupGrid(data.matrix, data.total_members);
        }
      });
  }

  function renderGroupGrid(matrix, totalMembers) {
    const gridEl = document.getElementById('groupAvailabilityGrid');
    if (!gridEl) return;

    const weekDates = getWeekDayDates();
    const matrixMap = {};
    matrix.forEach(m => {
      matrixMap[`${m.day_of_week}_${m.hour}`] = m;
    });

    let html = `<div class="availability-grid-container">`;

    html += `<div class="grid-header-cell"></div>`;
    weekDates.forEach(d => {
      html += `
        <div class="grid-header-cell ${d.isToday ? 'today-header' : ''}">
          <div class="grid-header-day">${d.dayName} ${d.isToday ? '•' : ''}</div>
          <div class="grid-header-date">${d.monthName} ${d.dayNum}</div>
        </div>
      `;
    });

    for (let h = 9; h <= 17; h++) {
      const hourLabel = h > 12 ? `${h - 12} PM` : (h === 12 ? '12 PM' : `${h} AM`);
      html += `<div class="grid-time-label">${hourLabel}</div>`;

      weekDates.forEach(d => {
        const info = matrixMap[`${d.dayOfWeek}_${h}`] || { available_count: 0, available_members: [] };
        const count = info.available_count;
        const ratio = totalMembers > 0 ? count / totalMembers : 0;

        let alpha = 0.05;
        if (ratio > 0) {
          alpha = 0.25 + 0.75 * ratio;
        }

        const bgStyle = `background-color: rgba(0, 180, 216, ${alpha.toFixed(2)});`;
        const textStyle = ratio > 0.5 ? 'color: #ffffff;' : 'color: var(--ink);';
        const isGroupEvent = !!info.group_event;

        let tooltipText = `${count} of ${totalMembers} free`;
        if (info.available_members && info.available_members.length > 0) {
          tooltipText += `: ${info.available_members.join(', ')}`;
        }
        if (isGroupEvent) {
          tooltipText += ` | Event: ${info.group_event}`;
        }

        html += `
          <div class="grid-cell group-cell ${isGroupEvent ? 'group-event-cell' : ''} ${d.isToday ? 'today-cell' : ''}" 
               style="${bgStyle} ${textStyle}">
            ${count > 0 ? count : ''}
            <div class="grid-cell-tooltip">${tooltipText}</div>
          </div>
        `;
      });
    }

    html += `</div>`;
    gridEl.innerHTML = html;
  }

  const btnSyncCalendar = document.getElementById('btnSyncGoogleCalendar');
  if (btnSyncCalendar) {
    btnSyncCalendar.addEventListener('click', () => {
      const tz = document.getElementById('tzSelect')?.value || 'America/Monterrey';
      btnSyncCalendar.disabled = true;
      btnSyncCalendar.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Syncing...`;

      fetch('/api/meetings/sync-google/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrftoken
        },
        body: JSON.stringify({ timezone: tz })
      })
        .then(res => res.json())
        .then(data => {
          btnSyncCalendar.disabled = false;
          btnSyncCalendar.innerHTML = `<i class="fa-brands fa-google"></i> Sync with Google Calendar`;
          if (data.connected && data.status === 'success') {
            loadMeetingHub();
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
    tzSelect.addEventListener('change', () => loadMeetingHub());
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
                  <div class="badge-icon-circle" style="background-color: ${b.color || '#00B4D8'};">
                    <i class="fa-solid ${b.icon_class || 'fa-award'}"></i>
                  </div>
                  <div class="badge-title">${b.name}</div>
                  <div class="badge-desc">${b.description}</div>
                  <div class="badge-status-pill earned"><i class="fa-solid fa-check"></i> EARNED</div>
                </div>
              `;
            } else if (b.progress > 0) {
              return `
                <div class="badge-card unearned">
                  <div class="badge-icon-circle">
                    <i class="fa-solid ${b.icon_class || 'fa-award'}"></i>
                  </div>
                  <div class="badge-title">${b.name}</div>
                  <div class="badge-desc">${b.description}</div>
                  <div class="badge-progress-wrap">
                    <div class="badge-progress-bar">
                      <div class="badge-progress-fill" style="width: ${b.progress}%;"></div>
                    </div>
                    <div class="badge-progress-text">${b.progress}% COMPLETE</div>
                  </div>
                </div>
              `;
            } else {
              return `
                <div class="badge-card unearned">
                  <div class="badge-icon-circle">
                    <i class="fa-solid ${b.icon_class || 'fa-award'}"></i>
                  </div>
                  <div class="badge-title">${b.name}</div>
                  <div class="badge-desc">${b.description}</div>
                  <div class="badge-status-pill locked"><i class="fa-solid fa-lock"></i> LOCKED</div>
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