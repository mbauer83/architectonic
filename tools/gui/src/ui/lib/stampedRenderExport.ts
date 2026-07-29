/**
 * Stamped-render export: styled output leaves the browser ONLY through the server-stamped
 * export, which burns the computed classification banner into the returned bytes. The
 * caller hands over the on-screen SVG markup; a downloaded file is triggered on success,
 * and any failure is returned as a message string (never thrown) for the view to surface.
 */
export const downloadStampedRender = async (
  slug: string,
  svgMarkup: string,
): Promise<string | null> => {
  const response = await fetch('/api/viewpoints/export-render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slug, svg: svgMarkup }),
  })
  if (!response.ok) return `export failed (HTTP ${response.status})`
  const blob = await response.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${slug}.svg`
  link.click()
  URL.revokeObjectURL(link.href)
  return null
}
