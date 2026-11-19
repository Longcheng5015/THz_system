"""THz Emission v1.9: stage moves and lock-in reads per scan point, with the real scan worker and
fake instruments that count every driver call.

1. Stage2 and Rotary1-3 move and read back only when their target changes. The first point of every
   scan moves; a failed move makes the next point move again; a replaced device always moves.
2. Each lock-in is read with one SNAP? 1,2 per point: no get_x/get_y and no 50 ms gap between X and Y.
3. Stage1's position is the value move_to() returned; position() is not called (scan points and the
   peak search).
Also: Jog buttons are disabled and Realtime lock-in timers are stopped during a scan (nothing else may
move an axis or query a lock-in while the cache and SNAP? reads are in use); repeat blocks, three coupled
rotaries and a calibration table; the real SR830.snap() parses a SNAP? reply.
Error and exit paths: controls stay disabled until the worker has ended (also when a scan plan is rejected
in the worker); Exit stops the scan and closes the instruments only after the worker has ended, or the
exit can be cancelled after a timeout; the window stays disabled while exiting, and a stabilization
thread started after the exit began is stopped too. Controls come back exactly once per scan, on the GUI
thread, after the worker has ended. Points not acquired (failed move or read, scan stopped early) are NaN;
a trace with NaN points gets no FFT spectrum (and the previous one moves to the red curve). A lock-in not
used in the scan is stored as NaN. Clear Display also clears both Realtime traces.

    python OPTP_System/tests/test_thz_v19_point_io.py [path to the GUI .py, default THz Emission v1.9]

No hardware, offscreen. QSettings and data go to a temporary folder that is removed at the end.
"""
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[2]
SRC = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'THz_emission_system/THz_emission_system_iTC_v1.9.py'
os.chdir(SRC.parent)
sys.path.insert(0, str(SRC.parent))
source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'thz_point_io_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)

import h5py
import numpy as np
from PySide6.QtCore import QSettings, QThread, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

REAL = sys.__stdout__
TMP = Path(tempfile.mkdtemp(prefix='thz_v19_point_io_'))
ns['QSettings'] = lambda org, name: QSettings(str(TMP / f'{org}.{name}.ini'), QSettings.IniFormat)


def data_folder(self):
    self.dataSave_path = str(TMP)
    self.ui.dataSavePath.setText(str(TMP))
    return str(TMP)


ns['moSys'].setup_data_folder = data_folder

calls = []   # (device, method, argument) in call order, from every thread
sleeps = []  # every time.sleep() made by the GUI module


class TimeProxy:
    """The module's time.sleep() is recorded; everything else is the real time module."""
    def __getattr__(self, name):
        return getattr(time, name)

    def sleep(self, seconds):
        sleeps.append(seconds)
        time.sleep(seconds)


ns['time'] = TimeProxy()
app = QApplication.instance() or QApplication([])
m = ns['moSys']()
ui = m.ui
warnings, errors, results = [], [], []
QMessageBox.warning = staticmethod(lambda *args: warnings.append(args[2]))
QMessageBox.question = staticmethod(lambda *args: QMessageBox.Yes)
m.on_handle_scan_error = lambda message: errors.append(message)


def report(msg):
    REAL.write(msg + "\n")
    REAL.flush()


def check(label, condition, detail=''):
    results.append(bool(condition))
    report(('PASS ' if condition else 'FAIL ') + label + ('' if condition or not detail else f'  [{detail}]'))


class PIStage:
    """Stage1 like physik_E861: move_to() returns the position it measured (here target + 2 um)."""
    def __init__(self, pos, delay=0.0, slow_move=None, slow_delay=0.0):
        self.pos, self.delay, self.slow_move, self.slow_delay, self.count = pos, delay, slow_move, slow_delay, 0

    def move_to(self, target):
        self.count += 1
        calls.append(('stage1', 'move_to', target))
        time.sleep(self.slow_delay if self.count == self.slow_move else self.delay)
        self.pos = target
        return target + 0.002

    def position(self):
        calls.append(('stage1', 'position', None))
        return self.pos

    def travel_limits(self):
        return 0, 1000


class KinesisAxis:
    """Stage2 / rotary like the Kinesis drivers: move_to() returns nothing, position() reads back
    target + 0.001. fail_on / pos_fail_on list 1-based move_to / position calls that raise."""
    def __init__(self, name, pos, fail_on=(), pos_fail_on=()):
        self.name, self.pos, self.fail_on, self.attempts = name, pos, set(fail_on), 0
        self.pos_fail_on, self.reads = set(pos_fail_on), 0

    def move_to(self, target):
        self.attempts += 1
        calls.append((self.name, 'move_to', target))
        if self.attempts in self.fail_on:
            raise RuntimeError('simulated move failure')
        self.pos = target

    def position(self):
        self.reads += 1
        calls.append((self.name, 'position', None))
        if self.reads in self.pos_fail_on:
            raise RuntimeError('simulated read-back failure')
        return self.pos + 0.001

    def travel_limits(self):
        return 0, 1000


def signal_value(offset):
    """What the fake lock-ins see: depends on where the axes really are at the moment of the read."""
    pos = lambda name: getattr(getattr(m, name, None), 'pos', 0.0) or 0.0
    return offset + pos('stage1') + pos('stage2') / 1000 + pos('rotary2') / 100


