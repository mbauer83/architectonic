/**
 * Pure helpers for `QueryDerivedAttributesPanel.vue`: list mutation, and which `of:` source
 * heads are legal for a given traversal (`relationship.hops` only exists for a
 * relationship-derived traversal — mirrors the backend's
 * `derived-of-source-traversal-mismatch` check).
 */

import type { DerivedAttributeNode, DerivedOfHead, DerivedTraversal } from '../../domain/viewpointBindings'
import { mkDerivedAttribute } from '../../domain/viewpointBindings'

export const addDerivedAttribute = (attributes: readonly DerivedAttributeNode[]): DerivedAttributeNode[] => [
  ...attributes, mkDerivedAttribute(),
]

export const removeDerivedAttributeAt = (
  attributes: readonly DerivedAttributeNode[],
  index: number,
): DerivedAttributeNode[] => attributes.filter((_, i) => i !== index)

export const updateDerivedAttributeAt = (
  attributes: readonly DerivedAttributeNode[],
  index: number,
  patch: Partial<DerivedAttributeNode>,
): DerivedAttributeNode[] => attributes.map((a, i) => (i === index ? { ...a, ...patch } : a))

export const ofHeadOptions = (traversal: DerivedTraversal): readonly DerivedOfHead[] =>
  traversal === 'derived' ? ['none', 'connection', 'endpoint', 'relationship-hops'] : ['none', 'connection', 'endpoint']
