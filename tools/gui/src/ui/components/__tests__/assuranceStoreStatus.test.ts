/**
 * The store's lock state is worth saying only when it stands in the way.
 *
 * An unlocked store gets no banner: a permanent "all is well" strip above every visit is what
 * teaches a reader to skip the strip — including on the visit where it says the store is locked.
 * And the two failing states must not share a message: telling someone to `init` an already
 * initialised store invites them to consider replacing it.
 */
import { describe, expect, it } from 'vitest'
import {
  GETTING_STARTED,
  bannerFor,
  type AssuranceStatus,
} from '../AssuranceStoreStatus.helpers'

const status = (state: AssuranceStatus['status']): AssuranceStatus => ({
  configured: state !== 'not_initialised',
  unlocked: state === 'unlocked',
  status: state,
})

describe('bannerFor', () => {
  it('says nothing about a store that is open', () => {
    expect(bannerFor(status('unlocked'))).toBeNull()
  })

  it('says nothing before the status has loaded', () => {
    /* A flash of "locked" while the request is in flight would be a false alarm. */
    expect(bannerFor(null)).toBeNull()
  })

  it('asks for init when there is no store yet, with the first-run sequence', () => {
    const banner = bannerFor(status('not_initialised'))

    expect(banner?.command).toBe('arch-assurance init')
    expect(banner?.showGettingStarted).toBe(true)
  })

  it('asks for unlock when the store exists, and does not mention init', () => {
    const banner = bannerFor(status('locked'))

    expect(banner?.command).toBe('arch-assurance unlock')
    expect(banner?.showGettingStarted).toBe(false)
    expect(`${banner?.title} ${banner?.hint}`).not.toContain('init')
  })

  it('tells the reader that unlock applies to the running backend', () => {
    /* Each backend process must be authorised and a restart re-locks the store, so someone who
       unlocks first and starts the backend after gets a locked store and no explanation. */
    const hint = bannerFor(status('locked'))?.hint ?? ''

    expect(hint).toContain('running')
    expect(hint).toContain('restart')
  })

  it('distinguishes the two failing states', () => {
    expect(bannerFor(status('locked'))?.title).not.toBe(
      bannerFor(status('not_initialised'))?.title,
    )
  })
})

describe('GETTING_STARTED', () => {
  it('puts init before unlock, which is the only order that works', () => {
    const commands = GETTING_STARTED.map(step => step.command)

    expect(commands.indexOf('arch-assurance init')).toBeLessThan(
      commands.indexOf('arch-assurance unlock'),
    )
  })

  it('explains every step, so the list is not just commands to paste', () => {
    for (const step of GETTING_STARTED) {
      expect(step.then.length).toBeGreaterThan(0)
    }
  })
})
