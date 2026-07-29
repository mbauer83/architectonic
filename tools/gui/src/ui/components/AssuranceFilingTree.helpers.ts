/**
 * The assurance filing tree: group → analysis, with node counts.
 *
 * Three relations, held apart. A **group** files analyses — flat, with no method of its own, which
 * is what distinguishes it from the analyses it holds. An analysis **authors** the nodes it
 * produced (`node.analysis_id`). And an analysis may **participate** in nodes another authored,
 * which is what lets an FMEA reason over an STPA's control structure without copying it.
 *
 * **Two levels, with counts — no node leaves.** The architecture nav shows framework groups and
 * domains with counts and sends you to the table for the entities themselves; this mirrors that.
 * Listing every node in the sidebar turned "no analysis" into a 26-entry fold-out and pushed the
 * analyses — the thing you actually navigate by — off the bottom. The list beside the nav is where
 * nodes belong, and clicking an analysis scopes it.
 *
 * Participation is not a branch here either: a node counted under two analyses would read as two
 * nodes, and the second would look like the copy the whole arrangement exists to avoid. A node's
 * borrowers are shown on the node itself, where "also used by" can say what the relation is.
 *
 * The assurance vocabulary lives here, in the caller. `NavTree` renders the result and names none
 * of it — the shape of a tree is the caller's knowledge, and a shared component that knew about
 * analyses would be one the architecture side could not use.
 */
import type { NavTreeNode } from './NavTree.helpers'
// The scope vocabulary belongs to the surface that reads it; re-exported so the nav has one
// definition of the reserved word rather than a second spelling of it.
import { NO_ANALYSIS_SCOPE } from '../views/AssuranceBrowseView.helpers'

export { NO_ANALYSIS_SCOPE }

export interface AssuranceGroup {
  group_id: string
  name: string
  description?: string
}

export interface AssuranceAnalysis {
  analysis_id: string
  name: string
  method: string
  status?: string
  group_id?: string | null
}

export interface AssuranceTreeNode {
  node_id: string
  name: string
  node_type: string
  analysis_id?: string | null
}

/** Heading for analyses nobody has filed yet. An analysis is worth recording before anyone settles
 *  where it belongs, so being unfiled is a normal state and needs a home in the tree. */
export const UNFILED_LABEL = 'Unfiled'
export const UNFILED_KEY = 'group:unfiled'

/** Heading for nodes belonging to no analysis at all. Nodes are supposed to have one; when the
 *  store holds a stray, hiding it would make it unreachable from this surface entirely. */
export const UNATTRIBUTED_LABEL = 'No analysis'
export const UNATTRIBUTED_KEY = 'analysis:none'

/** Counting key for nodes that name no analysis. Not a group id — nothing files them. */
const NO_ANALYSIS = ''

const byName = <T extends { name: string }>(items: readonly T[]): T[] =>
  [...items].sort((left, right) => left.name.localeCompare(right.name))

/** An analysis, badged with how many nodes it authored. Clicking it scopes the list beside the
 *  nav — more useful than any single node, and it works for an analysis with nothing in it yet. */
const analysisBranch = (analysis: AssuranceAnalysis, nodeCount: number): NavTreeNode => ({
  key: analysis.analysis_id,
  label: analysis.name || analysis.analysis_id,
  badge: `${analysis.method} · ${nodeCount}`,
  to: { path: '/assurance', query: { analysis: analysis.analysis_id } },
})

/**
 * Build the tree.
 *
 * Every group is shown, including an empty one: a group the reader just made and has filed nothing
 * into yet must appear, or creating it looks like it failed.
 */
export const buildFilingTree = (
  groups: readonly AssuranceGroup[],
  analyses: readonly AssuranceAnalysis[],
  nodes: readonly AssuranceTreeNode[],
): NavTreeNode[] => {
  const countByAnalysis = new Map<string, number>()
  for (const node of nodes) {
    const key = node.analysis_id || NO_ANALYSIS
    countByAnalysis.set(key, (countByAnalysis.get(key) ?? 0) + 1)
  }
  const countFor = (analysisId: string) => countByAnalysis.get(analysisId) ?? 0

  const analysesFor = (groupId: string | null): AssuranceAnalysis[] =>
    byName(analyses.filter((analysis) => (analysis.group_id || null) === groupId))

  const branchesFor = (members: readonly AssuranceAnalysis[]): NavTreeNode[] =>
    members.map((analysis) => analysisBranch(analysis, countFor(analysis.analysis_id)))

  const groupBranch = (group: AssuranceGroup): NavTreeNode => {
    const members = analysesFor(group.group_id)
    return {
      key: group.group_id,
      label: group.name || group.group_id,
      badge: String(members.length),
      children: branchesFor(members),
    }
  }

  const unfiled = analysesFor(null)
  const strayCount = countByAnalysis.get(NO_ANALYSIS) ?? 0

  return [
    ...byName(groups).map(groupBranch),
    // Both trailing headings appear only when they hold something: an always-present "Unfiled" that
    // is usually empty is a permanent reminder of nothing.
    ...(unfiled.length > 0
      ? [{
          key: UNFILED_KEY,
          label: UNFILED_LABEL,
          badge: String(unfiled.length),
          children: branchesFor(unfiled),
        }]
      : []),
    // A count, not a fold-out. Nodes belonging to no analysis violate the model's own rule, so the
    // number is worth stating — but it is a defect to go and fix, not a place to browse from, and it
    // does not get more room in the sidebar than the analyses do.
    ...(strayCount > 0
      ? [{
          key: UNATTRIBUTED_KEY,
          label: UNATTRIBUTED_LABEL,
          badge: String(strayCount),
          to: { path: '/assurance', query: { analysis: NO_ANALYSIS_SCOPE } },
        }]
      : []),
  ]
}