REALTIME_READ_S = [0.0]  # duration of a Realtime read (reader thread only)


class Lockin:
    def __init__(self, name, offset, fail_on=()):
        self.name, self.offset, self.fail_on, self.snaps = name, offset, set(fail_on), 0

    def snap(self, *params):
        self.snaps += 1
        calls.append((self.name, 'snap', params))
        if self.snaps in self.fail_on:
            raise RuntimeError('simulated GPIB timeout')
        x = signal_value(self.offset)
        return [x, -x][:len(params)]

    def get_x(self):
        calls.append((self.name, 'get_x', None))
        if type(QThread.currentThread()).__name__ == 'RealtimeReader':
            time.sleep(REALTIME_READ_S[0])  # a Realtime reader thread (from THz v2.0 / OPTP v4.5 / MO v3.1 / Imaging v2.2)
        return signal_value(self.offset)

    def get_y(self):
        calls.append((self.name, 'get_y', None))
        return -signal_value(self.offset)


move_log = []  # (targets, (ok, positions)) of every move_active_stages call
original_move = m.move_active_stages


FAIL_CALL = [None]  # index of a move_active_stages call to fail as a failed move (scenario: last point)


def logged_move(targets):
    if FAIL_CALL[0] is not None and len(move_log) == FAIL_CALL[0]:
        print(f"Error moving active stages: simulated failure of the move to {targets}")
        move_log.append((targets, (False, None)))
        return False, None
    result = original_move(targets)
    move_log.append((targets, result))
    return result


m.move_active_stages = logged_move

enable_log = []  # (scanning, called on the GUI thread) for every set_ControlsEnabledDuringScan call
original_enable = m.set_ControlsEnabledDuringScan


def logged_enable(scanning):
    enable_log.append((scanning, QThread.currentThread() == app.thread()))
    return original_enable(scanning)


m.set_ControlsEnabledDuringScan = logged_enable
ONCE = [(True, True), (False, True)]  # disabled at the start, enabled again exactly once, both on the GUI thread


def reset(stage1_NO=4, stage2_NO=2, rot2_NO=2, mode='THz_Scan', rot2_fail_on=(), rot2_pos_fail_on=(),
          rot_active=(False, True, False), stage1_rep=1):
    for name in ('activeiTC', 'ScanT', 'AutoBlock', 'activeFlipMount', 'activePowerMeter', 'pmRecord',
                 'realtimeDisp1', 'realtimeDisp2'):
        getattr(ui, name).setChecked(False)
    for name in ('activeStage1', 'activeStage2', 'activeLockin1', 'activeLockin2'):
        getattr(ui, name).setChecked(True)
    ui.scanMode.setCurrentText(mode)
    ui.Rot_stages_couple.setChecked(True)
    ui.pol_cali_mode.setChecked(False)
    m.cali_table = None
    ui.wait1.setValue(0)
    ui.wait2.setValue(0)
    for name in ('scanRepNO1', 'scanRepNO2', 'ScanRepNO_R1', 'ScanRepNO_R2'):
        getattr(ui, name).setValue(1)
    ui.scanRepNO1.setValue(stage1_rep)
    for n, start, count in ((1, 10, stage1_NO), (2, 50, stage2_NO)):
        getattr(ui, f'iPos{n}').setValue(start)
        getattr(ui, f'stage{n}Step1').setValue(1)
        getattr(ui, f'stage{n}Step1NO').setValue(count)
        getattr(ui, f'stage{n}Step2NO').setValue(0)
        getattr(ui, f'stage{n}Step3NO').setValue(0)
    for n in (1, 2, 3):  # Rotary n: start n*10 deg, step n deg, rot2_NO states when active
        getattr(ui, f'activeRot{n}').setChecked(rot_active[n - 1])
        getattr(ui, f'iRot{n}').setValue(n * 10)
        getattr(ui, f'rotary{n}Step').setValue(n)
        getattr(ui, f'rotary{n}StepNO').setValue(rot2_NO)
        failures = (rot2_fail_on, rot2_pos_fail_on) if n == 2 else ((), ())
        setattr(m, f'rotary{n}', KinesisAxis(f'rotary{n}', n * 10, *failures) if rot_active[n - 1] else None)
    m.stage1, m.stage2 = PIStage(10), KinesisAxis('stage2', 50)
    m.lockin1, m.lockin2 = Lockin('lockin1', 0.0), Lockin('lockin2', 1000.0)
    m.mercuryiTC = None
    m.is_custom_save_path = True


run_number = 0
during = {}  # widget states right after runScan(), while the scan is in progress
JOGS = [f'{axis}Jog{side}' for axis in ('stage1', 'stage2', 'rot1', 'rot2', 'rot3') for side in 'LR']


