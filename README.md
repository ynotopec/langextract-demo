# langextract-demo

Demo Streamlit pour extraire des entités depuis un PDF avec `langextract` via un endpoint OpenAI-compatible.

## Objectifs couverts

- ✅ Idempotent (relancer les scripts est sans effet destructif)
- ✅ Gestion d'environnement avec `uv`
- ✅ Virtualenv par défaut: `~/venv/<basename projet>`
- ✅ `install.sh` compatible installation + upgrade (`--upgrade`)
- ✅ `source run.sh [IP] [PORT]` (utilisable aussi en mode `bash run.sh` / systemd)
- ✅ Compatible infra GPU (H100 / DGX Spark) via endpoint OpenAI-compatible

---

## Prérequis

- Linux/macOS
- `python3`
- accès réseau à un endpoint OpenAI-compatible (local ou distant)

> Si `uv` n'est pas installé, `install.sh` l'installe automatiquement avec `pip --user`.

## Variables d'environnement

1. Copier l'exemple:

```bash
cp .env.example .env
```

2. Renseigner uniquement les variables importantes dans `.env`:

- `OPENAI_API_MODEL`
- `OPENAI_API_BASE`
- `OPENAI_API_KEY`

Les variables optionnelles restent commentées avec `#` dans `.env.example`.

## Installation (idempotente)

```bash
./install.sh
```

- crée `~/venv/<basename projet>` si absent
- synchronise les dépendances avec `uv sync`

### Upgrade dépendances

```bash
./install.sh --upgrade
```

- met à jour le lock (`uv lock --upgrade`)
- resynchronise l'environnement

## Exécution

### Shell interactif

```bash
source run.sh [IP] [PORT]
```

Exemple:

```bash
source run.sh 0.0.0.0 8501
```

### Compatibilité systemd

Exemple `ExecStart`:

```ini
ExecStart=/bin/bash -lc 'cd /opt/langextract-demo && source run.sh 0.0.0.0 8501'
```

### Scripts de compatibilité

- `start.sh` → alias vers `run.sh`
- `upgrade.sh` → alias vers `install.sh --upgrade`

## Notes H100 / DGX Spark

L'application consomme un endpoint OpenAI-compatible. Pour H100/DGX Spark, la compatibilité dépend surtout de votre couche de serving (ex: vLLM) et du modèle exposé dans `OPENAI_API_MODEL`/`OPENAI_API_BASE`.

## Extraction et compatibilité

- Interface et instructions par défaut en français, comme sur `dev`.
- Le provider `openai` est forcé via `ModelConfig` pour tous les noms de modèles,
  y compris les alias tels que `ai-flash` (SGLang/vLLM).
- Le format JSON utilisé par `dev` est conservé par défaut. Si l’endpoint rejette
  le mode JSON (`src property must be a valid json object`), définir
  `USE_OPENAI_JSON_MODE=0` dans `.env` puis redémarrer pour utiliser YAML.
  Les exports restent JSONL et HTML dans les deux modes.
- Les pages PDF illisibles ou sans texte sont signalées avec leur numéro et
  ignorées. Un PDF scanné nécessite un OCR en amont ; aucun OCR n’est intégré.

### Entités nulles renvoyées par le modèle

`Extraction text must be a string, integer, or float. Found: <class 'NoneType'>`
indique qu’une valeur d’entité produite par le modèle vaut `null`. Le traitement
peut se terminer malgré cette erreur, sans garantir que toutes les entités du
segment ont été conservées.

Le prompt demande d’omettre les entités absentes. Le parseur retire uniquement
les entités nulles et leurs attributs associés, conserve les entités valides du
même segment et affiche un avertissement avec le nombre d’entités ignorées.
Un dictionnaire d’attributs `null` est valide et reste accepté. Les autres erreurs
de structure interrompent explicitement l’extraction pour éviter un résultat
partiel présenté comme complet.

Cette adaptation utilise l’extension `FormatHandler` de LangExtract, sans modifier
la bibliothèque ni ses logs. Elle requiert `langextract[openai]>=1.7.1,<2` ; lancer
`./install.sh` pour synchroniser les dépendances. `dev` reste inchangée comme point
de comparaison fonctionnel.

## Tests

```bash
python -m pip install . pytest
python -m pytest -q
```

Les tests utilisent un endpoint OpenAI simulé localement : aucune clé réelle ni
connexion à un fournisseur ne sont nécessaires. Ils couvrent JSON/YAML, les
entités nulles, les erreurs de structure, les pages ignorées, les exports et
l’interface Streamlit. Ils ne valident pas la qualité des réponses de votre modèle.
