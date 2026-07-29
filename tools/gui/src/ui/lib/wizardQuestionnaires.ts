/**
 * Content-driven questionnaire/spine step definitions (WU-B2c, uplifted per WU-B4). Wording
 * lives here, not in a component template, so it iterates without code churn.
 *
 * The flow is **omnidirectional** (decision D-7): there is no planning/reverse mode. The spine
 * (motivation ↔ business ↔ common ↔ application) is a map, not a rail — every questionnaire
 * completion offers goal-labeled bridges to its spine neighbors in *both* directions, questions
 * are phrased to read naturally whether the user is planning something new or documenting
 * something that exists, and every question is skippable (a requirement without a stakeholder,
 * a process without a role, are legitimate lightweight models).
 *
 * Question wording is grounded in each type's `create_when` guidance
 * (`/api/authoring-guidance`); the behavioural core (role/process/service) lives in the
 * **common** domain in this ontology, not business. `nameHint` gives beginners a concrete
 * example of a well-formed name (shown as the name input's placeholder).
 */
export interface QuestionnaireStep {
  readonly entityType: string
  readonly question: string
  /** Example of a well-formed name, e.g. "e.g. 'Audit events are traceable end-to-end'". */
  readonly nameHint?: string
  /** Connection kinds this step is really about, ranked first when suggesting links to the
   * spine (e.g. the subdivision step prefers aggregation over the globally higher-ranked
   * triggering). */
  readonly chainPreference?: readonly string[]
}

export interface QuestionnaireBridge {
  /** Short user-goal label for the bridge button, e.g. "Map the impact". */
  readonly label: string
  readonly prompt: string
  readonly nextDomain: string
}

export interface DomainQuestionnaire {
  readonly domain: string
  readonly steps: readonly QuestionnaireStep[]
  /** Goal-labeled hand-offs shown on completion — spine neighbors in both directions where
   * they exist; off-spine questionnaires (strategy) point at their natural anchors. */
  readonly bridges: readonly QuestionnaireBridge[]
}

/** Spine order used for the fresh-session default and adjacency-based recommendations. */
export const SPINE: readonly string[] = ['motivation', 'business', 'common', 'application']

/** One-line beginner orientation per domain, shown on the hub cards. */
export const DOMAIN_INTROS: Record<string, string> = {
  motivation: 'Why: who wants what, and why it matters',
  strategy: 'How, broadly: capabilities, resources, courses of action',
  common: 'Behaviour: roles, processes, services, events',
  business: 'Who: actors, business objects, products',
  application: 'With what: software components, data, interfaces',
  technology: 'On what: infrastructure, platforms, networks',
  implementation: 'Getting there: work packages, deliverables, plateaus',
}

