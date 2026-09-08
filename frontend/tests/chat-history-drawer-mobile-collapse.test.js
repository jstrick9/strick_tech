/**
 * #073 — Chat history drawer must default-collapse on mobile.
 *
 * `#chat-history-drawer` is a flex-shrink:0 child of the chat pane, shown at
 * 280px by default. On a phone-width viewport that shoved the message area down
 * to ~100px on first load, making chat unusable. The `#sidebar` is hidden on
 * mobile (`@media max-width:768px`) but the history drawer was not.
 *
 * Fix: default-collapse the drawer on mobile and auto-collapse/restore as the
 * viewport crosses the 768px breakpoint. Source-level regression tests.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/56-chat-history.js'), 'utf8');

describe('#073 chat history drawer collapses on mobile', () => {
  it('listens for the mobile breakpoint via matchMedia', () => {
    expect(SRC).toMatch(/matchMedia\s*\(\s*'\(max-width:\s*768px\)'\s*\)/);
  });

  it('collapses the drawer when entering phone width', () => {
    const block = SRC.slice(SRC.indexOf('isMobileQuery'), SRC.indexOf('isMobileQuery') + 1200);
    // On entering mobile it must call toggleChatHistoryDrawer when shown.
    expect(block).toMatch(/e\.matches/);
    expect(block).toMatch(/toggleChatHistoryDrawer/);
  });

  it('restores the drawer when returning to desktop width', () => {
    const block = SRC.slice(SRC.indexOf('onMobileChange'));
    expect(block).toMatch(/_autoCollapsed/);
    expect(block).toMatch(/e\.matches\s*===?\s*false|else\s*\{/);
    // must restore when crossing back over the breakpoint
    const restore = block.slice(block.indexOf('Leaving phone width'));
    expect(restore).toMatch(/toggleChatHistoryDrawer/);
  });
});
