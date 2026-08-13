import type { EntitySummary } from '../../domain'
import { DOMAIN_COLORS, DOMAIN_NAMES, type DomainName } from '../../domain/types.generated'

type ModuleLike = { readonly name: string }

/** What a domain is called. The *colour* is not here: it is the ontology's declaration, generated
 * into `types.generated.ts`, because three hand-written palettes disagreed on every domain and one
 * of them was missing a domain entirely — so the same element was one colour in a rendered diagram
 * and another in the graph explorer. A label is this surface's own business; a colour is not. */
const DOMAIN_LABELS: Partial<Record<DomainName, string>> = {
  motivation: 'Motivation',
  strategy: 'Strategy',
  common: 'Common',
  business: 'Business',
  application: 'Application',
  technology: 'Technology',
  implementation: 'Implementation',
  sysml: 'SysML v2',
}

export { DOMAIN_COLORS }

export const DOMAIN_OPTIONS = [
  { key: '' as string, label: 'All' },
  ...DOMAIN_NAMES
    .filter(n => n !== 'unknown')
    .map(name => ({
      key: name,
      label: DOMAIN_LABELS[name] ?? (name.charAt(0).toUpperCase() + name.slice(1)),
    })),
]

/** The declared colour for a domain, or a neutral grey for one no ontology has coloured. */
export const getDomainColor = (domain?: string) =>
  (domain ? DOMAIN_COLORS[domain] : undefined) ?? '#cbd5e1'

export const getDomainLabel = (domain: string) =>
  DOMAIN_OPTIONS.find(option => option.key === domain)?.label ?? domain

export const getEntityConnectionTotal = (entity: EntitySummary) =>
  (entity.conn_in ?? 0) + (entity.conn_sym ?? 0) + (entity.conn_out ?? 0)

export const friendlyEntityId = (id: string) => {
  const parts = id.split('.')
  return parts.length > 2 ? parts.slice(2).join('.') : id
}

export const FRAMEWORK_GROUPS = [
  {
    key: 'archimate-4',
    moduleName: 'archimate-4-0',
    label: 'ArchiMate 4',
    domains: ['motivation', 'strategy', 'common', 'business', 'application', 'technology', 'implementation'],
  },
  {
    key: 'sysml-v2',
    moduleName: 'sysml_v2_min',
    label: 'SysML v2',
    domains: ['sysml'],
  },
] as const

const DEFAULT_MODULES: readonly ModuleLike[] = [{ name: 'archimate-4-0' }]

const moduleNameSet = (modules?: readonly ModuleLike[]) =>
  new Set((modules ?? DEFAULT_MODULES).map((module) => module.name))

export const frameworkGroupsForModules = (modules?: readonly ModuleLike[]) => {
  const enabled = moduleNameSet(modules)
  return FRAMEWORK_GROUPS.filter((group) => enabled.has(group.moduleName))
}

export const metaOntologyOptionsForModules = (modules?: readonly ModuleLike[]) => [
  { value: '', label: 'No restriction' },
  ...frameworkGroupsForModules(modules).map((group) => ({
    value: group.key,
    label: group.label,
  })),
]

export const domainOptionsForDomains = (domains: Iterable<string>) => {
  const available = new Set(domains)
  return DOMAIN_OPTIONS.filter((option) => option.key && available.has(option.key))
}

export const domainOptionsForModules = (modules?: readonly ModuleLike[]) =>
  domainOptionsForDomains(frameworkGroupsForModules(modules).flatMap((group) => [...group.domains]))

export const softTint = (hex: string, strength = 0.82) => {
  const value = hex.replace('#', '')
  if (value.length !== 6) return hex
  const mix = (offset: number) =>
    Math.round(parseInt(value.slice(offset, offset + 2), 16) * (1 - strength) + 255 * strength)
      .toString(16)
      .padStart(2, '0')
  return `#${mix(0)}${mix(2)}${mix(4)}`
}
