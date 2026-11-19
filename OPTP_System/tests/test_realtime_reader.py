"""Realtime lock-in display (THz Emission v2.0, OPTP v4.5, MO v3.1, OPTP Imaging v2.2): the reads run in a
background thread at the wait time, the interval follows the wait box, and the real intervals are printed.

1. Changing the time constant or the multiplier sets the wait box and the Realtime interval (before: only
   the box changed, the display kept its old interval); typing in the box, the mouse wheel and the arrow
   keys set it too; the printed wait time is the box value after its limit.
2. The lock-in is read outside the GUI thread; readings are plotted on the GUI thread, all of them.
3. With the GUI thread blocked 250 ms out of every 300 ms, the reads stay at the set interval.
4. A new interval applies at once, also during a long wait.
5. Every 50 intervals (at most one line every 10 s), at an interval change and at switch-off, one line gives
   the real intervals and read times; a missing lock-in and a failing read print one warning per streak; a
   failing lock-in is retried 1 s after the end of the failed read, also when the read itself timed out after
   more than 1 s; the median of an even number of intervals is the mean of the middle two.
6. Switching off: no read after the one in progress, and its reading is not plotted; switching on again
   while that read runs keeps one reader (never two reads at once); readings of the previous switch-on that
   still wait for the GUI thread are not shown after a restart; after Auto Zero no reading taken before the
   offset replaces its readback.
7. Exit stops both readers before the instruments close; application quit (window close) stops them before
   the Live Process mirror, so their last report reaches the Live Process file.
8. SR830 driver: commands and queries from several threads, also through two objects on the same address,
   never overlap; close() waits for a query; open() of a second object on the same address (its device
   clear) does not overlap a query of the first.
9. With the reader reading back to back, a GUI lock-in command waits at most about one read; Close Instr.
   while the display runs prints no read-failure warning; at most 100 readings wait for a blocked GUI.

    python OPTP_System/tests/test_realtime_reader.py thz|optp|mo|img [path to another version]

Run on an earlier version (for example THz v1.9) the same checks show its QTimer behavior failing.
No hardware, offscreen; QSettings and data go to a temporary folder that is removed at the end.
"""
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[2]
SYSTEM = sys.argv[1] if len(sys.argv) > 1 else 'thz'
FILES = {'thz': 'THz_emission_system/THz_emission_system_iTC_v2.0.py',
         'optp': 'OPTP_System/OPTP_system_iTC_v4.5.py',
         'mo': 'MO_System/MO_system_iTC_v3.1.py',
         'img': 'OPTP_image_System/OPTP_iTC_image_v2.2.py'}
SRC = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / FILES[SYSTEM]
os.chdir(SRC.parent)  # OPTP Imaging loads its .ui relative to the working directory
sys.path.insert(0, str(SRC.parent))
source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'realtime_reader_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

REAL = sys.__stdout__
TMP = Path(tempfile.mkdtemp(prefix=f'realtime_reader_{SYSTEM}_'))
ns['QSettings'] = lambda org, name: QSettings(str(TMP / f'{org}.{name}.ini'), QSettings.IniFormat)


def data_folder(self):
    self.dataSave_path = str(TMP)
    self.ui.dataSavePath.setText(str(TMP))
    return str(TMP)


ns['moSys'].setup_data_folder = data_folder
printed = []  # every print() of the GUI module, from every thread
ns['print'] = lambda *args, **kwargs: printed.append(' '.join(str(a) for a in args))

app = QApplication.instance() or QApplication([])
m = ns['moSys']()
ui = m.ui
QMessageBox.warning = staticmethod(lambda *args: None)
QMessageBox.question = staticmethod(lambda *args: QMessageBox.Yes)
MAIN = threading.get_ident()
results = []
cu1 = m.chart_updaters['realDisChart1']


def report(msg):
    REAL.write(msg + "\n")
    REAL.flush()


def check(label, condition, detail=''):
    results.append(bool(condition))
    report(('PASS ' if condition else 'FAIL ') + label + ('' if condition or not detail else f'  [{detail}]'))


