<script setup lang="ts">
/**
 * What a write *would* do, as the product's own dry run reports it: the id and path it would take, the
 * verification it would pass or fail, and the whole file it would produce.
 *
 * Lifted out of `EntityCreateView`, where the pane was inline and the view was exactly at its
 * grandfathered length limit — so exactly at the point where it could not take another import line, which
 * is why its helpers module carried a bare `export { entityDetailRoute }` pass-through that existed for
 * no reason but that. The pane is the right thing to lift because it is the one part of that view with no
 * knowledge of *entities*: it renders a `WriteResult`, and every create surface in the product produces
 * one.
 *
 * **It renders the refusal as prominently as the success.** A dry run that answers `wrote: false` with
 * verification issues is the shape this release kept finding hidden inside a 200, and a preview that
 * showed only the file it would write would hide it here too.
 *
 * No unit test of its own: it holds no logic to test, and these tests mount nothing. What guards the
 * lift is `tests/e2e/gui-exploration-and-authoring.spec.ts`, which drives the create form to a real dry
 * run and asserts both the "Verification passed." line and the auto-populated frontmatter in the file
 * this pane renders. A markup-and-styles move is exactly the change a browser assertion catches and a
 * unit test cannot.
 */
import type { WriteResult } from '../../domain'

defineProps<{
  /** The dry run's answer. The caller renders nothing when it has not run one. */
  preview: WriteResult
  /** Whether the verification passed — the caller's reading of it, not a second computation here. */
  clean: boolean
  /** The issues to show when it did not. Empty when `clean`. */
  issues: readonly string[]
}>()
</script>

<template>
  <section class="preview-section card">
    <h2 class="preview-title">
      Dry-run preview
    </h2>
    <div class="preview-meta">
      <span class="mono">{{ preview.artifact_id }}</span>
      <span class="preview-path mono">→ {{ preview.path }}</span>
    </div>

    <div
      v-if="!clean"
      class="state-msg state-msg--error"
    >
      <strong>Verification issues found:</strong>
      <ul class="preview-issues">
        <li
          v-for="issue in issues"
          :key="issue"
        >
          {{ issue }}
        </li>
      </ul>
    </div>
    <div
      v-else
      class="state-msg state-msg--ok"
    >
      Verification passed.
    </div>

    <pre
      v-if="preview.content"
      class="preview-content"
    >{{ preview.content }}</pre>
  </section>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 20px; }
.preview-title {
  font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em;
  color: #374151; margin-bottom: 12px;
}
.preview-meta { font-size: 12px; color: #6b7280; margin-bottom: 8px; display: flex; flex-direction: column; gap: 2px; }
.preview-path { color: #9ca3af; }
.mono { font-family: monospace; }
/* Was an inline `style` attribute on the `<ul>`, which scoped styles exist to avoid. */
.preview-issues { margin-top: 4px; font-size: 12px; margin-bottom: 0; padding-left: 18px; }
.preview-content {
  font-size: 11px; color: #374151; white-space: pre-wrap; max-height: 400px; overflow-y: auto;
  font-family: monospace; margin-top: 12px; background: #f9fafb; border-radius: 6px; padding: 10px;
}
/* Copied verbatim from the view this came out of: lifting a pane must not restyle it. */
.state-msg { font-size: 13px; color: #6b7280; padding: 4px 0; }
.state-msg--error { color: #dc2626; }
.state-msg--ok { color: #16a34a; }
</style>