def run():
    """Run one scan with the real worker; return the four lock-in datasets (flattened) or None."""
    global run_number
    run_number += 1
    folder = TMP / str(run_number)
    folder.mkdir()
    m.dataSave_path = str(folder)
    calls.clear(); sleeps.clear(); move_log.clear(); warnings.clear(); errors.clear(); enable_log.clear()
    previous = m.scan_Thread
    m.runScan()
    during.clear()
    during.update(jog_enabled=[getattr(ui, n).isEnabled() for n in JOGS],
                  realtime=[ui.realtimeDisp1.isChecked(), ui.realtimeDisp2.isChecked()],
                  timers=[realtime_active(m.chart_updaters[c]) for c in ('realDisChart1', 'realDisChart2')],
                  readers_running=[getattr(m.chart_updaters[c], 'reader', None) is not None
                                   and m.chart_updaters[c].reader.isRunning() for c in ('realDisChart1', 'realDisChart2')])
    if m.scan_Thread is not previous:
        deadline = time.monotonic() + 30
        while m.scan_Thread.isRunning():
            app.processEvents()
            if time.monotonic() > deadline:
                raise RuntimeError('scan worker timed out')
            time.sleep(0.005)
        m.scan_Thread.wait()
        for _ in range(5):
            app.processEvents()
    files = list(folder.glob('*.h5'))
    if not files:
        return None
    with h5py.File(files[0], 'r') as f:
        return {key: f[key][()].ravel() for key in ('lockin1_X', 'lockin1_Y', 'lockin2_X', 'lockin2_Y')}


def moves(device):
    return [arg for dev, method, arg in calls if dev == device and method == 'move_to']


def count(device, method):
    return sum(1 for dev, meth, _ in calls if dev == device and meth == method)


def count_after_first_snap(device, method):
    """Calls of 'method' after the first SNAP? of this device, i.e. after the scan started reading it. A
    Realtime reader thread may still read once between calls.clear() and the scan start."""
    first = next((i for i, (dev, meth, _) in enumerate(calls) if dev == device and meth == 'snap'), len(calls))
    return sum(1 for dev, meth, _ in calls[first:] if dev == device and meth == method)


def realtime_active(updater):
    """Realtime display running: the QTimer up to THz v1.9 / OPTP v4.4 / MO v3.0 / Imaging v2.1, then a reader
    thread that has not been asked to stop."""
    reader = getattr(updater, 'reader', None)
    return updater.timer.isActive() if reader is None else reader.isRunning() and not reader.stop_requested()


def realtime_update(name):
    """One Realtime reading shown in chart 'name': the QTimer slot up to THz v1.9 / OPTP v4.4 / MO v3.0 /
    Imaging v2.1; from the next versions the reader thread is switched on until its first reading is shown."""
    updater = m.chart_updaters[name]
    if getattr(updater, 'reader', None) is None:
        updater.update()
        return
    index = m.indices[name]
    interval = updater.interval
    updater.update_Interval(10000)  # exactly one reading: the first read starts at once, the next 10 s later
    button = getattr(ui, 'realtimeDisp' + name[-1])
    button.setChecked(True)
    deadline = time.monotonic() + 3
    while m.indices[name] == index and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    button.setChecked(False)
    updater.reader.wait(3000)
    updater.update_Interval(interval)


def changes(axis_index):
    """Targets requested for one axis, keeping only the first of each run of equal targets."""
    requested = [targets[axis_index] for targets, _ in move_log]
    return [t for i, t in enumerate(requested) if i == 0 or t != requested[i - 1]]


# ---- 1. THz_Scan: Rot2 (outermost) x Stage2 x Stage1 (innermost) = 2 x 2 x 4 points ----
reset()
data = run()
points = len(move_log) - 1  # the first call moves to the initial positions
check('scan ran: 16 points, no warnings or errors', data is not None and points == 16
      and not warnings and not errors, f'points={points}, warnings={warnings}, errors={errors}')
check('Stage2 moves only when its target changes (4 moves instead of 17)',
      moves('stage2') == changes(1) and len(moves('stage2')) == 4 and count('stage2', 'position') == 4,
      f"moves={moves('stage2')}, expected={changes(1)}")
check('Rotary2 moves only when its angle changes (2 moves instead of 17)',
      moves('rotary2') == changes(3) == [20, 22] and count('rotary2', 'position') == 2,
      f"moves={moves('rotary2')}")
check('Stage1 moves at every point; position() never called',
      len(moves('stage1')) == 17 and count('stage1', 'position') == 0)
ok_positions = [(t, p) for t, (ok, p) in move_log if ok]
check('reported positions: Stage1 from move_to(), Stage2/Rotary2 from the last read-back, inactive -1',
      len(ok_positions) == 17 and all(
          p[0] == round(t[0] + 0.002, 3) and p[1] == round(t[1] + 0.001, 3)
          and p[3] == round(t[3] + 0.001, 3) and p[2] == -1 and p[4] == -1 for t, p in ok_positions))
check('each lock-in: one SNAP? 1,2 per point, no OUTP? reads',
      all(count(name, 'snap') == 16 and count(name, 'get_x') == 0 and count(name, 'get_y') == 0
          for name in ('lockin1', 'lockin2'))
      and all(arg == (1, 2) for dev, meth, arg in calls if meth == 'snap'))
check('no 50 ms wait between X and Y', 0.05 not in sleeps, f'sleeps={sorted(set(sleeps))}')
check('normal end: controls disabled at the start and enabled again exactly once, on the GUI thread',
      enable_log == ONCE and ui.runButton.isEnabled(), f'enable_log={enable_log}')
