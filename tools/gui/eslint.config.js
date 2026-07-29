import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import vueParser from 'vue-eslint-parser'

export default tseslint.config(
  {
    ignores: ['dist/**', 'coverage/**', 'coverage-e2e/**', '.nyc_output/**'],
  },
  {
    files: ['**/*.ts'],
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      parser: tseslint.parser,
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      '@typescript-eslint/no-unused-expressions': ['error', { allowTernary: true }],
    },
  },
  {
    files: ['**/*.vue'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommendedTypeChecked,
      ...pluginVue.configs['flat/recommended'],
    ],
    languageOptions: {
      parser: vueParser,
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
      parserOptions: {
        parser: tseslint.parser,
        extraFileExtensions: ['.vue'],
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-unused-expressions': ['error', { allowTernary: true }],
    },
  },
  {
    files: [
      'src/ui/components/ArchimateTypeGlyph.vue',
      'src/ui/components/AssuranceDiagramPanel.vue',
      'src/ui/components/DiagramEntitySidebar.vue',
      'src/ui/components/DiagramMatrixView.vue',
      'src/ui/components/GraphCanvas.vue',
      'src/ui/components/MarkdownEditor.vue',
      'src/ui/components/SidebarEntityEditor.vue',
      'src/ui/views/CreateMatrixView.vue',
      'src/ui/views/DiagramDetailView.vue',
      'src/ui/views/DocumentDetailView.vue',
      'src/ui/views/EditDiagramView.vue',
      'src/ui/views/EditMatrixView.vue',
      'src/ui/views/EntityDetailView.vue',
      'src/ui/views/GraphExploreView.vue',
      'src/ui/views/ViewpointDiagramView.vue',
    ],
    rules: {
      'vue/no-v-html': 'off',
    },
  },
  {
    files: ['**/*.js'],
    extends: [js.configs.recommended],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
    },
  },
  {
    files: ['vite.config.ts'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
  {
    // E2E test infra (Playwright). Runs in Node, with browser-context callbacks for
    // addInitScript/evaluate. Type-aware linting is not needed here and the files live
    // outside the app tsconfig the project service loads, so disable it for these paths.
    files: ['playwright.config.ts', 'tests/**/*.ts'],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: {
      parserOptions: { projectService: false, project: false },
      globals: {
        ...globals.node,
        ...globals.browser,
      },
    },
  },
  {
    // This config file itself runs in Node (env-gated fast tier below reads process.env).
    files: ['eslint.config.js'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
  // Fast tier (`npm run lint:fast`, LINT_TYPED=0): disables type-aware rules so that
  // ESLint's per-file --cache is sound. The per-file cache cannot see the type graph:
  // a cached "clean" verdict of a type-aware rule goes stale when OTHER files or
  // dependencies change types, and a partial-program run (file subset) cannot resolve
  // types at all — both produce wrong verdicts. Syntactic rules are a pure function
  // of the single file, so caching them is correct. Type errors remain covered in the
  // inner loop by `npm run typecheck` (vue-tsc), whose incremental mode tracks the
  // dependency graph soundly. The authoritative full typed lint is `npm run lint`
  // (cold, whole program) — the same thing CI runs.
  ...(process.env.LINT_TYPED === '0'
    ? [{ files: ['**/*.ts', '**/*.vue'], extends: [tseslint.configs.disableTypeChecked] }]
    : []),
)
