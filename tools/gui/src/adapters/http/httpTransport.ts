import { Effect, Schema, ParseResult } from 'effect'
import { NetworkError, NotFoundError } from '../../domain/errors'

// Shared HTTP transport for the REST adapters: URL building, timeout-bounded fetch,
// and schema-decoded JSON verbs. Adapter files compose these; error mapping to the
// typed domain errors happens here, once.

export const REQUEST_TIMEOUT_MS = 10000

export const buildUrl = (
  path: string,
  params?: Readonly<Record<string, string | number | boolean | undefined>>,
  adminPath?: boolean,
): string => {
  const url = new URL((adminPath ? '/admin/api' : '/api') + path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, String(v))
    }
  }
  return url.toString()
}

export const fetchWithTimeout = async (
  url: string,
  init?: RequestInit,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<Response> => {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(new DOMException(`Timed out after ${timeoutMs}ms`, 'TimeoutError')), timeoutMs)
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
    window.clearTimeout(timeout)
  }
}

export const fetchJson = <A, I>(
  url: string,
  schema: Schema.Schema<A, I>,
  timeoutMs?: number,
): Effect.Effect<A, NetworkError | ParseResult.ParseError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url, undefined, timeoutMs)
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
  timeoutMs?: number,
): Effect.Effect<A, NetworkError | ParseResult.ParseError> =>
  Effect.tryPromise({
    try: async () => {
      const resp = await fetchWithTimeout(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }, timeoutMs)
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

