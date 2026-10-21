# 3.7 RQ 07: sensibilidade à definição operacional

> Reproduzível a partir dos CSVs: `python -m pipeline --config config.yaml --variants` coleta as
> unidades de deploy alternativas, e `python -m analises.rq07 --config config.yaml` gera as
> tabelas em `analises/resultados/`.

## Resultados

Comparamos a classificação DORA dos 300 repositórios em três combinações de definições
operacionais. As combinações mudam ao mesmo tempo a unidade de deploy e as variantes de lead
time e de CFR:

| Combinação | Unidade de deploy | Unidades na janela | Lead time | CFR |
|---|---|---|---|---|
| C1 (referência) | release | 22.005 | (a) por release | (a) proxy de CI |
| C2 | release + pré-release | 28.454 (6.449 pré-releases) | (b) por commit | (b) proxy de entrega |
| C3 | tag (datada pelo commit apontado) | 51.392 (29.432 sem release) | (b) por commit | (a) proxy de CI |

O tempo de recuperação vem dos workflow runs e é o mesmo nas três combinações. Entre 15 e 17
repositórios ficam sem classificação geral em cada combinação, por falta de alguma métrica.

**Tabela 7.1. Métricas em cada combinação: mediana [IQR].**

| Combinação | Frequência (deploys/semana) | Lead time (h) | CFR |
|---|---|---|---|
| C1 | 0,52 [0,25; 1,21] | 239 [103; 796] | 0,046 [0,023; 0,112] |
| C2 | 0,65 [0,31; 1,38] | 194 [74; 531] | 0,152 [0,018; 0,354] |
| C3 | 0,90 [0,36; 2,16] | 183 [72; 486] | 0,046 [0,023; 0,112] |

**Tabela 7.2. Distribuição da classificação geral.**

| Combinação | Elite | High | Medium | Low | Sem classificação |
|---|---|---|---|---|---|
| C1 | 20 | 122 | 130 | 12 | 16 |
| C2 | 10 | 118 | 145 | 10 | 17 |
| C3 | 24 | 150 | 105 | 6 | 15 |

**Tabela 7.3. Concordância entre as combinações** (apenas repositórios classificados nas duas).

| Par | n | Mudaram de categoria | Subiram / desceram | Entre vizinhas | Kappa ponderado (linear) |
|---|---|---|---|---|---|
| C1 × C2 | 283 | 74 (26,1%) | 29 / 45 | 69 (93%) | 0,580 (moderada) |
| C1 × C3 | 284 | 69 (24,3%) | 54 / 15 | 67 (97%) | 0,645 (substancial) |
| C2 × C3 | 283 | 67 (23,7%) | 63 / 4 | 65 (97%) | 0,639 (substancial) |

**Tabela 7.4. % de repositórios que mudam de categoria em cada métrica.**

| Par | Frequência | Lead time | CFR | Recuperação |
|---|---|---|---|---|
| C1 × C2 | 11,3% | 46,5% | 54,0% | 0,0% |
| C1 × C3 | 25,7% | 49,5% | 0,0% | 0,0% |
| C2 × C3 | 14,7% | 13,0% | 54,0% | 0,0% |

## Discussão

**Frente à hipótese H7.** A hipótese previa que ao menos 30% dos repositórios mudariam de
categoria geral, com kappa ponderado entre 0,4 e 0,6, e que a maioria das mudanças seria entre
categorias vizinhas. Ela foi confirmada só em parte:

- **Mudanças de categoria abaixo do previsto.** Entre 23,7% e 26,1% dos repositórios mudam de
  categoria geral, menos que os 30% esperados.
- **Kappa no limite superior ou acima da faixa.** A concordância é moderada entre C1 e C2 (0,580)
  e substancial nos outros pares (0,645 e 0,639), na escala de Landis e Koch (1977).
- **Mudanças entre vizinhas confirmadas.** Entre 93% e 97% das mudanças são de uma única
  categoria (por exemplo, de High para Medium); quase nenhum repositório salta duas faixas.

**A estabilidade da classificação geral esconde mudanças grandes em cada métrica.** Com
releases ou tags, e lead time (a) ou (b), a categoria de lead time muda em cerca de metade dos
repositórios. Com CFR (a) ou (b), a categoria de CFR muda em 54%. A classificação geral muda bem
menos por dois motivos:

