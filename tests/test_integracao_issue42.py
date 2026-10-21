from pathlib import Path

import pytest

from analises.instalar_issue42 import integrate


def test_integracao_idempotente_preserva_outras_rqs(tmp_path):
    (tmp_path / "artigo").mkdir()
    article = tmp_path / "artigo/main.tex"
    before = r"\section{Resultados}\subsection{RQ 01 a 04}\label{sec:rq0104}" + "\n"
    after = r"\subsection{RQ 05}Preservar texto da RQ05." + "\n"
    article.write_text(before + r"\textbf{[TODO -- issue \#42]} Antigo placeholder." + "\n" + after)
    (tmp_path / "README.md").write_text("Texto autoral e outras RQs.\n")
    integrate(tmp_path)
    first = article.read_bytes(), (tmp_path / "README.md").read_bytes()
    integrate(tmp_path)
    assert first == (article.read_bytes(), (tmp_path / "README.md").read_bytes())
    assert article.read_text().startswith(before)
    assert article.read_text().endswith(after)
    assert article.read_text().count(r"\input{resultados_rq01_04.tex}") == 1


def test_nao_substitui_texto_autoral_sem_marcador(tmp_path):
    (tmp_path / "artigo").mkdir()
    article = tmp_path / "artigo/main.tex"
    original = r"\label{sec:rq0104}Resultado escrito pelo grupo.\subsection{RQ05}"
    article.write_text(original)
    (tmp_path / "README.md").write_text("Original")
    with pytest.raises(ValueError, match="texto autoral"):
        integrate(tmp_path)
    assert article.read_text() == original
