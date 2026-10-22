import copy,json,shutil,subprocess,sys
from pathlib import Path
import httpx,pytest
from PIL import Image
from app.text_edit_agent import apply,atomic,read,revision,render,render_html,validate,Conflict,digest

@pytest.fixture
def project(tmp_path):
 assets=tmp_path/'assets';assets.mkdir();fonts={}
 for name,weight in [('regular','Regular'),('bold','Bold')]:
  src=Path('/usr/share/fonts/opentype/noto')/f'NotoSansCJK-{weight}.ttc';dest=assets/src.name;shutil.copyfile(src,dest);fonts[name]={'path':'assets/'+dest.name,'sha256':digest(dest.read_bytes())}
 bg=assets/'bg.png';Image.new('RGB',(256,256),'white').save(bg)
 d={'schema_version':1,'width':256,'height':256,'fonts':fonts,'assets':{'bg':{'path':'assets/bg.png','sha256':digest(bg.read_bytes())}},'cuts':[{'id':'cut1','name':'test','approved_copy':'원문','background':'bg','background_color':'#ffffff','masks':[],'texts':[{'id':'t1','text':'원문','x':20,'y':20,'width':216,'height':80,'color':'#000000','font_size':24,'min_font_size':12,'weight':400,'align':'left','line_height':1.3,'auto_fit':True}]}]}
 p=tmp_path/'project.json';atomic(p,d);return p

def patch(d,text):
 t=copy.deepcopy(d['cuts'][0]['texts'][0]);t['text']=text
 return {'base_revision':revision(d),'operations':[{'cut_id':'cut1','collection':'texts','action':'replace','id':'t1','value':t}]}

def test_literal_patch_history_and_conflict(project):
 d=read(project);literal='교정 <script>alert(1)</script>\n  띄어쓰기?!';p=patch(d,literal);r=apply(project,p)
 assert read(project)['cuts'][0]['texts'][0]['text']==literal
 assert json.loads((project.parent/'versions'/f'{revision(d)}.json').read_text())==d
 with pytest.raises(Conflict):apply(project,p)
 assert revision(read(project))==r['revision']

def test_invalid_transaction_does_not_write(project):
 d=read(project);p=patch(d,'바뀌면 안 됨');p['operations'][0]['value']['x']=250
 before=project.read_bytes()
 with pytest.raises(ValueError):apply(project,p)
 assert project.read_bytes()==before and not (project.parent/'edits.jsonl').exists()

@pytest.mark.parametrize('change',['asset','path','overflow'])
def test_validation_guards(project,change):
 d=read(project)
 if change=='asset':(project.parent/'assets/bg.png').write_bytes(b'tampered')
 elif change=='path':d['fonts']['regular']['path']='../outside.ttf'
 else:d['cuts'][0]['texts'][0]['height']=300
 with pytest.raises(ValueError):validate(d,project.parent)

def test_render_determinism_and_direct_html_edit(project):
 apply(project,patch(read(project),'정확한 한글'))
 a=render(project,'cut1')[0];b=render(project,'cut1')[0]
 assert a['png_sha256']==b['png_sha256']
 assert [x['text'] for x in a['metrics']]==['정확한 한글']
 source=project.parent/a['html'];source.write_text(source.read_text().replace('정확한 한글','직접 교정'))
 r=render_html(source,project.parent/'direct.png')
 assert r['metrics'][0]['text']=='직접 교정' and r['png_sha256']!=a['png_sha256']
 assert len(r['resources'])>=4


def test_browser_save_reload_and_export(project):
 from playwright.sync_api import sync_playwright
 proc=subprocess.Popen([sys.executable,'-u','-m','app.text_edit_agent','serve','--project',str(project),'--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:
  url=proc.stdout.readline().strip().split()[-1]
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(url);page.wait_for_function("document.querySelector('#preview').contentWindow.renderResult?.ready");frame=next(f for f in page.frames if '/preview/' in f.url)
   count=frame.evaluate("async()=>{await Promise.all([TextLayers.mount(input.doc,input.cut),TextLayers.mount(input.doc,input.cut)]);return document.querySelectorAll('.text').length}")
   assert count==1
   page.locator('#layers button').first.click();page.locator('#text').fill('저장된 정확한 문구');page.locator('#save').click();page.wait_for_function("document.querySelector('#status').textContent.startsWith('저장됨')")
   page.reload();page.locator('#layers button').first.click();assert page.locator('#text').input_value()=='저장된 정확한 문구'
   page.locator('#export').click();page.wait_for_selector('#exports a',timeout=30000);assert httpx.get(url+page.locator('#exports a').first.get_attribute('href')).status_code==200
   assert page.locator('#exports a').count()==2
   assert httpx.get(url+page.locator('#exports a').nth(1).get_attribute('href')).status_code==200
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors
   state=httpx.get(url+'/api/project').json();r=httpx.post(url+'/api/save',json={'project':state['project'],'base_revision':state['revision']});assert r.status_code==403
   browser.close()
 finally:proc.terminate();proc.wait(timeout=10)


def test_fabric_drag_resize_persist_and_blank_preview(project):
 from playwright.sync_api import sync_playwright
 proc=subprocess.Popen([sys.executable,'-u','-m','app.text_edit_agent','serve','--project',str(project),'--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:
  url=proc.stdout.readline().strip().split()[-1]
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1100,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(url);page.wait_for_function("document.querySelector('#preview').contentWindow.renderResult?.ready")
   assert page.evaluate('fabric.version')=='6.9.0'
   page.locator('#layers button').first.click();page.locator('#width').fill('120')
   page.wait_for_function("controls.canvas.getActiveObject().width===120")
   board=page.locator('#interaction').bounding_box()
   page.mouse.move(board['x']+65,board['y']+55);page.mouse.down();page.mouse.move(board['x']+90,board['y']+75,steps=6);page.mouse.up()
   assert int(page.locator('#x').input_value())==45 and int(page.locator('#y').input_value())==40
   # Drag the actual Fabric bottom-right handle, not a synthetic callback.
   corner=page.evaluate("()=>{let c=controls.canvas.getActiveObject().oCoords.br;return {x:c.x,y:c.y}}")
   page.mouse.move(board['x']+corner['x'],board['y']+corner['y']);page.mouse.down();page.mouse.move(board['x']+corner['x']+20,board['y']+corner['y']+15,steps=6);page.mouse.up()
   assert int(page.locator('#width').input_value())>120
   page.locator('#show-copy').uncheck()
   frame=next(f for f in page.frames if '/preview/' in f.url)
   assert frame.locator('.text').evaluate('(e)=>getComputedStyle(e).visibility')=='hidden'
   page.locator('#save').click();page.wait_for_function("document.querySelector('#status').textContent.startsWith('저장됨')")
   expected=read(project)['cuts'][0]['texts'][0].copy();assert expected['text']=='원문'
   page.reload();page.locator('#layers button').first.click();assert int(page.locator('#x').input_value())==expected['x']
   page.locator('#export').click();page.wait_for_selector('#exports a',timeout=30000)
   receipt=json.loads(next((project.parent/'exports').rglob('cut1.json')).read_text())
   assert receipt['metrics'][0]['text']=='원문'
   page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   assert not errors
   browser.close()
 finally:proc.terminate();proc.wait(timeout=10)
