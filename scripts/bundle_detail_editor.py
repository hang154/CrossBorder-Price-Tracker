"""Copy the standalone local editor and reviewer into a portable delivery."""
from pathlib import Path
import shutil

def bundle(dest,port=8774):
 repo=Path(__file__).resolve().parents[1];app=dest/'editor/app';app.mkdir(parents=True,exist_ok=True)
 for name in ['text_edit_agent.py','text_edit_agent.html','text_layer_runtime.js','text_layer_controls.js','detail_layout.py','detail_style_review.py']:
  shutil.copyfile(repo/'app'/name,app/name)
 (app/'__init__.py').write_text('')
 shutil.copytree(repo/'app/vendor',app/'vendor',dirs_exist_ok=True)
 (dest/'editor/run.py').write_text('from app.text_edit_agent import main\nmain()\n')
 (dest/'editor/review.py').write_text('from app.detail_style_review import serve\nfrom pathlib import Path\nserve(Path(__file__).resolve().parents[1],8775)\n')
 (dest/'editor/requirements.txt').write_text('Pillow>=11\nplaywright>=1.50\n')
 (dest/'편집기_실행.txt').write_text(f'Python3가 있는 Linux/macOS에서 압축을 풀고 이 폴더를 작업 경로로 사용하세요.\npython3 -m pip install -r editor/requirements.txt\npython3 -m playwright install chromium\npython3 editor/run.py serve --project editable-project/project.json --port {port}\n브라우저 http://127.0.0.1:{port} 에서 문구 위치·서식을 편집하고 PNG를 출력합니다.\n비교 화면의 선택 저장: python3 editor/review.py (http://127.0.0.1:8775)\n모델 API나 인증 키 없이 편집·출력할 수 있습니다. 원본 JSON·폰트·배경 자산을 함께 유지하세요.\nWindows에서는 WSL을 사용하세요(fcntl 파일 잠금 필요).\n')
