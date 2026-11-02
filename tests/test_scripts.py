import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("sourced", [False, True])
def test_launch_uses_requested_venv_and_keeps_ip_port(tmp_path, sourced):
    source = Path(__file__).resolve().parents[1]
    project = tmp_path / "project with spaces"
    (project / "frontend/dist").mkdir(parents=True)
    (project / "frontend/dist/index.html").write_text("built frontend")
    (project / "run.sh").write_text((source / "run.sh").read_text())
    (project / "install.sh").write_text("exit 99\n")
    venv = tmp_path / "custom venv"
    uv = tmp_path / "uv"
    uv.write_text("""#!/usr/bin/env bash
set -eu
case "$1" in
  venv)
    mkdir -p "$2/bin"
    touch "$2/bin/activate"
    cat > "$2/bin/python" <<'PYTHON'
#!/usr/bin/env bash
printf '%s\\n' "$@" > "$LAUNCH_LOG"
PYTHON
    chmod +x "$2/bin/python"
    ;;
  sync) printf '%s' "$UV_PROJECT_ENVIRONMENT" > "$SYNC_LOG" ;;
  *) exit 99 ;;
esac
""")
    uv.chmod(0o755)
    env = dict(
        os.environ,
        UV_BIN=str(uv),
        VENV_DIR=str(venv),
        LAUNCH_LOG=str(tmp_path / "launch"),
        SYNC_LOG=str(tmp_path / "sync"),
    )
    subprocess.run([str(uv), "venv", str(venv)], env=env, check=True)
    command = (
        ["bash", "-c", 'source "$1" 10.0.1.1 8997', "test", str(project / "run.sh")]
        if sourced
        else ["bash", str(project / "run.sh"), "10.0.1.1", "8997"]
    )
    # A second run must reuse the venv and preserve the same launch arguments.
    for _ in range(2):
        subprocess.run(command, env=env, cwd=tmp_path, check=True, capture_output=True)
        assert (tmp_path / "launch").read_text().splitlines() == [
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "10.0.1.1",
            "--port",
            "8997",
            "--no-access-log",
        ]
