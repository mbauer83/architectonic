// Traffic-Light Protocol (TLP) presentation — colour by value, never a single red.
// Shared by every assurance surface that shows a TLP tag (browse list, node detail,
// architecture lens) so the tag's colour always matches its classification.

export type TlpLevel = 'TLP:WHITE' | 'TLP:CLEAR' | 'TLP:GREEN' | 'TLP:AMBER' | 'TLP:RED'

/** Text colour for a TLP tag, keyed on the classification value. */
export function tlpColor(tlp: string | null | undefined): string {
  switch ((tlp ?? '').toUpperCase()) {
    case 'TLP:RED':
      return '#dc2626' // red
    case 'TLP:AMBER':
    case 'TLP:AMBER+STRICT':
      return '#b45309' // amber
    case 'TLP:GREEN':
      return '#15803d' // green
    case 'TLP:WHITE':
    case 'TLP:CLEAR':
      return '#475569' // neutral grey (unrestricted)
    default:
      return '#475569'
  }
}