const QUESTIONNAIRES: readonly DomainQuestionnaire[] = [
  {
    domain: 'motivation',
    steps: [
      {
        entityType: 'stakeholder',
        question: 'Who cares about this, and why?',
        nameHint: "e.g. 'Compliance Officer'",
      },
      {
        entityType: 'driver',
        question: 'What internal or external force makes this matter — a push for change, or the reason it exists?',
        nameHint: "e.g. 'Regulatory pressure for audit trails'",
      },
      {
        entityType: 'assessment',
        question: 'What specific problem or condition does that force create?',
        nameHint: "e.g. 'Privileged actions are not traceable today'",
      },
      {
        entityType: 'goal',
        question: 'What desired state of affairs would resolve it?',
        nameHint: "e.g. 'Audit events are traceable end-to-end'",
      },
      {
        entityType: 'outcome',
        question: 'How will you know the goal was actually achieved?',
        nameHint: "e.g. '100% of privileged actions logged'",
      },
      {
        entityType: 'requirement',
        question: 'What specific, testable need must be met?',
        nameHint: "e.g. 'Record all administrative actions'",
      },
    ],
    bridges: [
      {
        label: 'Map the impact',
        prompt: 'You have a motivation chain. Now bridge it to impact: who in the business is '
          + 'affected, and what do they work with?',
        nextDomain: 'business',
      },
    ],
  },
  {
    domain: 'business',
    steps: [
      {
        entityType: 'business-actor',
        question: 'Which organizational entity — department, team, or external organization — '
          + 'does or is affected by this work?',
        nameHint: "e.g. 'Customer Service Department'",
      },
      {
        entityType: 'business-object',
        question: 'What tangible or intangible business thing does that work use or produce?',
        nameHint: "e.g. 'Audit Record'",
      },
    ],
    bridges: [
      {
        label: 'Capture the why',
        prompt: 'Ground this in motivation: which drivers, goals, and requirements explain why '
          + 'these actors and objects matter?',
        nextDomain: 'motivation',
      },
      {
        label: 'Model how the work gets done',
        prompt: 'You know who is involved and what they handle. Now model how the work actually '
          + 'gets done: the roles, processes, and services live in the common domain.',
        nextDomain: 'common',
      },
    ],
  },
  {
    domain: 'common',
    steps: [
      {
        entityType: 'role',
        question: 'What responsibility or capability — independent of who currently holds it — '
          + 'performs this work?',
        nameHint: "e.g. 'Audit Reviewer'",
      },
      {
        entityType: 'process',
        question: 'What ordered sequence of activities achieves the result?',
        nameHint: "e.g. 'Review Audit Trail'",
      },
      {
        entityType: 'function',
        question: 'How does the process subdivide — what grouped behaviours (functions) or '
          + 'sub-processes compose it? (For a sub-process, add another process instead.)',
        nameHint: "e.g. 'Collect Audit Evidence'",
        chainPreference: ['archimate-aggregation'],
      },
      {
        entityType: 'event',
        question: 'What happening marks an important transition — triggering or interrupting '
          + 'behaviour, or coordinating hand-offs between (sub-)processes?',
        nameHint: "e.g. 'Audit Threshold Exceeded'",
      },
      {
        entityType: 'service',
        question: 'What explicit, well-defined behavior does this offer to its environment?',
        nameHint: "e.g. 'Audit Logging Service'",
      },
    ],
    bridges: [
      {
        label: 'Identify who is involved',
        prompt: 'Which organizational entities perform or consume this behaviour, and what '
          + 'business things do they handle?',
        nextDomain: 'business',
      },
      {
        label: 'Link supporting applications',
        prompt: 'Which applications support or automate this behaviour, and what data do they '
          + 'manage?',
        nextDomain: 'application',
      },
    ],
  },
  {
    domain: 'application',
    steps: [
      {
        entityType: 'application-component',
        question: 'Which deployable unit of software is involved — existing (often imported by '
          + 'the reverse-architecture tooling) or planned?',
        nameHint: "e.g. 'Audit Log Service'",
      },
      {
        entityType: 'data-object',
        question: 'What type of data does it manage or exchange?',
        nameHint: "e.g. 'Audit Event'",
      },
    ],
    bridges: [
      {
        label: 'Model the behaviour it supports',
        prompt: 'Model what this software is *for*: the services it offers, the processes '
          + 'behind them, and the roles involved — which tooling cannot infer from code alone.',
        nextDomain: 'common',
      },
    ],
  },
  {
    domain: 'strategy',
    steps: [
      {
        entityType: 'capability',
        question: 'What ability must the organization have or strengthen to achieve its goals?',
        nameHint: "e.g. 'Audit Trail Management'",
      },
      {
        entityType: 'value-stream',
        question: 'What end-to-end sequence of value-adding stages does that ability serve?',
        nameHint: "e.g. 'Incident Investigation'",
      },
      {
        entityType: 'resource',
        question: 'What people, assets, or means are required to provide it?',
        nameHint: "e.g. 'Security Operations Team'",
      },
    ],
    bridges: [
      {
        label: 'Ground it in goals',
        prompt: 'Which goals and requirements does this capability serve, and who wants them?',
        nextDomain: 'motivation',
      },
      {
        label: 'Realize it as behaviour',
        prompt: 'What roles, processes, and services realize this capability day to day?',
        nextDomain: 'common',
      },
    ],
  },
]

export const questionnaireForDomain = (domain: string): DomainQuestionnaire | undefined =>
  QUESTIONNAIRES.find((q) => q.domain === domain)
