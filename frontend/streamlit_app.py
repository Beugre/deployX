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
#  Warm-up automatique du backend
# ------------------------------------------------------------------ #


def wake_up_backend(max_retries: int = 30, interval: float = 5.0) -> bool:
    """Ping le backend jusqu'à ce qu'il réponde (max ~2min30)."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(f"{BACKEND_URL}/health", timeout=10)
            if resp.status_code == 200:
                return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            pass
        time.sleep(interval)
    return False


# Au chargement, vérifier si le backend est prêt
if "backend_ready" not in st.session_state:
    st.session_state["backend_ready"] = False

if not st.session_state["backend_ready"]:
    # Test rapide
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=3)
        if r.status_code == 200:
            st.session_state["backend_ready"] = True
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pass

    if not st.session_state["backend_ready"]:
        placeholder = st.empty()
        placeholder.info(
            "⏳ **Réveil du backend en cours…**\n\n"
            "Le plan gratuit Render met le serveur en veille après 15 min d'inactivité. "
            "Le redémarrage prend généralement **30 à 90 secondes**. "
            "Merci de patienter, cette page se mettra à jour automatiquement."
        )

        progress = st.progress(0, text="Connexion au backend…")
        error_display = st.empty()
        start_ts = time.time()
        attempt = 0
        # Boucle sans limite — on attend tant que le backend n'est pas prêt
        # Timeout long (120s) pour laisser Render démarrer le container,
        # au lieu de plein de petits timeouts qui expirent trop tôt.
        while True:
            attempt += 1
            elapsed = int(time.time() - start_ts)
            minutes = elapsed // 60
            seconds = elapsed % 60
            pct = min(int((elapsed / 180) * 100), 99)
            progress.progress(pct, text=f"⏳ Tentative {attempt} — {minutes}m {seconds:02d}s écoulées…")
            try:
                resp = requests.get(f"{BACKEND_URL}/health", timeout=120)
                if resp.status_code == 200:
                    st.session_state["backend_ready"] = True
                    progress.progress(100, text="✅ Backend prêt !")
                    time.sleep(0.5)
                    placeholder.empty()
                    progress.empty()
                    error_display.empty()
                    st.rerun()
                else:
                    error_display.caption(f"⚠️ Réponse HTTP {resp.status_code} — le backend démarre…")
                    time.sleep(5)
            except requests.exceptions.ConnectionError as e:
                error_display.caption(f"🔌 ConnectionError : {str(e)[:200]}")
                time.sleep(5)
            except requests.exceptions.Timeout:
                error_display.caption("⏱️ Timeout 120s — le backend n'a pas répondu")
                time.sleep(2)

            elapsed = int(time.time() - start_ts)
            minutes = elapsed // 60
            seconds = elapsed % 60
            # Barre de progression sur 5 min (300s) — reste à 99% si ça dépasse
            pct = min(int((elapsed / 300) * 100), 99)
            progress.progress(pct, text=f"⏳ Tentative {attempt} — {minutes}m {seconds:02d}s écoulées…")
            time.sleep(5)


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


def api_post(path: str, params: dict | None = None) -> Any:
    """Appel POST vers le backend FastAPI."""
    try:
        resp = requests.post(f"{BACKEND_URL}{path}", params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as exc:
        st.error(f"❌ Erreur API ({exc.response.status_code}) : {exc.response.text[:300]}")
        return None
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        st.error("❌ Backend indisponible.")
        return None


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
if "selected_pipeline_id" not in st.session_state:
    st.session_state["selected_pipeline_id"] = None

NAV_LIST = "📋 Liste des déploiements"
NAV_DETAIL = "🔍 Détail d'un déploiement"
NAV_RUN = "▶️ Lancer une pipeline"
NAV_HISTORY = "📊 Historique pipeline"
NAV_OPTIONS = [NAV_LIST, NAV_DETAIL, NAV_RUN, NAV_HISTORY]

NAV_MAP = {"list": NAV_LIST, "detail": NAV_DETAIL, "run": NAV_RUN, "history": NAV_HISTORY}
NAV_REVERSE = {v: k for k, v in NAV_MAP.items()}


def _on_nav_change():
    """Callback quand l'utilisateur clique sur le radio."""
    st.session_state["nav"] = NAV_REVERSE.get(st.session_state["nav_radio"], "list")


