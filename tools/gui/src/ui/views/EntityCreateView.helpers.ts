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

/**
 * The property rows a create sends, split into values and the ad-hoc types declared beside them.
 *
 * A row whose key is blank is not a property — it is an empty row the form leaves lying around for
 * the next one to be typed into. An ad-hoc type is recorded only where the effective schema does
 * not already declare the attribute: where it does, the schema's type is the answer and repeating
 * it in the request would let the two disagree.
 */
export const propertyRowsForWrite = (
  rows: readonly { key: string; value: string; adHocType: string }[],
  descriptors: Readonly<Record<string, unknown>>,
): { props: Record<string, string>; adhocTypes: Record<string, string> } => {
  const props: Record<string, string> = {}
  const adhocTypes: Record<string, string> = {}
  for (const row of rows) {
    const key = row.key.trim()
    if (!key) continue
    props[key] = row.value
    if (!descriptors[key] && row.adHocType !== 'string') adhocTypes[key] = row.adHocType
  }
  return { props, adhocTypes }
}
