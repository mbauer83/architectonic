from __future__ import annotations

from pathlib import Path

from src.diagram_types.sequence.renderer import SequencePumlRenderer


def _r(**kwargs: object) -> SequencePumlRenderer:
    return SequencePumlRenderer(dict(kwargs))


def _ll(ll_id: str, label: str, participant_type: str | None = None) -> dict[str, object]:
    m: dict[str, object] = {"id": ll_id, "label": label}
    if participant_type:
        m["participant_type"] = participant_type
    return m


def _msg(
    msg_id: str,
    label: str,
    arrow: str | None = None,
    *,
    activate_target: bool = False,
    deactivate_target: bool = False,
) -> dict[str, object]:
    m: dict[str, object] = {"id": msg_id, "label": label}
    if arrow:
        m["arrow"] = arrow
    if activate_target:
        m["activate_target"] = True
    if deactivate_target:
        m["deactivate_target"] = True
    return m


def _conn(conn_type: str, source: str, target: str) -> dict[str, object]:
    return {"id": f"c-{conn_type}-{source}", "conn_type": conn_type, "source": source, "target": target}


def _render(
    diagram_entities: object = None,
    name: str = "Flow",
    diagram_connections: list[dict[str, object]] | None = None,
) -> str:
    return _r().render_body(
        name, [], [], "sequence", Path("/tmp"),
        diagram_entities=diagram_entities,
        diagram_connections=diagram_connections,
    )


def test_empty_renders_startuml_enduml() -> None:
    puml = _render(diagram_entities={})
    assert "@startuml" in puml
    assert "@enduml" in puml


def test_lifeline_declared_as_participant() -> None:
    puml = _render(diagram_entities={"lifeline": [_ll("ll1", "Web App")]})
    assert 'participant "Web App" as ll1' in puml


def test_lifeline_actor_keyword() -> None:
    puml = _render(diagram_entities={"lifeline": [_ll("ll1", "User", "actor")]})
    assert 'actor "User" as ll1' in puml


def test_multiple_lifelines_sequential_aliases() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    puml = _render(diagram_entities={"lifeline": lls})
    assert "ll1" in puml
    assert "ll2" in puml


def test_simple_sync_message() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "request")]
    kcs = [_conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2")]
    puml = _render(diagram_entities={"lifeline": lls, "message": msgs}, diagram_connections=kcs)
    assert "ll1 -> ll2: request" in puml


def test_reply_arrow() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "response", "reply")]
    kcs = [_conn("seq-from", "m1", "ll2"), _conn("seq-to", "m1", "ll1")]
    puml = _render(diagram_entities={"lifeline": lls, "message": msgs}, diagram_connections=kcs)
    assert "ll2 --> ll1: response" in puml


def test_async_arrow() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "fire", "async")]
    kcs = [_conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2")]
    puml = _render(diagram_entities={"lifeline": lls, "message": msgs}, diagram_connections=kcs)
    assert "ll1 ->> ll2: fire" in puml


def test_messages_ordered_by_array_index() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    # m2 listed first in array but m1 should render first (array index 0 = first = m2)
    msgs = [_msg("m2", "second"), _msg("m1", "first")]
    kcs = [
        _conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2"),
        _conn("seq-from", "m2", "ll2"), _conn("seq-to", "m2", "ll1"),
    ]
    puml = _render(diagram_entities={"lifeline": lls, "message": msgs}, diagram_connections=kcs)
    # m2 is first in array, so "second" appears before "first"
    assert puml.index("second") < puml.index("first")


def test_connections_read_from_underscore_connections() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "call")]
    # Pass via _connections in diagram_entities (no separate diagram_connections)
    kcs = [_conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2")]
    puml = _render(diagram_entities={"lifeline": lls, "message": msgs, "_connections": kcs})
    assert "ll1 -> ll2: call" in puml


def test_opt_grouping_wraps_messages() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "call")]
    grps = [{"id": "g1", "kind": "opt", "operands": [
        {"guard": "if ready", "start_message_id": "m1", "end_message_id": "m1"},
    ]}]
    kcs = [_conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2")]
    puml = _render(
        diagram_entities={"lifeline": lls, "message": msgs, "grouping": grps},
        diagram_connections=kcs,
    )
    assert "opt [if ready]" in puml
    assert "end" in puml
    assert puml.index("opt [if ready]") < puml.index("ll1 -> ll2: call")
    assert puml.index("ll1 -> ll2: call") < puml.rindex("end")


def test_alt_grouping_with_else() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "yes-path"), _msg("m2", "no-path")]
    grps = [{"id": "g1", "kind": "alt", "operands": [
        {"guard": "success", "start_message_id": "m1", "end_message_id": "m1"},
        {"guard": "failure", "start_message_id": "m2", "end_message_id": "m2"},
    ]}]
    kcs = [
        _conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2"),
        _conn("seq-from", "m2", "ll2"), _conn("seq-to", "m2", "ll1"),
    ]
    puml = _render(
        diagram_entities={"lifeline": lls, "message": msgs, "grouping": grps},
        diagram_connections=kcs,
    )
    assert "alt [success]" in puml
    assert "else [failure]" in puml
    assert "end" in puml
    assert puml.index("alt [success]") < puml.index("yes-path")
    assert puml.index("yes-path") < puml.index("else [failure]")
    assert puml.index("else [failure]") < puml.index("no-path")


