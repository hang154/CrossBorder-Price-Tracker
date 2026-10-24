"""H3 I2V adapter. Submit once, reconcile unknown POSTs, resume by job ID."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import httpx
from app.qwen_image_api import atomic, ImageAPI


def connection_settings(base=None):
    path=Path(os.getenv('H3_CONNECTION_FILE','~/.config/h3_gpu1_edit_api/connection.json')).expanduser()
    settings=json.loads(path.read_text()) if path.is_file() else {}
    if not isinstance(settings,dict):raise ValueError('H3 연결 설정은 JSON 객체여야 합니다.')
    endpoint=base or os.getenv('H3_API_BASE') or settings.get('base') or 'http://100.106.29.5:18751'
    if not isinstance(endpoint,str):raise ValueError('H3 서버 주소 오류')
    endpoint=endpoint.rstrip('/')
    if endpoint.endswith('/v1'):endpoint=endpoint[:-3]
    return dict(base=endpoint,interface=os.getenv('H3_BIND_INTERFACE',settings.get('interface')))


def interface_transport(interface, proxy=None):
    """Bind before connect; HTTPX socket_options are applied after connect."""
    import httpcore
    from httpcore._backends.sync import SyncStream
    if not isinstance(interface,str) or not interface or len(interface.encode())>15 or '\0' in interface:
        raise ValueError('H3 네트워크 인터페이스 이름 오류')
    if not hasattr(socket,'SO_BINDTODEVICE'):
        raise ValueError('인터페이스 지정은 Linux에서 지원합니다.')
    class BoundBackend(httpcore.SyncBackend):
        def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):
            last=None
            for family,kind,proto,_,address in socket.getaddrinfo(host,port,0,socket.SOCK_STREAM):
                sock=socket.socket(family,kind,proto)
                try:
                    sock.settimeout(timeout)
                    sock.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,interface.encode()+b'\0')
                    if local_address:sock.bind((local_address,0))
                    for option in socket_options or []:sock.setsockopt(*option)
                    sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    sock.connect(address)
                    return SyncStream(sock)
                except OSError as exc:
                    sock.close();last=exc
            if isinstance(last,socket.timeout):raise httpcore.ConnectTimeout(str(last)) from None
            raise httpcore.ConnectError(str(last)) from None
    transport=httpx.HTTPTransport(proxy=proxy,retries=0)
    # HTTPX has no public network-backend hook. Keep this compatibility point isolated.
    transport._pool._network_backend=BoundBackend()
    return transport


class VideoAPI:
    def __init__(self, base=None, token_file=None, client=None):
        settings=connection_settings(base)
        self.base=settings['base']
        if client is None:
            key = Path(token_file or os.getenv('H3_TOKEN_FILE', '~/.config/h3_gpu1_edit_api/api_token.txt')).expanduser()
            if not key.is_file():
                raise ValueError('H3 토큰 파일이 없습니다. H3_TOKEN_FILE에 기존 파일 경로를 지정하세요.')
            interface=settings['interface']
            network={'transport':interface_transport(interface,os.getenv('H3_HTTP_PROXY') or None)} if interface else {'proxy':os.getenv('H3_HTTP_PROXY') or None}
            client = httpx.Client(headers={'Authorization': 'Bearer '+key.read_text().strip()}, timeout=httpx.Timeout(90, connect=10), **network)
        self.client = client

    def health(self):
        r = self.client.get(self.base+'/health'); r.raise_for_status(); return r.json()

    def submit(self, prompt, start_image, journal, duration=5, steps=50, generate_sound=False, end_image=None):
        if duration not in (5, 10, 15) or not isinstance(steps, int) or not 1 <= steps <= 100:
            raise ValueError('길이는 5/10/15초, steps는 1~100입니다.')
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('장면 설명이 필요합니다.')
        images = [Path(start_image)] + ([Path(end_image)] if end_image else [])
        spec = dict(prompt=prompt, duration=duration, steps=steps, generate_sound=bool(generate_sound),
                    images=[{'name':p.name, 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in images])
        fingerprint = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        journal = Path(journal)
        if journal.exists():
            saved = json.loads(journal.read_text())
            if saved.get('fingerprint') != fingerprint:
                raise ValueError('입력이 변경됐습니다. 새 작업 경로를 사용하세요.')
            if saved.get('id'): return saved
            raise RuntimeError('제출 결과 미확인. 서버에서 확인하기 전 재제출하지 않습니다.')
        saved = dict(state='SUBMITTING', fingerprint=fingerprint, request=spec, submitted_at=time.time(), automatic_post_retry=False)
        journal.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(journal, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(saved, f, ensure_ascii=False); f.flush(); os.fsync(f.fileno())
        try:
            with contextlib.ExitStack() as stack:
                files = {'start_image':(images[0].name, stack.enter_context(images[0].open('rb')), 'image/png')}
                if end_image: files['end_image'] = (images[1].name, stack.enter_context(images[1].open('rb')), 'image/png')
                r = self.client.post(self.base+'/v1/jobs', data={'prompt':prompt, 'duration':str(duration), 'steps':str(steps), 'generate_sound':str(bool(generate_sound)).lower()}, files=files)
            saved['http_status'] = r.status_code
            if r.status_code in (400, 401, 403, 413, 422, 429):
                saved['state'] = 'REJECTED'; atomic(journal, saved); r.raise_for_status()
            if r.status_code not in (200, 201, 202): raise RuntimeError('제출 응답 미확인')
            job = r.json(); job_id = job.get('id') or job.get('job_id'); ImageAPI.job_id(job_id)
            saved.update(id=job_id, state=job.get('status', 'QUEUED')); atomic(journal, saved); return saved
        except Exception as exc:
            if saved['state'] != 'REJECTED':
                saved.update(state='UNKNOWN', error=type(exc).__name__); atomic(journal, saved)
            raise

    def poll(self, journal):
        journal = Path(journal); saved = json.loads(journal.read_text())
        job_id = ImageAPI.job_id(saved.get('id'))
        r = self.client.get(self.base+'/v1/jobs/'+job_id); r.raise_for_status(); job = r.json()
        saved.update(state=job['status'], updated_at=time.time(), last_status=job); atomic(journal, saved); return saved

    def download(self, journal, output):
        journal, output = Path(journal), Path(output); saved = json.loads(journal.read_text())
        if output.exists():
            if saved.get('output_sha256') == hashlib.sha256(output.read_bytes()).hexdigest(): return saved
            raise FileExistsError('다른 출력이 이미 있습니다.')
        if saved.get('state') != 'SUCCEEDED': raise ValueError('성공한 작업만 다운로드할 수 있습니다.')
        r = self.client.get(self.base+'/v1/jobs/'+ImageAPI.job_id(saved['id'])+'/video'); r.raise_for_status()
        output.parent.mkdir(parents=True, exist_ok=True); partial = output.with_suffix('.partial.mp4')
        if partial.exists(): raise FileExistsError('이전 부분 파일을 먼저 확인하세요.')
        with partial.open('xb') as f: f.write(r.content)
        try:
            probe = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',str(partial)], capture_output=True, text=True, check=True)
            info = json.loads(probe.stdout)
            if not any(s.get('codec_type') == 'video' for s in info['streams']): raise ValueError('영상 스트림 없음')
            if float(info['format']['duration']) <= 0: raise ValueError('잘못된 영상 길이')
            partial.rename(output)
        except Exception:
            partial.unlink(missing_ok=True); raise
        saved.update(output=str(output), output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(), probe=info); atomic(journal, saved); return saved


def transcode(source, output, width=780, fps=12, quality='high'):
    """Palette GIF, H264 MP4 or animated WebP; never overwrite."""
    source, output = Path(source), Path(output)
    if output.exists(): raise FileExistsError(output)
    if not 128 <= int(width) <= 1920 or not 1 <= int(fps) <= 30: raise ValueError('너비/FPS 범위 오류')
    if quality not in ('standard','high'):raise ValueError('품질 설정 오류')
    vf = f'fps={int(fps)},scale={int(width)}:-2:flags=lanczos'
    ext = output.suffix.lower()
    if ext == '.gif': args = ['-filter_complex',vf+f',split[a][b];[a]palettegen=max_colors={256 if quality=="high" else 128}[p];[b][p]paletteuse=dither=sierra2_4a','-loop','0']
    elif ext == '.webp': args = ['-vf',vf,'-c:v','libwebp_anim','-quality','90' if quality=='high' else '72','-loop','0']
    elif ext == '.mp4': args = ['-vf',vf,'-c:v','libx264','-crf','18' if quality=='high' else '25','-pix_fmt','yuv420p','-movflags','+faststart','-an']
    else: raise ValueError('GIF/MP4/WebP만 지원합니다.')
    subprocess.run(['ffmpeg','-v','error','-n','-threads','2','-i',str(source),*args,str(output)], check=True)
    if not output.is_file() or not output.stat().st_size: raise ValueError('영상 출력 실패')
    return str(output)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['health','submit','poll','download','convert']);p.add_argument('--base');p.add_argument('--token-file');p.add_argument('--journal');p.add_argument('--image');p.add_argument('--end-image');p.add_argument('--prompt');p.add_argument('--duration',type=int,default=5);p.add_argument('--steps',type=int,default=50);p.add_argument('--sound',action='store_true');p.add_argument('--output');p.add_argument('--width',type=int,default=780);p.add_argument('--fps',type=int,default=12);a=p.parse_args()
    if a.command=='convert': result=transcode(a.image,a.output,a.width,a.fps)
    else:
        api=VideoAPI(a.base,a.token_file)
        if a.command=='health': result=api.health()
        elif a.command=='submit': result=api.submit(a.prompt,a.image,a.journal,a.duration,a.steps,a.sound,a.end_image)
        elif a.command=='poll': result=api.poll(a.journal)
        else: result=api.download(a.journal,a.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
