/**
 * Links into the documents list narrowed to one document type, as the list's own `doc_type` filter
 * reads it from the address.
 */
import { ROUTE_TEMPLATES } from '../router/artifactRoutes'

/** The shipped stress-analysis document type, as the server declares it. */
export const STRESS_ANALYSIS_DOC_TYPE = 'stress-analysis'

/** The documents list showing only documents of *docType*. */
export const documentsOfTypeRoute = (docType: string) =>
  ({ path: ROUTE_TEMPLATES.documentList, query: { doc_type: docType } }) as const