expected_x = sorted(t[0] + t[1] / 1000 + t[3] / 100 for t, (ok, _p) in move_log[1:] if ok)
check('stored X/Y: X and Y from the same snapshot, at the planned positions, for both lock-ins',
      data is not None and len(expected_x) == 16 and moves('stage1')[1:5] == [10, 10.001, 10.002, 10.003]
      and np.allclose(np.sort(data['lockin1_X']), expected_x)
      and np.allclose(data['lockin1_Y'], -data['lockin1_X'])
      and np.allclose(data['lockin2_X'], data['lockin1_X'] + 1000)
      and np.allclose(data['lockin2_Y'], -data['lockin2_X']))

# ---- 1b. the other two modes (THz_pol has the rotation innermost, so Rotary2 changes at every point) ----
for mode in ('2D_THz', 'THz_pol'):
    reset(mode=mode)
    data = run()
    check(f'{mode}: 16 points; Stage2/Rotary2 move exactly when their targets change; 16 snaps per lock-in',
          data is not None and len(move_log) == 17 and not errors
          and moves('stage2') == changes(1) and moves('rotary2') == changes(3)
          and count('stage1', 'position') == 0 and count('lockin1', 'snap') == 16 and count('lockin2', 'snap') == 16
          and (data['lockin1_X'] > 10).sum() == 16 and np.allclose(data['lockin1_Y'], -data['lockin1_X']),
          f"stage2 {len(moves('stage2'))} moves, rotary2 {len(moves('rotary2'))} moves")
    report(f'  {mode}: Stage2 {len(moves("stage2"))} moves, Rotary2 {len(moves("rotary2"))} moves for 16 points')

# ---- 2. a new scan moves every axis again, even to the same target ----
reset(stage2_NO=1, rot2_NO=1)
for attempt in (1, 2):
    m.stage2.pos, m.rotary2.pos = 50, 20  # already there, as at the end of the previous scan
    data = run()
    check(f'constant targets, scan {attempt}: Stage2 and Rotary2 move once at the start, then never',
          data is not None and len(move_log) == 5 and moves('stage2') == [50] and moves('rotary2') == [20]
          and np.isfinite(data['lockin1_X']).sum() == 4,
          f"moves stage2={moves('stage2')}, rotary2={moves('rotary2')}")

# ---- 3. a failed move: that point is skipped, the next point moves the axis again ----
reset(rot2_fail_on=(2,))  # the first change to 22 deg fails
data = run()
check('failed Rotary2 move: retried at the next point, then skipped again',
      moves('rotary2') == [20, 22, 22] and count('rotary2', 'position') == 2,
      f"moves={moves('rotary2')}")
check('failed point is NaN in all four datasets (v1.8: 0); the other 15 are acquired',
      data is not None and all(np.isnan(data[k]).sum() == 1 for k in data) and (data['lockin1_X'] > 10).sum() == 15
      and not any((data[k] == 0).any() for k in data))
empty = lambda y: y is None or len(y) == 0  # pyqtgraph reads an emptied curve back as None
blue, red = (m.curves['fdsChart'][c].getData()[1] for c in ('blue', 'red'))
check('FFT display: the sweep with the NaN point has no spectrum (now red, empty); the last sweep has one',
      empty(red) and blue is not None and len(blue) > 0 and np.isfinite(np.abs(blue)).all(),
      f'red={None if red is None else len(red)}, blue={None if blue is None else len(blue)}')
xs = [10.000, 10.001, 10.002, 10.003]
m.update_TDS_FDS_chart({'tds_x': xs, 'tds_y': [1.0, 2.0, 3.0, 4.0]})
clean = np.array(m.curves['fdsChart']['blue'].getData()[1])
m.update_TDS_FDS_chart({'tds_x': xs, 'tds_y': [1.0, np.nan, np.nan, 2.0]})  # two acquired points
blue, red = (m.curves['fdsChart'][c].getData()[1] for c in ('blue', 'red'))
check('FFT display with only two acquired points: no exception, blue empty, the previous spectrum is red',
      len(clean) > 0 and empty(blue) and np.allclose(np.asarray(red), clean))
m.update_TDS_FDS_chart({'tds_x': xs, 'tds_y': [4.0, 3.0, 2.0, 1.0]})
blue, red = (m.curves['fdsChart'][c].getData()[1] for c in ('blue', 'red'))
check('next complete trace: blue has its spectrum, red is empty (the trace before had none)',
      blue is not None and len(blue) > 0 and empty(red))
full = np.array(m.curves['fdsChart']['blue'].getData()[1])
m.update_TDS_FDS_chart({'tds_x': [10.000, 10.001], 'tds_y': [1.0, 2.0]})  # a complete two-point trace
blue, red = (m.curves['fdsChart'][c].getData()[1] for c in ('blue', 'red'))
two_ok = empty(blue) and np.allclose(np.asarray(red), full)
m.update_TDS_FDS_chart({'tds_x': [10.000], 'tds_y': [1.0]})  # a single point
blue, red = (m.curves['fdsChart'][c].getData()[1] for c in ('blue', 'red'))
one_ok = empty(blue) and empty(red)
m.update_TDS_FDS_chart({'tds_x': xs, 'tds_y': [1.0, 2.0, 3.0, 4.0]})
blue, red = (m.curves['fdsChart'][c].getData()[1] for c in ('blue', 'red'))
check('two-point and single-point traces: no exception, no spectrum, red always the previous trace',
      two_ok and one_ok and np.allclose(np.asarray(blue), clean) and empty(red),
      f'two_ok={two_ok}, one_ok={one_ok}')
