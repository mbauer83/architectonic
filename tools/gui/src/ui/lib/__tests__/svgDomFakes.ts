/**
 * Minimal fake DOM harness shared by viewer-extension `mapElements` tests. No jsdom/happy-dom in
 * this project — these fakes stand in for the small slice of the SVG DOM API the matchers
 * actually call (`querySelectorAll('g'|'a'|'g[data-entity-1]'|'g.message')`, `getElementById`,
 * `closest('g')`, `querySelector(':scope > title')`).
 */
import type { EntitySummary } from '../../../domain'

export class FakeElement {
  id = ''
  parent: FakeElement | null = null
  children: FakeElement[] = []
  private attrs = new Map<string, string>()

  constructor(public tagName: string) {}

  setId(id: string): this { this.id = id; return this }
  setAttribute(name: string, value: string): void { this.attrs.set(name, value) }
  getAttribute(name: string): string | null { return this.attrs.get(name) ?? null }
  hasAttribute(name: string): boolean { return this.attrs.has(name) }
  removeAttribute(name: string): void { this.attrs.delete(name) }
  addEventListener(): void { /* not exercised by mapElements itself */ }
  get classList() { return { add: () => {}, remove: () => {} } }

  appendChild(child: FakeElement): FakeElement {
    child.parent = this
    this.children.push(child)
    return child
  }

  querySelector(selector: string): FakeElement | null {
    if (selector === ':scope > title') return this.children.find((c) => c.tagName === 'title') ?? null
    throw new Error(`unsupported selector: ${selector}`)
  }

  closest(selector: string): FakeElement | null {
    if (selector !== 'g') throw new Error(`unsupported selector: ${selector}`)
    if (this.tagName === 'g') return this
    return this.parent?.closest(selector) ?? null
  }

  get previousElementSibling(): FakeElement | null {
    const siblings = this.parent?.children ?? []
    const index = siblings.indexOf(this)
    return index > 0 ? siblings[index - 1] : null
  }
}

const hasClass = (e: FakeElement, cls: string): boolean =>
  (e.getAttribute('class') ?? '').split(/\s+/).includes(cls)

export const collectDescendants = (
  root: FakeElement,
  pred: (e: FakeElement) => boolean,
  out: FakeElement[],
): void => {
  for (const child of root.children) {
    if (pred(child)) out.push(child)
    collectDescendants(child, pred, out)
  }
}

export class FakeSvgRoot extends FakeElement {
  constructor() { super('svg') }

  querySelectorAll(selector: string): FakeElement[] {
    const out: FakeElement[] = []
    if (selector === 'g') collectDescendants(this, (e) => e.tagName === 'g', out)
    else if (selector === 'a') collectDescendants(this, (e) => e.tagName === 'a', out)
    else if (selector === 'g[data-entity-1]') collectDescendants(this, (e) => e.tagName === 'g' && e.hasAttribute('data-entity-1'), out)
    else if (selector === 'g.message') collectDescendants(this, (e) => e.tagName === 'g' && hasClass(e, 'message'), out)
    else throw new Error(`unsupported selector: ${selector}`)
    return out
  }

  getElementById(id: string): FakeElement | null {
    const out: FakeElement[] = []
    collectDescendants(this, (e) => e.id === id, out)
    return out[0] ?? null
  }
}

export const asSvgRoot = (root: FakeSvgRoot) => root as unknown as SVGSVGElement

export const makeEntity = (
  id: string,
  alias: string,
  artifactType = 'application-component',
): EntitySummary => ({
  artifact_id: id,
  artifact_type: artifactType,
  name: id,
  version: '0.1.0',
  status: 'active',
  domain: 'application',
  subdomain: '',
  path: '/tmp/x.md',
  is_global: false,
  group: 'uncategorized',
  display_alias: alias,
})
