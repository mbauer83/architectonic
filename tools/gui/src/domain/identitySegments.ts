/**
 * Spelling an artifact identifier as one URL path segment.
 *
 * Encoding only — no opinion about which URL it is going into. That separation is the point: the Vue
 * router additionally refuses ids that collide with a literal segment one of *its* collection routes
 * spells (`new`, `edit`, `groups`, …), and the REST surface has no such collision, so an adapter
 * reaching for the router's guarded version inherited a rule that is not about it.
 *
 * Two properties the callers depend on, both of them about what the server does with the result:
 *
 * - `.` is **not** escaped. `encodeURIComponent` leaves it alone, which is what we want: the server
 *   decodes `%2E` back to `.`, so escaping it would create a second spelling of one identity.
 * - `/` **is** escaped, to `%2F`. The server rejects that rather than treating it as a deeper path,
 *   because a slash is outside the identifier grammar. An identifier whose parts are separated by one
 *   — a construct a diagram owns — is addressed by giving each part its own segment instead; see
 *   `diagramLocalIds`.
 */
export const encodeIdentitySegment = (id: string): string => encodeURIComponent(id)
