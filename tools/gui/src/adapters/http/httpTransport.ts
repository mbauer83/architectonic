import { parseDiagramLocalId } from '../../domain/diagramLocalIds'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import { Effect, Schema, ParseResult } from 'effect'
import { NetworkError, NotFoundError } from '../../domain/errors'
import { TIMEOUT_BUDGET_MS, timeoutBudgetForPath } from './routeTimeoutPolicy'

// Shared HTTP transport for the REST adapters: URL building, timeout-bounded fetch,
// and schema-decoded JSON verbs. Adapter files compose these; error mapping to the
// typed domain errors happens here, once.
//
// The abort budget is derived from the request path, not passed in by the caller. Three call
// sites used to pass a longer budget by hand for viewpoint execution while every other
// long-running route silently kept the generic one — and the dev proxy had made its own,
// different set of exceptions. Deriving it means the classification in `routeTimeoutPolicy`
// is the only place the decision exists, and a renamed route carries its budget with it.

export const REQUEST_TIMEOUT_MS = TIMEOUT_BUDGET_MS.default ?? 10000

export const buildUrl = (
  path: string,
  params?: Readonly<Record<string, string | number | boolean | readonly string[] | undefined>>,
  adminPath?: boolean,
): string => {
  const url = new URL((adminPath ? '/admin/api' : '/api') + path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined) continue
      // An array becomes the *repeated* key FastAPI reads a `list[str]` query parameter from —
      // `?print=a&print=b`, not one comma-joined value. Joining is what the other list-valued reads
      // here do (`domains`, `entity_types`), and it is right for them because those routes declare a
      // single comma-separated string; a route declaring a list would receive one member named
      // "a,b". So the shape follows what the route declares, and both shapes are expressible.
      if (Array.isArray(v)) v.forEach((member) => url.searchParams.append(k, member))
      else url.searchParams.set(k, String(v as string | number | boolean))
    }
  }
  return url.toString()
}

/**
 * Where to read the entity `id` from.
 *
 * Turning identity into an address is this adapter's job, and there are two addresses because there
 * are two kinds of thing. An ordinary artifact is a member of the entity collection. A construct a
 * diagram owns is a sub-entity of that diagram, and *must* be addressed there: its identifier
 * contains a slash (`…#nodes/g11`), a slash ends a URL path segment, and an encoded one is decoded
 * back by the server before routing — so the flat address matches no route and answers 404.
 */
export const entityAddress = (id: string): string => {
  const local = parseDiagramLocalId(id)
  if (local === null) return buildUrl(`/entities/${encodeIdentitySegment(id)}`)
  return buildUrl(
    `/diagrams/${encodeIdentitySegment(local.diagramId)}`
    + `/entities/${encodeIdentitySegment(local.entityType)}`
    + `/${encodeIdentitySegment(local.localId)}`,
  )
}

/** The abort budget for a URL, from its path's timeout class. `null` means never abort. */
const budgetFor = (url: string): number | null => {
  try {
    return timeoutBudgetForPath(new URL(url, window.location.origin).pathname)
  } catch {
    return REQUEST_TIMEOUT_MS
  }
}

export const fetchWithTimeout = async (url: string, init?: RequestInit): Promise<Response> => {
  const timeoutMs = budgetFor(url)
  const controller = new AbortController()
  const timeout =
    timeoutMs === null
      ? undefined
      : window.setTimeout(
          () => controller.abort(new DOMException(`Timed out after ${timeoutMs}ms`, 'TimeoutError')),
          timeoutMs,
        )
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } catch (error) {
    console.error('HTTP request failed', {
      url,
      method: init?.method ?? 'GET',
      timeoutMs,
      error,
    })
    throw error
  } finally {
    if (timeout !== undefined) window.clearTimeout(timeout)
  }
}

export const fetchJson = <A, I>(
  url: string,
  schema: Schema.Schema<A, I>,
): Effect.Effect<A, NetworkError | ParseResult.ParseError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url)
      if (resp.status === 404) throw new NotFoundError({ id: url })
      if (!resp.ok) throw new NetworkError({ status: resp.status, message: resp.statusText })
      return resp.json() as Promise<unknown>
    },
    catch: (e) =>
      e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) }),
  }).pipe(Effect.flatMap(Schema.decodeUnknown(schema)))

export const fetchJsonNotFound = <A, I>(
  url: string,
  schema: Schema.Schema<A, I>,
  id: string,
): Effect.Effect<A, NetworkError | ParseResult.ParseError | NotFoundError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url)
      if (resp.status === 404) throw new NotFoundError({ id })
      if (!resp.ok) throw new NetworkError({ status: resp.status, message: resp.statusText })
      return resp.json() as Promise<unknown>
    },
    catch: (e) => {
      if (e instanceof NotFoundError || e instanceof NetworkError) return e
      return new NetworkError({ status: 0, message: String(e) })
    },
  }).pipe(Effect.flatMap(Schema.decodeUnknown(schema)))

export const fetchText = (url: string): Effect.Effect<string, NetworkError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url)
      if (!resp.ok) throw new NetworkError({ status: resp.status, message: resp.statusText })
      return resp.text()
    },
    catch: (e) => e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) }),
  })

export const postJson = <A, I>(
  url: string,
  body: unknown,
  schema: Schema.Schema<A, I>,
): Effect.Effect<A, NetworkError | ParseResult.ParseError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText)
        throw new NetworkError({ status: resp.status, message: text })
      }
      return resp.json() as Promise<unknown>
    },
    catch: (e) =>
      e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) }),
  }).pipe(Effect.flatMap(Schema.decodeUnknown(schema)))

export const putJson = <A, I>(
  url: string,
  body: unknown,
  schema: Schema.Schema<A, I>,
): Effect.Effect<A, NetworkError | ParseResult.ParseError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText)
        throw new NetworkError({ status: resp.status, message: text })
      }
      return resp.json() as Promise<unknown>
    },
    catch: (e) =>
      e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) }),
  }).pipe(Effect.flatMap(Schema.decodeUnknown(schema)))

export const patchJson = <A, I>(
  url: string,
  body: unknown,
  schema: Schema.Schema<A, I>,
): Effect.Effect<A, NetworkError | ParseResult.ParseError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText)
        throw new NetworkError({ status: resp.status, message: text })
      }
      return resp.json() as Promise<unknown>
    },
    catch: (e) =>
      e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) }),
  }).pipe(Effect.flatMap(Schema.decodeUnknown(schema)))

/**
 * A deletion that reports nothing.
 *
 * Separate from `deleteReq` rather than a flag on it: a 204 has no body, so decoding one is not a
 * schema the caller can choose — it is a different exchange. The dry-run form, which *does* answer
 * with its plan, keeps `deleteReq`.
 */
export const deleteNoContent = (url: string): Effect.Effect<void, NetworkError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url, { method: 'DELETE' })
      if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText)
        throw new NetworkError({ status: resp.status, message: text })
      }
    },
    catch: (e) =>
      e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) }),
  })

export const deleteReq = <A, I>(
  url: string,
  schema: Schema.Schema<A, I>,
): Effect.Effect<A, NetworkError | ParseResult.ParseError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url, { method: 'DELETE' })
      if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText)
        throw new NetworkError({ status: resp.status, message: text })
      }
      return resp.json() as Promise<unknown>
    },
    catch: (e) =>
      e instanceof NetworkError ? e : new NetworkError({ status: 0, message: String(e) }),
  }).pipe(Effect.flatMap(Schema.decodeUnknown(schema)))

