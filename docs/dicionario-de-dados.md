# Dicionário de dados

Todos os CSVs são gerados por `python -m pipeline --config config.yaml` em `output_dir`
(padrão `data/processed/`). Datas estão em ISO 8601 UTC, como devolvidas pela API.

## `funnel.csv`

Funil de seleção: quantos repositórios chegaram a cada etapa e por que os demais saíram.
Para cada etapa vale `count(etapa anterior) = count + discarded`.

| Coluna | Tipo | Unidade | Origem / fórmula |
|---|---|---|---|
| `stage` | texto | — | Etapa: `candidates`, `with_actions`, `with_min_releases`, `with_min_runs`, `included` |
| `count` | inteiro | repositórios | Repositórios que chegaram até a etapa. `candidates`: resultados de `GET /search/repositories` avaliados; `with_actions`: `GET /repos/{o}/{r}/actions/workflows` com `total_count > 0`; `with_min_releases`: releases publicadas na janela >= `min_releases`; `with_min_runs`: runs válidos >= `min_runs`; `included`: tamanho final da amostra |
| `discarded` | inteiro | repositórios | Repositórios que pararam nesta etapa |
| `reasons` | texto | — | Motivos do descarte no formato `motivo=quantidade`, separados por `; `. Motivos: `no_actions`, `few_releases`, `few_runs`, `api_error` (erro da API que persistiu após as novas tentativas) |

## `repositories.csv`

Um repositório da amostra final por linha.

| Coluna | Tipo | Unidade | Origem / fórmula |
|---|---|---|---|
| `full_name` | texto | — | `owner/repo` (campo `full_name` da busca) |
| `owner` | texto | — | `owner.login` |
| `name` | texto | — | `name` |
| `html_url` | texto | — | Página do repositório no GitHub (usada na planilha da amostra-ouro) |
| `default_branch` | texto | — | Campo `default_branch` da API |
| `stars` | inteiro | estrelas | Campo `stargazers_count` |
| `language` | texto | — | Linguagem principal (`language`); vazio se não houver |
| `created_at` | data/hora | — | Campo `created_at` do repositório (base da idade) |
| `contributors` | inteiro | pessoas | Última página de `GET /repos/{o}/{r}/contributors?per_page=1&anon=true`; vazio quando a API recusa a lista (403 em repositórios muito grandes) |
| `releases_valid` | inteiro | releases | Releases com `draft = false` e `prerelease = false` e `published_at` dentro da janela |
| `workflow_runs_valid` | inteiro | execuções | Runs no default branch, `event = push`, criadas na janela, com `conclusion` de sucesso ou falha (cancelled, skipped, neutral, action_required, stale e em andamento são ignoradas) |

## `releases.csv`

Releases da definição principal (deploys) dentro da janela, uma por linha.

| Coluna | Tipo | Unidade | Origem / fórmula |
|---|---|---|---|
| `full_name` | texto | — | Repositório |
| `release_id` | inteiro | — | Campo `id` da release |
| `tag_name` | texto | — | Campo `tag_name` |
| `published_at` | data/hora | — | Campo `published_at` (data do deploy) |

## `commits.csv`

Commits incluídos em cada release da janela: `GET /repos/{o}/{r}/compare/{anterior}...{release}`,
paginado. A release anterior é a release publicada imediatamente antes (sem pré-releases),
mesmo que esteja fora da janela.

| Coluna | Tipo | Unidade | Origem / fórmula |
|---|---|---|---|
| `full_name` | texto | — | Repositório |
| `release_id` | inteiro | — | Release que inclui o commit (chave para `releases.csv`) |
| `release_tag` | texto | — | `tag_name` da release |
| `release_published_at` | data/hora | — | `published_at` da release |
| `commit_sha` | texto | — | `sha` do commit |
| `commit_author_date` | data/hora | — | `commit.author.date` (quando a mudança foi escrita) |
| `commit_message` | texto | — | Primeira linha de `commit.message` (usada na heurística de release corretiva) |

Lead time em horas: (a) por release, `release_published_at − min(commit_author_date)`;
(b) por commit, `release_published_at − commit_author_date` (ver `metricas.py`).

## `ignored_releases.csv`

Releases da janela que ficaram fora do cálculo de lead time.

| Coluna | Tipo | Unidade | Origem / fórmula |
|---|---|---|---|
| `full_name` | texto | — | Repositório |
| `release_id` | inteiro | — | Campo `id` da release |
| `tag_name` | texto | — | Campo `tag_name` |
| `reason` | texto | — | `no_previous_release` (primeira release da história), `no_new_commits` (compare sem commits) ou `compare_error:<Erro>` (ex.: tag apagada, 404) |

## `workflow_runs.csv`

Workflow runs válidos (sucesso ou falha) do default branch disparados por `push` na janela.
A janela é consultada mês a mês e subdividida quando uma consulta atinge o teto de 1000 runs.

| Coluna | Tipo | Unidade | Origem / fórmula |
|---|---|---|---|
| `full_name` | texto | — | Repositório |
| `id` | inteiro | — | Campo `id` do run |
| `workflow_id` | inteiro | — | Workflow do run (o tempo de recuperação é calculado por workflow) |
| `name` | texto | — | Nome do workflow |
| `conclusion` | texto | — | `success`, `failure`, `timed_out` ou `startup_failure` |
| `created_at` | data/hora | — | Campo `created_at` |
| `run_started_at` | data/hora | — | Início do run (início de um episódio de falha) |
| `updated_at` | data/hora | — | Fim do run (fim de um episódio, quando é um sucesso) |

> As colunas das métricas DORA por repositório (frequência, lead time, CFR,
> tempo de recuperação e classificação) serão documentadas aqui quando entrarem
> no CSV final (Lab03S02). As funções de cálculo já estão em `metricas.py`.
