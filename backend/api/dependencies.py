"""
backend/api/dependencies.py

POST /api/dependencies/analyze

Accepts a path to an EXE or DLL, runs Stage 2 (PEAnalyzer) and Stage 3
(DependencyAnalyzer), and returns the full dependency graph with architecture
relationships.

Scientific-language rule: the response describes what was *observed* in the
PE headers.  It never says "incompatible" or "crashed".  Consumers must read
the architecture_relationships list and their associated severity / reason
fields to form their own assessment.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.analyzers.dependency_analyzer import DependencyAnalyzer
from backend.analyzers.pe_analyzer import PEAnalyzer
from backend.models.graph import (
    ArchitectureRelationship,
    DependencyEdge,
    DependencyNode,
)
from backend.models.application import ApplicationIdentity
from backend.twin.graph import ExecutionTwinGraph

router = APIRouter(prefix="/api/dependencies", tags=["dependencies"])


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    path: str = Field(description="Absolute path to the EXE or DLL to analyse.")
    max_depth: int = Field(default=32, ge=0, le=64)
    analyze_system_dlls: bool = False
    extra_search_paths: list[str] = Field(default_factory=list)


class GraphSummary(BaseModel):
    total_nodes:               int
    total_edges:               int
    total_dependencies:        int
    resolved:                  int
    missing:                   int
    skipped:                   int
    max_depth_reached:         int
    cycles_detected:           int
    architecture_relationships: int
    analysis_complete:         bool


class AnalyzeResponse(BaseModel):
    application:               ApplicationIdentity
    nodes:                     list[DependencyNode]
    edges:                     list[DependencyEdge]
    architecture_relationships: list[ArchitectureRelationship]
    graph_summary:             GraphSummary
    warnings:                  list[str]
    errors:                    list[str]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_dependencies(req: AnalyzeRequest) -> AnalyzeResponse:
    # Stage 2: PE analysis of the root binary
    pe_analysis = PEAnalyzer().analyze(req.path)

    # Stage 3: recursive dependency traversal
    dep_analyzer = DependencyAnalyzer(
        max_depth=req.max_depth,
        analyze_system_dlls=req.analyze_system_dlls,
        extra_search_paths=req.extra_search_paths,
    )
    dep_analysis = dep_analyzer.analyze(pe_analysis)

    # Build the twin graph for summary statistics
    twin_graph = ExecutionTwinGraph.from_analysis(dep_analysis)
    summary_dict = twin_graph.summary()

    graph_summary = GraphSummary(
        total_nodes=summary_dict["total_nodes"],
        total_edges=summary_dict["total_edges"],
        total_dependencies=summary_dict["total_dependencies"],
        resolved=summary_dict["resolved"],
        missing=summary_dict["missing"],
        skipped=summary_dict["skipped"],
        max_depth_reached=summary_dict["max_depth_reached"],
        cycles_detected=summary_dict["cycles"],
        architecture_relationships=summary_dict["architecture_relationships"],
        analysis_complete=summary_dict["analysis_complete"],
    )

    warnings = pe_analysis.analyzer_warnings + dep_analysis.analyzer_warnings
    errors   = pe_analysis.analyzer_errors   + dep_analysis.analyzer_errors

    return AnalyzeResponse(
        application=pe_analysis.identity,
        nodes=dep_analysis.nodes,
        edges=dep_analysis.edges,
        architecture_relationships=dep_analysis.architecture_relationships,
        graph_summary=graph_summary,
        warnings=warnings,
        errors=errors,
    )
