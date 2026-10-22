import io,json
import httpx,pytest
from PIL import Image
from app.qwen_image_api import ImageAPI

def client(handler):return ImageAPI(client=httpx.Client(transport=httpx.MockTransport(handler)))

def test_submit_poll_download_and_resume(tmp_path):
 calls=[];im=Image.new('RGB',(256,256));buf=io.BytesIO();im.save(buf,'PNG')
 def handler(r):
  calls.append(r.method)
  if r.method=='POST':return httpx.Response(202,json={'id':'abc','status':'QUEUED'})
  if r.url.path.endswith('/image'):return httpx.Response(200,content=buf.getvalue(),headers={'content-type':'image/png'})
  return httpx.Response(200,json={'id':'abc','status':'SUCCEEDED'})
 api=client(handler);j=tmp_path/'job.json';out=tmp_path/'out.png'
 api.submit('문구',j,size='256x256');api.submit('문구',j,size='256x256')
 api.poll(j);result=api.download(j,out);api.download(j,out)
 assert calls==['POST','GET','GET'] and result['dimensions']==[256,256]
 with pytest.raises(ValueError):api.submit('changed',j,size='256x256')

@pytest.mark.parametrize('mode',['timeout','502','invalid202','429','422'])
def test_no_post_retry_on_failures(tmp_path,mode):
 calls=[]
 def handler(r):
  calls.append(r.method)
  if mode=='timeout':raise httpx.ReadTimeout('timeout')
  return httpx.Response(502 if mode=='502' else 429 if mode=='429' else 422 if mode=='422' else 202,json={'detail':'invalid input'})
 api=client(handler);j=tmp_path/'job.json'
 with pytest.raises(Exception):api.submit('x',j)
 with pytest.raises(RuntimeError):api.submit('x',j)
 assert calls==['POST']
 assert json.loads(j.read_text())['state']==('REJECTED' if mode in ['429','422'] else 'UNKNOWN')

def test_edit_and_validation(tmp_path):
 ref=tmp_path/'ref.png';Image.new('RGB',(256,256)).save(ref)
 def handler(r):
  assert r.url.path.endswith('/images/edits')
  assert b'name="image"' in r.content and b'name="prompt"' in r.content
  assert b'Content-Type: image/png' in r.content
  return httpx.Response(202,json={'id':'edit1','status':'QUEUED'})
 api=client(handler);api.submit('한국어',tmp_path/'job.json',images=[ref])
 with pytest.raises(ValueError):api.validate('2049x2048',50,[])
 with pytest.raises(ValueError):api.validate('2048x2048',101,[])