failed_at = next(i for i, (_, (ok, _p)) in enumerate(move_log) if not ok)
check('Stage2 (moved before the failure at that point) is not moved again at the next point',
      move_log[failed_at + 1][0][1] == move_log[failed_at][0][1]
      and moves('stage2') == changes(1), f"moves={moves('stage2')}")

# ---- 4. a replaced device (reconnect) always moves ----
m._scan_axis_cache = {}
calls.clear()
a, b = KinesisAxis('axisA', 0), KinesisAxis('axisB', 0)
m._move_unless_there('rotary2', a, 5)
m._move_unless_there('rotary2', a, 5)
m._move_unless_there('rotary2', b, 5)
m._move_unless_there('rotary2', b, 5)
check('same target on a replaced device object moves once more', moves('axisA') == [5] and moves('axisB') == [5])

# ---- 4b. a failed read-back after a move: that point is skipped, the next point moves again ----
reset(rot2_pos_fail_on=(2,))  # the read-back after the change to 22 deg fails
data = run()
check('failed Rotary2 read-back: no cache entry, the next point moves and reads back again',
      moves('rotary2') == [20, 22, 22] and count('rotary2', 'position') == 3
      and data is not None and np.isnan(data['lockin1_X']).sum() == 1,
      f"moves={moves('rotary2')}, reads={count('rotary2', 'position')}")

# ---- 4c. repeat blocks with three coupled rotaries ----
reset(rot_active=(True, True, True), stage1_rep=2)
data = run()
check('Stage1 repeat 2, Rotary1-3 coupled: every axis moves exactly when its target changes; all points acquired',
      data is not None and not errors and data['lockin1_X'].size == 32 and (data['lockin1_X'] > 10).all()
      and all(moves(name) == changes(i) for i, name in ((1, 'stage2'), (2, 'rotary1'), (3, 'rotary2'), (4, 'rotary3')))
      and moves('rotary1') == [10, 11] and moves('rotary3') == [30, 33],
      f"errors={errors}, stage2={moves('stage2')}, rot1={moves('rotary1')}, rot3={moves('rotary3')}")

# ---- 4d. calibration table (Rotary1 + Rotary2 from the table) ----
reset(rot_active=(True, True, False), rot2_NO=3)
ui.pol_cali_mode.setChecked(True)
m.cali_table = {'rot2_cali': [20, 22.5, 25], 'rot1_cali': [11, 13, 15]}
data = run()
check('calibration table: Rotary1 follows the table (interpolated at the Rotary2 angles); both move once per state',
      data is not None and not errors and (data['lockin1_X'] > 10).sum() == 24
      and moves('rotary1') == changes(2) and np.allclose(moves('rotary1'), [10, 11, 12.6, 14.2])
      and moves('rotary2') == changes(3) == [20, 22, 24],
      f"errors={errors}, rot1={moves('rotary1')}, rot2={moves('rotary2')}")

# ---- 4e. Realtime switched on before the scan, and the Jog buttons during the scan ----
reset()
REALTIME_READ_S[0] = 0.3  # runScan() must wait for a Realtime read in progress
ui.realtimeDisp1.setChecked(True)
ui.realtimeDisp2.setChecked(True)
calls.clear()
deadline = time.monotonic() + 1.5
while time.monotonic() < deadline:  # let the Realtime timers query the lock-ins before the scan
    app.processEvents()
    time.sleep(0.01)
before = count('lockin1', 'get_x') + count('lockin2', 'get_x')
data = run()
check('Realtime on before the scan: switched off and stopped at scan start, no OUTP? during the scan',
      before > 0 and during['realtime'] == [False, False] and during['timers'] == [False, False]
      and during['readers_running'] == [False, False]
      and all(count_after_first_snap(n, 'get_x') == 0 and count_after_first_snap(n, 'get_y') == 0
              and count(n, 'snap') == 16
              for n in ('lockin1', 'lockin2'))
      and not ui.realtimeDisp1.isChecked() and not ui.realtimeDisp2.isChecked(),
      f"before={before}, during={during}, get_x={count('lockin1', 'get_x')}+{count('lockin2', 'get_x')}")
REALTIME_READ_S[0] = 0.0
check('Jog buttons disabled during the scan and enabled again afterwards',
      during['jog_enabled'] == [False] * 10 and all(getattr(ui, n).isEnabled() for n in JOGS),
      f"during={during.get('jog_enabled')}")

# ---- 4f. the real SR830.snap() parses a SNAP? reply ----
class FakeVisa:
    def __init__(self):
        self.sent = []

    def query(self, cmd):
        self.sent.append(cmd)
        return '1.234560e-06,-7.890000e-07\n'


