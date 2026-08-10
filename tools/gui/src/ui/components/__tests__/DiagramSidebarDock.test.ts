// @vitest-environment jsdom
//
// Where the dock puts the sidebar, and whether the same instance survives the move.
//
// jsdom implements no Fullscreen API, so `isFullscreen` is passed as the prop it is — these tests are
// about the dock's own decisions (teleport or not, reveal or not, remount or not), not about
// fullscreen actually happening. That the sidebar is *visible* over a real fullscreen canvas depends
// on `:fullscreen` CSS jsdom does not evaluate, so it is the browser suite's job.

import { afterEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent, h, nextTick, ref, type App } from 'vue'
import DiagramSidebarDock from '../DiagramSidebarDock.vue'

/** Stands in for the sidebar, and counts its own mounts so a remount cannot pass unnoticed. */
let mountCount = 0
const Sidebar = defineComponent({
  name: 'Sidebar',
  setup() {
    mountCount += 1
    return () => h('aside', { class: 'sidebar' }, 'panel')
  },
})

let mounted: App | null = null

interface DockProps {
  fullscreenHost: HTMLElement | null
  isFullscreen: boolean
  hasSelection: boolean
}

const render = (props: DockProps) => {
  mountCount = 0
  const container = document.createElement('div')
  document.body.appendChild(container)
  const app = createApp({
    render: () => h(DiagramSidebarDock, { ...props }, { default: () => h(Sidebar) }),
  })
  app.mount(container)
  mounted = app
  return container
}

const freshHost = () => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  return host
}

afterEach(() => {
  mounted?.unmount()
  mounted = null
  document.body.innerHTML = ''
})

describe('while the canvas is docked in the layout', () => {
  it('renders the sidebar in place, selected or not', () => {
    for (const hasSelection of [true, false]) {
      const host = freshHost()
      const container = render({ fullscreenHost: host, isFullscreen: false, hasSelection })
      expect(container.querySelector('.sidebar')).not.toBeNull()
      expect(host.querySelector('.sidebar')).toBeNull()
      mounted?.unmount()
      mounted = null
    }
  })

  it('adds no wrapper around it, because the sidebar is the grid child', () => {
    // A wrapper would become the grid child and leave the sidebar's `position: sticky` resolving
    // against an element of its own height — working layout, silently dead stickiness.
    const container = render({ fullscreenHost: freshHost(), isFullscreen: false, hasSelection: true })
    expect(container.firstElementChild?.classList.contains('sidebar')).toBe(true)
  })
})

describe('once the canvas owns the screen', () => {
  it('moves the sidebar into the fullscreen host when something is selected', () => {
    const host = freshHost()
    render({ fullscreenHost: host, isFullscreen: true, hasSelection: true })
    expect(host.querySelector('.sidebar')).not.toBeNull()
  })

  it('withholds it while nothing is selected, so the diagram is not covered for no reason', () => {
    const host = freshHost()
    render({ fullscreenHost: host, isFullscreen: true, hasSelection: false })
    expect(host.querySelector('.sidebar')).toBeNull()
  })

  it('stays in place while the host element has not mounted yet', () => {
    // Teleporting to null throws in Vue; before the canvas exists there is nowhere to go.
    const container = render({ fullscreenHost: null, isFullscreen: true, hasSelection: true })
    expect(container.querySelector('.sidebar')).not.toBeNull()
  })

  it('keeps the same sidebar instance across the move, rather than remounting it', async () => {
    // The reason this is a Teleport with `:disabled` and not a v-if/v-else over two positions: a
    // remount re-runs the sidebar's entity query and discards its scroll position on every toggle.
    const host = freshHost()
    const container = document.createElement('div')
    document.body.appendChild(container)
    const isFullscreen = ref(false)
    mountCount = 0
    const app = createApp({
      render: () =>
        h(
          DiagramSidebarDock,
          { fullscreenHost: host, isFullscreen: isFullscreen.value, hasSelection: true },
          { default: () => h(Sidebar) },
        ),
    })
    app.mount(container)
    mounted = app

    expect(mountCount).toBe(1)
    expect(container.querySelector('.sidebar')).not.toBeNull()

    isFullscreen.value = true
    await nextTick()

    expect(host.querySelector('.sidebar')).not.toBeNull()
    expect(mountCount).toBe(1)
  })
})
