'use strict';

(() => {
  const form = document.getElementById('changelist-form');
  const actions = form?.querySelector('.actions');
  const select = actions?.querySelector('select[name="action"]');
  const actionLabel = select?.closest('label');
  const run = actions?.querySelector('button[name="index"]');
  if (!actionLabel || !run) return;

  const buttons = document.createElement('span');
  buttons.style.display = 'inline-flex';
  buttons.style.flexWrap = 'wrap';
  buttons.style.gap = '8px';
  for (const option of select.options) {
    if (!option.value || option.disabled) continue;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button';
    button.textContent = option.textContent.trim();
    button.addEventListener('click', () => {
      select.value = option.value;
      run.click();
    });
    buttons.append(button);
  }
  if (!buttons.childElementCount) return;

  actions.insertBefore(buttons, actionLabel);
  // Keep Django's action form as a fallback and use its native submission path.
  actionLabel.classList.add('hidden');
  run.classList.add('hidden');

  function updateButtons() {
    const hasSelection = Boolean(form.querySelector('input.action-select:checked'));
    buttons.classList.toggle('hidden', !hasSelection);
  }

  form.addEventListener('change', event => {
    if (event.target.matches('input.action-select')) updateButtons();
  });
  form.addEventListener('click', event => {
    if (event.target.closest('#action-toggle, .actions .clear a')) updateButtons();
  });
  window.addEventListener('pageshow', updateButtons);
  updateButtons();
})();
