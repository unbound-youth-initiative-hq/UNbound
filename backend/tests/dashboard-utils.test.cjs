const test = require('node:test');
const assert = require('node:assert/strict');
const { taskCardsMarkup, phaseRoadmapMarkup, readJsonResponse, safeUrl, safeColor, safeIcon, percentage } = require('../static/dashboard-utils.js');

const task = { id: 12, title: 'Prepare notes', description: 'Team work', scope: 'team', status: 'pending', source: 'unbound' };

test('actual task renderer treats hostile task text as text and rejects attribute injection', () => {
  const html = taskCardsMarkup([{ ...task, title: '<img src=x onerror="alert(1)">', description: '</div><script>alert(1)</script>', icon: 'fa-check" onclick="alert(1)', color: 'red; background:url(javascript:alert(1))' }], '');
  assert.ok(!html.includes('<img'));
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'));
  assert.ok(html.includes('&lt;/div&gt;&lt;script&gt;'));
  assert.ok(!html.includes('background:url'));
  assert.ok(!html.includes('onclick="alert'));
});

test('assignment permissions keep completion while hiding unauthorized deletion', () => {
  const html = taskCardsMarkup([{ ...task, can_delete: false }], '');
  assert.ok(html.includes('updateTaskStatus(12'));
  assert.ok(!html.includes('deleteTask('));
  assert.ok(taskCardsMarkup([{ ...task, can_delete: true }], '').includes('deleteTask(12)'));
});

test('availability tasks are completed through Meeting Hub and respect status permission', () => {
  const html = taskCardsMarkup([{ ...task, availability_request_id: 9, can_change_status: false }], '');
  assert.ok(html.includes('openWhenToMeet(9)'));
  assert.ok(!html.includes('updateTaskStatus'));
  assert.ok(!taskCardsMarkup([{ ...task, can_change_status: false }], '').includes('updateTaskStatus'));
});

test('IDs and statuses cannot introduce script into event handlers or classes', () => {
  assert.equal(taskCardsMarkup([{ ...task, id: '12);alert(1)//' }], ''), '');
  const html = taskCardsMarkup([{ ...task, status: '\" onmouseover=alert(1)', availability_request_id: '9);alert(1)' }], '');
  assert.ok(!html.includes('onmouseover'));
  assert.ok(!html.includes('openWhenToMeet'));
});

test('dynamic phase names are escaped and an unknown current phase marks none completed', () => {
  const phases = [{ name: '<script>phase</script>', description: '<img src=x>' }, { name: 'Build', description: 'Test & learn' }];
  const html = phaseRoadmapMarkup(phases, 'unknown');
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('<img'));
  assert.ok(!html.includes('phase-step completed'));
  assert.ok(!html.includes('phase-step active'));
  assert.ok(phaseRoadmapMarkup(phases, 'Build').includes('phase-step completed'));
  assert.ok(phaseRoadmapMarkup([], '').includes('No fellowship phases'));
});

test('external URLs reject executable, relative and credential-bearing URLs', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,x', '//host/path', 'http://host/path', 'https://user:secret@host']) assert.equal(safeUrl(url), '#');
  assert.equal(safeUrl('https://drive.google.com/file/d/1'), 'https://drive.google.com/file/d/1');
});

test('style tokens are narrowly validated', () => {
  assert.equal(safeColor('#ff00aa'), '#ff00aa');
  assert.equal(safeColor('red;display:none'), '#00B4D8');
  assert.equal(safeIcon('fa-calendar-check'), 'fa-calendar-check');
  assert.equal(safeIcon('fa-check" onclick="x'), 'fa-award');
  assert.equal(percentage('NaN'), 0);
  assert.equal(percentage(200), 100);
});

test('HTTP rejection cannot flow into success feedback', async () => {
  let success = false;
  await assert.rejects(readJsonResponse({ ok: false, status: 400, json: async () => ({ detail: 'Invalid time range' }) }).then(() => { success = true; }), /Invalid time range/);
  assert.equal(success, false);
  await assert.rejects(readJsonResponse({ ok: false, status: 403, json: async () => ({ detail: 'Permission denied' }) }), /Permission denied/);
});

test('validation errors, invalid responses and successful empty deletes are handled', async () => {
  await assert.rejects(readJsonResponse({ ok: false, status: 400, json: async () => ({ title: ['Required.'] }) }), /title: Required/);
  await assert.rejects(readJsonResponse({ ok: false, status: 500, json: async () => { throw new Error('HTML'); } }), /unexpected response/);
  assert.deepEqual(await readJsonResponse({ ok: true, status: 204 }), {});
});

test('all-busy submission success is accepted independently of available slots', async () => {
  const data = { status: 'success', is_completed: true, slots: [{ is_available: false }] };
  assert.deepEqual(await readJsonResponse({ ok: true, status: 200, json: async () => data }), data);
});
