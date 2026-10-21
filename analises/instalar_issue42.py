"""Integra somente os blocos da Issue #42, sem substituir outras RQs."""
from pathlib import Path

README_BEGIN = "<!-- issue42-rq01-04 -->"
README_END = "<!-- /issue42-rq01-04 -->"
TEX_BEGIN = "% issue42-rq01-04"
TEX_END = "% /issue42-rq01-04"


def integrate(root=Path(".")):
    root = Path(root)
    article = root / "artigo/main.tex"
    original = article.read_text(encoding="utf-8-sig")
    replacement = TEX_BEGIN + "\n\\input{resultados_rq01_04.tex}\n" + TEX_END
    if TEX_BEGIN in original:
        start = original.index(TEX_BEGIN)
        end = original.index(TEX_END, start) + len(TEX_END)
    else:
        anchor = r"\label{sec:rq0104}"
        if anchor not in original:
            raise ValueError("Artigo sem sec:rq0104; integracao automatica interrompida para preservar o texto.")
        start = original.index(anchor) + len(anchor)
        end = original.find(r"\subsection{", start)
        if end == -1:
            raise ValueError("Nao encontrei a secao seguinte a RQ01-04 no artigo.")
        old = original[start:end].strip()
        if old and not old.startswith(r"\textbf{[TODO -- issue \#42]}"):
            raise ValueError("RQ01-04 ja tem texto autoral sem marcador; integracao interrompida para nao sobrescrever.")
        replacement = "\n\n" + replacement + "\n\n"
    integrated = original[:start] + replacement + original[end:]
    readme = root / "README.md"
    content = readme.read_text(encoding="utf-8-sig")
    block = README_BEGIN + '''
## RQ 01 a 04 e classificação C1 — Issue #42

Requer Python 3.12 e as dependências de `requirements.txt`. Não consulta a API nem refaz a mineração.

```bash
python -m analises.rq01_04
pytest tests/test_rq01_04.py tests/test_integracao_issue42.py
```

Entrada única: `data/processed/metrics.csv`. Saídas em `analises/resultados/rq01_04/`:
estatísticas (mediana, Q1, Q3 e IQR), categorias C1 com ausentes explícitos,
comparações pareadas, censura por repositório, cinco PNGs e manifesto SHA-256.
O comando também atualiza `docs/resultados-rq01-rq04.md`,
`artigo/resultados_rq01_04.tex` e as cinco figuras correspondentes em `artigo/figuras/`.
Ao enviar ao Overleaf, inclua esse `.tex` gerado junto de `main.tex` e `figuras/`.

Zeros são preservados e ausentes não são imputados. IQR é Q3-Q1, com quantis lineares.
C1 usa as colunas do CSV, com lead time (a) e CFR (a); não recalibra os limiares.
As unidades de análise são repositórios: a mediana das medianas não é a mediana de todos os episódios.
O relatório confronta H1 a H4 com os dados e separa censura de recuperação observada.
Repetições são byte a byte iguais no mesmo ambiente; versões e hashes são registrados no manifesto.
''' + README_END
    if README_BEGIN in content:
        a = content.index(README_BEGIN)
        b = content.index(README_END, a) + len(README_END)
        content = content[:a] + block + content[b:]
    else:
        content = content.rstrip() + "\n\n" + block + "\n"
    article.write_text(integrated, encoding="utf-8", newline="\n")
    readme.write_text(content, encoding="utf-8", newline="\n")
    workflow = root / ".github/workflows/testes.yml"
    if workflow.exists():
        ci = workflow.read_text(encoding="utf-8-sig")
        ci = ci.replace("pip install -r requirements.txt", "pip install -r requirements-issue42.txt")
        marker = "# issue42-reproducao"
        if marker not in ci:
            ci = ci.rstrip() + '''
      # issue42-reproducao
      - name: Reproduzir RQ01-04 nos dados finais
        run: |
          python -m analises.rq01_04
          python -m analises.verificar_issue42
'''
        workflow.write_text(ci, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    integrate()
