"""Regression checks for v4.0 Goto T replacement with actual QThreads, no hardware."""
import ast
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QThread, Signal, Slot

SRC = Path(__file__).resolve().parents[1] / 'OPTP_system_iTC_v4.0.py'
tree = ast.parse(SRC.read_text(encoding='utf-8-sig'))
worker = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'iTCstabilizeThread')
controller = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'moSys')
goto = next(n for n in controller.body if isinstance(n, ast.FunctionDef) and n.name == 'iTC_goto_targetT')
ns = dict(QThread=QThread, Signal=Signal, Slot=Slot, threading=threading, time=time,
          QApplication=SimpleNamespace(processEvents=lambda: None))
exec(compile(ast.Module(body=[worker, goto], type_ignores=[]), str(SRC), 'exec'), ns)
app = QCoreApplication.instance() or QCoreApplication([])

class ITC:
    def __init__(self):
        self.io_lock = threading.RLock()
        self.targets = []
        self.read_started = threading.Event()
        self.release_read = threading.Event()
        self.block_read = False
        self.temperature = 1.0

    def set_temp_point(self, uid, target):
        self.targets.append(target)

    def read_temperature(self, uid):
        self.read_started.set()
        if self.block_read:
            self.release_read.wait()
        return self.temperature

box = lambda value: SimpleNamespace(value=lambda: value)
def make_controller():
    return SimpleNamespace(ui=SimpleNamespace(activeiTC=SimpleNamespace(isChecked=lambda: True),
        Tolerance=box(0.1), waitiTC=box(10), T_stab_cnt=box(2), TempDone=SimpleNamespace(status=False)),
        mercuryiTC=ITC(), uid_TEMP='sensor', itc_stab_thread=None, stop_flag=False,
        on_temp_done=lambda ok: None)

def cleanup(m):
    m.mercuryiTC.release_read.set()
    if m.itc_stab_thread is not None:
        m.itc_stab_thread.request_stop()
        assert m.itc_stab_thread.wait(3000)
    app.processEvents()

goto_target = ns['iTC_goto_targetT']
Worker = ns['iTCstabilizeThread']

# A ten-second polling sleep must not delay replacement by ten seconds.
m = make_controller()
try:
    assert goto_target(m, 10)
    old = m.itc_stab_thread
    assert m.mercuryiTC.read_started.wait(1)
    time.sleep(0.1)
    begin = time.monotonic()
    assert goto_target(m, 20)
    assert time.monotonic() - begin < 1
    assert not old.isRunning() and m.itc_stab_thread is not old
    assert m.mercuryiTC.targets == [10, 20] and not m.stop_flag
    for target in (30, 40, 50):
        assert goto_target(m, target)
    print('PASS repeated Goto T interrupts long waits and joins old workers')
finally:
    cleanup(m)

# Real blocked communication: keep the old object and do not send a new setpoint.
m = make_controller()
m.mercuryiTC.block_read = True
try:
    assert goto_target(m, 10)
    old = m.itc_stab_thread
    assert m.mercuryiTC.read_started.wait(1)
    assert not goto_target(m, 20)
    assert m.itc_stab_thread is old and old.isRunning()
    assert m.mercuryiTC.targets == [10]
    try:
        goto_target(m, 30, update_ui=False)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Scan must abort if previous worker cannot stop')
    assert m.itc_stab_thread is old and m.mercuryiTC.targets == [10]
    print('PASS communication timeout retains worker and rejects manual/scan setpoints')
finally:
    cleanup(m)
assert goto_target(m, 40)
cleanup(m)
print('PASS retry works after blocked communication finishes')

# Result payload and native finished signal must each be delivered independently.
for outcome in ('stable', 'error', 'stop'):
    m = make_controller()
    m.mercuryiTC.temperature = 10
    if outcome == 'error':
        def fail_read(uid):
            raise RuntimeError('simulated read failure')
        m.mercuryiTC.read_temperature = fail_read
    t = Worker(m, 10, 0.1, 10, 1)
    m.itc_stab_thread = t
    results, ended = [], []
    t.stabilized.connect(results.append)
    t.finished.connect(lambda: ended.append(True))
    if outcome == 'stop':
        t.stop_flag = True
    try:
        t.start()
        assert t.wait(1000)
        app.processEvents()
        assert results == [outcome == 'stable'] and ended == [True]
        assert t.stab_success == (outcome == 'stable')
        print(f'PASS {outcome}: result and native thread termination signals')
    finally:
        cleanup(m)
print('All v4.0 temperature thread regression checks passed.')