sr = ns['SR830']('GPIB0::8::INSTR')
sr._inst = FakeVisa()
x, y = sr.snap(1, 2)
check('SR830.snap(1, 2) sends "SNAP? 1,2" and returns X, Y as floats',
      sr._inst.sent == ['SNAP? 1,2'] and x == 1.23456e-06 and y == -7.89e-07)

# ---- 4g. a lock-in read that fails: NaN for that lock-in only ----
reset()
m.lockin1 = Lockin('lockin1', 0.0, fail_on=(3,))
data = run()
check('Lock-in 1 read error: its X/Y are NaN at that point (v1.8: 0), Lock-in 2 is still stored',
      data is not None and np.isnan(data['lockin1_X']).sum() == 1 and np.isnan(data['lockin1_Y']).sum() == 1
      and np.isfinite(data['lockin2_X']).all() and (data['lockin1_X'] == 0).sum() == 0)

# ---- 4h. scan plan rejected in the worker: controls stay disabled while the worker still runs ----
reset()
m.stage2.travel_limits = lambda: (0, 1)  # every Stage2 target is outside: rejected after the worker started
in_block = threading.Event()


def slow_block(thread=None):  # the worker's end-of-scan AutoBlock, made slow (a flip-mount move)
    in_block.set()
    time.sleep(0.8)


m.auto_block_after_scan = slow_block
real_error = ns['moSys'].on_handle_scan_error.__get__(m)
m.on_handle_scan_error = lambda message: (errors.append(message), real_error(message))
folder = TMP / 'rejected'
folder.mkdir()
m.dataSave_path = str(folder)
errors.clear(); enable_log.clear()
m.runScan()
deadline = time.monotonic() + 5
while not (errors and in_block.is_set()) and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.01)
for _ in range(10):  # let the error slot run while the worker sleeps in AutoBlock
    app.processEvents()
    time.sleep(0.01)
running = m.scan_Thread.isRunning()
locked = (not ui.runButton.isEnabled(), [getattr(ui, n).isEnabled() for n in JOGS], ui.realtimeDisp1.isEnabled())
m.scan_Thread.wait(5000)
for _ in range(5):
    app.processEvents()
check('rejected plan: while the worker still runs AutoBlock, Run, Jog and Realtime stay disabled; enabled once after it ends',
      errors and 'travel' in errors[0] and running and locked == (True, [False] * 10, False)
      and enable_log == ONCE and ui.runButton.isEnabled() and all(getattr(ui, n).isEnabled() for n in JOGS),
      f'errors={errors[:1]}, running={running}, locked={locked}, enable_log={enable_log}')
del m.auto_block_after_scan

# ---- 4h2. an exception in the worker: error reported, controls back once ----
reset()


def broken_scan(thread):
    raise RuntimeError('simulated worker exception')


m._execute_scan_logic = broken_scan
run()
del m._execute_scan_logic
check('worker exception: error reported, controls enabled again exactly once, on the GUI thread',
      errors and 'simulated worker exception' in errors[0] and enable_log == ONCE and ui.runButton.isEnabled(),
      f'errors={errors[:1]}, enable_log={enable_log}')
m.on_handle_scan_error = lambda message: errors.append(message)

# ---- 4h3. scan refused before it starts (an active instrument is not connected) ----
reset()
m.lockin2 = None  # Lock-in 2 is ticked active but not connected
ui.realtimeDisp1.setChecked(True)
data = run()
check('refused before start: no data file, controls never disabled, Realtime left as it was',
      data is None and warnings and 'not connected' in warnings[0] and enable_log == []
      and ui.runButton.isEnabled() and ui.realtimeDisp1.isChecked(),
      f'warnings={warnings[:1]}, enable_log={enable_log}')
ui.realtimeDisp1.setChecked(False)


class FakeStab(QThread):
    """A stabilization thread that only ends when asked to, like iTCstabilizeThread before the iTC settles."""
    def __init__(self):
        super().__init__()
        self.stop_flag = False

    def request_stop(self):
        self.stop_flag = True

    def run(self):
        while not self.stop_flag:
            self.msleep(10)


# ---- 4i. Exit during a long move (longer than v1.8's 2 s wait), with a late stabilization thread ----
reset()
m.stage1.slow_move, m.stage1.slow_delay = 6, 2.5  # the 6th Stage1 move (5th point) takes 2.5 s
m.itc_stab_thread = None
folder = TMP / 'exit'
folder.mkdir()
m.dataSave_path = str(folder)
closed, quits = [], []
m.closeInstruments = lambda only_active=True: closed.append(
    (m.scan_Thread.isRunning(), m.itc_stab_thread is not None and m.itc_stab_thread.isRunning()))
app.quit = lambda: quits.append(True)
enable_log.clear()
m.runScan()
first_thread = m.scan_Thread
deadline = time.monotonic() + 5
while m.stage1.count < 6 and time.monotonic() < deadline:  # Exit while the slow move is running
    app.processEvents()
    time.sleep(0.01)
probe = {}


def during_exit():
    probe['window'] = ui.isEnabled()
    probe['run'] = ui.runButton.isEnabled()
    QTest.mouseClick(ui.runButton, Qt.LeftButton)  # a click on Run while exiting must not start a scan
    probe['same_scan'] = m.scan_Thread is first_thread
    stab = FakeStab()  # a stabilization thread created after the exit began
    stab.start()
    m.itc_stab_thread = probe['stab'] = stab


