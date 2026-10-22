"""Owned, authenticated Xvfb display; never attach a crawler to the desktop."""
from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile


@contextmanager
def virtual_display():
 binary=shutil.which('Xvfb') or str(Path.home()/'.local/share/coupang-virtual-browser/runtime/usr/bin/Xvfb')
 if not Path(binary).is_file():raise RuntimeError('Xvfb is required; desktop display fallback is disabled')
 if not shutil.which('xauth'):raise RuntimeError('xauth is required for the private virtual display')
 original=dict(os.environ);server=None
 # Chrome creates Unix-domain sockets here; deep report paths exceed sun_path.
 with tempfile.TemporaryDirectory(prefix='cpvd-',dir='/tmp') as folder:
  root=Path(folder);authority=root/'Xauthority';authority.touch(mode=0o600)
  log=(root/'xvfb.log').open('w')
  try:
   # Xvfb allocates an unused display and reports it without touching DISPLAY.
   read_fd,write_fd=os.pipe()
   server=subprocess.Popen([binary,'-displayfd',str(write_fd),'-screen','0','1280x900x24','-nolisten','tcp','-auth',str(authority)],pass_fds=(write_fd,),stdout=log,stderr=log,start_new_session=True)
   os.close(write_fd)
   import select
   if not select.select([read_fd],[],[],10)[0]:raise RuntimeError('Private Xvfb startup timed out')
   with os.fdopen(read_fd) as pipe:number=pipe.readline().strip()
   if not number.isdigit() or server.poll() is not None:raise RuntimeError('Private Xvfb failed to allocate a display')
   display=':'+number
   subprocess.run(['xauth','-f',str(authority),'add',display,'MIT-MAGIC-COOKIE-1',secrets.token_hex(16)],check=True,capture_output=True)
   for key in ('DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER'):os.environ.pop(key,None)
   os.environ.update(DISPLAY=display,XAUTHORITY=str(authority),XDG_RUNTIME_DIR=str(root),XDG_SESSION_TYPE='x11',TMPDIR=str(root))
   if shutil.which('xdpyinfo'):
    subprocess.run(['xdpyinfo','-display',display],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=5)
   yield {'kind':'private_xvfb','display':display,'server_pid':server.pid,'desktop_display_reused':False,'desktop_dbus_reused':False}
  finally:
   os.environ.clear();os.environ.update(original)
   if server:
    server.terminate()
    try:server.wait(timeout=5)
    except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
   log.close()
