# Issue #30 — Protocolo de validação manual

## Sorteio e reprodução

A população é `data/processed/repositories.csv` da amostra final S02 (>=300 repositórios), e as releases estão em `data/processed/releases.csv`. Ordenamos repositórios por `full_name` e executamos `df.sample(n=60, random_state=42)`. Para cada selecionado, ordenamos suas releases por `release_id` e `tag_name` como strings e sorteamos cinco com `sample(n=5, random_state=42)`. Sem reposição em ambos os níveis. Não substituímos silenciosamente repositórios com menos de cinco releases. Se o snapshot trouxer o mesmo tag em IDs diferentes, mantemos o maior ID (ordenação por comprimento e valor do ID) para não sortear o mesmo link duas vezes; as exclusões ficam registradas em `duplicate_tag_exclusions` do manifesto. IDs repetidos são erro de integridade.

`validacao/manifesto.json` congela os 300 itens, os hashes SHA256 dos datasets, a semente 42 e as versões do pandas/numpy. As três planilhas são CSVs UTF-8 com BOM. Reexecutar preparação preserva todos os rótulos existentes e recusa mudança na amostra. Para nova coleta ou outro ambiente, use outra pasta de saída e refaça as avaliações; não reutilize os rótulos da amostra anterior. Fixe o ambiente usando `requirements-validacao.txt`.

`--piloto` permite testar com a amostra de 100 da S01; saídas são identificadas como piloto e não autorizam o encerramento da Issue. Para finalizar, use os dados de >=300 e gere a amostra final em uma pasta nova, ou arquive/mova integralmente a pasta piloto antes de gerar a final.

## Avaliação independente

Cada participante recebe apenas seu CSV e este protocolo, sem rótulos dos colegas, consenso, resultados de concordância ou predições da heurística. As planilhas têm somente identificação, links e campos de entrada. A ausência de predições nos arquivos não impede que o avaliador encontre outros dados no repositório: a independência depende também do procedimento dos participantes.

- `validacao/rotulos/gsantss.csv`
- `validacao/rotulos/arthies2323.csv`
- `validacao/rotulos/PortoPedro.csv`

Cada participante preenche sozinho:

1. `tipo_projeto`: `biblioteca/framework`, `aplicacao/servico`, `ferramenta cli` ou `outro`.
2. `entrega_real`: `sim`, `nao` ou `incerto`, conforme as releases representem entregas reais para usuários.
3. `corretiva`: `sim` ou `nao` para cada uma das cinco releases, pela leitura das notas e dos commits. O objetivo principal deve ser corrigir um defeito recente, e não apenas incluir uma alteração isolada de manutenção.

Os dois primeiros campos são do repositório: basta preenchê-los na primeira das suas cinco linhas. Se repetidos nas outras, devem ser iguais. `corretiva` é obrigatória em todas as 300 linhas. Não editar IDs, tags, links nem excluir/adicionar releases. Acentos como `não` são aceitos e normalizados somente na análise; os arquivos originais são preservados. Cada integrante deve versionar seu próprio arquivo após terminar a avaliação. Não atribuir autoria de colegas automaticamente.

## Concordância e consenso

Somente após receber os três arquivos completos, calcular kappa de Fleiss com `aggregate_raters` seguido de `fleiss_kappa(method='fleiss')`. Usar 60 itens nas dimensões de repositório e 300 na dimensão corretiva. Não contar o mesmo repositório cinco vezes. O kappa é calculado sobre os votos independentes originais, antes de qualquer conciliação.

Escala de Landis e Koch (1977): negativo = pobre; 0–0,20 = leve; >0,20–0,40 = razoável; >0,40–0,60 = moderada; >0,60–0,80 = substancial; >0,80–1 = quase perfeita. Se todos os votos forem da mesma categoria, a concordância esperada é 1 e o kappa é matematicamente indefinido: reportar valor nulo e justificativa, sem inventar kappa=1. Reportar também concordâncias observada/esperada e número de itens.

Aplicar maioria simples. Um empate 1-1-1 (possível em tipo do projeto e entrega real) fica em `pendencias.csv`. Copiar suas linhas para `desempates.csv` e, em reunião dos três, preencher decisão, justificativa, participantes separados por `;` e data real ISO `AAAA-MM-DD`. Nunca usar desempate automático arbitrário nem alterar os rótulos originais para aumentar concordância. A saída `consenso.csv` só é produzida sem pendências e é compatível com a avaliação de heurística da Issue #35.

`auditoria_consenso.csv` registra votos e método. `conclusao.json` registra hashes dos insumos e das saídas. Reanalisar invalida/arquiva o consenso anterior antes de validar as entradas, para não deixar um consenso desatualizado parecendo válido. O sistema valida completude, categorias, identidade e consistência; não pode comprovar sozinho que uma pessoa realizou a avaliação sem consultar os colegas.

## Comandos

```powershell
python -m pip install -r requirements.txt -r requirements-validacao.txt
python amostra_ouro.py preparar
# Somente ensaio com os 100 atuais: python amostra_ouro.py preparar --piloto
# Cada integrante preenche seu CSV de forma independente.
python amostra_ouro.py analisar
# Resolver eventuais empates em validacao/desempates.csv e repetir.
python amostra_ouro.py verificar
python -m pytest --cov=metricas --cov-report=term-missing --cov-fail-under=80
```

Distribua os arquivos de forma privada durante a avaliação para preservar independência. Reúna-os apenas depois de os três terem concluído. Os testes sintéticos ficam nos testes automatizados, nunca nos CSVs de rótulos reais.

## Metodologia do artigo

A subseção 2.6 de `docs/metodologia.md` descreve o procedimento. Resultados reais de kappa são gerados em `validacao/relatorio.md` após a análise dos rótulos. Não declarar a avaliação concluída enquanto houver entradas faltantes, empates ou população apenas piloto.

Referências: Landis, J. R.; Koch, G. G. The Measurement of Observer Agreement for Categorical Data. Biometrics 33(1), 1977, p.159–174. Statsmodels: https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.aggregate_raters.html e https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.fleiss_kappa.html.
