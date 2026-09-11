import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

/**
 * Structural pin for the workflow cluster's menu (asserted against the SFC template, as the
 * suite runs without DOM mounting).
 *
 * The menu carries both halves of "changes": the page listing what has been proposed, and the
 * verbs that save, submit, discard and promote. The two are not the same kind of entry and the
 * distinction is load-bearing — the verbs are fail-closed behind the reducer's authority
 * handling, the destination is a read and is not gated at all. So the button must not disable
 * itself when the reducer offers no verb: that is precisely the state a submission sits in while
 * it waits for review, and it would put the page holding it out of reach.
 */

const source = readFileSync(resolve(__dirname, '../SyncStatusCluster.vue'), 'utf8')
const template = source.slice(source.indexOf('<template>'), source.indexOf('</template>'))

describe('SyncStatusCluster structure', () => {
  it('opens the proposed-changes page from the menu', () => {
    expect(template).toContain('to="/changes"')
    expect(template).toContain('Proposed changes')
  })

  it('never disables the control that holds the destination', () => {
    expect(template).not.toContain(':disabled="!hasActions"')
    expect(template).toContain('v-if="menuOpen"')
  })

  it('keeps the verbs behind the reducer', () => {
    expect(template).toContain('v-for="action in menuActions"')
    expect(template).toContain('ACTION_LABELS[action]')
  })
})
