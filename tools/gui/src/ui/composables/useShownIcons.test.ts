import { describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { Effect } from 'effect'
import { useShownIcons } from './useShownIcons'

const ANSWER = {
  icons: { n1: { icon: 'ICO@1.mark01', style: 'badge' as const, level: 'type' as const, picture: 'sha256:a' } },
  pictures: { 'sha256:a': 'data:image/png;base64,AAAA' },
}

const setup = (enabled = true) => {
  const previewShownIcons = vi.fn(() => Effect.succeed(ANSWER))
  const entities = ref<Record<string, unknown>>({ type_icons: { node: 'ICO@1.mark01' } })
  const instances = ref([{ instance_id: 'n1' }])
  const scope = effectScope()
  const result = scope.run(() => useShownIcons({ previewShownIcons }, entities, instances, ref(enabled), 10))!
  return { previewShownIcons, entities, result, scope }
}

describe('which icon each instance shows', () => {
  it('asks once after a burst of edits and shows the answer', async () => {
    vi.useFakeTimers()
    const { previewShownIcons, entities, result, scope } = setup()
    entities.value = { type_icons: { node: 'ICO@1.other1' } }
    await nextTick()
    entities.value = { type_icons: { node: 'ICO@1.mark01' } }
    await nextTick()
    await vi.advanceTimersByTimeAsync(20)

    expect(previewShownIcons).toHaveBeenCalledTimes(1)
    expect(result.shown.value).toEqual(ANSWER)
    scope.stop()
    vi.useRealTimers()
  })

  it('asks nothing for a type that draws no icons', async () => {
    vi.useFakeTimers()
    const { previewShownIcons, result, scope } = setup(false)
    await vi.advanceTimersByTimeAsync(20)

    expect(previewShownIcons).not.toHaveBeenCalled()
    expect(result.shown.value.icons).toEqual({})
    scope.stop()
    vi.useRealTimers()
  })
})
