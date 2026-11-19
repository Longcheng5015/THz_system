"""OPTP v4.4, MO v3.0 and OPTP Imaging v2.1: the THz Emission v1.9 changes ported to these systems,
checked with the real scan worker and fake instruments that count every driver call.

    python OPTP_System/tests/test_v19_port_point_io.py optp|mo|img [path to the GUI .py]

1. Stage2 and the rotaries are moved and read back only when their target changes (OPTP: move + read;
   MO and Imaging keep their 1e-4 tolerance check, so a change costs read + move + read); the first point
   of every scan checks every axis; a failed move or read leaves no cache entry; a replaced device moves.
   MO: the Stage2 peak search voids the cached Stage2 target.
2. Each lock-in is read with one SNAP? 1,2 per point; no OUTP?, no 50 ms gap; a lock-in is read only when
   its 'active' box is ticked; Lock-in 2 alone waits its full wait2.
3. Points not acquired are NaN: a lock-in not used, and (MO, Imaging) a failed move or read. OPTP keeps
   its v3.5 policy: a failed move or read aborts the scan, and the points not reached are NaN.
4. Jog buttons are disabled and Realtime timers stopped during a scan; controls come back exactly once,
   on the GUI thread, after the worker has ended.
5. Exit stops the scan and a stabilization thread started after the exit began, and closes the
   instruments only after both have ended; the window stays disabled; a timeout can cancel the exit.
6. FFT display: no spectrum for a trace with NaN or fewer than 3 points; red is always the previous trace.
7. Clear Display clears the four scan traces and both Realtime traces.

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
SYSTEM = sys.argv[1] if len(sys.argv) > 1 else 'optp'
FILES = {'optp': 'OPTP_System/OPTP_system_iTC_v4.4.py',
         'mo': 'MO_System/MO_system_iTC_v3.0.py',
         'img': 'OPTP_image_System/OPTP_iTC_image_v2.1.py'}
SRC = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / FILES[SYSTEM]
ABORTS = SYSTEM == 'optp'  # OPTP: a failed move or lock-in read ends the scan (v3.5); MO/Imaging skip the point
TOLERANCE_CHECK = SYSTEM in ('mo', 'img')  # these read an axis before deciding to move it
os.chdir(SRC.parent)  # OPTP Imaging loads its .ui relative to the working directory
sys.path.insert(0, str(SRC.parent))
source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'port_point_io_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)

import h5py
import numpy as np
from PySide6.QtCore import QSettings, QThread, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

REAL = sys.__stdout__
TMP = Path(tempfile.mkdtemp(prefix=f'port_point_io_{SYSTEM}_'))
ns['QSettings'] = lambda org, name: QSettings(str(TMP / f'{org}.{name}.ini'), QSettings.IniFormat)


def data_folder(self):
    self.dataSave_path = str(TMP)
    self.ui.dataSavePath.setText(str(TMP))
    return str(TMP)


ns['moSys'].setup_data_folder = data_folder

calls = []   # (device, method, argument) in call order, from every thread
sleeps = []  # every time.sleep() made by the GUI module


class TimeProxy:
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


report(f'GUI under test: {SRC.name} ({SYSTEM})')


class Axis:
    """A Thorlabs-like axis: move_to() returns nothing, position() reads back. fail_on / pos_fail_on list
    1-based move / read calls that raise; slow_move / slow_delay make one move slow."""
    def __init__(self, name, pos, fail_on=(), pos_fail_on=(), slow_move=None, slow_delay=0.0):
        self.name, self.pos = name, pos
        self.fail_on, self.pos_fail_on, self.moves, self.reads = set(fail_on), set(pos_fail_on), 0, 0
        self.slow_move, self.slow_delay = slow_move, slow_delay

    def move_to(self, target, *args):
        self.moves += 1
        calls.append((self.name, 'move_to', target))
        if self.moves == self.slow_move:
            time.sleep(self.slow_delay)
        if self.moves in self.fail_on:
            raise RuntimeError('simulated move failure')
        self.pos = target

    def position(self):
        self.reads += 1
        calls.append((self.name, 'position', None))
        if self.reads in self.pos_fail_on:
            raise RuntimeError('simulated read-back failure')
        return self.pos

    def travel_limits(self):
        return 0, 1000


class PM500(Axis):
    """MO's Stage2: go_and_wait_abs / read_pos in um on axis 'X'."""
    def go_and_wait_abs(self, axis, pos_um, timeout=10.0):
        self.move_to(pos_um / 1000)

    def read_pos(self, axis):
        return self.position() * 1000


