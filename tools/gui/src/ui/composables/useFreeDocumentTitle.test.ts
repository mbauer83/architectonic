import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'
import { Effect } from 'effect'
import { NetworkError } from '../../domain/errors'
import { type FreeTitleAccess, useFreeDocumentTitle } from './useFreeDocumentTitle'

const settled = async () => {
  for (let tick = 0; tick < 4; tick += 1) await nextTick()
}

/** A server where *taken* names are held, answering the first free numbered one. */
const server = (taken: readonly string[]): FreeTitleAccess & { readonly asked: string[] } => {
  const asked: string[] = []
  return {
    asked,
    freeDocumentTitle: (docType, title) => {
      asked.push(title)
      const free = [title, `${title} (2)`, `${title} (3)`].find((one) => !taken.includes(one)) ?? title
      return Effect.succeed({ doc_type: docType, asked: title, title: free })
    },
  }
}

describe('a default document name', () => {
  it('is offered as the server makes it free', async () => {
    const proposed = ref('Stress analysis — Map')
    const title = useFreeDocumentTitle(server(['Stress analysis — Map']), 'stress-analysis', () => proposed.value)
    await settled()
    expect(title.value).toBe('Stress analysis — Map (2)')
  })

  it('follows the proposal, never answering a newer one with an older answer', async () => {
    const proposed = ref('Stress analysis — Map')
    const access = server(['Stress analysis — Map'])
    const title = useFreeDocumentTitle(access, 'stress-analysis', () => proposed.value)
    proposed.value = 'Stress analysis — Queues'
    expect(title.value).toBe('Stress analysis — Queues')
    await settled()
    expect(title.value).toBe('Stress analysis — Queues')
    expect(access.asked).toEqual(['Stress analysis — Map', 'Stress analysis — Queues'])
  })

  it('stays as proposed where the server cannot answer', async () => {
    const failing: FreeTitleAccess = {
      freeDocumentTitle: () => Effect.fail(new NetworkError({ status: 503, message: 'down' })),
    }
    const title = useFreeDocumentTitle(failing, 'stress-analysis', () => 'Stress analysis — Map')
    await settled()
    expect(title.value).toBe('Stress analysis — Map')
  })
})
