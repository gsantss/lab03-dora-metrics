"""Atualiza documentos e dependências sem substituir arquivos não relacionados."""
from pathlib import Path


def replace_block(path, begin, end, body):
    path=Path(path)
    content=path.read_text(encoding='utf-8-sig') if path.exists() else ''
    block=begin+'\n'+body.strip()+'\n'+end
    if begin in content:
        start=content.index(begin); stop=content.index(end,start)+len(end)
        content=content[:start]+block+content[stop:]
    else:
        content=content.rstrip()+'\n\n'+block+'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content,encoding='utf-8')

requirements=Path('requirements.txt')
text=requirements.read_text(encoding='utf-8-sig')
if '-r requirements-validacao.txt' not in text.splitlines():
    requirements.write_text(text.rstrip()+'\n-r requirements-validacao.txt\n',encoding='utf-8')

method=Path('docs/metodologia.md')
content=method.read_text(encoding='utf-8-sig') if method.exists() else '# Metodologia\n'
placeholder='*A cargo da issue #30: sorteio, protocolo de rotulagem e desempate, kappa de Fleiss e consenso.*'
body='''Nesta execução adaptada, a validação manual usa 60 repositórios de uma população de pelo menos 100, sorteados
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
rotulagem foi realizada. A avaliação da heurística frente ao consenso pertence à Issue #35.'''
if placeholder in content:
    content=content.replace(placeholder,'<!-- issue30-metodologia -->\n'+body+'\n<!-- /issue30-metodologia -->')
    method.write_text(content,encoding='utf-8')
else:
    replace_block(method,'<!-- issue30-metodologia -->','<!-- /issue30-metodologia -->','## Validação manual e concordância\n\n'+body)

replace_block('README.md','<!-- issue30-comandos -->','<!-- /issue30-comandos -->','''## Amostra-ouro e concordância — Issue #30

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
A Issue fecha pelo merge do PR somente após análise final sem pendências e CI aprovado.''')

replace_block('.gitignore','# issue30-historico','# /issue30-historico','validacao/historico/\nvalidacao-piloto/historico/')