# Forcer la valeur du widget radio AVANT son rendu
# Uniquement si le changement vient du code (bouton "Ouvrir", etc.)
# et pas du radio lui-même (sinon on crée une boucle)
if "_nav_from_code" in st.session_state and st.session_state["_nav_from_code"]:
    st.session_state["nav_radio"] = NAV_MAP.get(st.session_state["nav"], NAV_LIST)
    st.session_state["_nav_from_code"] = False

st.sidebar.markdown("## 🚀 DeployX")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    NAV_OPTIONS,
    label_visibility="collapsed",
    key="nav_radio",
    on_change=_on_nav_change,
)

# Synchroniser : si c'est le premier chargement ou un clic radio
st.session_state["nav"] = NAV_REVERSE.get(page, "list")

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<small style='color: #9ca3af;'>DeployX v2.0 — Azure DevOps Tracker</small>",
    unsafe_allow_html=True,
)


# ================================================================== #
#  PAGE 1 — Liste des déploiements
# ================================================================== #

if st.session_state["nav"] == "list":
    st.markdown('<p class="header-title">📋 Déploiements Azure DevOps</p>', unsafe_allow_html=True)
    st.markdown("")

    # Filtres
    # Mapping filtre → paramètres API Azure DevOps
    FILTER_OPTIONS = {
        "Tous":                   {"status": None, "result": None},
        "✅ Réussi":              {"status": "completed", "result": "succeeded"},
        "❌ Échoué":              {"status": "completed", "result": "failed"},
        "🔄 En cours":            {"status": "inProgress", "result": None},
        "🚫 Annulé":              {"status": "completed", "result": "canceled"},
        "⚠️ Partiellement réussi": {"status": "completed", "result": "partiallySucceeded"},
    }

    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns([2, 2, 2, 1.5, 1])
    with col_f1:
        filter_branch = st.text_input("🌿 Branche", placeholder="main")
    with col_f2:
        filter_status = st.selectbox(
            "📊 Statut",
            list(FILTER_OPTIONS.keys()),
        )
    with col_f3:
        filter_pipeline = st.text_input("🔧 Pipeline", placeholder="Nom de la pipeline")
    with col_f4:
        filter_top = st.slider("📦 Nombre max", 10, 200, 50)
    with col_f5:
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
    selected_filter = FILTER_OPTIONS[filter_status]
    if selected_filter["status"]:
        params["status"] = selected_filter["status"]
    if selected_filter["result"]:
        params["result"] = selected_filter["result"]

    deployments = api_get("/deployments", params)

    # Filtre côté client sur le nom de pipeline
    if filter_pipeline:
        search_term = filter_pipeline.lower()
        deployments = [
            d for d in deployments
            if search_term in d.get("pipeline_name", "").lower()
        ]

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
                st.session_state["_nav_from_code"] = True
                st.rerun()

        st.divider()

    # Auto-refresh si des builds sont en cours
    has_in_progress = any(
        d.get("status", "").lower() == "inprogress" for d in deployments
    )
    if has_in_progress:
        st.info("🔄 Build(s) en cours — rafraîchissement automatique dans 10 secondes…")
        time.sleep(10)
        st.rerun()


# ================================================================== #
#  PAGE 2 — Détail d'un déploiement
# ================================================================== #

