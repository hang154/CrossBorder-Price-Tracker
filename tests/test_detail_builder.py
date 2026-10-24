import copy
import hashlib
import json
from pathlib import Path
import pytest
from PIL import Image
from app.detail_builder import Studio,block,document,validate
from app.detail_workspace import Conflict


@pytest.mark.parametrize('value',[[],{},'naver',['../secret'],['naver','naver'],[{}]])
def test_invalid_market_selection_rejected(value):
    from app.detail_builder import export_markets
    with pytest.raises(ValueError,match='마켓'):export_markets(value)


def test_market_zip_renders_target_widths_from_frozen_revision(studio):
    import io,zipfile
    p=studio.create('123');p['blocks']=p['blocks'][:1];p=studio.save(p['id'],p,p['revision'])
    snapshot=copy.deepcopy(p);p['blocks'][0]['title']='나중에 저장한 문구';studio.save(p['id'],p,p['revision'])
    result=studio.export(p['id'],['toss','coupang','naver'],project_snapshot=snapshot)
    assert result['revision']==snapshot['revision']
    assert result['markets']==['coupang','naver','toss']
    with zipfile.ZipFile(result['zip']) as z:
        assert z.testzip() is None
        master=json.loads(z.read('project.json'));manifest=json.loads(z.read('manifest.json'))
        assert master['blocks'][0]['title']==snapshot['blocks'][0]['title']
        assert len(manifest['markets'])==3
        for entry in manifest['markets']:
            image=Image.open(io.BytesIO(z.read(entry['files'][0]['file'])))
            assert image.width=={'coupang':780,'naver':860,'toss':1000}[entry['id']]
            assert abs(image.height-snapshot['blocks'][0]['height']*image.width/860)<=2
        for entry in manifest['files']:assert hashlib.sha256(z.read(entry['file'])).hexdigest()==entry['sha256']
    assert studio.get(p['id'])['blocks'][0]['title']=='나중에 저장한 문구'
    # A different selection gets a separate package; stale market files cannot leak.
    other=studio.export(p['id'],['kakao'],project_snapshot=snapshot)
    assert other['folder']!=result['folder']
    with zipfile.ZipFile(other['zip']) as z:
        assert [n for n in z.namelist() if n.startswith('markets/')]==['markets/kakao/01.png']


@pytest.fixture
def studio(tmp_path):
    archive=tmp_path/'archive'/'123';archive.mkdir(parents=True)
    image=archive/'photo.png';Image.new('RGB',(300,300),'white').save(image)
    record=dict(status='complete',product_id='123',title='도자기 저금통',url='https://example.com/product/123',mandatory_information='품명: 저금통',main_image={'src':'https://example.com/photo.png'},assets=[dict(file='photo.png',source_url='https://example.com/photo.png',sha256=hashlib.sha256(image.read_bytes()).hexdigest(),width=300,height=300)])
    (archive/'detail.json').write_text(json.dumps(record))
    return Studio(tmp_path/'studio',tmp_path/'archive',tmp_path/'workspace')


