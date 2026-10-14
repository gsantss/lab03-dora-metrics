"""Issue #30: sorteio cego, concordância original e consenso auditável.

python amostra_ouro.py preparar [--piloto]
python amostra_ouro.py analisar
python amostra_ouro.py verificar
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import unicodedata
from urllib.parse import quote

import numpy as np
import pandas as pd
from statsmodels.stats.inter_rater import aggregate_raters, fleiss_kappa

RATERS = ('gsantss', 'arthies2323', 'PortoPedro')
SEED = 42
DIMENSIONS = {
    'tipo_projeto': ('biblioteca/framework', 'aplicacao/servico', 'ferramenta cli', 'outro'),
    'entrega_real': ('sim', 'nao', 'incerto'),
    'corretiva': ('sim', 'nao'),
}
META = ['full_name', 'repo_url', 'release_id', 'tag_name', 'release_url']
FIELDS = META + list(DIMENSIONS)
KEYS = ['full_name', 'release_id']

class Pending(ValueError):
    """Entradas humanas ou amostra final ainda pendentes."""

def normal(value):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(value).strip().lower()) if not unicodedata.combining(c))
    return ' '.join(text.split())

def read_csv(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')

def write_csv(path, rows, fields):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    tmp.replace(path)

def write_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    tmp.replace(path)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def unique_releases(releases):
    if releases.duplicated(KEYS).any():
        raise ValueError('Release duplicada no dataset (mesmo ID)')
    # Mesmo tag pode aparecer em IDs diferentes no snapshot; nao sortear o mesmo link duas vezes.
    work=releases.copy()
    work['_id_length']=work.release_id.str.len()
    work=work.sort_values(['full_name','tag_name','_id_length','release_id'],kind='stable')
    duplicate=work.duplicated(['full_name','tag_name'],keep='last')
    exclusions=work.loc[duplicate,['full_name','release_id','tag_name']].to_dict('records')
    return work.loc[~duplicate].drop(columns='_id_length'),exclusions

def draw(repositories, releases, seed=SEED, n=60, per_repo=5):
    if repositories.full_name.duplicated().any():
        raise ValueError('Repositório duplicado no dataset')
    releases, _ = unique_releases(releases)
    if len(repositories) < n:
        raise Pending(f'São necessários {n} repositórios; recebidos {len(repositories)}')
    names = repositories.sort_values('full_name', kind='stable').sample(n=n, random_state=seed).full_name.tolist()
    rows = []
    for name in names:
        pool = releases.loc[releases.full_name.eq(name)].sort_values(['release_id','tag_name'], kind='stable')
        if len(pool) < per_repo:
            raise Pending(f'{name}: menos de {per_repo} releases; não substituir silenciosamente o repositório')
        selected = pool.sample(n=per_repo, random_state=seed)
        for release in selected.to_dict('records'):
            tag = release['tag_name']
            rows.append({'full_name':name, 'repo_url':f'https://github.com/{name}', 'release_id':release['release_id'], 'tag_name':tag,
                         'release_url':f'https://github.com/{name}/releases/tag/{quote(tag, safe="")}'})
    return rows

def prepare(repositories, releases, directory, pilot=False):
    directory = Path(directory)
    repos = read_csv(repositories); rels = read_csv(releases)
    if len(repos) < 300 and not pilot:
        raise Pending(f'Amostra S02 exige pelo menos 300 repositórios; recebidos {len(repos)}. Use --piloto apenas para ensaio.')
    old_manifest = directory/'manifesto.json'
    if old_manifest.exists():
        old = json.loads(old_manifest.read_text(encoding='utf-8'))
        hashes = {'repositories.csv':digest(repositories),'releases.csv':digest(releases)}
        if old.get('source_sha256') != hashes:
            raise ValueError('Dataset mudou. Preserve a pasta atual e escolha outra --saida para novo sorteio.')
    # Não selecione colunas da heurística, mensagens de commits ou métricas.
    unique, exclusions = unique_releases(rels[['full_name','release_id','tag_name']])
    rows = draw(repos[['full_name']], unique)
    manifest = {'schema':1, 'seed':SEED, 'repositories':60, 'releases_per_repository':5,
                'population_count':len(repos), 'pilot':bool(pilot), 'duplicate_tag_exclusions':exclusions,
                'pandas_version':pd.__version__, 'numpy_version':np.__version__,
                'source_sha256':{'repositories.csv':digest(repositories),'releases.csv':digest(releases)}, 'sample':rows}
    dest = directory/'manifesto.json'
    # Primeiro valide a identidade e TODOS os arquivos antes de escrever qualquer um.
    if dest.exists() and json.loads(dest.read_text(encoding='utf-8')) != manifest:
        raise ValueError('Dataset/ambiente/sorteio mudou. Preserve a pasta atual e escolha outra --saida para novo sorteio.')
    expected = pd.DataFrame(rows)
    for rater in RATERS:
        target = directory/'rotulos'/f'{rater}.csv'
        if target.exists():
            old = read_csv(target)
            if list(old.columns) != FIELDS or old[META].sort_values(KEYS).to_dict('records') != expected[META].sort_values(KEYS).to_dict('records'):
                raise ValueError(f'{target}: identidade ou ordem da amostra alterada; arquivo não sobrescrito')
    write_json(dest, manifest)
    write_csv(directory/'amostra.csv', rows, META)
    for rater in RATERS:
        target = directory/'rotulos'/f'{rater}.csv'
        if not target.exists():
            write_csv(target, [dict(row, tipo_projeto='', entrega_real='', corretiva='') for row in rows], FIELDS)
    # Os arquivos preenchidos nunca são regenerados nem substituídos.
    return manifest

def load_labels(directory, manifest):
    expected = {(r['full_name'],r['release_id']):r for r in manifest['sample']}
    outputs = {}
    for rater in RATERS:
        path = Path(directory)/'rotulos'/f'{rater}.csv'
        if not path.exists(): raise Pending(f'Falta o arquivo de {rater}: {path}')
        frame = read_csv(path)
        if list(frame.columns) != FIELDS or frame.duplicated(KEYS).any():
            raise ValueError(f'{rater}: colunas inválidas ou chaves duplicadas')
        actual = {(r.full_name,r.release_id) for r in frame.itertuples()}
        if actual != set(expected): raise ValueError(f'{rater}: faltam/sobram releases da amostra')
        repo_labels = {}
        for name, part in frame.groupby('full_name', sort=True):
            for dim in ('tipo_projeto','entrega_real'):
                values = {normal(v) for v in part[dim] if normal(v)}
                if not values: raise Pending(f'{rater}: preencher {dim} em {name}')
                if len(values)!=1 or not values.issubset(DIMENSIONS[dim]):
                    raise ValueError(f'{rater}: {dim} inconsistente/inválido em {name}: {values}')
                repo_labels[(name,dim)] = next(iter(values))
        normalized = {}
        for row in frame.to_dict('records'):
            key = (row['full_name'],row['release_id'])
            if any(row[field] != expected[key][field] for field in META):
                raise ValueError(f'{rater}: identidade/links alterados em {key}')
            value = normal(row['corretiva'])
            if not value: raise Pending(f'{rater}: preencher corretiva em {key}')
            if value not in DIMENSIONS['corretiva']: raise ValueError(f'{rater}: corretiva inválida em {key}')
            normalized[key] = {'corretiva':value, **{d:repo_labels[(key[0],d)] for d in ('tipo_projeto','entrega_real')}}
        outputs[rater] = normalized
    return outputs

def interpretation(value):
    if value is None: return 'indefinido (sem variabilidade nas categorias)'
    if value < 0: return 'pobre'
    for limit, label in ((.20,'leve'),(.40,'razoavel'),(.60,'moderada'),(.80,'substancial'),(1.000001,'quase perfeita')):
        if value <= limit: return label
    raise ValueError('Kappa fora do intervalo esperado')

def agreement(matrix):
    data = np.asarray(matrix)
    if data.ndim != 2 or data.shape[1] != 3 or len(data)==0:
        raise ValueError('São exigidos itens completos de três avaliadores')
    # Chamada solicitada pelo enunciado: itens x avaliadores -> contagens por categoria.
    table, _ = aggregate_raters(data)
    proportions = table.sum(axis=0)/table.sum()
    observed = float(np.mean((np.sum(table**2,axis=1)-3)/6))
    expected = float(np.sum(proportions**2))
    value = None if math.isclose(expected,1.0) else float(fleiss_kappa(table, method='fleiss'))
    if value is not None and not math.isfinite(value): raise ValueError('Kappa não finito')
    return {'kappa':value, 'interpretacao':interpretation(value),'itens':len(data),'avaliadores':3,
            'concordancia_observada':observed,'concordancia_esperada':expected}

def votes(labels, sample):
    tasks = []
    for name in sorted({r['full_name'] for r in sample}):
        first = next(r for r in sample if r['full_name']==name)
        key = (name,first['release_id'])
        for dim in ('tipo_projeto','entrega_real'):
            tasks.append({'full_name':name,'release_id':'','dimensao':dim,'votos':[labels[a][key][dim] for a in RATERS]})
    for row in sample:
        key = (row['full_name'],row['release_id'])
        tasks.append({'full_name':key[0],'release_id':key[1],'dimensao':'corretiva','votos':[labels[a][key]['corretiva'] for a in RATERS]})
    return tasks

DECISION_FIELDS = ['full_name','release_id','dimensao','decisao','justificativa','participantes','data_reuniao']

def analyze(directory, require_final=False):
    directory = Path(directory)
    # Falha posterior não pode deixar um consenso anterior parecendo atualizado.
    for name in ('consenso.csv','conclusao.json','kappa.json','relatorio.md','auditoria_consenso.csv','pendencias.csv'):
        target=directory/name
        if target.exists():
            backup=directory/'historico';backup.mkdir(exist_ok=True)
            archived=backup/(target.stem+'-'+digest(target)[:16]+target.suffix)
            if archived.exists():
                target.unlink()
            else:
                target.replace(archived)
    manifest = json.loads((directory/'manifesto.json').read_text(encoding='utf-8'))
    if manifest.get('schema')!=1 or len(manifest['sample'])!=300 or len({r['full_name'] for r in manifest['sample']})!=60:
        raise ValueError('Manifesto deve conter exatamente 60 repositórios e 300 releases')
    labels = load_labels(directory, manifest)
    tasks = votes(labels, manifest['sample'])
    report = {dim:agreement([t['votos'] for t in tasks if t['dimensao']==dim]) for dim in DIMENSIONS}
    write_json(directory/'kappa.json',report)
    decisions_path=directory/'desempates.csv'
    decisions={}
    if decisions_path.exists():
        df=read_csv(decisions_path)
        if list(df.columns)!=DECISION_FIELDS or df.duplicated(['full_name','release_id','dimensao']).any():
            raise ValueError('Desempates com colunas inválidas ou chaves duplicadas')
        decisions={(r['full_name'],r['release_id'],r['dimensao']):r for r in df.to_dict('records')}
    resolved={}; pendings=[]; audit=[]; used=set()
    for task in tasks:
        key=(task['full_name'],task['release_id'],task['dimensao'])
        label,count=Counter(task['votos']).most_common(1)[0]
        method='maioria'
        if count<2:
            decision=decisions.get(key)
            if not decision or not normal(decision['decisao']):
                pendings.append({**dict(zip(DECISION_FIELDS,['','','','','','',''])), 'full_name':key[0],'release_id':key[1],'dimensao':key[2]})
                continue
            label=normal(decision['decisao']);method='reuniao';used.add(key)
            if label not in DIMENSIONS[key[2]] or not decision['justificativa'].strip():
                raise ValueError(f'Desempate inválido/sem justificativa: {key}')
            participants={s.strip() for s in decision['participantes'].split(';')}
            if participants!=set(RATERS): raise ValueError(f'Reunião deve registrar os três participantes: {key}')
            from datetime import date
            date.fromisoformat(decision['data_reuniao'])
        resolved[key]=label
        audit.append({'full_name':key[0],'release_id':key[1],'dimensao':key[2],**dict(zip(RATERS,task['votos'])),'consenso':label,'metodo':method})
    if set(decisions)-used: raise ValueError('Há desempates extras ou referentes a casos sem empate')
    if not decisions_path.exists(): write_csv(decisions_path,[],DECISION_FIELDS)
    write_csv(directory/'pendencias.csv',pendings,DECISION_FIELDS)
    write_csv(directory/'auditoria_consenso.csv',audit,['full_name','release_id','dimensao',*RATERS,'consenso','metodo'])
    if pendings:
        raise Pending(f'{len(pendings)} empates 1-1-1: transcreva pendencias.csv para desempates.csv e registre a decisão em reunião')
    consensus=[]
    for row in manifest['sample']:
        name,rid=row['full_name'],row['release_id']
        consensus.append({**row,'tipo_projeto':resolved[(name,'','tipo_projeto')],
                          'entrega_real':resolved[(name,'','entrega_real')],'corretiva':resolved[(name,rid,'corretiva')]})
    # Compatível com validacao.py da Issue #35: full_name, tag_name, corretiva.
    write_csv(directory/'consenso.csv',consensus,FIELDS)
    hashes={str(Path('rotulos')/f'{a}.csv'):digest(directory/'rotulos'/f'{a}.csv') for a in RATERS}
    for name in ('manifesto.json','desempates.csv','kappa.json','consenso.csv','auditoria_consenso.csv'):
        hashes[name]=digest(directory/name)
    final = not manifest['pilot'] and manifest['population_count']>=300
    write_json(directory/'conclusao.json',{'final':final,'population_count':manifest['population_count'],'repositories':60,'releases':300,'pending':0,'sha256':hashes})
    lines=['# Concordância da amostra-ouro', '', f'População: {manifest["population_count"]} repositórios. Piloto: {manifest["pilot"]}.', '', '| Dimensão | Itens | Kappa | Interpretação |', '|---|---:|---:|---|']
    for dim, result in report.items():
        number = 'indefinido' if result['kappa'] is None else f"{result['kappa']:.6f}"
        lines.append(f"| {dim} | {result['itens']} | {number} | {result['interpretacao']} |")
    lines += ['', 'Valores calculados nos votos independentes antes da consolidação. Maioria simples e reunião para empates 1-1-1. Nenhum caso aberto no consenso gerado. A origem humana dos rótulos deve ser atestada pelos próprios participantes.']
    (directory/'relatorio.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if require_final and not final: raise Pending('Amostra piloto: repita o sorteio após obter a amostra final S02 (>=300 repositórios)')
    return report

def verify(directory):
    directory=Path(directory)
    report=analyze(directory,require_final=True)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('acao',choices=['preparar','analisar','verificar'])
    parser.add_argument('--repositorios',default='data/processed/repositories.csv')
    parser.add_argument('--releases',default='data/processed/releases.csv')
    parser.add_argument('--saida',default='validacao')
    parser.add_argument('--piloto',action='store_true')
    args=parser.parse_args()
    try:
        if args.acao=='preparar':
            result=prepare(args.repositorios,args.releases,args.saida,args.piloto)
            print(f"Planilhas preservadas/geradas: 60 repos, 300 releases; piloto={result['pilot']}")
        else:
            result=analyze(args.saida,require_final=args.acao=='verificar')
            print(json.dumps(result,ensure_ascii=False,indent=2))
    except (Pending,ValueError,FileNotFoundError,KeyError) as exc:
        parser.exit(2,f'PENDENTE/ERRO: {exc}\n')

if __name__=='__main__': main()
