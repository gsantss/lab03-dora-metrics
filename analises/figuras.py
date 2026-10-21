"""Figuras das RQ 05 e RQ 06.

Escolhas de forma (com a fonte em docs/resultados-rq05-rq06.md):
- RQ 05: dispersão (eixo x em log) com tendência LOWESS e, abaixo, mediana e IQR por quartil
  de frequência, que é o resumo que o enunciado pede (mediana e IQR, não média).
- RQ 06 (efeitos): gráfico de pontos de Cleveland com o tamanho de efeito dos 30 testes.
- RQ 06 (distribuições): caixa (mediana e IQR) com os pontos brutos de cada repositório
  (Weissgerber et al., 2015; Allen et al., 2019), para os testes significativos após Holm.

Cores: um único azul para dados de uma só série; cinza para o que não é significativo.
Nenhuma figura usa eixo duplo, e nenhuma informação depende só da cor (círculo cheio
versus vazado para a significância).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"

FACTOR_LABELS = {
    "linguagem": "Linguagem",
    "estrelas": "Estrelas",
    "contribuidores": "Contribuidores",
    "idade": "Idade",
    "tipo_projeto": "Tipo do projeto",
}

# métricas em que o eixo logarítmico faz sentido (positivas e muito assimétricas)
LOG_METRICS = {"deployment_frequency", "lead_time_release_h", "lead_time_commit_h", "recovery_h"}

# limites de ε² (Rea e Parker) usados para classificar o tamanho de efeito
EPSILON_LIMITS = ((0.01, "desprezível | pequeno"), (0.04, "pequeno | médio"), (0.16, "médio | grande"))


def _rc() -> dict:
    return {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.axisbelow": True,
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "normal",
        "axes.titlelocation": "left",
        "legend.frameon": False,
    }


def _pyplot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _num(value: float, digits: int = 2) -> str:
    """Número com vírgula decimal, como no artigo."""
    return f"{value:.{digits}f}".replace(".", ",")


def _p(value: float) -> str:
    if value < 0.001:
        mantissa, exponent = f"{value:.1e}".split("e")
        return f"{mantissa.replace('.', ',')} × 10{_superscript(int(exponent))}"
    return _num(value, 3)


def _superscript(exponent: int) -> str:
    table = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
    return str(exponent).translate(table)


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")


# ---------------------------------------------------------------------- RQ 05

def plot_rq05(metrics: pd.DataFrame, rq05: pd.DataFrame, path: Path) -> None:
    """Dispersão + tendência (linha de cima) e mediana/IQR por quartil de frequência (embaixo)."""
    from statsmodels.nonparametric.smoothers_lowess import lowess

    plt = _pyplot()
    panels = (
        ("cfr_ci", "CFR (a): proxy de CI", "(a) CFR de CI"),
        ("cfr_delivery", "CFR (b): proxy de entrega", "(b) CFR de entrega"),
    )
    with plt.rc_context(_rc()):
        fig, axes = plt.subplots(
            2, 2, figsize=(10, 7.4), gridspec_kw={"height_ratios": [3, 2], "hspace": 0.38, "wspace": 0.18}
        )
        for col, (column, title, variant) in enumerate(panels):
            pair = metrics[["deployment_frequency", column]].dropna()
            x, y = pair["deployment_frequency"], pair[column]

            ax = axes[0, col]
            ax.scatter(x, y, s=22, color=BLUE, alpha=0.45, linewidths=0, label="Repositório")
            trend = lowess(y, np.log10(x), frac=0.6, return_sorted=True)
            ax.plot(10 ** trend[:, 0], trend[:, 1], color=INK_2, linewidth=2, label="Tendência (LOWESS)")
            ax.set_xscale("log")
            ax.set_ylim(-0.03, max(1.0, float(y.max()) * 1.05))
            ax.grid(True, axis="y")
            row = rq05.loc[rq05["variante"] == variant].iloc[0]
            ax.set_title(f"{title}\nρ = {_num(row['rho'])}  ·  p = {_p(row['p'])}  ·  n = {int(row['n'])}")
            ax.set_xlabel("Frequência de deploy (releases por semana, escala log)")
            if col == 0:
                ax.set_ylabel("Taxa de falha")

            # mediana e IQR por quartil de frequência
            ax2 = axes[1, col]
            bins = pd.qcut(x, q=4, duplicates="drop")
            groups = [y[bins == interval].to_numpy() for interval in bins.cat.categories]
            labels = [
                f"Q{i + 1}\n{interval.left:.2f}–{interval.right:.2f}".replace(".", ",")
                for i, interval in enumerate(bins.cat.categories)
            ]
            ax2.boxplot(
                groups, tick_labels=labels, showfliers=False, widths=0.5,
                boxprops={"color": INK_2, "linewidth": 1.2},
                whiskerprops={"color": INK_2, "linewidth": 1.2},
                capprops={"color": INK_2, "linewidth": 1.2},
                medianprops={"color": BLUE, "linewidth": 2.4},
            )
            ax2.grid(True, axis="y")
            ax2.set_xlabel("Quartil da frequência de deploy (releases por semana)")
            if col == 0:
                ax2.set_ylabel("Taxa de falha")
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.955), ncol=2)
        fig.text(
            0.01, 0.005,
            "Embaixo: caixa = IQR, linha azul = mediana, bigodes = 1,5 × IQR (pontos fora dos bigodes omitidos).",
            color=MUTED, fontsize=8,
        )
        _save(fig, path)
        plt.close(fig)


# ---------------------------------------------------------------------- RQ 06

def _test_label(row: pd.Series, metric_labels: dict) -> str:
    return f"{FACTOR_LABELS.get(row['fator'], row['fator'])} × {metric_labels.get(row['metrica'], row['metrica'])}"


def plot_rq06_effects(table: pd.DataFrame, metric_labels: dict, path: Path) -> None:
    """Gráfico de pontos de Cleveland: tamanho de efeito de cada um dos testes, ordenado."""
    plt = _pyplot()
    data = table.assign(magnitude_abs=table["efeito"].abs()).sort_values("magnitude_abs").reset_index(drop=True)
    with plt.rc_context(_rc()):
        fig, ax = plt.subplots(figsize=(8.6, 0.28 * len(data) + 1.8))
        y = np.arange(len(data))
        ax.hlines(y, 0, data["magnitude_abs"], color=GRID, linewidth=0.8, zorder=1)
        significant = data["significativo_holm"].to_numpy(dtype=bool)
        ax.scatter(
            data.loc[significant, "magnitude_abs"], y[significant], s=46, color=BLUE, zorder=3,
            label="Significativo após Holm",
        )
        ax.scatter(
            data.loc[~significant, "magnitude_abs"], y[~significant], s=46, facecolor=SURFACE,
            edgecolor=MUTED, linewidth=1.4, zorder=3, label="Não significativo",
        )
        for limit, _ in EPSILON_LIMITS:
            ax.axvline(limit, color=AXIS, linewidth=0.8, zorder=0)
        ax.set_yticks(y)
        ax.set_yticklabels([_test_label(row, metric_labels) for _, row in data.iterrows()])
        ax.set_xlim(0, float(data["magnitude_abs"].max()) * 1.12)
        ax.set_ylim(-0.8, len(data) - 0.2)
        ax.set_xlabel(
            "Tamanho de efeito (ε² de Kruskal-Wallis; |δ| de Cliff para dois grupos)\n"
            "Linhas verticais em 0,01, 0,04 e 0,16: limites entre desprezível, pequeno, médio e grande"
        )
        ax.set_title(f"Tamanho de efeito dos {len(data)} testes da RQ 06")
        ax.grid(True, axis="x")
        ax.legend(loc="lower right")
        _save(fig, path)
        plt.close(fig)


def _ordered_groups(values: pd.Series, groups: pd.Series) -> list[str]:
    names = [g for g in groups.dropna().unique()]
    if all(re.fullmatch(r"Q\d", str(g)) for g in names):
        return sorted(names)
    medians = values.groupby(groups).median()
    return sorted(names, key=lambda g: medians.get(g, np.inf))


def plot_rq06_distributions(
    metrics: pd.DataFrame, factors: pd.DataFrame, table: pd.DataFrame, metric_labels: dict, path: Path
) -> bool:
    """Caixa (mediana e IQR) com os pontos brutos, para os testes significativos após Holm.

    Devolve False (sem gerar arquivo) quando nenhum teste é significativo.
    """
    chosen = table[table["significativo_holm"]].sort_values("p_holm").reset_index(drop=True)
    if chosen.empty:
        return False

    plt = _pyplot()
    rng = np.random.default_rng(42)
    ncols = 2
    nrows = int(np.ceil(len(chosen) / ncols))
    with plt.rc_context(_rc()):
        fig, axes = plt.subplots(nrows, ncols, figsize=(11, 3.1 * nrows), squeeze=False)
        for ax in axes.flat[len(chosen):]:
            ax.set_visible(False)
        for ax, (_, row) in zip(axes.flat, chosen.iterrows()):
            values, groups = metrics[row["metrica"]], factors[row["fator"]]
            frame = pd.DataFrame({"v": values, "g": groups}).dropna()
            order = _ordered_groups(frame["v"], frame["g"])
            for i, name in enumerate(order):
                v = frame.loc[frame["g"] == name, "v"].to_numpy()
                ax.scatter(
                    i + rng.uniform(-0.18, 0.18, len(v)), v, s=11, color=BLUE, alpha=0.35, linewidths=0, zorder=2
                )
            ax.boxplot(
                [frame.loc[frame["g"] == name, "v"].to_numpy() for name in order],
                positions=range(len(order)), showfliers=False, widths=0.5, manage_ticks=False,
                boxprops={"color": INK_2, "linewidth": 1.2}, whiskerprops={"color": INK_2, "linewidth": 1.2},
                capprops={"color": INK_2, "linewidth": 1.2}, medianprops={"color": INK, "linewidth": 2.2},
            )
            counts = frame["g"].value_counts()
            ax.set_xticks(range(len(order)))
            ax.set_xticklabels([f"{name}\nn = {counts[name]}" for name in order])
            if row["metrica"] in LOG_METRICS:
                ax.set_yscale("log")
            ax.grid(True, axis="y")
            ax.set_title(
                f"{_test_label(row, metric_labels)}\n"
                f"ε² = {_num(abs(row['efeito']), 3)} ({row['magnitude']})  ·  p Holm = {_p(row['p_holm'])}",
                fontsize=9,
            )
        fig.text(
            0.01, 0.0,
            "Caixa = IQR, linha escura = mediana, bigodes = 1,5 × IQR; pontos = repositórios. "
            "Quartis: Q1 = menor valor do fator. Escala logarítmica nas métricas de tempo e de frequência.",
            color=MUTED, fontsize=8,
        )
        fig.tight_layout(rect=(0, 0.015, 1, 1))
        _save(fig, path)
        plt.close(fig)
    return True
