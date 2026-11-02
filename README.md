# LangExtract PDF — FastAPI + VueDsfr

Extraction d’entités depuis un PDF via un modèle OpenAI-compatible (vLLM, SGLang,
API distante…). Streamlit est remplacé par une API FastAPI et une interface
Vue 3 + TypeScript + VueDsfr, servies sur **le même port**.

## Installation

Prérequis : Python ≥ 3.10, Node.js 24 ≥ 24.15.0 (ou ≥ 26), npm et un endpoint OpenAI-compatible.
`install.sh` installe `uv` si nécessaire et utilise par défaut
`~/venv/<nom-du-projet>` (`VENV_DIR` permet de choisir un autre emplacement).

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
# Reporter le token généré dans API_TOKEN et configurer les trois OPENAI_API_*.
./install.sh
source run.sh 127.0.0.1 8501
```

Si le Node système est trop ancien (par exemple Node 18 sous Ubuntu), construire
avec un Node 24 temporaire sans modifier l’installation système :

```bash
npx --yes --package=node@24 -c './install.sh'
```

Node n’est ensuite pas nécessaire pour servir le frontend déjà construit.
`install.sh` vérifie la version avant toute installation de dépendances.

Ouvrir `http://127.0.0.1:8501`, saisir le token puis déposer un PDF.
`bash run.sh [IP] [PORT]` et `start.sh` fonctionnent aussi ; `upgrade.sh` actualise
les dépendances et reconstruit l’interface. Les fichiers `uv.lock` et
`frontend/package-lock.json` verrouillent les installations ordinaires.
Le lancement ne réinstalle pas les dépendances si l’environnement et le frontend
construit sont présents. Relancer `./install.sh` après une mise à jour du code.

## Configuration

| Variable | Usage | Défaut |
| --- | --- | --- |
| `API_TOKEN` | Secret d’accès à l’API, aléatoire, ≥ 32 caractères | Obligatoire |
| `OPENAI_API_MODEL` | Nom ou alias du modèle | `mistral-small-vllm` |
| `OPENAI_API_BASE` | Endpoint compatible OpenAI | `http://127.0.0.1:8000/v1` |
| `OPENAI_API_KEY` | Clé du fournisseur, distincte du token API | Obligatoire |
| `USE_OPENAI_JSON_MODE` | `1` : JSON ; `0` : sortie modèle YAML | `1` |
| `MAX_UPLOAD_BYTES` | Taille maximale d’un PDF | `20971520` (20 Mio) |
| `MAX_TEXT_CHARS` | Taille maximale du texte avant inférence | `500000` |

Le service refuse de démarrer sans token valide ou clé fournisseur.
`.env` est chargé par Python, sans exécution shell ni interpolation de `${…}`.
Les variables déjà définies dans l’environnement sont prioritaires.

## API

- `GET /healthz` : sonde publique ; ne vérifie pas la disponibilité du modèle.
- `GET /api/v1/config` : instructions et réglages par défaut, limite d’upload.
- `POST /api/v1/extractions` : formulaire multipart, champ `file` (PDF) et champ
  `options` (objet JSON sérialisé, facultatif).
- `/docs`, `/redoc`, `/openapi.json` : documentation publique, sans secrets.

Les routes `/api/v1/*` existantes exigent `Authorization: Bearer <API_TOKEN>`.
Le frontend ne reçoit jamais la clé fournisseur et ne stocke pas le token dans
les cookies, `localStorage` ou `sessionStorage`. La déconnexion efface le token
et les résultats en mémoire.

```bash
# API_TOKEN déjà défini dans votre environnement ; ne pas mettre de secret en dur.
curl --fail-with-body http://127.0.0.1:8501/api/v1/extractions \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -F 'file=@document.pdf;type=application/pdf' \
  -F 'options={"extraction_passes":2,"max_workers":8,"max_char_buffer":1200,"include_text":false}'
```

Options : `prompt` (1–10000 caractères), `extraction_passes` (1–5), `max_workers`
(1–24), `max_char_buffer` (500–4000), `include_text` (booléen).
La réponse contient `document`, `jsonl`, `html`, `warnings`, `skipped_pages`,
`omitted_entities` et `text` (null sauf demande explicite). Le document LangExtract
et le JSONL contiennent aussi le texte source nécessaire aux annotations.

