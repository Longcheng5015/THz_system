"""Headless end-to-end check of the v3.1 ScanLog box + per-day log file, using fake instruments.

Runs the real runScan() -> ScanThread path with fake lock-in / stages / iTC / flip mount; no hardware
and no window are needed. Data and log files go to a temporary folder.

    python OPTP_System/tests/test_scanlog.py

Prints PASS/FAIL per check, the generated log file, and "N/N passed"; exits 1 on any failure.
"""
import os, sys, tempfile, threading, time, glob
os.environ["QT_QPA_PLATFORM"] = "offscreen"

SYS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(SYS_DIR, "OPTP_system_iTC_v3.1.py")
os.chdir(SYS_DIR)
sys.path.insert(0, SYS_DIR)

src = open(SRC, encoding="utf-8").read()
src = src[: src.rindex("app = QApplication()")]  # drop the app start-up at the bottom
ns = {"__file__": SRC, "__name__": "optp_under_test"}
exec(compile(src, SRC, "exec"), ns)

from PySide6.QtWidgets import QApplication
app = QApplication([])


class FakeLockin:
    def get_x(self): return 1.0
    def get_y(self): return 0.5
    def close(self): pass


class FakeStage:
    def __init__(self): self.pos = 0.0
    def move_to(self, p): self.pos = p
    def position(self): return self.pos
    def travel_limits(self): return (0.0, 300.0)
    def close(self): pass


class FakeITC:
    def __init__(self, fail=False):
        self.io_lock = threading.RLock(); self.fail = fail; self.T = 300.0
    def set_temp_point(self, uid, T): self.T = T; return T
    def read_temperature(self, uid):
        if self.fail: raise RuntimeError("fake read failure")
        return self.T
    def __getattr__(self, name):  # PID and heater calls: accept anything
        return lambda *a, **k: True


class FakeMount:
    def __init__(self): self.p = 1
    def move_to(self, p): self.p = p
    def position(self): return self.p
    def close(self): pass


results = []
def check(name, cond):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)


def make_sys(tmp):
    m = ns["moSys"]()
    m.is_custom_save_path = True
    m.dataSave_path = tmp
    ui = m.ui
    for box in ("activeLockin1", "activeLockin2", "activeStage1", "activeStage2", "activeRot1", "activeRot2",
                "activeRot3", "activeiTC", "activeFlipMount", "ScanT", "AutoBlock"):
        getattr(ui, box).setChecked(False)
    ui.activeLockin1.setChecked(True); m.lockin1 = FakeLockin()
    ui.activeStage1.setChecked(True); m.stage1 = FakeStage()
    ui.wait1.setValue(0); ui.wait2.setValue(0)
    ui.iPos1.setValue(10.0)
    ui.stage1Step1.setValue(10); ui.stage1Step1NO.setValue(5)
    ui.stage1Step2NO.setValue(0); ui.stage1Step3NO.setValue(0)
    ui.scanRepNO1.setValue(1); ui.scanRepNO2.setValue(1)
    ui.ScanRepNO_R1.setValue(1); ui.ScanRepNO_R2.setValue(1)
    ui.WaitSamStable.setValue(0)
    ui.scanMode.setCurrentText("THz_Scan")
    return m


def run(m, stop_after=None, timeout=60):
    m.runScan()
    t0 = time.time(); stopped = False
    while m.scan_Thread is not None and (m.scan_Thread.isRunning() or time.time() - t0 < 0.3):
        app.processEvents()
        if stop_after is not None and not stopped and time.time() - t0 > stop_after:
            m.scan_Thread.request_stop(); stopped = True
        if time.time() - t0 > timeout:
            raise RuntimeError("scan did not finish")
        time.sleep(0.01)
    for _ in range(50):
        app.processEvents(); time.sleep(0.01)


def log_text(tmp):
    files = glob.glob(os.path.join(tmp, "ScanLog_*.txt"))
    return files, (open(files[0], encoding="utf-8").read() if files else "")


tmp = tempfile.mkdtemp()

# 1. plain THz_Scan: header + data file + finished, no per-point noise
m = make_sys(tmp)
run(m)
files, txt = log_text(tmp)
check("one dated log file created", len(files) == 1 and time.strftime("%Y-%m-%d") in files[0])
check("header has mode and lock-in and stage1", "Mode        : THz_Scan" in txt and "Lock-in 1   :" in txt
      and "Stage1      : start 10.0 mm, steps 10 um x 5, repeat 1" in txt)
