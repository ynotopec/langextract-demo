# langextract-demo

Minimal Streamlit app for extracting entities from PDFs with `langextract` against an OpenAI-compatible endpoint.

## Quick start

1. Copy env template:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` values.
3. Run app:
   ```bash
   ./start.sh [IP] [PORT]
   ```

Defaults are `127.0.0.1` and `8501`.

## Dependency maintenance

Use:

```bash
./upgrade.sh
```

This upgrades dependency locks and syncs your virtualenv.

## Notes

- Virtual environment path is idempotent and defaults to:
  `~/venv/<project-directory-name>`
- Override with `VENV_DIR=/custom/path ./start.sh`
