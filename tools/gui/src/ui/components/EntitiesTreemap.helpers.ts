/**
 * The ArchiMate vocabulary the entity treemap needs: how an entity is grouped, coloured and weighed.
 *
 * The counterpart of `AssuranceTreemap.helpers` for the architecture surface, and extracted for the
 * same two reasons that one was: the shared `Treemap` must not learn what a domain is, and grouping
 * rules that live inside an SFC cannot be unit-tested — this project's tests run in `node` with no
 * component mounting, so logic in a `.vue` file is reachable only through a browser.
 *
 * **Two axes, in this order: domain, then entity type.** With no domain chosen the treemap groups by
 * ArchiMate domain, which is the coarse question ("where is the weight in this model"). Choose one and
 * it regroups by `subdomain`, which *is* the entity type: an entity is filed at
 * `model/<domain>/<artifact-type>/`, every ontology loader builds that leaf from the artifact type, and
 * `derive_domain` reads the subdomain out of exactly that path segment. The two names are one axis, and
 * `tests/application/test_treemap_second_axis_is_entity_type.py` is what keeps them one.
 *
 * **Sized by total connections**, in and out. That reads as "how much of the model hangs off this",
 * which is the property a reader scanning for load-bearing entities is actually looking for.
 */

import type { EntitySummary } from '../../domain'
import { getDomainColor, getDomainLabel, getEntityConnectionTotal } from '../lib/domains'
import { groupLeaves, type TreemapGroup, type TreemapLeaf } from './Treemap.helpers'

/** Which axis the second level groups on, decided by whether a domain is being browsed. */
export type GroupMode = 'domain' | 'entity-type'

export const groupModeFor = (activeDomain: string): GroupMode =>
  activeDomain ? 'entity-type' : 'domain'

/**
 * The group an entity belongs to under the given mode.
 *
 * `subdomain` is the entity type — see the module docstring. `General` is the fallback for an entity
 * whose path carries no type segment at all, which the verifier treats as malformed; the treemap shows
 * it rather than dropping it, because a silently missing tile is the worse failure.
 */
export const groupNameOf = (entity: EntitySummary, mode: GroupMode): string =>
  mode === 'domain' ? getDomainLabel(entity.domain) : entity.subdomain || 'General'

/**
 * Colour: per domain when grouping by domain, and the browsed domain's own colour when grouping by
 * type — inside one domain every tile shares its hue, so the eye reads the type bands rather than
 * a second, meaningless colour dimension.
 */
export const groupColorOf = (entity: EntitySummary, mode: GroupMode, activeDomain: string): string =>
  mode === 'domain' ? getDomainColor(entity.domain) : getDomainColor(activeDomain)

export const entityTreemapGroups = (
  entities: readonly EntitySummary[],
  activeDomain: string,
): TreemapGroup[] => {
  const mode = groupModeFor(activeDomain)
  return groupLeaves(
    entities,
    (entity): TreemapLeaf => {
      const connections = getEntityConnectionTotal(entity)
      return {
        key: entity.artifact_id,
        label: entity.name || entity.artifact_id,
        meta: `${connections} connections`,
        value: connections,
        color: groupColorOf(entity, mode, activeDomain),
      }
    },
    (entity) => ({
      name: groupNameOf(entity, mode),
      color: groupColorOf(entity, mode, activeDomain),
    }),
  )
}

export const treemapNote = (activeDomain: string): string =>
  'Sized by total connections. Drag to pan, wheel to zoom. '
  + (groupModeFor(activeDomain) === 'domain' ? 'Grouped by domain.' : 'Grouped by entity type.')
