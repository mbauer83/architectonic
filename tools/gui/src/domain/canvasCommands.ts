/**
 * Every command of the shared canvas editor — each menu entry, key and gesture — and the named operation
 * it is on each page that edits with it (sketch 02·7, A-02.24).
 *
 * The operation is the backend's name for what saving the command writes
 * (`src/application/operation_catalog.py`): the name a policy allows or denies, which the permission
 * answer is keyed by (`domain/permissions`). On the
 * diagram page a command is a part of the diagram's save; on a candidate's it is an edit the candidate
 * records. A command that writes nothing on a page — opening a page, taking an element off a candidate's
 * view, arranging a picture a candidate does not keep — is `null` there, and is never refused.
 *
 * `tests/fixtures/canvas_commands.json` states the same table with, for each writing command, the request
 * that carries it; the backend's parity suite sends each through REST and through MCP and holds the two
 * results equal, and `canvasCommands.test.ts` holds this table to that one.
 */

export const CANVAS_COMMANDS = [
  'element.rename', 'element.details', 'element.connect', 'element.open', 'element.nest', 'element.unnest',
  'element.occurrence', 'element.restack', 'element.remove', 'element.delete', 'element.discard',
  'line.edit', 'line.straighten', 'line.move-end', 'line.relabel', 'line.draw',
  'selection.align', 'selection.distribute', 'selection.box', 'selection.remove',
  'box.rename', 'box.by-type', 'box.delete',
  'canvas.place', 'canvas.create',
  'key.nudge', 'key.resize', 'key.nudge-label', 'key.restack', 'key.remove', 'key.remove-bend',
  'gesture.move', 'gesture.resize', 'gesture.bend', 'gesture.end', 'gesture.label', 'gesture.connect',
  'gesture.nest', 'gesture.rename',
  'bar.return-to-automatic', 'bar.automatic-boxes', 'page.lay-out-automatically',
] as const

export type CanvasCommandName = (typeof CANVAS_COMMANDS)[number]

/** What each command is an operation of on a page; null where it writes nothing there. */
export type CommandOperations = Readonly<Record<CanvasCommandName, string | null>>

const COMPOSE = 'diagram.compose'
const PLACE = 'diagram.layout.place'
const ROUTE = 'diagram.layout.route'
const RESTACK = 'diagram.layout.restack'

/** The diagram page: every command is part of the diagram's one save. */
export const DIAGRAM_OPERATIONS: CommandOperations = {
  'element.rename': 'model.element.rename',
  'element.details': 'model.element.edit',
  'element.connect': 'model.relation.create',
  'element.open': null,
  'element.nest': COMPOSE,
  'element.unnest': COMPOSE,
  'element.occurrence': COMPOSE,
  'element.restack': RESTACK,
  'element.remove': COMPOSE,
  'element.delete': 'model.element.delete',
  'element.discard': null,
  'line.edit': 'model.relation.edit',
  'line.straighten': ROUTE,
  'line.move-end': ROUTE,
  'line.relabel': COMPOSE,
  'line.draw': COMPOSE,
  'selection.align': PLACE,
  'selection.distribute': PLACE,
  'selection.box': COMPOSE,
  'selection.remove': COMPOSE,
  'box.rename': COMPOSE,
  'box.by-type': COMPOSE,
  'box.delete': COMPOSE,
  'canvas.place': COMPOSE,
  'canvas.create': 'model.element.create',
  'key.nudge': PLACE,
  'key.resize': PLACE,
  'key.nudge-label': ROUTE,
  'key.restack': RESTACK,
  'key.remove': COMPOSE,
  'key.remove-bend': ROUTE,
  'gesture.move': PLACE,
  'gesture.resize': PLACE,
  'gesture.bend': ROUTE,
  'gesture.end': ROUTE,
  'gesture.label': ROUTE,
  'gesture.connect': 'model.relation.create',
  'gesture.nest': COMPOSE,
  'gesture.rename': 'model.element.rename',
  'bar.return-to-automatic': PLACE,
  'bar.automatic-boxes': COMPOSE,
  'page.lay-out-automatically': 'diagram.body.generate',
}

/**
 * A candidate's page (06·5): what changes the model is recorded as an edit of the candidate; how its
 * picture is arranged is not kept, so arranging it is never refused.
 */
export const CANDIDATE_OPERATIONS: CommandOperations = {
  'element.rename': 'change_set.edit_entity',
  'element.details': 'change_set.edit_entity',
  'element.connect': 'change_set.add_connection',
  'element.open': null,
  'element.nest': 'change_set.add_connection',
  'element.unnest': null,
  'element.occurrence': null,
  'element.restack': null,
  'element.remove': null,
  'element.delete': 'change_set.remove_entity',
  'element.discard': null,
  'line.edit': 'change_set.edit_connection',
  'line.straighten': null,
  'line.move-end': null,
  'line.relabel': null,
  'line.draw': null,
  'selection.align': null,
  'selection.distribute': null,
  'selection.box': null,
  'selection.remove': null,
  'box.rename': null,
  'box.by-type': null,
  'box.delete': null,
  'canvas.place': null,
  'canvas.create': 'change_set.create_entity',
  'key.nudge': null,
  'key.resize': null,
  'key.nudge-label': null,
  'key.restack': null,
  'key.remove': null,
  'key.remove-bend': null,
  'gesture.move': null,
  'gesture.resize': null,
  'gesture.bend': null,
  'gesture.end': null,
  'gesture.label': null,
  'gesture.connect': 'change_set.add_connection',
  'gesture.nest': 'change_set.add_connection',
  'gesture.rename': 'change_set.edit_entity',
  'bar.return-to-automatic': null,
  'bar.automatic-boxes': null,
  'page.lay-out-automatically': null,
}
