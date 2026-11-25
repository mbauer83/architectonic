/**
 * Where *Edit details…* on the shared canvas reads an element from when the session edits something other
 * than the model: a host that does (a candidate architecture's canvas) provides this, and the dialog opens
 * on the element as that holds it, marks each field that differs from what it stands on with the value
 * there, and says in the host's words what keeping the edit does. Without one the dialog edits the model's
 * element, kept with the diagram's edit session.
 */
import type { InjectionKey } from 'vue'
import type { DifferingField, HeldFields } from '../../domain/heldDetails'

export interface HeldElement {
  /** The element's fields as held. */
  readonly fields: HeldFields
  /** What the holder stands on, by name: its parent, or the model. */
  readonly beneath: string
  /** Each field that differs from what the holder stands on. */
  readonly differs: readonly DifferingField[]
}

export interface DetailsSource {
  /** What keeping an edit does, said once under the dialog's heading. */
  readonly note: string
  /** The element *artifactId* as held; rejected where it is not held. */
  readonly read: (artifactId: string) => Promise<HeldElement>
}

export const detailsSourceKey: InjectionKey<DetailsSource> = Symbol('detailsSource')
