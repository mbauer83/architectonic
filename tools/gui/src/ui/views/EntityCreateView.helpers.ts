/**
 * Why the create form's submit buttons are disabled, as one ordered explanation each.
 *
 * Quarantine outranks every other reason: the other two are things the operator can fix in
 * the form, whereas a quarantined (type, specialization) pair cannot be authored at all
 * until its schema declarations are reconciled outside the form. Kept pure and separate so
 * the ordering is testable without mounting the view.
 */

export const QUARANTINE_TITLE = 'Resolve the schema conflict shown above before authoring this type'
export const REQUIRED_TITLE = 'Fill in all required properties first'
export const PREVIEW_FIRST_TITLE = 'Run preview first to enable create'

export const previewBlockedReason = (quarantined: boolean, requiredMissing: boolean): string | undefined => {
  if (quarantined) return QUARANTINE_TITLE
  return requiredMissing ? REQUIRED_TITLE : undefined
}

export const createBlockedReason = (
  quarantined: boolean,
  previewClean: boolean,
  requiredMissing: boolean,
): string | undefined => {
  if (quarantined) return QUARANTINE_TITLE
  if (!previewClean) return PREVIEW_FIRST_TITLE
  return requiredMissing ? REQUIRED_TITLE : undefined
}