QTimer.singleShot(300, during_exit)
m.exitApp()
with h5py.File(next(folder.glob('*.h5')), 'r') as f:
    stopped = f['lockin1_X'][()].ravel()
check('Exit during a long move: instruments closed only after the scan and a late stabilization thread ended, then quit',
      closed == [(False, False)] and quits == [True] and probe.get('stab') is not None
      and probe['stab'].stop_flag and not probe['stab'].isRunning(), f'closed={closed}, quits={quits}')
check('while exiting the window is disabled; clicking Run starts no scan; controls came back once (window still off)',
      probe.get('window') is False and probe.get('run') is False and probe.get('same_scan') is True
      and enable_log == ONCE and not ui.isEnabled(), f'probe={probe}, enable_log={enable_log}')
check('scan stopped early: points not reached are NaN, none are 0',
      np.isnan(stopped).sum() > 0 and (stopped > 10).sum() > 0 and (stopped == 0).sum() == 0,
      f'acquired={(stopped > 10).sum()}, nan={np.isnan(stopped).sum()}')
ui.setEnabled(True)  # the patched quit() did not end the program
m.itc_stab_thread = None

# ---- 4j. a worker still busy after the timeout: the exit is cancelled through exitApp() ----
reset()
m.stage1.delay = 0.5  # long moves
folder = TMP / 'exit_cancel'
folder.mkdir()
m.dataSave_path = str(folder)
closed.clear(); quits.clear()
m.runScan()
t0 = time.monotonic()
while time.monotonic() - t0 < 0.2:
    app.processEvents()
    time.sleep(0.01)
answers = iter([QMessageBox.Yes, QMessageBox.No])  # "Exit?" -> Yes, "keep waiting?" -> No
QMessageBox.question = staticmethod(lambda *args: next(answers))
saved_defaults = ns['moSys'].stop_workers_for_exit.__defaults__
ns['moSys'].stop_workers_for_exit.__defaults__ = (0.2,)  # shorter timeout for the test
m.exitApp()
ns['moSys'].stop_workers_for_exit.__defaults__ = saved_defaults
QMessageBox.question = staticmethod(lambda *args: QMessageBox.Yes)
after_cancel = (ui.isEnabled(), m.scan_Thread.isRunning(), ui.runButton.isEnabled(), list(closed), list(quits), m.stop_flag)
m.scan_Thread.wait(10000)
for _ in range(5):
    app.processEvents()
check('timeout, exit cancelled: window usable again with scan controls still locked, nothing closed, the scan stops',
      after_cancel == (True, True, False, [], [], True) and not m.scan_Thread.isRunning() and ui.runButton.isEnabled(),
      f'after_cancel={after_cancel}')

# ---- 4k. no worker running: nothing to wait for ----
check('no running worker (finished thread, or none): stop_workers_for_exit returns at once',
      m.stop_workers_for_exit() is True)
saved_thread, m.scan_Thread = m.scan_Thread, None
check('scan thread never created: stop_workers_for_exit returns at once', m.stop_workers_for_exit() is True)
m.scan_Thread = saved_thread
del m.closeInstruments
del app.quit

# ---- 4l. only Lock-in 2 used: Lock-in 1 is NaN, not 0 ----
reset()
ui.activeLockin1.setChecked(False)  # Lock-in 1 stays connected (reset() sets it) but is not used
ui.wait2.setValue(30)  # Lock-in 2 alone must still wait its own settle time before each read
data = run()
check('only Lock-in 2 used: it waits the full wait2 (30 ms) before each of its 16 reads (v1.8: no wait)',
      sleeps.count(0.03) == 16 and count('lockin2', 'snap') == 16, f'sleeps={sorted(set(sleeps))}')
fds_blue = m.curves['fdsChart']['blue'].getData()[1]
check('only Lock-in 2 used: Lock-in 1 X/Y are NaN at every point (v1.8: 0), Lock-in 2 is stored; no FFT spectrum',
      data is not None and not errors and count('lockin1', 'snap') == 0 and np.isnan(data['lockin1_X']).all() and np.isnan(data['lockin1_Y']).all()
      and np.isfinite(data['lockin2_X']).all() and (data['lockin2_X'] > 1000).all()
      and (fds_blue is None or len(fds_blue) == 0), f'errors={errors[:1]}')

# ---- 4l2. a connected lock-in whose 'active' box is unticked is not read ----
reset()
ui.activeLockin2.setChecked(False)  # still connected: m.lockin2 is set by reset()
data = run()
check('Lock-in 2 connected but not active: never read, stored as NaN; Lock-in 1 unaffected',
      data is not None and count('lockin2', 'snap') == 0 and np.isnan(data['lockin2_X']).all()
      and np.isfinite(data['lockin1_X']).all() and count('lockin1', 'snap') == 16)

# ---- 4m. Clear Display clears the four scan traces and both Realtime traces ----
reset()
m.lockin1, m.lockin2 = Lockin('lockin1', 0.0), Lockin('lockin2', 1000.0)
for _ in range(5):  # Realtime traces, read from the lock-ins as the Realtime timer does
    realtime_update('realDisChart1')
    realtime_update('realDisChart2')
