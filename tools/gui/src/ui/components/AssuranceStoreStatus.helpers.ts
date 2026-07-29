/**
 * What to tell a reader about the assurance store's lock state.
 *
 * The state is only interesting when it stands in the way. An unlocked store needs no banner: the
 * content is right there, and a green "everything is fine" strip above every visit is noise that
 * teaches readers to ignore the strip — including on the visit where it says the store is locked.
 * So `bannerFor` returns null for the working case, and the browse surface renders nothing.
 *
 * The two failing cases are genuinely different and must not share a message. A store that was
 * never initialised needs `arch-assurance init`; a locked one needs `unlock` against the *running*
 * backend, and telling someone to init an initialised store invites them to consider replacing it.
 */

export type AssuranceStoreState = 'unlocked' | 'locked' | 'not_initialised'

export interface AssuranceStatus {
  configured: boolean
  unlocked: boolean
  status: AssuranceStoreState
  db_path?: string
  hint?: string | null
}

export interface AssuranceStatusBanner {
  state: Exclude<AssuranceStoreState, 'unlocked'>
  title: string
  /** What the reader has to do, as prose around the one command that does it. */
  hint: string
  command: string
  /** Whether to offer the longer first-run sequence — only useful when there is no store yet. */
  showGettingStarted: boolean
}

const NOT_INITIALISED: AssuranceStatusBanner = {
  state: 'not_initialised',
  title: 'Assurance store not initialised',
  hint: 'Create the encrypted assurance store in this workspace to enable the confidential '
    + 'assurance capability.',
  command: 'arch-assurance init',
  showGettingStarted: true,
}

const LOCKED: AssuranceStatusBanner = {
  state: 'locked',
  title: 'Assurance store locked',
  // Deliberately "while the backend is running": each backend process must be authorised, and a
  // restart re-locks the store. Someone who unlocks first and starts the backend after gets a
  // locked store and no explanation.
  hint: 'Authorise this backend process to open the store. Run it while the backend is running; '
    + 'restarting the backend locks the store again.',
  command: 'arch-assurance unlock',
  showGettingStarted: false,
}

/** The banner to show, or null when the store is open and there is nothing to say. */
export const bannerFor = (status: AssuranceStatus | null): AssuranceStatusBanner | null => {
  if (status === null || status.status === 'unlocked') return null
  return status.status === 'not_initialised' ? NOT_INITIALISED : LOCKED
}

/** The first-run sequence, in order. Shown only alongside the not-initialised banner. */
export const GETTING_STARTED: readonly { command: string; then: string }[] = [
  { command: 'arch-assurance init', then: 'creates the encrypted assurance store' },
  { command: 'arch-assurance unlock', then: 'authorises the running backend to open it' },
  { command: 'assurance_guidance', then: 'gives per-step method coaching as you author' },
]
