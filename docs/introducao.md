# 1. Introdução

> *Seção escrita no Lab03S01, antes da coleta completa e de qualquer observação dos
> dados. As hipóteses abaixo registram o que o grupo esperava encontrar, e não devem
> ser reescritas depois dos resultados: a comparação entre hipótese e resultado é feita
> na Discussão.*

## 1.1 Contexto

As métricas DORA (*DevOps Research and Assessment*) tornaram-se a referência de mercado
para medir o desempenho de entrega de software. Popularizadas por Forsgren, Humble e Kim
(2018) e atualizadas anualmente pelos relatórios *Accelerate State of DevOps*, elas
combinam duas dimensões. A **velocidade** é medida pela frequência de deploys
(*deployment frequency*) e pelo tempo entre um commit e sua entrega (*lead time for
changes*). A **estabilidade** é medida pela proporção de deploys que causam falha
(*change failure rate*, CFR) e pelo tempo de recuperação após um deploy com falha
(chamado de *failed deployment recovery time* desde 2023). Em 2024 o DORA acrescentou uma
quinta métrica, a *deployment rework rate*, que é a proporção de deploys não planejados,
feitos para corrigir problemas. A tese central desses relatórios é que velocidade e
estabilidade **não** formam um *trade-off*: as equipes de melhor desempenho se saem bem
nas duas dimensões.

Em projetos open-source hospedados no GitHub, essas métricas não podem ser observadas
diretamente, porque a plataforma não registra "deploys em produção" nem "falhas em
produção". O que existe são *releases* publicadas, execuções de *workflows* de CI/CD no
GitHub Actions e commits. Medir DORA nesse contexto exige, portanto, **proxies**: uma
release publicada passa a representar um deploy, e uma execução de CI com falha passa a
representar uma falha. Proxies podem enganar. Uma biblioteca que publica uma versão por
mês não está colocando nada em produção, porque quem faz o deploy são seus usuários. Um
teste instável que falha no CI não é um incidente percebido por ninguém fora do projeto.

## 1.2 Objetivo

Este estudo minera automaticamente as métricas DORA de repositórios open-source populares
(mais de 1.000 estrelas) que usam GitHub Actions. Os dados vêm das APIs públicas do
GitHub, em uma janela de observação de 12 meses comum a toda a turma, e os critérios de
inclusão, as definições operacionais e suas variantes estão descritos na Metodologia.
Além de calcular as métricas, o estudo pergunta **o quanto se pode confiar nelas**, por
dois caminhos:

1. **validando** os critérios automáticos contra o julgamento humano em uma amostra-ouro
   de 60 repositórios rotulada de forma independente por três avaliadores; e
2. **medindo a sensibilidade** da classificação DORA (Elite, High, Medium e Low) a
   escolhas de definição operacional, como a unidade de deploy e as variantes de lead
   time e de CFR.

## 1.3 Questões de pesquisa e hipóteses informais

- **RQ 01.** Qual a frequência de deploys dos repositórios populares que usam CI/CD?
- **RQ 02.** Qual o tempo entre um commit e seu respectivo deploy?
- **RQ 03.** Qual a taxa de falha das mudanças entregues por esses repositórios?
- **RQ 04.** Qual o tempo de recuperação após uma execução de CI/CD com falha?
- **RQ 05.** Repositórios com maior frequência de deploy apresentam maior ou menor taxa de falha?
- **RQ 06.** Quais características dos repositórios estão associadas a um melhor desempenho DORA?
- **RQ 07.** O quanto a classificação DORA de um repositório depende da definição operacional escolhida?
- **RQ 08** *(bônus, opcional).* Qual a taxa de retrabalho (*rework rate*) desses repositórios?

**H1 (frequência de deploy).** Esperamos uma frequência mediana **abaixo de uma release
por semana**, com a maioria dos repositórios na faixa *Medium* (entre uma por mês e uma
por semana) e uma cauda longa à direita. Poucos projetos devem atingir *High* ou *Elite*,
e esses tendem a ser os que automatizam a publicação (por exemplo, com bots de release ou
publicações a cada merge). Em open-source, uma release costuma empacotar muitas mudanças
para os usuários, em vez de colocar cada mudança no ar assim que fica pronta.

**H2 (lead time).** Esperamos que a variante **por commit (b)** fique na faixa de dias a
poucas semanas (*High*/*Medium*) e que a variante **por release (a)** seja
sistematicamente maior, com muitos repositórios acima de 30 dias (*Low*). A variante (a)
depende apenas do commit mais antigo da release: um único commit escrito muito antes,
vindo de um branch de longa duração ou de um PR que demorou a ser revisado, basta para
inflá-la. Esperamos que essa diferença seja maior nos repositórios que publicam menos
releases, porque cada release acumula mais commits.

**H3 (taxa de falha).** Para a variante **de CI (a)**, esperamos uma mediana entre 10% e
25% (*Elite*/*High*). Os pushes no default branch, na maioria, já passaram pelos testes do
pull request, mas ainda sobram testes instáveis, dependências externas e workflows
auxiliares (documentação, lint, publicação). Para a variante **de entrega (b)**,
esperamos valores **menores**, com a maioria dos repositórios abaixo de 15% e muitos
exatamente em zero, porque exigir uma release que muda só o *patch*, com commit de
correção, em até 7 dias é um critério restritivo. Esperamos ainda uma **correlação fraca
entre (a) e (b)**, já que elas medem fenômenos diferentes: falha de pipeline e correção
publicada.

