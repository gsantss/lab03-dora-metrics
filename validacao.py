"""Avaliação da heurística de release corretiva contra a amostra-ouro (consenso).

Uso:
    python validacao.py --consenso validacao/consenso.csv \
        --releases data/processed/releases.csv --commits data/processed/commits.csv.gz

`consenso.csv` precisa das colunas `full_name`, `tag_name` e `corretiva` (sim/nao).
"""
from __future__ import annotations

import argparse
import csv
import gzip
from collections import defaultdict
from typing import Callable, Iterable

from sklearn.metrics import precision_recall_fscore_support

from metricas import FIX_MESSAGE, is_patch_bump

Heuristic = Callable[[str, str, list[str]], bool]

F1_TARGET = 0.70


def _has_fix(messages: Iterable[str]) -> bool:
    return any(FIX_MESSAGE.search(m or "") for m in messages)


def v1_patch_and_fix(previous_tag: str, tag: str, messages: list[str]) -> bool:
    return is_patch_bump(previous_tag, tag) and _has_fix(messages)


def v2_patch_or_fix(previous_tag: str, tag: str, messages: list[str]) -> bool:
    return is_patch_bump(previous_tag, tag) or _has_fix(messages)


def v3_fix_only(previous_tag: str, tag: str, messages: list[str]) -> bool:
    return _has_fix(messages)


def v4_patch_only(previous_tag: str, tag: str, messages: list[str]) -> bool:
    return is_patch_bump(previous_tag, tag)


VARIANTS: dict[str, Heuristic] = {
    "v1 patch E fix": v1_patch_and_fix,
    "v2 patch OU fix": v2_patch_or_fix,
    "v3 só fix": v3_fix_only,
    "v4 só patch": v4_patch_only,
}


def evaluate(y_true: list[int], y_pred: list[int]) -> dict[str, float | int]:
    """Precisão, recall e F1 da classe positiva (corretiva)."""
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=[1], average=None, zero_division=0
    )
    return {
        "precision": float(precision[0]),
        "recall": float(recall[0]),
        "f1": float(f1[0]),
        "n": len(y_true),
        "positives": int(sum(y_true)),
    }


def _open(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, encoding="utf-8", newline="")


def load_rows(path: str) -> list[dict]:
    with _open(path) as fp:
        return list(csv.DictReader(fp))


def build_samples(consenso: list[dict], releases: list[dict], commits: list[dict]) -> list[dict]:
    """Junta cada release rotulada com a release anterior e as mensagens de commit."""
    by_key = {(r["full_name"], r["tag_name"]): r for r in releases}
    messages: dict[object, list[str]] = defaultdict(list)
    for commit in commits:
        messages[commit["release_id"]].append(commit.get("commit_message") or "")

    samples = []
    for row in consenso:
        release = by_key.get((row["full_name"], row["tag_name"]))
        if release is None:
            continue
        samples.append(
            {
                "previous_tag": release.get("previous_tag") or "",
                "tag": release["tag_name"],
                "messages": messages.get(release["release_id"], []),
                "label": 1 if row["corretiva"].strip().lower() == "sim" else 0,
            }
        )
    return samples


def compare_variants(samples: list[dict]) -> list[dict]:
    """Tabela versão × precisão × recall × F1, com a marca de atingiu/não o alvo."""
    y_true = [s["label"] for s in samples]
    table = []
    for name, heuristic in VARIANTS.items():
        y_pred = [int(heuristic(s["previous_tag"], s["tag"], s["messages"])) for s in samples]
        result = evaluate(y_true, y_pred)
        table.append({"versao": name, **result, "atinge_alvo": result["f1"] >= F1_TARGET})
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consenso", required=True)
    parser.add_argument("--releases", default="data/processed/releases.csv")
    parser.add_argument("--commits", default="data/processed/commits.csv.gz")
    args = parser.parse_args()

    samples = build_samples(
        load_rows(args.consenso), load_rows(args.releases), load_rows(args.commits)
    )
    print(f"{len(samples)} releases rotuladas encontradas nos dados\n")
    print(f"{'versão':<18}{'precisão':>10}{'recall':>9}{'F1':>7}  alvo F1>={F1_TARGET}")
    for row in compare_variants(samples):
        print(
            f"{row['versao']:<18}{row['precision']:>10.2f}{row['recall']:>9.2f}"
            f"{row['f1']:>7.2f}  {'ok' if row['atinge_alvo'] else 'abaixo'}"
        )


if __name__ == "__main__":
    main()
