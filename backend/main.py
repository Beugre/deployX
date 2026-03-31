"""
DeployX — Backend FastAPI.
Façade sécurisée entre le frontend Streamlit et l'API Azure DevOps.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from azure_devops_client import AzureDevOpsClient, AzureDevOpsClientError
from models import (
    BuildHistoryEntry,
    DeploymentDetail,
    DeploymentSummary,
    PipelineDefinition,
    QueueBuildRequest,
    TimelineResponse,
)

# Charger les variables d'environnement depuis .env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# ------------------------------------------------------------------ #
#  Initialisation
# ------------------------------------------------------------------ #

client: AzureDevOpsClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise le client Azure DevOps au démarrage."""
    global client
    try:
        client = AzureDevOpsClient()
    except AzureDevOpsClientError as exc:
        print(f"⚠️  Impossible d'initialiser le client Azure DevOps : {exc.message}")
        print("   Vérifiez les variables AZDO_ORG, AZDO_PROJECT et AZDO_PAT.")
        raise SystemExit(1)
    yield


app = FastAPI(
    title="DeployX API",
    description="Façade sécurisée pour le suivi des déploiements Azure DevOps",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — autorise le frontend Streamlit et l'embed Appian
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restreindre en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ #
#  Health check
# ------------------------------------------------------------------ #


@app.get("/health", tags=["Infra"])
async def health():
    return {"status": "ok"}


# ------------------------------------------------------------------ #
#  Endpoints Déploiements
# ------------------------------------------------------------------ #


@app.get(
    "/deployments",
    response_model=list[DeploymentSummary],
    tags=["Deployments"],
    summary="Liste des déploiements",
)
async def list_deployments(
    top: int = Query(50, ge=1, le=200, description="Nombre max de résultats"),
    branch: Optional[str] = Query(None, description="Filtrer par branche"),
    status: Optional[str] = Query(None, description="Filtrer par statut (inProgress, completed, …)"),
    result: Optional[str] = Query(None, description="Filtrer par résultat (succeeded, failed, canceled, partiallySucceeded)"),
    definition_id: Optional[int] = Query(None, description="Filtrer par pipeline definition ID"),
):
    """Retourne la liste des derniers déploiements Azure DevOps."""
    try:
        return await client.list_builds(
            top=top, branch=branch, status=status, result=result, definition_id=definition_id
        )
    except AzureDevOpsClientError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message)


@app.get(
    "/deployments/{build_id}",
    response_model=DeploymentDetail,
    tags=["Deployments"],
    summary="Détail d'un déploiement",
)
async def get_deployment(build_id: int):
    """Retourne le détail complet d'un déploiement, y compris la hiérarchie stage/job/step."""
    try:
        return await client.get_build(build_id)
    except AzureDevOpsClientError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message)


@app.get(
    "/deployments/{build_id}/timeline",
    response_model=TimelineResponse,
    tags=["Deployments"],
    summary="Timeline détaillée d'un déploiement",
)
async def get_deployment_timeline(build_id: int):
    """Retourne la timeline structurée (Stage → Job → Step) d'un déploiement."""
    try:
        return await client.get_timeline(build_id)
    except AzureDevOpsClientError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message)


@app.get(
    "/deployments/{build_id}/logs/{log_id}",
    tags=["Deployments"],
    summary="Contenu d'un log de step",
)
async def get_build_log(build_id: int, log_id: int):
    """Retourne le contenu texte brut d'un log d'étape."""
    try:
        content = await client.get_build_log(build_id, log_id)
        return {"log_id": log_id, "content": content}
    except AzureDevOpsClientError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message)


# ------------------------------------------------------------------ #
#  Endpoints Pipelines
# ------------------------------------------------------------------ #


@app.get(
    "/pipelines",
    response_model=list[PipelineDefinition],
    tags=["Pipelines"],
    summary="Liste des pipelines",
)
async def list_pipelines():
    """Retourne la liste des définitions de pipelines Azure DevOps."""
    try:
        return await client.list_definitions()
    except AzureDevOpsClientError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message)


@app.post(
    "/pipelines/{definition_id}/run",
    tags=["Pipelines"],
    summary="Lancer une pipeline",
)
async def run_pipeline(definition_id: int, branch: Optional[str] = Query(None, description="Branche source")):
    """Déclenche un nouveau build pour la pipeline spécifiée."""
    try:
        return await client.queue_build(definition_id, branch)
    except AzureDevOpsClientError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message)


@app.post(
    "/deployments/{build_id}/cancel",
    tags=["Deployments"],
    summary="Annuler un déploiement",
)
async def cancel_deployment(build_id: int):
    """Annule un build en cours."""
    try:
        return await client.cancel_build(build_id)
    except AzureDevOpsClientError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message)


@app.get(
    "/pipelines/{definition_id}/history",
    response_model=list[BuildHistoryEntry],
    tags=["Pipelines"],
    summary="Historique d'une pipeline",
)
async def get_pipeline_history(
    definition_id: int,
    top: int = Query(30, ge=1, le=100, description="Nombre de builds"),
):
    """Retourne l'historique des builds pour une pipeline."""
    try:
        return await client.get_build_history(definition_id, top)
    except AzureDevOpsClientError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=exc.message)