def signal_value(offset):
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


move_log = []  # (targets, (ok, positions) or the exception) of every move_active_stages call
original_move = m.move_active_stages


FAIL_CALL = [None]  # index of a move_active_stages call to fail as a failed move (scenario: last point)


def logged_move(targets):
    if FAIL_CALL[0] is not None and len(move_log) == FAIL_CALL[0]:
        print(f"Error moving active stages: simulated failure of the move to {targets}")
        move_log.append((targets, (False, None)))
        return False, None
    try:
        result = original_move(targets)
    except Exception as e:  # OPTP raises on a failed move
        move_log.append((targets, (False, None)))
        raise
    move_log.append((targets, result))
    return result


m.move_active_stages = logged_move
enable_log = []
original_enable = m.set_ControlsEnabledDuringScan


def logged_enable(scanning):
    enable_log.append((scanning, QThread.currentThread() == app.thread()))
    return original_enable(scanning)


m.set_ControlsEnabledDuringScan = logged_enable
ONCE = [(True, True), (False, True)]
JOGS = [f'{axis}Jog{side}' for axis in ('stage1', 'stage2', 'rot1', 'rot2', 'rot3') for side in 'LR']
MODES = {'optp': ('THz_Scan', '1D_THz', 'POL_2D', '2D_THz'),
         'mo': ('1D_POL', 'POL_2D', 'THz_Scan', '1D_THz', '2D_THz'),
         'img': ('THz_Scan', '1D_THz', 'POL_2D', '2D_THz', '2D_IMG')}[SYSTEM]


def reset(mode=None, stage1_NO=4, stage2_NO=2, rot2_NO=2, rot_active=(False, True, False), stage1_rep=1, **fail):
    for name in ('activeiTC', 'ScanT', 'AutoBlock', 'activeFlipMount', 'activePowerMeter', 'pmRecord',
                 'realtimeDisp1', 'realtimeDisp2', 'driftComp'):
        if hasattr(ui, name):
            getattr(ui, name).setChecked(False)
    for name in ('activeStage1', 'activeStage2', 'activeLockin1', 'activeLockin2'):
        getattr(ui, name).setChecked(True)
    ui.scanMode.setCurrentText(mode or MODES[0])
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
    for n in (1, 2, 3):
        getattr(ui, f'activeRot{n}').setChecked(rot_active[n - 1])
        getattr(ui, f'iRot{n}').setValue(n * 10)
        getattr(ui, f'rotary{n}Step').setValue(n)
        getattr(ui, f'rotary{n}StepNO').setValue(rot2_NO)
        kw = {'fail_on': fail.get('rot2_fail_on', ()), 'pos_fail_on': fail.get('rot2_pos_fail_on', ())} if n == 2 else {}
        setattr(m, f'rotary{n}', Axis(f'rotary{n}', n * 10, **kw) if rot_active[n - 1] else None)
    m.stage1 = Axis('stage1', 10)
    m.stage2 = (PM500 if SYSTEM == 'mo' else Axis)('stage2', 50)
    m.lockin1, m.lockin2 = Lockin('lockin1', 0.0), Lockin('lockin2', 1000.0)
    m.mercuryiTC = None
    m.is_custom_save_path = True


run_number = 0
during = {}


def run():
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
    requested = [targets[axis_index] for targets, _ in move_log]
    return [t for i, t in enumerate(requested) if i == 0 or t != requested[i - 1]]


def axis_ok(name, index):
    """Moves only at target changes; reads only for those changes (OPTP 1 per change, MO/Imaging 2)."""
    ch = changes(index)
    reads = count(name, 'position')
    if TOLERANCE_CHECK:  # a change is read, moved only if more than 1e-4 away, and read again
        return set(moves(name)) <= set(ch) and len(moves(name)) <= len(ch) and reads == 2 * len(ch)
    return moves(name) == ch and reads == len(ch)


