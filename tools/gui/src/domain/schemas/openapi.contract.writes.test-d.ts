import { describe, expectTypeOf, it } from 'vitest'
import type { ModelRepository } from '../../ports/ModelRepository'
import type { components } from './openapi.generated'

/**
 * The **request** side of the contract, which nothing checked.
 *
 * Response payloads are asserted against the served document field by field, and have been for a
 * long time. The bodies the client sends were hand-written on both sides and compared by nobody —
 * so the connection forms sent `specialization` while every write body declares `specializations`,
 * and because those bodies are `extra="forbid"`, the server answered 422 rather than ignoring it.
 * Editing any connection from the GUI failed outright, and creating one with a specialization did
 * too, taking whatever else the form held — a polarity, most visibly — down with it.
 *
 * Nothing caught it. The component tests exercised the form and passed either way, because the
 * field name only matters at a boundary neither side of the test crosses.
 *
 * **Assignability, not equality.** A client may legitimately omit an optional field; what it may
 * never do is send one the body does not declare, which is exactly what `extra="forbid"` refuses
 * at runtime and what this refuses at compile time.
 */

/**
 * The field names a client can send that the body does not declare.
 *
 * Key sets rather than value assignability: what `extra="forbid"` refuses is an unknown *name*,
 * and comparing value types drags in the nullability the generator emits for every optional field,
 * which is variance noise about a question nobody asked.
 */
type UndeclaredFields<Client, Body> = Exclude<keyof Client, keyof Body>

describe('what the client may send is what the server declares', () => {
  it('adds a connection', () => {
    expectTypeOf<
      UndeclaredFields<
        Parameters<ModelRepository['addConnection']>[0],
        components['schemas']['AddConnectionBody']
      >
    >().toEqualTypeOf<never>()
  })

  it('edits a connection', () => {
    expectTypeOf<
      UndeclaredFields<
        Parameters<ModelRepository['editConnection']>[1],
        components['schemas']['EditConnectionBody']
      >
    >().toEqualTypeOf<never>()
  })

  it('creates an entity', () => {
    expectTypeOf<
      UndeclaredFields<
        Parameters<ModelRepository['createEntity']>[0],
        components['schemas']['CreateEntityBody']
      >
    >().toEqualTypeOf<never>()
  })

  it('edits an entity', () => {
    expectTypeOf<
      UndeclaredFields<
        Parameters<ModelRepository['editEntity']>[1],
        components['schemas']['EditEntityBody']
      >
    >().toEqualTypeOf<never>()
  })
})
