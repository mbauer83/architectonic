/**
 * Pure logic for ingesting an SBOM against an architecture entity.
 *
 * The admissible anchor types are FETCHED from the backend, never redeclared
 * here: the same vocabulary governs the REST and MCP surfaces, and a client copy
 * would let the GUI offer an ingest the API refuses (or hide one it would accept).
 */

export interface IngestSubmission {
  bomText: string
  vulnText: string
}

export interface ParsedIngest {
  bom?: Record<string, unknown>
  vulnerabilities?: unknown[]
  error?: string
}

export const canAnchorSignals = (
  entityType: string | undefined, admissible: readonly string[],
): boolean => !!entityType && admissible.includes(entityType)

/**
 * Coerce an untyped response field to a display string. Only primitives render;
 * an object or array yields the fallback rather than the `[object Object]` default
 * stringification, so a malformed body never leaks that into user-facing text.
 */
export const asText = (value: unknown, fallback = ''): string => {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return fallback
}

/**
 * Parse a submission into the request body, or a single message naming the first
 * problem. Vulnerability records are OPTIONAL — a BOM alone is a valid inventory
 * snapshot with no findings, which is a legitimate thing to want.
 */
export const parseSubmission = (submission: IngestSubmission): ParsedIngest => {
  if (!submission.bomText.trim()) return { error: 'Paste a CycloneDX SBOM (JSON) first.' }
  let bom: unknown
  try {
    bom = JSON.parse(submission.bomText)
  } catch (e) {
    return { error: `The SBOM is not valid JSON: ${String(e)}` }
  }
  if (!bom || typeof bom !== 'object' || Array.isArray(bom)) {
    return { error: 'Expected a JSON object (a CycloneDX SBOM document).' }
  }

  let vulnerabilities: unknown[] = []
  if (submission.vulnText.trim()) {
    let parsed: unknown
    try {
      parsed = JSON.parse(submission.vulnText)
    } catch (e) {
      return { error: `The vulnerability records are not valid JSON: ${String(e)}` }
    }
    if (!Array.isArray(parsed)) {
      return { error: 'Expected a JSON array of OSV vulnerability records.' }
    }
    vulnerabilities = parsed
  }
  return { bom: bom as Record<string, unknown>, vulnerabilities }
}

/**
 * Render an ingest outcome.
 *
 * Reports what the snapshot HOLDS, not what was submitted, and names the alias
 * collapse when they differ: telling a user "41 findings" when a read returns 24
 * is the defect the backend counts were changed to prevent. Non-success outcomes
 * are described in their own terms — a replay wrote nothing, a conflict means a
 * reused request id — rather than as a generic failure.
 */
export const describeOutcome = (status: number, body: Record<string, unknown>): string => {
  const outcome = asText(body['status'])
  const num = (key: string): number => {
    const value = body[key]
    return typeof value === 'number' ? value : 0
  }
  switch (outcome) {
    case 'activated': {
      const collapsed = num('collapsed_finding_count')
      const head = `Snapshot ${asText(body['snapshot_id'])} is now active — `
        + `${num('component_count')} components, ${num('finding_count')} findings `
        + `(of ${num('submitted_finding_count')} submitted`
      return collapsed > 0
        ? `${head}; ${collapsed} collapsed onto an existing vulnerability by alias).`
        : `${head}).`
    }
    case 'replayed':
      return `Already ingested under this request id — snapshot `
        + `${asText(body['snapshot_id'])}. Nothing was written.`
    case 'conflict':
      return 'That request id was already used with a different payload; nothing was '
        + 'written. Submit with a new request id.'
    case 'invalid': {
      const errors = Array.isArray(body['errors']) ? body['errors'] : []
      const detail = errors
        .map((entry) => {
          const record = entry as Record<string, unknown>
          return `${asText(record['field'])}: ${asText(record['message'])}`
        })
        .join('; ')
      return `Rejected — ${detail || 'validation failed'}.`
    }
    case 'failed':
      return `The ingest failed and was recorded as failed: `
        + `${asText(body['reason'], 'unknown reason')}. Retry with a new request id.`
    default:
      return `Unexpected response from the ingest endpoint (HTTP ${status}).`
  }
}

/** Whether an outcome means the store changed, and the views should re-read. */
export const changedTheStore = (body: Record<string, unknown>): boolean =>
  asText(body['status']) === 'activated'


/**
 * The idempotency key for one submission attempt.
 *
 * `request_id` is a machine concept — it names THIS submission so a retry after a
 * timeout returns the original outcome instead of creating a second snapshot. A
 * person pasting a bill of materials has no way to invent a meaningful one, so the
 * form generates it rather than asking.
 *
 * It is derived from the pasted content, which is what makes retry safe: pressing
 * Ingest twice on the same paste is idempotent (the second call replays), while
 * editing the BOM and ingesting again is genuinely a new request.
 */
export const requestIdFor = (submission: IngestSubmission): string => {
  const material = `${submission.bomText}\u0000${submission.vulnText}`
  let hash = 0x811c9dc5
  for (let i = 0; i < material.length; i += 1) {
    hash ^= material.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return `gui-${hash.toString(16).padStart(8, '0')}`
}
