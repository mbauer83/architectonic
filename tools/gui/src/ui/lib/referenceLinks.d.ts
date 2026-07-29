export function toRepoRelativePath(value?: string): string
export function relativePathBetweenArtifacts(fromPath?: string, toPath?: string): string
export function toSectionAnchor(section?: string): string
export function buildReferenceMarkdown(params: {
  currentPath?: string
  targetPath?: string
  title: string
  section?: string
}): string
export function draftDocumentPath(docType?: string, subdirectory?: string): string
