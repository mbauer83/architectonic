"""Literal transcription of the ArchiMate specification's Appendix-C example-viewpoint
description tables (Table C-2 through Table C-26) — an independent record of what the
spec says, for the default viewpoint library's spec-fidelity test to compare the shipped
YAML definitions against. No imports from the ontology module or the runtime catalog:
this file is data only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StandardViewpointTable:
    slug: str
    table: str
    purpose: tuple[str, ...]
    stakeholders: tuple[str, ...]
    concerns: tuple[str, ...]
    entity_types: tuple[str, ...]  # excludes grouping/junctions (admitted in every viewpoint)


STANDARD_VIEWPOINT_TABLES: tuple[StandardViewpointTable, ...] = (
    StandardViewpointTable(
        slug='organization',
        table='Table C-2',
        purpose=('designing', 'deciding', 'informing'),
        stakeholders=(
            'Enterprise Architects', 'Process Architects', 'Domain Architects', 'managers', 'employees',
            'shareholders',
        ),
        concerns=('identification of competencies, authority, and responsibilities',),
        entity_types=('business-actor', 'business-interface', 'collaboration', 'location', 'role'),
    ),
    StandardViewpointTable(
        slug='application-structure',
        table='Table C-3',
        purpose=('designing',),
        stakeholders=('Application Architects', 'Solution Architects'),
        concerns=('application structure', 'consistency and completeness', 'reduction of complexity'),
        entity_types=('application-component', 'application-interface', 'collaboration', 'data-object'),
    ),
    StandardViewpointTable(
        slug='information-structure',
        table='Table C-4',
        purpose=('designing',),
        stakeholders=('Domain Architects', 'Information Architects'),
        concerns=('structure and dependencies of the used data and information', 'consistency', 'completeness'),
        entity_types=('artifact', 'business-object', 'data-object', 'meaning'),
    ),
    StandardViewpointTable(
        slug='technology',
        table='Table C-5',
        purpose=('designing',),
        stakeholders=('Infrastructure Architects', 'Operational Managers'),
        concerns=('stability', 'security', 'dependencies', 'costs of the infrastructure'),
        entity_types=(
            'artifact', 'collaboration', 'communication-network', 'device', 'event', 'function', 'location', 'path',
            'process', 'service', 'system-software', 'technology-interface', 'technology-node',
        ),
    ),
    StandardViewpointTable(
        slug='layered',
        table='Table C-6',
        purpose=('designing', 'deciding', 'informing'),
        stakeholders=(
            'Enterprise Architects', 'Process Architects', 'Application Architects', 'Infrastructure Architects',
            'Domain Architects',
        ),
        concerns=('consistency', 'reduction of complexity', 'impact of change', 'flexibility'),
        entity_types=(),
    ),
    StandardViewpointTable(
        slug='physical',
        table='Table C-7',
        purpose=('designing',),
        stakeholders=('Infrastructure Architects', 'Operational Managers'),
        concerns=(
            'relationships and dependencies of the physical environment and how this relates to IT infrastructure',
        ),
        entity_types=(
            'communication-network', 'device', 'distribution-network', 'equipment', 'facility', 'location',
            'material', 'path', 'technology-node',
        ),
    ),
    StandardViewpointTable(
        slug='product',
        table='Table C-8',
        purpose=('designing', 'deciding'),
        stakeholders=('Product Developers', 'Product Managers', 'Process Architects', 'Domain Architects'),
        concerns=('product development', 'value offered by the products of the enterprise'),
        entity_types=(
            'application-component', 'application-interface', 'artifact', 'business-actor', 'business-interface',
            'business-object', 'collaboration', 'data-object', 'event', 'function', 'material', 'process', 'product',
            'role', 'service', 'value',
        ),
    ),
    StandardViewpointTable(
        slug='application-usage',
        table='Table C-9',
        purpose=('designing', 'deciding'),
        stakeholders=('Enterprise Architects', 'Process Architects', 'Application Architects', 'Operational Managers'),
        concerns=('consistency and completeness', 'reduction of complexity'),
        entity_types=(
            'application-component', 'application-interface', 'business-actor', 'business-object', 'collaboration',
            'data-object', 'event', 'function', 'process', 'role', 'service',
        ),
    ),
    StandardViewpointTable(
        slug='technology-usage',
        table='Table C-10',
        purpose=('designing',),
        stakeholders=('Application Architects', 'Infrastructure Architects', 'Operational Managers'),
        concerns=('dependencies', 'performance', 'scalability'),
        entity_types=(
            'application-component', 'artifact', 'collaboration', 'communication-network', 'data-object', 'device',
            'event', 'function', 'path', 'process', 'service', 'system-software', 'technology-interface',
            'technology-node',
        ),
    ),
    StandardViewpointTable(
        slug='process-cooperation',
        table='Table C-11',
        purpose=('designing', 'deciding'),
        stakeholders=('Process Architects', 'Domain Architects', 'Operational Managers'),
        concerns=('dependencies between processes', 'consistency and completeness', 'responsibilities'),
        entity_types=(
            'application-component', 'application-interface', 'business-actor', 'business-interface',
            'business-object', 'collaboration', 'data-object', 'event', 'function', 'location', 'process', 'role',
            'service',
        ),
    ),
    StandardViewpointTable(
        slug='application-cooperation',
        table='Table C-12',
        purpose=('designing',),
        stakeholders=('Enterprise Architects', 'Process Architects', 'Application Architects', 'Domain Architects'),
        concerns=(
            'relationships and dependencies between applications', 'orchestration/choreography of services',
            'consistency and completeness', 'reduction of complexity',
        ),
        entity_types=(
            'application-component', 'application-interface', 'collaboration', 'data-object', 'event', 'function',
            'location', 'process', 'service',
        ),
    ),
    StandardViewpointTable(
        slug='service-realization',
        table='Table C-13',
        purpose=('designing', 'deciding'),
        stakeholders=('Process Architects', 'Domain Architects', 'Product Managers', 'Operational Managers'),
        concerns=('added value of processes', 'consistency and completeness', 'responsibilities'),
        entity_types=(
            'application-component', 'application-interface', 'business-actor', 'business-interface',
            'business-object', 'collaboration', 'data-object', 'event', 'function', 'process', 'role', 'service',
        ),
    ),
    StandardViewpointTable(
        slug='implementation-and-deployment',
        table='Table C-14',
        purpose=('designing', 'deciding'),
        stakeholders=('Application Architects', 'Domain Architects'),
        concerns=('structure of application platforms and how they relate to supporting technology',),
        entity_types=(
            'application-component', 'application-interface', 'artifact', 'collaboration', 'data-object', 'event',
            'function', 'path', 'process', 'service', 'system-software', 'technology-interface',
        ),
    ),
    StandardViewpointTable(
        slug='stakeholder',
        table='Table C-15',
        purpose=('designing', 'deciding', 'informing'),
        stakeholders=(
            'Stakeholders', 'Business Managers', 'Enterprise Architects', 'ICT Architects', 'Business Analysts',
            'Requirements Managers',
        ),
        concerns=('architecture mission and strategy', 'motivation'),
        entity_types=('assessment', 'driver', 'goal', 'outcome', 'stakeholder'),
    ),
    StandardViewpointTable(
        slug='goal-realization',
        table='Table C-16',
        purpose=('designing', 'deciding'),
        stakeholders=(
            'Stakeholders', 'Business Managers', 'Enterprise Architects', 'ICT Architects', 'Business Analysts',
            'Requirements Managers',
        ),
        concerns=('architecture mission, strategy and tactics', 'motivation'),
        entity_types=('goal', 'outcome', 'principle', 'requirement'),
    ),
    StandardViewpointTable(
        slug='requirements-realization',
        table='Table C-17',
        purpose=('designing', 'deciding', 'informing'),
        stakeholders=('Enterprise Architects', 'ICT Architects', 'Business Analysts', 'Requirements Managers'),
        concerns=('architecture strategy and tactics', 'motivation'),
        entity_types=(),
    ),
    StandardViewpointTable(
        slug='motivation',
        table='Table C-18',
        purpose=('designing', 'deciding', 'informing'),
        stakeholders=('Enterprise Architects', 'ICT Architects', 'Business Analysts', 'Requirements Managers'),
        concerns=('architecture strategy and tactics', 'motivation'),
        entity_types=(
            'assessment', 'driver', 'goal', 'meaning', 'outcome', 'principle', 'requirement', 'stakeholder', 'value',
        ),
    ),
    StandardViewpointTable(
        slug='strategy',
        table='Table C-19',
        purpose=('designing', 'deciding'),
        stakeholders=('CxOs', 'Business Managers', 'Enterprise Architects', 'Business Architects'),
        concerns=('strategy development',),
        entity_types=('capability', 'course-of-action', 'outcome', 'resource', 'value-stream'),
    ),
    StandardViewpointTable(
        slug='capability-map',
        table='Table C-20',
        purpose=('designing', 'deciding'),
        stakeholders=('Business Managers', 'Enterprise Architects', 'Business Architects'),
        concerns=('architecture strategy and tactics', 'motivation'),
        entity_types=('capability', 'outcome', 'resource'),
    ),
    StandardViewpointTable(
        slug='value-stream',
        table='Table C-21',
        purpose=('designing', 'deciding'),
        stakeholders=('Business Managers', 'Enterprise Architects', 'Business Architects'),
        concerns=('architecture strategy and tactics', 'motivation'),
        entity_types=('capability', 'outcome', 'stakeholder', 'value', 'value-stream'),
    ),
    StandardViewpointTable(
        slug='outcome-realization',
        table='Table C-22',
        purpose=('designing', 'deciding'),
        stakeholders=('Business Managers', 'Enterprise Architects', 'Business Architects'),
        concerns=('business-oriented results',),
        entity_types=(),
    ),
    StandardViewpointTable(
        slug='resource-map',
        table='Table C-23',
        purpose=('designing', 'deciding'),
        stakeholders=('Business Managers', 'Enterprise Architects', 'Business Architects'),
        concerns=('architecture strategy and tactics', 'motivation'),
        entity_types=('capability', 'resource', 'work-package'),
    ),
    StandardViewpointTable(
        slug='project',
        table='Table C-24',
        purpose=('deciding', 'informing'),
        stakeholders=('Operational Managers', 'Enterprise Architects', 'ICT Architects', 'employees', 'shareholders'),
        concerns=('architecture vision and policies', 'motivation'),
        entity_types=('business-actor', 'deliverable', 'event', 'goal', 'outcome', 'role', 'work-package'),
    ),
    StandardViewpointTable(
        slug='migration',
        table='Table C-25',
        purpose=('designing', 'deciding', 'informing'),
        stakeholders=(
            'Enterprise Architects', 'Process Architects', 'Application Architects', 'Infrastructure Architects',
            'Domain Architects', 'employees', 'shareholders',
        ),
        concerns=('history of models',),
        entity_types=('deliverable', 'plateau', 'work-package'),
    ),
    StandardViewpointTable(
        slug='implementation-and-migration',
        table='Table C-26',
        purpose=('deciding', 'informing'),
        stakeholders=('Operational Managers', 'Enterprise Architects', 'ICT Architects', 'employees', 'shareholders'),
        concerns=('architecture vision and policies', 'motivation'),
        entity_types=(
            'business-actor', 'deliverable', 'event', 'goal', 'location', 'plateau', 'requirement', 'role',
            'work-package',
        ),
    ),
)
