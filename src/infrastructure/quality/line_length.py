"""Frontend line-length policy: no source line may exceed the column limit.

Python line length is enforced natively by Ruff (E501, line-length=120); this module adds the
equivalent for the frontend (.ts/.vue), which the project's ESLint config does not cap. A large
backlog of pre-existing over-limit lines is grandfathered per file and may only ratchet DOWN:
an edited or new file may not INCREASE its count of over-limit lines, and a file absent from the
baseline must have none. No new long lines are introduced while the backlog is burned down —
lower or remove entries as files are cleaned. Mirrors the source_file_length baseline pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.infrastructure.quality.source_file_length import _iter_frontend_source_files

LINE_LENGTH_LIMIT = 120

# Grandfathered per-file counts of lines exceeding LINE_LENGTH_LIMIT. Ratchets DOWN only:
# never raise an entry, never add one — new/edited code must keep every line within the limit.
LINE_LENGTH_BASELINE: dict[str, int] = {
    "tools/gui/src/adapters/http/HttpModelRepository.ts": 4,
    "tools/gui/src/adapters/http/httpTransport.ts": 1,
    "tools/gui/src/application/ModelService.ts": 4,
    "tools/gui/src/domain/derivedCandidateReview.ts": 3,
    "tools/gui/src/domain/layeredViewQuery.ts": 1,
    "tools/gui/src/domain/schemas/diagram-types.ts": 1,
    "tools/gui/src/domain/viewpointBindings.ts": 2,
    "tools/gui/src/domain/viewpointBindingsSerialization.ts": 6,
    "tools/gui/src/domain/viewpointCriteria.ts": 1,
    "tools/gui/src/domain/viewpointCriteriaSerialization.ts": 3,
    "tools/gui/src/domain/viewpointIssuePath.ts": 1,
    "tools/gui/src/domain/viewpointPresentation.ts": 1,
    "tools/gui/src/domain/viewpointPresentationSerialization.ts": 1,
    "tools/gui/src/ports/ModelRepository.ts": 7,
    "tools/gui/src/ui/App.vue": 3,
    "tools/gui/src/ui/components/ArchimateOccurrenceControls.vue": 3,
    "tools/gui/src/ui/components/ArtifactReferenceInput.vue": 3,
    "tools/gui/src/ui/components/AssuranceDiagramPanel.vue": 6,
    "tools/gui/src/ui/components/AssuranceEdgePicker.vue": 1,
    "tools/gui/src/ui/components/CandidateReviewPanel.vue": 1,
    "tools/gui/src/ui/components/ConditionRow.vue": 3,
    "tools/gui/src/ui/components/ConnectionAddForm.vue": 1,
    "tools/gui/src/ui/components/ConnectionsPanel.vue": 1,
    "tools/gui/src/ui/components/CriteriaTreeBuilder.helpers.ts": 3,
    "tools/gui/src/ui/components/CriteriaTreeBuilder.vue": 3,
    "tools/gui/src/ui/components/DerivedSecurityAttributesPanel.helpers.ts": 1,
    "tools/gui/src/ui/components/DiagramC4Navigation.vue": 2,
    "tools/gui/src/ui/components/DiagramDeletePanel.vue": 3,
    "tools/gui/src/ui/components/DiagramDetailHeader.vue": 4,
    "tools/gui/src/ui/components/DiagramEditHeader.vue": 5,
    "tools/gui/src/ui/components/DiagramEditSidebar.vue": 7,
    "tools/gui/src/ui/components/DiagramEditViewpointBar.vue": 4,
    "tools/gui/src/ui/components/DiagramEntitySidebar.vue": 7,
    "tools/gui/src/ui/components/DiagramOwnEntityTypeSection.vue": 3,
    "tools/gui/src/ui/components/DiagramPreviewPanel.vue": 2,
    "tools/gui/src/ui/components/DiagramSyncPanel.vue": 4,
    "tools/gui/src/ui/components/DiagramTypeConfigPanel.vue": 2,
    "tools/gui/src/ui/components/DomainColorLegend.vue": 1,
    "tools/gui/src/ui/components/EdgeConnectionDetails.vue": 1,
    "tools/gui/src/ui/components/EntitiesTreemap.vue": 5,
    "tools/gui/src/ui/components/EntityEditFormCard.vue": 2,
    "tools/gui/src/ui/components/EntityGroupNavTree.vue": 3,
    "tools/gui/src/ui/components/EntityPickerFixedRows.vue": 3,
    "tools/gui/src/ui/components/EntityPickerInput.vue": 6,
    "tools/gui/src/ui/components/EntityRefValueInput.vue": 1,
    "tools/gui/src/ui/components/EntitySelectionList.vue": 5,
    "tools/gui/src/ui/components/ExecutionLinkActions.vue": 1,
    "tools/gui/src/ui/components/GraphCanvas.helpers.ts": 1,
    "tools/gui/src/ui/components/GraphNodeDetails.vue": 4,
    "tools/gui/src/ui/components/GrcControlsStep.vue": 2,
    "tools/gui/src/ui/components/GrcCoverageStep.vue": 1,
    "tools/gui/src/ui/components/GrcObligationsStep.vue": 2,
    "tools/gui/src/ui/components/GrcRisksStep.vue": 2,
    "tools/gui/src/ui/components/GrcTreatmentStep.vue": 1,
    "tools/gui/src/ui/components/GroupSelector.vue": 2,
    "tools/gui/src/ui/components/LayeredViewBuilderPanel.vue": 4,
    "tools/gui/src/ui/components/MaterializeConnectionDialog.vue": 2,
    "tools/gui/src/ui/components/MatrixAxesEditor.vue": 4,
    "tools/gui/src/ui/components/MatrixEntityList.vue": 7,
    "tools/gui/src/ui/components/ModelThisPanel.vue": 2,
    "tools/gui/src/ui/components/NavBar.vue": 5,
    "tools/gui/src/ui/components/NeighborInclusionEditor.vue": 7,
    "tools/gui/src/ui/components/PinnedViewpointsSection.vue": 1,
    "tools/gui/src/ui/components/PreviewViewport.vue": 2,
    "tools/gui/src/ui/components/PromotionArtifactGroup.vue": 1,
    "tools/gui/src/ui/components/PromotionPlanSummary.vue": 10,
    "tools/gui/src/ui/components/QueryBindingsPanel.vue": 7,
    "tools/gui/src/ui/components/QueryDerivedAttributesPanel.vue": 9,
    "tools/gui/src/ui/components/QueryParametersPanel.vue": 4,
    "tools/gui/src/ui/components/SaveChangesDialog.vue": 11,
    "tools/gui/src/ui/components/SecurityPostureDashboard.helpers.ts": 1,
    "tools/gui/src/ui/components/StyleRuleCard.vue": 10,
    "tools/gui/src/ui/components/StyleRuleEditor.vue": 3,
    "tools/gui/src/ui/components/StyleRuleScaleFields.vue": 1,
    "tools/gui/src/ui/components/StyleValuePicker.vue": 2,
    "tools/gui/src/ui/components/SyncStatusCluster.helpers.ts": 5,
    "tools/gui/src/ui/components/SyncStatusCluster.vue": 4,
    "tools/gui/src/ui/components/TargetPopulationEditor.vue": 1,
    "tools/gui/src/ui/components/ValueRefInput.vue": 4,
    "tools/gui/src/ui/components/ViewpointCatalogRow.vue": 3,
    "tools/gui/src/ui/components/ViewpointDefinitionsList.vue": 11,
    "tools/gui/src/ui/components/ViewpointEditorNotices.vue": 1,
    "tools/gui/src/ui/components/ViewpointEditorTabs.vue": 1,
    "tools/gui/src/ui/components/ViewpointExecutionDiagnostics.helpers.ts": 2,
    "tools/gui/src/ui/components/ViewpointExecutionError.vue": 1,
    "tools/gui/src/ui/components/ViewpointGeneralTab.vue": 2,
    "tools/gui/src/ui/components/ViewpointParameterPrompt.vue": 5,
    "tools/gui/src/ui/components/ViewpointPresentationTab.vue": 8,
    "tools/gui/src/ui/components/ViewpointQueryTab.vue": 11,
    "tools/gui/src/ui/components/ViewpointScopeTab.helpers.ts": 1,
    "tools/gui/src/ui/components/ViewpointScopeTab.vue": 14,
    "tools/gui/src/ui/components/ViewpointTablePage.vue": 7,
    "tools/gui/src/ui/components/WitnessChainPopover.vue": 1,
    "tools/gui/src/ui/components/WizardDomainStage.vue": 1,
    "tools/gui/src/ui/components/WizardEntityForm.vue": 1,
    "tools/gui/src/ui/components/WizardEntityStage.vue": 2,
    "tools/gui/src/ui/components/WizardQuestionnaireStage.vue": 1,
    "tools/gui/src/ui/composables/useAggregatedExploration.ts": 1,
    "tools/gui/src/ui/composables/useDiagramEditSelection.ts": 2,
    "tools/gui/src/ui/composables/useDiagramEditSvgOverlay.ts": 1,
    "tools/gui/src/ui/composables/useDiagramSvgSelection.ts": 2,
    "tools/gui/src/ui/composables/useEntityEditForm.ts": 1,
    "tools/gui/src/ui/composables/useForceGraph.ts": 2,
    "tools/gui/src/ui/composables/usePromotionWorkflow.ts": 11,
    "tools/gui/src/ui/diagram-types/activity/ActivityStepEditor.vue": 5,
    "tools/gui/src/ui/diagram-types/activity/ActivityStepItem.vue": 4,
    "tools/gui/src/ui/diagram-types/activity/NoteSection.vue": 3,
    "tools/gui/src/ui/diagram-types/c4/C4ConnectionSection.vue": 7,
    "tools/gui/src/ui/diagram-types/c4/C4DiagramEditor.vue": 4,
    "tools/gui/src/ui/diagram-types/datatype/AttributeRow.vue": 3,
    "tools/gui/src/ui/diagram-types/datatype/ClassifierCard.vue": 3,
    "tools/gui/src/ui/diagram-types/datatype/ClassifierMetadata.vue": 1,
    "tools/gui/src/ui/diagram-types/datatype/ConnRow.vue": 7,
    "tools/gui/src/ui/diagram-types/datatype/DatatypeEditor.vue": 2,
    "tools/gui/src/ui/diagram-types/datatype/DatatypeNoteSection.vue": 2,
    "tools/gui/src/ui/diagram-types/datatype/GeneralizationSetCard.vue": 3,
    "tools/gui/src/ui/diagram-types/datatype/KeysSection.vue": 1,
    "tools/gui/src/ui/diagram-types/datatype/OrderedAttrPicker.vue": 2,
    "tools/gui/src/ui/diagram-types/datatype/RelationList.vue": 1,
    "tools/gui/src/ui/diagram-types/datatype/StringListEditor.vue": 1,
    "tools/gui/src/ui/diagram-types/datatype/useDatatypeModel.ts": 3,
    "tools/gui/src/ui/diagram-types/datatype/useDtBackingConstraint.ts": 1,
    "tools/gui/src/ui/diagram-types/sequence/GroupingEditor.vue": 5,
    "tools/gui/src/ui/diagram-types/sequence/LifelineStrip.vue": 1,
    "tools/gui/src/ui/diagram-types/sequence/MessageList.vue": 2,
    "tools/gui/src/ui/diagram-types/sequence/MessageRow.vue": 3,
    "tools/gui/src/ui/diagram-types/sequence/NotesPanel.vue": 4,
    "tools/gui/src/ui/diagram-types/sequence/useSequenceModel.ts": 11,
    "tools/gui/src/ui/keys.ts": 1,
    "tools/gui/src/ui/lib/errors.ts": 1,
    "tools/gui/src/ui/lib/svgSanitize.ts": 1,
    "tools/gui/src/ui/lib/viewpointExecutionErrorText.ts": 2,
    "tools/gui/src/ui/lib/viewpointExecutionParameters.ts": 1,
    "tools/gui/src/ui/lib/viewpointUrlState.ts": 1,
    "tools/gui/src/ui/router/index.ts": 5,
    "tools/gui/src/ui/views/AssuranceAibomPanel.vue": 5,
    "tools/gui/src/ui/views/AssuranceBaselinesView.vue": 3,
    "tools/gui/src/ui/views/AssuranceCastWizard.helpers.ts": 1,
    "tools/gui/src/ui/views/AssuranceCastWizardView.vue": 7,
    "tools/gui/src/ui/views/AssuranceGrcWizardView.vue": 3,
    "tools/gui/src/ui/views/AssuranceNodeForm.vue": 2,
    "tools/gui/src/ui/views/AssuranceStpaWizardView.vue": 4,
    "tools/gui/src/ui/views/AssuranceSupplyChainWizardView.vue": 6,
    "tools/gui/src/ui/views/AssuranceView.vue": 1,
    "tools/gui/src/ui/views/CreateDiagramView.vue": 12,
    "tools/gui/src/ui/views/CreateMatrixView.vue": 5,
    "tools/gui/src/ui/views/DiagramDetailView.vue": 7,
    "tools/gui/src/ui/views/DocumentCreateView.vue": 3,
    "tools/gui/src/ui/views/DocumentDetailView.vue": 2,
    "tools/gui/src/ui/views/DocumentsView.vue": 1,
    "tools/gui/src/ui/views/EditDiagramView.vue": 3,
    "tools/gui/src/ui/views/EditMatrixView.vue": 5,
    "tools/gui/src/ui/views/EntitiesView.helpers.ts": 1,
    "tools/gui/src/ui/views/EntitiesView.vue": 11,
    "tools/gui/src/ui/views/EntityCreateView.vue": 1,
    "tools/gui/src/ui/views/EntityDetailView.vue": 2,
    "tools/gui/src/ui/views/GraphExploreView.aggregate.ts": 3,
    "tools/gui/src/ui/views/GraphExploreView.helpers.ts": 3,
    "tools/gui/src/ui/views/GraphExploreView.vue": 6,
    "tools/gui/src/ui/views/GroupManagementView.vue": 15,
    "tools/gui/src/ui/views/LayeredExplorationView.helpers.ts": 2,
    "tools/gui/src/ui/views/LayeredExplorationView.vue": 8,
    "tools/gui/src/ui/views/PromoteView.vue": 10,
    "tools/gui/src/ui/views/SearchView.vue": 1,
    "tools/gui/src/ui/views/ViewpointDiagramView.helpers.ts": 2,
    "tools/gui/src/ui/views/ViewpointDiagramView.vue": 9,
    "tools/gui/src/ui/views/ViewpointMatrixView.helpers.ts": 2,
    "tools/gui/src/ui/views/ViewpointMatrixView.vue": 4,
    "tools/gui/src/ui/views/ViewpointsManagementView.helpers.ts": 2,
    "tools/gui/src/ui/views/ViewpointsManagementView.vue": 10,
}


@dataclass(frozen=True)
class LineLengthViolation:
    path: str
    over_limit_lines: int
    baseline: int


def over_limit_line_count(path: Path) -> int:
    return sum(
        1 for line in path.read_text(encoding="utf-8").splitlines() if len(line) > LINE_LENGTH_LIMIT
    )


def find_line_length_violations(repo_root: Path) -> list[LineLengthViolation]:
    violations: list[LineLengthViolation] = []
    for path in _iter_frontend_source_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        count = over_limit_line_count(path)
        baseline = LINE_LENGTH_BASELINE.get(rel, 0)
        if count > baseline:
            violations.append(LineLengthViolation(path=rel, over_limit_lines=count, baseline=baseline))
    return violations
