/**
 * An artifact's body, as a reader should see it beside a header that already names the artifact.
 *
 * Every entity file opens its `§content` section with `## <name>` — the writer emits it, and a file
 * read on its own needs a heading. A detail view has already put that name in its own header, so
 * rendering the body unchanged shows the name twice, once large and once larger.
 *
 * Only a heading that *restates the name* is dropped. A body whose first heading says something else
 * is a body with something to say, and removing it would take content away rather than a repetition.
 */

/** Leading ATX heading and the blank line after it, if the heading text is exactly `name`. */
const RESTATEMENT = /^\s*#{1,6}[ \t]+(?<heading>.+?)[ \t]*(?:\r?\n){1,2}/

export const bodyBelowARestatedTitle = (contentText: string, name: string): string => {
  const match = RESTATEMENT.exec(contentText)
  if (match?.groups === undefined) return contentText
  return match.groups.heading.trim() === name.trim()
    ? contentText.slice(match[0].length)
    : contentText
}
