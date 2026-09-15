// Frontend failure honesty: a lazy pane chunk that fetches 200 but fails to
// parse — or a renderer that throws while drawing — used to leave a blank
// pane with no content, no error and no retry, just the nav chrome.
// Verified live by serving a corrupted chunk and a throwing renderer over
// the real routes: the pane showed a lone "?" help button and nothing else.
//
// The loader must now (a) treat a registry entry evaluating to exactly
// `false` as "renderer never installed" and show an error, (b) show an
// error when the renderer throws instead of only console.warn-ing.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'js', '00-chunk-loader.js'), 'utf8');

describe('chunk loader failure honesty', () => {
  it('still guards the 404 path with an error box and retry', () => {
    expect(SOURCE).toContain("if (!ok) { showError(pane); return; }");
    const showError = SOURCE.match(/function showError[\s\S]*?\n  \}/)[0];
    expect(showError).toContain('Could not load this section');
    expect(showError).toContain('Retry');
    expect(showError).toContain("window.nav(pane)");
  });

  it('detects a chunk that loaded but never installed its renderer', () => {
    // The registry idiom `typeof window.X === 'function' && window.X()`
    // evaluates to exactly false in that case; the wrapper must branch on it.
    const wrapper = SOURCE.match(/registry\[pane\] = function[\s\S]*?\n      \};/)[0];
    expect(wrapper).toContain('out === false');
    expect(wrapper.indexOf('out === false')).toBeGreaterThan(wrapper.indexOf('original.apply(self, args)'));
    expect(wrapper).toContain("showError(pane, 'broken')");
  });

  it('surfaces a renderer crash instead of only console.warn', () => {
    const wrapper = SOURCE.match(/registry\[pane\] = function[\s\S]*?\n      \};/)[0];
    const catchIdx = wrapper.indexOf('} catch (e) {');
    const warnIdx = wrapper.indexOf('console.warn');
    const errorIdx = wrapper.indexOf("showError(pane, 'crashed')");
    expect(catchIdx).toBeGreaterThan(-1);
    expect(warnIdx).toBeGreaterThan(catchIdx);
    expect(errorIdx).toBeGreaterThan(warnIdx);
  });

  it('guards the already-loaded re-navigation path too (retry path)', () => {
    // Retry in the error box calls nav(pane); for a chunk that "loaded" (so
    // failed[] is unset) the wrapper short-circuits to original.apply —
    // that path must not silently blank the pane either.
    const wrapper = SOURCE.match(/registry\[pane\] = function[\s\S]*?\n      \};/)[0];
    const shortCircuit = wrapper.slice(0, wrapper.indexOf('showPending(pane)'));
    expect(shortCircuit).toContain('quick === false');
    expect(shortCircuit).toContain("showError(pane, 'broken')");
    expect(shortCircuit).toContain("showError(pane, 'crashed')");
  });

  it('error copy acknowledges the failure and says data is safe', () => {
    const showError = SOURCE.match(/function showError[\s\S]*?\n  \}/)[0];
    expect(showError).toMatch(/could not start|went wrong|Could not load/);
    expect(showError).toMatch(/data is safe|connection/);
    expect(showError).toMatch(/try again/i);
  });

  it('the error and loading affordances are styled, not bare', () => {
    const css = fs.readFileSync(path.join(__dirname, '..', 'styles-system.css'), 'utf8');
    expect(css).toContain('.chunk-error');
    expect(css).toContain('.chunk-loading');
  });

  it('every lazy pane in the split plan has a registry entry to wrap', () => {
    const plan = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'scripts', 'split-plan.json'), 'utf8'));
    const registry = fs.readFileSync(path.join(__dirname, '..', 'js', '00-pane-registry.js'), 'utf8');
    for (const pane of Object.keys(plan.lazy)) {
      // eslint-disable-next-line no-loop-func
      const entry = new RegExp(`^\\s*'${pane}':`, 'm');
      expect(entry.test(registry), `pane '${pane}' has no MASTER_PANE_REGISTRY entry`).toBe(true);
    }
  });
});

describe('second door: masterNav18 direct renderer hooks', () => {
  const HOOKS = fs.readFileSync(path.join(__dirname, '..', 'js', '06-sprint-features.js'), 'utf8');

  it('exposes the chunk error affordance for other call sites', () => {
    expect(SOURCE).toContain('window.paneChunkError = function');
  });

  it('guards direct renderer calls instead of letting them escape nav()', () => {
    const fn = HOOKS.match(/function masterNav18[\s\S]*?\n  \};/)[0];
    expect(fn).toContain('SPRINT_HOOKS[pane]');
    expect(fn).toContain('} catch (e) {');
    expect(fn).toContain('window.paneChunkError(pane, \'crashed\')');
    // every pane it hooks is also in the registry (duplication is safe to
    // reason about: no pane depends on this hook alone)
    const registry = fs.readFileSync(path.join(__dirname, '..', 'js', '00-pane-registry.js'), 'utf8');
    const panes = [...fn.matchAll(/'([a-z0-9-]+)':\s+'render/g)].map(m => m[1]);
    expect(panes.length).toBeGreaterThanOrEqual(15);
    for (const pane of panes) {
      // eslint-disable-next-line no-loop-func
      expect(new RegExp(`^\\s*'${pane}':`, 'm').test(registry), `pane '${pane}' missing from registry`).toBe(true);
    }
  });
});
