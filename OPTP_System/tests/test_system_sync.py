"""Headless check of the OPTP v3.0/v3.1 sync in MO, OPTP image and THz emission: flip mount / AutoBlock,
Inst. Config. panel and ScanLog.

    python OPTP_System/tests/test_system_sync.py mo      (or img / thz)

No hardware, no window: instrument classes are replaced by stand-ins, QSettings goes to a temp ini
file instead of the registry, and data / log files go to a temp folder. Exit code 0 = all pass.
Update FILES when a system gets a new version.
"""
import os, sys, tempfile, threading, time, glob
os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FILES = {'mo': 'MO_System/MO_system_iTC_v2.5.py',
         'img': 'OPTP_image_System/OPTP_iTC_image_v1.6.py',
         'thz': 'THz_emission_system/THz_emission_system_iTC_v1.4.py'}
SYSTEM = sys.argv[1]
SRC = os.path.join(ROOT, FILES[SYSTEM])
SYS_DIR = os.path.dirname(SRC)
os.chdir(SYS_DIR)
sys.path.insert(0, SYS_DIR)

# expected Inst. Config. defaults and how each instrument class is called, per system
EXPECT = {
    'mo':  {'title': 'Magneto-Optic Measurement System', 'org': 'MO_System',
            'defaults': {'Lockin1_res': 'GPIB0::3::INSTR', 'Lockin2_res': 'GPIB0::6::INSTR', 'Stage1_res': '73877174',
                         'Stage2_res': 'GPIB0::4::INSTR', 'Rot1_res': '27256338', 'Rot2_res': '27004364',
                         'Rot3_res': '27255894', 'FM_res': '37872830', 'iTC_res': 'ASRL3::INSTR'},
            'mode': 'THz_Scan'},
    'img': {'title': 'OPTP Imaging System', 'org': 'OPTP_image_System',
            'defaults': {'Lockin1_res': 'GPIB0::2::INSTR', 'Lockin2_res': 'GPIB0::3::INSTR', 'Stage1_res': '73844983',
                         'Stage2_res': '73844983', 'Rot1_res': '27004364', 'Rot2_res': '27255894',
                         'Rot3_res': '27255894', 'FM_res': '37872830', 'iTC_res': 'ASRL5::INSTR'},
            'mode': 'THz_Scan'},
    'thz': {'title': 'THz Emission Measurement System', 'org': 'THz_emission_system',
            'defaults': {'Lockin1_res': 'GPIB0::3::INSTR', 'Lockin2_res': 'GPIB0::6::INSTR', 'Stage1_res': '0119001337',
                         'Stage2_res': '73844983', 'Rot1_res': '27004364', 'Rot2_res': '27005114',
                         'Rot3_res': '27255894', 'FM_res': '37872830', 'iTC_res': 'ASRL11::INSTR'},
            'mode': 'THz_Scan'},
}[SYSTEM]

from PySide6.QtCore import QSettings
TMP = tempfile.mkdtemp()

# The THz system imports the PI driver, which needs pipython. On a PC without it, register a placeholder so
# the module imports; the PI stage itself is replaced by a stand-in below, so nothing of pipython is used.
try:
    import pipython  # noqa: F401
except ImportError:
    import types
    _pi = types.ModuleType('pipython'); _pi.GCSDevice = object; _pi.GCSError = Exception
    _pit = types.ModuleType('pipython.pitools'); _pit.waitontarget = _pit.waitonreferencing = lambda *a, **k: None
    sys.modules['pipython'] = _pi; sys.modules['pipython.pitools'] = _pit
    print("note: pipython not installed - placeholder module used (PI stage is a stand-in in this test)")

src = open(SRC, encoding="utf-8").read()
src = src[: src.rindex("app = QApplication()")]  # drop the app start-up at the bottom
ns = {"__file__": SRC, "__name__": "system_under_test"}
exec(compile(src, SRC, "exec"), ns)


def ini_settings(org, app):
    """QSettings(org, app) would write the Windows registry; keep the test inside a temp ini file."""
    return QSettings(os.path.join(TMP, f"{org}.{app}.ini"), QSettings.IniFormat)


