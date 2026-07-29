/** Barrel re-export — schemas live in `./schemas/*`, split by domain area. Kept as one
 * public import path (`from '../../domain/schemas'` / `from '../domain'`) so nothing outside
 * `domain/` needs to know about the split. */
export * from './schemas/stats'
export * from './schemas/connections'
export * from './schemas/entities'
export * from './schemas/search'
export * from './schemas/assurance'
export * from './schemas/documents'
export * from './schemas/diagram-types'
export * from './schemas/viewpointReferences'
export * from './schemas/viewpoints'
export * from './schemas/diagrams'
export * from './schemas/write-results'
export * from './schemas/promotion'
export * from './schemas/sync-status'
export * from './schemas/server'
export * from './schemas/groups'
export * from './schemas/authoring-guidance'