- ela é a mediana das quatro notas, e uma única métrica que muda de faixa raramente desloca essa
  mediana;
- o tempo de recuperação é o mesmo nas três combinações e funciona como âncora.

Parte da robustez observada é, portanto, um efeito mecânico da forma de agregação, e não uma
evidência de que as métricas medem a mesma coisa.

**As alternativas mudam a classificação em direções opostas.** Usar tags (C3) **melhora** a
classificação: 54 repositórios sobem e 15 descem em relação à C1. Muitos projetos criam tags sem
publicar releases, como uma tag por pacote em monorepos ou *builds* de integração. Isso eleva a
frequência mediana de 0,52 para 0,90 deploy por semana. O lead time também cai, de 239 h para
183 h, em parte porque a C3 usa a variante (b) e em parte porque cada tag agrupa menos commits
que uma release: com a mesma variante (b), a C2 fica em 194 h. Incluir pré-releases e usar o proxy de entrega (C2) **piora** a
classificação: 45 repositórios descem e 29 sobem. O motivo principal é o CFR, cuja mediana sobe
de 4,6% (CI) para 15,2% (entrega): falhas de pipeline no default branch são raras, enquanto
releases de correção logo após uma release são comuns.

**Limitação desta análise.** Cada combinação altera mais de uma definição ao mesmo tempo, então
não é possível atribuir uma mudança de categoria a uma única escolha. A Tabela 7.4 ajuda a
separar parte desses efeitos. Entre C1 e C3, o CFR não muda e toda a diferença vem da unidade de
deploy e do lead time. Entre C2 e C3, o lead time usa a mesma variante e a diferença vem da
unidade e do CFR.

**Implicação para as RQ 01 a 06.** As conclusões sobre a **classificação geral** são
moderadamente robustas: cerca de três em cada quatro repositórios mantêm a categoria. As
conclusões **por métrica** não são: a faixa de lead time e a de CFR dependem da variante
escolhida, e a frequência de deploy depende de contar releases ou tags. Por isso, os resultados
das RQ 02, 03 e 05 devem ser lidos sempre com as duas variantes lado a lado, e a frequência de
deploy, como uma medida de **publicação de versões**, não de deploy em produção.

# 3.8 RQ 08 (bônus): rework rate

## Resultados

Calculamos a *deployment rework rate*, a fração das releases da janela que são corretivas
segundo a mesma heurística do CFR (b). Uma release é corretiva quando muda só o número de
*patch* e contém ao menos um commit de `fix`, `hotfix`, `bugfix` ou `revert`. A rework rate
mediana é **0,60** [IQR 0,33; 0,80], contra **0,18** [0,02; 0,40] do CFR (b) nos mesmos
298 repositórios. A rework rate supera o CFR (b) em 263 deles (88%). A correlação de Spearman
entre as duas é positiva, mas fraca: ρ = 0,315 (p < 0,001).

## Discussão

A hipótese H8 previa uma rework rate maior que o CFR (b), da mesma ordem de grandeza (10% a
25%) e fortemente correlacionada com ele:

- **Rework maior que o CFR (b): confirmado.**
- **Mesma ordem de grandeza: refutado.** A mediana de 60% é bem maior que a esperada.
- **Correlação forte: refutado.** A correlação é fraca.

A diferença de magnitude se explica pela heurística. Em projetos que usam mensagens no padrão
*Conventional Commits*, quase toda release de *patch* contém algum commit `fix:`. Assim, a
rework rate passa a medir sobretudo a **proporção de releases de patch**, um traço da política de
versionamento do projeto, e não o retrabalho não planejado que o DORA pretende capturar. O CFR (b)
é mais restritivo, porque exige que a correção chegue em até 7 dias depois da release avaliada.
Isso faz o CFR (b) depender também do ritmo de publicação, o que ajuda a explicar a correlação
fraca entre as duas medidas.

Os dois resultados dependem da validade da heurística de release corretiva (seção 2.7). Se a
heurística marca como corretivas releases que não são, a rework rate e o CFR (b) ficam
superestimados na mesma proporção.
