import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useSimilarEntities } from '../useSimilarEntities'
import type { EntityDisplayInfo } from '../../../domain'

const entity = (artifact_id: string, name: string): EntityDisplayInfo => ({
  artifact_id, name, artifact_type: 'stakeholder', domain: 'motivation', subdomain: '',
  status: 'draft', display_alias: artifact_id, element_type: 'stakeholder', element_label: 'Stakeholder', diagram_internal: false,
})

describe('useSimilarEntities', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('debounces typing and surfaces same-type matches for the final query', async () => {
    const search = vi.fn().mockResolvedValue([entity('s1', 'Compliance Officer')])
    const name = ref('')
    const similar = useSimilarEntities(search, () => 'stakeholder', name)

    name.value = 'Comp'
    await nextTick()
    name.value = 'Compliance'
    await nextTick()
    await vi.advanceTimersByTimeAsync(400)

    expect(search).toHaveBeenCalledTimes(1)
    expect(search).toHaveBeenCalledWith('Compliance', 'stakeholder')
    expect(similar.matches.value.map((m) => m.artifact_id)).toEqual(['s1'])
  })

  it('clears matches when the query drops below the minimum length', async () => {
    const search = vi.fn().mockResolvedValue([entity('s1', 'X')])
    const name = ref('')
    const similar = useSimilarEntities(search, () => 'stakeholder', name)

    name.value = 'Portal'
    await nextTick()
    await vi.advanceTimersByTimeAsync(400)
    expect(similar.matches.value).toHaveLength(1)

    name.value = 'P'
    await nextTick()
    expect(similar.matches.value).toHaveLength(0)
    expect(search).toHaveBeenCalledTimes(1)
  })

  it('degrades search failures to no matches instead of surfacing an error', async () => {
    const search = vi.fn().mockRejectedValue(new Error('backend down'))
    const name = ref('')
    const similar = useSimilarEntities(search, () => 'stakeholder', name)

    name.value = 'Portal'
    await nextTick()
    await vi.advanceTimersByTimeAsync(400)
    expect(similar.matches.value).toHaveLength(0)
  })

  it('reset drops pending lookups and current matches', async () => {
    const search = vi.fn().mockResolvedValue([entity('s1', 'X')])
    const name = ref('')
    const similar = useSimilarEntities(search, () => 'stakeholder', name)

    name.value = 'Portal'
    await nextTick()
    similar.reset()
    await vi.advanceTimersByTimeAsync(400)
    expect(similar.matches.value).toHaveLength(0)
  })
})
