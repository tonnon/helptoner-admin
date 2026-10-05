import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def rodar_django(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Roda o manage.py com o Python atual, em outro processo, e captura a saída como texto."""
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=RAIZ,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