def axis_detail(name, index):
    return f"{name}: moves={moves(name)}, reads={count(name, 'position')}, changes={changes(index)}"


# ---- 1. every scan mode: Stage2/Rotary2 only at target changes, SNAP?, controls once ----
for mode in MODES:
    reset(mode=mode)
    data = run()
    points = len(move_log) - 1
    acquired = None if data is None else int(np.isfinite(data['lockin1_X']).sum())
    check(f'{mode}: scan ran, every point acquired, no warnings or errors',
          data is not None and not warnings and not errors and acquired == data['lockin1_X'].size and acquired == points,
          f'points={points}, acquired={acquired}, warnings={warnings[:1]}, errors={errors[:1]}')
    check(f'{mode}: Stage2 and Rotary2 moved and read only at target changes',
          axis_ok('stage2', 1) and axis_ok('rotary2', 3), axis_detail('stage2', 1) + '; ' + axis_detail('rotary2', 3))
    check(f'{mode}: one SNAP? 1,2 per point and lock-in, no OUTP?, no 50 ms gap; controls back once on the GUI thread',
          all(count(n, 'snap') == points and count(n, 'get_x') == 0 and count(n, 'get_y') == 0 for n in ('lockin1', 'lockin2'))
          and all(arg == (1, 2) for dev, meth, arg in calls if meth == 'snap')
          and 0.05 not in sleeps and enable_log == ONCE and ui.runButton.isEnabled(),
          f"snaps={count('lockin1', 'snap')}/{points}, sleeps={sorted(set(sleeps))}, enable_log={enable_log}")
    report(f"  {mode}: {points} points, Stage2 {len(moves('stage2'))} moves / {count('stage2', 'position')} reads, "
           f"Rotary2 {len(moves('rotary2'))} moves / {count('rotary2', 'position')} reads")
    if mode == MODES[0]:
        expected = sorted(t[0] + t[1] / 1000 + t[3] / 100 for t, (ok, _p) in move_log[1:] if ok)
        check('stored X/Y equal the snapshot at the planned positions, for both lock-ins',
              data is not None and np.allclose(np.sort(data['lockin1_X']), expected)
              and np.allclose(data['lockin1_Y'], -data['lockin1_X']) and np.allclose(data['lockin2_X'], data['lockin1_X'] + 1000))

# ---- 2. a new scan checks every axis again ----
reset(stage2_NO=1, rot2_NO=1)
for attempt in (1, 2):
    m.stage2.pos, m.rotary2.pos = 50, 20
    data = run()
    reads_per_change = 2 if TOLERANCE_CHECK else 1
    check(f'constant targets, scan {attempt}: Stage2 and Rotary2 checked once at the start, then never',
          data is not None and count('stage2', 'position') == reads_per_change and count('rotary2', 'position') == reads_per_change,
          axis_detail('stage2', 1) + '; ' + axis_detail('rotary2', 3))

# ---- 3. repeat blocks with three coupled rotaries; calibration table ----
reset(rot_active=(True, True, True), stage1_rep=2)
data = run()
check('Stage1 repeat 2, Rotary1-3 coupled: every cached axis only at target changes; all points acquired',
      data is not None and not errors and np.isfinite(data['lockin1_X']).all()
      and all(axis_ok(name, i) for i, name in ((1, 'stage2'), (2, 'rotary1'), (3, 'rotary2'), (4, 'rotary3'))),
      '; '.join(axis_detail(name, i) for i, name in ((1, 'stage2'), (2, 'rotary1'), (3, 'rotary2'), (4, 'rotary3'))))
reset(rot_active=(True, True, False), rot2_NO=3)
ui.pol_cali_mode.setChecked(True)
m.cali_table = {'rot2_cali': [20, 22.5, 25], 'rot1_cali': [11, 13, 15]}
data = run()
check('calibration table: rotaries only at target changes; all points acquired',
      data is not None and not errors and np.isfinite(data['lockin1_X']).all() and axis_ok('rotary1', 2) and axis_ok('rotary2', 3),
      f'errors={errors[:1]}; ' + axis_detail('rotary1', 2) + '; ' + axis_detail('rotary2', 3))

