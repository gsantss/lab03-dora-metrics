"""RQ 05 e RQ 06 (Lab03S03, parte B).

Reexecutável a partir dos CSVs finais:

    python -m analises.rq05_rq06

RQ 05: correlação de Spearman entre frequência de deploy e CFR (a) e (b).
RQ 06: fatores × métricas DORA, com Kruskal-Wallis (ou Mann-Whitney para dois grupos),
correção de Holm e tamanho de efeito (ε² e Cliff's delta).
"""
from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from analises.figuras import plot_rq05, plot_rq06_distributions, plot_rq06_effects

WINDOW_END = pd.Timestamp("2026-09-30", tz="UTC")
MIN_LANGUAGE_REPOS = 10  # linguagens com menos repositórios viram "Outras"

METRICS = {
    "deployment_frequency": "Frequência de deploy (releases/semana)",
    "lead_time_release_h": "Lead time (a) por release (h)",
    "lead_time_commit_h": "Lead time (b) por commit (h)",
    "cfr_ci": "CFR (a) proxy de CI",
    "cfr_delivery": "CFR (b) proxy de entrega",
    "recovery_h": "Tempo de recuperação (h)",
}


# ---------------------------------------------------------------- estatística

def spearman(x: pd.Series, y: pd.Series) -> dict:
    """Spearman entre x e y, descartando pares com valor ausente."""
    pair = pd.concat([x, y], axis=1).dropna()
    if len(pair) < 3:
        return {"rho": np.nan, "p": np.nan, "n": len(pair)}
    rho, p = stats.spearmanr(pair.iloc[:, 0], pair.iloc[:, 1])
    return {"rho": float(rho), "p": float(p), "n": int(len(pair))}


def cliffs_delta(x, y) -> float:
    """δ = 2·U1/(n1·n2) − 1, com U1 de mannwhitneyu(x, y)."""
    u1 = stats.mannwhitneyu(x, y, alternative="two-sided").statistic
    return float(2 * u1 / (len(x) * len(y)) - 1)


def cliffs_magnitude(delta: float) -> str:
    """Romano et al. (2006)."""
    d = abs(delta)
    if d < 0.147:
        return "desprezível"
    if d < 0.33:
        return "pequeno"
    if d < 0.474:
        return "médio"
    return "grande"


def epsilon_squared(h: float, n: int) -> float:
    """ε² = H / (n − 1)."""
    return float(h / (n - 1))


def epsilon_magnitude(eps: float) -> str:
    """Faixas de ε² adotadas pelo grupo (convenção, sem fonte única): <0,01 desprezível; <0,04 pequeno; <0,16 médio; resto grande."""
    if eps < 0.01:
        return "desprezível"
    if eps < 0.04:
        return "pequeno"
    if eps < 0.16:
        return "médio"
    return "grande"


# --------------------------------------------------------------------- fatores

def quartile_groups(values: pd.Series) -> pd.Series:
    """Converte um fator numérico em quartis (Q1..Q4); empates na borda podem reduzir os grupos."""
    bins = pd.qcut(values, q=4, duplicates="drop")
    labels = {interval: f"Q{i + 1}" for i, interval in enumerate(bins.cat.categories)}
    return bins.map(labels).astype(object).where(values.notna())


def collapse_small_languages(language: pd.Series, minimum: int = MIN_LANGUAGE_REPOS) -> pd.Series:
    counts = language.value_counts()
    keep = set(counts[counts >= minimum].index)
    return language.where(language.isin(keep), "Outras")


def build_factors(repos: pd.DataFrame, tipo: pd.Series | None = None) -> pd.DataFrame:
    """Uma coluna por fator, indexada por full_name."""
    age_days = (WINDOW_END - pd.to_datetime(repos["created_at"], utc=True)).dt.days
    factors = pd.DataFrame(
        {
            "linguagem": collapse_small_languages(repos["language"].fillna("Sem linguagem")),
            "estrelas": quartile_groups(repos["stars"]),
            "contribuidores": quartile_groups(repos["contributors"]),
            "idade": quartile_groups(age_days),
        }
    )
    factors.index = repos["full_name"]
    if tipo is not None:
        factors["tipo_projeto"] = tipo.reindex(factors.index)
    return factors


