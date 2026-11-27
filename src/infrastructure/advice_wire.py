"""How an advice acknowledgement is sent over the wire, by REST and MCP alike.

One declaration for both surfaces, so the published schema and the tool's argument say the same
thing. What makes an acknowledgement acceptable — an advice code, a short reason — is decided by
`verification_advice.checked_acknowledgements` in the write path, not here: this is the shape only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from src.domain.verification_advice import ADVICE_CODES, REASON_MAX_LENGTH

_CODES = ", ".join(sorted(ADVICE_CODES))


class AcceptedAdviceEntry(BaseModel):
    """One acknowledged advice: the code, and why the element is right as it stands."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        description=f"The advice code acknowledged ({_CODES}). Warning (W…) and error (E…) codes are refused."
    )
    reason: str = Field(description=f"Why the element is right as it stands; at most {REASON_MAX_LENGTH} characters.")


#: The description an edit or create surface gives the field.
ACCEPTED_ADVICE_DESCRIPTION = (
    "Acknowledged advice, as [{code, reason}]. Replaces the stored set; [] clears it. An acknowledged "
    "advice is quiet at every status. Only advice codes are accepted: acknowledging a warning or an "
    "error is refused."
)


def acknowledgements(
    entries: Sequence[AcceptedAdviceEntry | Mapping[str, object]] | None,
) -> list[dict[str, str]] | None:
    """The entries as the plain mappings the write path checks, or None where none were sent.

    Each is validated into the wire shape first, so a caller handing the tool function plain mappings
    — as a direct Python caller does, where the MCP framework would have validated — meets the same
    refusal of an unknown key.
    """
    return None if entries is None else [AcceptedAdviceEntry.model_validate(entry).model_dump() for entry in entries]
