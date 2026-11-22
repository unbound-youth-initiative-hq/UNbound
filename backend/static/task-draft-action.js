'use strict';

(() => {
  const button = document.querySelector('[data-task-draft-action]');
  if (!button) return;
  const form = button.form;
  const actions = form.querySelector('.actions');
  const select = actions?.querySelector('select[name="action"]');
  const selectedAction = select?.querySelector('option[value="prepare_selected_task_drafts"]');
  const run = actions?.querySelector('button[name="index"]');
  if (!selectedAction || !run) return;

  // Use the Django action for selection and its built-in cross-page behavior.
  selectedAction.hidden = true;
  if (!Array.from(select.options).some(option => option.value && option !== selectedAction)) {
    select.closest('label').classList.add('hidden');
    run.classList.add('hidden');
  }

  function hasSelection() {
    return Boolean(form.querySelector('input.action-select:checked'));
  }

  function updateLabel() {
    button.textContent = hasSelection() ? 'Email about selected tasks' : 'Email about overdue tasks';
  }

  form.addEventListener('change', event => {
    if (event.target.matches('input.action-select')) updateLabel();
  });
  form.addEventListener('click', event => {
    if (event.target.closest('#action-toggle, .actions .clear a')) updateLabel();
  });
  button.addEventListener('click', event => {
    if (hasSelection()) {
      event.preventDefault();
      select.value = selectedAction.value;
      run.click();
    }
  });
  window.addEventListener('pageshow', () => {
    if (select.value === selectedAction.value) select.value = '';
    updateLabel();
  });
  updateLabel();
})();
