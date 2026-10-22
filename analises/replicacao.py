"""Comparação de uma replicação com o CSV original (Lab03, replicação cruzada).

Compara o CSV de métricas do estudo original com o de uma execução do pipeline (por outro grupo,
sobre uma subamostra), repositório a repositório:

    python -m analises.replicacao --original original.csv --replica replica.csv
    python -m analises.replicacao --original original.csv --replica replica.csv --mapa mapa.json

Saídas, em --saida (padrão analises/resultados/replicacao):
    metricas.csv      diferença relativa por métrica (mediana e IQR, % idênticos, % dentro da tolerância)
    classificacao.csv concordância da classificação DORA (% iguais e kappa ponderado)
    divergencias.csv  um repositório e uma métrica por linha, acima da tolerância (base das Issues)
    resumo.md         o mesmo resumo em texto

O `--mapa` é um JSON {"nome na planilha": "nome usado aqui"} para o caso de o outro grupo usar colunas
com nomes diferentes. Os nomes usados aqui são os de `metrics.csv` deste repositório.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

CHAVE = "full_name"
METRICAS = {
    "deployment_frequency": "Frequência de deploy",
    "lead_time_release_h": "Lead time (a)",
    "lead_time_commit_h": "Lead time (b)",
    "cfr_ci": "CFR (a)",
    "cfr_delivery": "CFR (b)",
    "recovery_h": "Tempo de recuperação",
}
CLASSES = {
    "class_deployment_frequency": "Frequência de deploy",
    "class_lead_time": "Lead time",
    "class_cfr": "CFR",
    "class_recovery": "Tempo de recuperação",
    "class_overall": "Classificação geral",
}
ORDEM = {"Low": 1, "Medium": 2, "High": 3, "Elite": 4}
TOLERANCIA = 0.10  # diferença relativa acima da qual o repositório entra em divergencias.csv


def carregar(path: str | Path, mapa: dict[str, str] | None = None, chave: str = CHAVE) -> pd.DataFrame:
    """Lê um CSV de métricas, renomeia as colunas pelo mapa e indexa pela chave."""
    df = pd.read_csv(path, encoding="utf-8-sig")
    if mapa:
        df = df.rename(columns=mapa)
    if chave not in df.columns:
        raise KeyError(f"coluna-chave '{chave}' não encontrada; colunas: {list(df.columns)}")
    if df[chave].duplicated().any():
        raise ValueError(f"a chave '{chave}' tem valores repetidos")
    return df.set_index(chave)


def diferenca_relativa(original: pd.Series, replica: pd.Series) -> pd.Series:
    """|replica − original| / |original|. Zero com zero é 0; original zero com réplica diferente é indefinido (NaN)."""
    original = pd.to_numeric(original, errors="coerce")
    replica = pd.to_numeric(replica, errors="coerce")
    absoluta = (replica - original).abs()
    relativa = absoluta / original.abs()
    relativa = relativa.where(original != 0, np.where(absoluta == 0, 0.0, np.nan))
    return relativa.where(original.notna() & replica.notna())


def comparar_metrica(original: pd.Series, replica: pd.Series, tolerancia: float = TOLERANCIA) -> dict:
    rel = diferenca_relativa(original, replica)
    pares = rel.notna()
    ambos = original.notna() & replica.notna()
    indefinidos = int((ambos & ~pares).sum())
    valores = rel[pares]
    n = int(len(valores))
    return {
        "n_pares": n,
        "n_indefinidos": indefinidos,  # original = 0 e réplica diferente de 0
        "mediana": float(valores.median()) if n else np.nan,
        "q1": float(valores.quantile(0.25)) if n else np.nan,
        "q3": float(valores.quantile(0.75)) if n else np.nan,
        "pct_identicos": float((valores <= 1e-9).mean() * 100) if n else np.nan,
        "pct_dentro_tolerancia": float((valores <= tolerancia).mean() * 100) if n else np.nan,
    }


def comparar_classe(original: pd.Series, replica: pd.Series) -> dict:
    df = pd.DataFrame({"o": original, "r": replica}).dropna()
    df = df[df["o"].isin(ORDEM) & df["r"].isin(ORDEM)]
    n = int(len(df))
    if n == 0:
        return {"n": 0, "pct_iguais": np.nan, "kappa_ponderado": np.nan}
    kappa = cohen_kappa_score(df["o"].map(ORDEM), df["r"].map(ORDEM), weights="linear", labels=[1, 2, 3, 4])
    return {
        "n": n,
        "pct_iguais": float((df["o"] == df["r"]).mean() * 100),
        "kappa_ponderado": float(kappa) if not np.isnan(kappa) else np.nan,
    }


def alinhar(original: pd.DataFrame, replica: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Restringe o original aos repositórios da réplica (a subamostra) e devolve os que não existem no original."""
    ausentes = sorted(set(replica.index) - set(original.index))
    comuns = [r for r in replica.index if r in original.index]
    return original.loc[comuns], replica.loc[comuns], ausentes


