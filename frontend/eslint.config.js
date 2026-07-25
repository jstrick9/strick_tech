import js from '@eslint/js';
import globals from 'globals';

export default [
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: {
        ...globals.browser,
        ...globals.es2022,
        // Agentic OS globals
        'S': 'readonly',
        'nav': 'writable',
        'toast': 'writable',
        'escHtml': 'writable',
        'renderMarkdown': 'writable',
        'renderMarkdownEnhanced': 'writable',
        'addMessage': 'writable',
        'addThinking': 'writable',
        'updateMessageBubble': 'writable',
        'sendChat': 'writable',
        'clearChatHistory': 'writable',
        'openPalette': 'writable',
        'closePalette': 'writable',
        'filterPalette': 'writable',
        'toggleSidebar': 'writable',
        'toggleSidebarGroup': 'writable',
        'initSidebarGroups': 'writable',
        'applyTheme': 'writable',
        'loadSettings': 'writable',
        'gmPrompt': 'writable',
        'gmAlert': 'writable',
        'gmConfirm': 'writable',
        'showToast': 'writable',
        'openExternalLink': 'writable',
        'MASTER_PANE_REGISTRY': 'writable',
        'PANE_TO_GROUP': 'writable',
        'hljs': 'readonly',
        'Monaco': 'readonly',
        'monaco': 'readonly',
        'require': 'readonly',
        'EventSource': 'readonly',
      },
    },
    rules: {
      // Security
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'warn',

      // Quality
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-undef': 'warn',
      'no-redeclare': 'warn',
      'no-dupe-keys': 'error',
      'no-duplicate-case': 'error',
      'no-unreachable': 'warn',
      'no-constant-condition': 'warn',

      // Style (relaxed for legacy code)
      'no-empty': ['warn', { allowEmptyCatch: true }],
      'no-extra-semi': 'warn',
      'no-irregular-whitespace': 'error',
    },
  },
  {
    ignores: [
      'node_modules/',
      'tests/',
    ],
  },
];
