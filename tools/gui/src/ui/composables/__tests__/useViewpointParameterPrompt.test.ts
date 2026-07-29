import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useViewpointParameterPrompt } from '../useViewpointParameterPrompt'
import type { ViewpointDefinitionEnvelope } from '../../../domain'

const envelope = (slug: string, parameters: unknown[]): ViewpointDefinitionEnvelope => ({
  slug, version: 1, name: slug, tier: 'module', scope_summary: { unrestricted: true }, query_summary: null, fork_status: null,
  query: { query_schema: 1, entity_criteria: { kind: 'group', conjunction: 'and', children: [] }, parameters },
})

describe('useViewpointParameterPrompt', () => {
  it('resolves immediately for a definition with no required-undefaulted parameters', async () => {
    const onResolved = vi.fn().mockResolvedValue(undefined)
    const definitions = ref([envelope('plain', [])])
    const prompt = useViewpointParameterPrompt(onResolved, definitions)

    await prompt.run('plain')
    expect(onResolved).toHaveBeenCalledWith({ slug: 'plain', parameters: {} })
    expect(prompt.visible.value).toBe(false)
  })

  it('shows the prompt instead of resolving for a required-undefaulted parameter', async () => {
    const onResolved = vi.fn().mockResolvedValue(undefined)
    const definitions = ref([envelope('parameterized', [{ name: 'anchor', type: 'entity-id' }])])
    const prompt = useViewpointParameterPrompt(onResolved, definitions)

    await prompt.run('parameterized')
    expect(onResolved).not.toHaveBeenCalled()
    expect(prompt.visible.value).toBe(true)
    expect(prompt.parameters.value.map((p) => p.name)).toEqual(['anchor'])
  })

  it('resolves with the coerced wire values on submit, then hides the prompt', async () => {
    const onResolved = vi.fn().mockResolvedValue(undefined)
    const definitions = ref([envelope('parameterized', [{ name: 'anchor', type: 'entity-id' }])])
    const prompt = useViewpointParameterPrompt(onResolved, definitions)

    await prompt.run('parameterized')
    await prompt.submit({ anchor: 'ARC@1000000001' })

    expect(onResolved).toHaveBeenCalledWith({ slug: 'parameterized', parameters: { anchor: 'ARC@1000000001' } })
    expect(prompt.visible.value).toBe(false)
  })

  it('cancel hides the prompt without resolving', async () => {
    const onResolved = vi.fn().mockResolvedValue(undefined)
    const definitions = ref([envelope('parameterized', [{ name: 'anchor', type: 'entity-id' }])])
    const prompt = useViewpointParameterPrompt(onResolved, definitions)

    await prompt.run('parameterized')
    prompt.cancel()

    expect(prompt.visible.value).toBe(false)
    expect(onResolved).not.toHaveBeenCalled()
  })
})
