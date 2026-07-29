import type { Router } from 'vue-router'

/**
 * Click handler for `v-html`-rendered markdown: hrefs rewritten to in-app routes
 * (see domain/artifactLinks) must navigate through the SPA router, not reload.
 */
export const routeInternalLinkClicks = (router: Router) => (event: MouseEvent): void => {
  const anchor = (event.target as HTMLElement).closest('a[href]')
  const href = anchor?.getAttribute('href')
  if (!href?.startsWith('/')) return
  event.preventDefault()
  void router.push(href)
}
