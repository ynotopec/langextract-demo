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


@pytest.mark.parametrize(
    "version,accepted",
    [
        ("18.19.1", False),
        ("20.19.0", False),
        ("22.22.2", False),
        ("24.14.0", False),
        ("24.15.0", True),
        ("25.0.0", False),
        ("26.0.0", True),
    ],
)
def test_install_checks_node_before_any_dependency_install(tmp_path, version, accepted):
    import json
    import shutil

    real_node = shutil.which("node")
    if real_node is None:
        pytest.skip("Node is tested by the frontend CI job")
    project = Path(__file__).resolve().parents[1]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    node = bin_dir / "node"
    node.write_text(
        "#!/usr/bin/env python3\nimport subprocess,sys\n"
        f'if sys.argv[1] == "--version": print("v{version}")\n'
        "else:\n"
        f"    prefix = \"Object.defineProperty(process.versions, 'node', {{value: '{version}'}});\"\n"
        f'    sys.exit(subprocess.run([{json.dumps(real_node)}, "-e", prefix + sys.argv[2]]).returncode)\n'
    )
    node.chmod(0o755)
    for name in ("npm", "uv"):
        stub = bin_dir / name
        stub.write_text(
            '#!/usr/bin/env bash\nprintf called > "$INSTALL_MARKER"\nexit 99\n'
        )
        stub.chmod(0o755)
    marker = tmp_path / "called"
    env = dict(
        os.environ,
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        UV_BIN=str(bin_dir / "uv"),
        INSTALL_MARKER=str(marker),
    )
    result = subprocess.run(
        ["bash", str(project / "install.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if accepted:
        assert result.returncode == 99  # npm reached, no real package installation.
        assert marker.exists()
    else:
        assert result.returncode == 1
        assert "incompatible" in result.stderr
        assert not marker.exists()


@pytest.mark.parametrize("sourced", [False, True])
@pytest.mark.parametrize(
    "entry,expected",
    [
        ('OPENAI_API_KEY="synthetic\\$value"', "synthetic$value"),
        ("OPENAI_API_KEY='synthetic$value'", "synthetic$value"),
        (
            'KEY_PREFIX=synthetic\nOPENAI_API_KEY="${KEY_PREFIX}-value"',
            "synthetic-value",
        ),
        ("OPENAI_API_KEY=synthetic\\#value", "synthetic#value"),
        ('export OPENAI_API_KEY="synthetic-plain"', "synthetic-plain"),
    ],
)
def test_launcher_preserves_shell_env_values_without_python_reparse(
    tmp_path, sourced, entry, expected
):
    import json
    import sys

    source = Path(__file__).resolve().parents[1]
    project = tmp_path / "project with spaces"
    (project / "frontend/dist").mkdir(parents=True)
    (project / "frontend/dist/index.html").write_text("built")
    (project / "run.sh").write_text((source / "run.sh").read_text())
    (project / ".env").write_text(entry + "\n")
    venv = tmp_path / "custom venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/activate").write_text("")
    fake_python = venv / "bin/python"
    fake_python.write_text("""#!/usr/bin/env bash
exec "$REAL_PYTHON" - <<'PYCHILD'
import json, os
from pathlib import Path
import app
app.__file__ = str(Path.cwd() / 'app.py')
settings = app.Settings.from_env()
Path(os.environ['SETTINGS_LOG']).write_text(json.dumps({'key': settings.model_key}))
PYCHILD
""")
    fake_python.chmod(0o755)
    env = dict(
        os.environ,
        VENV_DIR=str(venv),
        REAL_PYTHON=sys.executable,
        PYTHONPATH=str(source),
        SETTINGS_LOG=str(tmp_path / "settings.json"),
        OPENAI_API_KEY="synthetic-stale-inherited",
        LANGEXTRACT_DOTENV_SOURCED="stale",
    )
    command = (
        ["bash", "-c", 'source "$1"', "test", str(project / "run.sh")]
        if sourced
        else ["bash", str(project / "run.sh")]
    )
    subprocess.run(command, env=env, cwd=tmp_path, check=True, capture_output=True)
    assert json.loads((tmp_path / "settings.json").read_text())["key"] == expected