# ---- 4. failures: a move, a read-back, a lock-in read ----
# the first change of Rotary2's angle fails: OPTP moves at the first point too (attempt 2), MO/Imaging find
# Rotary2 already at its start angle and only move at the change (attempt 1)
reset(rot2_fail_on=(1,) if TOLERANCE_CHECK else (2,))
data = run()
if ABORTS:
    check('failed Rotary2 move: the scan ends with an error (OPTP v3.5 policy); points not reached are NaN, none 0',
          errors and 'simulated move failure' in errors[0] and data is not None and np.isnan(data['lockin1_X']).any()
          and not (data['lockin1_X'] == 0).any() and enable_log == ONCE, f'errors={errors[:1]}, enable_log={enable_log}')
else:
    check('failed Rotary2 move: that point is NaN in all four datasets, the next point moves Rotary2 again',
          data is not None and all(np.isnan(data[k]).sum() == 1 for k in data) and not any((data[k] == 0).any() for k in data)
          and moves('rotary2').count(22) == 2, axis_detail('rotary2', 3))
# the read-back after the move to 22 deg fails: OPTP read 2; MO/Imaging read 4 (2 at the start, then pre-check + after)
reset(rot2_pos_fail_on=(4,) if TOLERANCE_CHECK else (2,))
data = run()
if ABORTS:
    check('failed Rotary2 read-back: the scan ends with an error; no zeros stored',
          errors and 'read-back' in errors[0] and data is not None and not (data['lockin1_X'] == 0).any(), f'errors={errors[:1]}')
else:
    check('failed Rotary2 read-back: no cache entry, the next point checks Rotary2 again (2 more reads); the point is NaN',
          data is not None and np.isnan(data['lockin1_X']).sum() == 1 and count('rotary2', 'position') == 6
          and moves('rotary2') == [22], axis_detail('rotary2', 3))
reset()
m.lockin1 = Lockin('lockin1', 0.0, fail_on=(3,))
data = run()
if ABORTS:
    check('Lock-in 1 read error: the scan ends with an error (OPTP v3.5 policy); no zeros stored',
          errors and 'Lock-in 1' in errors[0] and data is not None and not (data['lockin1_X'] == 0).any(), f'errors={errors[:1]}')
else:
    check('Lock-in 1 read error: its X/Y are NaN at that point, Lock-in 2 is stored, the scan goes on',
          data is not None and not errors and np.isnan(data['lockin1_X']).sum() == 1 and np.isfinite(data['lockin2_X']).all())

if not ABORTS:
    # ---- the last point's move fails: its trace / pixel is still sent to the display, with the NaN ----
    tds_seen, img_seen = [], []
    real_tds = ns['moSys'].update_TDS_FDS_chart.__get__(m)
    m.update_TDS_FDS_chart = lambda data: (tds_seen.append(list(data['tds_y'])), real_tds(data))
    if hasattr(m, 'on_img_update'):
        real_img = ns['moSys'].on_img_update.__get__(m)
        m.on_img_update = lambda data: (img_seen.append(data), real_img(data))
    LAST_MODES = [mode for mode in MODES if mode in ('THz_Scan', '2D_IMG')]
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


# ---- 5. lock-ins not used ----
reset()
ui.activeLockin1.setChecked(False)
m.lockin1 = None
ui.wait2.setValue(30)
data = run()
points = len(move_log) - 1
check('only Lock-in 2 used: Lock-in 1 is NaN everywhere (before: 0), Lock-in 2 waits its full 30 ms before each read',
      data is not None and not errors and np.isnan(data['lockin1_X']).all() and np.isfinite(data['lockin2_X']).all()
      and sleeps.count(0.03) == points == count('lockin2', 'snap'), f'sleeps={sorted(set(sleeps))}, errors={errors[:1]}')
reset()
ui.activeLockin2.setChecked(False)  # still connected
data = run()
check("Lock-in 2 connected but its 'active' box unticked: never read, stored as NaN",
      data is not None and count('lockin2', 'snap') == 0 and np.isnan(data['lockin2_X']).all() and np.isfinite(data['lockin1_X']).all())

