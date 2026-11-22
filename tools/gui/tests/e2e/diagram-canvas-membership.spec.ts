import { expect, test } from '@playwright/test'

const diagram = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'

test('adding a neighbour previews its drawing and can be undone before saving', async ({ page }) => {
  await page.goto(`/diagrams/${encodeURIComponent(diagram)}`)
  await page.getByTestId('diagram-edit').click()
  const picker = page.getByRole('region', { name: 'Add from model' })
  const member = picker.getByRole('button').first()
  const name = (await member.innerText()).replace('⠿', '').trim()
  const preview = page.waitForResponse(response => response.url().endsWith('/layout/geometry/preview'))
  await member.focus()
  await member.press('Enter')
  expect((await preview).ok()).toBe(true)
  await page.getByTestId('edit-undo').click()
  await expect(page.getByTestId('change-count')).toHaveText('No changes')
  await page.getByTestId('edit-redo').click()
  await page.getByTestId('change-count').click()
  await expect(page.getByTestId('change-list')).toContainText(name)
})
