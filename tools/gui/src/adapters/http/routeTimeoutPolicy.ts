import policy from './routeTimeoutPolicy.json'

/**
 * Named timeout classes for the REST surface, shared by the HTTP client and the dev proxy.
 *
 * The two used to be set independently, and they already disagreed: the proxy gave the entity
 * neighbourhood read 65 s while the client gave it the 10 s default, and gave
 * `/api/diagrams/{id}/viewpoint-projection` the 10 s generic rule while the client allowed 60 s.
 * Whichever budget is shorter is the one the user experiences, so a disagreement is not a
 * redundancy — it silently overrides the decision someone made on the other side.
 *
 * The classification therefore lives in `routeTimeoutPolicy.json`, **generated from the REST
 * route-policy manifest** and checked like any other generated artifact. Data rather than a module
 * because the two consumers live in different TypeScript programs — the app and the Vite config —
 * and a module can only be owned by one of them. Neither derives anything from it: the proxy
 * context patterns and their ordering are computed where the manifest lives, so two readings of one
 * document cannot diverge.
 *
 * **The proxy is classified per template, the client per operation.** A proxy matches a URL and
 * cannot see the method, so a template whose write is long-running lends its budget to its read
 * as well. That direction is safe: too generous a proxy budget lets the client's own abort be
 * what the user sees, while too tight a one severs a request the client was still waiting on.
 */

export type TimeoutClass = 'default' | 'derived-graph' | 'streaming'
export type NonDefaultTimeoutClass = Exclude<TimeoutClass, 'default'>

/** Client abort budget per class. `null` means never abort — the stream is meant to stay open. */
export const TIMEOUT_BUDGET_MS: Record<TimeoutClass, number | null> = policy.budgetMs

/**
 * How much longer the dev proxy waits than the client does.
 *
 * The client's own `AbortController` should be what ends a request that is taking too long,
 * because it produces a typed timeout the UI can explain. A proxy that gives up first produces
 * `ERR_EMPTY_RESPONSE`, which looks like the backend crashed.
 */
export const PROXY_HEADROOM_MS: number = policy.proxyHeadroomMs

/**
 * Canonical route templates per non-default class, in the manifest's `{param}` spelling.
 *
 * Kept as templates rather than prefixes because identity is now *inside* the path:
 * `/api/entities/{artifact_id}/neighbors` has no prefix that distinguishes it from a plain
 * entity read, so the prefix contexts a dev proxy usually uses cannot express it.
 */
export const TEMPLATES_BY_TIMEOUT_CLASS: Record<NonDefaultTimeoutClass, readonly string[]> =
  policy.templates

/**
 * Retired templates still mounted, and the class they keep until their rename lands.
 *
 * A rename has to move the proxy rule in the same commit as the decorator, so this list shrinks
 * entry by entry alongside the migration ledger and is empty when it is done. Without it, the
 * window between "canonical template declared" and "route actually renamed" would leave a
 * long-running read on the generic budget it demonstrably exceeds.
 */
export const LEGACY_TEMPLATES_BY_TIMEOUT_CLASS: Record<
  NonDefaultTimeoutClass,
  readonly string[]
> = policy.legacyTemplates

/** Every template in a class, canonical and not-yet-migrated alike. */
export const allTemplatesFor = (timeoutClass: NonDefaultTimeoutClass): readonly string[] => [
  ...TEMPLATES_BY_TIMEOUT_CLASS[timeoutClass],
  ...LEGACY_TEMPLATES_BY_TIMEOUT_CLASS[timeoutClass],
]

/**
 * Dev-proxy context keys per class, most specific first — the patterns, already derived.
 *
 * Vite reads a context beginning with `^` as a regular expression and uses the first key that
 * matches, so a longer template has to be offered before a shorter one it extends. That ordering,
 * and the template-to-pattern translation, are done where the manifest lives; nothing here derives
 * anything, which is what keeps the two frontend readings of this document identical.
 */
export const PROXY_CONTEXTS: Record<NonDefaultTimeoutClass, readonly string[]> =
  policy.proxyContexts

export const proxyContextsFor = (timeoutClass: NonDefaultTimeoutClass): readonly string[] =>
  PROXY_CONTEXTS[timeoutClass]

const compiled: ReadonlyArray<readonly [NonDefaultTimeoutClass, readonly RegExp[]]> = [
  ['streaming', PROXY_CONTEXTS.streaming.map((pattern) => new RegExp(pattern))],
  ['derived-graph', PROXY_CONTEXTS['derived-graph'].map((pattern) => new RegExp(pattern))],
]

/** The class a concrete request path falls into. `streaming` wins over `derived-graph`. */
export const timeoutClassForPath = (pathname: string): TimeoutClass => {
  for (const [timeoutClass, patterns] of compiled) {
    if (patterns.some((pattern) => pattern.test(pathname))) return timeoutClass
  }
  return 'default'
}

/** The client abort budget for a concrete request path, or `null` for a stream. */
export const timeoutBudgetForPath = (pathname: string): number | null =>
  TIMEOUT_BUDGET_MS[timeoutClassForPath(pathname)]

/** The dev proxy's budget for a class: the client's, plus headroom. */
export const proxyTimeoutMs = (timeoutClass: NonDefaultTimeoutClass): number | undefined => {
  const budget = TIMEOUT_BUDGET_MS[timeoutClass]
  return budget === null ? undefined : budget + PROXY_HEADROOM_MS
}

/** The generic fallback the dev proxy applies to everything unclassified. */
export const DEFAULT_PROXY_TIMEOUT_MS = (TIMEOUT_BUDGET_MS.default ?? 0) + PROXY_HEADROOM_MS
