document.querySelectorAll('[data-email-draft]').forEach(draft => {
  const subject = draft.querySelector('[data-draft-subject]');
  const body = draft.querySelector('[data-draft-body]');
  const open = draft.querySelector('[data-draft-open]');
  const recipientLink = open.getAttribute('href').split('?')[0];
  const copy = draft.querySelector('[data-draft-copy]');
  const status = draft.querySelector('[data-draft-status]');

  function updateLink() {
    const text = body.value.replace(/\r?\n/g, '\r\n');
    open.href = `${recipientLink}?subject=${encodeURIComponent(subject.value)}&body=${encodeURIComponent(text)}`;
  }

  subject.addEventListener('input', updateLink);
  body.addEventListener('input', updateLink);
  if (navigator.clipboard) {
    copy.hidden = false;
    copy.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(body.value);
        status.textContent = 'Message copied.';
      } catch {
        body.select();
        status.textContent = 'Select and copy the message manually.';
      }
    });
  }
});
