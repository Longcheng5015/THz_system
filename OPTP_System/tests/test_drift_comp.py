"""Headless check of temperature drift compensation and beam settling (Peak search tab).

Runs the real runScan() -> ScanThread path with fake instruments: the fake lock-in reads a Gaussian THz
peak on stage1 whose position drifts linearly with the fake iTC temperature, so the expected iPos1 / iPos2
of every temperature point are known exactly. No hardware, no window, no registry (QSettings -> temp ini).

    python OPTP_System/tests/test_drift_comp.py        (v3.5 by default)
    python OPTP_System/tests/test_drift_comp.py 3.2    (check an earlier version)

Prints PASS/FAIL per check and "N/N passed"; exits 1 on any failure.
"""
import os, sys, tempfile, threading, time, glob
os.environ["QT_QPA_PLATFORM"] = "offscreen"

SYS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = sys.argv[1] if len(sys.argv) > 1 else "3.5"
SRC = os.path.join(SYS_DIR, f"OPTP_system_iTC_v{VERSION}.py")
os.chdir(SYS_DIR)
sys.path.insert(0, SYS_DIR)

import numpy as np
import h5py
from PySide6.QtCore import QSettings
TMP = tempfile.mkdtemp()

src = open(SRC, encoding="utf-8").read()
src = src[: src.rindex("app = QApplication()")]  # drop the app start-up at the bottom
ns = {"__file__": SRC, "__name__": "optp_under_test"}
exec(compile(src, SRC, "exec"), ns)
ns['QSettings'] = lambda org, app: QSettings(os.path.join(TMP, f"{org}.{app}.ini"), QSettings.IniFormat)

from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])

results = []
def check(name, cond):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)


# ---------------------------------------------------------------- fakes
P0, T0, K = 188.922, 10.0, -0.0004       # peak at 10 K; drift -0.4 um/K -> -4 um per 10 K
SIGMA = 0.004                            # 4 um Gaussian width
EVENTS, READS = [], []                   # event order, and (stage1, stage2) at every lock-in read


class FakeStage:
    def __init__(self): self.pos = 0.0
    def move_to(self, p): self.pos = p
    def position(self): return self.pos
    def travel_limits(self): return (0.0, 300.0)
    def close(self): pass


class FakeITC:
    def __init__(self):
        self.io_lock = threading.RLock(); self.T = 300.0
    def set_temp_point(self, uid, T): self.T = T; return T
    def read_temperature(self, uid): return self.T
    def __getattr__(self, name): return lambda *a, **k: True


class FakeMount:
    def __init__(self): self.p = 2
    def move_to(self, p):
        self.p = p
        EVENTS.append('pass' if p == 1 else 'block')   # fmPassCh = CH1 -> position 1 passes
    def position(self): return self.p
    def close(self): pass


class FakeLockin:
    mode = 'normal'          # 'normal' | 'nan' | 'far'
    stop_at = None           # press Stop (from the scan thread, deterministically) at this read
    def peak(self):
        p = P0 + K * (m.mercuryiTC.T - T0)
        return p + (0.2 if self.mode == 'far' else 0.0)
    def get_x(self):
        if not EVENTS or EVENTS[-1] != 'read':
            EVENTS.append('read')
        READS.append((m.stage1.pos, m.stage2.pos))
        if self.stop_at is not None and len(READS) == self.stop_at:
            m.scan_Thread.request_stop()
        if self.mode == 'nan':
            return float('nan')
        d = m.stage1.pos - self.peak()
        # Gaussian peak plus a weak, broad wing that rises toward the peak (so a far-away peak puts the
        # maximum on the window edge nearest to it)
        return float(np.exp(-d * d / (2 * SIGMA * SIGMA)) + 1e-3 * np.exp(-abs(d) / 0.5))
    def get_y(self): return 0.0
    def close(self): pass


# ---------------------------------------------------------------- set-up
m = ns['moSys']()
ui = m.ui

check("defaults: Drift comp. on, Ppos 'Not set', R1 3 um x 30, R2 1 um x 30, Reverse, Pass -> Soak",
      ui.driftComp.isChecked() and ui.TDS_Ppos.value() == ui.TDS_Ppos.minimum() and ui.TDS_Ppos.text() == 'Not set'
      and (ui.R1_step.value(), ui.R1_pts.value(), ui.R2_step.value(), ui.R2_pts.value()) == (3, 30, 1, 30)
      and ui.stage2CompDir.isChecked() and ui.stage2CompDir.text() == 'Reverse'
      and ui.passOrder.isChecked() and ui.passOrder.text() == 'Pass → Soak')
