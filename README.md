# 🚀 DeployX — Azure DevOps Deployment Tracker

Application complète pour **visualiser et suivre les déploiements Azure DevOps** avec une interface user-friendly.

## Architecture

```
Appian (embed iframe)
       ↓
Streamlit (frontend UI)   ← port 8501
       ↓
FastAPI (backend API)     ← port 8000
       ↓
Azure DevOps REST API
```

---

## Prérequis

- **Python 3.11+**
- Un **Personal Access Token (PAT)** Azure DevOps avec le scope `Build → Read`
- Accès réseau vers `https://dev.azure.com`

---

## Installation

```bash
# 1. Cloner / accéder au projet
cd DeployX

# 2. Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
cp .env.example .env
```

Ouvrez `.env` et remplissez vos valeurs :

```env
AZDO_ORG=votre-organisation
AZDO_PROJECT=votre-projet
AZDO_PAT=votre-personal-access-token
DEPLOYX_BACKEND_URL=http://localhost:8000
```

### Générer un PAT Azure DevOps

1. Allez sur `https://dev.azure.com/{votre-org}/_usersSettings/tokens`
2. Cliquez sur **New Token**
3. Scope : **Build → Read**
4. Copiez le token généré dans `AZDO_PAT`

---

## Lancement

### 1. Démarrer le backend FastAPI

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Vérifiez : [http://localhost:8000/health](http://localhost:8000/health) → `{"status": "ok"}`

Documentation API interactive : [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Démarrer le frontend Streamlit

Dans un **second terminal** :

```bash
cd frontend
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

Accédez à : [http://localhost:8501](http://localhost:8501)

---

## Endpoints API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/deployments` | Liste des déploiements |
| `GET` | `/deployments/{id}` | Détail d'un déploiement (avec hiérarchie) |
| `GET` | `/deployments/{id}/timeline` | Timeline structurée (Stage → Job → Step) |

### Paramètres de `/deployments`

| Paramètre | Type | Description |
|-----------|------|-------------|
| `top` | int | Nombre max de résultats (1-200, défaut: 50) |
| `branch` | string | Filtrer par branche |
| `status` | string | Filtrer par statut (`inProgress`, `completed`, …) |
| `definition_id` | int | Filtrer par pipeline ID |

---

## Structure du projet

```
DeployX/
├── backend/
│   ├── __init__.py
│   ├── main.py                  # FastAPI — endpoints
│   ├── azure_devops_client.py   # Client Azure DevOps REST API
│   └── models.py                # Modèles Pydantic
├── frontend/
│   └── streamlit_app.py         # Interface utilisateur Streamlit
├── .env.example                 # Template de configuration
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Intégration Appian (iframe)

### Configuration Streamlit pour iframe

Créez un fichier `.streamlit/config.toml` dans le dossier `frontend/` :

```toml
[server]
enableXsrfProtection = false
enableCORS = false

[browser]
gatherUsageStats = false
```

### Exemple HTML embed pour Appian

```html
<iframe
  src="http://votre-serveur:8501"
  width="100%"
  height="800px"
  frameborder="0"
  style="border: none; border-radius: 8px;"
  allow="clipboard-read; clipboard-write"
></iframe>
```

### Contraintes d'intégration

| Contrainte | Solution |
|------------|----------|
| **X-Frame-Options** | Streamlit n'envoie pas ce header par défaut → OK pour iframe |
| **CORS** | Le backend FastAPI autorise toutes les origines (à restreindre en prod) |
| **HTTPS** | En production, utilisez un reverse proxy (nginx) avec certificat SSL |
| **Auth** | Le PAT reste côté backend, jamais exposé au frontend. L'accès à Streamlit peut être sécurisé via Streamlit Auth ou un reverse proxy |

### Recommandations production

- Placez un **reverse proxy nginx** devant Streamlit et FastAPI
- Activez **HTTPS** (Let's Encrypt / certificat interne)
- Restreignez **CORS** aux domaines Appian autorisés
- Ajoutez une **authentification** sur le frontend si nécessaire
- Utilisez **Docker** pour déployer les deux services

---

## Fonctionnalités

### Page 1 — Liste des déploiements
- Affichage de tous les pipelines avec statut, branche, durée, déclencheur
- Filtres : branche, statut, nombre de résultats
- Tri par date, pipeline ou statut
- Sélection d'un run pour afficher le détail

### Page 2 — Détail d'un déploiement
- Header : pipeline, run ID, statut, durée, branche, déclencheur, commit
- Hiérarchie visuelle repliable : **Stage → Job → Step**
- Code couleur : ✅ vert (succès), ❌ rouge (échec), 🔄 orange (en cours), ⏳ bleu (en attente)
- Affichage des messages d'erreur
- Affichage des durées par étape
- **Rafraîchissement automatique** toutes les 5 secondes si le déploiement est en cours

---

## Sécurité

- ❌ Aucun appel direct à Azure DevOps depuis Streamlit
- ❌ Le PAT n'est jamais exposé côté frontend
- ✅ Le backend joue le rôle de **façade sécurisée**
- ✅ Configuration par **variables d'environnement**
- ✅ Le `.env` est ignoré par git (`.gitignore`)

---

## Licence

Projet interne — usage libre.
