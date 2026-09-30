# Icons on Diagram Elements

**Give a diagram's elements a product logo or a picture of your own**, beside the element's name or as
the element itself. An icon belongs to the diagram's presentation and changes nothing in the model.

An icon lives in one of two places:

- **The library** of a repository, shared by every diagram there. A library icon has a name, an
  attribution (whose mark it is, and on what terms it is used), the types or specializations it may be
  shown on, a default style and tags.
- **A diagram's own icons**, stored inside that diagram's file. Use one for a picture that one diagram
  needs; move it into the library when others need it too.

&nbsp;

## Which icon an element shows

A diagram states icons at two levels, and the more specific statement wins:

1. **This element** — an icon for one instance on this diagram. An element drawn twice can show a
   different icon in each place.
2. **Its type here** — an icon for every element of a type, or of a specialization, on this diagram. A
   specialization's statement wins over its type's.
3. **The specialization's default** — a repository may name a library icon as a specialization's
   `notation.icon`, in `.arch-repo/specializations.yaml`.

With none of these, the element keeps its type's glyph. An icon that does not apply to the element —
because its type changed, or the icon's `applies-to` did — is passed over, and the next level decides.

&nbsp;

## Styles

| Style | Drawn as | Diagram types |
|---|---|---|
| **Badge** | the icon in place of the type glyph, beside the name | ArchiMate, C4 |
| **Figure** | the icon as the element, its name beneath | ArchiMate |

An icon carries a default style; a statement may choose the other. An ArchiMate element that contains
others is drawn as a box, so a figure icon on it is shown as a badge. Activity, sequence, datatype, GSN
and matrix diagrams draw no icons, and the editor offers no icon controls for them.

&nbsp;

## In the diagram editor

Each row of the included-entities list has an icon chip at its left edge. It is empty until you hover
over the row; once an icon is set it shows the picture, and its tooltip says where the icon comes from.
Clicking the chip opens the picker:

- **This element / All ‹type› here** — the level the choice is stated at.
- **Icon's own / Badge / Figure** — the style, limited to the ones the diagram type draws.
- **The library**, searchable, listing only icons that apply to the element.
- **Upload for this diagram…** — add a picture as one of the diagram's own icons.
- **Clear** — withdraw the statement at that level, so the next level decides.

The row shows the result at once, and **Preview** draws it. Nothing is written until the diagram is
saved, so an abandoned edit leaves nothing behind; an uploaded icon no statement uses is dropped on save.

&nbsp;

## The icon library

**Icons** in the header opens the library. Icons are given to elements in the diagram editor; the
library page is for curating what there is to give.

- **Add to the library…** checks the file before anything is written, and shows what would be stored,
  or why the file is refused. The attribution you enter is kept for the session, so adding a set of
  vendor icons asks for it once.
- **Edit** changes the name, attribution, what the icon is for, its tags and its default style. The
  picture cannot be edited: a new version of a logo is a new icon.
- **Retire** stops the library offering the icon, while every diagram that shows it goes on showing
  it. **Reinstate** offers it again.
- **Replace…** moves every diagram showing the icon to another icon in the library, lists those
  diagrams before it does so, and deletes the first icon.
- **Delete** removes an icon nothing uses. While a diagram or a specialization default uses it, the
  deletion is refused and the refusal names them.

An icon's `applies-to` can be narrowed only while every element showing the icon still falls within
it. An icon for a type covers that type's specializations.

The diagram page lists the icons that diagram holds for itself, each with **Add to the library…**. The
icon joins the library under the attribution you give, the diagram names the library icon from then
on, and its own copy is removed. A picture the library already holds is not added twice: the diagram
is pointed at the existing icon.

&nbsp;

## What an upload may be

| | |
|---|---|
| Formats | SVG, PNG, JPEG, WebP |
| Largest file | 1 MB, at most 4096 px on either edge |
| Stored as | a PNG at most 128 px high, 384 px wide and 32 KB |
| Library upload request | 2 MB |

An SVG is rebuilt from an allow-list of elements and attributes before it is drawn, so scripts, event
attributes, external references and embedded foreign content never reach the renderer; what was
removed is reported. The stored PNG is what every diagram draws, so an icon looks the same wherever it
is shown.

A diagram holds at most eight icons of its own; a picture used more widely belongs in the library.

&nbsp;

## In the repository

- A library icon is a text file, `diagram-catalog/icons/ICO@….md`: its details in frontmatter, then
  the stored PNG as a `png-base64` block and, for an SVG upload, the cleaned SVG. It is committed,
  synced and reviewed like any other artifact.
- A diagram's statements are in its `diagram-entities`: `display_icons` for instances, `type_icons`
  for types and specializations, `icons` for its own pictures.
- **Every diagram body carries the pictures it draws**, in a block between `' arch-icons:begin` and
  `' arch-icons:end`. A body renders anywhere PlantUML does, with or without the library. The block is
  rebuilt on every write; an edit made to it by hand lasts until the next one.
- **Promotion** takes a promoted diagram's library icons to the enterprise repository. An icon the
  enterprise already holds under the same picture is not copied: the promoted diagram names the
  enterprise's icon instead.
- A **proposed change** to an enterprise diagram records its icon statements with the rest of the
  diagram, and a rebase replays them.

&nbsp;

## Through MCP, REST and the command line

| MCP tool | REST | Does |
|---|---|---|
| `artifact_query_icons` | `GET /api/icons` | list the library, filtered by what an icon applies to, a tag or text |
| `artifact_create_icon` | `POST /api/icons` | add an icon; a dry run reports what would be stored |
| `artifact_edit_icon` | `PATCH /api/icons/{id}` | change name, attribution, applies-to, tags, default style or status |
| `artifact_replace_icon` | `POST /api/icons/{id}/replace` | move every diagram to another icon, then delete this one |
| `artifact_share_icon` | `POST /api/diagrams/{id}/icons/{key}/share` | move a diagram's own icon into the library |
| `artifact_delete_icon` | `DELETE /api/icons/{id}` | delete an icon nothing uses |
| — | `GET /api/icons/{id}/image` | the stored PNG |
| — | `POST /api/icons/preview` | which icon each instance of a diagram shows, saved or not |

`artifact_create_diagram` and `artifact_edit_diagram` take `display_icons`, `type_icons` and `icons`
inside `diagram_entities`, so an agent can create a diagram with its icons in one call, and
`artifact_authoring_guidance(diagram_type=…)` describes them for the type.

`arch-icons import <dir> --attribution "…" [--tag …] [--for …] [--style badge|figure] [--commit]` adds
every SVG, PNG, JPEG and WebP file in a folder to the library through the same checks. Without
`--commit` it reports what it would add, what it would refuse and why, and what the library already
holds.

&nbsp;

## What the verifier reports

| Code | Meaning |
|---|---|
| `E360` | an icon file cannot be read as one |
| `E361` | an icon's id is not an `ICO@…` id, or the file is not named after it |
| `E362` | an icon's `render-digest` does not name the picture it carries |
| `E363` | an icon's picture is not a PNG within the stored limits, or not the size it declares |
| `E364` | a diagram names an icon the library, or the diagram itself, does not hold |
| `E365` | a diagram gives icons on a type that draws none, or in a style it does not draw |
| `W360` | an icon's `applies-to` names no type or specialization the product knows |
| `W361` | an icon is stated for an element it does not apply to; the diagram shows the next level instead |
| `W362` | a `type_icons` key names no type or specialization the product knows |

---

*Next: [Viewpoints →](viewpoints.md)*
