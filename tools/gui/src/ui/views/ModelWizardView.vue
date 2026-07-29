<script setup lang="ts">
import { inject, watch, computed, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { useQuery } from '../composables/useQuery'
import { useWizardSession, createdCountByDomain } from '../composables/useWizardSession'
import { useSuggestionCommit } from '../composables/useSuggestionCommit'
import { buildWizardDomainCards } from './ModelWizardView.helpers'
import WizardDomainStage from '../components/WizardDomainStage.vue'
import WizardConnectionSuggestions from '../components/WizardConnectionSuggestions.vue'
import { WIZARD_DRAFT_KEYWORD } from '../components/WizardDomainStage.helpers'
import { SPINE } from '../lib/wizardQuestionnaires'
import { getDomainLabel, friendlyEntityId } from '../lib/domains'
import type { AuthoringGuidance, EntityDisplayInfo, ModuleSummary } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'

const svc = inject(modelServiceKey)!
const session = useWizardSession()
const guidanceQuery = useQuery<AuthoringGuidance, RepoError>()
const modulesQuery = useQuery<readonly ModuleSummary[], RepoError>()
const reviewLaterCommit = useSuggestionCommit(session)

const spineLabel = SPINE.map(getDomainLabel).join(' ↔ ')

const lastDomain = computed(() =>
  session.state.createdEntities.at(-1)?.domain ?? session.state.activeDomain)
const domainCards = computed(() =>
  buildWizardDomainCards(createdCountByDomain(session.state), lastDomain.value, modulesQuery.data.value ?? undefined))
const activeDomain = computed(() => session.state.activeDomain)
const hasProgress = computed(() =>
  session.state.createdEntities.length > 0 || session.state.reviewLaterQueue.length > 0)

const openDomain = (domain: string) => session.setActiveDomain(domain)

const startOver = () => {
  session.reset()
  guidanceQuery.reset()
}

const acceptReviewLater = (suggestion: (typeof session.state.reviewLaterQueue)[number]) =>
  reviewLaterCommit.accept(suggestion, (id) => session.resolveReviewLater(id))
const dismissReviewLater = (id: string) => session.resolveReviewLater(id)

// Drafts left behind by *previous* wizard sessions (tagged wizard-draft, decision D-6) —
// surfaced so abandoned work is finished or cleaned up instead of silently accumulating.
// This session's own creations are excluded; lookup failure just hides the banner.
const priorDrafts = ref<readonly EntityDisplayInfo[]>([])
onMounted(() => {
  modulesQuery.run(svc.listModules())
  void Effect.runPromise(
    svc.searchEntityDisplay({ query: '', limit: 20, keywords: [WIZARD_DRAFT_KEYWORD] }),
  ).then((result) => {
    const sessionIds = new Set(session.state.createdEntities.map((e) => e.artifactId))
    priorDrafts.value = result.items.filter((item) => !sessionIds.has(item.artifact_id))
  }).catch(() => { priorDrafts.value = [] })
})

// Any activeDomain change — a direct click, resuming a session on mount, or a questionnaire's
// bridge step switching domains — refetches guidance for it. Single source of truth instead of
// duplicating the fetch at every call site that can change the active domain.
watch(activeDomain, (domain) => {
  if (domain) guidanceQuery.run(svc.getAuthoringGuidance({ domains: [domain] }))
}, { immediate: true })
</script>

<template>
  <div class="wizard-view">
    <div class="wizard-header">
      <h1 class="page-title">
        Guided Modeling Wizard
      </h1>
      <p class="wizard-subtitle">
        Pick a domain to see what belongs there and why. The spine —
        {{ spineLabel }} — connects in both directions: start from a need, from an existing
        system, or anywhere between. Every question is skippable; nothing here is gated.
      </p>
      <button
        v-if="hasProgress"
        type="button"
        class="btn-link"
        @click="startOver"
      >
        Start over
      </button>
    </div>

    <div
      v-if="priorDrafts.length"
      class="draft-banner"
    >
      <strong>{{ priorDrafts.length }} draft{{ priorDrafts.length === 1 ? '' : 's' }}</strong>
      from earlier wizard sessions:
      <RouterLink
        v-for="draft in priorDrafts.slice(0, 5)"
        :key="draft.artifact_id"
        class="draft-link"
        :to="{ path: '/entity', query: { id: draft.artifact_id } }"
      >
        {{ draft.name }}
      </RouterLink>
      <span v-if="priorDrafts.length > 5">…</span>
    </div>

    <div class="domain-hub">
      <button
        v-for="card in domainCards"
        :key="card.key"
        type="button"
        class="domain-card"
        :class="{ 'domain-card--active': card.key === activeDomain }"
        :style="{ borderLeftColor: card.color }"
        @click="openDomain(card.key)"
      >
        <span class="domain-card__label">{{ card.label }}</span>
        <span
          v-if="card.recommended"
          class="domain-card__badge"
        >{{ hasProgress ? 'Next' : 'Start here' }}</span>
        <span class="domain-card__intro">{{ card.intro }}</span>
        <span
          v-if="card.createdCount > 0"
          class="domain-card__count"
        >{{ card.createdCount }} created</span>
      </button>
    </div>

    <div
      v-if="activeDomain"
      class="domain-panel"
    >
      <h2 class="domain-panel__title">
        {{ domainCards.find(c => c.key === activeDomain)?.label }}
      </h2>

      <div
        v-if="guidanceQuery.loading.value"
        class="state-msg"
      >
        Loading guidance…
      </div>
      <div
        v-else-if="guidanceQuery.errorMessage.value"
        class="state-msg state-msg--error"
      >
        {{ guidanceQuery.errorMessage.value }}
      </div>
      <WizardDomainStage
        v-else
        :key="activeDomain"
        :domain="activeDomain"
        :guidance="guidanceQuery.data.value"
        :session="session"
      />
    </div>

    <div
      v-if="session.state.createdEntities.length"
      class="recap"
    >
      <h2 class="domain-panel__title">
        This session
      </h2>
      <ul class="recap-list">
        <li
          v-for="entity in session.state.createdEntities"
          :key="entity.artifactId"
        >
          <RouterLink :to="{ path: '/entity', query: { id: entity.artifactId } }">
            {{ entity.name }}
          </RouterLink>
          <span class="recap-meta">{{ entity.artifactType }} · {{ entity.domain }}
            · {{ friendlyEntityId(entity.artifactId) }}</span>
        </li>
      </ul>
      <p
        v-if="session.state.createdConnections.length"
        class="recap-connections"
      >
        Connections made: {{ session.state.createdConnections.map((c) => c.summary).join(' · ') }}
      </p>
    </div>

    <div
      v-if="session.state.reviewLaterQueue.length"
      class="review-later"
    >
      <h2 class="domain-panel__title">
        Review later
      </h2>
      <div
        v-if="reviewLaterCommit.error.value"
        class="state-msg state-msg--error"
      >
        {{ reviewLaterCommit.error.value }}
      </div>
      <WizardConnectionSuggestions
        :suggestions="session.state.reviewLaterQueue"
        :busy="reviewLaterCommit.busy.value"
        :guidance="guidanceQuery.data.value"
        hide-later
        @accept="acceptReviewLater"
        @dismiss="dismissReviewLater"
      />
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: 22px; font-weight: 600; margin-bottom: 4px; }
.wizard-header { margin-bottom: 20px; }
.wizard-subtitle { color: #6b7280; margin: 0 0 8px; }
.btn-link {
  background: none; border: none; color: #2563eb; cursor: pointer; padding: 0;
  font-size: 13px; text-decoration: underline;
}
.state-msg { color: #6b7280; padding: 8px 0; }
.state-msg--error { color: #dc2626; }

.draft-banner {
  border: 1px solid #fcd34d; background: #fffbeb; color: #92400e; border-radius: 8px;
  padding: 10px 14px; margin-bottom: 16px; font-size: 13px;
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
}
.draft-link { color: #b45309; text-decoration: underline; }

.domain-hub {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.domain-card {
  display: flex; flex-direction: column; gap: 4px;
  padding: 14px 16px; border: 1px solid #e5e7eb; border-left: 4px solid transparent;
  border-radius: 8px; background: #fff; cursor: pointer; text-align: left;
}
.domain-card:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, .08); }
.domain-card--active { outline: 2px solid #2563eb; outline-offset: -1px; }
.domain-card__label { font-weight: 600; }
.domain-card__badge {
  align-self: flex-start; font-size: 11px; font-weight: 600; color: #1d4ed8;
  background: #dbeafe; border-radius: 10px; padding: 1px 8px;
}
.domain-card__intro {
  font-size: 12px; color: #6b7280; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.domain-card__count { font-size: 12px; color: #6b7280; }

.domain-panel, .review-later, .recap {
  border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px;
}
.domain-panel__title { font-size: 16px; font-weight: 600; margin: 0 0 12px; }
.recap-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.recap-list a { color: #2563eb; font-size: 13px; }
.recap-meta { font-size: 12px; color: #6b7280; margin-left: 8px; }
.recap-connections { font-size: 12px; color: #4b5563; margin: 10px 0 0; }
</style>
