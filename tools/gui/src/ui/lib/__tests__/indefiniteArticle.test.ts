import { describe, it, expect } from 'vitest'
import { articleFor, withArticle } from '../indefiniteArticle'

/**
 * Covers the words this is actually interpolated into UI prose: entity-type slugs and viewpoint
 * tier names. The vowel-initial cases are the ones the wizard used to get wrong ("a
 * application-component").
 */
describe('articleFor', () => {
  it.each(['application-component', 'application-interface', 'artifact', 'assessment', 'outcome',
    'or-junction', 'and-junction', 'event', 'equipment', 'unsafe-control-action', 'enterprise',
    'engagement'])('uses "an" before %s', (noun) => {
    expect(articleFor(noun)).toBe('an')
  })

  it.each(['requirement', 'goal', 'stakeholder', 'value-stream', 'data-object', 'process',
    'module'])('uses "a" before %s', (noun) => {
    expect(articleFor(noun)).toBe('a')
  })

  it('is case-insensitive on the leading letter', () => {
    expect(articleFor('Outcome')).toBe('an')
    expect(articleFor('Goal')).toBe('a')
  })
})

describe('withArticle', () => {
  it('joins the article to the noun', () => {
    expect(withArticle('application-component')).toBe('an application-component')
    expect(withArticle('requirement')).toBe('a requirement')
  })
})