class FakeLockin:
    """get_x() takes read_s; records when each read starts, in which thread, and how many run at once."""
    def __init__(self, read_s=0.005, value=1.5e-3):
        self.read_s, self.fail, self.value = read_s, False, value
        self.starts, self.ends, self.threads, self.time_constants = [], [], set(), []
        self.active = self.max_active = 0
        self._lock = threading.Lock()

    def get_x(self):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        self.starts.append(time.monotonic())
        self.threads.add(threading.get_ident())
        try:
            time.sleep(self.read_s)
            if self.fail:
                raise RuntimeError('simulated GPIB timeout')
            return self.value
        finally:
            self.ends.append(time.monotonic())
            with self._lock:
                self.active -= 1

    def set_time_constant(self, index):
        self.time_constants.append(index)


def pump(seconds, block_s=0.0, period_s=0.3):
    """Run the GUI event loop; with block_s, the GUI thread is busy block_s out of every period_s."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if block_s:
            time.sleep(block_s)
            app.processEvents()
            time.sleep(max(0.0, period_s - block_s))
        app.processEvents()
        time.sleep(0.002)


def until(condition, timeout=3.0):
    end = time.monotonic() + timeout
    while not condition() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.002)
    return condition()


def plotted(name='realDisChart1'):
    x, y = m.curves[name].getData()
    return [] if y is None else list(y)


def reader_running(updater):
    reader = getattr(updater, 'reader', None)
    return reader is not None and reader.isRunning()


def set_interval(ms):
    ui.wait1.setValue(ms)
    ui.wait1.editingFinished.emit()


def intervals_ms(starts):
    return [round((b - a) * 1000) for a, b in zip(starts, starts[1:])]


def realtime(on, wait_off=True):
    ui.realtimeDisp1.setChecked(on)
    if not on and wait_off and getattr(cu1, 'reader', None) is not None:
        cu1.reader.wait(3000)


# ---- 1. the interval follows the wait box ----
m.lockin1, m.lockin2 = FakeLockin(), FakeLockin()
cu2 = m.chart_updaters['realDisChart2']
ui.wait1multip.setValue(3)
ui.timeConst1.setCurrentIndex(10)  # 1 s
ok_tc = ui.wait1.value() == 3000 and cu1.interval == 3000
ui.wait1multip.setValue(2)
ui.wait1multip.editingFinished.emit()
ok_mult = ui.wait1.value() == 2000 and cu1.interval == 2000
ui.wait2multip.setValue(3)
ui.timeConst2.setCurrentIndex(9)  # 300 ms
ok_l2 = ui.wait2.value() == 900 and cu2.interval == 900
ui.timeConst1.setCurrentIndex(ui.timeConst1.count() - 1)  # longer than the wait box allows
ok_clamp = cu1.interval == ui.wait1.value() == ui.wait1.maximum()
reader = getattr(cu1, 'reader', None)
check('time constant / multiplier set the wait box and the Realtime interval (Lock-in 1 and 2, clamped to the box)',
      ok_tc and ok_mult and ok_l2 and ok_clamp
      and (reader is not None and reader.interval_s == ui.wait1.value() / 1000),
      f'tc={ok_tc}, mult={ok_mult}, l2={ok_l2}, clamp={ok_clamp}, wait1={ui.wait1.value()}, interval={cu1.interval}')
set_interval(150)
check('editing the wait box by hand still sets the interval', cu1.interval == 150)
ui.wait1.stepBy(5)  # mouse wheel or arrow keys: only valueChanged, no editingFinished
check('stepping the wait box (wheel, arrow keys) sets the interval at once; typed digits count when the edit ends',
      cu1.interval == 155 and not ui.wait1.keyboardTracking() and not ui.wait2.keyboardTracking(),
      f'interval={cu1.interval}, tracking={ui.wait1.keyboardTracking()}')
check('the printed wait time is the box value after its limit (10000 ms), not time constant x multiplier',
      any(p.startswith('Updated wait time to 10000 ms for lockin1') for p in printed)
      and not any(p.startswith('Updated wait time to 60000000 ms') for p in printed))

# ---- 2. reads outside the GUI thread, every reading plotted on the GUI thread ----
fake = m.lockin1 = FakeLockin()
plot_threads = set()
curve = m.curves['realDisChart1']
original_setData = curve.setData
curve.setData = lambda *a, **k: (plot_threads.add(threading.get_ident()), original_setData(*a, **k))[1]
set_interval(100)
realtime(True)
pump(1.05)
realtime(False)
pump(0.05)
check('reads run outside the GUI thread; plotting runs on the GUI thread',
      fake.starts and MAIN not in fake.threads and plot_threads == {MAIN},
      f'reads={len(fake.starts)}, read threads main={MAIN in fake.threads}, plot threads main={plot_threads == {MAIN}}')
check('about 10 reads in 1 s at 100 ms; every reading is plotted (not one in progress at switch-off), number box shows it',
      9 <= len(fake.starts) <= 12 and len(fake.starts) - 1 <= len(plotted()) <= len(fake.starts)
      and ui.realDisChart1Num.text() == '1.5000e-03', f'reads={len(fake.starts)}, plotted={len(plotted())}')
del curve.setData

# ---- 3. the GUI thread busy 250 ms out of every 300 ms ----
m.clear_lockin_display()
fake = m.lockin1 = FakeLockin()
realtime(True)
pump(3.0, block_s=0.25)
realtime(False)
pump(0.1)
iv = intervals_ms(fake.starts)
inside = sorted(iv)[int(0.9 * len(iv)) - 1] if iv else None  # 90th percentile
check('GUI thread blocked 250 ms of every 300 ms: reads stay at 100 ms (min >= 95, 90 % <= 130, max < 180 ms), all plotted',
      len(iv) >= 25 and min(iv) >= 95 and inside <= 130 and max(iv) < 180
      and len(fake.starts) - 1 <= len(plotted()) <= len(fake.starts),
      f'n={len(iv)}, min={min(iv) if iv else None}, max={max(iv) if iv else None}, plotted={len(plotted())}')

# ---- 4. a new interval applies at once ----
fake = m.lockin1 = FakeLockin()
set_interval(3000)
realtime(True)
until(lambda: len(fake.starts) >= 1)
pump(0.2)
changed = time.monotonic()
set_interval(100)
until(lambda: len(fake.starts) >= 2, timeout=4.0)
realtime(False)
delay = round((fake.starts[1] - changed) * 1000) if len(fake.starts) >= 2 else None
check('changing 3000 -> 100 ms during the wait: the next read follows at once (<= 50 ms)',
      delay is not None and delay <= 50, f'delay={delay} ms')

# ---- 5. interval report, warnings ----
printed.clear()
fake = m.lockin1 = FakeLockin(read_s=0.002)
set_interval(20)
if reader is not None:
    reader.REPORT_MIN_S = 0  # the 50-interval rule alone (the 10 s limit is checked below)
realtime(True)
until(lambda: len(fake.starts) >= 60, timeout=5.0)
set_interval(40)
until(lambda: len(fake.starts) >= 70, timeout=5.0)
realtime(False)
pump(0.05)
pattern = re.compile(r'Realtime realDisChart1 \(lockin1\): (\d+) intervals, min (\d+) / median (\d+) / max (\d+) ms '
                     r'\(set (\d+) ms\); read time median (\d+) / max (\d+) ms')
lines = [pattern.fullmatch(p) for p in printed if p.startswith('Realtime realDisChart1')]
counts = [(int(g[1]), int(g[5])) for g in lines if g]
total = sum(n for n, _ in counts)
check('report every 50 intervals, at an interval change and at switch-off, with the set interval',
      lines and all(lines) and counts[0] == (50, 20) and counts[-1][1] == 40 and len(counts) >= 3
      # every read starts an interval except the first one and the first one after the change
      and all(n <= 50 for n, _ in counts) and total == len(fake.starts) - 2,
      f'reports={counts}, reads={len(fake.starts)}, lines={[p for p in printed if p.startswith("Realtime")][:4]}')
check('the reported median of the 20 ms batch is about 20 ms', lines and lines[0] and 18 <= int(lines[0][3]) <= 24,
      f'median={lines[0][3] if lines and lines[0] else None}')
if reader is not None:
    del reader.REPORT_MIN_S
printed.clear()
if reader is not None:
    reader._report([0.010, 0.030], [0.001, 0.003], 0.02)
check('report: the median of an even number of intervals is the mean of the middle two (10, 30 -> 20 ms)',
      printed and 'median 20 /' in printed[0] and 'read time median 2 /' in printed[0], f'{printed[:1]}')

printed.clear()
fake = m.lockin1 = FakeLockin(read_s=0.0)
set_interval(0)  # the box allows 0 ms: reads back to back
realtime(True)
pump(1.5)
realtime(False)
pump(0.05)
flood = [pattern.fullmatch(p) for p in printed if p.startswith('Realtime realDisChart1')]
iv = intervals_ms(fake.starts)
check('wait 0 ms: back-to-back reads keep a 2 ms pause; no report line within 10 s, one at switch-off',
      len(flood) == 1 and flood[0] and int(flood[0][1]) > 100 and iv and min(iv) >= 2,
      f'report lines={len(flood)}, reads={len(fake.starts)}, min interval={min(iv) if iv else None} ms')

printed.clear()
m.lockin1 = None
set_interval(30)
realtime(True)
pump(0.3)
missing = [p for p in printed if 'is not connected for realDisChart1' in p]
fake = m.lockin1 = FakeLockin()
connected = until(lambda: len(plotted()) > 0 and fake.starts, timeout=2.0)
fail_from = len(fake.starts)
fake.fail = True
pump(2.3)
failed = [p for p in printed if 'Realtime read of lockin1 failed' in p]
fail_iv = intervals_ms(fake.starts[fail_from:])
recovered_from = len(fake.starts)
fake.fail = False
pump(1.3)  # the 1 s retry ends, then reads every 30 ms
recovered = len(fake.starts) - recovered_from
fake.fail = True
pump(0.15)
failed_again = [p for p in printed if 'Realtime read of lockin1 failed' in p]
realtime(False)
fake = m.lockin1 = FakeLockin(read_s=1.05)
fake.fail = True  # a VISA timeout longer than 1 s
realtime(True)
pump(3.4)
realtime(False)
gaps = [round((start - end) * 1000) for end, start in zip(fake.ends, fake.starts[1:])]
check('a failed read that took 1.05 s: the next read starts 1 s after its end, not right away',
      gaps and min(gaps) >= 950, f'gaps after failed reads={gaps} ms')
check('missing lock-in: one warning, readings start once it is connected',
      len(missing) == 1 and connected, f'missing={len(missing)}, connected={connected}')
check('failing reads: one warning per failure streak, retried once a second, every 30 ms again after recovery',
      len(failed) == 1 and len(failed_again) == 2 and len(fail_iv) >= 1 and min(fail_iv) >= 950 and recovered > 10,
      f'warnings={len(failed)}/{len(failed_again)}, failing intervals={fail_iv}, reads after recovery={recovered}')

# ---- 6. switching off and on ----
m.clear_lockin_display()
fake = m.lockin1 = FakeLockin(read_s=0.3)
set_interval(50)
realtime(True)
until(lambda: len(fake.starts) >= 2)
time.sleep(0.05)              # the second read is in progress
shown = len(plotted())
realtime(False, wait_off=False)
pump(0.6)
check('switched off during a read: no further read, the read in progress is not plotted',
      len(fake.starts) == 2 and len(plotted()) == shown and not reader_running(cu1),
      f'reads={len(fake.starts)}, plotted={shown}->{len(plotted())}, running={reader_running(cu1)}')
realtime(True)
until(lambda: len(fake.starts) >= 3)
time.sleep(0.05)
realtime(False, wait_off=False)
realtime(True)                # on again while the read is still running
pump(1.0)
realtime(False)
check('on again during the last read: reading continues, never two reads at once',
      len(fake.starts) >= 5 and fake.max_active == 1, f'reads={len(fake.starts)}, max at once={fake.max_active}')

m.clear_lockin_display()
old = m.lockin1 = FakeLockin(value=11.0)
set_interval(20)
realtime(True)
until(lambda: len(old.starts) >= 1)
time.sleep(0.3)              # the GUI thread is busy: readings of the old lock-in queue up
realtime(False)              # no event processed in between
m.clear_lockin_display()
new = m.lockin1 = FakeLockin(value=22.0)
realtime(True)
pump(0.3)
realtime(False)
values = set(m.buffers['realDisChart1'])
check('restart while readings of the previous switch-on still wait: only the new readings are shown',
      len(old.starts) > 5 and values == {22.0}, f'old reads={len(old.starts)}, shown values={sorted(values)}')


class OffsetSession:
    """OUTP? 1 takes 200 ms and returns the X before or after AOFF."""
    def __init__(self):
        self.x, self.reading = 5.0, False

    def query(self, cmd):
        x, self.reading = self.x, True
        time.sleep(0.2)
        self.reading = False
        return str(x)

    def write(self, cmd):
        if cmd.startswith('AOFF'):
            self.x = 0.0

    def close(self):
        pass


sr = ns['SR830']('GPIB0::9::INSTR')
sr._inst = offset_session = OffsetSession()
m.lockin1 = sr
set_interval(1000)
m.clear_lockin_display()
realtime(True)
until(lambda: offset_session.reading)  # a Realtime read of the X before the offset is in progress
m.apply_lockin_parameter('lockin1', 'AutoZero')
pump(0.3)
realtime(False)
check('Auto Zero during a Realtime read: its readback (0) stays, the earlier reading (5) is not shown after it',
      ui.realDisChart1Num.text() == '0.0000e+00' and list(m.buffers['realDisChart1'])[-1:] == [0.0],
      f'box={ui.realDisChart1Num.text()}, chart={list(m.buffers["realDisChart1"])}')

# ---- 9. GUI commands while the reader reads back to back; Close Instr.; a blocked GUI ----
SR830 = ns['SR830']


class SlowSession:
    """A VISA session whose queries take read_s (the real SR830 driver, with its lock, wraps it)."""
    def __init__(self, read_s):
        self.read_s, self.closed = read_s, False

    def query(self, cmd):
        time.sleep(self.read_s)
        return '1.0e-3'

    def write(self, cmd):
        pass

    def close(self):
        self.closed = True


sr = SR830('GPIB0::8::INSTR')
sr._inst = SlowSession(0.2)
m.lockin1 = sr
set_interval(1)
realtime(True)
until(lambda: reader_running(cu1))
pump(0.3)
waits = []
for _ in range(6):
    t0 = time.monotonic()
    sr.write('PHAS 0')  # as a GUI command (phase, sensitivity, Auto Zero, close) from the GUI thread
    waits.append(round((time.monotonic() - t0) * 1000))
    pump(0.07)
realtime(False)
check('reader reading back to back (200 ms reads): a GUI lock-in command waits at most about one read',
      max(waits) <= 260, f'waits={waits} ms')

printed.clear()
m.lockin2 = None
ui.activeLockin1.setChecked(True)
closed = []
record = ns['print']


def print_slowly(*args, **kwargs):
    """A real print takes time (terminal, Live Process box and file): here 20 ms after 'Lock-in1 closed'."""
    record(*args, **kwargs)
    if args and str(args[0]).startswith('\u2713 Lock-in1 closed'):
        time.sleep(0.02)


ns['print'] = print_slowly
for _ in range(10):
    sr = SR830('GPIB0::8::INSTR')
    sr._inst = session = SlowSession(0.03)
    m.lockin1 = sr
    realtime(True)
    pump(0.1)
    m.closeInstruments()        # Close Instr. with Lock-in 1 ticked
    closed.append(session.closed and m.lockin1 is None)
    pump(0.1)
    realtime(False)
ns['print'] = record
spurious = [p for p in printed if 'Realtime read of lockin1 failed' in p]
check('Close Instr. ten times while the display reads back to back: closed, no read-failure warning',
      all(closed) and not spurious, f'closed={closed.count(True)}/10, warnings={spurious[:1]}')

m.clear_lockin_display()
fake = m.lockin1 = FakeLockin(read_s=0.0)
set_interval(1)
realtime(True)
pump(0.2)
index0, reads0 = m.indices['realDisChart1'], len(fake.starts)
time.sleep(1.0)               # the GUI thread is blocked for 1 s
reads_blocked = len(fake.starts) - reads0
app.processEvents()           # the readings queued meanwhile
shown_after = m.indices['realDisChart1'] - index0
realtime(False)
pump(0.05)
check('GUI thread blocked 1 s at 1 ms: the reader keeps reading, at most 100 readings wait to be shown',
      reads_blocked > 150 and shown_after <= 105, f'reads during the block={reads_blocked}, shown after={shown_after}')

# ---- 7. exit and application quit ----
fake1, fake2 = m.lockin1, m.lockin2 = FakeLockin(read_s=0.2), FakeLockin(read_s=0.2)
ui.wait2.setValue(50)
ui.wait2.editingFinished.emit()
realtime(True)
ui.realtimeDisp2.setChecked(True)
until(lambda: fake1.starts and fake2.starts)
time.sleep(0.05)
seen = {}
real_close = m.closeInstruments
m.closeInstruments = lambda only_active=True: seen.update(
    running=[reader_running(cu1), reader_running(cu2)], active=[fake1.active, fake2.active])
quits = []
app.quit = lambda: quits.append(True)
m.exitApp()
del m.closeInstruments, app.quit
ui.setEnabled(True)
check('Exit: both readers have ended (no read in progress) when the instruments close',
      seen == {'running': [False, False], 'active': [0, 0]} and quits == [True], f'seen={seen}, quit={quits}')
ui.realtimeDisp1.setChecked(False)
ui.realtimeDisp2.setChecked(False)
fake = m.lockin1 = FakeLockin()
set_interval(50)
realtime(True)
until(lambda: len(fake.starts) >= 4)
del ns['print']               # from here the module prints through the Live Process mirror again
app.aboutToQuit.emit()       # also stops the Live Process mirror; the scenarios after this one do not print
live_file = ''.join(f.read_text(encoding='utf-8') for f in TMP.glob('LiveProcess_*.txt'))
check('application quit (also the window close button) stops the readers first: their last report is in the '
      'Live Process file', not reader_running(cu1) and not reader_running(cu2)
      and 'Realtime realDisChart1 (lockin1): ' in live_file, f'report in file={"Realtime realDisChart1" in live_file}')
ui.realtimeDisp1.setChecked(False)

# ---- 8. SR830 driver: one command or query at a time ----


class Session:
    def __init__(self):
        self.active = self.max_active = 0
        self.closed_at = None
        self.lock = threading.Lock()

    def _io(self, reply=None):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.01)
        with self.lock:
            self.active -= 1
        return reply

    def query(self, cmd):
        return self._io(f'{cmd}-reply\n')

    def write(self, cmd):
        self._io()

    def close(self):
        self.closed_at = time.monotonic()


sr = SR830('GPIB0::8::INSTR')
sr._inst = session = Session()
same = SR830(' gpib0::8::instr')  # the other Lock-in box set to the same instrument
same._inst = session
other = SR830('GPIB0::7::INSTR')
replies = []


def worker(tag):
    device = same if tag == 'C' else sr
    for i in range(15):
        replies.append(device.query(f'{tag}{i}') == f'{tag}{i}-reply')
        device.write(f'W{tag}{i}')


threads = [threading.Thread(target=worker, args=(t,)) for t in 'ABC']
for t in threads:
    t.start()
for t in threads:
    t.join()
check('SR830: queries and writes from three threads, two objects on the same address, never overlap',
      session.max_active == 1 and all(replies) and len(replies) == 45
      and sr._io_lock is same._io_lock and sr._io_lock is not other._io_lock, f'max at once={session.max_active}')
session.query = lambda cmd: (time.sleep(0.3), 'slow')[1]
t = threading.Thread(target=lambda: sr.query('OUTP? 1'))
started = time.monotonic()
t.start()
time.sleep(0.05)
sr.close()
t.join()
check('SR830: close() waits for a query in progress', session.closed_at is not None
      and session.closed_at - started >= 0.29 and sr._inst is None,
      f'closed after {None if session.closed_at is None else round((session.closed_at - started) * 1000)} ms')

# open() of a second object on the same address (its device clear) while the first one queries
import pyvisa


class ClearingSession(Session):
    def clear(self):
        self._io()


shared = ClearingSession()
first = SR830('GPIB0::6::INSTR')
first._inst = shared
second = SR830('GPIB0::6::INSTR')


class FakeResourceManager:
    def open_resource(self, resource):
        return shared


real_rm = pyvisa.ResourceManager
pyvisa.ResourceManager = FakeResourceManager
try:
    t = threading.Thread(target=lambda: [first.query(f'Q{i}') for i in range(20)])
    t.start()
    time.sleep(0.05)
    opened = [second.open() for _ in range(3) if not setattr(second, '_inst', None)]
    t.join()
finally:
    pyvisa.ResourceManager = real_rm
check('SR830: open() of a second object on the same address (device clear) never overlaps a query',
      shared.max_active == 1 and opened == ['', '', ''], f'max at once={shared.max_active}, open={opened}')

ui.close()
shutil.rmtree(TMP, ignore_errors=True)
report(f'RESULT {SRC.name}: {sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