# ---- 6. Realtime on before the scan; Jog during the scan ----
reset()
REALTIME_READ_S[0] = 0.3  # runScan() must wait for a Realtime read in progress
ui.realtimeDisp1.setChecked(True)
ui.realtimeDisp2.setChecked(True)
calls.clear()
deadline = time.monotonic() + 1.5
while time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.01)
before = count('lockin1', 'get_x') + count('lockin2', 'get_x')
data = run()
check('Realtime on before the scan: switched off and stopped at scan start, no OUTP? during the scan, still off after',
      before > 0 and during['realtime'] == [False, False] and during['timers'] == [False, False]
      and during['readers_running'] == [False, False]
      and all(count_after_first_snap(n, 'get_x') == 0 for n in ('lockin1', 'lockin2'))
      and not ui.realtimeDisp1.isChecked() and not ui.realtimeDisp2.isChecked(), f'before={before}, during={during}')
REALTIME_READ_S[0] = 0.0
check('Jog buttons disabled during the scan and enabled again afterwards',
      during['jog_enabled'] == [False] * 10 and all(getattr(ui, n).isEnabled() for n in JOGS), f"during={during.get('jog_enabled')}")

# ---- 7. a worker that ends with an exception while a slow AutoBlock still runs ----
reset()
in_block = threading.Event()


def slow_block(thread=None):
    in_block.set()
    time.sleep(0.8)


def broken_scan(thread):
    raise RuntimeError('simulated worker exception')


m.auto_block_after_scan = slow_block
m._execute_scan_logic = broken_scan
real_error = ns['moSys'].on_handle_scan_error.__get__(m)
m.on_handle_scan_error = lambda message: (errors.append(message), real_error(message))
folder = TMP / 'broken'
folder.mkdir()
m.dataSave_path = str(folder)
errors.clear(); enable_log.clear()
m.runScan()
deadline = time.monotonic() + 5
while not in_block.is_set() and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.01)
for _ in range(10):
    app.processEvents()
    time.sleep(0.01)
running = m.scan_Thread.isRunning()
locked = (not ui.runButton.isEnabled(), [getattr(ui, n).isEnabled() for n in JOGS])
m.scan_Thread.wait(5000)
for _ in range(5):
    app.processEvents()
check('worker exception: while its AutoBlock still runs Run and Jog stay disabled; controls back once afterwards',
      running and locked == (True, [False] * 10) and errors and 'simulated worker exception' in errors[0]
      and enable_log == ONCE and ui.runButton.isEnabled(), f'running={running}, locked={locked}, enable_log={enable_log}')
del m.auto_block_after_scan, m._execute_scan_logic
m.on_handle_scan_error = lambda message: errors.append(message)

# ---- 7b. a scan plan rejected by the travel check while a slow AutoBlock runs ----
reset()
m.rotary2.travel_limits = lambda: (0, 1)  # every Rotary2 angle is outside its travel
in_block.clear()
m.auto_block_after_scan = slow_block
m.on_handle_scan_error = lambda message: (errors.append(message), real_error(message))
folder = TMP / 'rejected'
folder.mkdir()
m.dataSave_path = str(folder)
errors.clear(); warnings.clear(); enable_log.clear()
m.runScan()
deadline = time.monotonic() + 5
while not (errors or warnings) and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.01)
for _ in range(10):
    app.processEvents()
    time.sleep(0.01)
running = m.scan_Thread.isRunning() if m.scan_Thread is not None else False
locked = (not ui.runButton.isEnabled(), [getattr(ui, n).isEnabled() for n in JOGS])
if m.scan_Thread is not None:
    m.scan_Thread.wait(5000)
for _ in range(5):
    app.processEvents()
if SYSTEM == 'optp':  # OPTP checks the plan in runScan(), before anything is disabled or started
    check('rejected plan (OPTP: before the worker starts): warning shown, controls never disabled',
          warnings and 'travel' in warnings[0] and enable_log == [] and ui.runButton.isEnabled(),
          f'warnings={warnings[:1]}, errors={errors[:1]}, enable_log={enable_log}')
