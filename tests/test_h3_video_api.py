import json
from pathlib import Path
import httpx
import pytest
from PIL import Image
from app.h3_video_api import VideoAPI


def setup_api(tmp_path, handler):
    image=tmp_path/'start.png';Image.new('RGB',(256,256),'white').save(image)
    client=httpx.Client(transport=httpx.MockTransport(handler),headers={'Authorization':'Bearer test-secret'})
    return VideoAPI('http://h3.test',client=client),image,tmp_path/'job.json'


def test_submit_once_resume_and_auth(tmp_path):
    calls=[]
    def handler(request):
        assert request.headers['Authorization']=='Bearer test-secret';calls.append(request.method)
        if request.method=='POST':
            assert b'name="start_image"' in request.content
            assert b'name="generate_sound"' in request.content
            return httpx.Response(202,json={'id':'test-123','status':'QUEUED'})
        return httpx.Response(200,json={'id':'test-123','status':'SUCCEEDED'})
    api,image,journal=setup_api(tmp_path,handler)
    assert api.submit('slow push in',image,journal)['id']=='test-123'
    api.submit('slow push in',image,journal)
    assert api.poll(journal)['state']=='SUCCEEDED'
    assert calls==['POST','GET']
    assert 'test-secret' not in journal.read_text()


def test_unknown_post_never_retried(tmp_path):
    calls=[]
    def handler(request):calls.append(request.method);raise httpx.ReadTimeout('lost response')
    api,image,journal=setup_api(tmp_path,handler)
    with pytest.raises(httpx.ReadTimeout):api.submit('scene',image,journal)
    assert json.loads(journal.read_text())['state']=='UNKNOWN'
    with pytest.raises(RuntimeError):api.submit('scene',image,journal)
    assert calls==['POST']


def test_rejected_and_changed_input_require_new_job(tmp_path):
    api,image,journal=setup_api(tmp_path,lambda r:httpx.Response(422,json={'error':'invalid'}))
    with pytest.raises(httpx.HTTPStatusError):api.submit('scene',image,journal)
    assert json.loads(journal.read_text())['state']=='REJECTED'
    with pytest.raises(ValueError):api.submit('different scene',image,journal)


def test_invalid_parameters_do_not_submit(tmp_path):
    calls=[]
    api,image,journal=setup_api(tmp_path,lambda r:calls.append(r))
    with pytest.raises(ValueError):api.submit('scene',image,journal,duration=6)
    assert not journal.exists() and not calls


def test_failed_video_not_downloaded(tmp_path):
    calls=[]
    api,image,journal=setup_api(tmp_path,lambda r:calls.append(r))
    journal.write_text(json.dumps({'id':'x','state':'RUNNING'}))
    with pytest.raises(ValueError):api.download(journal,tmp_path/'out.mp4')
    assert not calls


def test_connection_file_and_environment_precedence(tmp_path,monkeypatch):
    from app.h3_video_api import connection_settings
    config=tmp_path/'connection.json';config.write_text(json.dumps({'base':'http://lan.test:18751/v1/','interface':'wlo1'}))
    monkeypatch.setenv('H3_CONNECTION_FILE',str(config));monkeypatch.delenv('H3_API_BASE',raising=False);monkeypatch.delenv('H3_BIND_INTERFACE',raising=False)
    assert connection_settings()=={'base':'http://lan.test:18751','interface':'wlo1'}
    monkeypatch.setenv('H3_API_BASE','http://override.test:18751');monkeypatch.setenv('H3_BIND_INTERFACE','')
    assert connection_settings()=={'base':'http://override.test:18751','interface':''}
    assert connection_settings('http://explicit.test/v1')['base']=='http://explicit.test'


def test_interface_is_bound_before_tcp_connection(monkeypatch):
    import socket
    from app.h3_video_api import interface_transport
    calls=[]
    class FakeSocket:
        def settimeout(self,value):calls.append(('timeout',value))
        def setsockopt(self,*args):calls.append(('option',args))
        def connect(self,address):calls.append(('connect',address))
        def close(self):calls.append(('close',))
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('192.168.0.40',18751))])
    monkeypatch.setattr(socket,'socket',lambda *a:FakeSocket())
    transport=interface_transport('wlo1');stream=transport._pool._network_backend.connect_tcp('192.168.0.40',18751,timeout=3)
    bind=calls.index(('option',(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,b'wlo1\0')))
    assert bind<calls.index(('connect',('192.168.0.40',18751)))
    stream.close();transport.close()
