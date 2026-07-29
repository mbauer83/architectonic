// @vitest-environment jsdom
//
// Relationship guidance in the wizard, through a real mount: what matters is that a suggested
// relationship can disclose when to use it — collapsed, so it informs without taking over the row —
// and that a type with nothing to say discloses nothing at all.
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, type App } from 'vue'
import WizardConnectionSuggestions from '../WizardConnectionSuggestions.vue'
import type { WizardSuggestion } from '../../composables/useWizardSession'
import type { AuthoringGuidance } from '../../../domain'

const SUGGESTION: WizardSuggestion = {
  id: 's1',
  domain: 'application',
  summary: 'Checkout Service serves Order Process',
  sourceId: 'APP@1.a',
  sourceName: 'Checkout Service',
  connectionType: 'archimate-serving',
  targetId: 'PRC@1.b',
  targetName: 'Order Process',
}

const guidance = (connectionTypes: unknown[]): AuthoringGuidance =>
  ({ connection_types: connectionTypes } as unknown as AuthoringGuidance)

let mounted: App | null = null

const render = (props: Record<string, unknown>) => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({
    render: () => h(WizardConnectionSuggestions, { suggestions: [SUGGESTION], ...props }),
  })
  app.mount(host)
  mounted = app
  return host
}

afterEach(() => {
  mounted?.unmount()
  mounted = null
  document.body.innerHTML = ''
})

describe('WizardConnectionSuggestions relationship guidance', () => {
  it('discloses the relationship type\'s guidance, collapsed, labelled by the bare type name', () => {
    const host = render({
      guidance: guidance([
        {
          name: 'archimate-serving',
          create_when: 'Create a serving relation when the target consumes what the source provides.',
          never_create_when: 'Don\'t use serving where the dependency is structural.',
          specializations: [],
        },
      ]),
    })
    const details = host.querySelector('details.conn-guidance') as HTMLDetailsElement
    expect(details).not.toBeNull()
    expect(details.open).toBe(false)
    expect((details.querySelector('summary') as HTMLElement).textContent?.trim()).toBe('When to use serving')
    expect([...details.querySelectorAll('.conn-guidance__text')].map((p) => p.textContent?.trim())).toEqual([
      'Create a serving relation when the target consumes what the source provides.',
      'Don\'t use serving where the dependency is structural.',
    ])
  })

  it('renders no disclosure when the type carries no guidance', () => {
    const host = render({
      guidance: guidance([{ name: 'archimate-serving', create_when: '', never_create_when: '', specializations: [] }]),
    })
    expect(host.querySelector('details.conn-guidance')).toBeNull()
    expect(host.querySelector('.suggestion-summary')?.textContent).toContain('Checkout Service')
  })

  it('renders no disclosure when no guidance has been fetched at all', () => {
    const host = render({})
    expect(host.querySelector('details.conn-guidance')).toBeNull()
  })

  it('keeps the row actions alongside the guidance', () => {
    const host = render({
      guidance: guidance([{ name: 'archimate-serving', create_when: 'cw', specializations: [] }]),
    })
    expect([...host.querySelectorAll('.suggestion-actions button')].map((b) => b.textContent?.trim()))
      .toEqual(['Accept', 'Later', 'Dismiss'])
  })
})