Codes principaux : `401` token absent/invalide ; `413` fichier/requête trop gros ;
`415` format HTTP incorrect ; `422` PDF ou paramètres invalides ; `502` erreur
fournisseur/extraction ; `503` extraction déjà en cours (`Retry-After: 5`).
L’authentification et l’admission ont lieu **avant** lecture du corps et du PDF.
Le corps est également borné sans `Content-Length` ; le parseur multipart limite
le nombre de fichiers et de champs. Les fichiers temporaires sont fermés après
traitement. Aucune extraction ni aucun historique ne sont persistés côté serveur.

## Fonctionnement conservé

- Instructions françaises et exemples métier du dépôt existant.
- Provider `openai` forcé, même pour un alias comme `ai-flash`.
- JSON par défaut ; YAML avec `USE_OPENAI_JSON_MODE=0` si l’endpoint refuse JSON.
- Entités nulles omises avec avertissement ; attributs nulls acceptés.
- Pages sans texte/illisibles signalées ; OCR préalable nécessaire pour les scans.
- Résumé, tableau d’entités et surlignage dans le texte ; exports JSONL et HTML.
  La vue intégrée utilise des nœuds texte Vue échappés. Le HTML LangExtract est
  uniquement téléchargé, jamais injecté dans le DOM de l’application.

## Déploiement

Une extraction active par processus ; les suivantes reçoivent `503`, sans file
non bornée. PDF et inférence s’exécutent dans un thread pour garder les sondes
réactives. Les requêtes internes au modèle suivent `max_workers`. Conserver un
seul worker Uvicorn pour cette limite globale ; plusieurs instances nécessitent
une admission partagée. L’appel est synchrone HTTP, sans file de tâches durable.

```ini
[Service]
WorkingDirectory=/opt/langextract-demo
ExecStart=/bin/bash /opt/langextract-demo/run.sh 127.0.0.1 8501
Restart=on-failure
```

Exécuter l’installation avant de démarrer le service. Mettre un reverse proxy
HTTPS devant Uvicorn hors accès local ; régler sa taille de requête à au moins
21 Mio et son délai de lecture selon la durée d’inférence. Le token est un
secret partagé révocable par changement de configuration et redémarrage ;
ce mécanisme ne fournit pas d’identités individuelles ni de SSO.
Le fournisseur configuré reçoit le texte des documents ; ses règles de
conservation sont indépendantes de cette application.

## Frontend et skills

Implémentation guidée par les skills du dépôt
[`ynotopec/gouv-fr-skills`](https://github.com/ynotopec/gouv-fr-skills) :
`fr-gov-build-vue-frontend`, `fr-gov-build-vue-design-system`,
`fr-gov-scaffold-backend-api`, `fr-gov-secure-coding-rules`.
VueDsfr 8.21.0 et DSFR `~1.14.4` sont alignés, avec les cinq couches CSS
obligatoires, hébergées localement avec les polices. Aucune dépendance au dépôt
de skills à l’exécution. L’interface est en français, avec labels, navigation
clavier, lien d’évitement et annonces de statut. Aucun audit RGAA complet
n’a été réalisé ; aucune conformité réglementaire n’est revendiquée.

L’audit npm couvre aussi les outils de développement. Vitest est en version
corrigée ; des overrides limités à `js-beautify` (dépendance des tests Vue)
imposent `glob` ≥14.0.2 et `minimatch` ≥11.0.1 en attendant leur adoption amont.

Pour développer séparément : lancer l’API sur 8501, puis `cd frontend && npm ci
&& npm run dev`. Le proxy Vite relaie `/api` vers le backend local ; aucun CORS
ouvert n’est nécessaire.

## Vérification

Installer [Gitleaks](https://github.com/gitleaks/gitleaks), puis activer le hook
versionné : `git config core.hooksPath .githooks`. Le hook contrôle l’index avec
`gitleaks protect --staged --redact` ; la CI contrôle aussi l’historique complet.

```bash
uv sync --locked
uv run pytest -q
uv run ruff check .
cd frontend
npm ci
npm test
npm run build
npm audit --audit-level=moderate
```

Les tests backend couvrent l’authentification, l’upload borné (y compris sans
Content-Length), les paramètres, l’admission concurrente, les erreurs et les
exports avec un endpoint OpenAI simulé localement. Les tests front couvrent
l’authentification, l’upload, les erreurs, l’échappement et les exports.
La qualité réelle des réponses doit être vérifiée avec votre modèle.
