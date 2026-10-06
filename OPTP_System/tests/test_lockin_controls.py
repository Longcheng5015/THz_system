"""Latest-system Lock-in UI tests using real SR830 methods over fake VISA sessions.

No hardware, visible windows or registry settings. Run with --native-preview to
also render the Windows layout and save a preview in the temporary directory.
An optional optp/mo/img/thz argument selects the system (default: optp).
OPTP defaults to v3.9; --optp-version=3.7 checks the previous behavior.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

NATIVE = '--native-preview' in sys.argv
if not NATIVE:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
REPO = Path(__file__).resolve().parents[2]
SYSTEM = next((arg for arg in sys.argv[1:] if not arg.startswith('--')), 'optp')
OPTP_VERSION = next((arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--optp-version=')), '3.9')
PHASE_ARROWS = SYSTEM == 'optp' and tuple(map(int, OPTP_VERSION.split('.'))) >= (3, 8)
SETTINGS_READBACK = SYSTEM != 'optp' or PHASE_ARROWS
FILES = {
    'optp': (f'OPTP_System/OPTP_system_iTC_v{OPTP_VERSION}.py', 'OPTP_iTC_main_v3.5.ui'),
    'mo': ('MO_System/MO_system_iTC_v2.7.py', 'MO_system_iTC_v2.5.ui'),
    'img': ('OPTP_image_System/OPTP_iTC_image_v1.8.py', 'OPTP_iTC_image_v1.6.ui'),
    'thz': ('THz_emission_system/THz_emission_system_iTC_v1.6.py', 'THz_emission_system_iTC_v1.4.ui'),
}
SRC = REPO / FILES[SYSTEM][0]
ROOT = SRC.parent
os.chdir(ROOT)  # Imaging loads its UI relative to the working directory.
sys.path.insert(0, str(ROOT))
source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'optp_lockin_controls_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)

import h5py
import numpy as np
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QTabWidget, QStyle, QStyleOptionSpinBox, QAbstractSpinBox

TMP = Path(tempfile.mkdtemp(prefix=f'{SYSTEM}_lockin_controls_'))
ns['QSettings'] = lambda org, name: QSettings(str(TMP / f'{org}.{name}.ini'), QSettings.IniFormat)
app = QApplication.instance() or QApplication([])
warnings = []
QMessageBox.warning = staticmethod(lambda *args: warnings.append(args[2]))
QMessageBox.question = staticmethod(lambda *args: QMessageBox.Yes)
real_sr830 = ns['SR830']


class Session:
    def __init__(self, phase):
        self.phase, self.raw_x, self.offset, self.y = phase, 0.003, 0.0, 0.001
        self.sensitivity, self.time_constant = (14, 10) if phase > 0 else (17, 6)
        self.noise, self.fail_write, self.fail_query = 2e-8, None, None
        self.commands, self.closed = [], False

    def write(self, command):
        self.commands.append(command)
        if command.startswith(self.fail_write or '<never>'):
            raise OSError('simulated write failure')
        if command == 'AOFF 1':
            self.offset = self.raw_x
        elif command.startswith('PHAS '):
            self.phase = round((float(command.split()[1]) + 180) % 360 - 180, 2)
        else:
            raise AssertionError(f'unexpected write: {command}')

    def query(self, command):
        self.commands.append(command)
        if command == self.fail_query:
            raise OSError('simulated read failure')
        return {'*IDN?': 'Stanford Research Systems,SR830,FAKE,1.0', 'PHAS?': str(self.phase),
                'SENS?': str(self.sensitivity), 'OFLT?': str(self.time_constant),
                'OUTP? 1': str(self.raw_x - self.offset + self.noise), 'OUTP? 2': str(self.y)}[command]

    def close(self): self.closed = True


class FakeSR830(real_sr830):
    fail_open = False
    fail_phase = False
    sessions = []

    def open(self):
        self._inst = Session(37.42 if '::8::' in self.resource else -125.75)
        self.sessions.append(self._inst)
        if self.fail_phase:
            self._inst.fail_query = 'PHAS?'
        return 'simulated open failure' if self.fail_open else ''


ns['SR830'] = FakeSR830


def isolated_data_folder(self):
    self.dataSave_path = str(TMP)
    self.ui.dataSavePath.setText(str(TMP))
    return str(TMP)


ns['moSys'].setup_data_folder = isolated_data_folder
m = ns['moSys']()
ui = m.ui
m.qwait_time = lambda ms: None
m.is_custom_save_path = True
m.dataSave_path = str(TMP)
results = []


def check(name, passed):
    results.append(bool(passed))
    print(('PASS ' if passed else 'FAIL ') + name)


def writes(session):
    return [c for c in session.commands if not c.endswith('?') and not c.startswith('OUTP?')]


def phase_text_fits(box):
    edit = box.lineEdit()
    margins = edit.textMargins()
    return edit.fontMetrics().horizontalAdvance(box.text()) + 4 + margins.left() + margins.right() <= edit.width()


check('disconnected phase is unknown; Phase and Auto Zero disabled',
      not ui.phase1.isEnabled() and not ui.phase2.isEnabled()
      and not ui.autoZero1.isEnabled() and not ui.autoZero2.isEnabled()
      and not ui.phase1.cleanText() and not ui.phase2.cleanText())
if SETTINGS_READBACK:
    check('disconnected sensitivity/time constant keep the existing defaults',
          ui.sensitivity1.currentIndex() == ui.sensitivity2.currentIndex() == 23
          and ui.timeConst1.currentIndex() == ui.timeConst2.currentIndex() == 8)
check('both rows have tooltips, decimal phase and degree suffix',
      all(getattr(ui, f'phase{i}').decimals() == 2 and getattr(ui, f'phase{i}').suffix() == '\N{DEGREE SIGN}'
          and getattr(ui, f'phase{i}').toolTip() and getattr(ui, f'autoZero{i}').toolTip() for i in (1, 2)))
def formatted_tooltip(widget):
    tip = widget.toolTip()
    doc = QTextDocument()
    doc.setHtml(tip)
    lines = doc.toPlainText().splitlines()
    return ('<p><b>' in tip and '</b></p><p>' in tip
            and '<br/>' in tip and len(lines) >= 3
            and max(map(len, lines)) <= 60)


check('new tooltips have a bold title, separate body and short explicit lines',
      all(formatted_tooltip(getattr(ui, f'{name}{i}'))
          for name in ('phase', 'autoZero') for i in (1, 2)))
if SYSTEM == 'optp':
    check('beam/repeat settings and active defaults retained',
          ui.beamSettle.value() == 5 and ui.repeatPeak.isChecked()
          and all(getattr(ui, n).isChecked() for n in ('activeLockin1', 'activeLockin2', 'activeStage1', 'activeStage2')))

for name in ('activeStage1', 'activeStage2', 'activeRot1', 'activeRot2', 'activeRot3',
             'activeFlipMount', 'AutoBlock', 'activePowerMeter', 'pmRecord', 'activeiTC', 'ScanT', 'driftComp'):
    if hasattr(ui, name):
        getattr(ui, name).setChecked(False)
ui.activeLockin1.setChecked(True)
ui.activeLockin2.setChecked(True)
ui.Lockin1_res.setCurrentText('GPIB0::8::INSTR')
ui.Lockin2_res.setCurrentText('GPIB0::9::INSTR')
m.connectInstruments()
s1, s2 = m.lockin1._inst, m.lockin2._inst
if SETTINGS_READBACK:
    check('connection reads sensitivity, time constant and phase independently, with no writes',
          ui.sensitivity1.currentIndex() == 14 and ui.timeConst1.currentIndex() == 10
          and ui.sensitivity2.currentIndex() == 17 and ui.timeConst2.currentIndex() == 6
          and all(cmd in s1.commands and cmd in s2.commands for cmd in ('SENS?', 'OFLT?', 'PHAS?'))
          and not writes(s1) and not writes(s2))
    check('connection readback retains the configured acquisition waits and multipliers',
          ui.wait1.value() == ui.wait2.value() == 200
          and ui.wait1multip.value() == ui.wait2multip.value() == 2)
check('connect reads both phases without writing defaults',
      ui.phase1.value() == 37.42 and ui.phase2.value() == -125.75 and not writes(s1) and not writes(s2))
check('connected controls enabled independently', ui.phase1.isEnabled() and ui.phase2.isEnabled()
      and ui.autoZero1.isEnabled() and ui.autoZero2.isEnabled())

ui.phase1.editingFinished.emit()
check('focus-only editingFinished does not write phase', not writes(s1))
ui.phase1.setValue(541.23); ui.phase1.editingFinished.emit()
check('phase 1 writes decimals, reads wrapped result and leaves lock-in 2 untouched',
      writes(s1) == ['PHAS 541.23'] and ui.phase1.value() == -178.77 and not writes(s2))
ui.phase1.editingFinished.emit()
check('readback does not trigger another write', writes(s1) == ['PHAS 541.23'])

ui.phase2.selectAll()
QTest.keyClicks(ui.phase2, '-12.34')
check('typing phase does not issue intermediate commands', not writes(s2))
QTest.keyClick(ui.phase2, Qt.Key_Return)
check('Enter commits typed phase to the correct instrument', writes(s2) == ['PHAS -12.34'] and ui.phase2.value() == -12.34)
check('typing a number without a degree sign automatically displays the degree suffix',
      ui.phase2.hasAcceptableInput() and ui.phase2.text().endswith('\N{DEGREE SIGN}')
      and ui.phase2.cleanText() == '-12.34')

if PHASE_ARROWS:
    ui.setAttribute(Qt.WA_DontShowOnScreen, True)
    ui.resize(1920, 1040); ui.show(); ui.activateWindow(); app.processEvents()
    check('Phase arrows visible, 1-degree steps, decimal input and commit-only typing retained',
          all(box.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.UpDownArrows and box.singleStep() == 1
              and box.decimals() == 2 and not box.keyboardTracking() for box in (ui.phase1, ui.phase2)))

    def click_arrow(box, up):
        option = QStyleOptionSpinBox()
        option.initFrom(box)
        option.buttonSymbols = box.buttonSymbols()
        option.frame = box.hasFrame()
        part = QStyle.SC_SpinBoxUp if up else QStyle.SC_SpinBoxDown
        rect = box.style().subControlRect(QStyle.CC_SpinBox, option, part, box)
        assert not rect.isEmpty()
        QTest.mouseClick(box, Qt.LeftButton, pos=rect.center())
        app.processEvents()

    for index, session, other in ((1, s1, s2), (2, s2, s1)):
        box = getattr(ui, f'phase{index}')
        for up in (True, False):
            box.setFocus(); app.processEvents()
            before, other_before = len(session.commands), list(other.commands)
            expected = round(session.phase + (1 if up else -1), 2)
            click_arrow(box, up)
            check(f'Phase {index} arrow {up=}: immediate single write/readback, other device unchanged',
                  session.commands[before:] == [f'PHAS {expected}', 'PHAS?']
                  and box.value() == expected and other.commands == other_before)
        before = list(session.commands)
        QTest.keyClick(box, Qt.Key_Return)
        getattr(ui, f'phase{3-index}').setFocus(); app.processEvents()
        check(f'Phase {index}: Enter/focus loss after arrow adds no duplicate write', session.commands == before)

    for index, session in ((1, s1), (2, s2)):
        box = getattr(ui, f'phase{index}')
        box.setFocus(); app.processEvents(); box.selectAll()
        before = len(session.commands)
        QTest.keyClicks(box, '23.45')
        check(f'Phase {index}: typed decimals stay pending', len(session.commands) == before)
        getattr(ui, f'phase{3-index}').setFocus(); app.processEvents()
        check(f'Phase {index}: leaving the field commits exactly once',
              session.commands[before:] == ['PHAS 23.45', 'PHAS?'] and box.value() == 23.45)

    # Pending typed text plus an arrow must apply the final stepped value once.
    ui.phase1.setFocus(); app.processEvents(); ui.phase1.selectAll()
    before = len(s1.commands)
    QTest.keyClicks(ui.phase1, '42.25'); click_arrow(ui.phase1, True)
    check('arrow after pending text applies the stepped decimal value once',
          s1.commands[before:] == ['PHAS 43.25', 'PHAS?'] and ui.phase1.value() == 43.25)
    s1.phase = 179.75; m.refresh_lockin_phase('lockin1')
    before = len(s1.commands)
    click_arrow(ui.phase1, True)
    check('arrow step displays wrapped hardware readback without a feedback write',
          s1.commands[before:] == ['PHAS 180.75', 'PHAS?'] and ui.phase1.value() == -179.25)

for index, session, other in ((1, s1, s2), (2, s2, s1)):
    old_other = list(other.commands)
    phase, y = session.phase, session.y
    getattr(ui, f'autoZero{index}').click()
    check(f'Auto Zero {index}: hardware AOFF 1, real residual displayed, phase/Y/other device unchanged',
          session.commands[-2:] == ['AOFF 1', 'OUTP? 1']
          and float(getattr(ui, f'realDisChart{index}Num').text()) == session.noise
          and session.phase == phase and session.y == y and other.commands == old_other)

ui.realtimeDisp1.setChecked(True)
m.chart_updaters['realDisChart1'].update()
check('Realtime uses the same post-offset instrument reading', float(ui.realDisChart1Num.text()) == s1.noise)
ui.realtimeDisp1.setChecked(False)

m.set_ControlsEnabledDuringScan(True)
before = list(s1.commands)
ui.autoZero1.click(); ui.phase1.setValue(7); ui.phase1.editingFinished.emit()
check('scan locks both new controls and guards programmatic setting calls',
      not ui.autoZero1.isEnabled() and not ui.phase1.isEnabled() and s1.commands == before
      and not m.apply_lockin_parameter('lockin1', 'AutoZero'))
m.set_ControlsEnabledDuringScan(False)
m.refresh_lockin_phase('lockin1')
check('connected controls re-enabled after scan', ui.autoZero1.isEnabled() and ui.phase1.isEnabled())

s1.fail_write = 'PHAS '
ui.phase1.setValue(10); ui.phase1.editingFinished.emit()
check('phase write failure warns and does not display an unverified setting', warnings and not ui.phase1.cleanText())
s1.fail_write = None
before = list(s1.commands)
ui.phase1.editingFinished.emit()
check('unknown phase cannot send a default zero on focus changes', s1.commands == before)
m.refresh_lockin_phase('lockin1')
s1.fail_query = 'PHAS?'
ui.phase1.setValue(20); ui.phase1.editingFinished.emit()
check('phase readback failure clears field even if write succeeded', s1.phase == 20 and not ui.phase1.cleanText())
s1.fail_query = None
m.connectInstruments()
check('reconnecting an already connected lock-in refreshes actual phase', ui.phase1.value() == 20)
if SETTINGS_READBACK:
    for query, field in (('SENS?', 'sensitivity1'), ('OFLT?', 'timeConst1')):
        s1.fail_query = query
        before = list(writes(s1))
        m.connect_lockin(1)
        check(f'{query} failure clears only the unknown setting, still reads phase and sends no writes',
              getattr(ui, field).currentIndex() == -1 and ui.phase1.value() == s1.phase
              and writes(s1) == before)
    s1.fail_query = None
    s1.sensitivity, s1.time_constant = 26, 19
    ui.wait1.setValue(731); ui.wait1multip.setValue(2.5)
    before = list(writes(s1))
    m.connect_lockin(1)
    check('repeated connection refreshes changed hardware indices and preserves custom wait settings',
          ui.sensitivity1.currentIndex() == 26 and ui.timeConst1.currentIndex() == 19
          and ui.wait1.value() == 731 and ui.wait1multip.value() == 2.5 and writes(s1) == before)
    s1.sensitivity = 99
    m.connect_lockin(1)
    check('out-of-range instrument response is shown as unknown without changing the instrument',
          ui.sensitivity1.currentIndex() == -1 and writes(s1) == before)
    s1.sensitivity = 14; m.connect_lockin(1)

s1.fail_write = 'AOFF '
ui.autoZero1.click()
check('Auto Zero write failure does not fabricate zero', ui.realDisChart1Num.text() == '--')
s1.fail_write = None; s1.fail_query = 'OUTP? 1'
ui.autoZero1.click()
check('Auto Zero read failure does not fabricate zero', ui.realDisChart1Num.text() == '--')
s1.fail_query = None

ui.activeLockin2.setChecked(False)
m.closeInstruments()
check('closing one lock-in clears its phase; the unticked connected device stays usable',
      m.lockin1 is None and not ui.phase1.isEnabled() and not ui.phase1.cleanText()
      and m.lockin2 is not None and ui.phase2.isEnabled() and not s2.closed)
m.set_ControlsEnabledDuringScan(True); m.set_ControlsEnabledDuringScan(False)
check('scan unlock does not enable disconnected controls', not ui.phase1.isEnabled() and not ui.autoZero1.isEnabled())
FakeSR830.fail_open = True
m.connectInstruments()
check('failed open is closed and leaves no connected placeholder',
      m.lockin1 is None and FakeSR830.sessions[-1].closed and not ui.phase1.isEnabled())
FakeSR830.fail_open = False; FakeSR830.fail_phase = True
m.connectInstruments()
check('phase query failure on connect leaves phase unknown without writing defaults',
      m.lockin1 is not None and not ui.phase1.cleanText() and not writes(m.lockin1._inst))
FakeSR830.fail_phase = False; m.lockin1._inst.fail_query = None
m.connectInstruments()

# Small formal scan after Auto Zero: uses the same real driver's get_x() path.
ui.activeLockin2.setChecked(True)
ui.autoZero1.click(); ui.autoZero2.click()
ui.scanMode.setCurrentText('THz_Scan' if SYSTEM == 'thz' else '1D_THz')
for axis, count in (('stage1', 1), ('stage2', 3)):
    getattr(ui, axis + 'Step1').setValue(1)
    getattr(ui, axis + 'Step1NO').setValue(count)
    getattr(ui, axis + 'Step2NO').setValue(0); getattr(ui, axis + 'Step3NO').setValue(0)
for name in ('scanRepNO1', 'scanRepNO2', 'ScanRepNO_R1', 'ScanRepNO_R2'):
    getattr(ui, name).setValue(1)
ui.wait1.setValue(0); ui.wait2.setValue(0)
m.runScan()
deadline = time.monotonic() + 15
while m.scan_Thread.isRunning() or m._scanning:
    app.processEvents(); time.sleep(0.005)
    if time.monotonic() > deadline: raise RuntimeError('scan timed out')
m.scan_Thread.wait()
with h5py.File(next(TMP.glob('*.h5')), 'r') as data:
    check('formal scan saves both post-offset X channels and unmodified Y',
          np.allclose(data['lockin1_X'][()], 2e-8, atol=1e-12)
          and np.allclose(data['lockin2_X'][()], 2e-8, atol=1e-12)
          and np.allclose(data['lockin1_Y'][()], 0.001))

if NATIVE:
    ui.setAttribute(Qt.WA_DontShowOnScreen, True)
    ui.resize(1920, 1040); ui.show(); app.processEvents()
    # Same loader/styles as the running program, but the baseline has no device connections.
    baseline = ns['uiLoader'].load(str(ROOT / FILES[SYSTEM][1]))
    baseline.setAttribute(Qt.WA_DontShowOnScreen, True)
    baseline.resize(1920, 1040); baseline.show(); app.processEvents()
    for index in (1, 2):
        old = getattr(baseline, f'realDisChart{index}Num')
        display, phase = getattr(ui, f'realDisChart{index}Num'), getattr(ui, f'phase{index}')
        display.setText('-1.2345e-03'); m.show_lockin_phase(f'lockin{index}', -180)
        print('LAYOUT', index, 'old', old.width(), 'new', display.width(), 'ratio', display.width()/old.width(), 'phase', phase.width())
        check(f'native Lock-in {index}: display ~3/5, number and phase fit',
              abs(display.width()/old.width() - 0.6) < 0.06
              and display.fontMetrics().horizontalAdvance(display.text()) + 10 <= display.width()
              and phase_text_fits(phase))
    ui.grab().save(str(TMP / 'native_ui.png'))
    # Capture only the two Lock-in boxes for visual review.
    panel = ui.realDisChart1Num.parentWidget()
    panel.grab().save(str(TMP / 'lockin1_native.png'))
    print('PREVIEW', TMP)
    ui.resize(1661, 973); baseline.resize(1661, 973); app.processEvents()
    for index in (1, 2):
        display, phase = getattr(ui, f'realDisChart{index}Num'), getattr(ui, f'phase{index}')
        print('LAYOUT smaller', index, 'number', display.width(), 'phase', phase.width())
        check(f'native Lock-in {index}: both fields fit at original 1661 px window width',
              display.fontMetrics().horizontalAdvance(display.text()) + 10 <= display.width()
              and phase_text_fits(phase))
    baseline.close()

m.closeInstruments(only_active=False)
ui.close()
print(f'\n{sum(results)}/{len(results)} passed')
print('Temporary results:', TMP)
sys.exit(0 if all(results) else 1)
