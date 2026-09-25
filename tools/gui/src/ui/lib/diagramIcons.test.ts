import { describe, expect, it } from 'vitest'
import {
  instanceIconOf, localIconKeyFor, typeIconOf, typesWithIcons, withInstanceIcon, withLocalIcon, withTypeIcon,
} from './diagramIcons'
import { withoutInstanceStatements } from './diagramStatements'

const MARK = 'ICO@1790000001.mark01'

describe('stating an icon', () => {
  it('stores a bare reference without a style, and a mapping with one', () => {
    const plain = withInstanceIcon({}, 'n1', { icon: MARK })
    const styled = withTypeIcon(plain, 'technology-node', { icon: MARK, style: 'figure' })

    expect(styled).toEqual({ display_icons: { n1: MARK }, type_icons: { 'technology-node': { icon: MARK, style: 'figure' } } })
    expect(instanceIconOf(styled, 'n1')).toEqual({ icon: MARK })
    expect(typeIconOf(styled, 'technology-node')).toEqual({ icon: MARK, style: 'figure' })
    expect(typesWithIcons(styled)).toEqual(['technology-node'])
  })

  it('withdraws with null, keeping the key so a merge can carry the withdrawal', () => {
    expect(withInstanceIcon({ display_icons: { n1: MARK } }, 'n1', null)).toEqual({ display_icons: {} })
  })

  it('reads a statement it cannot understand as none', () => {
    expect(instanceIconOf({ display_icons: { n1: 7, n2: { style: 'badge' } } }, 'n1')).toBeUndefined()
    expect(instanceIconOf({ display_icons: [MARK] }, 'n1')).toBeUndefined()
  })
})

describe('an upload the diagram holds for itself', () => {
  const upload = { name: 'Azure Kubernetes Service', content_base64: 'AAAA', source_format: 'png' as const }

  it('is held under a slug of its name and named local:<key>', () => {
    const held = withLocalIcon({}, upload)

    expect(held.icon).toBe('local:azure-kubernetes-service')
    expect(held.diagramEntities).toEqual({ icons: { 'azure-kubernetes-service': upload } })
  })

  it('gets a key of its own beside one already taken', () => {
    expect(localIconKeyFor({ icons: { 'azure-kubernetes-service': {} } }, upload.name)).toBe('azure-kubernetes-service-2')
    expect(localIconKeyFor({}, '***')).toBe('icon')
  })
})

describe('an instance that is gone', () => {
  it('takes its label and its icon with it, and leaves the type statements', () => {
    const data = {
      display_labels: { n1: 'One', n2: 'Two' }, display_icons: { n1: MARK }, type_icons: { node: MARK },
    }

    expect(withoutInstanceStatements(data, ['n1'])).toEqual({
      display_labels: { n2: 'Two' }, display_icons: {}, type_icons: { node: MARK },
    })
  })
})
