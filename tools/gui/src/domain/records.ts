/** Whether *value* is an object whose fields can be read by name: a JSON object, a stored row. */
export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null
