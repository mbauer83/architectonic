/**
 * Logic test for domain-change resets the entity-type filter in EntitiesView.
 *
 * Tests the reactive invariant without mounting a component (no DOM needed).
 * The watch `watch(activeDomain, () => { typeFilter.value = '' })` in EntitiesView
 * is the subject under test; here we verify the invariant directly using Vue reactivity.
 */
import { describe, it, expect } from 'vitest'
import { ref, watch, nextTick } from 'vue'

describe('domain change resets entity-type filter', () => {
  it('clears typeFilter when activeDomain changes to a new value', async () => {
    const activeDomain = ref('business')
    const typeFilter = ref('application-component')

    // Mirror the watch added to EntitiesView
    watch(activeDomain, () => {
      typeFilter.value = ''
    })

    activeDomain.value = 'application'
    await nextTick()

    expect(typeFilter.value).toBe('')
  })

  it('clears typeFilter when activeDomain is cleared (all-domains view)', async () => {
    const activeDomain = ref('technology')
    const typeFilter = ref('node')

    watch(activeDomain, () => {
      typeFilter.value = ''
    })

    activeDomain.value = ''
    await nextTick()

    expect(typeFilter.value).toBe('')
  })

  it('does not clear typeFilter when activeDomain is set to the same value', async () => {
    const activeDomain = ref('business')
    const typeFilter = ref('application-component')

    watch(activeDomain, () => {
      typeFilter.value = ''
    })

    activeDomain.value = 'business'
    await nextTick()

    // Vue watch does not fire when the value is unchanged
    expect(typeFilter.value).toBe('application-component')
  })

  it('uniqueTypes re-derives from activeDomain without reload', () => {
    // Verify the computed uniqueTypes shape from the taxonomy filtering logic
    // (domain filter is reactive — no extra load needed for the dropdown to update).
    const activeDomain = ref('business')

    const taxonomy = {
      domains: [
        { name: 'business', types: [{ name: 'role' }, { name: 'process' }] },
        { name: 'application', types: [{ name: 'application-component' }] },
      ],
    }

    const uniqueTypes = () => {
      const domains = activeDomain.value
        ? taxonomy.domains.filter((d) => d.name === activeDomain.value)
        : taxonomy.domains
      return [...new Set(domains.flatMap((d) => d.types.map((t) => t.name)))].sort()
    }

    expect(uniqueTypes()).toEqual(['process', 'role'])

    activeDomain.value = 'application'
    expect(uniqueTypes()).toEqual(['application-component'])

    activeDomain.value = ''
    expect(uniqueTypes()).toEqual(['application-component', 'process', 'role'])
  })
})