def test_evidence_corruption_stops_creation(studio):
    Path(studio.products[0]['source']).with_name('photo.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):studio.create('123')
    assert not (studio.root/'projects').exists()


def test_stale_revision_preserves_editor_content(studio):
    p=studio.create('123');old=copy.deepcopy(p);p['blocks'][0]['title']='사람이 수정한 문구';saved=studio.save(p['id'],p,p['revision'])
    with pytest.raises(Conflict):studio.save(old['id'],old,old['revision'])
    assert studio.get(p['id'])['blocks'][0]['title']=='사람이 수정한 문구'
    assert saved['revision']==2


def test_review_block_requires_actual_evidence(studio):
    p=studio.create('123');p['blocks'][0]['category']='고객 리뷰'
    with pytest.raises(ValueError,match='실제 근거'):validate(p)


def test_html_escapes_external_copy(studio):
    p=studio.create('123');p['blocks'][0]['title']='<script>alert(1)</script>'
    result=document(p);assert '<script>' not in result and '&lt;script&gt;' in result


def test_workspace_export_is_idempotent(studio):
    p=studio.create('123');a=studio.publish_workspace(p['id']);b=studio.publish_workspace(p['id'])
    assert a['page_id']==b['page_id']
    from app.detail_workspace import Store
    assert len(Store(studio.workspace).state()['pages'])==1


def test_geometry_and_path_traversal_rejected(studio):
    with pytest.raises(ValueError):studio.folder('../credentials')
    p=studio.create('123');p['blocks'][0]['imageY']=1000
    with pytest.raises(ValueError,match='벗어'):validate(p)


def listing_studio(tmp_path,rows):
    source=tmp_path/'winter.json';source.write_text(json.dumps(rows))
    return Studio(tmp_path/'listing-studio',tmp_path/'archive',list_file=source),source


def listed_variant(item='10'):
    return dict(product_id='123',item_id=item,vendor_item_id='20',title='겨울 문풍지 3M',url='https://www.coupang.com/vp/products/123?itemId='+item,image_url='https://thumbnail.coupangcdn.com/photo.png',price=9990,rating=4.5,review_count=1000,group_name='문풍지')


def test_listing_catalog_preserves_variants_and_deduplicates_groups(tmp_path):
    a=listed_variant();b=listed_variant('11');c={**a,'group_name':'다른 분류'}
    s,_=listing_studio(tmp_path,[a,b,c]);assert len(s.products)==2
    assert s.products[0]['id']!=s.products[1]['id']


def test_listing_draft_freezes_photo_without_promoting_reviews(tmp_path,monkeypatch):
    import contextlib,io,httpx
    stream=io.BytesIO();Image.new('RGB',(230,230),'white').save(stream,'PNG');calls=[]
    @contextlib.contextmanager
    def fetch(*args,**kwargs):
        calls.append(args);yield httpx.Response(200,content=stream.getvalue(),request=httpx.Request('GET',args[1]))
    monkeypatch.setattr(httpx,'stream',fetch)
    s,_=listing_studio(tmp_path,[listed_variant()]);p=s.create(s.products[0]['id']);s.create(s.products[0]['id'])
    assert len(calls)==1
    assert p['source']['scope']=='listing' and '미확보' in ' '.join(p['missing'])
    copy=' '.join(b['title']+' '+b['body'] for b in p['blocks'])
    assert '9990' not in copy and '1000' not in copy and '4.5' not in copy
    record=json.loads(Path(p['source']['path']).read_text());assert record['status']=='partial'
    assert record['listing_observation_sha256']


def test_listing_changes_and_untrusted_image_host_rejected(tmp_path):
    row=listed_variant();s,path=listing_studio(tmp_path,[row]);row['title']='바뀐 상품';path.write_text(json.dumps([row]))
    with pytest.raises(ValueError,match='목록이 변경'):s.create(s.products[0]['id'])
    row['image_url']='https://private.example/image.png';s,path=listing_studio(tmp_path,[row])
    with pytest.raises(ValueError,match='대표 이미지 URL'):s.create(s.products[0]['id'])


@pytest.mark.parametrize('motion',[
    {'tracks':{'image':{'effect':'spin'}}},
    {'tracks':{'image':{'start':float('nan')}}},
    {'tracks':{'image':{'duration':0}}},
    {'tracks':{'image':{'enabled':'false'}}},
    {'tracks':{'unknown':{}}},[],
])
def test_invalid_saved_motion_is_rejected(studio,motion):
    p=studio.create('123');p['blocks'][0]['motion']=motion
    with pytest.raises(ValueError,match='모션'):validate(p)


def test_qwen_motion_preserves_copy_and_disabled_missing_layers(studio,monkeypatch):
    import app.detail_builder as module
    p=studio.create('123');original=copy.deepcopy(p)
    def planner(folder,name,messages,schema,validator):
        available=json.loads(messages[0]['content'])['available']
        result={key:{'effect':'rise','start':.2,'duration':.8,'enabled':available[key]} for key in module.MOTION_LAYERS}
        validator(result);return result
    monkeypatch.setattr(module,'qwen',planner)
    saved=studio.recommend_motion(p['id'],p['blocks'][0]['id'])
    assert [(b['title'],b['body']) for b in saved['blocks']]==[(b['title'],b['body']) for b in original['blocks']]
    assert not saved['blocks'][0]['motion']['tracks']['cards']['enabled']
    assert saved['revision']==p['revision']+1


@pytest.mark.parametrize('field,value',[('fps',24.0),('duration',5.0),('width',True),('quality','unknown')])
def test_invalid_motion_export_settings_rejected(field,value):
    from app.detail_builder import motion_settings
    args=dict(format='gif',duration=5,fps=24,quality='high',width=780);args[field]=value
    with pytest.raises(ValueError):motion_settings(**args)
