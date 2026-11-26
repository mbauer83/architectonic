# Diagram canvas

The keys, gestures, menus and preferences of the diagram canvas, in view mode and edit mode. For a
walk through editing a diagram, see [Edit a diagram on its canvas](../03-modeling/editing-diagrams.md);
for reading one, see [Reading a diagram](../03-modeling/diagramming.md#reading-a-diagram).

&nbsp;

## Which diagrams are edited on the canvas

| Diagram | **Edit** opens |
|---|---|
| ArchiMate, in the engagement repository | edit mode on the canvas |
| ArchiMate with a hand-written body (`manual-layout`) | nothing; the page offers **Lay out automatically…** first |
| ArchiMate in the enterprise repository, and every other diagram type | the diagram's editor page |

&nbsp;

## The edit bar

| Item | What it does |
|---|---|
| **Automatic layout** / **Arranged by hand** | Whether the picture is PlantUML's arrangement or one stored with the diagram. **Return to automatic** on the second gives the automatic arrangement back, as one undoable step |
| **Undo**, **Redo** | Step through the session's history. The tooltip names the step |
| **Return to automatic boxes** | Shown whenever the boxes differ from the automatic ones: moved, sized, renamed, created or deleted. Puts them back: layer and type boxes are computed again, and boxes moved or sized return to where they were |
| **Check layout** | Marks the lines that break a layout rule; see [Check layout](#check-layout) |
| *n* **changes · *m* to the model** | Opens the change list. Reads **No changes** when there are none |
| **Discard** | Returns to the last save. With changes to discard, it asks first: **Cancel** has the focus, and `Esc` cancels |
| **Save** | Writes the session; see [Saving](#saving) |
| Sidebar | Shows or hides the panel with **Search the model**. The choice is kept in this browser |

**Done** in the page header, or `Esc`, leaves edit mode. With unsaved changes the bar asks
*Discard and exit edit mode?* and offers **Save and exit**, **Discard and exit** and
**Keep editing**; the arrow keys move between them. Opening another diagram or another page while
there are unsaved changes asks the same question, and **Save and exit** or **Discard and exit** then
goes on to that page. Closing the browser tab or reloading asks through the browser's own dialog.

&nbsp;

## Keys

Keys do nothing while the focus is in a text field or a list box. Letters are matched by the
character they type, so they work on any keyboard layout.

### View mode

| Key | Action |
|---|---|
| `E` | Enter edit mode (the diagram must have the focus) |
| `Enter` | Go into the elements; select the focused one |
| `Shift`+`Enter` | Add the focused element to the selection, or take it out |
| Arrows | Move to the nearest element in that direction |
| `F` | Frame the reading |
| `Esc` | Clear the reading; pressed again, leave the elements |
| `0` | Fit the whole diagram |
| `+` / `−` | Zoom in / out |

### Edit mode

| Key | Action |
|---|---|
| `Tab` / `Shift`+`Tab` | Walk the shapes in reading order, a box just before its members. The canvas is one tab stop |
| `Enter` / `Shift`+`Enter` | Select the focused shape / add it to the selection or take it out |
| Arrows | Move the selection one grid step (8 px); with `Shift`, 1 px. A selected line label moves 2 px (`Shift`: 1 px). With nothing selected, move to the nearest element, or pan |
| `Alt`+arrows | Resize the selected shape from its right and bottom edges |
| `Ctrl`+`A` | Select every element |
| `Delete`, `Backspace` | Remove the selection from the diagram (it stays in the model), or a selected bend from its line |
| `F2` | Rename the selected element |
| `Menu`, `Shift`+`F10` | Open the menu of what is selected |
| `PgUp` / `PgDn` | Bring forward / send backward |
| `Shift`+`PgUp` / `Shift`+`PgDn` | Bring to front / send to back |
| `F` | Frame the selection |
| `R` | Switch the selection rectangle between *touches* and *encloses* |
| `Space` (held) | Drag pans |
| `Alt` (held) | Drag pans |
| `Ctrl`+`Z` | Undo |
| `Ctrl`+`Shift`+`Z`, `Ctrl`+`Y` | Redo |
| `0`, `+`, `−` | Fit, zoom in, zoom out |
| `Esc` | Close the open popover, the change list, the leave question or the discard question; clear the selection; then leave edit mode |

On macOS, `Cmd` stands for `Ctrl`. In a menu, the up and down arrows move (and wrap), `Home` and
`End` jump, `Enter` or `Space` chooses and `Esc` closes.

&nbsp;

## Pointer gestures in edit mode

| Gesture | On | Result |
|---|---|---|
| Drag | an element, or a box by its title band | Moves it; a box brings its contents |
| Drag | empty paper, or a box's body | Selection rectangle; with `Shift` it adds to the selection |
| Click, `Shift`-click | a shape | Select; add to or take out of the selection |
| Drag | one of the eight handles of a selected shape | Resize |
| Drag | an element's edge, or the dot beside a selected element | Draw a relation |
| Drag | a line, its end, a bend or its label | Move the segment, slide or move the end, move the bend, move the label |
| Double-click | an element | Rename |
| Double-click | a line / a bend | Add a bend / remove it |
| Double-click | a relation's label | Open the relation |
| Long press | an element / a line / a line's label | Rename / edit the relation / type the label in place |
| Right-click | empty paper, or a box's body | The create picker |
| Right-click | an element, a selection, a line, a box's title band | That thing's menu |
| `Space` + drag, `Alt` + drag | anywhere | Pan |
| Middle-button drag | anywhere | Pan |
| Wheel | anywhere | Zoom at the pointer |

A press becomes a drag after 4 px of travel; shorter, it is a click. A selection rectangle drawn
dashed selects every element it touches, drawn solid only those it encloses. A box is selected only
when the rectangle encloses it.

While an element is dragged it snaps to an 8 px grid and to its neighbours' edges and centres, and
dashed guides show what it lines up with. A group moved together snaps to the grid only. While it is
over a box or element that would take it, that target is outlined with *Into ‹box›* or
*Nest in ‹element›…*.

&nbsp;

## Menus

An item that is not permitted is disabled, and its hint says why: the workspace is read-only, a sync
is in progress, or the backend refused the operation.

### Element

| Item | Effect |
|---|---|
| **Rename** | Rename the element in the model. The form says how many other diagrams draw it |
| **Edit details…** | Name, status, summary, keywords, specializations, notes and attributes, kept with the session until Save |
| **Connect to…** | Name the other element, then choose the relation |
| **Open** | The element's page, in a new tab |
| **Nest in…** | A box (diagram only), or an element that may contain it (a model change) |
| **Take out of ‹box›** | Move it onto the box around it. Shown when it sits in one of the diagram's own boxes |
| **Add another occurrence here** | Draw the same element again where the menu was opened |
| **Bring to front**, **Bring forward**, **Send backward**, **Send to back** | Stacking order, stored with the layout |
| **Remove from diagram** | It stays in the model |
| **Delete from model…** | Asks first and lists the relations that go with it |
| **Discard this draft** | Replaces the two above for an element created in this session |

For a draft, **Edit details…**, **Open** and **Add another occurrence here** are disabled until it
is saved.

### Selection

| Item | Effect |
|---|---|
| **Align ▸** | Left edges, centres, right edges, top edges, middles, bottom edges. From two elements |
| **Distribute ▸** | Horizontally or vertically, with equal gaps; the outer two stay. Offered from three elements |
| **Put in a new box…** | A labelled box round the selection, on this diagram only |
| Stacking, **Remove from diagram** | As for one element |

### Line

| Item | Effect |
|---|---|
| **Edit relation…** | Its label on this diagram, and in the model its cardinalities and description. The type is fixed: remove the relation and draw another to change it |
| **Straighten** | Remove every bend; the line is routed round what is in its way |
| **Move end to side ▸** | Either end, to any side of its element |

### Box

Right-click a box's title band.

| Item | Effect |
|---|---|
| **Rename box…** | On this diagram only |
| **Box by type ▸** | A box inside it for one element type it holds |
| **Delete box** | What it holds stays on the diagram |

&nbsp;

## Creating elements and relations

The create picker (right-click on paper) searches the model first. A model element found there is
added; one already drawn is added as a second occurrence. **Create “‹text›” as…** and
**Or create a new element of type** start a new element. Opened inside a box, the picker is headed
**Add to ‹box›** and lists only the types that box takes.

The **New element** form asks for the name, the type, a specialization where the type has any, and
the **Project**, preselected with the one used most on the diagram. **More fields** adds the summary
and the type's attributes. **Create draft** places the element; on an arranged picture it is placed
where you clicked, on an automatic one PlantUML places it. Created inside an element that may
contain it, the canvas asks at once whether to make it part of that element.

A **draft** is an element whose status is `draft`, or one created in this session and not yet
saved. It carries a small grey **d** in its corner, in both modes; the mark is not part of a
download. A relation that will be created at Save is drawn in the accent colour.

The relation form, after a drag between two elements or **Connect to…**, offers
**In the model: draw it** (relations the model already holds between them; drawing one changes the
diagram only) and **Not in the model: create it** (the types the ontology permits; a model change at
Save). An optional label is drawn on this diagram only.

&nbsp;

## The change list

Headed **Save will write**, it groups the session's changes:

| Group | Rows |
|---|---|
| **Model** — every diagram that draws these sees them | Create element · Rename element · Edit details · Delete from model · Create relationship · Edit relationship |
| **Diagram** — this diagram only | Added to diagram · Drawn again · Drawn from the model · Nested in ‹box› · Taken out of its box · Removed from the diagram (it stays in the model) · Label on this diagram · Layout changed · box changes |

Arrangement is one row, **Layout changed**, however much moved. The count in the edit bar is the
number of rows, with the model rows named separately.

&nbsp;

## Saving

**Save** writes the model changes and the diagram in one transaction, model changes first. A refusal
writes nothing; the reason is shown in the edit bar and the list stays open. You stay in edit mode.

The list opens before the save when the session changes the model, and asks for
**Confirm and save**. A session that changes only this diagram saves in one press, unless the
preference below says *always*.

Every action is one undo step. The first move on an automatic picture takes it over; the notice
that says so offers **Undo**, which returns to the automatic picture and everything after it.

&nbsp;

## Check layout

With **Check layout** on, each line that breaks a rule is marked on the canvas by a dashed band, or
a dashed outline round its ends. Hovering a mark gives its sentence, and the button's tooltip lists
them all, or says *No layout rule is broken*.

| A line … |
|---|
| runs through text |
| bends at a decorated end |
| runs along another line or a border |
| jogs |
| crosses an element it does not join |
| has no route that keeps every rule |
| joins two elements drawn over each other |

&nbsp;

## Preferences

The ⚙ button at the right of the navigation bar. Preferences are kept in this browser and change
neither the model nor any diagram.

| Preference | Choices (default first) |
|---|---|
| Theme | System · Light · Dark. Diagrams stay on light paper |
| A selection rectangle selects | every element it touches · the elements it encloses. `R` switches while editing |
| While moving and resizing | snap to a fine grid (8 px) and to alignment guides · show alignment guides only as hints (nothing snaps) |
| Keyboard shortcuts | detect the layout · QWERTZ · QWERTY. Decides the key for zoom in and how keys are named |
| Show the list of changes before saving | only when the model changes · always |

&nbsp;

## Viewport

| Control | Effect |
|---|---|
| **−**, percentage, **+**, **⊙** | Zoom out, the zoom level, zoom in, fit the diagram |
| **Reset view** | Back to the opening view; shown after the view has moved |
| **View fullscreen** / **Exit fullscreen** | `Esc` also leaves fullscreen |
| Overview | In the corner while the pointer is over the canvas and part of the picture is out of sight. It marks the selection and the reading; press or drag on it to move the window |

The opening view depends on how small the whole picture would be: at 50 % or more it is shown whole
and centred; between 35 % and 50 % it is fitted to the window's width from the top; below 35 % it
opens at 60 % on the top-left box.

---

*Back to [Configuration](configuration.md) · How-to: [Edit a diagram on its canvas](../03-modeling/editing-diagrams.md)*
