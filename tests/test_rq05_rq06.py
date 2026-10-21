import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.multitest import multipletests

from analises.figuras import (
    _ordered_groups,
    _p,
    plot_rq06_distributions,
    plot_rq06_effects,
)
from analises.rq05_rq06 import (
    METRICS,
    build_factors,
    cliffs_delta,
    cliffs_magnitude,
    collapse_small_languages,
    compare_groups,
    epsilon_magnitude,
    epsilon_squared,
    plot_rq05,
    quartile_groups,
    run_rq05,
    run_rq06,
    spearman,
)


# ---------------------------------------------------------------- Spearman

def test_spearman_perfect_monotonic_relation():
    result = spearman(pd.Series([1, 2, 3, 4, 5]), pd.Series([10, 20, 30, 40, 50]))
    assert result["rho"] == pytest.approx(1.0)
    assert result["n"] == 5


def test_spearman_inverse_relation_is_minus_one():
    result = spearman(pd.Series([1, 2, 3, 4]), pd.Series([9, 7, 5, 1]))
    assert result["rho"] == pytest.approx(-1.0)


def test_spearman_drops_missing_pairs():
    result = spearman(pd.Series([1, 2, 3, 4, np.nan]), pd.Series([1, 2, np.nan, 4, 5]))
    assert result["n"] == 3


def test_spearman_with_too_few_pairs_returns_nan():
    result = spearman(pd.Series([1, 2]), pd.Series([1, 2]))
    assert np.isnan(result["rho"]) and result["n"] == 2


# ------------------------------------------------------------ tamanho de efeito

def test_cliffs_delta_extremes_and_tie():
    assert cliffs_delta([1, 2, 3], [4, 5, 6]) == pytest.approx(-1.0)
    assert cliffs_delta([4, 5, 6], [1, 2, 3]) == pytest.approx(1.0)
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == pytest.approx(0.0)


@pytest.mark.parametrize(
    "delta,expected",
    [(0.10, "desprezível"), (-0.20, "pequeno"), (0.40, "médio"), (-0.474, "grande"), (1.0, "grande")],
)
def test_cliffs_magnitude_thresholds(delta, expected):
    assert cliffs_magnitude(delta) == expected


def test_epsilon_squared_formula_and_thresholds():
    assert epsilon_squared(10, 11) == pytest.approx(1.0)
    assert epsilon_magnitude(0.005) == "desprezível"
    assert epsilon_magnitude(0.02) == "pequeno"
    assert epsilon_magnitude(0.10) == "médio"
    assert epsilon_magnitude(0.30) == "grande"


# ------------------------------------------------------------------- fatores

def test_quartile_groups_splits_into_four_equal_groups():
    groups = quartile_groups(pd.Series(range(1, 9), dtype=float))
    assert groups.tolist() == ["Q1", "Q1", "Q2", "Q2", "Q3", "Q3", "Q4", "Q4"]


def test_quartile_groups_keeps_missing_values_missing():
    groups = quartile_groups(pd.Series([1.0, 2.0, 3.0, 4.0, np.nan]))
    assert pd.isna(groups.iloc[-1])


def test_collapse_small_languages_groups_rare_ones_as_outras():
    language = pd.Series(["Go"] * 3 + ["Rust"] * 3 + ["Zig"], dtype=object)
    result = collapse_small_languages(language, minimum=3)
    assert result.tolist() == ["Go"] * 3 + ["Rust"] * 3 + ["Outras"]


def test_build_factors_has_requested_columns_and_optional_type():
    repos = pd.DataFrame(
        {
            "full_name": [f"o/r{i}" for i in range(8)],
            "language": ["Go"] * 8,
            "stars": range(1, 9),
            "contributors": range(10, 18),
            "created_at": [f"202{i % 5}-01-01T00:00:00Z" for i in range(8)],
        }
    )
    tipo = pd.Series({"o/r0": "biblioteca/framework"})
    factors = build_factors(repos, tipo)
    assert list(factors.columns) == ["linguagem", "estrelas", "contribuidores", "idade", "tipo_projeto"]
    assert factors.loc["o/r0", "tipo_projeto"] == "biblioteca/framework"
    assert pd.isna(factors.loc["o/r1", "tipo_projeto"])
    assert "tipo_projeto" not in build_factors(repos).columns


# ------------------------------------------------------------- comparação de grupos

def test_compare_groups_kruskal_wallis_matches_hand_calculation():
    # grupos 1-3, 4-6, 7-9: somas de postos 6, 15, 24 → H = 7,2 e ε² = 7,2 / 8 = 0,9
    values = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9], dtype=float)
    groups = pd.Series(["a"] * 3 + ["b"] * 3 + ["c"] * 3)
    result = compare_groups(values, groups)
    assert result["teste"] == "Kruskal-Wallis"
    assert result["estatistica"] == pytest.approx(7.2)
    assert result["efeito"] == pytest.approx(0.9)
    assert result["magnitude"] == "grande"
    assert result["n"] == 9 and result["grupos"] == 3