elif st.session_state["nav"] == "detail":
    st.markdown('<p class="header-title">🔍 Détail du déploiement</p>', unsafe_allow_html=True)
    st.markdown("")

    # --- Bouton retour ---
    if st.button("⬅️ Retour à la liste"):
        st.session_state["nav"] = "list"
        st.session_state["_nav_from_code"] = True
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

    # Actions : Re-run / Annuler (avec confirmation)
    act1, act2, act3 = st.columns([1, 1, 4])
    with act1:
        with st.popover("🔁 Re-run"):
            st.markdown(f"**Relancer le build #{build_id}** sur la branche `{detail.get('branch', '—')}` ?")
            if st.button("✅ Confirmer le re-run", key="confirm_rerun"):
                def_id = detail.get("definition_id")
                if def_id:
                    with st.spinner("Lancement…"):
                        result = api_post(
                            f"/pipelines/{def_id}/run",
                            params={"branch": detail.get("branch")},
                        )
                        if result and result.get("id"):
                            st.success(f"✅ Build #{result['id']} lancé !")
                            time.sleep(1)
                            st.session_state["selected_build_id"] = result["id"]
                            st.rerun()
                else:
                    st.warning("Definition ID non disponible pour ce build.")
    with act2:
        if is_in_progress:
            with st.popover("🛑 Annuler"):
                st.markdown(f"⚠️ **Annuler le build #{build_id}** en cours ?")
                if st.button("❌ Confirmer l'annulation", key="confirm_cancel"):
                    with st.spinner("Annulation…"):
                        result = api_post(f"/deployments/{build_id}/cancel")
                        if result:
                            st.warning(f"🚫 Build #{build_id} annulé.")
                            time.sleep(1)
                            st.rerun()
    with act3:
        # Lien vers l'historique de la pipeline
        def_id = detail.get("definition_id")
        if def_id:
            if st.button("📊 Historique pipeline", key="history_link"):
                st.session_state["selected_pipeline_id"] = def_id
                st.session_state["nav"] = "history"
                st.session_state["_nav_from_code"] = True
                st.rerun()

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


# ================================================================== #
#  PAGE 3 — Lancer une pipeline
# ================================================================== #

elif st.session_state["nav"] == "run":
    st.markdown('<p class="header-title">▶️ Lancer une pipeline</p>', unsafe_allow_html=True)
    st.markdown("")

    # Charger les pipelines disponibles
    pipelines = api_get("/pipelines")
    if not pipelines:
        st.info("Aucune pipeline trouvée.")
        st.stop()

    # Dropdown pour choisir la pipeline
    pipeline_names = {p["name"]: p for p in pipelines}
    selected_name = st.selectbox(
        "🔧 Pipeline à lancer",
        list(pipeline_names.keys()),
    )
    selected_pipeline = pipeline_names[selected_name]

    # Branche
    default_branch = selected_pipeline.get("default_branch", "main")
    branch_input = st.text_input(
        "🌿 Branche",
        value=default_branch,
        placeholder="main",
    )

    # Résumé
    st.markdown("---")
    st.markdown(f"**Pipeline** : {selected_name}")
    st.markdown(f"**Branche** : `{branch_input or default_branch}`")
    st.markdown(f"**Definition ID** : `{selected_pipeline['id']}`")

    # Bouton lancer avec confirmation
    st.markdown("")
    with st.popover("🚀 Lancer le build", use_container_width=True):
        st.markdown(f"**Lancer la pipeline** `{selected_name}` sur la branche `{branch_input or default_branch}` ?")
        if st.button("✅ Confirmer le lancement", key="confirm_launch", type="primary"):
            with st.spinner("Lancement en cours…"):
                result = api_post(
                    f"/pipelines/{selected_pipeline['id']}/run",
                    params={"branch": branch_input or default_branch},
                )
                if result and result.get("id"):
                    st.success(f"✅ Build **#{result['id']}** lancé avec succès !")
                    st.balloons()
                    time.sleep(2)
                    st.session_state["selected_build_id"] = result["id"]
                    st.session_state["nav"] = "detail"
                    st.session_state["_nav_from_code"] = True
                    st.rerun()
                elif result:
                    st.error(f"Réponse inattendue : {result}")


