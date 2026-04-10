import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQ_FILE = ROOT / "requirements.txt"
STAMP_FILE = VENV_DIR / ".requirements.sha256"
APP_FILE = ROOT / "app.py"

if os.name == "nt":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"


def run_checked(cmd):
    subprocess.check_call(cmd, cwd=str(ROOT))


def ensure_venv():
    if VENV_PYTHON.exists():
        return
    print("Creating virtual environment...")
    venv.EnvBuilder(with_pip=True).create(str(VENV_DIR))


def requirements_hash():
    return hashlib.sha256(REQ_FILE.read_bytes()).hexdigest()


def ensure_dependencies():
    if not REQ_FILE.exists():
        raise FileNotFoundError("requirements.txt not found.")

    expected_hash = requirements_hash()
    current_hash = STAMP_FILE.read_text(encoding="utf-8").strip() if STAMP_FILE.exists() else ""

    if current_hash == expected_hash:
        print("Dependencies already up to date.")
        return

    print("Installing dependencies...")
    run_checked([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"])
    run_checked([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQ_FILE)])
    STAMP_FILE.write_text(expected_hash, encoding="utf-8")


def run_app():
    host = os.getenv("HOST", "127.0.0.1").strip()
    port = os.getenv("PORT", "5000").strip()
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"Starting web app at http://{display_host}:{port}")
    return subprocess.call([str(VENV_PYTHON), str(APP_FILE)], cwd=str(ROOT))


def main():
    ensure_venv()
    ensure_dependencies()
    exit_code = run_app()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"Setup failed while running command: {exc.cmd}")
        raise SystemExit(exc.returncode) from exc
    except Exception as exc:
        print(f"Setup failed: {exc}")
        raise SystemExit(1) from exc
