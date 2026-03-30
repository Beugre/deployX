"""
DeployX — Frontend Streamlit.
Interface utilisateur pour visualiser et suivre les déploiements Azure DevOps.
Communique exclusivement avec le backend FastAPI (jamais directement avec Azure DevOps).
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Optional

import requests
import streamlit as st

# ------------------------------------------------------------------ #
#  Configuration
# ------------------------------------------------------------------ #

BACKEND_URL = os.environ.get("DEPLOYX_BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="DeployX — Azure DevOps Tracker",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------ #
#  Styles CSS personnalisés
# ------------------------------------------------------------------ #

st.markdown(
    """
    <style>
    .status-succeeded { color: #22c55e; font-weight: 700; }
    .status-failed { color: #ef4444; font-weight: 700; }
    .status-inprogress { color: #f97316; font-weight: 700; }
    .status-canceled { color: #6b7280; font-weight: 700; }
    .status-pending { color: #3b82f6; font-weight: 700; }
    .status-unknown { color: #9ca3af; font-weight: 700; }

    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.82em;
        font-weight: 600;
        color: white;
    }
    .badge-succeeded { background: #22c55e; }
    .badge-failed { background: #ef4444; }
    .badge-inprogress { background: #f97316; }
    .badge-canceled { background: #6b7280; }
    .badge-pending { background: #3b82f6; }
    .badge-unknown { background: #9ca3af; }
    .badge-partiallysucceeded { background: #eab308; }

    .job-block {
        border-left: 3px solid #8b5cf6;
        padding: 8px 12px;
        margin: 6px 0 6px 4px;
        background: #f5f3ff;
        border-radius: 5px;
    }
    .step-row {
        padding: 5px 10px;
        margin: 2px 0 2px 8px;
        border-radius: 4px;
        font-size: 0.92em;
    }
    .step-succeeded { background: #f0fdf4; border-left: 3px solid #22c55e; }
    .step-failed { background: #fef2f2; border-left: 3px solid #ef4444; }
    .step-inprogress { background: #fff7ed; border-left: 3px solid #f97316; }
    .step-pending { background: #eff6ff; border-left: 3px solid #3b82f6; }
    .step-skipped, .step-canceled { background: #f9fafb; border-left: 3px solid #d1d5db; }

    .error-box {
        background: #fef2f2;
        border: 1px solid #fca5a5;
        border-radius: 6px;
        padding: 10px;
        margin: 6px 0;
        color: #b91c1c;
        font-size: 0.88em;
    }

    .header-title {
        font-size: 1.6em;
        font-weight: 700;
        margin-bottom: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #


def api_get(path: str, params: dict | None = None) -> Any:
    """Appel GET vers le backend FastAPI."""
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Backend indisponible. Vérifiez que le serveur FastAPI est démarré.")
        st.info("💡 Sur Render (plan Free), le backend peut mettre ~30s à se réveiller. Rechargez la page.")
        st.stop()
    except requests.exceptions.Timeout:
        st.warning("⏳ Le backend met du temps à répondre (cold start probable). Rechargez la page dans quelques secondes.")
        st.stop()
    except requests.exceptions.HTTPError as exc:
        code = exc.response.status_code
        # Si la réponse est du HTML (page d'erreur Render), afficher un message propre
        content_type = exc.response.headers.get("content-type", "")
        if "html" in content_type or exc.response.text.strip().startswith("<!"):
            if code == 502:
                st.warning("⏳ Le backend est en cours de démarrage (cold start). Rechargez dans ~30 secondes.")
            else:
                st.error(f"❌ Erreur {code} du backend. Vérifiez que le service est bien déployé.")
        else:
            st.error(f"❌ Erreur API ({code}) : {exc.response.text[:300]}")
        st.stop()


def badge(status: str) -> str:
    s = status.lower().replace(" ", "")
    return f'<span class="badge badge-{s}">{status}</span>'


def status_icon(status: str) -> str:
    mapping = {
        "succeeded": "✅",
        "failed": "❌",
        "inprogress": "🔄",
        "pending": "⏳",
        "canceled": "🚫",
        "partiallysucceeded": "⚠️",
        "skipped": "⏭️",
    }
    return mapping.get(status.lower().replace(" ", ""), "❓")


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


def format_time(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, TypeError):
        return iso_str


def extract_log_id(log_url: Optional[str]) -> Optional[int]:
    """Extrait le log ID numérique depuis l'URL de log Azure DevOps."""
    if not log_url:
        return None
    try:
        # URL format: .../builds/{id}/logs/{logId}
        return int(log_url.rstrip("/").split("/")[-1])
    except (ValueError, IndexError):
        return None


# ------------------------------------------------------------------ #
#  Navigation pilotée par session_state
# ------------------------------------------------------------------ #

# Initialiser l'état de navigation
if "nav" not in st.session_state:
    st.session_state["nav"] = "list"
if "selected_build_id" not in st.session_state:
    st.session_state["selected_build_id"] = None

NAV_LIST = "📋 Liste des déploiements"
NAV_DETAIL = "🔍 Détail d'un déploiement"
NAV_OPTIONS = [NAV_LIST, NAV_DETAIL]

# Forcer la valeur du widget radio AVANT son rendu
# Quand on change session_state["nav"], on synchronise la clé du widget
if st.session_state["nav"] == "detail":
    st.session_state["nav_radio"] = NAV_DETAIL
else:
    st.session_state["nav_radio"] = NAV_LIST

st.sidebar.markdown("## 🚀 DeployX")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    NAV_OPTIONS,
    label_visibility="collapsed",
    key="nav_radio",
)

# Synchroniser le retour : si l'utilisateur clique manuellement sur le radio
if page == NAV_LIST:
    st.session_state["nav"] = "list"
else:
    st.session_state["nav"] = "detail"

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<small style='color: #9ca3af;'>DeployX v1.0 — Azure DevOps Tracker</small>",
    unsafe_allow_html=True,
)


# ================================================================== #
#  PAGE 1 — Liste des déploiements
# ================================================================== #

if st.session_state["nav"] == "list":
    st.markdown('<p class="header-title">📋 Déploiements Azure DevOps</p>', unsafe_allow_html=True)
    st.markdown("")

    # Filtres
    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 1])
    with col_f1:
        filter_branch = st.text_input("🌿 Branche", placeholder="main")
    with col_f2:
        filter_status = st.selectbox(
            "📊 Statut",
            ["Tous", "inProgress", "completed", "cancelling", "notStarted"],
        )
    with col_f3:
        filter_top = st.slider("📦 Nombre max", 10, 200, 50)
    with col_f4:
        st.markdown("")
        st.markdown("")
        st.button("🔄 Rafraîchir")

    # Paramètres API
    params: dict[str, Any] = {"top": filter_top}
    if filter_branch:
        params["branch"] = (
            f"refs/heads/{filter_branch}"
            if not filter_branch.startswith("refs/")
            else filter_branch
        )
    if filter_status != "Tous":
        params["status"] = filter_status

    deployments = api_get("/deployments", params)

    if not deployments:
        st.info("Aucun déploiement trouvé.")
        st.stop()

    st.markdown(f"**{len(deployments)}** déploiement(s) trouvé(s)")

    # Tri
    sort_col = st.selectbox(
        "Trier par",
        ["Date (récent)", "Date (ancien)", "Pipeline", "Statut"],
        label_visibility="collapsed",
    )
    if sort_col == "Date (récent)":
        deployments.sort(key=lambda d: d.get("start_time") or "", reverse=True)
    elif sort_col == "Date (ancien)":
        deployments.sort(key=lambda d: d.get("start_time") or "")
    elif sort_col == "Pipeline":
        deployments.sort(key=lambda d: d.get("pipeline_name", "").lower())
    elif sort_col == "Statut":
        deployments.sort(key=lambda d: d.get("status", ""))

    # Affichage
    for dep in deployments:
        dep_id = dep["id"]
        dep_status = dep.get("result") or dep.get("status", "unknown")
        icon = status_icon(dep_status)

        col1, col2, col3, col4, col5 = st.columns([0.5, 3, 2, 2, 1.5])
        with col1:
            st.markdown(f"### {icon}")
        with col2:
            st.markdown(f"**{dep['pipeline_name']}**")
            st.caption(f"Run #{dep_id} • `{dep.get('branch', '—')}`")
        with col3:
            st.markdown(f"{badge(dep_status)}", unsafe_allow_html=True)
            st.caption(f"👤 {dep.get('triggered_by', '—')}")
        with col4:
            st.caption(f"🕐 {format_time(dep.get('start_time'))}")
            st.caption(f"⏱️ {format_duration(dep.get('duration'))}")
        with col5:
            if st.button("Ouvrir ▶", key=f"open_{dep_id}"):
                st.session_state["selected_build_id"] = dep_id
                st.session_state["nav"] = "detail"
                st.rerun()

        st.divider()


# ================================================================== #
#  PAGE 2 — Détail d'un déploiement
# ================================================================== #

else:
    st.markdown('<p class="header-title">🔍 Détail du déploiement</p>', unsafe_allow_html=True)
    st.markdown("")

    # --- Bouton retour ---
    if st.button("⬅️ Retour à la liste"):
        st.session_state["nav"] = "list"
        st.rerun()

    # Sélection du build ID
    default_id = st.session_state.get("selected_build_id", "")
    build_id_input = st.text_input(
        "🔢 Build ID",
        value=str(default_id) if default_id else "",
        placeholder="Ex : 12345",
    )

    if not build_id_input:
        st.info("Saisissez un Build ID ou sélectionnez un déploiement depuis la liste.")
        st.stop()

    try:
        build_id = int(build_id_input)
    except ValueError:
        st.error("L'identifiant doit être un nombre entier.")
        st.stop()

    # Chargement
    detail = api_get(f"/deployments/{build_id}")
    if not detail:
        st.error("Déploiement introuvable.")
        st.stop()

    dep_status = detail.get("result") or detail.get("status", "unknown")
    is_in_progress = detail.get("status", "").lower() == "inprogress"

    # Header
    st.markdown("---")
    h1, h2, h3, h4 = st.columns(4)
    with h1:
        st.metric("Pipeline", detail["pipeline_name"])
    with h2:
        st.metric("Run ID", f"#{detail['id']}")
    with h3:
        st.markdown(f"**Statut** : {badge(dep_status)}", unsafe_allow_html=True)
    with h4:
        st.metric("Durée", format_duration(detail.get("duration")))

    info1, info2, info3 = st.columns(3)
    with info1:
        st.caption(f"🌿 Branche : `{detail.get('branch', '—')}`")
    with info2:
        st.caption(f"👤 Déclenché par : {detail.get('triggered_by', '—')}")
    with info3:
        st.caption(f"🕐 Début : {format_time(detail.get('start_time'))}")

    if detail.get("source_version"):
        st.caption(f"📝 Commit : `{detail['source_version'][:8]}`")

    st.markdown("---")

    # ---------------------------------------------------------- #
    #  Hiérarchie Stage → Job → Step
    # ---------------------------------------------------------- #

    stages = detail.get("stages", [])

    if not stages:
        st.warning("Aucune donnée de timeline disponible pour ce déploiement.")
    else:
        st.markdown("### 🏗️ Pipeline — Exécution détaillée")
        st.markdown("")

        for s_idx, stage in enumerate(stages):
            stage_status = stage.get("status", "unknown")
            stage_icon = status_icon(stage_status)
            stage_duration = format_duration(stage.get("duration"))

            with st.expander(
                f"{stage_icon}  Stage : {stage['name']}  —  {stage_status}  ({stage_duration})",
                expanded=(stage_status in ("failed", "inProgress")),
            ):
                # Erreur au niveau stage
                if stage.get("error_message"):
                    st.markdown(
                        f'<div class="error-box">💥 {stage["error_message"]}</div>',
                        unsafe_allow_html=True,
                    )

                jobs = stage.get("jobs", [])
                if not jobs:
                    st.caption("Aucun job dans ce stage.")

                for j_idx, job in enumerate(jobs):
                    job_status = job.get("status", "unknown")
                    job_icon = status_icon(job_status)
                    job_duration = format_duration(job.get("duration"))

                    # En-tête du job
                    st.markdown(
                        f"""<div class="job-block">
                            <strong>{job_icon} Job : {job['name']}</strong>
                            &nbsp; {badge(job_status)} &nbsp;
                            <span style="color:#6b7280;">⏱️ {job_duration}</span>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                    if job.get("error_message"):
                        st.markdown(
                            f'<div class="error-box">💥 {job["error_message"]}</div>',
                            unsafe_allow_html=True,
                        )

                    # Steps — chaque step est un expander cliquable
                    steps = job.get("steps", [])
                    if not steps:
                        st.caption("    Aucune étape détaillée.")
                        continue

                    for st_idx, step in enumerate(steps):
                        step_status = step.get("status", "unknown")
                        step_icn = status_icon(step_status)
                        step_duration = format_duration(step.get("duration"))
                        step_name = step.get("name", "Step")
                        step_label = f"{step_icn}  {step_name}  —  {step_duration}"

                        # Utiliser un expander pour chaque step
                        with st.expander(step_label, expanded=(step_status == "failed")):
                            # Infos de la step
                            sc1, sc2, sc3 = st.columns(3)
                            with sc1:
                                st.markdown(f"**Statut** : {badge(step_status)}", unsafe_allow_html=True)
                            with sc2:
                                st.caption(f"🕐 Début : {format_time(step.get('start_time'))}")
                            with sc3:
                                st.caption(f"🏁 Fin : {format_time(step.get('finish_time'))}")

                            # Erreur
                            if step.get("error_message"):
                                st.error(f"💥 {step['error_message']}")

                            # Log : bouton pour charger le contenu
                            log_url = step.get("log_url")
                            log_id = extract_log_id(log_url)
                            if log_id is not None:
                                log_key = f"log_{build_id}_{s_idx}_{j_idx}_{st_idx}"
                                if st.button(f"📄 Voir le log", key=log_key):
                                    with st.spinner("Chargement du log…"):
                                        log_data = api_get(
                                            f"/deployments/{build_id}/logs/{log_id}"
                                        )
                                        if log_data and log_data.get("content"):
                                            st.code(
                                                log_data["content"],
                                                language="text",
                                            )
                                        else:
                                            st.info("Log vide ou indisponible.")
                            else:
                                st.caption("Pas de log disponible pour cette étape.")

    # ---------------------------------------------------------- #
    #  Auto-refresh si en cours
    # ---------------------------------------------------------- #

    if is_in_progress:
        st.markdown("---")
        st.info("🔄 Déploiement en cours — rafraîchissement automatique dans 5 secondes…")
        time.sleep(5)
        st.rerun()
