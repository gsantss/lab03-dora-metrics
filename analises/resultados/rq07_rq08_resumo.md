# RQ 07 e RQ 08: resultados

## Distribuição da classificação geral

| Combinação | Definição | Elite | High | Medium | Low | Sem classificação |
|---|---|---|---|---|---|---|
| C1 | release · lead time (a) · CFR (a) | 20 | 122 | 130 | 12 | 16 |
| C2 | release + pré-release · lead time (b) · CFR (b) | 10 | 118 | 145 | 10 | 17 |
| C3 | tag · lead time (b) · CFR (a) | 24 | 150 | 105 | 6 | 15 |

## Métricas em cada combinação: mediana [IQR]

| Combinação | Frequência (deploys/semana) | Lead time (h) | CFR |
|---|---|---|---|
| C1 | 0.518 [0.249, 1.208] | 239.152 [102.888, 795.744] | 0.046 [0.023, 0.112] |
| C2 | 0.652 [0.307, 1.376] | 193.504 [74.383, 531.176] | 0.152 [0.018, 0.354] |
| C3 | 0.901 [0.364, 2.162] | 183.060 [71.750, 485.697] | 0.046 [0.023, 0.112] |

## Comparação entre combinações

| Par | n | Mudaram de categoria | Subiram / desceram | Entre vizinhas | Kappa ponderado (linear) | Mudou frequência | Mudou lead time | Mudou CFR | Mudou recuperação |
|---|---|---|---|---|---|---|---|---|---|
| C1×C2 | 283 | 74 (26.1%) | 29 / 45 | 69 | 0.58 | 11.3% | 46.5% | 54.0% | 0.0% |
| C1×C3 | 284 | 69 (24.3%) | 54 / 15 | 67 | 0.645 | 25.7% | 49.5% | 0.0% | 0.0% |
| C2×C3 | 283 | 67 (23.7%) | 63 / 4 | 65 | 0.639 | 14.7% | 13.0% | 54.0% | 0.0% |

## RQ 08: rework rate

- Repositórios: 298
- Rework rate, mediana [IQR]: 0.600 [0.332, 0.800]
- CFR (b), mediana [IQR]: 0.181 [0.021, 0.400]
- Repositórios com rework rate maior que o CFR (b): 263
- Spearman (rework × CFR b): ρ = 0.315, p = 2.64e-08