ns['QSettings'] = ini_settings  # looked up at call time, so the system's code uses the ini file

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

results = []
def check(name, cond):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)


# ---------------------------------------------------------------- stand-in instruments
CALLS = []

class Anything:
    """Accepts any method call; records constructor args."""
    def __init__(self, *a, **k):
        CALLS.append((type(self).__name__, a, k)); self.pos = 0.0
    def __getattr__(self, name):
        return lambda *a, **k: 0.0
    def connect(self): return self
    def open(self): return None
    def position(self): return self.pos
    def move_to(self, p, *a, **k): self.pos = p
    def travel_limits(self): return (-1000.0, 1000.0)
    def close(self): pass

class FakeSR830(Anything):
    def get_x(self): return 1.0
    def get_y(self): return 0.5
    def open(self): return None
    def get_id(self): return "SR830"

class FakeLinear(Anything): pass
class FakeRotary(Anything): pass
class FakePM500(Anything): pass
class FakePI(Anything): pass

class FakeMount:
    def __init__(self, serial=None, *a, **k):
        CALLS.append(('FakeMount', (serial,), k)); self.p = 1; self.moves = []
    def move_to(self, p): self.p = p; self.moves.append(p)
    def position(self): return self.p
    def close(self): pass

class FakeITC:
    def __init__(self, resource=None, fail=False):
        CALLS.append(('FakeITC', (resource,), {}))
        self.io_lock = threading.RLock(); self.fail = fail; self.T = 300.0
    def set_temp_point(self, uid, T): self.T = T; return T
    def read_temperature(self, uid):
        if self.fail: raise RuntimeError("fake read failure")
        return self.T
    def get_system_catalog(self): return {'MB0.H1': ['HTR'], 'MB1.T1': ['TEMP']}
    def __getattr__(self, name):
        return lambda *a, **k: True


# ---------------------------------------------------------------- 1. UI + panel defaults
m = ns["moSys"]()
ui = m.ui
check("title kept", ui.titlelabel.text() == EXPECT['title'])
for w in ('tabWidget', 'connGroup', 'ScanLog', 'scanLogText', 'FlipMount', 'FM_connect', 'FM_Indicate',
          'AutoBlock', 'fmManual', 'fmPassCh', 'activeFlipMount', 'scanDevices', 'PMLed', 'activePowerMeter'):
    if getattr(ui, w, None) is None:
        check(f"widget {w} present", False)
check("new widgets present", all(getattr(ui, w, None) is not None for w in ('tabWidget', 'ScanLog', 'FlipMount', 'connGroup')))
check("panel defaults are this system's addresses",
      all(getattr(ui, k).currentText() == v for k, v in EXPECT['defaults'].items()))
check("LED off and button 'Block / Pass' before connect",
      ui.FM_Indicate.status is False and ui.fmManual.text() == "Block / Pass")

# ---------------------------------------------------------------- 2. connect uses panel values
originals = {}
for name, cls in (('SR830', FakeSR830), ('LinearStage', FakeLinear), ('RotaryStage', FakeRotary),
                  ('PM500', FakePM500), ('PILinearStage', FakePI), ('FilterFlipper', FakeMount),
                  ('MercuryiTC', FakeITC)):
    if name in ns:
        originals[name] = ns[name]
        ns[name] = cls
for box in ('activeLockin1', 'activeLockin2', 'activeStage1', 'activeStage2', 'activeRot1', 'activeRot2',
            'activeRot3', 'activeFlipMount', 'activeiTC'):
    getattr(ui, box).setChecked(True)
edited = {'Lockin1_res': 'GPIB0::21::INSTR', 'Rot2_res': '11111111', 'FM_res': '22222222', 'iTC_res': 'ASRL9::INSTR'}
for k, v in edited.items():
    getattr(ui, k).setCurrentText(v)
