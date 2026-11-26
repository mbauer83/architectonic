"""An entity a candidate creates is read as one entity once the model holds it under the id chosen for it.

Operations name it by the create's reference; the model holds it by its id. A view that read the model by id
and the stack by reference held it twice, and a comparison against the model listed it removed and added. The
view answers it by that id either way.
"""

from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.candidate_view import CandidateView, difference, view_of
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import AddConnection, ConnectionAddress, CreateEntity
from src.application.change_sets.reading import RecordedReading

_ID = "APP@1795000000.aBcDeFg"
_OTHER = "APP@1795000000.hIjKlMn"
_CREATE = CreateEntity("cache", {"artifact_type": "application-component", "name": "Cache", "group": "g"}, _ID)
_LINK = AddConnection(ConnectionAddress(_CREATE.reference, "archimate-serving", _OTHER), {})


def _candidate() -> CandidateArchitecture:
    return CandidateArchitecture("CAND@1.a", "Cached", "", "draft", ChangeSet((_CREATE, _LINK), "r1"),
                                 scope=(_OTHER,))


def _live(*, holding: bool) -> RecordedReading:
    other = {"artifact_type": "application-component", "name": "Other", "status": "active"}
    created = {"artifact_type": "application-component", "name": "Cache", "group": "g", "status": "draft"}
    served = {ConnectionAddress(_ID, "archimate-serving", _OTHER): {}} if holding else {}
    return RecordedReading({_OTHER: other, **({_ID: created} if holding else {})}, served)


def test_the_view_holds_a_created_entity_once_whether_or_not_the_model_holds_it() -> None:
    for holding in (False, True):
        view = view_of((_candidate(),), _live(holding=holding))
        assert set(view.entities) == {_ID, _OTHER}, holding
        assert view.chosen == {_ID: _ID}
        assert set(view.connections) == {ConnectionAddress(_ID, "archimate-serving", _OTHER)}


def test_what_the_model_holds_of_it_is_read_under_the_create_with_what_the_create_states_over_it() -> None:
    view = view_of((_candidate(),), _live(holding=True))
    assert view.entities[_ID]["status"] == "draft"  # the model's, which the create does not state
    assert view.entities[_ID]["name"] == "Cache"


def test_against_the_model_that_holds_it_nothing_is_listed_twice() -> None:
    live = _live(holding=True)
    before = CandidateView(dict(live.entities), dict(live.connections))
    changes = difference(before, view_of((_candidate(),), live))
    assert changes == []
