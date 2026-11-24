<script setup lang="ts">
/**
 * Coverage table for a viewpoint that declares trace patterns.
 *
 * A separate surface from the entity table because the rows mean something different: they are
 * ordered worst-verdict-first and carry a composed verdict, so reading down the first column
 * is a work list. Every cell states its status in words — an authoritative gap and a
 * verdict-free diagnostic observation must never be distinguishable by colour alone.
 */
import { computed } from 'vue'

import type { TraceTable } from '../../domain/schemas/viewpoints'
import {
  traceColumns,
  traceDerivationNote,
  traceDisplayRows,
  traceTruncationNote,
} from './ViewpointTraceTable.helpers'

const props = defineProps<{ table: TraceTable | null }>()

const columns = computed(() => traceColumns(props.table))
const rows = computed(() => traceDisplayRows(props.table))
const truncationNote = computed(() => traceTruncationNote(props.table))
const derivationNote = computed(() => traceDerivationNote(props.table))
</script>

<template>
  <section
    v-if="rows.length > 0"
    class="vp-trace"
  >
    <p
      v-if="derivationNote"
      class="vp-trace-note vp-trace-note--warn"
    >
      {{ derivationNote }}
    </p>
    <p
      v-if="truncationNote"
      class="vp-trace-note"
    >
      {{ truncationNote }}
    </p>
    <table class="vp-trace-table">
      <thead>
        <tr>
          <th>Element</th>
          <th>Verdict</th>
          <th
            v-for="col in columns"
            :key="col.key"
          >
            {{ col.label }}
            <span
              v-if="col.role === 'diagnostic'"
              class="vp-trace-role"
              title="Diagnostic observation — never counts as a gap"
            >observation</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.entityId"
        >
          <td>
            <RouterLink :to="`/entities/${row.entityId}`">
              {{ row.name }}
            </RouterLink>
            <span class="vp-trace-type">{{ row.type }}</span>
          </td>
          <td>
            <span :class="['vp-trace-verdict', `vp-trace-verdict--${row.tone}`]">{{ row.verdict }}</span>
          </td>
          <td
            v-for="(cell, index) in row.cells"
            :key="columns[index]?.key ?? index"
          >
            <span :class="['vp-trace-cell', `vp-trace-cell--${cell.tone}`]">{{ cell.text }}</span>
            <span
              v-if="cell.detail"
              class="vp-trace-detail"
            >{{ cell.detail }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.vp-trace { margin-top: 18px; }
.vp-trace-note { font-size: 12px; color: var(--muted); margin: 0 0 8px; }
.vp-trace-note--warn { color: var(--warn-text); }

.vp-trace-table {
  width: 100%; border-collapse: collapse; background: var(--surface);
  border: 1px solid var(--border); border-radius: 8px; overflow: hidden;
}
.vp-trace-table th, .vp-trace-table td { padding: 10px 14px; text-align: left; vertical-align: top; }
.vp-trace-table th {
  background: var(--hover); border-bottom: 1px solid var(--border); font-size: 11px;
  font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--muted);
}
.vp-trace-table td { border-bottom: 1px solid var(--hair); font-size: 13px; }
.vp-trace-table tr:last-child td { border-bottom: 0; }

.vp-trace-role {
  display: block; font-size: 9px; font-weight: 400;
  text-transform: none; letter-spacing: 0; color: var(--faint);
}
.vp-trace-type { display: block; font-size: 11px; color: var(--faint); }
.vp-trace-detail { display: block; font-size: 11px; color: var(--muted); }

.vp-trace-verdict, .vp-trace-cell {
  display: inline-block; padding: 1px 8px; border-radius: 10px;
  font-size: 11px; font-weight: 600;
}
.vp-trace-verdict--negative, .vp-trace-cell--negative { background: var(--danger-soft); color: var(--danger-strong); }
.vp-trace-verdict--positive, .vp-trace-cell--positive { background: var(--ok-soft); color: var(--ok-text); }
.vp-trace-verdict--neutral, .vp-trace-cell--neutral { background: var(--soft); color: var(--text-2); }
</style>
