"""Shared access observations and home-first validation; no timed admission delay."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit

HOME = 'https://www.coupang.com/'


class CoupangAccessError(ValueError):
    pass


class AccessGate:
    def __init__(self, path=None, *, clock=time.time):
        self.path = Path(path or os.environ.get('COUPANG_ACCESS_STATE', str(Path.home()/'.local/state/product-sourcing/coupang-access.json')))
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def locked(self):
        fd = os.open(str(self.path)+'.lock', os.O_CREAT|os.O_RDWR, 0o600)
        with os.fdopen(fd, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.path.read_text()) if self.path.exists() else {}
            yield state

    def save(self, state):
        # Migrate earlier cooldown records; they cannot defer a new attempt.
        for key in ('blocked_until','last_action','last_action_kind'):
            state.pop(key, None)
        state.update(cooldown_enabled=False, artificial_delay_seconds=0)
        fd, name = tempfile.mkstemp(prefix='.coupang-access-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(state, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)

    def status(self):
        with self.locked() as state:
            self.save(state)
            return dict(state)

    @contextlib.contextmanager
    def action(self, action, args=()):
        if action == 'open' and args:
            u = urlsplit(str(args[0]))
            if u.hostname and (u.hostname == 'coupang.com' or u.hostname.endswith('.coupang.com')) and str(args[0]) != HOME:
                raise CoupangAccessError('Coupang entry must open HOME; follow observed UI links afterwards')
        # No sleep, timestamp admission or persistent cooldown check.
        yield

    def blocked(self, stage, *, challenge=False):
        with self.locked() as state:
            state.update(block_events=state.get('block_events',0)+1,
                         blocked_at=self.clock(),
                         reason='human_verification' if challenge else 'access_denied',
                         blocked_stage=stage)
            self.save(state)

    def home_ready(self):
        with self.locked() as state:
            state.update(home_verified_at=self.clock())
            self.save(state)
