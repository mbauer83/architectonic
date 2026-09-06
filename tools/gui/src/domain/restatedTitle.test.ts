import { describe, expect, it } from 'vitest'
import { bodyBelowARestatedTitle } from './restatedTitle'

describe('a body beside a header that already names the artifact', () => {
  it('drops the heading that restates the name', () => {
    const body = '## Architect\n\nA concrete actor.\n'
    expect(bodyBelowARestatedTitle(body, 'Architect')).toBe('A concrete actor.\n')
  })

  it('keeps a heading that says something else', () => {
    const body = '## Responsibilities\n\nAuthoring.\n'
    expect(bodyBelowARestatedTitle(body, 'Architect')).toBe(body)
  })

  it('matches the name whatever heading level the writer used', () => {
    expect(bodyBelowARestatedTitle('# Architect\n\nText.\n', 'Architect')).toBe('Text.\n')
    expect(bodyBelowARestatedTitle('#### Architect\n\nText.\n', 'Architect')).toBe('Text.\n')
  })

  it('tolerates the surrounding whitespace a name can carry', () => {
    expect(bodyBelowARestatedTitle('##   Architect  \n\nText.\n', ' Architect ')).toBe('Text.\n')
  })

  it('leaves a body with no heading alone', () => {
    expect(bodyBelowARestatedTitle('Just prose.\n', 'Architect')).toBe('Just prose.\n')
  })

  it('leaves an empty body alone rather than failing on it', () => {
    expect(bodyBelowARestatedTitle('', 'Architect')).toBe('')
  })

  it('drops only the first heading, never a later one that repeats the name', () => {
    const body = '## Architect\n\nText.\n\n## Architect\n\nMore.\n'
    expect(bodyBelowARestatedTitle(body, 'Architect')).toBe('Text.\n\n## Architect\n\nMore.\n')
  })

  it('does not treat a hash inside a word as a heading', () => {
    expect(bodyBelowARestatedTitle('#Architect\n\nText.\n', 'Architect')).toBe('#Architect\n\nText.\n')
  })
})
