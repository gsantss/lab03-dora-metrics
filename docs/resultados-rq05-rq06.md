# Resultados e discussão: RQ 05 e RQ 06

Dados: `data/processed/metrics.csv` e `repositories.csv` (300 repositórios). Reprodução:
`python -m analises.rq05_rq06` (saídas em `analises/resultados/`).

## RQ 05. Frequência de deploy × taxa de falha

Correlação de Spearman entre a frequência de deploy (releases por semana) e o CFR.

| Variante do CFR | ρ | p-valor | n |
|---|---:|---:|---:|
| (a) proxy de CI | 0,154 | 0,0076 | 300 |
| (b) proxy de entrega | 0,483 | 8,3 × 10⁻¹⁹ | 298 |

Figura (`analises/resultados/rq05_dispersao.png`): em cima, a dispersão com o eixo da frequência em escala logarítmica e a tendência LOWESS; embaixo, a mediana e o IQR do CFR em cada quartil da frequência, que é o resumo pedido no enunciado. O eixo do CFR ficou linear, porque muitos repositórios têm CFR igual a zero e o zero não existe em escala logarítmica.
Dois repositórios ficaram sem CFR (b): todas as suas releases foram censuradas, por caírem nos últimos 7 dias da janela.

**Discussão.**

- **CFR (a):** a correlação é positiva e fraca (ρ = 0,15). Ela é estatisticamente significativa (p = 0,008), mas explica pouco: o CFR de CI mediano é de apenas 4,6% e 89% dos repositórios, de qualquer frequência, ficam abaixo de 20%. A hipótese H5 esperava uma correlação nula ou levemente negativa. O resultado é compatível com a tese do DORA de que velocidade e estabilidade não são um *trade-off*, porque quem publica mais não falha de forma relevante mais vezes. Mas não confirma a parte de que os repositórios mais rápidos seriam mais estáveis.
- **CFR (b):** a correlação é positiva e moderada (ρ = 0,48), mais forte do que o "fraco e positivo" esperado na H5. A explicação mais provável está na própria definição: uma release é marcada como falha se for seguida, em até 7 dias, por uma release corretiva. Quem publica várias vezes por semana tem, por construção, mais chance de ter uma release de *patch* logo depois da anterior. Isso indica um limite do proxy, e não um *trade-off* real entre velocidade e estabilidade. A mediana do CFR (b) sobe de 0 no primeiro quartil de frequência para cerca de 0,33 no último. A curva LOWESS volta a descer acima de aproximadamente 3 releases por semana, mas isso acontece em uma região com poucos repositórios (31 com 3 ou mais releases por semana, e só 4 acima de 10), então não tratamos essa queda como um resultado.
- **Em conjunto:** os dados não sustentam um *trade-off* medido pelo CFR de CI, e o aumento do CFR (b) com a frequência é em boa parte um artefato do proxy. Correlação não implica causalidade, e a frequência pode estar associada a outras características (idade, equipe, tipo de projeto), como a RQ 06 mostra.

## RQ 06. Características associadas ao desempenho DORA

Cinco fatores contra seis métricas (frequência, lead time (a) e (b), CFR (a) e (b), tempo de recuperação), num total de 30 testes:

- **linguagem:** linguagens com menos de 10 repositórios foram agrupadas em "Outras" (grupos: TypeScript 82, Python 70, Outras 42, Go 33, Rust 32, JavaScript 27, C++ 14);
- **estrelas, contribuidores e idade:** quartis (75 repositórios por grupo; a idade é contada até 30/09/2026);
- **tipo do projeto:** só os 60 repositórios da amostra-ouro, com o rótulo de `validacao/consenso.csv` (24 aplicação/serviço, 19 biblioteca/framework, 9 CLI, 8 outro).

Com 4 ou mais grupos em todos os fatores, o teste foi sempre o de Kruskal-Wallis, com ε² = H / (n − 1) como tamanho de efeito. O Mann-Whitney e o Cliff's delta estão implementados e testados, mas nenhum fator teve só dois grupos. Os p-valores foram corrigidos por Holm nos 30 testes. Para o ε², o enunciado não fixa faixas, então usamos as de Rea e Parker: < 0,01 desprezível, < 0,04 pequeno, < 0,16 médio e o restante grande.

Figuras: `analises/resultados/rq06_efeitos.png` mostra o tamanho de efeito dos 30 testes (gráfico de pontos, círculo cheio = significativo após Holm), e `analises/resultados/rq06_distribuicoes.png` mostra, para os 10 significativos, a distribuição por grupo com os pontos de cada repositório, a mediana e o IQR. Os valores que sustentam as figuras estão em `analises/resultados/rq06_testes.csv`, que serve de tabela equivalente.

