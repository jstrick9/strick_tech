/**
 * Kanban — card rendering must never inject user data as markup.
 *
 * Regression guard for a stored XSS. `task.agent` is fully user-controlled
 * (POST /api/tasks accepts any string for it). An unrecognised agent fell
 * through to `label: task.agent`, and that label was interpolated into BOTH
 * the title="" attribute and the card body WITHOUT escaping — while the task
 * title and description immediately beside it were correctly escaped.
 *
 * A task created with agent='"><img src=x onerror=alert(1)>' therefore stored
 * the payload and rendered it as live DOM on every board load. This test runs
 * the SHIPPED kanbanRenderCard against a real DOM and asserts no executable
 * element is produced.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { JSDOM } from 'jsdom';

const __dirname = dirname(fileURLToPath(import.meta.url));
const KANBAN_JS = readFileSync(resolve(__dirname, '../js/28-kanban.js'), 'utf-8');

let renderCard;
let dom;

beforeAll(() => {
  dom = new JSDOM('<!DOCTYPE html><div id="host"></div>');
  // Extract the shipped functions so the test exercises real code, not a copy.
  const priorities = KANBAN_JS.match(/const KANBAN_PRIORITIES[\s\S]*?\n};/);
  const agents = KANBAN_JS.match(/const KANBAN_AGENTS[\s\S]*?\n};/);
  const escHtml = KANBAN_JS.match(/function kanbanEscapeHtml[\s\S]*?\n}\n/);
  const escAttr = KANBAN_JS.match(/function kanbanEscapeAttr[\s\S]*?\n}\n/);
  const render = KANBAN_JS.match(/function kanbanRenderCard[\s\S]*?\n}\n/);
  for (const [name, m] of Object.entries({ priorities, agents, escHtml, escAttr, render })) {
    if (!m) throw new Error(`could not extract ${name} from 28-kanban.js`);
  }
  // eslint-disable-next-line no-new-func
  renderCard = new Function(
    'document',
    `${priorities[0]}\n${agents[0]}\n${escHtml[0]}\n${escAttr[0]}\n${render[0]}\nreturn kanbanRenderCard;`
  )(dom.window.document);
});

function renderInto(task) {
  const host = dom.window.document.getElementById('host');
  host.innerHTML = renderCard(task);
  return host;
}

const base = { id: 1, title: 'ok', description: '', priority: 'medium', agent: 'builder' };

describe('kanbanRenderCard escaping', () => {
  it('does not execute an <img onerror> payload supplied via agent', () => {
    const host = renderInto({ ...base, agent: '"><img src=x onerror=alert(1)>' });
    expect(host.querySelectorAll('img[onerror]')).toHaveLength(0);
    expect(host.querySelectorAll('img')).toHaveLength(0);
  });

  it('does not inject a <script> supplied via agent', () => {
    const host = renderInto({ ...base, agent: '<script>alert(1)</script>' });
    expect(host.querySelectorAll('script')).toHaveLength(0);
  });

  it('does not let agent break out of the title attribute', () => {
    const host = renderInto({ ...base, agent: '" onmouseover="alert(1)' });
    const el = host.querySelector('.kanban-card-agent');
    expect(el).not.toBeNull();
    expect(el.hasAttribute('onmouseover')).toBe(false);
  });

  it('still escapes title and description', () => {
    const host = renderInto({
      ...base,
      title: '<img src=x onerror=alert(1)>',
      description: '<script>alert(2)</script>',
    });
    expect(host.querySelectorAll('img')).toHaveLength(0);
    expect(host.querySelectorAll('script')).toHaveLength(0);
  });

  it('renders a malicious agent value as visible text, not markup', () => {
    const payload = '<b>bold</b>';
    const host = renderInto({ ...base, agent: payload });
    expect(host.querySelectorAll('b')).toHaveLength(0);
    expect(host.querySelector('.kanban-card-agent').textContent).toContain(payload);
  });

  it('still renders known agents with their icon and label', () => {
    const host = renderInto({ ...base, agent: 'builder' });
    const text = host.querySelector('.kanban-card-agent').textContent;
    expect(text).toContain('Builder');
    expect(text).toContain('⚡');
  });
});
