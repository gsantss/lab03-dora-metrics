"""RQ 07 (sensibilidade da classificação DORA à definição operacional) e RQ 08 (rework rate).

Reexecutável a partir dos CSVs: `python -m analises.rq07 --config config.yaml`.
Entradas: `data/processed/` (metrics.csv, releases.csv, commits/) e `data/processed/variantes/`
(gerado por `python -m pipeline --config config.yaml --variants`).
"""
from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, quantiles

import yaml
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score

from metricas import (
    cfr_delivery,
    classify_cfr,
    classify_deployment_frequency,
    classify_lead_time,
    classify_recovery,
    deployment_frequency,
    is_corrective_release,
    median_lead_time_commits,
    overall_classification,
)
from pipeline.dataset import grouped_by_repository, repository_rows
from pipeline.selection import write_csv

SCORE = {"Elite": 4, "High": 3, "Medium": 2, "Low": 1}
METRICS = ("deployment_frequency", "lead_time", "cfr", "recovery")
PAIRS = (("C1", "C2"), ("C1", "C3"), ("C2", "C3"))
# Combinações da RQ 07 (enunciado, seção 5): unidade de deploy, lead time, CFR.
COMBINATIONS = {
    "C1": "release · lead time (a) · CFR (a)",
    "C2": "release + pré-release · lead time (b) · CFR (b)",
    "C3": "tag · lead time (b) · CFR (a)",
}


def _float(value: str) -> float | None:
    return float(value) if value not in (None, "") else None


def classify(frequency: float, lead_time: float | None, failure_rate: float | None, recovery: float | None) -> dict:
    classes = {
        "deployment_frequency": classify_deployment_frequency(frequency),
        "lead_time": classify_lead_time(lead_time) if lead_time is not None else None,
        "cfr": classify_cfr(failure_rate) if failure_rate is not None else None,
        "recovery": classify_recovery(recovery) if recovery is not None else None,
    }
    classes["overall"] = overall_classification(classes.values()) if all(classes.values()) else None
    return classes


def c1_classes(metrics: dict) -> dict:
    """C1 é a referência já calculada em metrics.csv."""
    return {
        "deployment_frequency": metrics["class_deployment_frequency"] or None,
        "lead_time": metrics["class_lead_time"] or None,
        "cfr": metrics["class_cfr"] or None,
        "recovery": metrics["class_recovery"] or None,
        "overall": metrics["class_overall"] or None,
        "values": {
            "deployment_frequency": _float(metrics["deployment_frequency"]),
            "lead_time": _float(metrics["lead_time_release_h"]),
            "cfr": _float(metrics["cfr_ci"]),
        },
    }


def variant_classes(variant: str, units: list[dict], commits: list[dict], metrics: dict, start: datetime, end: datetime) -> dict:
    """C2 e C3 usam lead time (b); C2 usa CFR (b) das próprias unidades, C3 o CFR (a) de CI.
    O tempo de recuperação vem do CI e é o mesmo nas três combinações."""
    published = {str(u["release_id"]): u["published_at"] for u in units}
    commits = [
        {**c, "release_published_at": published[str(c["release_id"])], "commit_message": c.get("commit_message", "")}
        for c in commits
        if str(c["release_id"]) in published
    ]
    values = {
        "deployment_frequency": deployment_frequency(len(units), start, end),
        "lead_time": median_lead_time_commits(commits),
        "cfr": cfr_delivery(units, commits, end)[0] if variant == "C2" else _float(metrics["cfr_ci"]),
    }
    return {**classify(*values.values(), _float(metrics["recovery_h"])), "values": values}


