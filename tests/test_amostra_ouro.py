import json
import pandas as pd
import pytest
from amostra_ouro import (RATERS, FIELDS, META, DIMENSIONS, Pending, draw, prepare,
                         read_csv, write_csv, analyze, agreement, interpretation, normal)

@pytest.fixture
def data(tmp_path):
    repos=pd.DataFrame({'full_name':[f'owner/repo{i:03d}' for i in range(300)]})
    releases=pd.DataFrame([{'full_name':name,'release_id':str(i*10+j),'tag_name':f'v1.0.{j}'} for i,name in enumerate(repos.full_name) for j in range(6)])
    rp,lp=tmp_path/'repos.csv',tmp_path/'releases.csv'
    repos.to_csv(rp,index=False);releases.to_csv(lp,index=False)
    return rp,lp,tmp_path/'validacao'

def fill(directory):
    for rater in RATERS:
        path=directory/'rotulos'/f'{rater}.csv'
        frame=read_csv(path)
        for i,name in enumerate(frame.full_name.unique()):
            mask=frame.full_name.eq(name)
            frame.loc[mask,'tipo_projeto']='outro' if i%2 else 'biblioteca/framework'
            frame.loc[mask,'entrega_real']='sim' if i%2 else 'nao'
        frame['corretiva']=['sim' if i%2 else 'nao' for i in range(len(frame))]
        write_csv(path,frame.to_dict('records'),FIELDS)

def test_draw_reproducible_after_reordering(data):
    rp,lp,_=data
    a=draw(read_csv(rp),read_csv(lp))
    b=draw(read_csv(rp).sample(frac=1,random_state=5),read_csv(lp).sample(frac=1,random_state=6))
    assert a==b and len(a)==300 and len({r['full_name'] for r in a})==60
    assert set(a[0])==set(META)

def test_pandas_sampling_matches_spec(data):
    rp,lp,_=data
    expected=read_csv(rp).sort_values('full_name',kind='stable').sample(n=60,random_state=42).full_name.tolist()
    assert list(dict.fromkeys(r['full_name'] for r in draw(read_csv(rp),read_csv(lp))))==expected

def test_short_duplicate_and_few_releases(data):
    rp,lp,_=data;rs,ls=read_csv(rp),read_csv(lp)
    with pytest.raises(Pending):draw(rs.head(59),ls)
    with pytest.raises(ValueError):draw(pd.concat([rs,rs.head(1)]),ls)
    with pytest.raises(ValueError):draw(rs,pd.concat([ls,ls.head(1)]))
    with pytest.raises(Pending):draw(rs,ls.iloc[0:0])

def test_prepare_preserves_completed_labels(data):
    rp,lp,directory=data
    prepare(rp,lp,directory);fill(directory)
    before={a:(directory/'rotulos'/f'{a}.csv').read_bytes() for a in RATERS}
    prepare(rp,lp,directory)
    assert all((directory/'rotulos'/f'{a}.csv').read_bytes()==before[a] for a in RATERS)
    assert all('heuristica' not in read_csv(directory/'rotulos'/f'{a}.csv').columns for a in RATERS)

def test_dataset_change_rejected(data):
    rp,lp,directory=data;prepare(rp,lp,directory)
    with rp.open('a') as fp:fp.write('new/repo\n')
    with pytest.raises(ValueError,match='mudou'):prepare(rp,lp,directory)

def test_pilot_never_final(data):
    rp,lp,directory=data;read_csv(rp).head(100).to_csv(rp,index=False)
    with pytest.raises(Pending):prepare(rp,lp,directory)
    prepare(rp,lp,directory,pilot=True);fill(directory)
    with pytest.raises(Pending,match='piloto'):analyze(directory,require_final=True)
    assert json.loads((directory/'conclusao.json').read_text())['final'] is False

def test_kappa_by_hand():
    result=agreement([['a','a','a'],['a','a','b'],['b','b','b'],['b','b','a']])
    assert result['kappa']==pytest.approx(1/3)
    assert result['concordancia_observada']==pytest.approx(2/3)
    assert result['interpretacao']=='razoavel'
    assert agreement([['a','a','a'],['b','b','b']])['kappa']==1
    assert agreement([['a','b','c'],['c','a','b']])['kappa']==pytest.approx(-.5)
    assert agreement([['a','a','a']])['kappa'] is None
    with pytest.raises(ValueError):agreement([['a','b']])

