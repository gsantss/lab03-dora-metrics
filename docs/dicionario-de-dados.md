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
| `previous_tag` | texto | — | Release anterior usada no `compare` do lead time (ver `commits/`); vazio na primeira release da história |

## `commits/<owner>__<repo>.csv.gz`

Commits incluídos em cada release da janela: `GET /repos/{o}/{r}/compare/{anterior}...{release}`,
paginado. A release anterior (`previous_tag` em `releases.csv`) é a maior versão menor que a
da release, com o mesmo prefixo de tag, publicada antes dela e sem pré-releases, mesmo que
esteja fora da janela. Tags sem versão reconhecível usam a release anterior por data.
Um arquivo gzip por repositório (ex.: `godotengine__godot.csv.gz`); repositórios sem linhas não têm arquivo.

> **Por que a mesma linha de versão (#27):** na coleta da S01 a release anterior era a
> anterior por data. Em projetos com linhas de versão em paralelo, a `godot 3.6.3-stable` era
> comparada com a `4.7.2-stable` e trazia 9.545 commits antigos; 250 releases (3%) tinham mais
> de 1.000 commits e somavam 68% das linhas. Com a regra atual, a 3.6.3 é comparada com a
> 3.6.2 (28 commits), o total cai de 1,19 milhão para 533 mil commits e as releases com mais
> de 1.000 commits passam a 84 (1%). As que restam são, em geral, releases de ciclo longo
> (ex.: `rust 1.95.0`, `vscode 1.116.0`).

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

## `workflow_runs/<owner>__<repo>.csv.gz`

Workflow runs válidos (sucesso ou falha) do default branch disparados por `push` na janela.
A janela é consultada mês a mês e subdividida, se preciso até frações de um dia, quando uma
consulta atinge o teto de 1000 runs.
Um arquivo gzip por repositório (ex.: `godotengine__godot.csv.gz`); repositórios sem linhas não têm arquivo.

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

## `metrics.csv`

Métricas DORA, uma linha por repositório da amostra final, calculadas por `pipeline/dataset.py`
com as funções de `metricas.py`. Sai do mesmo comando da coleta. Para recalcular só esse
arquivo a partir dos CSVs acima, sem API: `python -m pipeline --config config.yaml --metrics-only`.
Valores vazios indicam que a métrica não pôde ser calculada (ex.: nenhum episódio de falha).
Medianas são calculadas dentro de cada repositório; para a amostra, reporte mediana e IQR.

| Coluna | Tipo | Unidade | Origem / fórmula |
|---|---|---|---|
| `full_name` | texto | — | Repositório (chave para os demais CSVs) |
| `releases` | inteiro | releases | Releases da definição principal na janela (`releases.csv`) |
| `deployment_frequency` | decimal | releases/semana | **RQ 01.** `releases ÷ semanas da janela` (≈ 52,14) |
| `lead_time_release_h` | decimal | horas | **RQ 02 (a).** Mediana, entre as releases, de `published_at − commit_author_date mais antigo` da release |
| `lead_time_commit_h` | decimal | horas | **RQ 02 (b).** Mediana de `published_at − commit_author_date` de todos os commits de todas as releases |
| `lead_time_releases` | inteiro | releases | Releases com ao menos um commit no cálculo de lead time |
| `lead_time_ignored` | inteiro | releases | Releases fora do lead time (`ignored_releases.csv`): sem anterior, sem commits novos ou erro no compare |
| `workflow_runs` | inteiro | execuções | Runs válidos (sucesso ou falha) em `workflow_runs/` |
| `cfr_ci` | decimal | fração (0–1) | **RQ 03 (a).** `falhas ÷ (falhas + sucessos)`; falha = `failure`, `timed_out`, `startup_failure` |
| `cfr_delivery` | decimal | fração (0–1) | **RQ 03 (b).** Releases seguidas em até 7 dias por uma release corretiva ÷ releases avaliadas (heurística v1: só o patch muda **e** há commit de fix/hotfix/bugfix/revert) |
| `cfr_delivery_evaluated` | inteiro | releases | Denominador do CFR (b): `releases − cfr_delivery_censored` |
| `cfr_delivery_censored` | inteiro | releases | Releases dos últimos 7 dias da janela (censuradas: ainda não se sabe se haverá correção) |
| `recovery_h` | decimal | horas | **RQ 04.** Mediana dos episódios de falha de todos os workflows: `updated_at` do primeiro sucesso − `run_started_at` da primeira falha, dentro do mesmo workflow |
| `recovery_episodes` | inteiro | episódios | Episódios de falha, recuperados ou não |
| `recovery_censored` | inteiro | episódios | Episódios sem sucesso até o fim da janela (censurados; fora da mediana) |
| `recovery_censored_ratio` | decimal | fração (0–1) | `recovery_censored ÷ recovery_episodes` |
| `class_deployment_frequency` | texto | — | Elite (≥ 7/semana), High (≥ 1/semana), Medium (≥ 1/mês), Low |
| `class_lead_time` | texto | — | Sobre `lead_time_release_h`: Elite (< 1 dia), High (< 1 semana), Medium (< 30 dias), Low |
| `class_cfr` | texto | — | Sobre `cfr_ci`: Elite (≤ 15%), High (≤ 30%), Medium (≤ 45%), Low |
| `class_recovery` | texto | — | Sobre `recovery_h`: Elite (< 1 h), High (< 1 dia), Medium (< 1 semana), Low |
| `class_overall` | texto | — | **Classificação de referência C1** (release, lead time (a), CFR (a)): mediana das quatro notas (Elite 4 … Low 1), arredondada para baixo; vazio se faltar alguma métrica |

## `variantes/` (RQ 07)

Unidades de deploy alternativas da amostra final, geradas por
`python -m pipeline --config config.yaml --variants`. Em ambas, a release anterior segue a
regra da mesma linha de versão, mas versões iguais contam como anteriores e vale a mais
recente: `2.0.0` é comparada com `2.0.0-rc2`, para que os commits já entregues numa
pré-release não sejam contados de novo.

| Arquivo | Conteúdo |
|---|---|
| `c2_units.csv` | **C2**: releases e pré-releases publicadas na janela. Colunas: `full_name`, `release_id`, `tag_name`, `published_at`, `previous_tag`, `prerelease` (verdadeiro para pré-release) |
| `c3_units.csv` | **C3**: tags cuja data cai na janela. Mesmas colunas; `release_id` é o nome da tag e `published_at` é a data do commit apontado pela tag (`committedDate` da API GraphQL; tags anotadas usam o commit de destino) |
| `c2_commits/` | Commits de cada unidade da C2, um `.csv.gz` por repositório: `release_id`, `commit_author_date`, `commit_message` (primeira linha; entra no CFR (b)). A data de publicação vem de `c2_units.csv` |
| `c3_commits/` | Commits de cada tag da C3, um `.csv.gz` por repositório: `release_id` (nome da tag) e `commit_author_date`. A C3 usa o CFR (a), então a mensagem não é guardada |
| `errors.csv` | Repositórios cuja coleta das variantes falhou (`full_name`, `error`); ficam fora de C2 e C3 |

## `analises/resultados/` (RQ 07 e RQ 08)

Gerados por `python -m analises.rq07 --config config.yaml`, sem API.

| Arquivo | Conteúdo |
|---|---|
| `rq07_classificacoes.csv` | Uma linha por repositório: categoria de cada métrica (`deployment_frequency`, `lead_time`, `cfr`, `recovery`) e geral (`overall`) em C1, C2 e C3, e os valores usados (`*_valor`: deploys por semana, lead time em horas e CFR como fração; lead time (a) em C1 e (b) em C2 e C3) |
| `rq07_comparacoes.csv` | Uma linha por par de combinações: `n` (classificados nas duas), `mudaram` e `mudaram_pct` (mudança da categoria geral), `subiram` e `desceram` (categoria melhor ou pior na segunda combinação), `vizinhas` (mudanças de uma só categoria), `kappa_linear` (kappa de Cohen ponderado linear) e a % de mudança em cada métrica |
| `rq08_rework.csv` | Uma linha por repositório: `releases`, `corretivas` (heurística do CFR b aplicada a cada release e à sua anterior), `rework_rate = corretivas ÷ releases` e `cfr_delivery` para comparação |
| `rq07_rq08_resumo.md` | Tabelas-resumo para o artigo |
