from __future__ import annotations

from enum import Enum
from typing import Any

from sleep_ai_scientist.common.pydantic_compat import BaseModel, Field


class NodeType(str, Enum):
    Paper = "Paper"
    Finding = "Finding"
    Mechanism = "Mechanism"
    Variable = "Variable"
    Modality = "Modality"
    DataFeature = "DataFeature"
    Confound = "Confound"


class EdgeType(str, Enum):
    paper_reports_finding = "paper_reports_finding"
    finding_supports_mechanism = "finding_supports_mechanism"
    finding_refutes_mechanism = "finding_refutes_mechanism"
    mechanism_measured_by_variable = "mechanism_measured_by_variable"
    variable_belongs_to_modality = "variable_belongs_to_modality"
    variable_mapped_to_data_feature = "variable_mapped_to_data_feature"
    confound_affects_variable = "confound_affects_variable"


class GraphNode(BaseModel):
    node_id: str
    label: str
    node_type: NodeType
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
