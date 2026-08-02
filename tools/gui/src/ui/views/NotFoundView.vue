<script setup lang="ts">
/**
 * The page for an address this application does not serve.
 *
 * There was none. An unmatched path rendered the chrome and an empty `<main>` — indistinguishable
 * from a view that failed to load, and from a working page whose content had not arrived yet. The
 * 0.2.0 addressing move made that reachable in ordinary use: an old bookmark, a link in a document,
 * a stale in-app link all landed on a blank screen that said nothing and offered nothing.
 *
 * It names the address, because a reader's first question is whether they mistyped it, and offers
 * the surfaces the retired addresses belonged to.
 */
import { useRoute } from 'vue-router'

const route = useRoute()

const LINKS = [
  { to: '/', label: 'Home' },
  { to: '/entities', label: 'Browse the model' },
  { to: '/viewpoints', label: 'Viewpoints' },
  { to: '/assurance', label: 'Assurance' },
] as const
</script>

<template>
  <div class="not-found">
    <h1 class="nf-title">
      No page at this address
    </h1>
    <p class="nf-path">
      <code>{{ route.fullPath }}</code>
    </p>
    <p class="nf-body">
      Addresses changed in 0.2.0: identity moved into the path. A link kept from before then may
      name a surface that has since moved rather than one that is gone.
    </p>
    <ul class="nf-links">
      <li
        v-for="link in LINKS"
        :key="link.to"
      >
        <RouterLink :to="link.to">
          {{ link.label }}
        </RouterLink>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.not-found { max-width: 640px; margin: 48px auto; }
.nf-title { font-size: 20px; font-weight: 700; color: #1e293b; margin: 0 0 10px; }
.nf-path { margin: 0 0 14px; }
.nf-path code {
  font-size: 12px; background: #f1f5f9; border: 1px solid #e2e8f0;
  border-radius: 4px; padding: 2px 6px; color: #334155; word-break: break-all;
}
.nf-body { font-size: 13px; color: #475569; margin: 0 0 16px; }
.nf-links { display: flex; flex-wrap: wrap; gap: 16px; list-style: none; padding: 0; margin: 0; font-size: 13px; }
</style>