m.qwait_time = lambda ms: None
m.connectInstruments()
ns.update(originals)  # the real classes are also used outside connecting (e.g. SR830 label lists)
args = [a[0] if a else None for _, a, _ in CALLS]
check("edited lock-in address reaches SR830", 'GPIB0::21::INSTR' in args)
check("edited rotary serial reaches RotaryStage", '11111111' in args)
check("edited flip mount serial reaches FilterFlipper", '22222222' in args)
check("edited iTC resource reaches MercuryiTC", 'ASRL9::INSTR' in args)
if SYSTEM == 'mo':
    check("Stage2 PM500 gets its VISA resource", ('FakePM500', ('GPIB0::4::INSTR',)) in [(n, a) for n, a, _ in CALLS])
if SYSTEM == 'thz':
    pi = [(a, k) for n, a, k in CALLS if n == 'FakePI']
    check("Stage1 PI E-861 gets its serial and the axis ID as a string",
          pi and pi[0][0][0] == '0119001337' and pi[0][1].get('axis') == '1')
if SYSTEM == 'img':
    check("Stage2 gets serial 73844983 channel 2", ('FakeLinear', ('73844983', 2)) in [(n, a) for n, a, _ in CALLS])
check("flip mount connected, LED/button show its state",
      m.flipmount is not None and ui.FM_connect.status is True and ui.fmManual.text() in ("Blocked", "Pass"))
s = ini_settings(EXPECT['org'], "InstrumentConnections")
check("settings saved under this system's own name", s.value('FM_res') == '22222222')
m2 = ns["moSys"]()
check("a new window restores saved values", m2.ui.FM_res.currentText() == '22222222')
m2.ui.close()

# manual button
ui.fmPassCh.setCurrentIndex(0)
ui.fmManual.setChecked(True)
check("manual press blocks: mount at CH2, LED off", m.flipmount.p == 2 and ui.FM_Indicate.status is False)
ui.fmManual.setChecked(False)
check("manual release passes: mount at CH1, LED on", m.flipmount.p == 1 and ui.FM_Indicate.status is True)

# ---------------------------------------------------------------- 3. scans (lock-in 1 + stage1 only)
for box in ('activeLockin2', 'activeStage2', 'activeRot1', 'activeRot2', 'activeRot3', 'activeiTC',
            'activeFlipMount', 'ScanT', 'AutoBlock'):
    getattr(ui, box).setChecked(False)
m.lockin1 = FakeSR830(); m.stage1 = FakeLinear()
m.is_custom_save_path = True
m.dataSave_path = TMP
ui.wait1.setValue(0); ui.wait2.setValue(0)
ui.stage1Step1.setValue(10); ui.stage1Step1NO.setValue(5); ui.stage1Step2NO.setValue(0); ui.stage1Step3NO.setValue(0)
ui.scanRepNO1.setValue(1); ui.scanRepNO2.setValue(1); ui.ScanRepNO_R1.setValue(1); ui.ScanRepNO_R2.setValue(1)
if getattr(ui, 'WaitSamStable', None) is not None:
    ui.WaitSamStable.setValue(0)
ui.scanMode.setCurrentText(EXPECT['mode'])

from PySide6.QtWidgets import QMessageBox
refusals = []
QMessageBox.warning = staticmethod(lambda *a, **k: refusals.append(a[2] if len(a) > 2 else ''))


def run(stop_after=None, timeout=60):
    before = m.scan_Thread
    m.runScan()
    if m.scan_Thread is before:
        return False  # refused
    t0 = time.time(); stopped = False
    while m.scan_Thread.isRunning() or time.time() - t0 < 0.3:
        app.processEvents()
        if stop_after is not None and not stopped and time.time() - t0 > stop_after:
            m.scan_Thread.request_stop(); stopped = True
        if time.time() - t0 > timeout:
            raise RuntimeError("scan did not finish")
        time.sleep(0.01)
    for _ in range(50):
        app.processEvents(); time.sleep(0.01)
    return True


def last_block():
    files = glob.glob(os.path.join(TMP, "ScanLog_*.txt"))
    txt = open(files[0], encoding="utf-8").read() if files else ""
    return files, txt.split("=" * 72)[-1]