**H4 (tempo de recuperação).** Esperamos uma mediana da ordem de **horas** (*High*, entre
1 hora e 1 dia). Uma falha no default branch é visível e atrapalha toda a equipe, e falhas
de testes instáveis se resolvem com uma nova execução em minutos. Esperamos também uma
cauda longa, com workflows que ficam quebrados por dias, e uma proporção pequena, mas
não desprezível, de **episódios censurados** (falhas não recuperadas até o fim da janela),
maior nos repositórios com muitos workflows auxiliares.

**H5 (velocidade × estabilidade).** Para o CFR **de CI (a)**, esperamos uma correlação de
Spearman **fraca ou nula**, possivelmente levemente negativa, o que estaria de acordo com
a tese do DORA: projetos que publicam com mais frequência tendem a ter automação mais
madura. Para o CFR **de entrega (b)**, esperamos uma correlação **fraca e positiva**, em
parte como artefato da definição: quanto mais releases por semana, maior a chance de uma
release de *patch* cair a menos de 7 dias da anterior. Se isso se confirmar, indica um
limite do proxy, e não um *trade-off* real entre velocidade e estabilidade.

**H6 (características dos repositórios).** Pretendemos comparar pelo menos linguagem
principal, número de contribuidores, idade e tipo do projeto. Esperamos que (i)
repositórios com **mais contribuidores** tenham maior frequência de deploy e menor lead
time, sem diferença clara de CFR; (ii) **bibliotecas e frameworks** publiquem com menos
frequência e tenham lead time maior que ferramentas de linha de comando e aplicações;
(iii) ecossistemas com publicação automatizada de pacotes (JavaScript/TypeScript, Go,
Rust) tenham frequência maior que C/C++ e Java; e (iv) repositórios **mais antigos**
tenham lead time maior, por terem processos de release mais conservadores. Esperamos
tamanhos de efeito pequenos a médios, com poucas diferenças ainda significativas depois
da correção de Holm.

**H7 (sensibilidade à definição).** Esperamos que a classificação seja **sensível** à
definição: que ao menos 30% dos repositórios mudem de categoria geral entre a combinação
de referência e pelo menos uma alternativa, com kappa de Cohen ponderado apenas moderado
(entre 0,4 e 0,6). As maiores mudanças devem vir do uso de **tags** como unidade de deploy
(monorepos que criam uma tag por pacote, projetos que criam tags sem publicar releases) e
da inclusão de **pré-releases** (projetos com versões *rc*, *beta* ou *nightly*
frequentes). Esperamos que a maioria das mudanças aconteça entre categorias vizinhas, por
exemplo de *High* para *Medium*.

**H8 (bônus, opcional: taxa de retrabalho).** Se o grupo fizer a RQ 08, a opção prevista é
a *rework rate*. Esperamos que ela seja **maior que o CFR de entrega (b)**, porque conta
toda release corretiva sem a janela de 7 dias e sem censura, mas da mesma ordem de
grandeza (10% a 25%), e fortemente correlacionada com o CFR (b), já que ambas dependem da
mesma heurística de release corretiva.

## 1.4 Ameaças iniciais de construto

Antes de coletar os dados, já identificamos ameaças à validade de construto, ou seja,
pontos em que podemos não estar medindo o que pretendemos. Elas serão quantificadas na
validação manual (Lab03S02) e na análise de sensibilidade (Lab03S03):

- **Release ≠ deploy.** Em bibliotecas e frameworks, a release disponibiliza uma versão,
  mas o deploy é feito pelos usuários. A rotulagem manual registra, por repositório, se as
  releases representam entregas reais ao usuário.
- **Falha de CI ≠ falha em produção.** O CFR de CI mede a instabilidade do pipeline, o que
  inclui testes instáveis e workflows que não entregam nada, e não incidentes percebidos
  pelos usuários.
- **Heurística de release corretiva.** Projetos que não seguem o Versionamento Semântico,
  que usam versionamento por calendário ou que misturam correções em releases de novas
  funcionalidades podem ser classificados incorretamente. A heurística será avaliada com
  precisão, recall e F1 contra a amostra-ouro.
- **Data do commit.** `commit.author.date` registra quando a mudança foi escrita e é
  preservada em rebases, *squash merges* e *cherry-picks*, o que pode inflar o lead time.
- **Ordem das releases.** As releases são ordenadas pela data de publicação. Em projetos
  que mantêm várias linhas de versão em paralelo (com *backports*), a "release anterior"
  pode pertencer a outra linha, e a comparação de commits reflete isso.
- **Recuperação pelo CI.** O tempo de recuperação usa apenas execuções do default branch
  disparadas por `push`. Uma nova execução bem-sucedida do mesmo commit (*re-run*) conta
  como recuperação, mesmo sem nenhuma correção no código.

## 1.5 Organização do artigo

A Seção 2 descreve a metodologia: fonte de dados, funil de seleção, janela, definições
operacionais e protocolo de validação manual. A Seção 3 apresenta os resultados por
questão de pesquisa, e a Seção 4 os discute à luz das hipóteses acima. A Seção 5 detalha
as ameaças à validade, e a Seção 6 relata a replicação cruzada do pipeline por outro grupo.

## Referências

- Forsgren, N.; Humble, J.; Kim, G. *Accelerate: The Science of Lean Software and
  DevOps*. IT Revolution, 2018.
- DORA. *Accelerate State of DevOps* (relatórios anuais) e *DORA's software delivery
  metrics: the four keys*. Disponível em <https://dora.dev/>.
- DORA. *A history of DORA's software delivery metrics*. Disponível em
  <https://dora.dev/insights/dora-metrics-history/>.