ui.stage2CompDir.setChecked(False); ui.passOrder.setChecked(False)
check("toggle captions follow the state", ui.stage2CompDir.text() == 'Forward' and ui.passOrder.text() == 'Soak → Pass')
ui.stage2CompDir.setChecked(True); ui.passOrder.setChecked(True)

m.is_custom_save_path = True
m.dataSave_path = TMP
for box in ("activeLockin1", "activeLockin2", "activeStage1", "activeStage2", "activeRot1", "activeRot2",
            "activeRot3", "activeiTC", "activeFlipMount", "ScanT", "AutoBlock"):
    getattr(ui, box).setChecked(False)
lockin = FakeLockin()
ui.activeLockin1.setChecked(True); m.lockin1 = lockin
ui.activeStage1.setChecked(True); m.stage1 = FakeStage()
ui.activeStage2.setChecked(True); m.stage2 = FakeStage()
ui.activeiTC.setChecked(True); m.mercuryiTC = FakeITC(); m.uid_TEMP = "T"; m.uid_HTR = "H"
ui.activeFlipMount.setChecked(True); m.flipmount = FakeMount(); ui.fmPassCh.setCurrentIndex(0)
ui.wait1.setValue(0); ui.wait2.setValue(0)
ui.T_stab_cnt.setValue(1); ui.waitiTC.setValue(0); ui.WaitSamStable.setValue(0)
ui.scanRepNO1.setValue(1); ui.scanRepNO2.setValue(1); ui.ScanRepNO_R1.setValue(1); ui.ScanRepNO_R2.setValue(1)
m.tp_manager.clear_all(); m.tp_manager.add_sequence(10, 10, 3)       # 10, 20, 30 K

IPOS2_0 = 117.310


def soak(thread=None):
    EVENTS.append('soak'); return True
m.wait_sample_stable = soak

HAS_BEAM_SETTLE = hasattr(ui, 'beamSettle')
BEAM_WAITS = []
STOP_IN_BEAM_WAIT = [False]
if HAS_BEAM_SETTLE:
    check("beam settle defaults to 5 min and accepts 0", ui.beamSettle.value() == 5 and ui.beamSettle.minimum() == 0)
    m.set_ControlsEnabledDuringScan(True)
    check("beam settle input is locked during scans", not ui.beamSettle.isEnabled())
    m.set_ControlsEnabledDuringScan(False)
    check("beam settle input is restored after scans", ui.beamSettle.isEnabled())
    real_beam_wait = m.wait_beam_stable
    real_sleep = m._sleep_unless_stopped

    def beam_wait(thread=None):
        EVENTS.append('beam_wait')
        durations = []
        def fast_sleep(seconds, thread=None):
            durations.append(seconds)
            if STOP_IN_BEAM_WAIT[0]:
                thread.request_stop()
            return not m._check_scan_stop(thread)
        m._sleep_unless_stopped = fast_sleep
        try:
            result = real_beam_wait(thread)
            BEAM_WAITS.append((sum(durations), m.flipmount.p, result))
            return result
        finally:
            m._sleep_unless_stopped = real_sleep
    m.wait_beam_stable = beam_wait

warnings, answers = [], []
QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(a[2] if len(a) > 2 else ''))
QMessageBox.question = staticmethod(lambda *a, **k: (answers.append(a[2]), QMessageBox.Yes if ANSWER[0] else QMessageBox.No)[1])
ANSWER = [True]


def setup_1d():
    ui.scanMode.setCurrentText('1D_THz')
    ui.stage1Step1.setValue(1); ui.stage1Step1NO.setValue(1); ui.stage1Step2NO.setValue(0); ui.stage1Step3NO.setValue(0)
    ui.stage2Step1.setValue(10); ui.stage2Step1NO.setValue(3); ui.stage2Step2NO.setValue(0); ui.stage2Step3NO.setValue(0)


def reset_positions(ipos1=P0, ipos2=IPOS2_0, ppos=P0):
    ui.iPos1.setValue(ipos1); ui.iPos2.setValue(ipos2); ui.TDS_Ppos.setValue(ppos)


def run(stop_after=None, timeout=120):
    EVENTS.clear(); READS.clear(); warnings.clear(); answers.clear()
    BEAM_WAITS.clear()
    before = m.scan_Thread
    for f in glob.glob(os.path.join(TMP, "*.h5")):
        os.remove(f)
    m.runScan()
    if m.scan_Thread is before:
        return False
    t0 = time.time(); stopped = False
    while m.scan_Thread.isRunning() or time.time() - t0 < 0.3:
        app.processEvents()
        if stop_after is not None and not stopped and len(READS) >= stop_after:
            m.scan_Thread.request_stop(); stopped = True
        if time.time() - t0 > timeout:
            raise RuntimeError("scan did not finish")
        time.sleep(0.005)
    for _ in range(50):
        app.processEvents(); time.sleep(0.005)
    return True


