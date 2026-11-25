/**
 * Every canvas command is a named operation (A-02.24), the same one the backend's parity suite sends
 * through REST and MCP (A-02.41): this table is held to `tests/fixtures/canvas_commands.json`, and every
 * entry the element menu offers names its command.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { CANDIDATE_OPERATIONS, CANVAS_COMMANDS, DIAGRAM_OPERATIONS } from '../canvasCommands'
import { elementMenuItems, STACKING_ITEMS } from '../canvasElementMenu'
import { permitted } from '../canvasMenu'
import { CANDIDATE_WORDS, DIAGRAM_WORDS } from '../canvasWords'

interface Row {
  command: string
  diagram: { operation: string | null }
  candidate: { operation: string | null }
}

const { commands } = JSON.parse(
  readFileSync(fileURLToPath(new URL('../../../../../../tests/fixtures/canvas_commands.json', import.meta.url)), 'utf-8'),
) as { commands: Row[] }

describe('the canvas commands, as the backend names their operations', () => {
  it('lists every command the fixture does, and no other', () => {
    expect([...CANVAS_COMMANDS].sort()).toEqual(commands.map((row) => row.command).sort())
  })

  it('names the operation the fixture does for each command, on the diagram page and on a candidate', () => {
    const table = (page: 'diagram' | 'candidate') => Object.fromEntries(commands.map((row) => [row.command, row[page].operation]))
    expect(DIAGRAM_OPERATIONS).toEqual(table('diagram'))
    expect(CANDIDATE_OPERATIONS).toEqual(table('candidate'))
  })

  it('gives each page its own table', () => {
    expect(DIAGRAM_WORDS.operations).toBe(DIAGRAM_OPERATIONS)
    expect(CANDIDATE_WORDS.operations).toBe(CANDIDATE_OPERATIONS)
  })

  it('has every entry of the element menu name its command, in every form the menu takes', () => {
    const forms = [
      elementMenuItems(DIAGRAM_WORDS, false, 'Box', true), elementMenuItems(DIAGRAM_WORDS, true),
      elementMenuItems(CANDIDATE_WORDS, false), STACKING_ITEMS,
    ]
    for (const items of forms) expect(items.filter((item) => item.command === undefined)).toEqual([])
  })
})

describe('a menu as the permission answer offers it', () => {
  const items = elementMenuItems(DIAGRAM_WORDS, false)

  it('disables a refused entry and says why in place of what it does', () => {
    const shown = permitted(items, (command) => (command === 'element.delete'
      ? { allowed: false, reason: 'Not permitted for your role' } : { allowed: true }))
    const remove = shown.find((item) => item.id === 'delete')
    expect(remove).toMatchObject({ disabled: true, hint: 'Not permitted for your role' })
    expect(shown.filter((item) => item.disabled)).toEqual([remove])
  })

  it('leaves an entry that is no canvas command as it is', () => {
    const plain = [{ id: 'back', label: '‹ Back' }]
    expect(permitted(plain, () => ({ allowed: false, reason: 'no' }))).toEqual(plain)
  })
})
