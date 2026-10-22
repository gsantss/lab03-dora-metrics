"""Confere repetição byte a byte nos dados reais antes da publicação do PR."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib

from analises.rq01_04 import generate


def hashes(directory):
    root = Path(directory)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def main():
    metrics = Path("data/processed/metrics.csv")
    original = metrics.read_bytes()
    out = Path("analises/resultados/rq01_04")
    expected = hashes(out)
    with TemporaryDirectory(prefix="issue42-reproducao-") as work:
        work = Path(work)
        result = generate(metrics, work / "resultados", work / "artigo", work / "docs.md")
        if result["repositories"] != 300:
            raise ValueError(f"Issue #42 requer a coleta final de 300 repositorios; recebidos {result['repositories']}")
        actual = hashes(work / "resultados")
        if expected != actual:
            different = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
            raise ValueError("Reexecucao divergiu: " + ", ".join(different))
        if (work / "artigo/resultados_rq01_04.tex").read_bytes() != Path("artigo/resultados_rq01_04.tex").read_bytes():
            raise ValueError("Artigo divergiu na reexecucao")
        if (work / "docs.md").read_bytes() != Path("docs/resultados-rq01-rq04.md").read_bytes():
            raise ValueError("Relatorio Markdown divergiu na reexecucao")
        for png in (work / "artigo/figuras").glob("*.png"):
            if png.read_bytes() != (Path("artigo/figuras") / png.name).read_bytes():
                raise ValueError(f"Figura do artigo divergiu: {png.name}")
    if metrics.read_bytes() != original:
        raise ValueError("metrics.csv foi alterado durante a analise")
    print("Reproducao aprovada: 300 repositorios, tabelas/PNGs/artigo identicos; CSV de entrada preservado.")


if __name__ == "__main__":
    main()
