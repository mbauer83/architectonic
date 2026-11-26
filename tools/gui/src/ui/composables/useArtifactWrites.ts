/**
 * The writes of an artifact on this page (`domain/artifactWrites`), by where it lives and the backend's
 * mode as the app shell read it. A control asks `useCan` for the operation named here; nothing on a
 * detail page reads the backend's mode for itself.
 *
 * With no mode provided — a component mounted outside the app shell — the backend is taken not to be in
 * admin mode, so no write is ever chosen to land upstream on an answer no one gave.
 */
import { computed, inject, ref, type ComputedRef } from 'vue'
import { artifactWrites, type ArtifactWrites } from '../../domain/artifactWrites'
import { adminModeKey } from '../keys'

export const useArtifactWrites = (enterprise: () => boolean): ComputedRef<ArtifactWrites> => {
  const adminMode = inject(adminModeKey, ref(false))
  return computed(() => artifactWrites(enterprise(), adminMode.value))
}
