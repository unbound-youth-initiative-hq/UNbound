'use strict';

document.addEventListener('DOMContentLoaded', () => {
  function initialize(root) {
    root.querySelectorAll('[data-resource-preview]').forEach(preview => {
      if (preview.closest('.empty-form')) return;
      const scope = preview.closest('.inline-related, form');
      const field = name => scope.querySelector(`[name="${name}"], [name$="-${name}"]`);
      const url = field('url');
      if (!url) return;

      const title = field('title');
      const description = field('description');
      const typeOverride = field('resource_type_override');
      const iconOverride = field('resource_icon_override');
      const options = JSON.parse(preview.querySelector('script').textContent);
      const rules = options.rules.map(([kind, hosts, pattern]) => [kind, hosts, new RegExp(pattern)]);
      const name = preview.querySelector('[data-resource-name]');
      const type = preview.querySelector('[data-resource-type]');
      const icon = preview.querySelector('[data-resource-icon]');
      const summary = preview.querySelector('[data-resource-description]');

      function inferredType() {
        let parsed;
        try {
          parsed = new URL(url.value.trim());
        } catch {
          return 'link';
        }
        const rule = rules.find(([, hosts, pattern]) => hosts.includes(parsed.hostname) && pattern.test(parsed.pathname));
        return rule?.[0] || 'website';
      }

      function update() {
        const kind = typeOverride.value || inferredType();
        name.textContent = title.value.trim() || 'Resource title';
        type.textContent = options.types[kind];
        icon.className = options.icons[iconOverride.value || options.defaults[kind]];
        summary.textContent = description.value.trim();
        summary.hidden = !summary.textContent;
      }

      [url, title, description, typeOverride, iconOverride].forEach(control => {
        control.addEventListener('input', update);
        control.addEventListener('change', update);
      });
      update();
    });
  }

  initialize(document);
  document.addEventListener('formset:added', event => initialize(event.target));
});
