"""Qwen-Image async jobs: durable submit once, resume by ID, authenticated PNG."""
import hashlib
import io
import json
import os
import re
import time
from pathlib import Path
import httpx
from PIL import Image

BASE='https://hang010412.tail144a38.ts.net/qwen-image-api/v1'
TERMINAL={'SUCCEEDED','FAILED','CANCELLED'}


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    with open(temp,'w') as f:
        os.chmod(temp,0o600);json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def headers(key_file=None):
    key=Path(key_file).expanduser().read_text().strip() if key_file else os.environ.get('QWEN_IMAGE_API_KEY') or os.environ.get('HERETIC_API_KEY')
    if not key:
        conventional=Path.home()/'.config/heretic2_handoff/api_key.txt'
        if conventional.is_file():key=conventional.read_text().strip()
    if not key:
        from app.sourcing_agent import connection
        return {'Authorization':connection()['Authorization']}
    return {'Authorization':'Bearer '+key}


class ImageAPI:
    def __init__(self,auth=None,base=BASE,client=None):
        self.base=base.rstrip('/')
        self.client=client or httpx.Client(headers=auth or headers(),timeout=httpx.Timeout(90,connect=15),follow_redirects=False)

    @staticmethod
    def validate(size,steps,images):
        if not re.fullmatch(r'\d+x\d+',size):raise ValueError('Invalid size')
        w,h=map(int,size.split('x'))
        if any(n<256 or n>2752 or n%32 for n in (w,h)):raise ValueError('Size: 256..2752, multiples of 32')
        if not 1<=steps<=100:raise ValueError('Steps: 1..100')
        if images and not 1<=len(images)<=10:raise ValueError('References: 1..10')
        if sum(Path(p).stat().st_size for p in images)>33*1024**2:raise ValueError('Multipart must fit 34MiB including overhead')

    def submit(self,prompt,journal,images=(),size='1536x2304',steps=50,seed=42):
        """Never retry a POST. Existing unknown journals require reconciliation."""
        journal=Path(journal);images=[Path(p) for p in images]
        self.validate(size,steps,images)
        specification={'prompt':prompt,'size':size,'steps':steps,'seed':seed,
            'images':[{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'name':p.name} for p in images]}
        fingerprint=hashlib.sha256(json.dumps(specification,sort_keys=True).encode()).hexdigest()
        if journal.exists():
            saved=json.loads(journal.read_text())
            if saved.get('fingerprint')!=fingerprint:raise ValueError('Job input changed; use a new journal')
            if saved.get('id'):return saved
            raise RuntimeError('Existing submission has no ID; reconcile it, do not resubmit')
        saved={'state':'SUBMITTING','fingerprint':fingerprint,'submitted_at':time.time(),'automatic_post_retry':False,'request':specification}
        journal.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive create prevents two processes from submitting the same job.
        fd=os.open(journal,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:json.dump(saved,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        try:
            if images:
                import contextlib
                with contextlib.ExitStack() as stack:
                    import mimetypes
                    files=[('image',(p.name,stack.enter_context(p.open('rb')),mimetypes.guess_type(p.name)[0] or 'application/octet-stream')) for p in images]
                    response=self.client.post(self.base+'/images/edits',data={k:str(v) for k,v in specification.items() if k in ['prompt','size','steps','seed']},files=files)
            else:
                response=self.client.post(self.base+'/images/generations',json={k:v for k,v in specification.items() if k!='images'})
            saved['http_status']=response.status_code
            if response.status_code in [401,413,422,429]:
                saved.update(state='REJECTED',error='HTTP '+str(response.status_code),error_response=response.text[:4000]);atomic(journal,saved)
                response.raise_for_status()
            if response.status_code!=202:raise RuntimeError('Ambiguous submission HTTP '+str(response.status_code))
            job=response.json();job_id=job.get('id')
            self.job_id(job_id)
            saved.update(id=job_id,state=job.get('status','QUEUED'),submit_response=job)
            atomic(journal,saved);return saved
        except Exception as exc:
            if saved.get('state')!='REJECTED':
                saved.update(state='UNKNOWN',error=type(exc).__name__);atomic(journal,saved)
            raise

    @staticmethod
    def job_id(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value):raise ValueError('Invalid job ID')
        return value

    def status(self,job_id):
        response=self.client.get(self.base+'/image-jobs/'+self.job_id(job_id))
        response.raise_for_status();return response.json()

    def poll(self,journal):
        journal=Path(journal);saved=json.loads(journal.read_text())
        if not saved.get('id'):raise RuntimeError('Unknown submission; no automatic POST retry')
        job=self.status(saved['id']);saved.update(state=job['status'],last_status=job,updated_at=time.time())
        atomic(journal,saved);return saved

    def download(self,journal,output):
        journal,output=Path(journal),Path(output);saved=json.loads(journal.read_text())
        if output.exists():
            if saved.get('output_sha256')==hashlib.sha256(output.read_bytes()).hexdigest():return saved
            raise FileExistsError('Output exists without matching receipt')
        if saved.get('state')!='SUCCEEDED':raise RuntimeError('Download only after SUCCEEDED')
        response=self.client.get(self.base+'/image-jobs/'+self.job_id(saved['id'])+'/image')
        response.raise_for_status()
        if 'image/png' not in response.headers.get('content-type',''):raise ValueError('Expected PNG')
        data=response.content
        with Image.open(io.BytesIO(data)) as image:
            if image.format!='PNG':raise ValueError('Not a PNG')
            dimensions=list(image.size);image.verify()
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('xb') as f:f.write(data)
        saved.update(output=str(output),output_sha256=hashlib.sha256(data).hexdigest(),dimensions=dimensions,downloaded_at=time.time())
        atomic(journal,saved);return saved
