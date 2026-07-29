/**
 * Rendered entity content, with the heading that merely repeats the entity's own name removed.
 *
 * Every sidebar that shows an entity already names it above the content, and the markdown a
 * repository entity carries almost always opens with that same name as its first heading — so
 * rendering it verbatim prints the name twice, one line apart. The diagram sidebar had solved
 * this for itself; the graph sidebar had not, and gained a second copy the moment its headline
 * started naming the entity too. One definition, used by both.
 */

/** Whitespace-insensitive comparison, so a wrapped heading still matches the name. */
const normalized = (value: string): string => value.trim().replace(/\s+/g, ' ')

export const contentHtmlWithoutTitleHeading = (
  contentHtml: string | null | undefined,
  entityName: string,
): string | null => {
  if (!contentHtml) return null
  // No DOM (SSR, unit environment without one): hand back the content untouched rather than
  // guess at its structure with a regex. Showing the heading is a blemish; corrupting the
  // markup would be a defect.
  if (typeof DOMParser === 'undefined') return contentHtml

  const doc = new DOMParser().parseFromString(`<div>${contentHtml}</div>`, 'text/html')
  const wrapper = doc.body.firstElementChild
  if (!wrapper) return contentHtml
  const firstHeading = wrapper.querySelector('h1, h2, h3, h4, h5, h6')
  if (!firstHeading) return contentHtml

  if (normalized(firstHeading.textContent ?? '') === normalized(entityName)) firstHeading.remove()
  return wrapper.innerHTML
}
