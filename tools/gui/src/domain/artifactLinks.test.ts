import { describe, expect, it } from 'vitest'
import { artifactRouteForHref } from './artifactLinks'

describe('artifactRouteForHref', () => {
  it('maps a worktree-relative model href to the entity route', () => {
    const href =
      '../../../projects/engineering-quality/model/motivation/requirement/' +
      'REQ@1777135513.nnvsra.write-composable-maintainable-intelligible-code.md'
    expect(artifactRouteForHref(href)).toBe(
      '/entity?id=' +
        encodeURIComponent('REQ@1777135513.nnvsra.write-composable-maintainable-intelligible-code'),
    )
  })

  it('maps a docs href to the document route', () => {
    const href = '../../docs/standard/engineering-quality/STD@1777137196.ItT-3l.general-coding-guidelines.md'
    expect(artifactRouteForHref(href)).toBe(
      '/documents/' + encodeURIComponent('STD@1777137196.ItT-3l.general-coding-guidelines'),
    )
  })

  it('maps a diagram-catalog puml href to the diagram route', () => {
    const href = '../diagram-catalog/diagrams/assurance/CC@1780829796.SOoZQh.assurance-module-components.puml'
    expect(artifactRouteForHref(href)).toBe(
      '/diagram?id=' + encodeURIComponent('CC@1780829796.SOoZQh.assurance-module-components'),
    )
  })

  it('routes an outgoing-file href to the owning entity', () => {
    const href = 'model/motivation/requirement/REQ@1.Ab-12.some-requirement.outgoing.md'
    expect(artifactRouteForHref(href)).toBe('/entity?id=' + encodeURIComponent('REQ@1.Ab-12.some-requirement'))
  })

  it('leaves external and non-artifact links alone', () => {
    expect(artifactRouteForHref('https://example.com/model/REQ@1.Ab.x.md')).toBeNull()
    expect(artifactRouteForHref('mailto:someone@example.com')).toBeNull()
    expect(artifactRouteForHref('//cdn.example.com/REQ@1.Ab.x.md')).toBeNull()
    expect(artifactRouteForHref('#section-heading')).toBeNull()
    expect(artifactRouteForHref('../other-doc.md')).toBeNull()
    expect(artifactRouteForHref('')).toBeNull()
  })

  it('requires a known repository area in the path', () => {
    expect(artifactRouteForHref('somewhere/REQ@1.Ab.x.md')).toBeNull()
  })

  it('tolerates percent-encoded filenames', () => {
    const href = 'model/motivation/requirement/REQ%401.Ab.some-thing.md'
    expect(artifactRouteForHref(href)).toBe('/entity?id=' + encodeURIComponent('REQ@1.Ab.some-thing'))
  })

  describe('same-directory links', () => {
    // One ADR citing another writes the bare filename. There is no `docs/` segment to read the
    // kind from, so the href used to survive unrewritten, the browser resolved it against the
    // current route, and `/documents/ADR@….md` is not a route — an error page.
    const sibling = 'ADR@1780761609.GQWvwi.markdown-file-based-architecture-repository.md'
    const siblingId = 'ADR@1780761609.GQWvwi.markdown-file-based-architecture-repository'

    it('routes a bare filename using the rendering artifact’s area', () => {
      expect(artifactRouteForHref(sibling, 'docs')).toBe('/documents/' + encodeURIComponent(siblingId))
      expect(artifactRouteForHref('REQ@1.Ab.x.md', 'model')).toBe(
        '/entity?id=' + encodeURIComponent('REQ@1.Ab.x'),
      )
    })

    it('carries an anchor through as the route, dropping the fragment from the id', () => {
      expect(artifactRouteForHref(`${sibling}#decision`, 'docs')).toBe(
        '/documents/' + encodeURIComponent(siblingId),
      )
    })

    it('leaves a bare filename alone when the caller names no area', () => {
      expect(artifactRouteForHref(sibling)).toBeNull()
    })

    it('does not apply the area to a path that names a directory it cannot classify', () => {
      // `../elsewhere/X.md` is not a sibling. Guessing the current area for it would route
      // somewhere confidently wrong, which is worse than leaving the link as authored.
      expect(artifactRouteForHref('../elsewhere/ADR@1.Ab.x.md', 'docs')).toBeNull()
      expect(artifactRouteForHref('nested/ADR@1.Ab.x.md', 'docs')).toBeNull()
    })

    it('still prefers an area the path states over the caller’s', () => {
      expect(artifactRouteForHref('../../model/x/REQ@1.Ab.x.md', 'docs')).toBe(
        '/entity?id=' + encodeURIComponent('REQ@1.Ab.x'),
      )
    })
  })
})