def test_loop_grouping_with_label() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "poll")]
    grps = [{"id": "g1", "kind": "loop", "label": "until done", "operands": [
        {"start_message_id": "m1", "end_message_id": "m1"},
    ]}]
    kcs = [_conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2")]
    puml = _render(
        diagram_entities={"lifeline": lls, "message": msgs, "grouping": grps},
        diagram_connections=kcs,
    )
    assert "loop until done" in puml


def test_group_kind_uses_label() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "op")]
    grps = [{"id": "g1", "kind": "group", "label": "Transaction", "operands": [
        {"start_message_id": "m1", "end_message_id": "m1"},
    ]}]
    kcs = [_conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2")]
    puml = _render(
        diagram_entities={"lifeline": lls, "message": msgs, "grouping": grps},
        diagram_connections=kcs,
    )
    assert "group Transaction" in puml


def test_activate_target_flag() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "start", activate_target=True)]
    kcs = [_conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2")]
    puml = _render(diagram_entities={"lifeline": lls, "message": msgs}, diagram_connections=kcs)
    assert "ll1 -> ll2 ++: start" in puml


def test_deactivate_target_flag() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "done", deactivate_target=True)]
    kcs = [_conn("seq-from", "m1", "ll2"), _conn("seq-to", "m1", "ll1")]
    puml = _render(diagram_entities={"lifeline": lls, "message": msgs}, diagram_connections=kcs)
    assert "ll2 -> ll1 --: done" in puml


def test_note_right_of_lifeline() -> None:
    lls = [_ll("ll1", "A")]
    notes = [{"id": "n1", "text": "important", "placement": "right_of", "lifeline_ids": ["ll1"]}]
    puml = _render(diagram_entities={"lifeline": lls, "note": notes})
    assert "note right of ll1: important" in puml


def test_note_left_of_lifeline() -> None:
    lls = [_ll("ll1", "A")]
    notes = [{"id": "n1", "text": "left note", "placement": "left_of", "lifeline_ids": ["ll1"]}]
    puml = _render(diagram_entities={"lifeline": lls, "note": notes})
    assert "note left of ll1: left note" in puml


def test_note_over_multiple_lifelines() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    notes = [{"id": "n1", "text": "shared", "placement": "over", "lifeline_ids": ["ll1", "ll2"]}]
    puml = _render(diagram_entities={"lifeline": lls, "note": notes})
    assert "note over ll1, ll2: shared" in puml


def test_note_after_message() -> None:
    lls = [_ll("ll1", "A"), _ll("ll2", "B")]
    msgs = [_msg("m1", "call"), _msg("m2", "callback")]
    notes = [{"id": "n1", "text": "check here", "placement": "right_of",
              "lifeline_ids": ["ll1"], "after_message_id": "m1"}]
    kcs = [
        _conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll2"),
        _conn("seq-from", "m2", "ll2"), _conn("seq-to", "m2", "ll1"),
    ]
    puml = _render(
        diagram_entities={"lifeline": lls, "message": msgs, "note": notes},
        diagram_connections=kcs,
    )
    assert puml.index("ll1 -> ll2: call") < puml.index("note right of ll1: check here")
    assert puml.index("note right of ll1: check here") < puml.index("ll2 -> ll1: callback")


def test_self_message() -> None:
    lls = [_ll("ll1", "A")]
    msgs = [_msg("m1", "think", "self")]
    kcs = [_conn("seq-from", "m1", "ll1"), _conn("seq-to", "m1", "ll1")]
    puml = _render(diagram_entities={"lifeline": lls, "message": msgs}, diagram_connections=kcs)
    assert "ll1 -> ll1: think" in puml


def test_title_uses_diagram_name() -> None:
    puml = _render(diagram_entities={}, name="My Sequence")
    assert "title My Sequence" in puml


def test_collect_references_reads_entity_and_connection_bindings() -> None:
    renderer = _r()
    bindings = [
        {"id": "b1", "subject": {"kind": "entity", "id": "ll1"},
         "correspondence_kind": "represents", "target": {"entity_id": "ENT@123"}},
        {"id": "b2", "subject": {"kind": "connection", "id": "m1"},
         "correspondence_kind": "represents", "target": {"connection_id": "A---B@@serving"}},
        {"id": "b3", "subject": {"kind": "connection", "id": "m2"},
         "correspondence_kind": "abstracts",
         "target": {"connection_ids": ["A---B@@flow", "B---C@@access"]}},
    ]
    refs = renderer.collect_references("sequence", Path("/tmp"), bindings=bindings)
    assert "ENT@123" in refs.entity_ids
    assert "A---B@@serving" in refs.connection_ids
    assert "A---B@@flow" in refs.connection_ids
    assert "B---C@@access" in refs.connection_ids
