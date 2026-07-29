import type { EntitySummary } from '../../domain'
import { DOMAIN_NAMES, type DomainName } from '../../domain/types.generated'

type DomainDisplayConfig = { color: string; label: string }
type ModuleLike = { readonly name: string }

const DOMAIN_CONFIG: Partial<Record<DomainName, DomainDisplayConfig>> = {
  motivation:     { color: '#d8c1e4', label: 'Motivation' },
  strategy:       { color: '#efbd5d', label: 'Strategy' },
  common:         { color: '#e8e5d3', label: 'Common' },
  business:       { color: '#f4de7f', label: 'Business' },
  application:    { color: '#b6d7e1', label: 'Application' },
  technology:     { color: '#c3e1b4', label: 'Technology' },
  implementation: { color: '#f4c896', label: 'Implementation' },
  sysml:          { color: '#c0d4ee', label: 'SysML v2' },
}

export const DOMAIN_COLORS: Partial<Record<DomainName, string>> = Object.fromEntries(
  (Object.entries(DOMAIN_CONFIG) as [DomainName, DomainDisplayConfig][]).map(([k, v]) => [k, v.color]),
)

export const DOMAIN_OPTIONS = [
  { key: '' as string, label: 'All' },
  ...DOMAIN_NAMES
    .filter(n => n !== 'unknown')
    .map(name => ({
      key: name,
      label: DOMAIN_CONFIG[name]?.label ?? (name.charAt(0).toUpperCase() + name.slice(1)),
    })),
]

export const getDomainColor = (domain?: string) =>
  (domain ? DOMAIN_COLORS[domain as DomainName] : undefined) ?? '#cbd5e1'

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
