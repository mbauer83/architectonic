// @vitest-environment jsdom
//
// The prompt for a git credential a remote refused: a password field that opts out of autofill, the
// reason when a credential was refused, and an answer handed over once with the fields cleared.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import GitCredentialDialog from '../GitCredentialDialog.vue'
import type { GitCredentialRequest } from '../../lib/gitCredentials'

let app: App | null = null

const mounted = (request: GitCredentialRequest) => {
  const [submitted, cancelled] = [vi.fn(), vi.fn()]
  const host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(GitCredentialDialog, { request, onSubmit: submitted, onCancel: cancelled }) })
  app.mount(host)
  return { host, submitted, cancelled }
}

const type = async (input: HTMLInputElement, value: string): Promise<void> => {
  input.value = value
  input.dispatchEvent(new Event('input'))
  await nextTick()
}

afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

describe('GitCredentialDialog', () => {
  it('asks for an SSH passphrase in a password field with autofill off', () => {
    const { host } = mounted({ protocol: 'ssh', remote: 'git@host:acme/repo.git', rejected: false })
    const secret = host.querySelector<HTMLInputElement>('#git-credential-secret')!
    expect(secret.type).toBe('password')
    expect(secret.autocomplete).toBe('off')
    expect(host.querySelector('#git-credential-username')).toBeNull()
    expect(host.textContent).toContain('git@host:acme/repo.git')
    expect(host.querySelector('[role="alert"]')).toBeNull()
  })

  it('says the last credential was refused when asking again', () => {
    const { host } = mounted({ protocol: 'ssh', remote: 'git@host:acme/repo.git', rejected: true })
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('refused')
  })

  it('hands over the answer once and clears the field', async () => {
    const { host, submitted } = mounted({ protocol: 'ssh', remote: 'git@host:acme/repo.git', rejected: false })
    const secret = host.querySelector<HTMLInputElement>('#git-credential-secret')!
    await type(secret, 'open sesame')
    host.querySelector('form')!.dispatchEvent(new Event('submit'))
    await nextTick()
    expect(submitted).toHaveBeenCalledWith({ secret: 'open sesame' })
    expect(secret.value).toBe('')
  })

  it('asks for a token and an optional username over https', async () => {
    const { host, submitted } = mounted({ protocol: 'https', remote: 'https://host/acme/repo.git', rejected: false })
    const username = host.querySelector<HTMLInputElement>('#git-credential-username')!
    expect(username.autocomplete).toBe('off')
    await type(username, 'ci-bot')
    await type(host.querySelector<HTMLInputElement>('#git-credential-secret')!, 'ghp_token')
    host.querySelector('form')!.dispatchEvent(new Event('submit'))
    await nextTick()
    expect(submitted).toHaveBeenCalledWith({ secret: 'ghp_token', username: 'ci-bot' })
  })

  it('cancels without an answer', async () => {
    const { host, submitted, cancelled } = mounted({ protocol: 'ssh', remote: 'r', rejected: false })
    host.querySelector<HTMLButtonElement>('button[type="button"]')!.click()
    await nextTick()
    expect(cancelled).toHaveBeenCalled()
    expect(submitted).not.toHaveBeenCalled()
  })
})