check("inactive instruments not listed", "Stage2" not in txt and "Rotary" not in txt and "Lock-in 2" not in txt)
check("data file event logged", "Data file:" in txt and ".h5" in txt)
check("finished line with duration", "Scan finished (duration 0:00:" in txt)
check("no per-point readings", "Acquired" not in txt and "Lockin1 X=" not in txt)
check("box shows same text as file", m.ui.scanLogText.toPlainText().strip() == txt.strip())

# 2. second scan appends a separated block; 1D_THz with polarization -> peak tracking lines
m.ui.scanMode.setCurrentText("1D_THz")
m.ui.activeStage2.setChecked(True); m.stage2 = FakeStage()
m.ui.stage2Step1.setValue(10); m.ui.stage2Step1NO.setValue(3); m.ui.stage2Step2NO.setValue(0); m.ui.stage2Step3NO.setValue(0)
m.ui.activeRot2.setChecked(True); m.rotary2 = FakeStage()
m.ui.rotary2Step.setValue(10); m.ui.rotary2StepNO.setValue(2)
run(m)
_, txt = log_text(tmp)
check("two scan blocks separated by rule", txt.count("=" * 72) == 2 and txt.count("Scan started") == 2)
check("rotation mode logged", "Rotary2     :" in txt and "Rotation    : Independent" in txt)
check("one peak-tracking summary line", txt.count("Stage1 peak tracking: 10 sweeps, peak ") == 1 and "Stage1 peak at" not in txt)

# 3. user stop
m.ui.scanMode.setCurrentText("THz_Scan")
m.ui.activeStage2.setChecked(False); m.ui.activeRot2.setChecked(False)
m.ui.stage1Step1NO.setValue(300); m.ui.wait1.setValue(10)
run(m, stop_after=0.5)
_, txt = log_text(tmp)
last = txt.split("=" * 72)[-1]
check("stop logged as stopped by user", "Scan stopped by user" in last and "Scan finished" not in last)
m.ui.stage1Step1NO.setValue(5); m.ui.wait1.setValue(0)

# 4. error path (both stage reps > 1): error logged once, no 'finished' after it
m.ui.activeStage2.setChecked(True)
m.ui.scanRepNO1.setValue(2); m.ui.scanRepNO2.setValue(2)
run(m)
_, txt = log_text(tmp)
last = txt.split("=" * 72)[-1]
check("error logged, no finished after", "Scan error: Error: stage1_rep" in last and "Scan finished" not in last
      and last.count("duration") == 1)
m.ui.scanRepNO2.setValue(1); m.ui.scanRepNO1.setValue(1); m.ui.activeStage2.setChecked(False)

# 5. temperature scan with AutoBlock: T points logged
m.ui.activeiTC.setChecked(True); m.mercuryiTC = FakeITC(); m.uid_TEMP = "T"; m.uid_HTR = "H"
m.ui.ScanT.setChecked(True); m.ui.T_stab_cnt.setValue(1); m.ui.waitiTC.setValue(0)
m.tp_manager.clear_all(); m.tp_manager.add_sequence(10, 10, 2)
m.ui.activeFlipMount.setChecked(True); m.flipmount = FakeMount(); m.ui.AutoBlock.setChecked(True)
run(m)
_, txt = log_text(tmp)
last = txt.split("=" * 72)[-1]
check("temperature list in header", "Temperature : 10, 20 K" in last)
check("AutoBlock in header", "AutoBlock   : on" in last)
check("both T points reached + 2 data files", last.count("reached (stabilized + sample soak)") == 2 and last.count("Data file:") == 2)
check("temperature scan finished", "Scan finished" in last)

# 6. stabilization failure -> aborted with reason
m.mercuryiTC = FakeITC(fail=True)
run(m)
_, txt = log_text(tmp)
last = txt.split("=" * 72)[-1]
check("stabilization failure logged as aborted", "Scan aborted: temperature stabilization failed at 10" in last)

print("\n----- log file -----\n" + txt)
print(f"{sum(ok for _, ok in results)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)
