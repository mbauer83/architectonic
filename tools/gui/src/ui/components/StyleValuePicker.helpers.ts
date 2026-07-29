/**
 * Pure helpers for `StyleValuePicker.vue`: the swatch option list per configuration and
 * the custom-hex selection logic — kept out of the SFC so they are unit-testable without
 * a DOM mount.
 */

import { STYLE_TOKENS } from '../../domain/viewpointPresentation'
import { SCALE_ENDPOINT_TOKENS, isHexColorValue, tokenColor, tokenLabel } from '../lib/viewpointStyleTokens'

export interface SwatchOption {
  readonly token: string
  readonly color: string
  readonly label: string
}

/** The five semantic-token swatches, plus the four named heat-* scale endpoints when the
 * picker sits in a context where endpoints are valid values (scale gradients, defaults). */
export const pickerSwatches = (allowScaleEndpoints: boolean): SwatchOption[] =>
  [...STYLE_TOKENS, ...(allowScaleEndpoints ? SCALE_ENDPOINT_TOKENS : [])]
    .map((token) => ({ token, color: tokenColor(token), label: tokenLabel(token) }))

/** A current value that selects the "custom" swatch rather than a named one. */
export const isCustomSelection = (value: string | null): boolean =>
  value !== null && isHexColorValue(value)

/** What the native color input shows: the current explicit hex if there is one, else a
 * starting color for the first custom pick. */
export const customColorFor = (value: string | null): string =>
  value !== null && isHexColorValue(value) ? value : '#8b5cf6'
