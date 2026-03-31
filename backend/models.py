"""
Modèles Pydantic pour DeployX.
Définit les structures de données utilisées pour la transformation
de la timeline Azure DevOps en hiérarchie Stage → Job → Step.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class StepDetail(BaseModel):
    """Étape individuelle d'un job (task Azure DevOps)."""
    name: str
    status: str
    order: Optional[int] = None
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    duration: Optional[float] = None  # secondes
    error_message: Optional[str] = None
    log_url: Optional[str] = None


class JobDetail(BaseModel):
    """Job au sein d'un stage."""
    name: str
    status: str
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    duration: Optional[float] = None
    error_message: Optional[str] = None
    steps: list[StepDetail] = []


class StageDetail(BaseModel):
    """Stage de pipeline (ex: Build, Deploy)."""
    name: str
    status: str
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    duration: Optional[float] = None
    error_message: Optional[str] = None
    jobs: list[JobDetail] = []


class DeploymentSummary(BaseModel):
    """Résumé d'un déploiement pour la liste."""
    id: int
    pipeline_name: str
    definition_id: Optional[int] = None
    status: str
    branch: Optional[str] = None
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    duration: Optional[float] = None
    triggered_by: Optional[str] = None
    result: Optional[str] = None


class DeploymentDetail(BaseModel):
    """Détail complet d'un déploiement incluant la hiérarchie."""
    id: int
    pipeline_name: str
    definition_id: Optional[int] = None
    status: str
    result: Optional[str] = None
    branch: Optional[str] = None
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    duration: Optional[float] = None
    triggered_by: Optional[str] = None
    source_version: Optional[str] = None
    stages: list[StageDetail] = []


class TimelineResponse(BaseModel):
    """Réponse timeline structurée."""
    build_id: int
    stages: list[StageDetail] = []


class PipelineDefinition(BaseModel):
    """Définition de pipeline Azure DevOps."""
    id: int
    name: str
    path: Optional[str] = None
    default_branch: Optional[str] = None
    url: Optional[str] = None


class QueueBuildRequest(BaseModel):
    """Requête pour lancer un build."""
    definition_id: int
    branch: Optional[str] = None


class BuildHistoryEntry(BaseModel):
    """Entrée d'historique simplifié pour un graphique."""
    id: int
    status: str
    result: Optional[str] = None
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    duration: Optional[float] = None
