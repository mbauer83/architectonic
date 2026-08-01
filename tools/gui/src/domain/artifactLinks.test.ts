import { describe, expect, it } from 'vitest'
import { artifactTargetForHref } from './artifactLinks'

/** The parsing only. What a target is *routed* to is the router adapter's, and is asserted in
 * `ui/router/artifactLinkRoutes.test.ts` — this module no longer knows what a Vue path looks like. */
describe('artifactTargetForHref', () => {
  it('maps a worktree-relative model href to the entity route', () => {
    const href =
      '../../../projects/engineering-quality/model/motivation/requirement/' +
      'REQ@1777135513.nnvsra.write-composable-maintainable-intelligible-code.md'
    expect(artifactTargetForHref(href)).toEqual({
      area: 'model',
      id: 'REQ@1777135513.nnvsra.write-composable-maintainable-intelligible-code',
    })
  })

  it('maps a docs href to the document route', () => {
    const href = '../../docs/standard/engineering-quality/STD@1777137196.ItT-3l.general-coding-guidelines.md'
    expect(artifactTargetForHref(href)).toEqual({
      area: 'docs',
      id: 'STD@1777137196.ItT-3l.general-coding-guidelines',
    })
  })

  it('maps a diagram-catalog puml href to the diagram route', () => {
    const href = '../diagram-catalog/diagrams/assurance/CC@1780829796.SOoZQh.assurance-module-components.puml'
    expect(artifactTargetForHref(href)).toEqual({
      area: 'diagram-catalog',
      id: 'CC@1780829796.SOoZQh.assurance-module-components',
    })
  })

  it('routes an outgoing-file href to the owning entity', () => {
    const href = 'model/motivation/requirement/REQ@1.Ab-12.some-requirement.outgoing.md'
    expect(artifactTargetForHref(href)).toEqual({ area: 'model', id: 'REQ@1.Ab-12.some-requirement' })
  })

  it('leaves external and non-artifact links alone', () => {
    expect(artifactTargetForHref('https://example.com/model/REQ@1.Ab.x.md')).toBeNull()
    expect(artifactTargetForHref('mailto:someone@example.com')).toBeNull()
    expect(artifactTargetForHref('//cdn.example.com/REQ@1.Ab.x.md')).toBeNull()
    expect(artifactTargetForHref('#section-heading')).toBeNull()
    expect(artifactTargetForHref('../other-doc.md')).toBeNull()
    expect(artifactTargetForHref('')).toBeNull()
  })

  it('requires a known repository area in the path', () => {
    expect(artifactTargetForHref('somewhere/REQ@1.Ab.x.md')).toBeNull()
  })

  it('tolerates percent-encoded filenames', () => {
    const href = 'model/motivation/requirement/REQ%401.Ab.some-thing.md'
    expect(artifactTargetForHref(href)).toEqual({ area: 'model', id: 'REQ@1.Ab.some-thing' })
  })

  describe('same-directory links', () => {
    // One ADR citing another writes the bare filename. There is no `docs/` segment to read the
    // kind from, so the href used to survive unrewritten, the browser resolved it against the
    // current route, and `/documents/ADR@….md` is not a route — an error page.
    const sibling = 'ADR@1780761609.GQWvwi.markdown-file-based-architecture-repository.md'
    const siblingId = 'ADR@1780761609.GQWvwi.markdown-file-based-architecture-repository'

    it('routes a bare filename using the rendering artifact’s area', () => {
      expect(artifactTargetForHref(sibling, 'docs')).toEqual({ area: 'docs', id: siblingId })
      expect(artifactTargetForHref('REQ@1.Ab.x.md', 'model')).toEqual({ area: 'model', id: 'REQ@1.Ab.x' })
    })

    it('drops the fragment from the id', () => {
      expect(artifactTargetForHref(`${sibling}#decision`, 'docs')).toEqual({ area: 'docs', id: siblingId })
    })

    it('leaves a bare filename alone when the caller names no area', () => {
      expect(artifactTargetForHref(sibling)).toBeNull()
    })

    it('does not apply the area to a path that names a directory it cannot classify', () => {
      // `../elsewhere/X.md` is not a sibling. Guessing the current area for it would route
      // somewhere confidently wrong, which is worse than leaving the link as authored.
      expect(artifactTargetForHref('../elsewhere/ADR@1.Ab.x.md', 'docs')).toBeNull()
      expect(artifactTargetForHref('nested/ADR@1.Ab.x.md', 'docs')).toBeNull()
    })

    it('still prefers an area the path states over the caller’s', () => {
      expect(artifactTargetForHref('../../model/x/REQ@1.Ab.x.md', 'docs')).toEqual({
        area: 'model',
        id: 'REQ@1.Ab.x',
      })
    })
  })
})
