# 2. Metodologia

## 2.1 Fonte de dados e coleta

Os dados vêm das APIs REST públicas do GitHub e são coletados por um pipeline próprio,
escrito em Python sobre a biblioteca `requests`, sem bibliotecas prontas de acesso à API.
A coleta usa os endpoints de busca de repositórios (`/search/repositories`), workflows
(`/actions/workflows`), releases (`/releases`), comparação de commits (`/compare`), workflow
runs (`/actions/runs`) e contribuidores (`/contributors`).

O pipeline é executado com um único comando (`python -m pipeline --config config.yaml`) e lê o
token de acesso da variável de ambiente `GITHUB_TOKEN`. Para tornar a coleta reprodutível e
resistente a interrupções:

- cada resposta da API é salva em disco, com apenas os campos usados. Uma execução
  interrompida, por rate limit, queda de rede ou interrupção manual, continua de onde parou
  sem repetir chamadas;
- o script espera automaticamente quando a cota acaba, pelos cabeçalhos `X-RateLimit-Reset`
  e `Retry-After`;
- respostas 5xx e falhas de rede são repetidas com *backoff* exponencial (1 s, 2 s, 4 s, 8 s…);
- as funções de cálculo têm testes automatizados (pytest), com cobertura de 100% do módulo de
  métricas, executados no GitHub Actions a cada push.

A coleta da amostra final foi realizada entre 14 e 15 de outubro de 2026.

## 2.2 Seleção de repositórios

Os candidatos são repositórios com mais de 1.000 estrelas, não arquivados e que não são
espelhos. Como a busca devolve no máximo 1.000 resultados por consulta, ela é fatiada em
faixas de estrelas (> 50.000; 20.000–50.000; 10.000–19.999; 5.000–9.999; 2.000–4.999;
1.000–1.999), cada uma em ordem decrescente de estrelas. Os candidatos são avaliados nessa
ordem até a amostra atingir 300 repositórios. Um repositório é incluído se:

1. usa GitHub Actions (ao menos um workflow);
2. publicou ao menos 5 releases na janela;
3. tem ao menos 50 workflow runs válidos no default branch na janela.

**Tabela 1. Funil de seleção.**

| Etapa | Repositórios | Descartados | Motivo do descarte |
|---|---|---|---|
| Candidatos avaliados | 707 | — | — |
| Usam GitHub Actions | 639 | 68 | nenhum workflow |
| ≥ 5 releases na janela | 346 | 293 | menos de 5 releases publicadas |
| ≥ 50 workflow runs válidos | 300 | 46 | menos de 50 runs válidos |
| **Amostra final** | **300** | — | — |

Nenhum candidato foi descartado por erro de coleta.

Como os candidatos são avaliados do mais para o menos popular, a amostra é formada pelos
repositórios elegíveis mais populares do GitHub: todos têm 40.642 estrelas ou mais (mediana de 62.121).
Isso limita a generalização dos resultados para projetos menos populares (validade externa).

## 2.3 Janela de observação

A janela tem 12 meses, de 01/10/2025 a 30/09/2026 (UTC). Entram nos cálculos apenas as
releases publicadas e os workflow runs criados dentro dela.

## 2.4 Definições operacionais

- **Deploy.** Uma release publicada no GitHub (`draft = false`) que não é pré-release
  (`prerelease = false`). Pré-releases e tags sem release ficam para as variantes da RQ 07.
- **Branch.** Apenas o *default branch* de cada repositório.
- **Data de um commit.** `commit.author.date`, que registra quando a mudança foi escrita.
- **Execuções de CI.** Workflow runs do default branch disparados por `push`. As conclusões
  `success` contam como sucesso; `failure`, `timed_out` e `startup_failure`, como falha; as
  demais (`cancelled`, `skipped`, `neutral`, `action_required`, `stale` ou em andamento) são
  ignoradas. Os runs são consultados mês a mês, e um período é subdividido, se preciso até
  frações de um dia, quando atinge o teto de 1.000 resultados por consulta. Sem essa subdivisão,
  12 candidatos com mais de 1.000 runs num único dia seriam descartados, e com eles justamente
  os projetos mais ativos. Onze deles estão na amostra final, entre eles `pytorch/pytorch`
  (206 mil runs válidos na janela), `getsentry/sentry` e `grafana/grafana`.