@pytest.mark.parametrize('value,label',[(0,'leve'),(.2,'leve'),(.21,'razoavel'),(.4,'razoavel'),(.41,'moderada'),(.6,'moderada'),(.61,'substancial'),(.8,'substancial'),(.81,'quase perfeita'),(-.1,'pobre')])
def test_interpretation(value,label):assert interpretation(value)==label

def test_complete_consensus_and_denominators(data):
    rp,lp,directory=data;prepare(rp,lp,directory);fill(directory)
    report=analyze(directory,require_final=True)
    assert report['tipo_projeto']['itens']==60
    assert report['entrega_real']['itens']==60
    assert report['corretiva']['itens']==300
    result=read_csv(directory/'consenso.csv')
    assert len(result)==300 and not result.isna().any().any()
    assert all(report[d]['kappa']==1 for d in DIMENSIONS)
    assert json.loads((directory/'conclusao.json').read_text())['final']
    analyze(directory,require_final=True) # não perde rótulos e arquiva saída anterior

def test_missing_labels_and_stale_consensus(data):
    rp,lp,directory=data;prepare(rp,lp,directory);fill(directory);analyze(directory)
    path=directory/'rotulos/gsantss.csv';frame=read_csv(path);frame.loc[0,'corretiva']='';write_csv(path,frame.to_dict('records'),FIELDS)
    with pytest.raises(Pending):analyze(directory)
    assert not (directory/'consenso.csv').exists() and not (directory/'conclusao.json').exists()

def test_missing_duplicate_extra_identity_and_inconsistent_labels(data):
    rp,lp,directory=data;prepare(rp,lp,directory);fill(directory)
    path=directory/'rotulos/gsantss.csv';original=read_csv(path)
    mutations=[original.iloc[:-1],pd.concat([original,original.head(1)]),original.assign(repo_url='https://wrong')]
    bad=original.copy();bad.loc[0,'tipo_projeto']='outro' if bad.loc[0,'tipo_projeto']!='outro' else 'ferramenta cli';mutations.append(bad)
    for frame in mutations:
        write_csv(path,frame.to_dict('records'),FIELDS)
        with pytest.raises(ValueError):analyze(directory)

def test_ties_require_meeting_and_preserve_original_kappa(data):
    rp,lp,directory=data;prepare(rp,lp,directory);fill(directory)
    name=read_csv(directory/'rotulos/gsantss.csv').iloc[0].full_name
    for rater,value in zip(RATERS,['biblioteca/framework','outro','ferramenta cli']):
        path=directory/'rotulos'/f'{rater}.csv';frame=read_csv(path);frame.loc[frame.full_name.eq(name),'tipo_projeto']=value;write_csv(path,frame.to_dict('records'),FIELDS)
    with pytest.raises(Pending,match='empates'):analyze(directory)
    before=(directory/'kappa.json').read_bytes()
    pending=read_csv(directory/'pendencias.csv');pending['decisao']='outro';pending['justificativa']='Acordo após leitura do README';pending['participantes']=';'.join(RATERS);pending['data_reuniao']='2026-10-15'
    write_csv(directory/'desempates.csv',pending.to_dict('records'),list(pending.columns))
    analyze(directory,require_final=True)
    assert before==(directory/'kappa.json').read_bytes() # Kappa antes de reconciliar
    assert len(read_csv(directory/'consenso.csv'))==300

def test_normalization():assert normal('  NÃO  ')== 'nao'

def test_duplicate_tags_with_different_ids_are_audited(data):
    rp,lp,directory=data
    frame=read_csv(lp)
    duplicate=frame.iloc[0].copy();duplicate['release_id']='999999999'
    frame=pd.concat([frame,pd.DataFrame([duplicate])],ignore_index=True)
    frame.to_csv(lp,index=False)
    manifest=prepare(rp,lp,directory)
    assert len(manifest['duplicate_tag_exclusions'])==1
    assert manifest['duplicate_tag_exclusions'][0]['release_id']!='999999999'
    sample=manifest['sample']
    assert len({(r['full_name'],r['tag_name']) for r in sample})==300