else:  # the worker reports the rejection and then still runs its end-of-scan AutoBlock
    check('rejected plan in the worker: while its AutoBlock still runs Run and Jog stay disabled; controls back once',
          errors and 'travel' in errors[0] and running and locked == (True, [False] * 10)
          and enable_log == ONCE and ui.runButton.isEnabled(),
          f'errors={errors[:1]}, running={running}, locked={locked}, enable_log={enable_log}')
del m.auto_block_after_scan
m.on_handle_scan_error = lambda message: errors.append(message)

# ---- 8. refused before it starts ----
reset()
m.lockin2 = None  # ticked active but not connected
ui.realtimeDisp1.setChecked(True)
data = run()
check('refused before start: no data file, controls never disabled, Realtime left as it was',
      data is None and warnings and enable_log == [] and ui.runButton.isEnabled() and ui.realtimeDisp1.isChecked(),
      f'warnings={warnings[:1]}, enable_log={enable_log}')
ui.realtimeDisp1.setChecked(False)


class FakeStab(QThread):
    def __init__(self):
        super().__init__()
        self.stop_flag = False

    def request_stop(self):
        self.stop_flag = True

    def run(self):
        while not self.stop_flag:
            self.msleep(10)


# ---- 9. Exit during a long move, with a stabilization thread started after the exit began ----
reset()
m.stage1.slow_move, m.stage1.slow_delay = 6, 2.5
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
while m.stage1.moves < 6 and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.01)
probe = {}


def during_exit():
    probe['window'] = ui.isEnabled()
    probe['run'] = ui.runButton.isEnabled()
    QTest.mouseClick(ui.runButton, Qt.LeftButton)
    probe['same_scan'] = m.scan_Thread is first_thread
    stab = FakeStab()
    stab.start()
    m.itc_stab_thread = probe['stab'] = stab


QTimer.singleShot(300, during_exit)
m.exitApp()
with h5py.File(next(folder.glob('*.h5')), 'r') as f:
    stopped = f['lockin1_X'][()].ravel()
check('Exit during a long move: instruments closed only after the scan and a late stabilization thread ended, then quit',
      closed == [(False, False)] and quits == [True] and probe.get('stab') is not None
      and probe['stab'].stop_flag and not probe['stab'].isRunning(), f'closed={closed}, quits={quits}')
check('while exiting the window is disabled and a Run click starts no scan; controls came back once',
      probe.get('window') is False and probe.get('run') is False and probe.get('same_scan') is True
      and enable_log == ONCE and not ui.isEnabled(), f'probe={probe}, enable_log={enable_log}')
check('scan stopped early: points not reached are NaN, none are 0',
      np.isnan(stopped).sum() > 0 and np.isfinite(stopped).sum() > 0 and (stopped == 0).sum() == 0,
      f'acquired={np.isfinite(stopped).sum()}, nan={np.isnan(stopped).sum()}')
ui.setEnabled(True)
m.itc_stab_thread = None

# ---- 10. exit cancelled after the timeout ----
reset()
m.stage1.slow_move, m.stage1.slow_delay = 2, 3.0
folder = TMP / 'exit_cancel'
folder.mkdir()
m.dataSave_path = str(folder)
closed.clear(); quits.clear()
m.runScan()
deadline = time.monotonic() + 5
while m.stage1.moves < 2 and time.monotonic() < deadline:  # exit while the 3 s move runs
    app.processEvents()
    time.sleep(0.01)
answers = iter([QMessageBox.Yes, QMessageBox.No])
QMessageBox.question = staticmethod(lambda *args: next(answers))
saved_defaults = ns['moSys'].stop_workers_for_exit.__defaults__
ns['moSys'].stop_workers_for_exit.__defaults__ = (0.2,)
m.exitApp()
ns['moSys'].stop_workers_for_exit.__defaults__ = saved_defaults
QMessageBox.question = staticmethod(lambda *args: QMessageBox.Yes)
after_cancel = (ui.isEnabled(), m.scan_Thread.isRunning(), ui.runButton.isEnabled(), list(closed), list(quits), m.stop_flag)
m.scan_Thread.wait(15000)
for _ in range(5):
    app.processEvents()
