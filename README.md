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
- `commits.csv.gz`: commits incluídos em cada release (base do lead time e do CFR por entrega);
- `ignored_releases.csv`: releases fora do cálculo de lead time e o motivo;
- `workflow_runs.csv.gz`: workflow runs válidos do default branch (base do CFR por CI e do tempo de recuperação).

Os dois maiores saem comprimidos para caber no limite de 100 MB por arquivo do GitHub;
o pandas lê direto: `pd.read_csv("data/processed/commits.csv.gz")`.

O dicionário de dados de cada coluna está em [docs/dicionario-de-dados.md](docs/dicionario-de-dados.md).

## Estrutura

```
metricas.py          cálculo das métricas e classificação DORA
pipeline/            coleta (cliente REST, seleção, releases, workflow runs, collect)
tests/               testes pytest
config.yaml          parâmetros da execução
docs/                dicionário de dados e introdução do artigo
```

## Definições operacionais

Seguem o enunciado do laboratório: deploy = release publicada (`draft = false`,
`prerelease = false`); apenas o default branch; workflow runs com `event = push`;
`success` é sucesso, `failure`/`timed_out`/`startup_failure` são falha e as demais
conclusões são ignoradas.

Release corretiva (CFR por entrega, heurística v1, a validar na amostra-ouro): a versão
muda só no número de *patch* e há ao menos um commit com `revert`, `hotfix`, `bugfix` ou
`fix` entre as duas releases. Releases dos últimos 7 dias da janela são censuradas.
