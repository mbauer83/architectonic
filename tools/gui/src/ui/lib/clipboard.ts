/**
 * Copy text to the clipboard, on any origin the product is served from.
 *
 * `navigator.clipboard` exists only in a secure context — HTTPS, or `localhost`. An installation reached
 * over plain HTTP on an intranet (`http://archi.example.internal:8000`, through a VPN or from the office)
 * has no `navigator.clipboard` at all, and calling it threw. There the copy goes through a selected,
 * off-screen text area and the editing command, which browsers still honour inside a user gesture.
 *
 * Resolves when the text was copied; rejects when neither route could copy it, so the caller can say so.
 */
export async function copyText(text: string): Promise<void> {
  if (window.isSecureContext && navigator.clipboard !== undefined) {
    await navigator.clipboard.writeText(text)
    return
  }
  copyThroughSelection(text)
}

function copyThroughSelection(text: string): void {
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.left = '-9999px'
  document.body.appendChild(area)
  try {
    area.select()
    // The only clipboard route outside a secure context; deprecated, but kept by every browser.
    if (!document.execCommand('copy')) throw new Error('The browser refused to copy.')
  } finally {
    area.remove()
  }
}
