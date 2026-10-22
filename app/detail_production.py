"""Register editable production drafts from observed sourcing products."""
import argparse
import base64
import html
import io
import json
from pathlib import Path
from PIL import Image
from app.detail_workspace import Store


def photograph(path):
    im=Image.open(path).convert('RGB');im.thumbnail((1000,1400));b=io.BytesIO();im.save(b,'JPEG',quality=88)
    return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()


def document(spec):
    e=lambda x:html.escape(str(x));color=spec['color'];photo=spec['photo'];name=spec['name']
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+e(name)+'''</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f0e5;color:#382b27;font:17px/1.9 system-ui}main{max-width:820px;margin:auto;background:#fffdf7}section{padding:58px 36px}p{word-break:keep-all}.eyebrow{letter-spacing:.2em;font-size:12px;color:#92503d}h1{font-size:46px;line-height:1.35;letter-spacing:-.05em;font-weight:600}h2{font-size:30px;line-height:1.5;letter-spacing:-.035em}.hero{text-align:center;background:'''+('#eee2b5' if color=='노란색' else '#f0eae1')+'''}img{display:block;width:100%;max-height:650px;object-fit:contain;background:white}.rule{width:48px;height:2px;background:#8a3328;margin:32px auto}.lead{font-size:20px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px;border-top:1px solid #ded3c1;border-bottom:1px solid #ded3c1;padding:28px 0}.number{font-size:12px;color:#9b4a35}dl{display:grid;grid-template-columns:120px 1fr;gap:10px}dt{color:#7a695d}dd{margin:0}.closing{text-align:center;background:#442f29;color:#f9edd8}.small{font-size:13px;color:#867164}@media(max-width:600px){section{padding:38px 22px}h1{font-size:35px}h2{font-size:25px}.pair{grid-template-columns:1fr}}
</style></head><body><main>
<section class="hero" id="hero"><div class="eyebrow">A SMALL WISH, A NEW BEGINNING</div><h1>새로운 시작에<br>작은 마음을 더하세요.</h1><div class="rule"></div><p class="lead">'''+e(color)+''' 바탕에 붉은 문양을 담은<br>종이 부적</p><img src="'''+photo+'''" alt="'''+e(color)+''' 바탕의 붉은 문양 상품 사진"></section>
<section id="story"><div class="number">01 / 마음을 담는 방식</div><h2>기대하는 내일을<br>눈앞의 작은 상징으로.</h2><p>중요한 일을 앞두고 마음을 정돈하고 싶을 때.<br>한 해의 시작을 조금 특별하게 맞이하고 싶을 때.<br>당신의 바람을 떠올리는 작은 물건이 되어줍니다.</p></section>
<section id="design"><div class="number">02 / 색과 문양</div><h2>'''+e(color)+''' 종이 위,<br>선명하게 남는 붉은 선.</h2><div class="pair"><div><h3>한눈에 들어오는 대비</h3><p>밝은 바탕과 붉은 문양이 이루는 색의 조합.</p></div><div><h3>간결한 종이 형태</h3><p>복잡한 장식보다 문양 자체에 집중한 모습.</p></div></div></section>
<section id="occasion"><div class="number">03 / 이런 순간에</div><h2>나를 위한 다짐으로,<br>누군가를 응원하는 마음으로.</h2><p>새해를 준비하는 작은 선물.<br>새로운 도전을 앞둔 사람에게 전하는 응원.<br>하루의 시작에 떠올리고 싶은 나만의 바람.</p></section>
<section id="information"><h2>주문 전 확인해 주세요.</h2><dl><dt>상품 형태</dt><dd>붉은 문양의 종이 부적</dd><dt>바탕색</dt><dd>'''+e(color)+''' 계열</dd><dt>구성·크기</dt><dd>확정 옵션에서 안내 예정</dd><dt>문양</dt><dd>선택하는 상품 옵션에 따라 달라질 수 있습니다.</dd></dl><p class="small">소망을 담는 상징용품입니다. 특정 결과나 효능을 보장하지 않습니다.</p></section>
<section class="closing" id="closing"><p>당신이 바라는 내일을 향해.</p><h2>작은 마음 하나를<br>곁에 두세요.</h2></section>
</main></body></html>'''


def register(store,report,base_url='http://127.0.0.1:8884'):
    report=Path(report).resolve();data=json.loads(report.read_text());results=[]
    specs=[('1688/973958651038','흰색','흰 바탕 · 붉은 문양 종이부적'),('1688/1073499594799','노란색','노란 바탕 · 붉은 문양 종이부적')]
    for key,color,name in specs:
        row=next(a for a in data['candidates'] if a['key']==key);source=row['item_url'];state=store.state()
        existing=next((p for p in state['products'] if p['source_url']==source and p['name']==name),None)
        pid=existing['id'] if existing else store.add_product({'name':name,'source_url':source,'status':'기획 중','notes':'자사 제작 초안 · 공급 후보 사진 기반. 규격·구성·가격·판매자 확정 전.'})
        pages=[p for p in state['pages'] if p['product_id']==pid and p['kind']=='draft']
        if pages:page=store.get_page(pages[0]['id'])
        else:
            photo=Path(row['photo']['path']);plan='\n'.join(['제작 단계: 1차 편집 가능한 HTML 초안. 기존 제작물을 발견해 수입한 것이 아니라 새로 작성한 초안.',f'상품 콘셉트: {name}',f'공급 후보: {source}',f'관찰 근거: {report}',f'가격 표기: {row.get("price_text")} / MOQ: {row.get("moq_text")}', '기획 의도: 신년·중요한 도전·선물의 응원이라는 상징적 가치. 실제 운세·투자·학업 성과를 보장하지 않음.', '섹션: hero(첫 화면) → story(의미) → design(색·형태) → occasion(사용 상황) → information(고지) → closing(마무리).', '사람이 확정할 항목: 최종 제품/옵션, 크기, 장수, 판매 가격, 배송·교환·반품, 브랜드명, 자체 촬영 이미지.', '현재 공급사 사진은 후보 외형 참고. 사진 색상과 실제 납품 옵션은 별도 확인. 친필·축원·개광·천연주사 등은 확인 없이 기재하지 않음.', '편집 방법: 화면에서 문구 수정 / HTML 탭에서 레이아웃 편집 / 아래 수정 지시를 섹션 ID와 함께 저장.'])
            page=store.add_page(pid,{'title':'판매 상세 A안 · 1차 제작 초안','kind':'draft','plan':plan,'html':document({'name':name,'color':color,'photo':photograph(photo)})})
        results.append({'product_id':pid,'page_id':page['id'],'name':name,'editor_url':base_url+'/?page='+page['id'],'preview_url':base_url+'/pages/'+page['id']+'/preview','handoff_url':base_url+'/api/pages/'+page['id']+'/handoff'})
    folder=store.root/'production';folder.mkdir(exist_ok=True)
    for item in results:
        page=store.get_page(item['page_id']);(folder/(item['page_id']+'.html')).write_text(page['html']);(folder/(item['page_id']+'-handoff.json')).write_text(json.dumps(store.handoff(item['page_id']),ensure_ascii=False,indent=2))
    (folder/'manifest.json').write_text(json.dumps({'pages':results,'origin':'new_editable_drafts_from_observed_candidates','source_report':str(report)},ensure_ascii=False,indent=2));return results


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='sourcing-runs/detail-workspace');p.add_argument('--report',required=True);p.add_argument('--base-url',default='http://127.0.0.1:8884');a=p.parse_args();print(json.dumps(register(Store(a.root),a.report,a.base_url.rstrip('/')),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