def compare(classes_a: dict[str, dict], classes_b: dict[str, dict]) -> dict:
    """% de repositórios que mudam de categoria e kappa de Cohen ponderado (linear), na
    classificação geral; e a % de mudança em cada métrica. Só entram repositórios
    classificados nas duas combinações."""
    names = [n for n in classes_a if n in classes_b and classes_a[n]["overall"] and classes_b[n]["overall"]]
    a = [SCORE[classes_a[n]["overall"]] for n in names]
    b = [SCORE[classes_b[n]["overall"]] for n in names]
    changed = sum(x != y for x, y in zip(a, b))
    kappa = cohen_kappa_score(a, b, weights="linear", labels=[1, 2, 3, 4]) if names else math.nan
    result = {
        "n": len(names),
        "mudaram": changed,
        "mudaram_pct": round(100 * changed / len(names), 1) if names else None,
        "subiram": sum(y > x for x, y in zip(a, b)),  # categoria melhor na segunda combinação
        "desceram": sum(y < x for x, y in zip(a, b)),
        "vizinhas": sum(abs(x - y) == 1 for x, y in zip(a, b)),  # ex.: High <-> Medium
        "kappa_linear": None if math.isnan(kappa) else round(float(kappa), 3),
    }
    for metric in METRICS:
        pairs = [(classes_a[n][metric], classes_b[n][metric]) for n in classes_a if n in classes_b]
        pairs = [(x, y) for x, y in pairs if x and y]
        result[f"mudou_{metric}_pct"] = round(100 * sum(x != y for x, y in pairs) / len(pairs), 1) if pairs else None
    return result


def rework(releases: list[dict], commits: list[dict]) -> tuple[int, int]:
    """RQ 08: releases corretivas (heurística do CFR b) sobre o total de releases da janela."""
    messages: dict[str, list[str]] = {}
    for commit in commits:
        messages.setdefault(str(commit["release_id"]), []).append(commit["commit_message"])
    corrective = sum(
        bool(r["previous_tag"]) and is_corrective_release(r["previous_tag"], r["tag_name"], messages.get(str(r["release_id"]), []))
        for r in releases
    )
    return corrective, len(releases)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _median_iqr(values: list[float]) -> str:
    q1, _, q3 = quantiles(values, n=4)
    return f"{median(values):.3f} [{q1:.3f}, {q3:.3f}]"


def run(processed: Path, start: datetime, end: datetime, out_dir: Path) -> dict:
    with (processed / "metrics.csv").open(newline="", encoding="utf-8") as fp:
        metrics = {row["full_name"]: row for row in csv.DictReader(fp)}
    variants = processed / "variantes"
    failed = set(grouped_by_repository(variants / "errors.csv")) if (variants / "errors.csv").exists() else set()
    units = {v: grouped_by_repository(variants / f"{v.lower()}_units.csv") for v in ("C2", "C3")}
    releases = grouped_by_repository(processed / "releases.csv")

    classes: dict[str, dict[str, dict]] = {"C1": {}, "C2": {}, "C3": {}}
    rows, rework_rows = [], []
    for name, row in metrics.items():
        classes["C1"][name] = c1_classes(row)
        if name not in failed:
            for v in ("C2", "C3"):
                commits = repository_rows(variants / f"{v.lower()}_commits", name)
                classes[v][name] = variant_classes(v, units[v].get(name, []), commits, row, start, end)
        rows.append(
            {"full_name": name}
            | {f"{v}_{m}": classes[v].get(name, {}).get(m) for v in classes for m in (*METRICS, "overall")}
            | {
                f"{v}_{m}_valor": _round(classes[v].get(name, {}).get("values", {}).get(m))
                for v in classes
                for m in ("deployment_frequency", "lead_time", "cfr")
            }
        )
        corrective, total = rework(releases.get(name, []), repository_rows(processed / "commits", name))
        rework_rows.append(
            {
                "full_name": name,
                "releases": total,
                "corretivas": corrective,
                "rework_rate": round(corrective / total, 6) if total else None,
                "cfr_delivery": row["cfr_delivery"],
            }
        )

    comparisons = [{"par": f"{a}×{b}", **compare(classes[a], classes[b])} for a, b in PAIRS]
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "rq07_classificacoes.csv", rows)
    write_csv(out_dir / "rq07_comparacoes.csv", comparisons)
    write_csv(out_dir / "rq08_rework.csv", rework_rows)

    paired = [(float(r["rework_rate"]), float(r["cfr_delivery"])) for r in rework_rows if r["rework_rate"] is not None and r["cfr_delivery"]]
    rho, p_value = spearmanr([x for x, _ in paired], [y for _, y in paired])
    distribution = {
        v: {c: sum(1 for k in classes[v].values() if k["overall"] == c) for c in (*SCORE, None)} for v in classes
    }
    medians = {
        v: {
            m: _median_iqr(values)
            for m in ("deployment_frequency", "lead_time", "cfr")
            if len(values := [k["values"][m] for k in classes[v].values() if k["values"][m] is not None]) > 1
        }
        for v in classes
    }
    summary = {
        "excluidos_por_erro": sorted(failed),
        "distribuicao": distribution,
        "medianas": medians,
        "comparacoes": comparisons,
        "rework": {
            "n": len(paired),
            "rework_rate": _median_iqr([x for x, _ in paired]),
            "cfr_delivery": _median_iqr([y for _, y in paired]),
            "rework_maior_que_cfr_b": sum(x > y for x, y in paired),
            "spearman_rho": round(float(rho), 3),
            "spearman_p": float(p_value),
        },
    }
    (out_dir / "rq07_rq08_resumo.md").write_text(_markdown(summary), encoding="utf-8")
    return summary


