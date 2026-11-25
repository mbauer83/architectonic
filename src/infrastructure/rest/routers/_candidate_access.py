"""The candidate service the candidate and analysis routers act through, and how its refusals are answered."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from src.application.artifacts.document_part_edits import RowChangedSinceRead
from src.infrastructure.candidates.repository import CandidateConflict, NotStored
from src.infrastructure.candidates.service import CandidateService
from src.infrastructure.rest.routers import state as s


def service() -> CandidateService:
    root = s.maybe_engagement_root()
    if root is None:
        raise HTTPException(503, "Engagement repository is not initialised")
    return CandidateService(root)


@contextmanager
def refusals() -> Iterator[None]:
    """Not found as 404; a conflicting candidate, or a row changed since it was read, as 409; the rest as 422."""
    try:
        yield
    except NotStored as exc:
        raise HTTPException(404, str(exc)) from exc
    except (CandidateConflict, RowChangedSinceRead) as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
