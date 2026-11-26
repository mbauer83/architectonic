// @vitest-environment jsdom
/**
 * Unsaved edits are never lost without a question. The regression: opening another diagram while an
 * edit session held changes dropped them silently, and Discard threw them away on one press.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent, type App } from 'vue'
import { useEditSessionExits } from '../useEditSessionExits'

let app: App | null = null
afterEach(() => { app?.unmount(); app = null })

const session = (unsaved: boolean, saves = true) => {
  const said: string[] = []
  let exits!: ReturnType<typeof useEditSessionExits>
  app = createApp(defineComponent({
    setup() {
      exits = useEditSessionExits({
        unsaved: () => unsaved,
        save: () => { said.push('save'); return Promise.resolve(saves) },
        discard: () => { said.push('discard') },
        close: () => { said.push('close') },
      })
      return () => null
    },
  }))
  app.mount(document.createElement('div'))
  return { exits, said }
}

describe('opening another page', () => {
  it('goes at once when nothing is unsaved', () => {
    const { exits } = session(false)
    expect(exits.mayLeave(() => undefined)).toBe(true)
    expect(exits.leaving.value).toBe(false)
  })

  it('is held, and asked about, while something is unsaved', () => {
    const { exits, said } = session(true)
    expect(exits.mayLeave(() => said.push('went'))).toBe(false)
    expect(exits.leaving.value).toBe(true)
    expect(said).toEqual([])
  })

  it('goes on after Discard and exit, the changes thrown away first', () => {
    const { exits, said } = session(true)
    exits.mayLeave(() => said.push('went'))
    exits.discardAndExit()
    expect(said).toEqual(['discard', 'close', 'went'])
  })

  it('goes on after Save and exit, once the save is written', async () => {
    const { exits, said } = session(true)
    exits.mayLeave(() => said.push('went'))
    await exits.saveAndExit()
    expect(said).toEqual(['save', 'close', 'went'])
  })

  it('stays when the save is refused', async () => {
    const { exits, said } = session(true, false)
    exits.mayLeave(() => said.push('went'))
    await exits.saveAndExit()
    expect(said).toEqual(['save'])
  })

  it('is dropped by Keep editing, and by Escape, so a later Done does not go there', () => {
    for (const answer of ['keep', 'escape'] as const) {
      const { exits, said } = session(true)
      exits.mayLeave(() => said.push('went'))
      if (answer === 'keep') exits.keepEditing()
      else expect(exits.answerEscape()).toBe(true)
      expect(exits.leaving.value).toBe(false)
      exits.done()
      exits.discardAndExit()
      expect(said).toEqual(['discard', 'close'])
      app?.unmount()
      app = null
    }
  })
})

describe('closing the tab or reloading', () => {
  const unload = () => {
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    return event.defaultPrevented
  }

  it('is asked about by the browser while something is unsaved', () => {
    session(true)
    expect(unload()).toBe(true)
  })

  it('is not asked about when nothing is', () => {
    session(false)
    expect(unload()).toBe(false)
  })
})

describe('Discard', () => {
  it('asks first, and Cancel keeps the changes', () => {
    const { exits, said } = session(true)
    exits.askDiscard()
    expect(exits.discarding.value).toBe(true)
    exits.cancelDiscard()
    expect(exits.discarding.value).toBe(false)
    expect(said).toEqual([])
  })

  it('throws the changes away once confirmed, and stays in edit mode', () => {
    const { exits, said } = session(true)
    exits.askDiscard()
    exits.confirmDiscard()
    expect(said).toEqual(['discard'])
    expect(exits.discarding.value).toBe(false)
  })

  it('is cancelled by Escape', () => {
    const { exits, said } = session(true)
    exits.askDiscard()
    expect(exits.answerEscape()).toBe(true)
    expect(exits.discarding.value).toBe(false)
    expect(said).toEqual([])
  })

  it('asks nothing when there is nothing to discard', () => {
    const { exits } = session(false)
    exits.askDiscard()
    expect(exits.discarding.value).toBe(false)
  })
})
