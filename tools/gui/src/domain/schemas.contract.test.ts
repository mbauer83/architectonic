import { describe, expect, it } from 'vitest'
import { Schema } from 'effect'
import {
  AssuranceNodeListSchema,
  DiagramContextSchema,
  SearchResultSchema,
} from './schemas'

// Reduced, representative responses captured from the running backend on 2026-06-21.
// Fields are preserved verbatim; large arrays and source bodies are reduced to one item.
const SEARCH_RESPONSE = {
  query: 'document',
  hits: [{
    score: 1.0030534374868902,
    record_type: 'document',
    artifact_id: 'ADR@1780761609.GQWvwi.markdown-file-based-architecture-repository',
    name: 'Markdown File-Based Architecture Repository',
    status: 'accepted',
    path: '/architecture-repository/docs/adr/markdown-file-based-architecture-repository.md',
  }],
}

const ASSURANCE_NODES_RESPONSE = {
  nodes: [{
    node_id: 'LSS@1781181599.wczn.d5fa5c',
    node_type: 'loss',
    name: 'Disclosure of confidential assurance evidence to unauthorized parties',
    status: 'draft',
    tlp: 'TLP:AMBER',
    concern_class: 'security',
    disposition: null,
    uca_type: null,
    binding_status: null,
    node_role: null,
    attributes_json: '{}',
    content_text: 'Assurance evidence is disclosed to an unauthorized party.',
    created_at: '2026-06-11T12:39:59Z',
    updated_at: '2026-06-11T12:39:59Z',
    created_by: '',
    analysis_id: null,
  }],
  count: 1,
  visibility_limited: true,
}

const C4_CONTEXT_RESPONSE = {
  diagram: {
    artifact_id: 'CC@1780829785.Z_fI-N.amp-containers',
    artifact_type: 'diagram',
    name: 'AMP — Containers',
    diagram_type: 'c4-container',
    version: '0.1.0',
    status: 'draft',
    record_type: 'diagram',
    path: '/diagram-catalog/diagrams/amp-containers.puml',
    content_snippet: '',
  },
  entities: [{
    artifact_id: 'ROL@1776633082.udXPfB.ai-agent',
    artifact_type: 'role',
    name: 'AI Agent',
    version: '0.1.0',
    status: 'draft',
    domain: 'common',
    subdomain: 'role',
    path: '/model/common/role/ai-agent.md',
    is_global: false,
    group: 'uncategorized',
    display_alias: 'ROL_udXPfB',
  }],
  connections: [],
  candidate_connections: [],
  suggested_entities: [],
  explicit_connection_pairs: [['ROL_udXPfB', 'APP_Ne0utf']],
  generation: 12,
  etag: 'W/"model-12-91e6f958e17e7b4b4901"',
  c4_navigation: {
    current_level: 2,
    scope_entity_id: 'APP@1780783671.hkrdtm.architecture-management-platform',
    scope_entity_name: 'Architecture Management Platform',
    parent_diagrams: [{
      diagram_id: 'CSC@1780829783.z8RRON.amp-system-context',
      diagram_name: 'AMP — System Context',
      diagram_type: 'c4-system-context',
    }],
    child_diagrams: [],
  },
}

describe('captured backend response contracts', () => {
  it('decodes a search response containing a document hit', () => {
    expect(Schema.decodeUnknownSync(SearchResultSchema)(SEARCH_RESPONSE).hits[0].record_type)
      .toBe('document')
  })

  it('decodes a confidential assurance-node response', () => {
    expect(Schema.decodeUnknownSync(AssuranceNodeListSchema)(ASSURANCE_NODES_RESPONSE).nodes[0].tlp)
      .toBe('TLP:AMBER')
  })

  it('decodes a model-backed C4 diagram context', () => {
    expect(Schema.decodeUnknownSync(DiagramContextSchema)(C4_CONTEXT_RESPONSE).c4_navigation?.current_level)
      .toBe(2)
  })

  it('rejects wire drift in a required field', () => {
    const drifted = { ...ASSURANCE_NODES_RESPONSE, count: '1' }
    expect(() => Schema.decodeUnknownSync(AssuranceNodeListSchema)(drifted)).toThrow()
  })
})