def files():
    out = []
    for f in sorted(glob.glob(os.path.join(TMP, "*.h5"))):
        with h5py.File(f, 'r') as h:
            out.append((float(h['iPos1'][()]), float(h['iPos2'][()]), h['lockin1_X'][()].reshape(-1)))
    return out


def last_log():
    txt = open(glob.glob(os.path.join(TMP, "ScanLog_*.txt"))[0], encoding='utf-8').read()
    return txt.split("=" * 72)[-1]


peak = lambda T: round(P0 + K * (T - T0), 3)

# ---------------------------------------------------------------- start conditions
setup_1d(); ui.ScanT.setChecked(True); ui.AutoBlock.setChecked(False)
reset_positions(ppos=ui.TDS_Ppos.minimum())
check("temperature scan with Ppos 'Not set' is refused", not run() and warnings and 'TDS Ppos is not set' in warnings[0])
reset_positions()
ui.activeStage1.setChecked(False)
check("Stage1 not active is refused", not run() and warnings and 'Stage1' in warnings[0])
ui.activeStage1.setChecked(True)
ANSWER[0] = False
check("confirmation dialog answered No -> no scan", not run() and len(answers) == 1 and 'TDS Ppos' in answers[0])
ANSWER[0] = True
ui.iPos1.setValue(P0 + 0.005)
run()
check("dialog notes an iPos1 / Ppos mismatch when stage1 is fixed", answers and '+5.0 um' in answers[0])

# ---------------------------------------------------------------- 1D_THz, Reverse
reset_positions()
check("1D_THz temperature scan runs after Yes", run())
F = files()
exp1 = [peak(T) for T in (10, 20, 30)]
exp2 = [round(IPOS2_0 - (p - P0), 3) for p in exp1]
check("1D Reverse: 3 files, iPos1 = drifted peak per T", len(F) == 3 and [round(f[0], 3) for f in F] == exp1)
check("1D Reverse: iPos2 moves opposite (+4 um per 10 K)", [round(f[1], 3) for f in F] == exp2)
check("1D: every measured point sits on the peak (lock-in1 X ~ 1)", all(np.allclose(f[2], 1.0, atol=2e-3) for f in F))
check("UI ends with the compensated iPos1 / iPos2 / Ppos",
      (round(ui.iPos1.value(), 3), round(ui.iPos2.value(), 3), round(ui.TDS_Ppos.value(), 3)) == (exp1[-1], exp2[-1], exp1[-1]))
L = last_log()
check("ScanLog: header + one peak-search line per T point", "Drift comp. : on" in L and L.count("Peak search: Ppos") == 3
      and "delta -4.0 um" in L and "Scan finished" in L)
check("each T point: 61 + 61 search reads + 3 measurement reads; search starts with stage2 at iPos2",
      len(READS) == 3 * (61 + 61 + 3) and READS[0][1] == IPOS2_0)

# ---------------------------------------------------------------- Forward
reset_positions(); ui.stage2CompDir.setChecked(False)
run(); F = files()
check("1D Forward: iPos2 moves with the stage1 peak", [round(f[1], 3) for f in F] == [round(IPOS2_0 + (p - P0), 3) for p in exp1])
ui.stage2CompDir.setChecked(True)

# ---------------------------------------------------------------- other modes: same formula
for mode, s1_no in (('2D_THz', 5), ('THz_Scan', 5), ('POL_2D', 1)):
    reset_positions(ipos1=188.900)                 # window start / fixed point 22 um before the peak
    ui.scanMode.setCurrentText(mode)
    ui.stage1Step1.setValue(10); ui.stage1Step1NO.setValue(s1_no)
    ui.stage2Step1NO.setValue(2 if mode == '2D_THz' else 1)
    ANSWER[0] = True
    run(); F = files()
    check(f"{mode}: iPos1 shifted by the drift, iPos2 opposite",
          len(F) == 3 and [round(f[0], 3) for f in F] == [round(188.900 + (p - P0), 3) for p in exp1]
          and [round(f[1], 3) for f in F] == exp2)
setup_1d(); ui.stage2Step1NO.setValue(3)

