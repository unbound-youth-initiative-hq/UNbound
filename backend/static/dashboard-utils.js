/* Shared rendering and HTTP boundaries; also loaded by the Node regression tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.UNboundUI = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
  }

  function safeUrl(value, fallback = '#') {
    try {
      const url = new URL(String(value));
      return url.protocol === 'https:' && !url.username && !url.password ? url.href : fallback;
    } catch (_) { return fallback; }
  }

  function safeColor(value, fallback = '#00B4D8') {
    return /^#[0-9a-f]{3}(?:[0-9a-f]{3})?$/i.test(String(value)) ? value : fallback;
  }

  function taskIconForeground(color) {
    const rgb = safeColor(color).slice(1);
    const hex = rgb.length === 3 ? [...rgb].map(c => c + c).join('') : rgb;
    const [r, g, b] = hex.match(/../g).map(pair => {
      const value = parseInt(pair, 16) / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.179 ? '#000000' : '#ffffff';
  }

  function safeIcon(value, fallback = 'fa-award') {
    return /^fa-[a-z0-9-]+$/.test(String(value)) ? value : fallback;
  }

  function percentage(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : 0;
  }

  function recordId(value) {
    const number = Number(value);
    return Number.isSafeInteger(number) && number > 0 ? number : null;
  }

  async function readJsonResponse(response) {
    if (response.status === 204 && response.ok) return {};
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error('The server returned an unexpected response. Please try again.'); }
    if (!response.ok || data?.status === 'error') {
      let message = typeof data?.detail === 'string' ? data.detail : '';
      if (!message && data && typeof data === 'object') {
        message = Object.entries(data).filter(([, value]) => Array.isArray(value))
          .map(([field, errors]) => `${field}: ${errors.join(' ')}`).join(' ');
      }
      throw new Error(message || 'The request could not be saved. Please try again.');
    }
    return data;
  }

  function taskCardsMarkup(tasks, emptyMessage) {
    if (!tasks.length) return `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
    return tasks.map(task => {
      const id = recordId(task.id);
      if (!id) return '';
      const requestId = recordId(task.availability_request_id);
      const status = ['pending', 'in_progress', 'complete'].includes(task.status) ? task.status : 'pending';
      const label = { pending: 'Pending', in_progress: 'In Progress', complete: 'Completed' }[status];
      const team = task.scope === 'team';
      const color = safeColor(task.color, team ? '#00B4D8' : '#e0a009');
      const icon = safeIcon(task.icon, team ? 'fa-pen-to-square' : 'fa-check');
      return `<div class="proto-task-card ${status === 'complete' ? 'completed' : ''}">
        <div class="proto-task-icon-box" style="background-color: ${color}; color: ${taskIconForeground(color)};"><i class="fa-solid ${icon}"></i></div>
        <div class="proto-task-content">
          ${task.source === 'unbound' ? '<div class="source-badge"><i class="fa-solid fa-globe"></i> ASSIGNED BY UNBOUND</div>' : ''}
          <div class="proto-task-title">${escapeHtml(task.title)}</div>
          ${task.description ? `<div class="proto-task-desc">${escapeHtml(task.description)}</div>` : ''}
          ${task.due_date ? `<div class="proto-task-desc">Due ${escapeHtml(task.due_date)}${task.due_time ? ` · ${formatTaskTime(task.due_time)}` : ''}</div>` : ''}
          ${task.can_edit === true ? `<button class="btn btn-ghost btn-sm task-deadline-edit" type="button" data-task-deadline-id="${id}" data-task-title="${escapeHtml(task.title)}" data-icon="${icon}" data-color="${color}" data-due-date="${escapeHtml(task.due_date || '')}" data-due-time="${escapeHtml(task.due_time || '')}">Edit task details</button>` : ''}
          ${requestId ? `<button class="btn btn-ghost btn-open-w2m-task" type="button" onclick="openWhenBound(${requestId})"><i class="fa-solid fa-calendar-check"></i> Open WhenBound</button>` : ''}
        </div>
        <div class="proto-task-actions">
          ${requestId || task.can_change_status === false ? `<span class="status-select-pill ${status}">${label}</span>` : `<select class="status-select-pill ${status}" aria-label="Status for ${escapeHtml(task.title)}" onchange="updateTaskStatus(${id}, this.value)">
            <option value="pending" ${status === 'pending' ? 'selected' : ''}>Pending</option>
            <option value="in_progress" ${status === 'in_progress' ? 'selected' : ''}>In Progress</option>
            <option value="complete" ${status === 'complete' ? 'selected' : ''}>Completed</option>
          </select>`}
          ${task.can_delete === true ? `<button class="task-delete" title="Delete Task" onclick="deleteTask(${id})"><i class="fa-solid fa-trash"></i></button>` : ''}
        </div>
      </div>`;
    }).join('');
  }

  function phaseRoadmapMarkup(phases, currentPhase) {
    if (!Array.isArray(phases) || !phases.length) return '<div class="empty-state">No fellowship phases configured yet.</div>';
    const active = phases.findIndex(phase => phase.name === currentPhase);
    return phases.map((phase, index) => `<div class="phase-step ${index === active ? 'active' : active >= 0 && index < active ? 'completed' : ''}">
      <div class="step-line"></div><div class="step-name">${escapeHtml(phase.name)}</div>
      <div class="step-sub">${escapeHtml(phase.description)}</div>
    </div>`).join('');
  }

  function formatTaskTime(value) {
    const time = /^([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d(?:\.\d+)?)?$/.exec(value || '');
    if (!time) return '';
    const hour = Number(time[1]);
    return `${hour % 12 || 12}:${time[2]} ${hour < 12 ? 'AM' : 'PM'} Monterrey time`;
  }

  function adjacentAvailabilitySlot(key, day, hour, days, firstHour, endHour) {
    switch (key) {
      case 'ArrowLeft': day -= 1; break;
      case 'ArrowRight': day += 1; break;
      case 'ArrowUp': hour -= 1; break;
      case 'ArrowDown': hour += 1; break;
      case 'Home': day = 0; break;
      case 'End': day = days - 1; break;
      default: return null;
    }
    return {
      day: Math.min(days - 1, Math.max(0, day)),
      hour: Math.min(endHour - 1, Math.max(firstHour, hour))
    };
  }

  function availabilityDateBands(dates, columnLimit) {
    const weeks = [];
    for (const date of dates) {
      const lastWeek = weeks.at(-1);
      // A daylight-saving transition can change the row labels midweek.
      if (!lastWeek || lastWeek.length === 7 || date.hours?.join() !== lastWeek[0].hours?.join()) {
        weeks.push([date]);
      } else {
        lastWeek.push(date);
      }
    }

    return weeks.flatMap(week => {
      const bands = [];
      let start = 0;
      // Share the dates evenly across the number of bands that fit.
      for (let remaining = Math.ceil(week.length / columnLimit); remaining > 0; remaining--) {
        const end = start + Math.ceil((week.length - start) / remaining);
        bands.push(week.slice(start, end));
        start = end;
      }
      return bands;
    });
  }

  return { taskIconForeground, escapeHtml, safeUrl, safeColor, safeIcon, percentage, recordId, readJsonResponse, taskCardsMarkup, phaseRoadmapMarkup, formatTaskTime, adjacentAvailabilitySlot, availabilityDateBands };
}));