m.update_lockin_charts({'l1x': 1.0, 'l1y': 2.0, 'l2x': 3.0, 'l2y': 4.0})  # scan traces
CHARTS = ('lockin1XChart', 'lockin1YChart', 'lockin2XChart', 'lockin2YChart', 'realDisChart1', 'realDisChart2')
filled = all(len(m.buffers[c]) > 0 for c in CHARTS)
number = ui.realDisChart1Num.text()
ui.clearLockinDisplay.click()
cleared = all(len(m.buffers[c]) == 0 and m.indices[c] == -1 and m.curves[c].getData()[1] is None for c in CHARTS)
realtime_update('realDisChart1')
check('Clear Display: the four scan traces and both Realtime traces are emptied; the number box stays; Realtime restarts at 0',
      filled and cleared and ui.realDisChart1Num.text() == number and number != ''
      and m.indices['realDisChart1'] == 0 and len(m.buffers['realDisChart1']) == 1,
      f'filled={filled}, cleared={cleared}, number={number!r}')

# ---- the last point's move fails: its trace / pixel is still sent to the display, with the NaN ----
tds_seen, img_seen = [], []
real_tds = ns['moSys'].update_TDS_FDS_chart.__get__(m)
m.update_TDS_FDS_chart = lambda data: (tds_seen.append(list(data['tds_y'])), real_tds(data))
if hasattr(m, 'on_img_update'):
    real_img = ns['moSys'].on_img_update.__get__(m)
    m.on_img_update = lambda data: (img_seen.append(data), real_img(data))
LAST_MODES = [mode for mode in ('THz_Scan',) if mode in ('THz_Scan', '2D_IMG')]
for mode in LAST_MODES:
    reset(mode=mode)
    run()
    clean_tds, clean_img, last_call = len(tds_seen), len(img_seen), len(move_log) - 1
    tds_seen.clear(); img_seen.clear()
    reset(mode=mode)
    FAIL_CALL[0] = last_call  # the move of the last point fails
    data = run()
    FAIL_CALL[0] = None
    if mode == '2D_IMG':
        ok = (len(img_seen) == clean_img > 0 and data is not None and np.isnan(data['lockin1_X']).sum() == 1
              and np.isnan(np.asarray(img_seen[-1]['block']['l1x'], dtype=float)).sum() == 1)
        detail = f'images {len(img_seen)}/{clean_img}'
    else:
        ok = (len(tds_seen) == clean_tds > 0 and data is not None and np.isnan(data['lockin1_X']).sum() == 1
              and np.isnan(np.asarray(tds_seen[-1], dtype=float)).sum() == 1
              and m.curves['fdsChart']['blue'].getData()[1] is None)
        detail = f'traces {len(tds_seen)}/{clean_tds}'
    check(f'{mode}: the last point fails to move: its trace/pixel is still shown, with the NaN (no stale spectrum)', ok, detail)
    if mode == 'THz_Scan':  # the first point fails: nothing read before it, its trace still shown
        tds_seen.clear(); img_seen.clear()
        reset(mode=mode)
        FAIL_CALL[0] = 1
        data = run()
        FAIL_CALL[0] = None
        check(f'{mode}: the first point fails to move: no error, trace updates as in a clean scan, the first one with the NaN',
              len(tds_seen) == clean_tds and data is not None and not errors and np.isnan(data['lockin1_X']).sum() == 1
              and np.isnan(np.asarray(tds_seen[0], dtype=float)).sum() == 1, f'traces {len(tds_seen)}/{clean_tds}, errors={errors[:1]}')
    tds_seen.clear(); img_seen.clear()
del m.update_TDS_FDS_chart
if hasattr(m, 'on_img_update'):
    del m.on_img_update

# ---- 5. peak search: Stage1 position from move_to(), position() not called ----
reset()
calls.clear()
emitted = []


class Signal:
    def __init__(self, name):
        self.name = name

    def emit(self, value):
        emitted.append((self.name, value))


class FakeThread:
    stop_flag = False

    def __getattr__(self, name):
        return Signal(name)


class PeakLockin(Lockin):
    def get_x(self):  # a peak at 10.005 mm, inside the search window around iPos1 = 10 mm
        calls.append((self.name, 'get_x', None))
        return 1.0 - (m.stage1.pos - 10.005) ** 2


m.lockin1 = PeakLockin('lockin1', 0.0)
m.stop_flag = False
peak = m.get_TDS_peak_pos(FakeThread())
stage1_moves = moves('stage1')
shown = [v['stage1_pos'] for name, v in emitted if name == 'position_update']
check('peak search: shown Stage1 positions come from move_to(), position() not called',
      peak.get('status') == 'ok' and len(stage1_moves) > 0 and count('stage1', 'position') == 0
      and shown == [round(t + 0.002, 3) for t in stage1_moves],
      f"status={peak.get('status')}, moves={len(stage1_moves)}, position calls={count('stage1', 'position')}")

m.stop_console_mirror()
ui.close()
shutil.rmtree(TMP, ignore_errors=True)
report(f'RESULT {SRC.name}: {sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
