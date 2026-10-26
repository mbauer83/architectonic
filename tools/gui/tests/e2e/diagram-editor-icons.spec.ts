/**
 * An element's icon is chosen from its row in the diagram editor, and the row shows the result at once.
 *
 * What each row shows is the server's answer, not the editor's reckoning, so this is only checkable
 * against the running application: the precedence (the element's own statement over its type's) and
 * the normalising of an upload both happen behind the preview route. Nothing here is saved — an icon
 * uploaded for a diagram is held in the edit until the save — so the spec leaves the repository as it
 * found it.
 */
import { expect, test, type Locator, type Page } from '@playwright/test'

const DIAGRAM = 'ARC@1777452513.IqjFWO.repository-synchronization-git-integration'
const RED = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAHUlEQVR4nGP8EGD8n4ECwESJ5lEDRg0YNWAwGQAALqECktjim1MAAAAASUVORK5CYII='
const BLUE = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAHUlEQVR4nGPUqDjxn4ECwESJ5lEDRg0YNWAwGQAAAKoCh1pPr7gAAAAASUVORK5CYII='

const openEditor = async (page: Page): Promise<void> => {
  await page.goto(`/diagrams/${encodeURIComponent(DIAGRAM)}/edit`, { waitUntil: 'load' })
  await expect(page.locator('.entity-block').first()).toBeVisible({ timeout: 20_000 })
}

const row = (page: Page, name: string): Locator => page.locator('.entity-block').filter({ hasText: name })

const upload = async (
  page: Page, target: Locator, file: { name: string; base64: string }, scope: 'instance' | 'type' = 'instance',
): Promise<void> => {
  await target.locator('.icon-chip').click()
  const picker = page.locator('.icon-picker')
  await expect(picker).toBeVisible()
  await picker.locator(`input[type=radio][value="${scope}"]`).check()
  await picker.locator('input[type=file]').setInputFiles({
    name: file.name, mimeType: 'image/png', buffer: Buffer.from(file.base64, 'base64'),
  })
  await expect(picker).toBeHidden()
}

test('an upload for one element shows on its row, and in the preview', async ({ page }) => {
  await openEditor(page)
  const service = row(page, 'GUI Authoring Tool')
  await expect(service.locator('.icon-chip img')).toHaveCount(0)

  await upload(page, service, { name: 'gui-logo.png', base64: RED })

  await expect(service.locator('.icon-chip img')).toBeVisible({ timeout: 10_000 })
  await expect(service.locator('.icon-chip')).toHaveAttribute('title', /this element/)

  // The preview is a raster, so what it draws is read from the source it was rendered from.
  await page.locator('.sb-actions .btn-preview').click()
  await expect(page.locator('.preview-img')).toBeVisible({ timeout: 20_000 })
  await page.locator('.toggle-src').click()
  await expect(page.locator('.puml-src')).toContainText(/<img:\$ARCH_ICON_\w+\{[^}]*\}> GUI Authoring Tool/)
})

test('an element’s own icon overrides the one its type is given here', async ({ page }) => {
  await openEditor(page)
  const check = row(page, 'Check Repository')
  const pull = row(page, 'Pull Repository')
  await expect(pull.locator('.icon-chip img')).toHaveCount(0)

  await upload(page, check, { name: 'functions.png', base64: RED }, 'type')

  await expect(pull.locator('.icon-chip')).toHaveAttribute('title', /all of its type here/, { timeout: 10_000 })

  await upload(page, pull, { name: 'pull.png', base64: BLUE })

  await expect(pull.locator('.icon-chip')).toHaveAttribute('title', /this element/, { timeout: 10_000 })
  await expect(check.locator('.icon-chip')).toHaveAttribute('title', /all of its type here/)
})
