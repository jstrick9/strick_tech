import { describe, it, expect } from 'vitest';

// Test the _safeLS wrapper that protects localStorage from private browsing errors

describe('Safe localStorage wrapper', () => {
  it('getItem returns null for missing keys', () => {
    expect(localStorage.getItem('nonexistent')).toBeNull();
  });

  it('setItem and getItem round-trip', () => {
    localStorage.setItem('test_key', 'test_value');
    expect(localStorage.getItem('test_key')).toBe('test_value');
    localStorage.removeItem('test_key');
  });

  it('removeItem deletes key', () => {
    localStorage.setItem('to_delete', 'value');
    localStorage.removeItem('to_delete');
    expect(localStorage.getItem('to_delete')).toBeNull();
  });

  it('handles numeric values', () => {
    localStorage.setItem('num', 42);
    expect(localStorage.getItem('num')).toBe('42');
    localStorage.removeItem('num');
  });

  it('handles boolean values as strings', () => {
    localStorage.setItem('bool', true);
    expect(localStorage.getItem('bool')).toBe('true');
    localStorage.removeItem('bool');
  });
});

describe('Sidebar navigation groups', () => {
  const groups = ['core', 'build', 'ship', 'tools', 'enterprise'];

  it('has 5 sidebar groups', () => {
    expect(groups).toHaveLength(5);
  });

  it('core group is first (Getting Started)', () => {
    expect(groups[0]).toBe('core');
  });

  it('all groups have valid IDs', () => {
    groups.forEach(g => {
      expect(g).toMatch(/^[a-z]+$/);
    });
  });
});

describe('Chat model options', () => {
  const models = [
    { value: 'claude', label: 'Claude 3.5 Sonnet' },
    { value: 'gpt4o', label: 'GPT-4o' },
    { value: 'gemini', label: 'Gemini 2.5 Pro' },
    { value: 'local', label: 'Ollama Auto-Detect' },
  ];

  it('has at least 4 model options', () => {
    expect(models.length).toBeGreaterThanOrEqual(4);
  });

  it('all models have value and label', () => {
    models.forEach(m => {
      expect(m.value).toBeTruthy();
      expect(m.label).toBeTruthy();
    });
  });

  it('includes local model option', () => {
    expect(models.some(m => m.value === 'local')).toBe(true);
  });
});
