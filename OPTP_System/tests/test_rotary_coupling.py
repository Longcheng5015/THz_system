"""Latest-system coupled scans with unchecked axes; real scan workers, fake instruments.

Run with optp/mo/img/thz. No instrument connections, visible UI or registry writes.
"""
import itertools
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
SYSTEM = sys.argv[1] if len(sys.argv) > 1 else 'optp'
ROOT = Path(__file__).resolve().parents[2]
FILES = {
    'optp': 'OPTP_System/OPTP_system_iTC_v3.9.py',
    'mo': 'MO_System/MO_system_iTC_v2.7.py',
    'img': 'OPTP_image_System/OPTP_iTC_image_v1.8.py',
    'thz': 'THz_emission_system/THz_emission_system_iTC_v1.6.py',
}
src = ROOT / FILES[SYSTEM]
os.chdir(src.parent)
sys.path.insert(0, str(src.parent))
source = src.read_text(encoding='utf-8-sig')
ns = {'__file__': str(src), '__name__': 'rotary_coupling_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(src), 'exec'), ns)

import h5py
import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

TMP = Path(tempfile.mkdtemp(prefix=f'rotary_coupling_{SYSTEM}_'))
ns['QSettings'] = lambda org, name: QSettings(str(TMP / f'{org}.{name}.ini'), QSettings.IniFormat)


def data_folder(self):
    self.dataSave_path = str(TMP)
    self.ui.dataSavePath.setText(str(TMP))
    return str(TMP)


ns['moSys'].setup_data_folder = data_folder
app = QApplication.instance() or QApplication([])
m = ns['moSys']()
ui = m.ui
warnings, errors, reads, results = [], [], [], []
QMessageBox.warning = staticmethod(lambda *args: warnings.append(args[2]))
QMessageBox.question = staticmethod(lambda *args: QMessageBox.Yes)
m.on_handle_scan_error = lambda message: errors.append(message)


def check(label, condition):
    results.append(bool(condition))
    print(('PASS ' if condition else 'FAIL ') + label)


class Stage:
    def __init__(self, position):
        self.pos, self.moves = position, []

    def move_to(self, position):
        self.pos = position
        self.moves.append(position)

    def position(self):
        return self.pos

    def travel_limits(self):
        return 0, 1000

    def read_pos(self, axis):
        return self.pos * 1000

    def go_and_wait_abs(self, axis, position, timeout):
        self.move_to(position / 1000)


class Lockin:
    def get_x(self):
        reads.append((m.rotary1.pos, m.rotary2.pos, m.rotary3.pos))
        return float(m.rotary1.pos + m.rotary2.pos / 100)

    def get_y(self):
        return 0.0


def reset(active=(True, True, False), counts=(3, 3, 1), coupled=True, mode=None):
    for name in ('activeiTC', 'ScanT', 'AutoBlock', 'activeFlipMount', 'activePowerMeter', 'pmRecord',
                 'activeLockin2', 'realtimeDisp1', 'realtimeDisp2'):
        getattr(ui, name).setChecked(False)
    if hasattr(ui, 'driftComp'):
        ui.driftComp.setChecked(False)
    for name in ('activeStage1', 'activeStage2', 'activeLockin1'):
        getattr(ui, name).setChecked(True)
    ui.scanMode.setCurrentText(mode or ('THz_pol' if SYSTEM == 'thz' else 'POL_2D'))
    ui.Rot_stages_couple.setChecked(coupled)
    ui.pol_cali_mode.setChecked(False)
    m.cali_table = None
    ui.wait1.setValue(0)
    ui.wait2.setValue(0)
    for name in ('scanRepNO1', 'scanRepNO2', 'ScanRepNO_R1', 'ScanRepNO_R2'):
        getattr(ui, name).setValue(1)
    for n, count in ((1, 1), (2, 2)):
        getattr(ui, f'iPos{n}').setValue(100)
        getattr(ui, f'stage{n}Step1').setValue(1)
        getattr(ui, f'stage{n}Step1NO').setValue(count)
        getattr(ui, f'stage{n}Step2NO').setValue(0)
        getattr(ui, f'stage{n}Step3NO').setValue(0)
        setattr(m, f'stage{n}', Stage(100))
    for n in (1, 2, 3):
        getattr(ui, f'activeRot{n}').setChecked(active[n - 1])
        getattr(ui, f'iRot{n}').setValue(n * 10)
        getattr(ui, f'rotary{n}Step').setValue(n)
        getattr(ui, f'rotary{n}StepNO').setValue(counts[n - 1])
        setattr(m, f'rotary{n}', Stage(n * 10))
    m.lockin1, m.lockin2 = Lockin(), None
    m.mercuryiTC = None
    m.is_custom_save_path = True


run_number = 0


def run():
    global run_number
    run_number += 1
    folder = TMP / str(run_number)
    folder.mkdir()
    m.dataSave_path = str(folder)
    reads.clear(); warnings.clear(); errors.clear()
    previous = m.scan_Thread
    m.runScan()
    if m.scan_Thread is not previous:
        deadline = time.monotonic() + 20
        while m.scan_Thread.isRunning():
            app.processEvents()
            if time.monotonic() > deadline:
                raise RuntimeError('scan worker timed out')
            time.sleep(0.005)
        m.scan_Thread.wait()
        for _ in range(5):
            app.processEvents()
    files = list(folder.glob('*.h5'))
    if files:
        with h5py.File(files[0], 'r') as f:
            return f['lockin1_X'][()] if 'lockin1_X' in f else None
    return None


for count3 in (1, 7):
    reset(counts=(3, 3, count3))
    data = run()
    expected = {(10, 20, 30), (11, 22, 30), (12, 24, 30)}
    check(f'Rot3 unchecked, NO={count3}: paired Rot1/Rot2 and six acquired points',
          data is not None and data.shape[-2] == 3 and data.size == 6
          and np.isfinite(data).all() and len(reads) == 6 and set(reads) == expected)
    check(f'Rot3 unchecked, NO={count3}: no motion commands or scan errors',
          not m.rotary3.moves and not warnings and not errors)

reset(active=(True, True, True), counts=(3, 3, 3))
data = run()
check('three checked axes use matched states', data is not None and data.size == 6
      and set(reads) == {(10, 20, 30), (11, 22, 33), (12, 24, 36)} and bool(m.rotary3.moves))

for active, counts in (((True, True, True), (3, 3, 1)), ((True, True, False), (3, 2, 7))):
    reset(active=active, counts=counts)
    run()
    check(f'checked-axis count mismatch rejected {active}/{counts}', not reads
          and any('same number of states' in msg for msg in warnings + errors))

reset(active=(False, True, False), counts=(2, 3, 7))
data = run()
check('only Rot2 checked: other counts ignored and axes unmoved', data is not None and data.size == 6
      and set(reads) == {(10, 20, 30), (10, 22, 30), (10, 24, 30)}
      and not m.rotary1.moves and not m.rotary3.moves)

reset(active=(False, False, False), counts=(2, 3, 7))
data = run()
check('no rotary checked: one stationary polarization state', data is not None and data.size == 2
      and set(reads) == {(10, 20, 30)} and not any(getattr(m, f'rotary{n}').moves for n in (1, 2, 3)))

reset(coupled=False, mode='THz_Scan')
data = run()
check('Independent retains its Cartesian-product scan', data is not None and data.size == 18
      and set(reads) == {(a, b, 30) for a in (10, 11, 12) for b in (20, 22, 24)})

reset(counts=(1, 3, 7))
ui.pol_cali_mode.setChecked(True)
m.cali_table = {'rot2_cali': [20, 22, 24], 'rot1_cali': [11, 13, 15]}
data = run()
check('calibration with unchecked Rot3 uses Rot2 and needs no Rot3 column',
      data is not None and data.size == 6 and set(reads) == {(11, 20, 30), (13, 22, 30), (15, 24, 30)}
      and not m.rotary3.moves)

# The optional planner argument preserves older callers and covers every axis mask.
planner = ns['ScanPlanner']()
args = dict(iRot1=10, iRot2=20, iRot3=30, rotary1_pos_sequence=[10, 11, 12],
            rotary2_pos_sequence=[20, 22, 24], rotary3_pos_sequence=[30],
            rotary1_NO=3, rotary2_NO=3, rotary3_NO=1, polarization_policy='coupled')
check('older caller without active flags retains three-axis validation',
      'Rotary1, Rotary2 and Rotary3' in planner.build_pol_states(**args)['error_msg'])
for flags in itertools.product((False, True), repeat=3):
    three = dict(args, rotary3_pos_sequence=[30, 33, 36], rotary3_NO=3)
    state = planner.build_pol_states(**three, active_rotaries=flags)
    expected_count = 3 if any(flags) else 1
    check(f'planner mask {flags}', state['error_msg'] is None and state['N_pol'] == expected_count
          and all(len(state[f'pol_rot{n}_list']) == expected_count for n in (1, 2, 3))
          and all(state[f'pol_rot{n}_list'] == [n * 10] * expected_count
                  for n in (1, 2, 3) if not flags[n - 1]))

print(f'RESULT {SYSTEM}: {sum(results)}/{len(results)} passed; {TMP}')
sys.exit(0 if all(results) else 1)
