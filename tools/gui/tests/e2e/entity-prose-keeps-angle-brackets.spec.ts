import { expect, test } from '@playwright/test'

/**
 * Angle brackets in repository prose survive rendering.
 *
 * `marked` passes raw HTML through and DOMPurify removes any element its allowlist does not know,
 * keeping the children. An element with no children vanished completely — so the Group Directory
 * entity, whose summary reads `projects/<slug>/model/`, rendered as `projects//model/` with nothing
 * to say that anything had been dropped. Angle brackets here are placeholders: path shapes, type
 * names, id forms.
 *
 * Asserted against a real entity of this repository rather than a fixture, because the defect was in
 * the pipeline that renders real content and a fixture would have to reproduce the shape to catch it.
 * Both halves: the placeholder present, and the collapsed form absent — a page can contain the text
 * somewhere and still show the mangled sentence.
 */

const GROUP_DIRECTORY = 'ART@1780547760.NKi5Hz.group-directory'

test('a placeholder in an entity summary is shown, not swallowed', async ({ page }) => {
  await page.goto(`/entities/${encodeURIComponent(GROUP_DIRECTORY)}`)
  await expect(page.getByRole('heading', { name: 'Group Directory' }).first()).toBeVisible()

  const body = page.locator('body')
  await expect(body).toContainText('<slug>')
  await expect(body).toContainText('<doc-type>')
  await expect(body).not.toContainText('projects//model')
})
