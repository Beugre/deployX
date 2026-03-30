"""
Client Azure DevOps REST API.
Façade sécurisée pour communiquer avec l'API Azure DevOps.
Gère l'authentification Basic Auth (PAT) et la transformation des données.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
from typing import Any, Optional

import httpx

from models import (
    DeploymentDetail,
    DeploymentSummary,
    JobDetail,
    StageDetail,
    StepDetail,
    TimelineResponse,
)


class AzureDevOpsClientError(Exception):
    """Erreur levée lors d'un appel à l'API Azure DevOps."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AzureDevOpsClient:
    """Client HTTP pour l'API Azure DevOps REST."""

    API_VERSION = "7.1"

    def __init__(self) -> None:
        self.org = os.environ.get("AZDO_ORG", "")
        self.project = os.environ.get("AZDO_PROJECT", "")
        self.pat = os.environ.get("AZDO_PAT", "")

        if not all([self.org, self.project, self.pat]):
            raise AzureDevOpsClientError(
                "Variables d'environnement manquantes : AZDO_ORG, AZDO_PROJECT, AZDO_PAT"
            )

        self.base_url = (
            f"https://dev.azure.com/{self.org}/{self.project}/_apis"
        )

        token_b64 = base64.b64encode(f":{self.pat}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token_b64}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    #  HTTP helpers
    # ------------------------------------------------------------------ #

    async def _get(self, url: str, params: dict | None = None) -> Any:
        """Effectue un GET authentifié vers Azure DevOps (JSON)."""
        params = params or {}
        params["api-version"] = self.API_VERSION
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, headers=self.headers, params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                raise AzureDevOpsClientError(
                    f"Azure DevOps API error: {exc.response.status_code} — {exc.response.text}",
                    status_code=exc.response.status_code,
                ) from exc
            except httpx.RequestError as exc:
                raise AzureDevOpsClientError(
                    f"Erreur réseau lors de l'appel Azure DevOps : {exc}"
                ) from exc

    async def _get_text(self, url: str, params: dict | None = None) -> str:
        """Effectue un GET authentifié et retourne du texte brut (logs)."""
        params = params or {}
        params["api-version"] = self.API_VERSION
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, headers=self.headers, params=params)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as exc:
                raise AzureDevOpsClientError(
                    f"Azure DevOps API error: {exc.response.status_code} — {exc.response.text}",
                    status_code=exc.response.status_code,
                ) from exc
            except httpx.RequestError as exc:
                raise AzureDevOpsClientError(
                    f"Erreur réseau lors de l'appel Azure DevOps : {exc}"
                ) from exc

    # ------------------------------------------------------------------ #
    #  Builds (= déploiements)
    # ------------------------------------------------------------------ #

    async def list_builds(
        self,
        top: int = 50,
        branch: Optional[str] = None,
        status: Optional[str] = None,
        definition_id: Optional[int] = None,
    ) -> list[DeploymentSummary]:
        """Récupère la liste des builds Azure DevOps et les transforme."""
        url = f"{self.base_url}/build/builds"
        params: dict[str, Any] = {"$top": top}
        if branch:
            params["branchName"] = branch
        if status:
            params["statusFilter"] = status
        if definition_id:
            params["definitions"] = str(definition_id)

        data = await self._get(url, params)
        builds = data.get("value", [])
        return [self._map_build_summary(b) for b in builds]

    async def get_build(self, build_id: int) -> DeploymentDetail:
        """Récupère le détail d'un build spécifique."""
        url = f"{self.base_url}/build/builds/{build_id}"
        data = await self._get(url)
        timeline = await self.get_timeline(build_id)
        detail = self._map_build_detail(data)
        detail.stages = timeline.stages
        return detail

    async def get_timeline(self, build_id: int) -> TimelineResponse:
        """Récupère et structure la timeline d'un build."""
        url = f"{self.base_url}/build/builds/{build_id}/timeline"
        data = await self._get(url)
        records = data.get("records", [])
        stages = self._build_hierarchy(records)
        return TimelineResponse(build_id=build_id, stages=stages)

    async def get_build_log(self, build_id: int, log_id: int) -> str:
        """Récupère le contenu texte d'un log de build."""
        url = f"{self.base_url}/build/builds/{build_id}/logs/{log_id}"
        return await self._get_text(url)

    # ------------------------------------------------------------------ #
    #  Mapping helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_iso(ts: str) -> datetime:
        """Parse un timestamp ISO Azure DevOps (gère les décimales variables)."""
        import re
        # Azure DevOps renvoie un nombre variable de décimales (2, 7, etc.)
        # Python 3.9 fromisoformat ne supporte que 0, 3 ou 6 décimales.
        # → normaliser à exactement 6 décimales.
        def _normalize_frac(m: re.Match) -> str:
            frac = m.group(1)  # partie fractionnaire sans le "."
            return "." + frac[:6].ljust(6, "0")

        ts = ts.replace("Z", "+00:00")
        ts = re.sub(r"\.(\d+)", _normalize_frac, ts)
        return datetime.fromisoformat(ts)

    @staticmethod
    def _compute_duration(start: Optional[str], finish: Optional[str]) -> Optional[float]:
        """Calcule la durée en secondes entre deux timestamps ISO."""
        if not start or not finish:
            return None
        try:
            dt_start = AzureDevOpsClient._parse_iso(start)
            dt_finish = AzureDevOpsClient._parse_iso(finish)
            return round((dt_finish - dt_start).total_seconds(), 2)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _normalize_status(record: dict) -> str:
        """Retourne un statut normalisé à partir du record Azure DevOps."""
        result = record.get("result")
        state = record.get("state")
        if result:
            return result  # succeeded, failed, canceled, …
        if state == "inProgress":
            return "inProgress"
        if state == "pending":
            return "pending"
        return state or "unknown"

    def _map_build_summary(self, build: dict) -> DeploymentSummary:
        start = build.get("startTime")
        finish = build.get("finishTime")
        return DeploymentSummary(
            id=build["id"],
            pipeline_name=build.get("definition", {}).get("name", "—"),
            status=build.get("status", "unknown"),
            result=build.get("result"),
            branch=build.get("sourceBranch", "").replace("refs/heads/", ""),
            start_time=start,
            finish_time=finish,
            duration=self._compute_duration(start, finish),
            triggered_by=build.get("requestedFor", {}).get("displayName"),
        )

    def _map_build_detail(self, build: dict) -> DeploymentDetail:
        start = build.get("startTime")
        finish = build.get("finishTime")
        return DeploymentDetail(
            id=build["id"],
            pipeline_name=build.get("definition", {}).get("name", "—"),
            status=build.get("status", "unknown"),
            result=build.get("result"),
            branch=build.get("sourceBranch", "").replace("refs/heads/", ""),
            start_time=start,
            finish_time=finish,
            duration=self._compute_duration(start, finish),
            triggered_by=build.get("requestedFor", {}).get("displayName"),
            source_version=build.get("sourceVersion"),
        )

    def _build_hierarchy(self, records: list[dict]) -> list[StageDetail]:
        """
        Construit la hiérarchie Stage → Job → Step à partir des records
        de la timeline Azure DevOps.

        Azure DevOps renvoie : Stage → Phase → Job → Task
        On fusionne Phase+Job en un seul niveau « Job » pour simplifier.
        """
        # Index par id
        by_id: dict[str, dict] = {r["id"]: r for r in records}

        # Séparer selon le type
        stages_raw: list[dict] = []
        phases_raw: list[dict] = []
        jobs_raw: list[dict] = []
        steps_raw: list[dict] = []

        for r in records:
            rtype = (r.get("type") or "").lower()
            if rtype == "stage":
                stages_raw.append(r)
            elif rtype == "phase":
                phases_raw.append(r)
            elif rtype == "job":
                jobs_raw.append(r)
            elif rtype == "task":
                steps_raw.append(r)

        # Mapper phase_id → stage_id  (Phase est enfant d'un Stage)
        phase_to_stage: dict[str, str] = {}
        for p in phases_raw:
            pid = p.get("parentId")
            if pid:
                phase_to_stage[p["id"]] = pid

        # Construire les steps (enfants des Jobs)
        steps_by_parent: dict[str, list[StepDetail]] = {}
        for s in steps_raw:
            parent_id = s.get("parentId")
            if not parent_id:
                continue
            step = StepDetail(
                name=s.get("name", "Step"),
                status=self._normalize_status(s),
                order=s.get("order"),
                start_time=s.get("startTime"),
                finish_time=s.get("finishTime"),
                duration=self._compute_duration(s.get("startTime"), s.get("finishTime")),
                error_message=self._extract_error(s),
                log_url=s.get("log", {}).get("url") if isinstance(s.get("log"), dict) else None,
            )
            steps_by_parent.setdefault(parent_id, []).append(step)

        # Trier les steps par order
        for parent_id in steps_by_parent:
            steps_by_parent[parent_id].sort(key=lambda x: x.order or 0)

        # Construire les jobs (enfants des Phases)
        # On rattache chaque job au stage via la phase parente.
        jobs_by_stage: dict[str, list[JobDetail]] = {}
        for j in jobs_raw:
            phase_id = j.get("parentId")
            if not phase_id:
                continue
            # Remonter au stage via la phase
            stage_id = phase_to_stage.get(phase_id, phase_id)
            job = JobDetail(
                name=j.get("name", "Job"),
                status=self._normalize_status(j),
                start_time=j.get("startTime"),
                finish_time=j.get("finishTime"),
                duration=self._compute_duration(j.get("startTime"), j.get("finishTime")),
                error_message=self._extract_error(j),
                steps=steps_by_parent.get(j["id"], []),
            )
            jobs_by_stage.setdefault(stage_id, []).append(job)

        # Fallback : si pas de phases, les jobs sont directement enfants de stages
        if not phases_raw:
            for j in jobs_raw:
                parent_id = j.get("parentId")
                if not parent_id or parent_id in jobs_by_stage:
                    continue
                job = JobDetail(
                    name=j.get("name", "Job"),
                    status=self._normalize_status(j),
                    start_time=j.get("startTime"),
                    finish_time=j.get("finishTime"),
                    duration=self._compute_duration(j.get("startTime"), j.get("finishTime")),
                    error_message=self._extract_error(j),
                    steps=steps_by_parent.get(j["id"], []),
                )
                jobs_by_stage.setdefault(parent_id, []).append(job)

        # Construire les stages
        stages: list[StageDetail] = []
        for st in stages_raw:
            stage = StageDetail(
                name=st.get("name", "Stage"),
                status=self._normalize_status(st),
                start_time=st.get("startTime"),
                finish_time=st.get("finishTime"),
                duration=self._compute_duration(st.get("startTime"), st.get("finishTime")),
                error_message=self._extract_error(st),
                jobs=jobs_by_stage.get(st["id"], []),
            )
            stages.append(stage)

        # Si aucune stage n'est trouvée (pipeline classique sans stages),
        # on crée un stage virtuel contenant tous les jobs/steps
        if not stages and (jobs_raw or steps_raw):
            orphan_jobs: list[JobDetail] = []
            for j in jobs_raw:
                job = JobDetail(
                    name=j.get("name", "Job"),
                    status=self._normalize_status(j),
                    start_time=j.get("startTime"),
                    finish_time=j.get("finishTime"),
                    duration=self._compute_duration(j.get("startTime"), j.get("finishTime")),
                    error_message=self._extract_error(j),
                    steps=steps_by_parent.get(j["id"], []),
                )
                orphan_jobs.append(job)

            stages.append(
                StageDetail(
                    name="Pipeline",
                    status="completed",
                    jobs=orphan_jobs,
                )
            )

        return stages

    @staticmethod
    def _extract_error(record: dict) -> Optional[str]:
        """Extrait le message d'erreur d'un record timeline."""
        issues = record.get("issues", [])
        if issues:
            errors = [
                i.get("message", "")
                for i in issues
                if i.get("type", "").lower() == "error"
            ]
            if errors:
                return " | ".join(errors)
        # Fallback : result == failed sans issues
        if record.get("result") == "failed":
            return record.get("name", "Étape en échec")
        return None