check("plain scan runs", run())
files, last = last_block()
check("dated ScanLog file in the data folder", len(files) == 1 and time.strftime("%Y-%m-%d") in files[0])
check("header + data file + finished", f"Mode        : {EXPECT['mode']}" in last and "Data file:" in last
      and "Scan finished" in last)

ui.AutoBlock.setChecked(True); m.flipmount = None
check("AutoBlock without a mount is refused", not run() and refusals)
ui.AutoBlock.setChecked(False)
ui.activeFlipMount.setChecked(True); m.flipmount = FakeMount()
ui.activeLockin1.setChecked(False); ui.activeStage1.setChecked(False)
refusals.clear()
check("flip mount alone is refused", not run() and refusals)
ui.activeLockin1.setChecked(True); ui.activeStage1.setChecked(True)

# temperature scan with AutoBlock
ui.activeiTC.setChecked(True); m.mercuryiTC = FakeITC(); m.uid_TEMP = "T"; m.uid_HTR = "H"
ui.ScanT.setChecked(True); ui.T_stab_cnt.setValue(1); ui.waitiTC.setValue(0)
m.tp_manager.clear_all(); m.tp_manager.add_sequence(10, 10, 2)
ui.AutoBlock.setChecked(True); ui.fmPassCh.setCurrentIndex(0)
mount = FakeMount(); m.flipmount = mount
check("temperature scan with AutoBlock runs", run())
_, last = last_block()
# CH1 = pass (1), CH2 = block (2): block, pass per T point, then block at the end
check("mount: block, pass, block, pass, block", mount.moves == [2, 1, 2, 1, 2])
check("LED off (blocked) at the end", ui.FM_Indicate.status is False and ui.fmManual.text() == "Blocked")
check("log: both T points, both data files, AutoBlock, finished",
      last.count("K reached") + last.count("stabilization not started") == 2 and last.count("Data file:") == 2
      and "AutoBlock   : on" in last and "Scan finished" in last)

# stabilization failure
mount = FakeMount(); m.flipmount = mount
m.mercuryiTC = FakeITC(fail=True)
run()
_, last = last_block()
check("stabilization failure -> aborted, beam blocked", "Scan aborted: temperature stabilization failed" in last
      and mount.p == 2)

# stop mid-measurement
m.mercuryiTC = FakeITC(); ui.ScanT.setChecked(False)
ui.stage1Step1NO.setValue(300); ui.wait1.setValue(10)
mount = FakeMount(); m.flipmount = mount
run(stop_after=0.5)
_, last = last_block()
check("stop -> 'stopped by user', beam blocked", "Scan stopped by user" in last and mount.p == 2)

# MO: 1D_THz peak tracking (Stage2) runs per temperature point - the beam must pass for every lock-in
# read, the peak search included, and each T point logs one peak line
if SYSTEM == 'mo':
    reads = []

    class ReadingLockin(FakeSR830):
        def get_x(self):
            reads.append(m.flipmount.p)
            return 1.0

    ui.stage1Step1NO.setValue(5); ui.wait1.setValue(0)
    ui.activeStage2.setChecked(True); m.stage2 = FakePM500()
    ui.stage2Step1.setValue(10); ui.stage2Step1NO.setValue(3); ui.stage2Step2NO.setValue(0); ui.stage2Step3NO.setValue(0)
    ui.ScanT.setChecked(True); m.mercuryiTC = FakeITC()
    ui.scanMode.setCurrentText('1D_THz')
    m.lockin1 = ReadingLockin()
    mount = FakeMount(); m.flipmount = mount
    run()
    _, last = last_block()
    check("MO 1D_THz: every lock-in read (peak search included) with the beam passing",
          len(reads) > 400 and all(p == 1 for p in reads))
    check("MO 1D_THz: one Stage2 peak line per T point, finished",
          last.count("Stage2 peak tracking: peak at") == 2 and "Scan finished" in last)

import winreg
try:
    winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\" + EXPECT['org']))
    registry_touched = True
except OSError:
    registry_touched = False
check("real registry not touched by the test", not registry_touched)

print(f"\n{sum(ok for _, ok in results)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)
