"""RQ 01--04 e C1, somente a partir de metrics.csv (Issue #42).

python -m analises.rq01_04
python analises/rq01_04.py --metrics data/processed/metrics.csv --out analises/resultados/rq01_04

Uma observação por repositório. IQR = Q3-Q1, quantis por interpolação linear.
As categorias C1 são as colunas congeladas no CSV; não são recalibradas.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import PIL
import scipy
from scipy.stats import spearmanr

METRICS = {
    "deployment_frequency": ("RQ01", "Frequência de publicação", "releases/semana"),
    "lead_time_release_h": ("RQ02", "Lead time (a), por release", "h"),
    "lead_time_commit_h": ("RQ02", "Lead time (b), por commit", "h"),
    "cfr_ci": ("RQ03", "CFR (a), proxy de CI", "proporção"),
    "cfr_delivery": ("RQ03", "CFR (b), proxy de entrega", "proporção"),
    "recovery_h": ("RQ04", "Recuperação de CI", "h"),
    "recovery_censored_ratio": ("RQ04", "Episódios censurados por repositório", "proporção"),
}
CLASS_COLUMNS = {
    "class_deployment_frequency": "Frequência",
    "class_lead_time": "Lead time (a)",
    "class_cfr": "CFR (a)",
    "class_recovery": "Recuperação",
    "class_overall": "Geral C1",
}
CATEGORIES = ("Elite", "High", "Medium", "Low", "Sem classificação")
COUNTS = ("recovery_episodes", "recovery_censored")
REQUIRED = ("full_name", *METRICS, *COUNTS, *CLASS_COLUMNS)
BLUE = "#2766a2"


def load_metrics(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError("Colunas ausentes: " + ", ".join(sorted(missing)))
    if frame.empty:
        raise ValueError("metrics.csv está vazio")
    frame["full_name"] = frame["full_name"].str.strip()
    if frame.full_name.eq("").any() or frame.full_name.duplicated().any():
        raise ValueError("full_name vazio ou duplicado; a unidade deve ser um repositório")
    for column in (*METRICS, *COUNTS):
        raw = frame[column].str.strip()
        values = pd.to_numeric(raw.mask(raw.eq("")), errors="coerce")
        if (raw.ne("") & values.isna()).any() or np.isinf(values).any():
            raise ValueError(f"{column}: número inválido ou infinito")
        if (values.dropna() < 0).any():
            raise ValueError(f"{column}: valor negativo")
        if column in ("cfr_ci", "cfr_delivery", "recovery_censored_ratio") and (values.dropna() > 1).any():
            raise ValueError(f"{column}: proporção fora de [0,1]")
        if column in COUNTS and (values.isna().any() or (values % 1 != 0).any()):
            raise ValueError(f"{column}: contagem deve ser inteira e preenchida")
        frame[column] = values
    if (frame.recovery_censored > frame.recovery_episodes).any():
        raise ValueError("Episódios censurados excedem o total")
    expected = frame.recovery_censored / frame.recovery_episodes.replace(0, np.nan)
    actual = frame.recovery_censored_ratio
    if not np.array_equal(expected.isna(), actual.isna()) or not np.allclose(expected.dropna(), actual.dropna(), atol=0.00000051, rtol=0):
        raise ValueError("Proporção de censura inconsistente com as contagens")
    for column in CLASS_COLUMNS:
        frame[column] = frame[column].str.strip()
        if not frame[column].isin(("", *CATEGORIES[:4])).all():
            raise ValueError(f"{column}: categoria C1 desconhecida")
    return frame.sort_values("full_name", kind="stable").reset_index(drop=True)


def describe(values: pd.Series) -> dict:
    clean = values.dropna().astype(float)
    q = clean.quantile([0.25, 0.5, 0.75, 0.9], interpolation="linear")
    return {"n": int(len(clean)), "ausentes": int(values.isna().sum()),
            "min": float(clean.min()), "q1": float(q.loc[0.25]),
            "mediana": float(q.loc[0.5]), "q3": float(q.loc[0.75]),
            "iqr": float(q.loc[0.75] - q.loc[0.25]), "p90": float(q.loc[0.9]),
            "max": float(clean.max())}


def descriptive_table(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{"rq": rq, "metrica": key, "descricao": label,
                          "unidade": unit, **describe(frame[key])}
                         for key, (rq, label, unit) in METRICS.items()])


def category_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, label in CLASS_COLUMNS.items():
        counts = frame[key].replace("", CATEGORIES[-1]).value_counts()
        for category in CATEGORIES:
            count = int(counts.get(category, 0))
            rows.append({"coluna": key, "metrica": label, "categoria": category,
                         "n": count, "total": len(frame), "percentual": 100 * count / len(frame)})
    return pd.DataFrame(rows)


def paired_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rq, a, b in (("RQ02", "lead_time_release_h", "lead_time_commit_h"),
                     ("RQ03", "cfr_ci", "cfr_delivery")):
        pair = frame[[a, b]].dropna()
        correlation = float("nan")
        pvalue = float("nan")
        if len(pair) >= 3 and pair[a].nunique() > 1 and pair[b].nunique() > 1:
            correlation, pvalue = map(float, spearmanr(pair[a], pair[b]))
        delta = pair[a] - pair[b]
        rows.append({"rq": rq, "a": a, "b": b, "n_pares": len(pair),
                     "a_maior_b": int((delta > 0).sum()), "a_igual_b": int((delta == 0).sum()),
                     "a_menor_b": int((delta < 0).sum()),
                     "mediana_diferenca_a_menos_b": float(delta.median()),
                     "rho_spearman": correlation, "p_spearman_exploratorio": pvalue})
    return pd.DataFrame(rows)


def censorship(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    table = frame[["full_name", "recovery_h", *COUNTS, "recovery_censored_ratio"]].copy()
    table["episodios_observados"] = table.recovery_episodes - table.recovery_censored
    table["estado"] = np.select(
        [table.recovery_episodes.eq(0), table.episodios_observados.eq(0)],
        ["sem episodios", "somente censurados"], default="com recuperacao observada")
    episodes = int(table.recovery_episodes.sum())
    censored = int(table.recovery_censored.sum())
    return table, {"episodios_total": episodes, "episodios_censurados": censored,
                   "fracao_ponderada_por_episodios": censored / episodes if episodes else None,
                   "repositorios_sem_episodios": int(table.recovery_episodes.eq(0).sum()),
                   "repositorios_so_censurados": int(table.estado.eq("somente censurados").sum()),
                   "repositorios_com_censura": int(table.recovery_censored.gt(0).sum())}


def axis_scale(ax, series: list[pd.Series], axis="x") -> str:
    values = pd.concat(series).dropna().to_numpy(dtype=float)
    positive = values[values > 0]
    scale = "linear"
    if len(positive) and positive.max() / positive.min() >= 100:
        scale = "symlog" if (values == 0).any() else "log"
        options = {"linthresh": float(positive.min())} if scale == "symlog" else {}
        getattr(ax, f"set_{axis}scale")(scale, **options)
    return scale


def ecdf(ax, values: pd.Series, label: str, use_log: bool = False):
    clean = np.sort(values.dropna().to_numpy(dtype=float))
    if not len(clean):
        ax.text(0.5, 0.5, "Sem observações válidas", ha="center", transform=ax.transAxes)
    else:
        ax.step(clean, np.arange(1, len(clean) + 1) / len(clean), where="post", color=BLUE)
    scale = axis_scale(ax, [values]) if use_log else "linear"
    ax.set_xlabel(label + (f" — escala {scale}" if scale != "linear" else ""))
    ax.set_ylabel("Proporção acumulada de repositórios")
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.2)


def boxes(ax, values: list[pd.Series], labels: list[str], xlabel: str, use_log: bool):
    keep = [(i + 1, s.dropna().to_numpy(dtype=float)) for i, s in enumerate(values) if s.notna().any()]
    if keep:
        ax.boxplot([v for _, v in keep], positions=[i for i, _ in keep], orientation="horizontal",
                   widths=0.45, medianprops={"color": "#b34324", "linewidth": 1.8},
                   flierprops={"marker": ".", "markersize": 3})
    else:
        ax.text(0.5, 0.5, "Sem observações válidas", ha="center", transform=ax.transAxes)
    ax.set_yticks(range(1, len(labels) + 1), labels)
    scale = axis_scale(ax, values) if use_log else "linear"
    ax.set_xlabel(xlabel + (f" — escala {scale}" if scale != "linear" else ""))
    ax.grid(axis="x", alpha=0.2)


def plots(frame: pd.DataFrame, categories: pd.DataFrame, output: Path) -> dict[str, str]:
    """Fontes e metadados fixos: PNGs determinísticos no mesmo ambiente."""
    output.mkdir(parents=True, exist_ok=True)
    scales = {}
    def save(fig, name):
        fig.savefig(output / name, dpi=140, bbox_inches="tight", pad_inches=0.12,
                    metadata={"Software": "lab03-rq01-04"})
        plt.close(fig)
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "figure.figsize": (9.5, 4.4), "figure.constrained_layout.use": True}):
        fig, axes = plt.subplots(1, 2)
        ecdf(axes[0], frame.deployment_frequency, "Releases por semana", True)
        freq = categories[categories.coluna.eq("class_deployment_frequency")]
        axes[1].bar(freq.categoria, freq.n, color=BLUE)
        axes[1].set_ylabel("Repositórios")
        axes[1].tick_params(axis="x", labelrotation=25)
        for i, n in enumerate(freq.n):
            axes[1].text(i, n, str(n), ha="center", va="bottom")
        fig.suptitle("RQ 01 — Frequência de publicação e categorias C1")
        save(fig, "rq01_frequencia.png")
        fig, ax = plt.subplots(figsize=(9.5, 3.6))
        boxes(ax, [frame.lead_time_release_h, frame.lead_time_commit_h],
              ["(a) por release", "(b) por commit"], "Lead time (h)", True)
        ax.set_title("RQ 02 — Mediana, IQR, bigodes (1,5 × IQR) e valores extremos")
        save(fig, "rq02_lead_time.png")
        fig, ax = plt.subplots(figsize=(9.5, 3.6))
        boxes(ax, [frame.cfr_ci, frame.cfr_delivery], ["(a) CI", "(b) entrega"], "CFR (proporção)", False)
        ax.set_xlim(-0.02, 1.02)
        ax.set_title("RQ 03 — Proxies diferentes: falha de pipeline e correção publicada")
        save(fig, "rq03_cfr.png")
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.3))
        ecdf(axes[0], frame.recovery_h, "Mediana da recuperação de CI (h)", True)
        ecdf(axes[1], frame.recovery_censored_ratio, "Fração censurada por repositório")
        axes[1].set_xlim(-0.02, 1.02)
        fig.suptitle("RQ 04 — Recuperações observadas e episódios censurados")
        save(fig, "rq04_recuperacao.png")
        fig, ax = plt.subplots(figsize=(10, 4.4))
        left = np.zeros(len(CLASS_COLUMNS))
        colors = ("#2766a2", "#6699be", "#adc5d5", "#dbbca0", "#dddddd")
        for cat, color in zip(CATEGORIES, colors):
            vals = np.array([float(categories[(categories.coluna.eq(k)) & (categories.categoria.eq(cat))].percentual.iloc[0]) for k in CLASS_COLUMNS])
            bars = ax.barh(list(CLASS_COLUMNS.values()), vals, left=left, color=color, label=cat,
                           hatch="//" if cat == CATEGORIES[-1] else None)
            for i, bar in enumerate(bars):
                if vals[i] >= 5:
                    ax.text(left[i] + vals[i] / 2, bar.get_y() + bar.get_height() / 2,
                            f"{vals[i]:.1f}%", ha="center", va="center", fontsize=8,
                            color="white" if cat == "Elite" else "#111111")
            left += vals
        ax.set_xlim(0, 100)
        ax.set_xlabel("Percentual de todos os repositórios (inclui ausentes)")
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=5, fontsize=8)
        ax.set_title("C1 — Releases, lead time (a), CFR (a) e recuperação de CI")
        save(fig, "c1_categorias.png")
        for key in ("deployment_frequency", "lead_time_release_h", "lead_time_commit_h", "recovery_h"):
            fig, ax = plt.subplots()
            scales[key] = axis_scale(ax, [frame[key]])
            plt.close(fig)
    return scales


def fmt(value, digits=3):
    if value is None or not math.isfinite(float(value)):
        return "não disponível"
    return f"{float(value):.{digits}f}".replace(".", ",")


def markdown_table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers),
                       *("| " + " | ".join(map(str, row)) + " |" for row in rows)])


def discussion(frame, summary, paired, censor) -> list[tuple[str, str]]:
    stats = summary.set_index("metrica")
    p2, p3 = paired.iloc[0], paired.iloc[1]
    total = len(frame)
    frequency = stats.loc["deployment_frequency"]
    medium = int(frame.class_deployment_frequency.eq("Medium").sum())
    notes = [("RQ 01 e H1", (
        f"A frequência mediana é {fmt(frequency.mediana)} releases/semana; Q1={fmt(frequency.q1)}, Q3={fmt(frequency.q3)}, "
        f"IQR={fmt(frequency.iqr)} e máximo={fmt(frequency['max'])}. "
        f"A previsão de mediana abaixo de uma release por semana {'é compatível' if frequency.mediana < 1 else 'não é compatível'} com os dados. "
        f"Medium reúne {medium}/{total} repositórios ({fmt(100 * medium / total, 1)}%); "
        f"{'há maioria absoluta nessa categoria' if medium > total / 2 else 'não há maioria absoluta nessa categoria'}. "
        "Publicações automatizadas podem afetar a cauda, mas metrics.csv não permite testar essa explicação. Release é proxy de publicação, não evidência de deploy em produção."))]
    a, b = stats.loc["lead_time_release_h"], stats.loc["lead_time_commit_h"]
    long = int(frame.lead_time_release_h.gt(720).sum())
    pair = frame[["lead_time_release_h", "lead_time_commit_h", "deployment_frequency"]].dropna()
    gap = pair.lead_time_release_h - pair.lead_time_commit_h
    gap_rho = float("nan")
    if len(pair) >= 3 and gap.nunique() > 1 and pair.deployment_frequency.nunique() > 1:
        gap_rho = float(spearmanr(pair.deployment_frequency, gap).statistic)
    notes.append(("RQ 02 e H2", (
        f"As medianas são {fmt(a.mediana)} h (a) e {fmt(b.mediana)} h (b), com IQR {fmt(a.iqr)} h e {fmt(b.iqr)} h. "
        f"Nos {int(p2.n_pares)} pares válidos, (a) supera (b) em {int(p2.a_maior_b)}, empata em {int(p2.a_igual_b)} e fica abaixo em {int(p2.a_menor_b)}; "
        f"a mediana das diferenças pareadas é {fmt(p2.mediana_diferenca_a_menos_b)} h. A diferença entre medianas não substitui essa mediana pareada. "
        f"Há {long} repositórios com (a) acima de 30 dias. A previsão de (b) na faixa High/Medium "
        f"{'é compatível' if 24 <= b.mediana < 720 else 'não é compatível'} com sua mediana. "
        f"A previsão de (a) maior {'é compatível' if a.mediana > b.mediana else 'não é compatível'} com a comparação das medianas agregadas; "
        f"{'a maioria dos pares tem (a) maior' if p2.a_maior_b > p2.n_pares / 2 else 'não há maioria de pares com (a) maior'}. "
        "A leitura de H2 precisa separar distribuição agregada e comparação pareada, sem presumir que (a) seja sempre maior: "
        "(a) calcula o tempo do commit mais antigo até a publicação e depois a mediana entre releases; "
        "(b) agrega os tempos individuais dos commits, ponderando implicitamente releases com mais commits. "
        "Essa mudança de unidade e de ponderação pode inverter a comparação em alguns repositórios. "
        f"A correlação exploratória entre frequência e diferença (a)-(b) é rho={fmt(gap_rho)}, sem demonstrar causalidade. "
        "A duração de revisão de PRs e de branches não é observável nesse CSV.")))
    a, b = stats.loc["cfr_ci"], stats.loc["cfr_delivery"]
    valid_b = frame.cfr_delivery.dropna()
    notes.append(("RQ 03 e H3", (
        f"O CFR mediano é {fmt(100 * a.mediana, 1)}% no proxy de CI e {fmt(100 * b.mediana, 1)}% no proxy de entrega; "
        f"os IQRs são {fmt(100 * a.iqr, 1)} e {fmt(100 * b.iqr, 1)} pontos percentuais. "
        f"A faixa prevista de 10%-25% para a mediana de CI {'é observada' if 0.10 <= a.mediana <= 0.25 else 'não é observada'}. "
        f"A previsão de mediana menor no proxy de entrega {'é compatível' if b.mediana < a.mediana else 'não é compatível'} com os dados. "
        f"Dos {len(valid_b)} repositórios com CFR (b) válido, {int(valid_b.lt(0.15).sum())} ficam abaixo de 15% e {int(valid_b.eq(0).sum())} têm zero. "
        f"A correlação de Spearman entre os proxies é rho={fmt(p3.rho_spearman)} em {int(p3.n_pares)} pares "
        f"(p exploratório={fmt(p3.p_spearman_exploratorio, 6)}). "
        "São construtos diferentes: CI mede execuções elegíveis com falha; entrega procura uma release corretiva em até sete dias. "
        "Uma falha de teste, lint ou dependência externa não comprova incidente em produção. Uma correção publicada pode estar ligada a mudança anterior. "
        "Releases sem sete dias completos de acompanhamento são censuradas, não tratadas como sucesso. A magnitude do rho é a evidência para a expectativa de associação fraca em H3; um p pequeno não implica correlação forte nem equivalência entre os proxies.")))
    r = stats.loc["recovery_h"]
    notes.append(("RQ 04 e H4", (
        f"A mediana entre as medianas de recuperação dos repositórios é {fmt(r.mediana)} h, com Q1={fmt(r.q1)}, Q3={fmt(r.q3)}, IQR={fmt(r.iqr)} e máximo={fmt(r['max'])} h. "
        f"A expectativa de mediana entre uma hora e um dia {'é compatível' if 1 <= r.mediana < 24 else 'não é compatível'} com o resultado. "
        f"Há {censor['repositorios_com_censura']} repositórios com algum episódio censurado, {censor['repositorios_sem_episodios']} sem episódios e "
        f"{censor['repositorios_so_censurados']} somente com episódios censurados. "
        f"No agregado ponderado por episódios, são {censor['episodios_censurados']}/{censor['episodios_total']} "
        f"({fmt(100 * censor['fracao_ponderada_por_episodios'], 2) if censor['fracao_ponderada_por_episodios'] is not None else 'não disponível'}%). "
        "Essa razão não é a mediana das proporções por repositório. A tabela de censura lista ambos os contadores e a proporção para cada repositório. "
        "O tempo considera apenas episódios recuperados no mesmo workflow; censurados são excluídos das durações e podem subestimar tempos longos. "
        "Não estimamos a distribuição de sobrevivência dos episódios a partir dessas medianas agregadas. A relação com workflows auxiliares prevista em H4 não pode ser testada apenas com metrics.csv.")))
    return notes


def tex_escape(value):
    substitutions = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(substitutions.get(c, c) for c in str(value))


def render_tex(summary, categories, notes, total):
    text = ["% Gerado por analises.rq01_04; nao editar manualmente.",
            f"A análise utiliza {total} repositórios, com peso igual por repositório. Valores ausentes são excluídos por métrica; zero é mantido. "
            "O IQR é Q3 menos Q1, com quantis por interpolação linear. A tabela mostra proporções de CFR, não percentuais.",
            r"\begin{table}[ht]\centering\small",
            r"\caption{RQ 01 a 04: estatísticas por repositório.}\label{tab:rq0104-resumo}",
            r"\begin{tabular}{lrrrrr}\hline Métrica & $n$ & Mediana & Q1 & Q3 & IQR \\ \hline"]
    short = ["Frequência (releases/semana)", "Lead time (a), h", "Lead time (b), h", "CFR (a)", "CFR (b)", "Recuperação, h", "Fração censurada por repo"]
    for label, (_, row) in zip(short, summary.iterrows()):
        text.append(tex_escape(label) + " & " + str(int(row.n)) + " & " + " & ".join(fmt(row[k]) for k in ("mediana", "q1", "q3", "iqr")) + r" \\")
    text += [r"\hline\end{tabular}\end{table}", r"\begin{table}[ht]\centering\small",
             r"\caption{Distribuição C1: contagens, incluindo ausentes.}\label{tab:rq0104-c1}",
             r"\begin{tabular}{lrrrrr}\hline Métrica & Elite & High & Medium & Low & Ausentes \\ \hline"]
    for key, label in CLASS_COLUMNS.items():
        values = categories[categories.coluna.eq(key)].n.tolist()
        text.append(tex_escape(label) + " & " + " & ".join(map(str, values)) + r" \\")
    text += [r"\hline\end{tabular}\end{table}",
             "C1 mantém as categorias de metrics.csv: releases, lead time (a), CFR (a) e recuperação de CI. "
             "A classificação geral usa a mediana das quatro notas, arredondada para baixo pelo pipeline; sem as quatro métricas, fica ausente. "
             "Essas faixas são as definições operacionais do estudo e não uma certificação de desempenho em produção."]
    for heading, body in notes:
        text.extend([r"\paragraph{" + tex_escape(heading) + "} " + tex_escape(body)])
    for name, title in (("rq01_frequencia", "Frequência de publicação e categorias C1."),
                        ("rq02_lead_time", "Lead time nas duas variantes."),
                        ("rq03_cfr", "CFR de CI e de entrega."),
                        ("rq04_recuperacao", "Recuperação observada e proporções censuradas."),
                        ("c1_categorias", "Categorias C1 por métrica e geral.")):
        text.extend([r"\begin{figure}[ht]\centering",
                     r"\includegraphics[width=\linewidth]{figuras/" + name + ".png}",
                     r"\caption{" + tex_escape(title) + r"}\label{fig:rq0104-" + name.replace("_", "-") + "}",
                     r"\end{figure}"])
    return "\n\n".join(text) + "\n"


def generate(metrics: Path, out: Path, article: Path | None = None, docs: Path | None = None):
    frame = load_metrics(metrics)
    summary = descriptive_table(frame)
    categories = category_table(frame)
    paired = paired_table(frame)
    per_repo, censor = censorship(frame)
    out.mkdir(parents=True, exist_ok=True)
    tables = {"estatisticas.csv": summary, "categorias_c1.csv": categories,
              "comparacoes_pareadas.csv": paired, "censura_por_repositorio.csv": per_repo}
    for name, table in tables.items():
        table.to_csv(out / name, index=False, encoding="utf-8", float_format="%.12g", na_rep="", lineterminator="\n")
    scales = plots(frame, categories, out)
    notes = discussion(frame, summary, paired, censor)
    report = ["# RQ 01 a 04 e classificação C1", "", f"Amostra: {len(frame)} repositórios. Entrada única: metrics.csv.", "",
              "## Estatística descritiva", "",
              "Uma observação por repositório; não são medianas de todos os commits ou episódios agrupados. "
              "Q1 e Q3 usam interpolação linear; IQR = Q3-Q1. Ausentes são excluídos por métrica e não viram zero. CFR e censura estão em proporções [0,1].", "",
              markdown_table(["Métrica", "n", "Ausentes", "Mediana", "Q1", "Q3", "IQR"],
                             [[r.descricao, int(r.n), int(r.ausentes), *(fmt(r[k]) for k in ("mediana", "q1", "q3", "iqr"))] for _, r in summary.iterrows()]), "",
              "## Classificação de referência C1", "",
              "Categorias copiadas das colunas C1 do CSV. Não recalculamos limiares nem atribuímos Low a ausentes. "
              "C1: release, lead time (a), CFR (a), recuperação de CI. Geral: mediana das quatro notas, arredondada para baixo pelo pipeline; ausência de alguma métrica impede classificação geral.", "",
              markdown_table(["Métrica", *CATEGORIES],
                             [[label, *(str(int(v)) for v in categories[categories.coluna.eq(key)].n)] for key, label in CLASS_COLUMNS.items()]), "",
              "Percentuais e denominadores de todas as classes estão em categorias_c1.csv; todos os repositórios entram no denominador.", "",
              "## Resultados e discussão: H1 a H4", ""]
    for heading, body in notes:
        report += ["### " + heading, "", body, ""]
    report += ["## Reprodução", "", "```bash", "python -m analises.rq01_04", "```", "",
               "Gráficos sem aleatoriedade. Fonte DejaVu Sans e backend Agg. Escala log quando a amplitude positiva é pelo menos 100 vezes; "
               "symlog preserva zeros quando necessário. CFR e frações usam escala linear. PNGs reproduzíveis byte a byte no mesmo ambiente; "
               "versões diferentes de fontes/bibliotecas ou sistemas podem alterar pixels. O manifesto registra versões, SHA-256 da entrada e dos resultados, sem horário ou caminho absoluto.", ""]
    report_text = "\n".join(report)
    (out / "relatorio.md").write_text(report_text, encoding="utf-8", newline="\n")
    if docs:
        docs.parent.mkdir(parents=True, exist_ok=True)
        docs.write_text(report_text, encoding="utf-8", newline="\n")
    if article:
        article.mkdir(parents=True, exist_ok=True)
        (article / "resultados_rq01_04.tex").write_text(render_tex(summary, categories, notes, len(frame)), encoding="utf-8", newline="\n")
        figures = article / "figuras"
        figures.mkdir(exist_ok=True)
        for name in sorted(out.glob("*.png")):
            (figures / name.name).write_bytes(name.read_bytes())
    manifest = {"schema": 1, "input_sha256": hashlib.sha256(metrics.read_bytes()).hexdigest(),
                "repositories": len(frame), "quantiles": "linear", "unit": "repository",
                "versions": {"pandas": pd.__version__, "numpy": np.__version__, "matplotlib": matplotlib.__version__,
                             "scipy": scipy.__version__, "Pillow": PIL.__version__},
                "scales": scales, "censorship": censor,
                "sha256": {name.name: hashlib.sha256(name.read_bytes()).hexdigest() for name in sorted(out.iterdir())
                           if name.name in {*tables, "relatorio.md", "rq01_frequencia.png", "rq02_lead_time.png", "rq03_cfr.png", "rq04_recuperacao.png", "c1_categorias.png"}}}
    (out / "manifesto.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=Path("data/processed/metrics.csv"))
    parser.add_argument("--out", type=Path, default=Path("analises/resultados/rq01_04"))
    parser.add_argument("--artigo", type=Path, default=Path("artigo"))
    parser.add_argument("--docs", type=Path, default=Path("docs/resultados-rq01-rq04.md"))
    args = parser.parse_args()
    try:
        result = generate(args.metrics, args.out, args.artigo, args.docs)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"ERRO RQ01-04: {exc}\n")
    print(f"RQ01-04: {result['repositories']} repositórios; tabelas, cinco gráficos e artigo gerados em {args.out}.")


if __name__ == "__main__":
    main()
