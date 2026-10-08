# Dicionário de dados

## `funnel.csv`

Funil de seleção: quantos repositórios restaram em cada etapa.

| Coluna | Tipo | Unidade | Origem / fórmula |
|---|---|---|---|
| `stage` | texto | — | Etapa: `candidates`, `with_actions`, `with_min_releases`, `with_min_runs`, `included` |
| `count` | inteiro | repositórios | Repositórios que chegaram até a etapa. `candidates`: resultados de `GET /search/repositories`; `with_actions`: `GET /repos/{o}/{r}/actions/workflows` com `total_count > 0`; `with_min_releases`: releases publicadas na janela >= `min_releases`; `with_min_runs`: runs válidos >= `min_runs`; `included`: tamanho final da amostra |

## `repositories.csv`

Um repositório por linha.

| Coluna | Tipo | Unidade | Origem / fórmula |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` (campo `full_name` da busca) |
| `default_branch` | texto | — | Campo `default_branch` da API |
| `stars` | inteiro | estrelas | Campo `stargazers_count` |
| `language` | texto | — | Linguagem principal (`language`); vazio se não houver |
| `created_at` | data/hora ISO 8601 UTC | — | Campo `created_at` do repositório (base da idade) |
| `contributors` | inteiro | pessoas | Última página de `GET /repos/{o}/{r}/contributors?per_page=1&anon=true` |
| `releases_valid` | inteiro | releases | Releases com `draft = false` e `prerelease = false` e `published_at` dentro da janela |
| `workflow_runs_valid` | inteiro | execuções | Runs no default branch, `event = push`, criadas na janela, com `conclusion` de sucesso ou falha (cancelled, skipped, neutral, action_required, stale e em andamento são ignoradas) |

> As colunas das métricas DORA por repositório (frequência, lead time, CFR,
> tempo de recuperação e classificação) serão documentadas aqui quando entrarem
> no CSV final (Lab03S02).