check('timeout, exit cancelled: window usable again with scan controls locked, nothing closed, the scan stops',
      after_cancel == (True, True, False, [], [], True) and not m.scan_Thread.isRunning() and ui.runButton.isEnabled(),
      f'after_cancel={after_cancel}')
check('no running worker: stop_workers_for_exit returns at once', m.stop_workers_for_exit() is True)
del m.closeInstruments
del app.quit

# ---- 11. FFT display ----
empty = lambda y: y is None or len(y) == 0
xs = [10.000, 10.001, 10.002, 10.003]


def fds():
    return tuple(m.curves['fdsChart'][c].getData()[1] for c in ('blue', 'red'))


m.update_TDS_FDS_chart({'tds_x': xs, 'tds_y': [1.0, 2.0, 3.0, 4.0]})
clean = np.array(fds()[0])
m.update_TDS_FDS_chart({'tds_x': xs, 'tds_y': [1.0, np.nan, np.nan, 2.0]})
blue, red = fds()
gap_ok = len(clean) > 0 and empty(blue) and np.allclose(np.asarray(red), clean)
m.update_TDS_FDS_chart({'tds_x': [10.000, 10.001], 'tds_y': [1.0, 2.0]})
blue, red = fds()
two_ok = empty(blue) and empty(red)
m.update_TDS_FDS_chart({'tds_x': [10.000], 'tds_y': [1.0]})
one_ok = all(empty(y) for y in fds())
m.update_TDS_FDS_chart({'tds_x': xs, 'tds_y': [1.0, 2.0, 3.0, 4.0]})
blue, red = fds()
check('FFT display: no spectrum for a gap, two points or one point (no exception); red is always the previous trace',
      gap_ok and two_ok and one_ok and np.allclose(np.asarray(blue), clean) and empty(red),
      f'gap_ok={gap_ok}, two_ok={two_ok}, one_ok={one_ok}')

# ---- 12. Clear Display ----
reset()
for _ in range(5):
    realtime_update('realDisChart1')
    realtime_update('realDisChart2')
m.update_lockin_charts({'l1x': 1.0, 'l1y': 2.0, 'l2x': 3.0, 'l2y': 4.0})
CHARTS = ('lockin1XChart', 'lockin1YChart', 'lockin2XChart', 'lockin2YChart', 'realDisChart1', 'realDisChart2')
filled = all(len(m.buffers[c]) > 0 for c in CHARTS)
number = ui.realDisChart1Num.text()
ui.clearLockinDisplay.click()
cleared = all(len(m.buffers[c]) == 0 and m.indices[c] == -1 and m.curves[c].getData()[1] is None for c in CHARTS)
realtime_update('realDisChart1')
check('Clear Display: four scan traces and both Realtime traces emptied, number box kept, Realtime restarts at 0',
      filled and cleared and ui.realDisChart1Num.text() == number and number != ''
      and m.indices['realDisChart1'] == 0 and len(m.buffers['realDisChart1']) == 1, f'filled={filled}, cleared={cleared}')
set_during = {}
original_enable(True)
set_during['clear'] = ui.clearLockinDisplay.isEnabled()
original_enable(False)
check('Clear Display stays enabled during a scan', set_during['clear'] is True)

# ---- 13. a replaced device always moves; MO: the Stage2 peak search voids the cached Stage2 target ----
m._scan_axis_cache = {}
calls.clear()
a, b = Axis('axisA', 0), Axis('axisB', 0)
for device in (a, a, b, b):
    if TOLERANCE_CHECK:
        m._move_unless_there('rotary2', device, 5, move=device.move_to, read=device.position)
    else:
        m._move_unless_there('rotary2', device, 5)
check('same target on a replaced device object is checked (and moved) once more',
      moves('axisA') == [5] and moves('axisB') == [5])
if SYSTEM == 'mo':
    reset()
    m._scan_axis_cache = {'stage2': (m.stage2, 50, 50.0)}
    m.stop_flag = False
    m.get_TDS_peak_pos()
    check('MO Stage2 peak search: the cached Stage2 target is void afterwards', 'stage2' not in m._scan_axis_cache)

m.stop_console_mirror()
ui.close()
shutil.rmtree(TMP, ignore_errors=True)
report(f'RESULT {SRC.name}: {sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
