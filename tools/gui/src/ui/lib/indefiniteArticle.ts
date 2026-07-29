/**
 * Indefinite article for a lowercase noun the UI interpolates into prose, so a label reads
 * "an application-component" and "an enterprise-tier definition" rather than "a application-…".
 *
 * A vowel-letter test is enough for the words this is used on — type-name slugs and tier names,
 * every one of which begins with a letter matching its sound (`an outcome`, `an or-junction`,
 * `an unsafe-control-action`, `a module`). None begins with a consonant-sounding vowel (`a unit`,
 * `a one-off`) or a vowel-sounding consonant (`an hour`); should such a word ever reach here it
 * needs a per-word exception, because pronunciation is not derivable from spelling.
 */
export function articleFor(noun: string): 'a' | 'an' {
  return /^[aeiou]/i.test(noun) ? 'an' : 'a'
}

/** The noun with its indefinite article, e.g. `an application-component`. */
export function withArticle(noun: string): string {
  return `${articleFor(noun)} ${noun}`
}
