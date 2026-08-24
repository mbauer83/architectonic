// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'

import { renderMarkdown } from '../MarkdownService'

/**
 * What happens to angle brackets in repository prose.
 *
 * `marked` passes raw HTML through and DOMPurify then removes any element its allowlist does not
 * know. An unknown element with no children — `<slug>` — therefore vanished completely: the entity
 * detail page showed `projects//model/` where the source says `projects/<slug>/model/`, with nothing
 * to indicate that anything had been dropped.
 *
 * Authors write those brackets as placeholders, which is most of what angle brackets are for in this
 * corpus: path patterns, ArchiMate type names, id shapes. None of the repository's own prose relies on
 * real inline HTML. So a tag the sanitiser rejects is authored *text*, and the fix is to show it
 * escaped rather than to delete it — visible, inert, and no longer silently lossy.
 *
 * The sanitiser stays the authority on what is markup. This only changes what happens to what it
 * rejects: escaped and kept, instead of removed.
 */

describe('a tag the sanitiser does not allow', () => {
  it('is shown rather than dropped', () => {
    const html = renderMarkdown('Path patterns: projects/<slug>/model/')

    expect(html).toContain('&lt;slug&gt;')
  })

  it('keeps every placeholder in a path that has several', () => {
    const html = renderMarkdown('docs/<doc-type>/<slug>/ (document-collection)')

    expect(html).toContain('&lt;doc-type&gt;')
    expect(html).toContain('&lt;slug&gt;')
  })

  it('keeps an underscored type name', () => {
    expect(renderMarkdown('a <work_package> groups them')).toContain('&lt;work_package&gt;')
  })

  it('does not execute a script, and does not silently swallow it either', () => {
    const html = renderMarkdown('before <script>alert(1)</script> after')

    // Escaped, so the browser renders text. The assertion is on both halves: inert *and* present.
    expect(html).not.toMatch(/<script/)
    expect(html).toContain('&lt;script&gt;')
    expect(html).toContain('before')
    expect(html).toContain('after')
  })

  it('strips an event handler from a tag the allowlist does allow', () => {
    // A tag the sanitiser accepts stays markup — the authority is unchanged. `img` is allowed, so
    // this asserts the attribute is gone rather than the element.
    const html = renderMarkdown('<img src=x onerror=alert(1)>')

    expect(html).not.toMatch(/onerror/i)
    expect(html).toContain('<img')
  })
})

describe('what markdown still does', () => {
  it('renders emphasis as markup', () => {
    expect(renderMarkdown('**bold** and *thin*')).toContain('<strong>bold</strong>')
  })

  it('renders a list as a list', () => {
    const html = renderMarkdown('- one\n- two\n')

    expect(html).toContain('<ul>')
    expect(html).toContain('<li>one</li>')
  })

  it('renders a table as a table', () => {
    const html = renderMarkdown('| a | b |\n| --- | --- |\n| 1 | 2 |\n')

    expect(html).toContain('<table>')
    expect(html).toContain('<td>1</td>')
  })

  it('still escapes a tag inside a code span, without doubling it', () => {
    const html = renderMarkdown('use `<slug>` here')

    expect(html).toContain('<code>&lt;slug&gt;</code>')
    expect(html).not.toContain('&amp;lt;')
  })

  it('leaves a less-than that starts no tag alone', () => {
    expect(renderMarkdown('when a < b holds')).toContain('a &lt; b')
  })

  it('still rewrites a repository-relative artifact link to its route', () => {
    const html = renderMarkdown(
      '[x](../../model/motivation/requirement/REQ@1777135513.nnvsra.write-code.md)', 'model')

    expect(html).toContain('/entities/REQ%401777135513.nnvsra.write-code')
  })
})