# ---------------------------------------------------------------- AutoBlock beam / soak order
ui.AutoBlock.setChecked(True)
reset_positions(); ui.passOrder.setChecked(True); run()
compact = [e for i, e in enumerate(EVENTS) if i == 0 or e != EVENTS[i - 1]]
extra = ['beam_wait'] if HAS_BEAM_SETTLE else []
expected = ['block', 'pass', 'soak'] + extra + ['read']
check("Pass -> Soak: sample soak and beam settle finish before search", compact == expected * 3 + ['block'])
if HAS_BEAM_SETTLE:
    check("Pass -> Soak: full extra 300 s per T point, beam passing", BEAM_WAITS == [(300, 1, True)] * 3)
    check("ScanLog records beam settle duration and completion per T point",
          'Beam settle : 5 min' in last_log() and last_log().count('Beam settle wait complete') == 3)
reset_positions(); ui.passOrder.setChecked(False); run()
compact = [e for i, e in enumerate(EVENTS) if i == 0 or e != EVENTS[i - 1]]
expected = ['block', 'soak', 'pass'] + extra + ['read']
check("Soak -> Pass: sample soak and beam settle finish before search", compact == expected * 3 + ['block'])
if HAS_BEAM_SETTLE:
    check("Soak -> Pass: full extra 300 s per T point, beam passing", BEAM_WAITS == [(300, 1, True)] * 3)
check("beam passed once per T point and blocked at the end", EVENTS.count('pass') == 3 and EVENTS[-1] == 'block')
if HAS_BEAM_SETTLE:
    ui.beamSettle.setValue(0); reset_positions(); run()
    check("zero beam settle skips extra delay and completes measurement", BEAM_WAITS == [(0, 1, True)] * 3 and len(files()) == 3)
    ui.beamSettle.setValue(2); reset_positions(); run()
    check("custom beam settle is interpreted in minutes", BEAM_WAITS == [(120, 1, True)] * 3)
    ui.beamSettle.setValue(5)
    ui.driftComp.setChecked(False); reset_positions(); run()
    check("Drift comp. off still settles before measurement", BEAM_WAITS == [(300, 1, True)] * 3
          and len(READS) == 9 and len(files()) == 3 and EVENTS.index('beam_wait') < EVENTS.index('read'))
    ui.driftComp.setChecked(True)
    ui.ScanT.setChecked(False); reset_positions(); run()
    check("AutoBlock without temperature scan adds no beam settle wait", not BEAM_WAITS and len(files()) == 1)
    ui.ScanT.setChecked(True)
    for pass_first in (True, False):
        ui.passOrder.setChecked(pass_first); STOP_IN_BEAM_WAIT[0] = True
        reset_positions(); run()
        check(f"Stop during beam settle ({pass_first=}): no search/data, beam blocked",
              not READS and not files() and m.flipmount.p == 2
              and 'Beam settle wait interrupted' in last_log() and 'Scan stopped by user' in last_log())
    STOP_IN_BEAM_WAIT[0] = False
ui.passOrder.setChecked(True); ui.AutoBlock.setChecked(False)

# ---------------------------------------------------------------- failures keep the values and go on
reset_positions(); lockin.mode = 'nan'; run(); F = files()
if HAS_BEAM_SETTLE:
    check("AutoBlock off adds no beam settle wait", not BEAM_WAITS)
check("no valid reading: values kept, measurement continues, WARNING logged",
      len(F) == 3 and all(round(f[0], 3) == P0 and round(f[1], 3) == IPOS2_0 for f in F)
      and last_log().count("WARNING: peak search failed (no valid Lock-in 1 reading)") == 3)
reset_positions(); lockin.mode = 'far'; run(); F = files()
check("peak outside the window: edge maximum -> failed, values kept",
      len(F) == 3 and all(round(f[0], 3) == P0 for f in F) and "maximum on the window edge" in last_log())
lockin.mode = 'normal'

# ---------------------------------------------------------------- no compensation cases
reset_positions(); ui.driftComp.setChecked(False); run(); F = files()
check("Drift comp. off: no dialog, no search, iPos unchanged, log says off",
      not answers and len(F) == 3 and all(round(f[0], 3) == P0 and round(f[1], 3) == IPOS2_0 for f in F)
      and "Drift comp. : off" in last_log() and len(READS) == 3 * 3)
ui.driftComp.setChecked(True)
reset_positions(); ui.ScanT.setChecked(False); run(); F = files()
check("no temperature scan: no dialog, no search", not answers and len(F) == 1 and len(READS) == 3
      and "Drift comp." not in last_log())
ui.ScanT.setChecked(True)

# ---------------------------------------------------------------- stop during the search
reset_positions(); ui.AutoBlock.setChecked(True); lockin.stop_at = 20; run(); lockin.stop_at = None
check("Stop during the search ends the scan (no data file) and blocks the beam",
      not files() and "Scan stopped by user" in last_log() and m.flipmount.p == 2 and len(READS) == 20)

print(f"\n{sum(ok for _, ok in results)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)
