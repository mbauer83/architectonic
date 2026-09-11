import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

/**
 * Structural pin for the content-first header (the suite runs without DOM
 * mounting, so membership is asserted against the SFC template): one primary
 * navigation landmark holding the content entries, one right workflow-status
 * landmark holding the cluster and search, and no tier-first sections or
 * duplicated per-tier links.
 */

const source = readFileSync(resolve(__dirname, '../NavBar.vue'), 'utf8')
const template = source.slice(source.indexOf('<template>'), source.indexOf('</template>'))

describe('NavBar structure', () => {
  it('has one primary nav landmark with the content entries', () => {
    expect(template).toContain('aria-label="Primary"')
    for (const label of ['Browse', 'Documents', 'Diagrams', 'Viewpoints', 'Assurance']) {
      expect(template).toContain(label)
    }
  })

  it('carries one axis: a class of artifact, never a workflow state', () => {
    // Every entry above names a kind of artifact you can hold. The proposed-changes page is
    // the state of the enterprise-change workflow, which the cluster owns and now opens; it
    // was here, and the bar had no room for it — see the destination-reachability spec.
    const nav = template.slice(template.indexOf('aria-label="Primary"'), template.indexOf('</nav>'))
    expect(nav).not.toContain('/changes')
  })

  it('nouns only on the left: no workflow verbs inside the primary nav', () => {
    const nav = template.slice(template.indexOf('aria-label="Primary"'), template.indexOf('</nav>'))
    for (const verb of ['Save', 'Submit', 'Discard', 'Promote']) {
      expect(nav).not.toContain(`>${verb}<`)
    }
  })

  it('hosts the workflow-status landmark with the cluster and search', () => {
    expect(template).toContain('aria-label="Workflow and status"')
    const workflow = template.slice(template.indexOf('aria-label="Workflow and status"'))
    expect(workflow).toContain('<SyncStatusCluster')
    expect(workflow).toContain('nav__search')
  })

  it('does not call two different things "Changes"', () => {
    // Two controls were once both labelled "Changes": the cluster's git save flow, over uncommitted
    // work in this repository, and a primary-nav entry for the `/changes` page — edits to content
    // this repository does not own. One label in two places is indistinguishable at the moment of
    // clicking. There is one control now, and the entries inside it are named apart, so what this
    // pins is that a second "Changes" never reappears on the left.
    const nav = template.slice(template.indexOf('aria-label="Primary"'), template.indexOf('</nav>'))
    expect(nav).not.toContain('>\n        Changes\n      <')
  })

  it('has no tier-first sections or /global links', () => {
    expect(template).not.toContain('/global/')
    expect(template).not.toContain('nav__section-label')
    expect(template).not.toMatch(/>\s*Global\s*</)
  })

  it('keeps the viewpoint-driven highlight wiring', () => {
    expect(template).toContain("'nav__link--forced-active': viewpointDriven")
    expect(template).toContain("'nav__link--suppressed': viewpointDriven")
  })
})