def test_compare_groups_two_groups_uses_mann_whitney_and_cliffs_delta():
    values = pd.Series([1, 2, 3, 4, 5, 6], dtype=float)
    groups = pd.Series(["a", "a", "a", "b", "b", "b"])
    result = compare_groups(values, groups)
    assert result["teste"] == "Mann-Whitney"
    assert result["efeito_tipo"] == "Cliff's delta"
    assert result["efeito"] == pytest.approx(-1.0)


def test_compare_groups_needs_at_least_two_groups():
    values = pd.Series([1.0, 2.0, 3.0])
    assert compare_groups(values, pd.Series(["a", "a", "a"])) is None


def test_compare_groups_ignores_missing_values_and_singleton_groups():
    values = pd.Series([1, 2, 3, 4, 5, np.nan, 99], dtype=float)
    groups = pd.Series(["a", "a", "a", "b", "b", "b", "c"])  # "c" tem 1 observação
    result = compare_groups(values, groups)
    assert result["grupos"] == 2 and result["n"] == 5


# --------------------------------------------------------------------- RQ 05/06

def _synthetic(n=40, seed=0):
    rng = np.random.default_rng(seed)
    names = [f"o/r{i}" for i in range(n)]
    metrics = pd.DataFrame(
        {
            "deployment_frequency": rng.uniform(0.1, 20, n),
            "lead_time_release_h": rng.uniform(1, 500, n),
            "lead_time_commit_h": rng.uniform(1, 500, n),
            "cfr_ci": rng.uniform(0, 1, n),
            "cfr_delivery": rng.uniform(0, 1, n),
            "recovery_h": rng.uniform(1, 100, n),
        },
        index=names,
    )
    factors = pd.DataFrame(
        {"grupo_a": ["x", "y"] * (n // 2), "grupo_b": ["p", "q", "r", "s"] * (n // 4)},
        index=names,
    )
    return metrics, factors


def test_run_rq05_reports_both_variants():
    metrics, _ = _synthetic()
    metrics["cfr_ci"] = metrics["deployment_frequency"]  # relação monotônica perfeita
    table = run_rq05(metrics)
    assert table["variante"].tolist() == ["(a) CFR de CI", "(b) CFR de entrega"]
    assert table.loc[0, "rho"] == pytest.approx(1.0)
    assert (table["n"] == 40).all()


def test_run_rq06_applies_holm_correction_to_every_test():
    metrics, factors = _synthetic()
    table = run_rq06(metrics, factors)
    assert len(table) == 2 * 6  # 2 fatores × 6 métricas
    expected = multipletests(table["p"], method="holm")[1]
    assert table["p_holm"].to_numpy() == pytest.approx(expected)
    assert (table["p_holm"] >= table["p"]).all()
    assert (table["p_holm"] <= 1).all()
    assert set(table["teste"]) == {"Mann-Whitney", "Kruskal-Wallis"}
    assert table["efeito"].notna().all()


def test_plot_rq05_writes_png(tmp_path):
    pytest.importorskip("matplotlib")
    metrics, _ = _synthetic()
    target = tmp_path / "saida" / "dispersao.png"
    plot_rq05(metrics, run_rq05(metrics), target)
    assert target.exists() and target.stat().st_size > 0


def test_plot_rq06_effects_writes_png(tmp_path):
    pytest.importorskip("matplotlib")
    metrics, factors = _synthetic()
    table = run_rq06(metrics, factors)
    target = tmp_path / "efeitos.png"
    plot_rq06_effects(table, METRICS, target)
    assert target.exists() and target.stat().st_size > 0


def test_plot_rq06_distributions_only_for_significant_tests(tmp_path):
    pytest.importorskip("matplotlib")
    metrics, factors = _synthetic()
    table = run_rq06(metrics, factors)

    none_significant = table.assign(significativo_holm=False)
    target = tmp_path / "nenhum.png"
    assert plot_rq06_distributions(metrics, factors, none_significant, METRICS, target) is False
    assert not target.exists()

    some_significant = table.assign(significativo_holm=True)
    target = tmp_path / "distribuicoes.png"
    assert plot_rq06_distributions(metrics, factors, some_significant, METRICS, target) is True
    assert target.exists() and target.stat().st_size > 0


def test_ordered_groups_keeps_quartile_order_and_sorts_others_by_median():
    values = pd.Series([5.0, 6.0, 1.0, 2.0, 9.0, 9.5])
    quartiles = pd.Series(["Q3", "Q3", "Q1", "Q1", "Q2", "Q2"])
    assert _ordered_groups(values, quartiles) == ["Q1", "Q2", "Q3"]
    languages = pd.Series(["Go", "Go", "C++", "C++", "Rust", "Rust"])
    assert _ordered_groups(values, languages) == ["C++", "Go", "Rust"]  # medianas 1,5 < 5,5 < 9,25


def test_p_value_formatting_uses_decimal_comma_and_scientific_notation():
    assert _p(0.0076) == "0,008"
    assert _p(8.29e-19) == "8,3 × 10⁻¹⁹"
