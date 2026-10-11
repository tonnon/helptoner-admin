"""Gera static/css/app.css com o executável standalone do Tailwind CSS (sem Node.js).

    uv run python scripts/css.py             gera o CSS minificado
    uv run python scripts/css.py --observar  gera de novo a cada mudança nos templates
    uv run python scripts/css.py --conferir  falha se o static/css/app.css estiver desatualizado

O executável é baixado uma vez para .ferramentas/ e só é usado se o SHA-256 bater.
Só roda no Linux x64 (WSL no desenvolvimento, Ubuntu no CI).
"""

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

VERSAO = "4.3.3"
SHA256 = "dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a"
URL = (
    f"https://github.com/tailwindlabs/tailwindcss/releases/download/v{VERSAO}/tailwindcss-linux-x64"
)

RAIZ = Path(__file__).resolve().parent.parent
FERRAMENTAS = RAIZ / ".ferramentas"
ENTRADA = RAIZ / "tailwind" / "app.css"
SAIDA = RAIZ / "static" / "css" / "app.css"


def _sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(1 << 20):
            resumo.update(bloco)
    return resumo.hexdigest()


def executavel() -> Path:
    """O caminho do Tailwind conferido; baixa se faltar. Encerra se o SHA-256 não bater."""
    if sys.platform != "linux" or platform.machine() != "x86_64":
        sys.exit(
            f"scripts/css.py só roda no Linux x64 (aqui: {sys.platform} {platform.machine()}). "
            'No Windows, use o WSL: linux "uv run python scripts/css.py".'
        )
    destino = FERRAMENTAS / f"tailwindcss-{VERSAO}-linux-x64"
    if destino.exists() and _sha256(destino) == SHA256:
        return destino
    FERRAMENTAS.mkdir(exist_ok=True)
    parcial = destino.with_name(destino.name + ".baixando")
    print(f"Baixando o Tailwind CSS {VERSAO}...", file=sys.stderr)
    with urllib.request.urlopen(URL, timeout=120) as resposta, parcial.open("wb") as arquivo:
        shutil.copyfileobj(resposta, arquivo)
    obtido = _sha256(parcial)
    if obtido != SHA256:
        parcial.unlink()
        sys.exit(f"SHA-256 do Tailwind não confere: esperado {SHA256}, obtido {obtido}.")
    parcial.chmod(0o755)
    parcial.replace(destino)
    return destino


def gerar(saida: Path, *extras: str) -> int:
    comando = [str(executavel()), "-i", str(ENTRADA), "-o", str(saida), "--minify", *extras]
    return subprocess.run(comando, cwd=RAIZ, check=False).returncode


def conferir() -> int:
    with tempfile.TemporaryDirectory() as pasta:
        temporario = Path(pasta) / "app.css"
        if codigo := gerar(temporario):
            return codigo
        if not SAIDA.exists() or temporario.read_bytes() != SAIDA.read_bytes():
            print("CSS desatualizado: rode uv run python scripts/css.py", file=sys.stderr)
            return 1
    print("CSS em dia.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o CSS do sistema com o Tailwind.")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--observar", action="store_true", help="gera de novo a cada mudança")
    modo.add_argument("--conferir", action="store_true", help="só confere se o CSS está em dia")
    argumentos = parser.parse_args(argv)
    if argumentos.conferir:
        return conferir()
    if argumentos.observar:
        return gerar(SAIDA, "--watch")
    return gerar(SAIDA)


if __name__ == "__main__":
    sys.exit(main())
