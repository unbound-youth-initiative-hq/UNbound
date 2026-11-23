'use strict';

document.addEventListener('DOMContentLoaded', () => {
  const dates = document.getElementById('id_selected_dates');
  if (!dates) return;

  const controls = document.createElement('p');
  const picker = document.createElement('input');
  picker.type = 'date';
  picker.setAttribute('aria-label', 'Pick a meeting date');
  const add = document.createElement('button');
  add.type = 'button';
  add.className = 'button';
  add.textContent = 'Add date';
  const status = document.createElement('span');
  status.setAttribute('role', 'status');
  controls.append(picker, ' ', add, ' ', status);
  dates.before(controls);

  add.addEventListener('click', () => {
    if (!picker.value) {
      status.textContent = 'Choose a date first.';
      picker.focus();
      return;
    }
    const selected = dates.value.trim() ? dates.value.trim().split(/\s+/) : [];
    if (selected.includes(picker.value)) {
      status.textContent = 'That date is already listed.';
      return;
    }
    selected.push(picker.value);
    dates.value = selected.sort().join('\n');
    status.textContent = `Added ${picker.value}.`;
    picker.value = '';
    picker.focus();
  });
});
