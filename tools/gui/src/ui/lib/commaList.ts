/**
 * A list typed into one field as comma-separated text — keywords, tags, stakeholders — and back.
 * Whitespace around an item is not part of it, and an empty item is no item.
 */
export const csvToList = (text: string): string[] => text.split(',').map((v) => v.trim()).filter((v) => v.length > 0)
export const listToCsv = (list: readonly string[]): string => list.join(', ')
