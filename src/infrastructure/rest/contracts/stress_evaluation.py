"""A stress analysis's test set, the residuality it gives, and the perspectives offered to stressor writers."""
from typing import Literal

from pydantic import Field

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted
from src.infrastructure.rest.contracts.wire_shape import Closed


class HeldApartStressor(NullsOmitted):
    id: str
    stressor: str
    kind: str | None = None
    usable: bool = Field(description="False once a judge has struck it; it then leaves every denominator.")
    unusable_reason: str | None = Field(None, description="Why it was struck, in the judge's words.")


class StressVerdict(NullsOmitted):
    id: str = Field(description="The survival row holding the verdict.")
    stressor: str
    architecture: str = Field(description="`naive`, or the judged candidate's id.")
    verdict: Literal["survives", "degrades", "fails"] | None = Field(
        None, description="Absent on a row that only strikes the stressor.",
    )
    usable: bool
    reasoning: str


class ArchitectureStanding(NullsOmitted):
    architecture: str = Field(description="`naive`, or a candidate's id.")
    integrated: bool = Field(description="Whether this candidate has been integrated into the model.")
    usable: int = Field(description="How many test stressors are usable: the denominator n.")
    judged: int
    survives: int
    degrades: int
    fails: int
    naive_survives: int
    residuality: float | None = Field(
        None, description="(Y − X) / n with a degraded verdict counting one half; absent until both this "
        "architecture and the naive are judged on every usable stressor, and for the naive itself.",
    )
    strict: float | None = Field(None, description="The same with full survivals only.")


class EvaluationStage(NullsOmitted):
    """Where the procedure stands: naive judged, then adapted, then integrated, then the integration judged."""

    naive_judged: bool
    adapted: bool
    integrated: bool
    integration_judged: bool


class AnalysisEvaluation(NullsOmitted):
    document: str
    naive_candidate: str
    design_stressors: int = Field(description="How many stressors the design set holds, which a hold-out draws from.")
    stressors: list[HeldApartStressor]
    verdicts: list[StressVerdict]
    architectures: list[ArchitectureStanding] = Field(description="The naive first, then integrated, then judged.")
    stage: EvaluationStage


class HoldOut(Closed):
    """Hold a random third of the design stressors out into the test set."""

    seed: int | None = Field(None, description="Draw with this seed; a seed is chosen and answered when none is.")
    dry_run: bool = True


class HeldOut(Closed):
    document: str
    seed: int = Field(description="The seed drawn with: the same seed over the same stressors draws the same third.")
    dry_run: bool
    wrote: bool
    design_stressors: int = Field(description="How many design stressors the third was drawn from.")
    held_out: list[str] = Field(description="The stressors moved into the test set, by row id.")


class AnalysisStanding(ArchitectureStanding):
    document: str
    title: str


class CandidateResiduality(NullsOmitted):
    candidate: str
    analyses: list[AnalysisStanding] = Field(description="Each analysis that judged or integrated the candidate.")


class StressPerspective(Closed):
    id: str
    name: str
    kind: str = Field(description="What choosing it may put in a stressor's optional kind.")
    question: str


class PerspectiveFramework(Closed):
    id: str
    name: str
    perspectives: list[StressPerspective]


class StressPerspectives(Closed):
    frameworks: list[PerspectiveFramework]
