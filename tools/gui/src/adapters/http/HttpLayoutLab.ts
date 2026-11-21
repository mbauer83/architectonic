/**
 * The layout lab's routes, which the backend serves only while `ARCH_LAYOUT_LAB` is set.
 *
 * Outside `/api` and outside the published document, so not in the generated client: a lab is a
 * developer's bench, and nothing of it belongs in the contract the product's client is held to.
 * A lab that is off answers 404 on its status route; the menu shows its entry only on a 200.
 */
import { Effect, Schema } from 'effect'
import { NetworkError } from '../../domain/errors'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import type { Extent } from '../../domain/layout/geometry'
import type { DrawingNode, LabGeometry } from '../../domain/layout/lab/labGeometry'
import { DrawingNodeSchema, LabGeometrySchema } from '../../domain/layout/lab/labGeometry'
import { fetchWithTimeout } from './httpTransport'

const LAB = '/lab/layout'

const labUrl = (path: string): string => new URL(LAB + path, window.location.origin).toString()

const diagramUrl = (artifactId: string, part: string): string =>
  labUrl(`/diagrams/${encodeIdentitySegment(artifactId)}/${part}`)

/** The sentence an error envelope carries — `detail.message`, or a plain `detail` — else the raw body. */
const sentenceOf = (text: string): string => {
  try {
    const { detail } = JSON.parse(text) as { detail?: unknown }
    if (typeof detail === 'string') return detail
    if (typeof detail === 'object' && detail !== null && 'message' in detail && typeof detail.message === 'string') {
      return detail.message
    }
    return text
  } catch {
    return text
  }
}

const refusal = async (response: Response): Promise<NetworkError> => {
  const text = await response.text().catch(() => response.statusText)
  return new NetworkError({ status: response.status, message: sentenceOf(text) })
}

const asNetworkError = (error: unknown): NetworkError =>
  error instanceof NetworkError ? error : new NetworkError({ status: 0, message: String(error) })

/** Whether this backend serves the lab: only a lab that is on answers its status route with JSON. */
export const layoutLabIsOn = async (): Promise<boolean> => {
  try {
    const response = await fetch(labUrl(''))
    if (!response.ok) return false
    const body = (await response.json()) as { enabled?: unknown }
    return body.enabled === true
  } catch {
    return false
  }
}

/** The geometry of PlantUML's own picture of a stored diagram, each part named as a layout names it. */
export const labGeometry = (artifactId: string): Effect.Effect<LabGeometry, NetworkError> =>
  Effect.tryPromise({
    try: async () => {
      const response = await fetchWithTimeout(diagramUrl(artifactId, 'geometry'))
      if (!response.ok) throw await refusal(response)
      return (await response.json()) as unknown
    },
    catch: asNetworkError,
  }).pipe(
    Effect.flatMap(Schema.decodeUnknown(LabGeometrySchema)),
    Effect.mapError((error) =>
      error instanceof NetworkError ? error : new NetworkError({ status: 0, message: String(error) })),
  )

/** A shape the lab resized: PlantUML's drawing of it, where that was drawn, and where it is to go. */
export interface ShapeToReshape {
  readonly drawing: DrawingNode
  readonly box: boolean
  readonly drawn: Extent
  readonly to: Extent
}

const ReshapedSchema = Schema.Struct({ drawings: Schema.Array(DrawingNodeSchema) })

/** Each shape drawn again at its new size by the composer, in the order asked. Nothing is written. */
export const labReshape = (
  shapes: readonly ShapeToReshape[],
): Effect.Effect<readonly DrawingNode[], NetworkError> =>
  Effect.tryPromise({
    try: async () => {
      const response = await fetchWithTimeout(labUrl('/shapes'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shapes }),
      })
      if (!response.ok) throw await refusal(response)
      return (await response.json()) as unknown
    },
    catch: asNetworkError,
  }).pipe(
    Effect.flatMap(Schema.decodeUnknown(ReshapedSchema)),
    Effect.map((answer) => answer.drawings),
    Effect.mapError(asNetworkError),
  )

/** The server's composed picture of the diagram under *layout*, as SVG markup. Nothing is written. */
export const labPicture = (
  artifactId: string, layout: Record<string, unknown>,
): Effect.Effect<string, NetworkError> =>
  Effect.tryPromise({
    try: async () => {
      const response = await fetchWithTimeout(diagramUrl(artifactId, 'picture'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ layout }),
      })
      if (!response.ok) throw await refusal(response)
      return response.text()
    },
    catch: asNetworkError,
  })
