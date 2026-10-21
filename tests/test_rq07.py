import csv
from datetime import datetime, timezone

import pytest

from analises.rq07 import classify, compare, rework, run, variant_classes
from pipeline.collect import SampleWriter
from pipeline.variantes import VARIANT_OUTPUTS, VARIANT_PER_REPOSITORY

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 1, 15, tzinfo=timezone.utc)  # duas semanas


def overall(*classes):
    return {n: {"overall": c, "deployment_frequency": c, "lead_time": c, "cfr": c, "recovery": c} for n, c in classes}


def test_classify_sem_alguma_metrica_fica_sem_classificacao_geral():
    # High (3,5/semana), Elite (10 h), Elite (10%), Elite (0,5 h): mediana de (3, 4, 4, 4) = 4
    assert classify(3.5, 10.0, 0.1, 0.5)["overall"] == "Elite"
    assert classify(3.5, None, 0.1, 0.5)["overall"] is None


def test_variant_c2_usa_cfr_de_entrega_e_c3_usa_cfr_de_ci():
    units = [
        {"release_id": "1", "tag_name": "v1.0.0", "published_at": "2026-01-02T00:00:00Z"},
        {"release_id": "2", "tag_name": "v1.0.1", "published_at": "2026-01-03T00:00:00Z"},
    ]
    commits = [
        {"release_id": "2", "release_published_at": "2026-01-03T00:00:00Z", "commit_author_date": "2026-01-02T12:00:00Z", "commit_message": "fix: x"}
    ]
    metrics = {"cfr_ci": "0.5", "recovery_h": "2"}
    c2 = variant_classes("C2", units, commits, metrics, START, END)
    c3 = variant_classes("C3", units, commits, metrics, START, END)
    # v1.0.0 é corrigida pela v1.0.1 no dia seguinte: CFR (b) = 1/2 -> Low; CFR (a) = 0,5 -> Low
    assert c2["cfr"] == c3["cfr"] == "Low"
    assert c2["lead_time"] == "Elite"  # 12 h
    assert c2["deployment_frequency"] == "High"  # 1 por semana


def test_compare_conta_mudancas_e_kappa_ponderado():
    a = overall(("r1", "Elite"), ("r2", "High"), ("r3", "Medium"), ("r4", "Low"), ("r5", None))
    b = overall(("r1", "Elite"), ("r2", "High"), ("r3", "Medium"), ("r4", "Medium"), ("r5", "High"))
    result = compare(a, b)
    assert result["n"] == 4  # r5 sem classificação em a
    assert (result["mudaram"], result["mudaram_pct"]) == (1, 25.0)
    assert (result["subiram"], result["desceram"]) == (1, 0)  # r4: Low -> Medium
    assert 0 < result["kappa_linear"] < 1
    assert compare(a, a)["kappa_linear"] == 1.0


def test_rework_conta_releases_corretivas():
    releases = [
        {"release_id": "1", "tag_name": "v1.0.0", "previous_tag": ""},
        {"release_id": "2", "tag_name": "v1.0.1", "previous_tag": "v1.0.0"},
        {"release_id": "3", "tag_name": "v1.1.0", "previous_tag": "v1.0.1"},
        {"release_id": "4", "tag_name": "v1.1.1", "previous_tag": "v1.1.0"},
    ]
    commits = [
        {"release_id": "2", "commit_message": "fix: crash"},
        {"release_id": "3", "commit_message": "fix: outro"},  # minor: não é corretiva
        {"release_id": "4", "commit_message": "docs: readme"},  # patch sem fix: não é corretiva
    ]
    assert rework(releases, commits) == (1, 4)


def write_csv_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.filterwarnings("ignore")  # com um só repositório, kappa e Spearman ficam indefinidos
def test_run_gera_tabelas_a_partir_dos_csvs(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    metrics = []
    for name, cls in (("o/a", "High"), ("o/b", "Medium")):
        metrics.append(
            {"full_name": name, "deployment_frequency": "1.0", "lead_time_release_h": "12", "cfr_ci": "0.1", "recovery_h": "2",
             "cfr_delivery": "0.5", "class_deployment_frequency": cls,
             "class_lead_time": cls, "class_cfr": cls, "class_recovery": cls, "class_overall": cls}
        )
    write_csv_rows(processed / "metrics.csv", metrics)
    releases = [
        {"full_name": "o/a", "release_id": "1", "tag_name": "v1.0.0", "published_at": "2026-01-02T00:00:00Z", "previous_tag": ""},
        {"full_name": "o/a", "release_id": "2", "tag_name": "v1.0.1", "published_at": "2026-01-03T00:00:00Z", "previous_tag": "v1.0.0"},
        {"full_name": "o/b", "release_id": "3", "tag_name": "v2.0.0", "published_at": "2026-01-02T00:00:00Z", "previous_tag": ""},
    ]
    write_csv_rows(processed / "releases.csv", releases)
    commit = {"release_id": "2", "release_tag": "v1.0.1", "release_published_at": "2026-01-03T00:00:00Z",
              "commit_sha": "s", "commit_author_date": "2026-01-02T12:00:00Z", "commit_message": "fix: bug"}
    with SampleWriter(processed, {"commits": list(commit) + ["full_name"]}, {"commits"}) as writer:
        writer.write({"commits": [{"full_name": "o/a", **commit}]}, "o/a")

    units = [{**r, "prerelease": False} for r in releases if r["full_name"] == "o/a"]
    with SampleWriter(processed / "variantes", VARIANT_OUTPUTS, VARIANT_PER_REPOSITORY) as writer:
        writer.write({"c2_units": units, "c2_commits": [{"full_name": "o/a", **commit}], "c3_units": units,
                      "c3_commits": [{"full_name": "o/a", **commit}]}, "o/a")
        writer.write({"errors": [{"full_name": "o/b", "error": "RuntimeError: x"}]}, "o/b")

    out = tmp_path / "resultados"
    summary = run(processed, START, END, out)

    assert summary["excluidos_por_erro"] == ["o/b"]
    assert {c["par"]: c["n"] for c in summary["comparacoes"]} == {"C1×C2": 1, "C1×C3": 1, "C2×C3": 1}
    assert summary["distribuicao"]["C2"][None] == 0 and sum(summary["distribuicao"]["C1"].values()) == 2
    with (out / "rq08_rework.csv").open(encoding="utf-8") as fp:
        rework_rows = {r["full_name"]: r for r in csv.DictReader(fp)}
    assert (rework_rows["o/a"]["corretivas"], rework_rows["o/a"]["releases"]) == ("1", "2")
    assert (out / "rq07_rq08_resumo.md").read_text(encoding="utf-8").startswith("# RQ 07 e RQ 08")
