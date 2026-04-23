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
