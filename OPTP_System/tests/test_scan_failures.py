"""Exercise v3.5 failure handling through runScan -> ScanThread with fake instruments.

No hardware or visible windows. Data and QSettings are confined to a temporary directory.
Run: python OPTP_System/tests/test_scan_failures.py [version, default 3.5]
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
VERSION = sys.argv[1] if len(sys.argv) > 1 else '3.5'
SRC = ROOT / f'OPTP_system_iTC_v{VERSION}.py'
source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'optp_failure_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)

import h5py
import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

TMP = tempfile.TemporaryDirectory(prefix='optp_scan_failures_')
ns['QSettings'] = lambda org, app: QSettings(str(Path(TMP.name) / f'{org}.{app}.ini'), QSettings.IniFormat)
app = QApplication.instance() or QApplication([])
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
warnings = []
QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(a[2]))
m = ns['moSys']()
ui = m.ui
results = []
run_count = 0
signals = []
original_finished, original_error = m.on_scan_finished, m.on_handle_scan_error


def on_finished():
    signals.append(('finished', bool(m.h5_file), ''))
    original_finished()


def on_error(message):
    signals.append(('error', bool(m.h5_file), message))
    original_error(message)


m.on_scan_finished, m.on_handle_scan_error = on_finished, on_error


def check(label, condition):
    results.append(bool(condition))
    print(('PASS ' if condition else 'FAIL ') + label)


class Stage:
    def __init__(self, fail_at=None, offset=0):
        self.pos, self.calls, self.fail_at, self.offset = 10.0, 0, fail_at, offset

    def move_to(self, p):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError('simulated motor timeout')
        self.pos = p

    def position(self): return self.pos + self.offset
    def travel_limits(self): return 0.0, 300.0


class Lockin:
    def __init__(self, fail_on=None, fail_point=2):
        self.fail_on, self.fail_point, self.reads = fail_on, fail_point, []

    def read(self, channel):
        self.reads.append(channel)
        if channel == self.fail_on and self.reads.count(channel) == self.fail_point:
            raise RuntimeError('simulated lock-in timeout')
        return 1.0 if channel == 'x' else 0.5

    def get_x(self): return self.read('x')
    def get_y(self): return self.read('y')


class Mount:
    def __init__(self): self.p, self.fail_block, self.moves = 2, False, []
    def position(self): return self.p
    def move_to(self, p):
        self.moves.append(p)
        if self.fail_block and p == 2:
            raise RuntimeError('simulated block failure')
        self.p = p


class ITC:
    def __init__(self):
        self.io_lock = threading.RLock()
        self.T, self.follow, self.fail_read = 10.0, True, False
        self.targets = []

    def set_temp_point(self, uid, target):
        self.targets.append(target)
        if self.follow: self.T = target
        return True

    def read_temperature(self, uid):
        if self.fail_read: raise RuntimeError('simulated temperature read error')
        return self.T

    def __getattr__(self, name): return lambda *a, **k: True


def reset(temperature=False, drift=False):
    for name in ('activeRot1', 'activeRot2', 'activeRot3', 'activePowerMeter', 'pmRecord', 'realtimeDisp1', 'realtimeDisp2'):
        getattr(ui, name).setChecked(False)
    for name in ('activeStage1', 'activeStage2', 'activeLockin1', 'activeLockin2', 'activeFlipMount', 'AutoBlock'):
        getattr(ui, name).setChecked(True)
    ui.activeiTC.setChecked(temperature)
    ui.ScanT.setChecked(temperature)
    ui.driftComp.setChecked(drift)
    ui.Rot_stages_couple.setChecked(False); ui.pol_cali_mode.setChecked(False)
    m.cali_table = None
    for axis in (1, 2, 3):
        getattr(ui, f'iRot{axis}').setValue(0)
        getattr(ui, f'rotary{axis}Step').setValue(5)
        getattr(ui, f'rotary{axis}StepNO').setValue(1)
    ui.scanMode.setCurrentText('1D_THz')
    ui.iPos1.setValue(10); ui.iPos2.setValue(10); ui.TDS_Ppos.setValue(10)
    for axis, points in (('stage1', 1), ('stage2', 3)):
        getattr(ui, axis + 'Step1').setValue(1)
        getattr(ui, axis + 'Step1NO').setValue(points)
        getattr(ui, axis + 'Step2NO').setValue(0)
        getattr(ui, axis + 'Step3NO').setValue(0)
    for name in ('scanRepNO1', 'scanRepNO2', 'ScanRepNO_R1', 'ScanRepNO_R2', 'T_stab_cnt', 'waitiTC', 'R1_pts', 'R2_pts'):
        getattr(ui, name).setValue(1)
    for name in ('wait1', 'wait2', 'WaitSamStable', 'beamSettle'):
        getattr(ui, name).setValue(0)
    ui.fmPassCh.setCurrentIndex(0)
    m.stage1, m.stage2 = Stage(), Stage()
    m.lockin1, m.lockin2 = Lockin(), Lockin()
    m.flipmount, m.mercuryiTC = Mount(), ITC()
    m.uid_TEMP, m.uid_HTR = 'T', 'H'
    m.tp_manager.temp_sequence = [10]
    m.h5_file = None
    m.is_custom_save_path = True


def run():
    global run_count
    run_count += 1
    folder = Path(TMP.name) / str(run_count)
    folder.mkdir()
    m.dataSave_path = str(folder)
    signals.clear()
    m.runScan()
    worker = m.scan_Thread
    deadline = time.monotonic() + 15
    while worker.isRunning() or not signals:
        app.processEvents()
        if time.monotonic() > deadline: raise RuntimeError('test scan timed out')
        time.sleep(0.005)
    worker.wait()
    app.processEvents()
    assert len(signals) == 1 and signals[0][1] is False, signals
    paths = list(folder.glob('*.h5'))
    arrays = {}
    if paths:
        with h5py.File(paths[0], 'r') as data:
            arrays = {name: data[name][()].reshape(-1) for name in ('lockin1_X', 'lockin2_X') if name in data}
    log = next(folder.glob('ScanLog_*.txt')).read_text(encoding='utf-8')
    return arrays, paths, log


reset(); m.stage1 = Stage(fail_at=1)
data, paths, log = run()
check('initial move error: no readings, file closed, beam blocked', not m.lockin1.reads and np.isnan(data['lockin1_X']).all()
      and m.flipmount.p == 2 and 'Scan error' in log)

reset(); m.stage2 = Stage(fail_at=3)
data, paths, log = run()
check('point move error: earlier point preserved, remaining points NaN', data['lockin1_X'][0] == 1
      and np.isnan(data['lockin1_X'][1:]).all() and m.lockin1.reads == ['x', 'y'])

reset(); m.stage1 = Stage(offset=0.0002); m.stage2 = Stage(offset=-0.0002)
data, paths, log = run()
check('tiny position offsets do not abort', np.all(data['lockin1_X'] == 1) and 'Scan finished' in log)

for device in ('lockin1', 'lockin2'):
    for channel in ('x', 'y'):
        reset(); setattr(m, device, Lockin(fail_on=channel))
        data, paths, log = run()
        check(f'{device} {channel} exception: no fabricated zero, previous data preserved',
              data['lockin1_X'][0] == 1 and np.isnan(data['lockin1_X'][1:]).all()
              and 'Scan error' in log and m.flipmount.p == 2)

for connected in (False, True):
    reset(); ui.activeLockin1.setChecked(False)
    inactive = Lockin(fail_on='x', fail_point=1)
    m.lockin1 = inactive if connected else None
    ui.wait2.setValue(200)
    sleeps = []
    class FastTime:
        def sleep(self, seconds): sleeps.append(seconds)
        def __getattr__(self, name): return getattr(time, name)
    real_time, ns['time'] = ns['time'], FastTime()
    try: data, paths, log = run()
    finally: ns['time'] = real_time
    check(f'Lock-in 2 alone (Lock-in 1 connected={connected}): full wait, inactive device unread',
          sleeps == [0.2, 0.05] * 3 and not inactive.reads and np.all(data['lockin2_X'] == 1))

reset(); ui.activeLockin2.setChecked(False)
data, paths, log = run()
check('unchecked connected Lock-in 2 is not read', not m.lockin2.reads and np.all(data['lockin1_X'] == 1))

reset(); ui.realtimeDisp1.setChecked(True); ui.realtimeDisp2.setChecked(True)
data, paths, log = run()
check('scan releases both Realtime buttons and stops timers; they stay off afterwards',
      not ui.realtimeDisp1.isChecked() and not ui.realtimeDisp2.isChecked()
      and not m.chart_updaters['realDisChart1'].timer.isActive()
      and not m.chart_updaters['realDisChart2'].timer.isActive()
      and all(getattr(ui, name).isChecked() for name in ('activeLockin1', 'activeLockin2', 'activeStage1', 'activeStage2')))

reset(temperature=True); m.uid_TEMP = None
data, paths, log = run()
check('temperature start failure: abort before pass/search/file', not paths and not m.lockin1.reads
      and m.flipmount.p == 2 and 'stabilization could not start' in log)

reset(temperature=True); m.mercuryiTC.fail_read = True
data, paths, log = run()
check('temperature stabilization error: abort before measurement', not paths and 'Scan aborted' in log)

reset(temperature=True, drift=True); m.stage1 = Stage(fail_at=2)
data, paths, log = run()
check('peak-search move exception aborts before data file', not paths and 'failed during peak search' in log)

reset(temperature=True, drift=True); m.lockin1 = Lockin(fail_on='x', fail_point=1)
data, paths, log = run()
check('peak-search read exception aborts before data file', not paths and 'read failed during peak search' in log)

reset(temperature=True); m.flipmount.fail_block = True
data, paths, log = run()
check('block failure still allows temperature scan as requested', np.all(data['lockin1_X'] == 1) and 'Scan finished' in log)

reset(temperature=True)
observed = []
real_soak = m.wait_sample_stable
def inspect_soak(thread=None):
    observed.append(not m.itc_stab_thread.isRunning() and m.itc_stab_thread.stab_success)
    return real_soak(thread)
m.wait_sample_stable = inspect_soak
try: run()
finally: m.wait_sample_stable = real_soak
check('temperature stabilization thread exits before sample soak', observed == [True])

reset(); ui.activeiTC.setChecked(True); m.mercuryiTC.follow = False
m.iTC_goto_targetT(20, update_ui=False)
manual_worker = m.itc_stab_thread
data, paths, log = run()
check('ScanT off: scan completes while manual Goto T is still stabilizing',
      np.all(data['lockin1_X'] == 1) and manual_worker.isRunning() and not manual_worker.stab_success)
manual_worker.request_stop(); manual_worker.wait()

reset()
storage = ns['ScanStorageCore']
real_write = storage.write_lockin_point
write_count = [0]
def failing_write(*args):
    write_count[0] += 1
    if write_count[0] == 2: raise OSError('simulated storage failure')
    return real_write(*args)
storage.write_lockin_point = staticmethod(failing_write)
try: data, paths, log = run()
finally: storage.write_lockin_point = staticmethod(real_write)
check('unexpected write exception closes file and preserves preceding data', data['lockin1_X'][0] == 1
      and np.isnan(data['lockin1_X'][1:]).all() and 'simulated storage failure' in log)

def rejected_before_start(label, error_text):
    global run_count
    run_count += 1
    folder = Path(TMP.name) / str(run_count)
    folder.mkdir()
    m.dataSave_path = str(folder)
    warnings.clear(); signals.clear()
    before = m.scan_Thread
    active = [getattr(ui, name).isChecked() for name in ('activeLockin1', 'activeLockin2', 'activeStage1', 'activeStage2')]
    ui.realtimeDisp1.setChecked(True)
    m.runScan()
    same_worker = m.scan_Thread is before
    if not same_worker:
        m.scan_Thread.request_stop()
        deadline = time.monotonic() + 10
        while m.scan_Thread.isRunning() and time.monotonic() < deadline:
            app.processEvents(); time.sleep(0.005)
        assert not m.scan_Thread.isRunning(), 'unexpected worker did not stop'
    check(label, same_worker and len(warnings) == 1 and error_text in warnings[0]
          and not signals and not list(folder.iterdir())
          and not m.stage1.calls and not m.stage2.calls and not m.lockin1.reads and not m.lockin2.reads
          and not m.mercuryiTC.targets and not m.flipmount.moves and ui.realtimeDisp1.isChecked()
          and active == [getattr(ui, name).isChecked() for name in ('activeLockin1', 'activeLockin2', 'activeStage1', 'activeStage2')])
    ui.realtimeDisp1.setChecked(False)


reset(temperature=True, drift=True); ui.scanRepNO1.setValue(2); ui.scanRepNO2.setValue(2)
ui.WaitSamStable.setValue(10); ui.beamSettle.setValue(5)
rejected_before_start('stage repeat conflict rejected before temperature/beam/moves/files', 'cannot both be greater than 1')

reset(); ui.ScanRepNO_R1.setValue(2); ui.ScanRepNO_R2.setValue(2)
rejected_before_start('rotary repeat conflict rejected before worker starts', 'cannot both be greater than 1')

reset(temperature=True); ui.Rot_stages_couple.setChecked(True); ui.rotary2StepNO.setValue(2)
for axis in (1, 2, 3):
    getattr(ui, f'activeRot{axis}').setChecked(True); setattr(m, f'rotary{axis}', Stage())
rejected_before_start('coupled point-count mismatch rejected before temperature wait', 'same number of states')

reset(temperature=True, drift=True); m.stage2.travel_limits = lambda: (0.0, 10.001)
rejected_before_start('linear scan endpoint outside travel rejected before search/waits', 'Stage2:')

reset(); ui.activeRot1.setChecked(True); m.rotary1 = Stage(); ui.iRot1.setValue(20)
m.rotary1.travel_limits = lambda: (0.0, 20.0)
ui.rotary1StepNO.setValue(2)
rejected_before_start('rotary scan endpoint outside travel rejected before worker starts', 'Rotary1:')

reset(); ui.activeRot1.setChecked(True); m.rotary1 = Stage(); ui.pol_cali_mode.setChecked(True)
m.cali_table = {'rot2_cali': [0, 5], 'rot1_cali': [301, 302], 'rot3_cali': [0, 5]}
rejected_before_start('calibrated rotary targets are validated even with Independent selected', 'Rotary1:')

reset(); ui.activeRot1.setChecked(True); m.rotary1 = Stage(); ui.pol_cali_mode.setChecked(True)
ui.iRot1.setValue(21); m.rotary1.travel_limits = lambda: (0.0, 20.0)
m.cali_table = {'rot2_cali': [0, 5], 'rot1_cali': [10, 20], 'rot3_cali': [0, 5]}
rejected_before_start('initial rotary configuration is checked as well as calibrated targets', 'Rotary1:')

class WrappingStage(Stage):
    def travel_limits(self): return 0.0, 360.0
    def resolve_target(self, value): return value % 360.0
    def move_to(self, value): super().move_to(self.resolve_target(value))

reset(); ui.activeRot1.setChecked(True); m.rotary1 = WrappingStage()
ui.iRot1.setValue(90); ui.rotary1Step.setValue(90); ui.rotary1StepNO.setValue(4)
data, paths, log = run()
check('valid independent rotary plan still accepts wrapped angles', np.all(data['lockin1_X'] == 1)
      and data['lockin1_X'].size == 12 and m.rotary1.pos == 0)

reset(); ui.Rot_stages_couple.setChecked(True)
for axis in (1, 2, 3):
    getattr(ui, f'activeRot{axis}').setChecked(True); setattr(m, f'rotary{axis}', Stage())
for axis in (1, 2, 3): getattr(ui, f'rotary{axis}StepNO').setValue(2)
data, paths, log = run()
check('valid coupled plan still acquires all states', data['lockin1_X'].size == 6 and np.all(data['lockin1_X'] == 1))

reset(); ui.activeStage2.setChecked(False); m.stage2.travel_limits = lambda: (0.0, 10.001)
data, paths, log = run()
check('inactive axis travel remains ignored', np.all(data['lockin1_X'] == 1) and not m.stage2.calls)

reset(temperature=True, drift=True)
real_compensate = m.compensate_temperature_drift
m.compensate_temperature_drift = lambda *args: (10.0, 301.0, 10.0, False)
try: data, paths, log = run()
finally: m.compensate_temperature_drift = real_compensate
check('initial drift correction outside travel aborts before file creation/acquisition',
      not paths and not m.lockin1.reads and 'planned positions do not fit' in log
      and signals[0][0] == 'error' and m.flipmount.p == 2)

m.ui.close()
TMP.cleanup()
print(f'\n{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
