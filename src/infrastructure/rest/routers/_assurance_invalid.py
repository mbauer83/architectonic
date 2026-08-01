"""How an ``AnalysisInvalid`` becomes an HTTP refusal — one mapping, exhaustive by test.

``AnalysisInvalid`` carries a free-form ``error`` string, and both routers used to put it straight on
the wire as ``{"error": <that string>, "message": ...}`` with status 400. Three things were wrong with
that, and only the first is about shape:

* the body was not the shared envelope, so a client branching on ``detail.code`` fell through;
* the *string* was not in the closed vocabulary — five codes reached clients that the published
  ``ErrorCode`` union never declared;
* the *status* was 400 for all five, including two the plan assigns elsewhere: an analysis that
  authored nodes is ``409 analysis_not_empty`` (it is a state conflict, not a malformed request), and
  a missing group is ``404``. A 400 for either tells the caller to fix a request that was correct.

So the translation lives here, once, as a table — and ``tests/assurance/test_analysis_invalid_mapping.py``
extracts every code the use cases can construct and fails if one is missing from it. A sixth code
added to an application module cannot quietly inherit a generic 400.
"""

from __future__ import annotations

from src.application.assurance.analysis import AnalysisInvalid
from src.application.assurance.model_bind import BindInvalid
from src.infrastructure.rest.contracts.errors import (
    AnalysisNotEmptyDetails,
    ApiError,
    ErrorCode,
    FieldError,
    ValidationErrorDetails,
)

#: Which field each rejected-value code is about, so the envelope can carry a path a client
#: highlights rather than prose it has to parse.
_REJECTED_FIELD: dict[str, str] = {
    "missing_name": "name",
    "invalid_method": "method",
    "invalid_status": "status",
}

#: The status and code each application-level invalid maps to. Exhaustive over what the use cases
#: construct; the accompanying test is what keeps it that way.
_MAPPING: dict[str, tuple[int, ErrorCode]] = {
    "missing_name": (422, "validation_error"),
    "invalid_method": (422, "validation_error"),
    "invalid_status": (422, "validation_error"),
    "group_not_found": (404, "not_found"),
    "analysis_not_empty": (409, "analysis_not_empty"),
}


def invalid_as_api_error(result: AnalysisInvalid) -> ApiError:
    """The refusal this invariant violation is, in the shared envelope — returned to be ``raise``d.

    An unmapped code is a programming error rather than a client's, so it fails loudly here instead of
    reaching a client as an undeclared string: the whole point of a closed vocabulary is that nothing
    escapes it, and a permissive fallback would quietly reopen the hole this module closes.
    """
    mapped = _MAPPING.get(result.error)
    if mapped is None:  # pragma: no cover - the mapping test makes this unreachable
        raise AssertionError(
            f"AnalysisInvalid({result.error!r}) has no HTTP mapping. Add it to _MAPPING in "
            "_assurance_invalid.py, with a code from the closed ErrorCode vocabulary."
        )
    status_code, code = mapped
    if code == "validation_error":
        field = _REJECTED_FIELD[result.error]
        return ApiError(
            status_code,
            code,
            result.message,
            ValidationErrorDetails(field_errors=[FieldError(field=field, message=result.message)]),
        )
    if code == "analysis_not_empty":
        # No reassignment is offered in either the message or the details: provenance is immutable, so
        # the only resolutions are to delete the authored nodes or leave the analysis in place.
        return ApiError(
            status_code,
            code,
            result.message,
            AnalysisNotEmptyDetails(
                analysis_id=result.subject, authored_node_count=result.count
            ),
        )
    return ApiError(status_code, code, result.message)


#: The bind use case's own invalids. Neither needs a new vocabulary member: one is a state conflict and
#: the other a rejected value, which the closed union already names.
_BIND_MAPPING: dict[str, tuple[int, ErrorCode]] = {
    # The node is not in the state this operation applies to — nothing the caller sent is wrong.
    "invalid_binding_status": (409, "conflict"),
    # A type name the ontology does not know: a rejected value, so it carries its field.
    "unknown_arch_type": (422, "validation_error"),
}

_BIND_FIELD: dict[str, str] = {"unknown_arch_type": "suggested_arch_type"}


def bind_invalid_as_api_error(result: BindInvalid) -> ApiError:
    """The model-and-bind refusal, in the shared envelope — returned to be ``raise``d.

    Beside the analysis mapping rather than inside the router for the same reason: the status a refusal
    carries is a decision about what kind of failure it is, and deciding that inline is how one of them
    came to be a 400 that told the caller to fix a correct request.
    """
    mapped = _BIND_MAPPING.get(result.error)
    if mapped is None:  # pragma: no cover - the mapping test makes this unreachable
        raise AssertionError(
            f"BindInvalid({result.error!r}) has no HTTP mapping. Add it to _BIND_MAPPING."
        )
    status_code, code = mapped
    if code == "validation_error":
        return ApiError(
            status_code,
            code,
            result.message,
            ValidationErrorDetails(field_errors=[
                FieldError(field=_BIND_FIELD[result.error], message=result.message)
            ]),
        )
    return ApiError(status_code, code, result.message)
