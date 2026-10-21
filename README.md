# Lab03 — Mineração de Métricas DORA

Pipeline que coleta dados públicos de repositórios open-source com GitHub Actions
e calcula as métricas DORA (frequência de deploy, lead time, taxa de falha e tempo
de recuperação) usando releases e workflow runs como proxies.

## Requisitos

- Python 3.11+
- Um token do GitHub (sem escopos especiais, só leitura pública)

## Como executar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export GITHUB_TOKEN=<seu token>  # Windows PowerShell: $env:GITHUB_TOKEN="<seu token>"
python -m pipeline --config config.yaml
```

O token é lido **somente** da variável de ambiente `GITHUB_TOKEN` e nunca deve ser
commitado.

### Configuração (`config.yaml`)

| Chave | Significado |
|---|---|
| `window.start` / `window.end` | Janela de observação de 12 meses (AAAA-MM-DD, UTC) |
| `sample_size` | Quantidade de repositórios na amostra final |
| `min_releases` | Mínimo de releases publicadas na janela (padrão 5) |
| `min_runs` | Mínimo de workflow runs válidos no default branch (padrão 50) |
| `cache_dir` | Pasta do cache de respostas da API |
| `output_dir` | Pasta dos CSVs finais |

### Cache e retomada

Cada resposta da API é salva em `cache_dir` (um JSON por requisição). Se a coleta
for interrompida (rate limit, rede, `Ctrl+C`), rode o mesmo comando de novo: as
chamadas já feitas são lidas do disco e a coleta continua de onde parou. Quando a
cota da API acaba, o script espera até `X-RateLimit-Reset` automaticamente; erros
5xx são repetidos com backoff exponencial (1 s, 2 s, 4 s, ...).

## Testes

```bash
pytest --cov=metricas --cov-report=term-missing
```

Os testes rodam a cada push no GitHub Actions (`.github/workflows/testes.yml`),
com cobertura mínima de 80% do módulo `metricas.py`.

## Saídas

Geradas em `output_dir` (por padrão `data/processed/`):

- `funnel.csv`: funil de seleção, com quantos repositórios foram descartados em cada etapa e por quê;
- `repositories.csv`: repositórios da amostra final e seus metadados;
- `releases.csv`: releases (deploys) de cada repositório na janela;
- `commits/<owner>__<repo>.csv.gz`: commits incluídos em cada release (base do lead time e do CFR por entrega);
- `ignored_releases.csv`: releases fora do cálculo de lead time e o motivo;
- `workflow_runs/<owner>__<repo>.csv.gz`: workflow runs válidos do default branch (base do CFR por CI e do tempo de recuperação);
- `metrics.csv`: métricas DORA por repositório, com todas as variantes e a classificação de referência.

Para recalcular só o `metrics.csv` a partir dos CSVs já coletados (sem token nem API):

```bash
python -m pipeline --config config.yaml --metrics-only
```

Commits e runs ficam em um arquivo comprimido por repositório: num arquivo só, passariam do
limite de 100 MB por arquivo do GitHub. Para ler todos com pandas:
`pd.concat(map(pd.read_csv, glob.glob("data/processed/commits/*.csv.gz")))`.

O dicionário de dados de cada coluna está em [docs/dicionario-de-dados.md](docs/dicionario-de-dados.md).

## Análise de sensibilidade (RQ 07) e rework rate (RQ 08)

A RQ 07 compara a classificação DORA em três definições operacionais: C1 (release, lead
time (a), CFR (a)), C2 (release + pré-release, lead time (b), CFR (b)) e C3 (tag, lead time (b),
CFR (a)). As unidades de deploy de C2 e C3 são coletadas da amostra final (tags datadas pelo
commit apontado, via API GraphQL) e a análise roda a partir dos CSVs:

```bash
python -m pipeline --config config.yaml --variants   # gera data/processed/variantes/ (usa a API)
python -m analises.rq07 --config config.yaml         # gera analises/resultados/ (sem API)
```

## Correlação e comparação de grupos (RQ 05 e RQ 06)

A RQ 05 (Spearman entre frequência de deploy e CFR) e a RQ 06 (fatores associados ao desempenho,
com Kruskal-Wallis, correção de Holm e tamanho de efeito) rodam a partir de `metrics.csv` e
`repositories.csv`, sem API nem token:

```bash
pip install -r requirements.txt            # já inclui requirements-analise.txt (matplotlib e scipy)
python -m analises.rq05_rq06               # gera analises/resultados/rq05_*, rq06_* (CSVs e figuras)
```

## Validação manual e heurística de release corretiva

A amostra-ouro (60 repositórios, 5 releases cada) tem um arquivo de rótulos por avaliador em
`validacao/rotulos/`. O protocolo está em `docs/protocolo-amostra-ouro.md`. Depois de rotulada, a
concordância e o consenso saem de `amostra_ouro.py` (ver a seção sobre a Issue #30, abaixo), e a
heurística é avaliada contra o consenso, com precisão, *recall* e F1 de cada variante:

```bash
python validacao.py --consenso validacao/consenso.csv
```

Quem for rotular não deve abrir `validacao/rotulos/*.csv` dos colegas, `consenso.csv` nem
`relatorio.md` antes de terminar, para manter a independência.

## Replicação cruzada

Para comparar uma execução replicada (por exemplo, de 30 repositórios) com o CSV original:

```bash
python -m analises.replicacao --original original.csv --replica replica.csv
python -m analises.replicacao --original original.csv --replica replica.csv --mapa mapa.json
```

O `mapa.json` (opcional) traduz os nomes de coluna do outro grupo para os usados aqui, no formato
`{"coluna do arquivo": "nome em metrics.csv"}`. A saída, em `analises/resultados/replicacao/`,
traz a diferença relativa por métrica, a concordância da classificação DORA (com kappa
ponderado) e a lista de divergências por repositório, pronta para virar Issue.

## Artigo

O artigo está em `artigo/main.tex`, no template da SBC, com `referencias.bib` e as figuras em
`artigo/figuras/`. Para compilar, no Overleaf: abrir o projeto do template SBC, substituir o
`main.tex` por este, enviar `referencias.bib` e a pasta `figuras/`. Os arquivos `sbc-template.sty`
e `sbc.bst` vêm do template. As partes pendentes estão marcadas com `TODO`.

## Estrutura

```
metricas.py          cálculo das métricas e classificação DORA
pipeline/            coleta (cliente REST/GraphQL, seleção, releases, workflow runs, variantes da RQ 07)
analises/            análises das RQs e comparação de replicação, reexecutáveis a partir dos CSVs
validacao.py         avaliação da heurística de release corretiva contra o consenso
amostra_ouro.py      sorteio, concordância (kappa de Fleiss) e consenso da amostra-ouro
validacao/           rótulos, consenso e relatório de concordância
artigo/              artigo (main.tex), bibliografia e figuras
tests/               testes pytest
config.yaml          parâmetros da execução
docs/                dicionário de dados, protocolo e seções do artigo em markdown
```

## Definições operacionais

Seguem o enunciado do laboratório: deploy = release publicada (`draft = false`,
`prerelease = false`); apenas o default branch; workflow runs com `event = push`;
`success` é sucesso, `failure`/`timed_out`/`startup_failure` são falha e as demais
conclusões são ignoradas.

Release anterior (base do `compare` no lead time): a maior versão menor que a da release,
com o mesmo prefixo de tag (`v`, `pkg@`…), publicada antes dela. Isso evita comparar um
patch de uma linha antiga (`3.6.3`) com uma release de outra linha (`4.7.2`). Tags sem versão
reconhecível usam a release anterior por data.

Release corretiva (CFR por entrega, heurística v1): a versão muda só no número de *patch* e há
ao menos um commit com `revert`, `hotfix`, `bugfix` ou `fix` entre as duas releases. Contra o
consenso da amostra-ouro, a v1 tem precisão de 0,68, *recall* de 0,78 e F1 de 0,73 (meta de 0,70).
Releases dos últimos 7 dias da janela são censuradas.

<!-- issue30-comandos -->
## Amostra-ouro e concordância — Issue #30

```powershell
python -m pip install -r requirements.txt
python amostra_ouro.py preparar
# Preencher individualmente validacao/rotulos/{avaliador}.csv
python amostra_ouro.py analisar
# Se houver empates, preencher validacao/desempates.csv após reunião e repetir.
python amostra_ouro.py verificar
```

Esta versão permite preparar e concluir com população de 100 repositórios, sem `--piloto`.
A mudança adapta o fluxo por solicitação do usuário; não substitui o mínimo de 300 do enunciado.
A opção `--piloto` continua reservada a ensaios e não autoriza fechamento. Leia `docs/protocolo-amostra-ouro.md` antes de rotular.
Os três CSVs ficam em arquivos separados, sem predições ou rótulos dos demais.
Conserve a população e as versões fixas do ambiente para reproduzir o mesmo sorteio.
Não regenerar uma planilha preenchida nem colocar rótulos fictícios para cumprir aceite.
A Issue fecha pelo merge do PR somente após análise final sem pendências e CI aprovado.
<!-- /issue30-comandos -->

<!-- issue42-rq01-04 -->
## RQ 01 a 04 e classificação C1 — Issue #42

Requer Python 3.12 e as dependências de `requirements.txt`. Não consulta a API nem refaz a mineração.

```bash
python -m analises.rq01_04
pytest tests/test_rq01_04.py tests/test_integracao_issue42.py
```

Entrada única: `data/processed/metrics.csv`. Saídas em `analises/resultados/rq01_04/`:
estatísticas (mediana, Q1, Q3 e IQR), categorias C1 com ausentes explícitos,
comparações pareadas, censura por repositório, cinco PNGs e manifesto SHA-256.
O comando também atualiza `docs/resultados-rq01-rq04.md`,
`artigo/resultados_rq01_04.tex` e as cinco figuras correspondentes em `artigo/figuras/`.
Ao enviar ao Overleaf, inclua esse `.tex` gerado junto de `main.tex` e `figuras/`.

Zeros são preservados e ausentes não são imputados. IQR é Q3-Q1, com quantis lineares.
C1 usa as colunas do CSV, com lead time (a) e CFR (a); não recalibra os limiares.
As unidades de análise são repositórios: a mediana das medianas não é a mediana de todos os episódios.
O relatório confronta H1 a H4 com os dados e separa censura de recuperação observada.
Repetições são byte a byte iguais no mesmo ambiente; versões e hashes são registrados no manifesto.
<!-- /issue42-rq01-04 -->