def _markdown(summary: dict) -> str:
    lines = ["# RQ 07 e RQ 08: resultados", "", "## Distribuição da classificação geral", "",
             "| Combinação | Definição | Elite | High | Medium | Low | Sem classificação |", "|---|---|---|---|---|---|---|"]
    for v, counts in summary["distribuicao"].items():
        lines.append(f"| {v} | {COMBINATIONS[v]} | {counts['Elite']} | {counts['High']} | {counts['Medium']} | {counts['Low']} | {counts[None]} |")
    lines += ["", "## Métricas em cada combinação: mediana [IQR]", "",
              "| Combinação | Frequência (deploys/semana) | Lead time (h) | CFR |", "|---|---|---|---|"]
    for v, m in summary["medianas"].items():
        lines.append(f"| {v} | {m.get('deployment_frequency', '—')} | {m.get('lead_time', '—')} | {m.get('cfr', '—')} |")
    lines += ["", "## Comparação entre combinações", "",
              "| Par | n | Mudaram de categoria | Subiram / desceram | Entre vizinhas | Kappa ponderado (linear) | Mudou frequência | Mudou lead time | Mudou CFR | Mudou recuperação |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for c in summary["comparacoes"]:
        lines.append(
            f"| {c['par']} | {c['n']} | {c['mudaram']} ({c['mudaram_pct']}%) | {c['subiram']} / {c['desceram']} | {c['vizinhas']} | {c['kappa_linear']} "
            f"| {c['mudou_deployment_frequency_pct']}% "
            f"| {c['mudou_lead_time_pct']}% | {c['mudou_cfr_pct']}% | {c['mudou_recovery_pct']}% |"
        )
    r = summary["rework"]
    lines += ["", "## RQ 08: rework rate", "",
              f"- Repositórios: {r['n']}",
              f"- Rework rate, mediana [IQR]: {r['rework_rate']}",
              f"- CFR (b), mediana [IQR]: {r['cfr_delivery']}",
              f"- Repositórios com rework rate maior que o CFR (b): {r['rework_maior_que_cfr_b']}",
              f"- Spearman (rework × CFR b): ρ = {r['spearman_rho']}, p = {r['spearman_p']:.2e}"]
    if summary["excluidos_por_erro"]:
        lines += ["", f"Excluídos de C2 e C3 por erro de coleta: {', '.join(summary['excluidos_por_erro'])}."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m analises.rq07")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="analises/resultados")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    start = datetime.fromisoformat(str(config["window"]["start"])).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(str(config["window"]["end"])).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    summary = run(Path(config["output_dir"]), start, end, Path(args.out))
    print(_markdown(summary))


if __name__ == "__main__":
    main()
