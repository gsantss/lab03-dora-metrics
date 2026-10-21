import pytest

from validacao import (
    build_samples,
    compare_variants,
    evaluate,
    v1_patch_and_fix,
    v2_patch_or_fix,
    v3_fix_only,
    v4_patch_only,
)


def test_evaluate_matches_example_from_assignment():
    # heurística marcou 40 corretivas, 30 corretas; consenso tem 50 corretivas no total
    y_true = [1] * 30 + [0] * 10 + [1] * 20
    y_pred = [1] * 30 + [1] * 10 + [0] * 20
    result = evaluate(y_true, y_pred)
    assert result["precision"] == pytest.approx(0.75)
    assert result["recall"] == pytest.approx(0.60)
    assert result["f1"] == pytest.approx(2 * 0.75 * 0.60 / (0.75 + 0.60))
    assert result["positives"] == 50


def test_evaluate_without_predicted_positives_does_not_crash():
    result = evaluate([1, 0, 1], [0, 0, 0])
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0


def test_variants_on_known_cases():
    fix = ["fix: crash ao abrir arquivo"]
    feat = ["feat: nova tela"]
    # v2.3.0 -> v2.3.1 com fix: todas marcam
    assert v1_patch_and_fix("v2.3.0", "v2.3.1", fix)
    # só patch, sem fix: v1 não marca, v2 e v4 marcam
    assert not v1_patch_and_fix("v2.3.0", "v2.3.1", feat)
    assert v2_patch_or_fix("v2.3.0", "v2.3.1", feat)
    assert v4_patch_only("v2.3.0", "v2.3.1", feat)
    # minor com fix: v1 não marca, v2 e v3 marcam
    assert not v1_patch_and_fix("v2.4.0", "v2.5.0", fix)
    assert v2_patch_or_fix("v2.4.0", "v2.5.0", fix)
    assert v3_fix_only("v2.4.0", "v2.5.0", fix)
    # nada: ninguém marca
    assert not v2_patch_or_fix("v2.4.0", "v2.5.0", feat)


def test_build_samples_joins_release_previous_tag_and_commit_messages():
    consenso = [
        {"full_name": "o/r", "tag_name": "v2.3.1", "corretiva": "sim"},
        {"full_name": "o/r", "tag_name": "v2.5.0", "corretiva": "nao"},
        {"full_name": "o/r", "tag_name": "inexistente", "corretiva": "nao"},
    ]
    releases = [
        {"full_name": "o/r", "release_id": "1", "tag_name": "v2.3.1", "previous_tag": "v2.3.0"},
        {"full_name": "o/r", "release_id": "2", "tag_name": "v2.5.0", "previous_tag": "v2.4.0"},
    ]
    commits = [
        {"release_id": "1", "commit_message": "fix: crash"},
        {"release_id": "2", "commit_message": "feat: tela"},
    ]
    samples = build_samples(consenso, releases, commits)
    assert len(samples) == 2  # a que não existe nos dados é ignorada
    assert samples[0]["label"] == 1 and samples[0]["previous_tag"] == "v2.3.0"
    assert samples[1]["label"] == 0 and samples[1]["messages"] == ["feat: tela"]


def test_compare_variants_reports_f1_and_target():
    samples = [
        {"previous_tag": "v1.0.0", "tag": "v1.0.1", "messages": ["fix: x"], "label": 1},
        {"previous_tag": "v1.0.1", "tag": "v1.1.0", "messages": ["feat: y"], "label": 0},
        {"previous_tag": "v1.1.0", "tag": "v1.2.0", "messages": ["fix: z"], "label": 1},
    ]
    table = {row["versao"]: row for row in compare_variants(samples)}
    v1 = table["v1 patch E fix"]
    assert v1["precision"] == 1.0 and v1["recall"] == pytest.approx(0.5)
    v3 = table["v3 só fix"]
    assert v3["f1"] == 1.0 and v3["atinge_alvo"] is True
    assert table["v1 patch E fix"]["atinge_alvo"] is False


def test_load_rows_accepts_csv_with_bom(tmp_path):
    from validacao import load_rows

    path = tmp_path / "consenso.csv"
    path.write_bytes("full_name,tag_name,corretiva\no/r,v1.0.1,sim\n".encode("utf-8-sig"))
    rows = load_rows(str(path))
    assert rows[0]["full_name"] == "o/r"
    assert rows[0]["corretiva"] == "sim"


def test_load_rows_reads_every_file_of_a_directory(tmp_path):
    import gzip

    from validacao import load_rows

    for name, repo in (("a__x.csv.gz", "a/x"), ("b__y.csv.gz", "b/y")):
        with gzip.open(tmp_path / name, "wt", encoding="utf-8", newline="") as fp:
            fp.write(f"full_name,release_id,commit_message\n{repo},1,fix: bug\n")
    rows = load_rows(str(tmp_path))
    assert sorted(r["full_name"] for r in rows) == ["a/x", "b/y"]
