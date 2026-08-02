import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useViewpointParameterPrompt } from '../useViewpointParameterPrompt'
import type { ViewpointDefinitionEnvelope, ViewpointQuerySpec } from '../../../domain'
import { EMPTY_CRITERIA, viewpointEnvelope } from '../../__tests__/viewpointFixtures'

const envelope = (
  slug: string, parameters: ViewpointQuerySpec['parameters'],
): ViewpointDefinitionEnvelope =>
  viewpointEnvelope({
    slug, name: slug,
    query: { query_schema: 1, entity_criteria: EMPTY_CRITERIA, parameters },
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

  it('honours a preset for an all-optional definition instead of discarding it', async () => {
    // Regression: `?param.` values on a shared link were dropped for every definition whose
    // parameters were all optional or defaulted — the gate consulted the preset only when it
    // was about to prompt, and resolved with `{}` otherwise. The address-rewriting surfaces
    // then erased them from the URL as well, so the link could not even be re-shared.
    const onResolved = vi.fn().mockResolvedValue(undefined)
    const definitions = ref([envelope('coverage', [
      { name: 'gaps_only', type: 'boolean', required: false, default: 'false' },
    ])])
    const prompt = useViewpointParameterPrompt(onResolved, definitions)

    await prompt.run('coverage', { gaps_only: 'true' })

    expect(onResolved).toHaveBeenCalledWith({ slug: 'coverage', parameters: { gaps_only: true } })
    expect(prompt.visible.value).toBe(false)
  })

  it('a declared default covers a required parameter the preset does not name', async () => {
    const onResolved = vi.fn().mockResolvedValue(undefined)
    // `required` is written only when the parameter is optional, so both of these are required.
    const definitions = ref([envelope('mixed', [
      { name: 'scope', type: 'string', default: 'goal' },
      { name: 'anchor', type: 'entity-id' },
    ])])
    const prompt = useViewpointParameterPrompt(onResolved, definitions)

    await prompt.run('mixed', { anchor: 'ARC@1000000001' })

    expect(onResolved).toHaveBeenCalledWith({
      slug: 'mixed', parameters: { scope: 'goal', anchor: 'ARC@1000000001' },
    })
    expect(prompt.visible.value).toBe(false)
  })

  it('still prompts when a preset leaves a required, undefaulted parameter blank', async () => {
    const onResolved = vi.fn().mockResolvedValue(undefined)
    const definitions = ref([envelope('mixed', [
      { name: 'scope', type: 'string', required: false },
      { name: 'anchor', type: 'entity-id' },
    ])])
    const prompt = useViewpointParameterPrompt(onResolved, definitions)

    await prompt.run('mixed', { scope: 'goal' })

    expect(onResolved).not.toHaveBeenCalled()
    expect(prompt.visible.value).toBe(true)
  })

  it('resolves with no parameters at all when the caller supplied no preset', async () => {
    // Nothing was asked for, so nothing is asserted: the server applies the same declared
    // defaults, and an address naming values the caller never chose is noise.
    const onResolved = vi.fn().mockResolvedValue(undefined)
    const definitions = ref([envelope('defaulted', [
      { name: 'scope', type: 'string', required: false, default: 'goal' },
    ])])
    const prompt = useViewpointParameterPrompt(onResolved, definitions)

    await prompt.run('defaulted')

    expect(onResolved).toHaveBeenCalledWith({ slug: 'defaulted', parameters: {} })
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
