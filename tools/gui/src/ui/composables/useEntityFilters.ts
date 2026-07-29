import { computed, inject, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { domainOptionsForDomains } from '../lib/domains'
import { modelServiceKey } from '../keys'
import type { WriteHelp } from '../../domain'

export function buildTypeToDomain(map: Record<string, readonly string[]>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [domain, types] of Object.entries(map)) {
    for (const t of types) out[t] = domain
  }
  return out
}

export function deriveImpliedDomains(
  selectedTypes: string[],
  typeToDomain: Record<string, string>,
): string[] {
  return [...new Set(selectedTypes.map((t) => typeToDomain[t]).filter(Boolean))]
}

export function intersectWithFixed(available: string[], fixed?: string[]): string[] {
  if (!fixed?.length) return available
  const allowed = new Set(fixed)
  return available.filter((t) => allowed.has(t))
}

export function useEntityFilters(options?: { fixedEntityTypes?: string[] }) {
  const svc = inject(modelServiceKey)!
  const selectedDomains = ref<string[]>([])
  const selectedEntityTypes = ref<string[]>([])
  const writeHelp = ref<WriteHelp | null>(null)
  const domainOptions = computed(() =>
    domainOptionsForDomains(Object.keys(writeHelp.value?.entity_types_by_domain ?? {})),
  )

  const typeToDomain = computed(() =>
    buildTypeToDomain(writeHelp.value?.entity_types_by_domain ?? {}),
  )

  const impliedDomains = computed(() =>
    deriveImpliedDomains(selectedEntityTypes.value, typeToDomain.value),
  )

  const availableEntityTypes = computed(() => {
    const map = writeHelp.value?.entity_types_by_domain ?? {}
    const buckets = selectedDomains.value.length
      ? selectedDomains.value.flatMap((d) => map[d] ?? [])
      : Object.values(map).flat()
    const all = [...new Set(buckets)].sort()
    return intersectWithFixed(all, options?.fixedEntityTypes)
  })

  const toggle = (arr: string[], val: string) =>
    arr.includes(val) ? arr.filter((v) => v !== val) : [...arr, val]

  onMounted(() => {
    void Effect.runPromise(svc.getWriteHelp())
      .then((data) => { writeHelp.value = data })
      .catch(() => {})
  })

  return {
    selectedDomains,
    selectedEntityTypes,
    domainOptions,
    availableEntityTypes,
    impliedDomains,
    toggle,
  }
}
