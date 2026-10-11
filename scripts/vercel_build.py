"""Etapa de build da Vercel. A Vercel roda o collectstatic sozinha; aqui só se migra o banco
das implantações de prévia. A produção é migrada à mão, antes de promover a versão."""

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path


def main(env: Mapping[str, str], rodar=subprocess.run) -> None:
    if env.get("VERCEL_ENV") != "preview":
        return
    ambiente = dict(env)
    # O migrate usa a conexão direta (sem pooler), se houver.
    ambiente["DATABASE_URL"] = env.get("DATABASE_URL_DIRETA") or env["DATABASE_URL"]
    rodar(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        env=ambiente,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )


if __name__ == "__main__":
    main(os.environ)
