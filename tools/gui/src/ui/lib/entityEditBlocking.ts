/**
 * Why the entity-detail edit form's save is disabled. Shared by the header's action trio
 * and the card's — both drive the same edit transaction, so a divergent explanation there
 * would be a bug in itself.
 *
 * Quarantine outranks the missing-required-property reason: that one the operator can fix
 * in the form, whereas a quarantined (type, specialization) pair cannot be saved at all
 * until its schema declarations are reconciled outside it.
 */

export const EDIT_QUARANTINE_TITLE = 'Resolve the schema conflict shown in the form before saving'
export const EDIT_REQUIRED_TITLE = 'Fill in all required properties first'

export const editBlockedReason = (quarantined: boolean, requiredMissing: boolean): string | undefined => {
  if (quarantined) return EDIT_QUARANTINE_TITLE
  return requiredMissing ? EDIT_REQUIRED_TITLE : undefined
}
