import { type APIRequestContext, expect } from '@playwright/test'

/**
 * Shared catalog read for the viewpoint end-to-end specs.
 *
 * The entry is typed against the wire payload, not against the frontend's own decoder: these
 * specs exist to prove that what the GUI saved is what the backend stored, so routing the
 * assertion through the same schema the GUI uses to read would let a wrong decoder pass. Nested
 * query structures stay `unknown` and are compared whole with `toEqual`, which keeps the
 * assertion on the round-trip rather than on a restatement of the query grammar.
 */
export interface ViewpointCatalogEntry {
  slug: string
  scope: Record<string, unknown>
  // Optional exactly where the wire omits the key when the clause is empty, so a test that
  // relies on a clause being present has to say so rather than reading through a widened type.
  query: {
    entity_criteria: { children: unknown }
    parameters?: unknown
    bindings?: unknown
    derived?: unknown
    include_connected?: unknown[]
    connections?: unknown
  }
  broken_references: { reference: string }[]
}

interface ViewpointCatalog {
  viewpoints: ViewpointCatalogEntry[]
}

/**
 * The saved definition, once the write has actually landed.
 *
 * Polled rather than read once. The GUI returns to the list as soon as the save is accepted, so a
 * single read right after the heading appears races the catalog write — it passed when the suite
 * was small and failed intermittently under load, with the entry visible on the page while the API
 * call that had just been made reported nothing. Polling asserts the property the test is actually
 * about (the definition round-trips) instead of the timing of one request.
 */
export const findEntry = async (
  request: APIRequestContext,
  slug: string,
): Promise<ViewpointCatalogEntry> => {
  let found: ViewpointCatalogEntry | undefined
  await expect.poll(async () => {
    const resp = await request.get('/api/viewpoints')
    const body = await resp.json() as ViewpointCatalog
    found = body.viewpoints.find((v) => v.slug === slug)
    return found !== undefined
  }, { message: `viewpoint '${slug}' never appeared in /api/viewpoints`, timeout: 15_000 }).toBe(true)
  if (found === undefined) throw new Error(`viewpoint '${slug}' not in the catalog`)
  return found
}
