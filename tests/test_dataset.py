import csv
from datetime import datetime, timezone

import pytest

import pipeline.__main__ as entrypoint
from pipeline.collect import SampleWriter
from pipeline.dataset import METRIC_FIELDS, build_metrics, repository_metrics

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 1, 15, tzinfo=timezone.utc)  # duas semanas


def release(release_id, tag, published_at):
    return {"release_id": release_id, "tag_name": tag, "published_at": published_at}


def commit(release_id, published_at, author_date, message="feat: x"):
    return {
        "release_id": release_id,
        "release_published_at": published_at,
        "commit_author_date": author_date,
        "commit_message": message,
    }


def run(run_id, conclusion, started, updated, workflow_id="1"):
    return {
        "id": run_id,
        "workflow_id": workflow_id,
        "conclusion": conclusion,
        "run_started_at": started,
        "updated_at": updated,
    }


def test_repositorio_sem_runs_validos_fica_sem_classificacao_geral():
    releases = [release(1, "v1.0.0", "2026-01-02T00:00:00Z"), release(2, "v1.1.0", "2026-01-03T00:00:00Z")]
    commits = [commit(2, "2026-01-03T00:00:00Z", "2026-01-02T12:00:00Z")]
    row = repository_metrics("o/r", releases, commits, [], [], START, END)

    assert row["deployment_frequency"] == 1.0
    assert row["class_deployment_frequency"] == "High"
    assert row["lead_time_release_h"] == 12.0
    assert row["class_lead_time"] == "Elite"
    assert row["cfr_ci"] is None and row["class_cfr"] is None
    assert row["recovery_h"] is None and row["recovery_censored_ratio"] is None
    assert row["class_overall"] is None


def test_colunas_na_ordem_documentada():
    row = repository_metrics("o/r", [release(1, "v1", "2026-01-02T00:00:00Z")], [], [], [], START, END)
    assert list(row) == METRIC_FIELDS


def test_classificacao_geral_com_as_quatro_metricas():
    releases = [release(i, f"v1.0.{i}", f"2026-01-{i + 1:02d}T00:00:00Z") for i in range(1, 8)]
    commits = [commit(i, f"2026-01-{i + 1:02d}T00:00:00Z", f"2026-01-{i + 1:02d}T00:00:00Z") for i in range(2, 8)]
    runs = [
        run(1, "success", "2026-01-02T09:00:00Z", "2026-01-02T09:05:00Z"),
        run(2, "failure", "2026-01-02T10:00:00Z", "2026-01-02T10:05:00Z"),
        run(3, "success", "2026-01-02T10:20:00Z", "2026-01-02T10:30:00Z"),
        run(4, "success", "2026-01-02T11:00:00Z", "2026-01-02T11:05:00Z"),
        run(5, "success", "2026-01-02T12:00:00Z", "2026-01-02T12:05:00Z"),
        run(6, "success", "2026-01-02T13:00:00Z", "2026-01-02T13:05:00Z"),
        run(7, "success", "2026-01-02T14:00:00Z", "2026-01-02T14:05:00Z"),
    ]
    row = repository_metrics("o/r", releases, commits, [], runs, START, END)

    # 3,5 releases/semana (High), lead time 0 h (Elite), CFR 1/7 (Elite), recuperação 0,5 h (Elite)
    assert [row[k] for k in ("class_deployment_frequency", "class_lead_time", "class_cfr", "class_recovery")] == [
        "High",
        "Elite",
        "Elite",
        "Elite",
    ]
    assert row["recovery_h"] == 0.5
    assert row["class_overall"] == "Elite"  # mediana 4 de (3, 4, 4, 4)


def write_processed(out_dir, repos):
    """Grava os CSVs da coleta como o pipeline faz: um bloco de linhas por repositório."""
    with SampleWriter(out_dir) as writer:
        for name, data in repos:
            writer.write({"repositories": [{"full_name": name}], **data})


def test_nova_coleta_apaga_arquivos_de_repositorios_que_sairam(tmp_path):
    ok = {"full_name": "o/a", **run(1, "success", "2026-01-02T09:00:00Z", "2026-01-02T09:05:00Z")}
    write_processed(tmp_path, [("o/a", {"workflow_runs": [ok]}), ("o/b", {"workflow_runs": [{**ok, "full_name": "o/b"}]})])
    write_processed(tmp_path, [("o/a", {"workflow_runs": [ok]})])
    assert sorted(p.name for p in (tmp_path / "workflow_runs").iterdir()) == ["o__a.csv.gz"]


def test_formato_antigo_sem_pastas_por_repositorio_da_erro_claro(tmp_path):
    (tmp_path / "repositories.csv").write_text("full_name\no/a\n", encoding="utf-8")
    (tmp_path / "commits.csv.gz").write_bytes(b"")  # layout da coleta da S01
    with pytest.raises(FileNotFoundError, match="commits"):
        build_metrics(tmp_path, START, END)


def test_arquivo_por_repositorio_e_deterministico(tmp_path):
    rows = [{"full_name": "o/a", **commit(1, "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")}]
    write_processed(tmp_path / "x", [("o/a", {"commits": rows})])
    write_processed(tmp_path / "y", [("o/a", {"commits": rows})])
    first, second = (tmp_path / d / "commits" / "o__a.csv.gz" for d in ("x", "y"))
    assert first.read_bytes() == second.read_bytes()


def test_metrics_only_nao_usa_a_api(tmp_path, monkeypatch):
    out = tmp_path / "processed"
    write_processed(
        out,
        [("o/a", {"releases": [{"full_name": "o/a", **release(1, "v1.0.0", "2026-01-02T00:00:00Z")}]})],
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        "window: {start: '2026-01-01', end: '2026-01-14'}\n"
        f"sample_size: 1\nmin_releases: 1\nmin_runs: 1\ncache_dir: x\noutput_dir: {out.as_posix()}\n",
        encoding="utf-8",
    )

    def no_api(**_):
        raise AssertionError("--metrics-only não pode chamar a API")

    monkeypatch.setattr(entrypoint, "GitHubAPI", no_api)
    assert entrypoint.run(str(config), metrics_only=True) is None

    with (out / "metrics.csv").open(encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))
    assert [(r["full_name"], r["releases"]) for r in rows] == [("o/a", "1")]
