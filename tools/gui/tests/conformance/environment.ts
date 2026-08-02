/**
 * Where the harness expects a backend, read the same way the Playwright suite reads it.
 *
 * The browser globals themselves come from the `jsdom` environment the conformance config selects,
 * pointed at this origin — see the comment there for why a hand-rolled `window` shim was not enough.
 */
export const baseUrl = (): string =>
  (process.env.E2E_BASE_URL ?? process.env.CONFORMANCE_BASE_URL ?? 'http://localhost:8000').replace(
    /\/$/,
    '',
  )