def divergencias(original: pd.DataFrame, replica: pd.DataFrame, tolerancia: float = TOLERANCIA) -> pd.DataFrame:
    linhas = []
    for coluna in METRICAS:
        if coluna not in original or coluna not in replica:
            continue
        rel = diferenca_relativa(original[coluna], replica[coluna])
        ambos = original[coluna].notna() & replica[coluna].notna()
        for repo in original.index[ambos & ((rel > tolerancia) | rel.isna())]:
            linhas.append({
                "repositorio": repo, "metrica": coluna,
                "original": original.at[repo, coluna], "replica": replica.at[repo, coluna],
                "diferenca_relativa": rel.at[repo],
            })
    for coluna in CLASSES:
        if coluna not in original or coluna not in replica:
            continue
        for repo in original.index:
            o, r = original.at[repo, coluna], replica.at[repo, coluna]
            if pd.notna(o) and pd.notna(r) and o != r:
                linhas.append({"repositorio": repo, "metrica": coluna, "original": o, "replica": r,
                               "diferenca_relativa": np.nan})
    return pd.DataFrame(linhas, columns=["repositorio", "metrica", "original", "replica", "diferenca_relativa"])


def comparar(original: pd.DataFrame, replica: pd.DataFrame, tolerancia: float = TOLERANCIA) -> dict:
    orig, rep, ausentes = alinhar(original, replica)
    metricas = pd.DataFrame(
        [{"metrica": c, "nome": n, **comparar_metrica(orig[c], rep[c], tolerancia)}
         for c, n in METRICAS.items() if c in orig and c in rep]
    )
    classes = pd.DataFrame(
        [{"classificacao": c, "nome": n, **comparar_classe(orig[c], rep[c])}
         for c, n in CLASSES.items() if c in orig and c in rep]
    )
    return {
        "n_replica": int(len(replica)), "n_comuns": int(len(orig)), "ausentes_no_original": ausentes,
        "metricas": metricas, "classes": classes, "divergencias": divergencias(orig, rep, tolerancia),
    }


def resumo_md(resultado: dict, tolerancia: float = TOLERANCIA) -> str:
    linhas = [
        "# Comparação da replicação com o original", "",
        f"Repositórios na réplica: {resultado['n_replica']}; comparados com o original: {resultado['n_comuns']}.",
    ]
    if resultado["ausentes_no_original"]:
        linhas.append(f"Fora do original: {', '.join(resultado['ausentes_no_original'])}.")
    linhas += ["", f"## Diferença relativa por métrica (tolerância de {tolerancia:.0%})", "",
               "| Métrica | Pares | Mediana [IQR] | Idênticos | Dentro da tolerância | Indefinidos |",
               "|---|---:|---|---:|---:|---:|"]
    for _, r in resultado["metricas"].iterrows():
        linhas.append(
            f"| {r['nome']} | {r['n_pares']} | {r['mediana']:.3f} [{r['q1']:.3f}; {r['q3']:.3f}] "
            f"| {r['pct_identicos']:.0f}% | {r['pct_dentro_tolerancia']:.0f}% | {r['n_indefinidos']} |"
            if r["n_pares"] else f"| {r['nome']} | 0 | — | — | — | {r['n_indefinidos']} |"
        )
    linhas += ["", "## Classificação DORA", "", "| Classificação | n | Iguais | Kappa ponderado |", "|---|---:|---:|---:|"]
    for _, r in resultado["classes"].iterrows():
        linhas.append(
            f"| {r['nome']} | {r['n']} | {r['pct_iguais']:.0f}% | {r['kappa_ponderado']:.3f} |"
            if r["n"] else f"| {r['nome']} | 0 | — | — |"
        )
    linhas += ["", f"Divergências para abrir como Issue: {len(resultado['divergencias'])} (ver divergencias.csv).", ""]
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--original", required=True)
    parser.add_argument("--replica", required=True)
    parser.add_argument("--mapa", help="JSON {coluna do arquivo: nome usado aqui}")
    parser.add_argument("--chave", default=CHAVE)
    parser.add_argument("--tolerancia", type=float, default=TOLERANCIA)
    parser.add_argument("--saida", default="analises/resultados/replicacao")
    args = parser.parse_args()

    mapa = json.loads(Path(args.mapa).read_text(encoding="utf-8")) if args.mapa else None
    resultado = comparar(
        carregar(args.original, mapa, args.chave), carregar(args.replica, mapa, args.chave), args.tolerancia
    )
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    resultado["metricas"].to_csv(saida / "metricas.csv", index=False)
    resultado["classes"].to_csv(saida / "classificacao.csv", index=False)
    resultado["divergencias"].to_csv(saida / "divergencias.csv", index=False)
    texto = resumo_md(resultado, args.tolerancia)
    (saida / "resumo.md").write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