- **Commits de uma release.** São os commits devolvidos por `compare/{anterior}...{R}`. A
  release anterior de R é a de **maior versão menor que a de R, com o mesmo prefixo de tag**
  (como `v` ou `pkg@`, que separa os pacotes de um monorepo), publicada antes de R. Tags sem
  versão reconhecível usam a release anterior por data. Essa escolha evita comparar um patch de
  uma linha antiga com uma release de outra linha. Na coleta preliminar de 100 repositórios, a
  comparação por data levava a `godot 3.6.3-stable` a ser comparada com a `4.7.2-stable`, com
  9.545 commits; 3% das releases concentravam 68% dos commits. Com a regra adotada, essa
  release passa a ter 28 commits. Releases sem anterior (a primeira da história), sem commits
  novos ou cujo compare falha ficam fora do lead time e são contadas.
- **Lead time.** Para cada release R: (a) `R − commit mais antigo de R`, com valor do
  repositório igual à mediana entre as releases; (b) `R − cada commit de R`, com valor do
  repositório igual à mediana de todos os commits de todas as releases.
- **Taxa de falha (CFR).** (a) Proxy de CI: `falhas ÷ (falhas + sucessos)`. (b) Proxy de
  entrega: fração das releases seguidas, em até 7 dias, por uma release corretiva. A
  heurística v1 considera corretiva a release que muda apenas o número de *patch* em relação
  à anterior **e** contém ao menos um commit cuja primeira linha cita `fix`, `hotfix`,
  `bugfix` ou `revert`. Releases dos últimos 7 dias da janela são censuradas e ficam fora do
  denominador.
- **Tempo de recuperação.** Dentro de cada workflow, um episódio de falha começa na primeira
  falha após um sucesso e termina no próximo sucesso; dura `updated_at do sucesso −
  run_started_at da primeira falha`. O valor do repositório é a mediana dos episódios de todos
  os workflows. Episódios sem sucesso até o fim da janela são censurados: ficam fora da mediana
  e são reportados como proporção.
- **Classificação DORA.** Cada métrica é classificada em Elite, High, Medium ou Low pelos
  cortes fixos da disciplina. A classificação geral é a mediana das quatro notas (Elite = 4 …
  Low = 1), arredondada para baixo. A combinação de referência (C1) usa release como deploy,
  lead time (a) e CFR (a).
- **Estatística descritiva.** Por causa da assimetria das distribuições, todas as métricas são
  resumidas por mediana e intervalo interquartil (IQR).

## 2.5 Dataset

O pipeline gera, em `data/processed/`, o funil (`funnel.csv`), os metadados dos repositórios,
as releases, os commits de cada release, as releases fora do lead time, os workflow runs e o
dataset de métricas por repositório (`metrics.csv`). Cada coluna está documentada, com tipo,
unidade e fórmula, em `docs/dicionario-de-dados.md`.

## 2.6 Validação manual (amostra-ouro)

<!-- issue30-metodologia -->
## Validação manual e concordância

Nesta execução adaptada, a validação manual usa 60 repositórios de uma população de pelo menos 100, sorteados
com semente 42 após ordenação por full_name. Para cada repositório são sorteadas cinco
releases com a mesma semente, totalizando 300 itens. A redução da população para 100 foi solicitada pelo usuário; o enunciado S02 continua exigindo pelo menos 300 repositórios. O manifesto congela identificadores,
hashes dos dados e versões do ambiente. O protocolo detalhado está em
[protocolo-amostra-ouro.md](protocolo-amostra-ouro.md).

Três avaliadores (gsantss, arthies2323 e PortoPedro) recebem arquivos separados sem a
saída da heurística. Cada um registra independentemente tipo de projeto, se as releases
representam entregas reais e se cada uma das cinco releases é corretiva. Os dois primeiros
rótulos têm como unidade o repositório (60 itens); o terceiro, a release (300 itens).

A concordância é calculada nos votos originais por aggregate_raters e fleiss_kappa do
statsmodels, com interpretação pela escala de Landis e Koch (1977). Casos sem variabilidade
são reportados como kappa indefinido, com justificativa. O consenso segue maioria simples;
empates 1-1-1 exigem reunião dos três, com decisão, justificativa, participantes e data
registrados. Rótulos originais não são alterados. Resultados de kappa ficam em
validacao/kappa.json e validacao/relatorio.md; consenso e auditoria só podem ser considerados
finais após verificar todos os critérios. Arquivos piloto não representam a amostra final.

O módulo valida reprodutibilidade, completude e consistência; a independência do julgamento
é uma condição do protocolo humano. A implementação, por si só, não comprova que a
rotulagem foi realizada. A avaliação da heurística frente ao consenso pertence à Issue #35.
<!-- /issue30-metodologia -->

## 2.7 Validação da heurística de release corretiva

*A cargo da issue #35: precisão, recall e F1 de cada versão da heurística.*
