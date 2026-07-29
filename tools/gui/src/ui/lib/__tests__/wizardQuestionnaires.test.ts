import { describe, it, expect } from 'vitest'
import { questionnaireForDomain, SPINE, DOMAIN_INTROS } from '../wizardQuestionnaires'

const bridgeTargets = (domain: string): string[] =>
  (questionnaireForDomain(domain)?.bridges ?? []).map((b) => b.nextDomain)

describe('questionnaireForDomain', () => {
  it('returns the motivation questionnaire with its full stakeholder-to-requirement sequence', () => {
    expect(questionnaireForDomain('motivation')?.steps.map((s) => s.entityType)).toEqual([
      'stakeholder', 'driver', 'assessment', 'goal', 'outcome', 'requirement',
    ])
  })

  it('covers the business who/what pair', () => {
    expect(questionnaireForDomain('business')?.steps.map((s) => s.entityType))
      .toEqual(['business-actor', 'business-object'])
  })

  it('covers the common behavioural core incl. subdivision and coordination (role, process, function, event, service)', () => {
    expect(questionnaireForDomain('common')?.steps.map((s) => s.entityType))
      .toEqual(['role', 'process', 'function', 'event', 'service'])
  })

  it('the subdivision step prefers aggregation for its chain suggestions', () => {
    const step = questionnaireForDomain('common')?.steps.find((s) => s.entityType === 'function')
    expect(step?.chainPreference).toEqual(['archimate-aggregation'])
  })

  it('covers the application support pair', () => {
    expect(questionnaireForDomain('application')?.steps.map((s) => s.entityType))
      .toEqual(['application-component', 'data-object'])
  })

  it('covers the strategy capability anchor', () => {
    expect(questionnaireForDomain('strategy')?.steps.map((s) => s.entityType))
      .toEqual(['capability', 'value-stream', 'resource'])
  })

  it('every step has a non-empty question and a concrete name hint', () => {
    for (const domain of [...SPINE, 'strategy']) {
      for (const step of questionnaireForDomain(domain)?.steps ?? []) {
        expect(step.question.length, `${domain}/${step.entityType}`).toBeGreaterThan(0)
        expect(step.nameHint, `${domain}/${step.entityType}`).toMatch(/^e\.g\. /)
      }
    }
  })

  it('returns undefined for a domain with no defined questionnaire', () => {
    expect(questionnaireForDomain('technology')).toBeUndefined()
  })
})

describe('omnidirectional spine bridges (D-7)', () => {
  it('every spine domain bridges to each of its spine neighbors', () => {
    for (let i = 0; i < SPINE.length; i++) {
      const expected = [SPINE[i - 1], SPINE[i + 1]].filter((d): d is string => d !== undefined)
      expect(new Set(bridgeTargets(SPINE[i])), SPINE[i]).toEqual(new Set(expected))
    }
  })

  it('strategy bridges to its natural anchors (motivation, common)', () => {
    expect(new Set(bridgeTargets('strategy'))).toEqual(new Set(['motivation', 'common']))
  })

  it('every bridge has a goal label, a prompt, and a target with a questionnaire', () => {
    for (const domain of [...SPINE, 'strategy']) {
      for (const bridge of questionnaireForDomain(domain)?.bridges ?? []) {
        expect(bridge.label.length, `${domain}→${bridge.nextDomain}`).toBeGreaterThan(0)
        expect(bridge.prompt.length).toBeGreaterThan(0)
        expect(questionnaireForDomain(bridge.nextDomain), bridge.nextDomain).toBeDefined()
      }
    }
  })
})

describe('DOMAIN_INTROS', () => {
  it('has a one-liner for every ArchiMate domain', () => {
    for (const domain of ['motivation', 'strategy', 'common', 'business', 'application', 'technology', 'implementation']) {
      expect(DOMAIN_INTROS[domain]?.length, domain).toBeGreaterThan(0)
    }
  })
})