**Dez dos 30 testes seguem significativos após a correção de Holm:**

| Fator | Métrica | p (Holm) | ε² | Magnitude |
|---|---|---:|---:|---|
| idade | lead time (b) | 1,1 × 10⁻¹⁸ | 0,314 | grande |
| idade | lead time (a) | 2,5 × 10⁻¹⁶ | 0,277 | grande |
| idade | CFR (b) | 6,7 × 10⁻¹⁰ | 0,177 | grande |
| contribuidores | lead time (b) | 4,9 × 10⁻⁷ | 0,131 | médio |
| idade | frequência de deploy | 2,8 × 10⁻⁵ | 0,102 | médio |
| contribuidores | lead time (a) | 1,1 × 10⁻⁴ | 0,092 | médio |
| linguagem | lead time (a) | 0,004 | 0,089 | médio |
| linguagem | lead time (b) | 0,011 | 0,082 | médio |
| contribuidores | CFR (b) | 0,016 | 0,057 | médio |
| linguagem | CFR (b) | 0,024 | 0,074 | médio |

Os demais 20 testes não são significativos após Holm. Isso inclui todos os de **estrelas** (efeitos desprezíveis a pequenos) e todos os de **tipo do projeto** (efeitos médios em alguns casos, mas com apenas 60 repositórios e p ≥ 0,09 antes da correção).

**Direção dos efeitos (medianas por grupo).**

- **Idade** (do mais novo, Q1, ao mais antigo, Q4): o lead time (a) sobe de 83 h para 721 h, a frequência de deploy cai de 0,88 para 0,36 releases por semana e o CFR (b) cai de 0,32 para 0,03.
- **Contribuidores** (Q1 a Q4): o lead time (a) sobe de 149 h para 440 h e o CFR (b) mediano fica menor no grupo com mais contribuidores (0,09 em Q4, contra 0,20 a 0,25 nos demais). A frequência de deploy não difere de forma significativa.
- **Linguagem:** o lead time (a) mediano vai de 156 h (Python) e 173 h (TypeScript) até 1.119 h (C++), com Go (483 h) e Rust (332 h) no meio. O CFR (b) é mais alto em Python (0,24), Rust (0,21) e TypeScript (0,22), e igual a 0 em C++.

**Hipóteses da H6 frente aos resultados.**

1. *(i) Mais contribuidores, maior frequência e menor lead time:* **não confirmada.** A frequência não difere, e o lead time é **maior** nos repositórios com mais contribuidores, o oposto do esperado. Faz sentido que projetos grandes tenham um processo de release mais cuidadoso e que um commit espere mais para sair em release.
2. *(ii) Bibliotecas publicam com menos frequência e têm lead time maior:* **inconclusiva.** Não há diferença significativa por tipo de projeto, e o grupo é pequeno (60 repositórios, com 8 a 24 por categoria).
3. *(iii) Ecossistemas JS/TS, Go e Rust publicam mais que C/C++ e Java:* **não confirmada.** A frequência de deploy por linguagem não é significativa após Holm (p ajustado = 0,12). O que a linguagem diferencia é o lead time, e C++ é a que demora mais para chegar a uma release.
4. *(iv) Repositórios mais antigos têm lead time maior:* **confirmada**, com efeito grande. Os mais antigos também publicam com menos frequência e têm CFR (b) menor, coerente com o artefato do proxy discutido na RQ 05: menos releases por semana, menos releases de *patch* em sequência.

A H6 previa também "poucas diferenças ainda significativas depois da correção de Holm". Houve dez, concentradas em idade, contribuidores e linguagem, e quase todas sobre lead time e CFR (b).

## Limitações

- **Idade como confundidor.** A idade se associa a quase todas as métricas, e provavelmente a frequência, o lead time e o CFR (b) estão ligados entre si por causa dela. Os testes são univariados, então não separam esses efeitos.
- **CFR (b) é um proxy sensível à frequência**, como discutido na RQ 05. Os resultados com ele devem ser lidos com esse cuidado.
- **Tipo do projeto:** só 60 repositórios, e os rótulos vêm do consenso da amostra-ouro. A falta de significância pode ser falta de poder estatístico e não ausência de efeito.
- **Comparações múltiplas:** foram 30 testes corrigidos por Holm. Resultados com p ajustado perto de 0,05 (CFR (b) por linguagem, p = 0,024) são frágeis.
- **Linguagem:** o agrupamento em "Outras" mistura linguagens diferentes, e C++ tem só 14 repositórios.
