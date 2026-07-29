import { describe, expect, it } from 'vitest'
import { toGuiArtifactHref } from './matrixMarkdown'

describe('renderMatrixMarkdown', () => {
  it('routes model links to entity detail', () => {
    const markdown = '[Assurance Service](model/common/service/SRV@1780656241.ooK3YN.assurance-service.md)'
    const href = markdown.slice(markdown.indexOf('(') + 1, -1)
    expect(toGuiArtifactHref(href)).toBe('/entity?id=SRV@1780656241.ooK3YN.assurance-service')
  })

  it('supports artifact random segments containing hyphens and underscores', () => {
    const href = [
      'model/application/application-component/',
      'APP@1780656430.m-U5S1.assurance-mcp-endpoint-adapter.md)',
    ].join('').slice(0, -1)
    expect(toGuiArtifactHref(href)).toBe(
      '/entity?id=APP@1780656430.m-U5S1.assurance-mcp-endpoint-adapter',
    )
  })
})