# ---------------------------------------------------------------------- testes

def compare_groups(values: pd.Series, groups: pd.Series) -> dict | None:
    """Kruskal-Wallis (≥3 grupos) ou Mann-Whitney (2 grupos), com tamanho de efeito."""
    frame = pd.DataFrame({"v": values, "g": groups}).dropna()
    samples = {g: s["v"].to_numpy() for g, s in frame.groupby("g") if len(s) >= 2}
    if len(samples) < 2:
        return None
    n = int(sum(len(s) for s in samples.values()))
    if len(samples) == 2:
        a, b = (samples[k] for k in sorted(samples))
        result = stats.mannwhitneyu(a, b, alternative="two-sided")
        delta = cliffs_delta(a, b)
        return {
            "teste": "Mann-Whitney", "grupos": 2, "n": n,
            "estatistica": float(result.statistic), "p": float(result.pvalue),
            "efeito_tipo": "Cliff's delta", "efeito": delta,
            "magnitude": cliffs_magnitude(delta),
        }
    h, p = stats.kruskal(*samples.values())
    eps = epsilon_squared(h, n)
    return {
        "teste": "Kruskal-Wallis", "grupos": len(samples), "n": n,
        "estatistica": float(h), "p": float(p),
        "efeito_tipo": "epsilon²", "efeito": eps, "magnitude": epsilon_magnitude(eps),
    }


def run_rq06(metrics: pd.DataFrame, factors: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    rows = []
    for factor, metric in product(factors.columns, METRICS):
        result = compare_groups(metrics[metric], factors[factor])
        if result is not None:
            rows.append({"fator": factor, "metrica": metric, **result})
    table = pd.DataFrame(rows)
    reject, p_holm, _, _ = multipletests(table["p"], alpha=alpha, method="holm")
    table["p_holm"] = p_holm
    table["significativo_holm"] = reject
    return table


def run_rq05(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for variant, column in (("(a) CFR de CI", "cfr_ci"), ("(b) CFR de entrega", "cfr_delivery")):
        rows.append({"variante": variant, **spearman(metrics["deployment_frequency"], metrics[column])})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------ CLI

def load_tipo(consenso_path: Path) -> pd.Series | None:
    if not consenso_path.exists():
        return None
    df = pd.read_csv(consenso_path, encoding="utf-8-sig")
    return df.drop_duplicates("full_name").set_index("full_name")["tipo_projeto"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", default="data/processed/metrics.csv")
    parser.add_argument("--repositories", default="data/processed/repositories.csv")
    parser.add_argument("--consenso", default="validacao/consenso.csv")
    parser.add_argument("--out", default="analises/resultados")
    args = parser.parse_args()

    metrics = pd.read_csv(args.metrics).set_index("full_name")
    repos = pd.read_csv(args.repositories)
    factors = build_factors(repos, load_tipo(Path(args.consenso)))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rq05 = run_rq05(metrics)
    rq05.to_csv(out / "rq05_spearman.csv", index=False)
    plot_rq05(metrics, rq05, out / "rq05_dispersao.png")
    plot_rq05(metrics, rq05, out / "rq05_dispersao_compacta.png", compacto=True)  # versão para o artigo

    rq06 = run_rq06(metrics, factors)
    rq06.to_csv(out / "rq06_testes.csv", index=False)
    plot_rq06_effects(rq06, METRICS, out / "rq06_efeitos.png")
    plot_rq06_effects(rq06, METRICS, out / "rq06_efeitos_significativos.png", apenas_significativos=True)  # artigo
    plot_rq06_distributions(metrics, factors, rq06, METRICS, out / "rq06_distribuicoes.png")

    print(rq05.round(4).to_string(index=False))
    print(f"\nRQ 06: {len(rq06)} testes; {int(rq06['significativo_holm'].sum())} significativos após Holm")
    top = rq06.sort_values("p_holm").head(10)
    print(top[["fator", "metrica", "teste", "n", "p_holm", "efeito", "magnitude"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
