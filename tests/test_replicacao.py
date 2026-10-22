import json

import numpy as np
import pandas as pd
import pytest

from analises.replicacao import (
    alinhar,
    carregar,
    comparar,
    comparar_classe,
    comparar_metrica,
    diferenca_relativa,
    divergencias,
    main,
    resumo_md,
)


def _df(rows, cols):
    return pd.DataFrame(rows, columns=["full_name", *cols]).set_index("full_name")


def test_diferenca_relativa_basic_cases():
    original = pd.Series([10.0, 0.0, 0.0, 5.0, np.nan, 4.0])
    replica = pd.Series([12.0, 0.0, 3.0, 5.0, 1.0, np.nan])
    rel = diferenca_relativa(original, replica)
    assert rel.iloc[0] == pytest.approx(0.2)
    assert rel.iloc[1] == 0.0  # zero com zero
    assert np.isnan(rel.iloc[2])  # original zero, réplica diferente: indefinido
    assert rel.iloc[3] == 0.0
    assert np.isnan(rel.iloc[4]) and np.isnan(rel.iloc[5])  # ausentes


def test_comparar_metrica_summary():
    original = pd.Series([10.0, 10.0, 10.0, 10.0, 0.0])
    replica = pd.Series([10.0, 10.5, 15.0, 10.0, 2.0])
    result = comparar_metrica(original, replica, tolerancia=0.10)
    assert result["n_pares"] == 4  # o par com original zero e réplica diferente é indefinido
    assert result["n_indefinidos"] == 1
    assert result["pct_identicos"] == pytest.approx(50.0)
    assert result["pct_dentro_tolerancia"] == pytest.approx(75.0)  # 0, 0, 0,05 dentro; 0,5 fora
    assert result["mediana"] == pytest.approx(0.025)


def test_comparar_metrica_without_pairs_returns_nan():
    result = comparar_metrica(pd.Series([np.nan]), pd.Series([1.0]))
    assert result["n_pares"] == 0 and np.isnan(result["mediana"])


def test_comparar_classe_agreement_and_weighted_kappa():
    original = pd.Series(["Elite", "High", "Medium", "Low"])
    iguais = comparar_classe(original, original.copy())
    assert iguais["pct_iguais"] == 100.0 and iguais["kappa_ponderado"] == pytest.approx(1.0)

    trocada = pd.Series(["Elite", "High", "Medium", "Elite"])  # a última salta três faixas
    parcial = comparar_classe(original, trocada)
    assert parcial["pct_iguais"] == pytest.approx(75.0)
    assert parcial["kappa_ponderado"] < 1.0


def test_comparar_classe_ignores_missing_and_unknown_categories():
    original = pd.Series(["High", None, "Sem classificação", "Low"])
    replica = pd.Series(["High", "High", "High", "Low"])
    result = comparar_classe(original, replica)
    assert result["n"] == 2 and result["pct_iguais"] == 100.0


def test_alinhar_restricts_original_to_replica_subsample_and_reports_missing():
    original = _df([("a/x", 1), ("b/y", 2), ("c/z", 3)], ["m"])
    replica = _df([("b/y", 2), ("z/novo", 9)], ["m"])
    orig, rep, ausentes = alinhar(original, replica)
    assert list(orig.index) == ["b/y"] and list(rep.index) == ["b/y"]
    assert ausentes == ["z/novo"]


def test_divergencias_lists_metric_and_class_differences():
    original = _df([("a/x", 1.0, "High"), ("b/y", 2.0, "Low")], ["cfr_ci", "class_cfr"])
    replica = _df([("a/x", 1.0, "High"), ("b/y", 4.0, "Medium")], ["cfr_ci", "class_cfr"])
    table = divergencias(original, replica, tolerancia=0.10)
    assert set(table["repositorio"]) == {"b/y"}
    assert set(table["metrica"]) == {"cfr_ci", "class_cfr"}


def test_carregar_applies_column_map_and_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "outro.csv"
    path.write_text("repo,freq\na/x,1\nb/y,2\n", encoding="utf-8")
    df = carregar(path, {"repo": "full_name", "freq": "deployment_frequency"})
    assert list(df.columns) == ["deployment_frequency"] and list(df.index) == ["a/x", "b/y"]

    duplicado = tmp_path / "dup.csv"
    duplicado.write_text("full_name,m\na/x,1\na/x,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        carregar(duplicado)
    with pytest.raises(KeyError):
        carregar(path)  # sem o mapa, a coluna-chave não existe


def test_identical_files_give_zero_difference_and_full_agreement():
    df = _df([("a/x", 1.0, 5.0, "Elite"), ("b/y", 2.0, 7.0, "Low")],
             ["deployment_frequency", "lead_time_release_h", "class_overall"])
    result = comparar(df, df.copy())
    assert (result["metricas"]["mediana"] == 0).all()
    assert result["classes"].loc[0, "pct_iguais"] == 100.0
    assert result["divergencias"].empty


def test_main_writes_outputs_and_uses_map_file(tmp_path, monkeypatch, capsys):
    original = tmp_path / "orig.csv"
    replica = tmp_path / "rep.csv"
    original.write_text("repo,freq,cls\na/x,1.0,High\nb/y,2.0,Low\nc/z,3.0,Medium\n", encoding="utf-8")
    replica.write_text("repo,freq,cls\na/x,1.0,High\nb/y,3.0,Low\n", encoding="utf-8")
    mapa = tmp_path / "mapa.json"
    mapa.write_text(json.dumps({"repo": "full_name", "freq": "deployment_frequency", "cls": "class_overall"}),
                    encoding="utf-8")
    saida = tmp_path / "saida"
    monkeypatch.setattr("sys.argv", ["replicacao", "--original", str(original), "--replica", str(replica),
                                     "--mapa", str(mapa), "--saida", str(saida)])
    main()
    for nome in ("metricas.csv", "classificacao.csv", "divergencias.csv", "resumo.md"):
        assert (saida / nome).exists()
    divergentes = pd.read_csv(saida / "divergencias.csv")
    assert list(divergentes["repositorio"]) == ["b/y"]  # c/z não está na subamostra da réplica
    assert "Comparação da replicação" in capsys.readouterr().out


def test_resumo_md_mentions_repositories_missing_from_original():
    original = _df([("a/x", 1.0)], ["deployment_frequency"])
    replica = _df([("a/x", 1.0), ("novo/r", 2.0)], ["deployment_frequency"])
    texto = resumo_md(comparar(original, replica))
    assert "novo/r" in texto and "Frequência de deploy" in texto
