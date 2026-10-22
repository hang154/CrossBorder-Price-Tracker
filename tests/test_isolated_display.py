import os
from pathlib import Path
import pytest
from app import isolated_display


def test_private_display_uses_short_paths_and_restores_environment(monkeypatch):
 binary=isolated_display.shutil.which('Xvfb') or str(Path.home()/'.local/share/coupang-virtual-browser/runtime/usr/bin/Xvfb')
 if not Path(binary).is_file():pytest.skip('Xvfb not available')
 monkeypatch.setenv('TMPDIR','/a/very/deep/report/directory/'*8)
 before=dict(os.environ);pid=None
 with pytest.raises(RuntimeError,match='fixture error'):
  with isolated_display.virtual_display() as info:
   pid=info['server_pid'];assert os.environ['DISPLAY']!=before.get('DISPLAY')
   assert len(os.environ['TMPDIR'].encode())<60
   assert 'DBUS_SESSION_BUS_ADDRESS' not in os.environ and 'WAYLAND_DISPLAY' not in os.environ
   assert Path(os.environ['XAUTHORITY']).stat().st_mode & 0o777==0o600
   raise RuntimeError('fixture error')
 assert dict(os.environ)==before
 assert not Path('/proc/'+str(pid)).exists()


def test_missing_virtual_server_never_falls_back_to_desktop(tmp_path,monkeypatch):
 monkeypatch.setattr(isolated_display.shutil,'which',lambda _:None)
 monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path))
 before=dict(os.environ)
 with pytest.raises(RuntimeError,match='desktop display fallback is disabled'):
  with isolated_display.virtual_display():raise AssertionError('Must refuse startup')
 assert dict(os.environ)==before
