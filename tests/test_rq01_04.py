"""Contratos estatísticos, integridade dos dados e reprodução da Issue #42."""
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import pytest

from analises.rq01_04 import (
    CATEGORIES, CLASS_COLUMNS, METRICS, axis_scale, category_table, censorship,
    describe, generate, load_metrics, paired_table,
)


def example():
    return pd.DataFrame({
        "full_name": ["b/repo", "a/repo", "c/repo", "d/repo"],
        "deployment_frequency": [0, 1, 8, 0.5],
        "lead_time_release_h": [48, 24, 72, np.nan],
        "lead_time_commit_h": [24, 48, 72, np.nan],
        "cfr_ci": [0, 0.25, 0.5, 0.75],
        "cfr_delivery": [0.5, 0.25, 0, np.nan],
        "recovery_h": [2, 0, np.nan, np.nan],
        "recovery_episodes": [2, 1, 3, 0],
        "recovery_censored": [1, 0, 3, 0],
        "recovery_censored_ratio": [0.5, 0, 1, np.nan],
        "class_deployment_frequency": ["Low", "High", "Elite", "Medium"],
        "class_lead_time": ["High", "High", "High", ""],
        "class_cfr": ["Elite", "High", "Low", "Low"],
        "class_recovery": ["High", "Elite", "", ""],
        "class_overall": ["High", "High", "", ""],
    })


def save(frame, path):
    frame.to_csv(path, index=False, na_rep="", lineterminator="\n")
    return path


def test_hand_computed_quantiles_zero_and_missing():
    result = describe(pd.Series([0, 1, 2, 3, np.nan]))
    assert result["n"] == 4
    assert result["ausentes"] == 1
    assert result["mediana"] == 1.5
    assert result["q1"] == 0.75
    assert result["q3"] == 2.25
    assert result["iqr"] == 1.5


def test_categories_include_zero_counts_and_missing_denominator():
    result = category_table(example())
    overall = result[result.coluna.eq("class_overall")].set_index("categoria")
    assert overall.loc["Sem classificação", "n"] == 2
    assert overall.loc["High", "percentual"] == 50
    assert overall.loc["Elite", "n"] == 0
    for _, group in result.groupby("coluna"):
        assert list(group.categoria) == list(CATEGORIES)
        assert group.n.sum() == 4
        assert group.percentual.sum() == pytest.approx(100)


def test_paired_comparisons_use_same_repositories():
    result = paired_table(example())
    lead = result.iloc[0]
    assert lead.n_pares == 3
    assert (lead.a_maior_b, lead.a_igual_b, lead.a_menor_b) == (1, 1, 1)
    assert lead.mediana_diferenca_a_menos_b == 0
    assert result.iloc[1].rho_spearman == pytest.approx(-1)


def test_censoring_distinguishes_no_episodes_from_all_censored():
    table, result = censorship(example())
    assert result["episodios_total"] == 6
    assert result["episodios_censurados"] == 4
    assert result["fracao_ponderada_por_episodios"] == pytest.approx(4 / 6)
    assert result["repositorios_sem_episodios"] == 1
    assert result["repositorios_so_censurados"] == 1
    assert table.loc[3, "estado"] == "sem episodios"
    assert pd.isna(table.loc[3, "recovery_censored_ratio"])


@pytest.mark.parametrize("kind", ["duplicate", "column", "invalid", "infinity", "negative", "ratio", "fractional_count", "censored_count", "censored_ratio", "category"])
def test_bad_inputs_rejected(tmp_path, kind):
    frame = example()
    if kind == "duplicate": frame.loc[1, "full_name"] = frame.loc[0, "full_name"]
    if kind == "column": frame = frame.drop(columns=["cfr_ci"])
    if kind == "invalid": frame["cfr_ci"] = "erro"
    if kind == "infinity": frame["cfr_ci"] = float("inf")
    if kind == "negative": frame["deployment_frequency"] = -1
    if kind == "ratio": frame["cfr_delivery"] = 2
    if kind == "fractional_count": frame["recovery_episodes"] = 0.5
    if kind == "censored_count": frame["recovery_censored"] = 99
    if kind == "censored_ratio": frame["recovery_censored_ratio"] = 0.1
    if kind == "category": frame["class_overall"] = "Muito bom"
    with pytest.raises(ValueError):
        load_metrics(save(frame, tmp_path / "bad.csv"))


def test_missing_is_not_zero_and_order_is_canonical(tmp_path):
    result = load_metrics(save(example(), tmp_path / "sample.csv"))
    assert result.full_name.tolist() == ["a/repo", "b/repo", "c/repo", "d/repo"]
    assert result.recovery_h.isna().sum() == 2
    assert result.recovery_h.eq(0).sum() == 1


def test_constant_correlations_are_undefined():
    frame = example()
    frame["cfr_ci"] = 0
    assert np.isnan(paired_table(frame).iloc[1].rho_spearman)


def hashes(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob("*")) if p.is_file()}


def test_two_runs_same_csv_same_bytes_and_order_invariant(tmp_path):
    source = save(example(), tmp_path / "metrics.csv")
    before = source.read_bytes()
    generate(source, tmp_path / "one", tmp_path / "article1")
    generate(source, tmp_path / "two", tmp_path / "article2")
    assert hashes(tmp_path / "one") == hashes(tmp_path / "two")
    assert hashes(tmp_path / "article1") == hashes(tmp_path / "article2")
    assert source.read_bytes() == before
    shuffled = save(example().iloc[::-1], tmp_path / "reordered.csv")
    generate(shuffled, tmp_path / "three")
    first, third = hashes(tmp_path / "one"), hashes(tmp_path / "three")
    first.pop("manifesto.json"); third.pop("manifesto.json")
    assert first == third


def test_no_observations_for_duration_and_no_episodes(tmp_path):
    frame = example().iloc[:1].copy()
    for key in METRICS:
        if key != "deployment_frequency": frame[key] = np.nan
    for key in CLASS_COLUMNS:
        if key != "class_deployment_frequency": frame[key] = ""
    frame["recovery_episodes"] = 0
    frame["recovery_censored"] = 0
    source = save(frame, tmp_path / "empty_metrics.csv")
    result = generate(source, tmp_path / "results")
    assert result["repositories"] == 1
    assert result["censorship"]["fracao_ponderada_por_episodios"] is None


def test_scale_handles_zero_without_dropping_it():
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    assert axis_scale(ax, [pd.Series([0, 0.01, 100])]) == "symlog"
    assert axis_scale(ax, [pd.Series([0.01, 100])]) == "log"
    assert axis_scale(ax, [pd.Series([0, 0, 0])]) == "linear"
    plt.close(fig)
