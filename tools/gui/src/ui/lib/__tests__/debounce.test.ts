import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createDebouncer } from '../debounce'

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe('createDebouncer', () => {
  it('only runs the last call after rapid repeated scheduling', () => {
    const debounce = createDebouncer(300)
    const seen: number[] = []
    debounce(() => seen.push(1))
    vi.advanceTimersByTime(100)
    debounce(() => seen.push(2))
    vi.advanceTimersByTime(100)
    debounce(() => seen.push(3))
    vi.advanceTimersByTime(300)
    expect(seen).toEqual([3])
  })

  it('runs again for a call made after the delay has elapsed', () => {
    const debounce = createDebouncer(300)
    const seen: number[] = []
    debounce(() => seen.push(1))
    vi.advanceTimersByTime(300)
    debounce(() => seen.push(2))
    vi.advanceTimersByTime(300)
    expect(seen).toEqual([1, 2])
  })
})