# ================================================================== #
#  PAGE 4 — Historique par pipeline
# ================================================================== #

elif st.session_state["nav"] == "history":
    st.markdown('<p class="header-title">📊 Historique par pipeline</p>', unsafe_allow_html=True)
    st.markdown("")

    # Charger les pipelines disponibles
    pipelines = api_get("/pipelines")
    if not pipelines:
        st.info("Aucune pipeline trouvée.")
        st.stop()

    pipeline_names = {p["name"]: p for p in pipelines}

    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        # Si on vient avec un pipeline_id pré-sélectionné
        pre_selected = st.session_state.get("selected_pipeline_id")
        default_idx = 0
        if pre_selected:
            for i, p in enumerate(pipelines):
                if p["id"] == pre_selected:
                    default_idx = i
                    break
        selected_name = st.selectbox(
            "🔧 Pipeline",
            list(pipeline_names.keys()),
            index=default_idx,
        )
    with col_h2:
        history_top = st.slider("📦 Nombre de runs", 10, 100, 30)

    selected_pipeline = pipeline_names[selected_name]
    history = api_get(f"/pipelines/{selected_pipeline['id']}/history", {"top": history_top})

    if not history:
        st.info("Aucun historique pour cette pipeline.")
        st.stop()

    st.markdown(f"**{len(history)}** run(s) pour **{selected_name}**")
    st.markdown("---")

    # Graphique : durée + résultat
    import pandas as pd

    df = pd.DataFrame(history)
    df["display_result"] = df.apply(
        lambda r: r.get("result") or r.get("status", "unknown"), axis=1
    )
    df["duration_min"] = df["duration"].apply(
        lambda d: round(d / 60, 1) if d else 0
    )
    df["date"] = df["start_time"].apply(
        lambda s: s[:10] if s else "?"
    )

    # Barres colorées
    color_map = {
        "succeeded": "#22c55e",
        "failed": "#ef4444",
        "canceled": "#6b7280",
        "partiallySucceeded": "#eab308",
        "inProgress": "#f97316",
        "unknown": "#9ca3af",
    }

    # Résumé stats
    total = len(df)
    succeeded = len(df[df["display_result"] == "succeeded"])
    failed = len(df[df["display_result"] == "failed"])
    success_rate = round((succeeded / total) * 100) if total else 0

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.metric("Total runs", total)
    with s2:
        st.metric("✅ Réussis", succeeded)
    with s3:
        st.metric("❌ Échoués", failed)
    with s4:
        st.metric("📈 Taux de succès", f"{success_rate}%")

    st.markdown("---")

    # Chart avec st.bar_chart n'est pas assez flexible pour les couleurs.
    # Utilisons un tableau coloré
    st.markdown("### 📈 Derniers builds")
    for entry in history:
        e_id = entry["id"]
        e_result = entry.get("result") or entry.get("status", "unknown")
        e_icon = status_icon(e_result)
        e_dur = format_duration(entry.get("duration"))
        e_date = format_time(entry.get("start_time"))
        color = color_map.get(e_result, "#9ca3af")
        dur_pct = min(int((entry.get("duration", 0) or 0) / max(
            max((e.get("duration", 0) or 0) for e in history), 1
        ) * 100), 100)

        c1, c2, c3, c4 = st.columns([0.5, 2, 3, 1])
        with c1:
            st.markdown(f"{e_icon}")
        with c2:
            st.caption(f"#{e_id} — {e_date}")
        with c3:
            st.markdown(
                f'<div style="background:{color};height:20px;border-radius:4px;width:{max(dur_pct, 5)}%;"></div>',
                unsafe_allow_html=True,
            )
        with c4:
            st.caption(e_dur)
            if st.button("▶", key=f"hist_{e_id}"):
                st.session_state["selected_build_id"] = e_id
                st.session_state["nav"] = "detail"
                st.session_state["_nav_from_code"] = True
                st.rerun()
