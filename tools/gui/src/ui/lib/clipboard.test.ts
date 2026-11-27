// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'

import { copyText } from './clipboard'

const setSecure = (secure: boolean, clipboard: Clipboard | undefined) => {
  vi.stubGlobal('isSecureContext', secure)
  Object.defineProperty(navigator, 'clipboard', { value: clipboard, configurable: true })
}

describe('copyText', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('uses the clipboard API in a secure context', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    setSecure(true, { writeText } as unknown as Clipboard)

    await copyText('http://host/x')

    expect(writeText).toHaveBeenCalledWith('http://host/x')
  })

  it('copies through a selection over plain HTTP, where there is no clipboard API', async () => {
    setSecure(false, undefined)
    let copied = ''
    const exec = vi.fn(() => {
      copied = (document.activeElement as HTMLTextAreaElement | null)?.value
        ?? document.querySelector('textarea')?.value ?? ''
      return true
    })
    Object.defineProperty(document, 'execCommand', { value: exec, configurable: true })

    await copyText('http://intranet:8000/diagrams/x')

    expect(exec).toHaveBeenCalledWith('copy')
    expect(copied).toBe('http://intranet:8000/diagrams/x')
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('rejects when the browser refuses, so the caller can say the copy failed', async () => {
    setSecure(false, undefined)
    Object.defineProperty(document, 'execCommand', { value: () => false, configurable: true })

    await expect(copyText('x')).rejects.toThrow('refused')
    expect(document.querySelector('textarea')).toBeNull()
  })
})
