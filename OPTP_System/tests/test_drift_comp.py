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
VERSION_PARTS = tuple(map(int, VERSION.split('.')))
NEW_PEAK_RULES = VERSION_PARTS >= (3, 7)
ANGLE_PEAK_RULES = VERSION_PARTS >= (3, 8)
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
ns['moSys'].setup_data_folder = lambda self: setattr(self, 'dataSave_path', TMP)
m = ns['moSys']()
ui = m.ui

check("defaults: Drift comp. on, unset Ppos, search windows, Reverse and version-specific beam order",
      ui.driftComp.isChecked() and ui.TDS_Ppos.value() == ui.TDS_Ppos.minimum() and ui.TDS_Ppos.text() == 'Not set'
      and (ui.R1_step.value(), ui.R1_pts.value(), ui.R2_step.value(), ui.R2_pts.value()) == (3, 30, 1, 30)
      and ui.stage2CompDir.isChecked() and ui.stage2CompDir.text() == 'Reverse'
      and ui.passOrder.isChecked() == (VERSION_PARTS < (3, 6))
      and ui.passOrder.text() == ('Pass → Soak' if VERSION_PARTS < (3, 6) else 'Soak → Pass'))
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
if NEW_PEAK_RULES:
    check("ScanT off: one initial search and peak settings logged", answers and len(F) == 1
          and len(READS) == 125 and last_log().count('Peak search: Ppos') == 1
          and 'Drift comp. : on' in last_log() and np.allclose(F[0][2], 1, atol=2e-3))
    # Remove the controller entirely: neither initial nor repeat search may require it.
    saved_itc, saved_peak = m.mercuryiTC, lockin.peak
    m.mercuryiTC = None; ui.activeiTC.setChecked(False); lockin.peak = lambda: P0
    reset_positions(ppos=ui.TDS_Ppos.minimum())
    check("ordinary scan still rejects a missing Ppos before starting", not run()
          and warnings and 'TDS Ppos is not set' in warnings[0])
    for forward in (False, True):
        ui.stage2CompDir.setChecked(forward is False)
        reset_positions(ipos1=P0 + 0.050)
        run(); F = files()
        expected_stage2 = IPOS2_0 - 0.050 if forward else IPOS2_0 + 0.050
        check(f"no iTC: stale 50 um offset removed and Stage2 compensated ({forward=})",
              len(F) == 1 and np.isclose(F[0][0], P0) and np.isclose(F[0][1], expected_stage2)
              and np.allclose(F[0][2], 1, atol=2e-3) and 'will not be retained' in answers[0])
    ui.stage2CompDir.setChecked(True)
    for mode in ('THz_Scan', '2D_THz', 'POL_2D'):
        ui.scanMode.setCurrentText(mode); reset_positions(ipos1=P0 - 0.020)
        run(); F = files()
        check(f"ordinary {mode}: search once and preserve the scan offset", len(F) == 1
              and np.isclose(F[0][0], P0 - 0.020) and last_log().count('Peak search: Ppos') == 1)
    setup_1d(); ui.driftComp.setChecked(False); reset_positions(); run()
    check("ordinary scan: Drift comp off disables searching without an iTC", not answers
          and len(READS) == 3 and 'Drift comp. : off' in last_log())
    ui.driftComp.setChecked(True)
    m.mercuryiTC, lockin.peak = saved_itc, saved_peak
    ui.activeiTC.setChecked(True)
else:
    check("no temperature scan: no dialog, no search", not answers and len(F) == 1 and len(READS) == 3
          and "Drift comp." not in last_log())
ui.ScanT.setChecked(True)

# ---------------------------------------------------------------- stop during the search
reset_positions(); ui.AutoBlock.setChecked(True); lockin.stop_at = 20; run(); lockin.stop_at = None
check("Stop during the search ends the scan (no data file) and blocks the beam",
      not files() and "Scan stopped by user" in last_log() and m.flipmount.p == 2 and len(READS) == 20)

# ---------------------------------------------------------------- drift continuing between Stage2 repeats
if hasattr(ui, 'repeatPeak'):
    check("repeat peak defaults on", ui.repeatPeak.isChecked() and ui.repeatPeak.text() == 'Re-peak: ON')
    ui.repeatPeak.setChecked(False)
    check("repeat peak toggle caption follows off", ui.repeatPeak.text() == 'Re-peak: OFF')
    ui.repeatPeak.setChecked(True)
    m.set_ControlsEnabledDuringScan(True)
    check("repeat peak toggle is locked during acquisition", not ui.repeatPeak.isEnabled())
    m.set_ControlsEnabledDuringScan(False)

    setup_1d(); ui.scanRepNO2.setValue(3)
    m.tp_manager.clear_all(); m.tp_manager.add_sequence(10, 10, 2)
    shifts, measured, search_calls = {}, {}, []
    searching, fail_search_no = [False], [None]
    old_peak, old_get_x = lockin.peak, lockin.get_x
    old_compensate = m.compensate_temperature_drift
    lockin.peak = lambda: old_peak() + shifts.get(m.mercuryiTC.T, 0.0)

    def drifting_read():
        value = old_get_x()
        if not searching[0]:
            temperature = m.mercuryiTC.T
            measured[temperature] = measured.get(temperature, 0) + 1
            # The sample drifts +4 um AFTER each 3-point Stage2 sweep, including with re-peak off.
            if measured[temperature] % 3 == 0:
                shifts[temperature] = shifts.get(temperature, 0.0) + 0.004
        return value

    def track_search(*args):
        search_calls.append(m.mercuryiTC.T)
        searching[0] = True
        previous_mode = lockin.mode
        if len(search_calls) == fail_search_no[0]:
            lockin.mode = 'far'
        try:
            return old_compensate(*args)
        finally:
            lockin.mode = previous_mode
            searching[0] = False

    lockin.get_x = drifting_read
    m.compensate_temperature_drift = track_search

    def repeat_run():
        shifts.clear(); measured.clear(); search_calls.clear()
        reset_positions()
        run()
        saved = []
        for path in sorted(glob.glob(os.path.join(TMP, '*.h5'))):
            with h5py.File(path, 'r') as h:
                saved.append({
                    'signal': h['lockin1_X'][()],
                    'positions': h['repeat_scan_positions_mm'][()] if 'repeat_scan_positions_mm' in h else None,
                    'initial': (float(h['iPos1'][()]), float(h['iPos2'][()])),
                })
        return saved

    saved = repeat_run()
    check("two temperatures x three repeats: exactly six peak searches", search_calls == [10] * 3 + [20] * 3)
    check("re-peak corrects ongoing drift: every measured point stays on the peak",
          len(saved) == 2 and all(np.allclose(f['signal'], 1, atol=2e-3) for f in saved))
    expected_peaks = [np.array([peak(t) + r * 0.004 for r in range(3)]) for t in (10, 20)]
    check("per-repeat metadata stores stage1, compensated stage2 and latest peak",
          all(np.allclose(f['positions'][0, 0, :, 0, 0, :],
                          np.column_stack((p, IPOS2_0 - (p - P0), p))) for f, p in zip(saved, expected_peaks)))
    check("initial scalar coordinates remain the first sweep reference",
          all(np.allclose(f['initial'], (p[0], IPOS2_0 - (p[0] - P0))) for f, p in zip(saved, expected_peaks)))
    check("repeat search adds no extra beam passes, sample soaks or beam-settle waits",
          EVENTS.count('pass') == 2 and EVENTS.count('soak') == 2 and len(BEAM_WAITS) == 2)
    check("ScanLog records the repeat setting and each extra search",
          'Repeat peak : on' in last_log() and last_log().count('Repeat peak search: Stage2 repeat') == 4)

    ui.stage2CompDir.setChecked(False)
    saved = repeat_run()
    check("repeat compensation also honors Forward direction",
          all(np.allclose(f['positions'][0, 0, :, 0, 0, 1], IPOS2_0 + (p - P0)) for f, p in zip(saved, expected_peaks)))
    ui.stage2CompDir.setChecked(True)

    ui.repeatPeak.setChecked(False)
    saved = repeat_run()
    check("repeat peak off retains one search per temperature and the original file layout",
          search_calls == [10, 20] and all(f['positions'] is None for f in saved))
    check("off switch permits the drifted later sweeps, proving no hidden repeat search",
          all(np.all(f['signal'][0, 0, :, 1, 0, 0] < 0.8) for f in saved))
    ui.repeatPeak.setChecked(True)

    ui.scanMode.setCurrentText('2D_THz'); ui.stage1Step1NO.setValue(3)
    saved = repeat_run()
    check("2D_THz with Stage2 repeats still searches only once per temperature",
          search_calls == [10, 20] and all(f['positions'] is None for f in saved))
    setup_1d()
    ui.driftComp.setChecked(False)
    saved = repeat_run()
    check("Drift comp. off disables both initial and repeat searches", not search_calls and all(f['positions'] is None for f in saved))
    ui.driftComp.setChecked(True); ui.ScanT.setChecked(False)
    saved = repeat_run()
    if NEW_PEAK_RULES:
        check("ordinary 1D repeats re-peak and track continuing drift", len(search_calls) == 3
              and len(saved) == 1 and saved[0]['positions'] is not None
              and np.allclose(saved[0]['signal'], 1, atol=2e-3))
        check("ordinary repeat searches add no temperature/soak/beam waits", not BEAM_WAITS
              and EVENTS.count('soak') == 0 and EVENTS.count('pass') == 1)
        ui.repeatPeak.setChecked(False); saved = repeat_run()
        check("ordinary Re-peak off keeps just the initial search", len(search_calls) == 1
              and saved[0]['positions'] is None and np.all(saved[0]['signal'][0, 0, :, 1, 0, 0] < 0.8))
        ui.repeatPeak.setChecked(True)
    else:
        check("non-temperature 1D repeats add no peak searches", not search_calls and len(saved) == 1 and saved[0]['positions'] is None)
    ui.ScanT.setChecked(True); ui.scanRepNO2.setValue(1)
    saved = repeat_run()
    check("Stage2 repeat count one adds no extra search", search_calls == [10, 20] and all(f['positions'] is None for f in saved))
    ui.scanRepNO2.setValue(3)

    lockin.stop_at = 122 + 3 + 20
    saved = repeat_run()
    lockin.stop_at = None
    check("Stop during repeat search preserves first sweep, leaves later sweeps NaN, closes file and blocks",
          len(saved) == 1 and np.isfinite(saved[0]['signal'][0, 0, :, 0, 0, 0]).all()
          and np.isnan(saved[0]['signal'][0, 0, :, 1:, 0, 0]).all()
          and np.isnan(saved[0]['positions'][0, 0, 1:, 0, 0, :]).all()
          and not m.h5_file and m.flipmount.p == 2 and 'Scan stopped by user' in last_log())

    fail_search_no[0] = 2
    saved = repeat_run()
    check("failed repeat peak search keeps the previous reference and later searches can recover",
          np.allclose(saved[0]['positions'][0, 0, 0, 0, 0, :], saved[0]['positions'][0, 0, 1, 0, 0, :])
          and np.allclose(saved[0]['signal'][0, 0, :, 2, 0, 0], 1, atol=2e-3)
          and 'WARNING: peak search failed' in last_log())
    fail_search_no[0] = None

    original_limits = m.stage2.travel_limits
    m.stage2.travel_limits = lambda: (IPOS2_0 - 0.003, 300)
    try:
        saved = repeat_run()
    finally:
        m.stage2.travel_limits = original_limits
    check("repeat correction outside travel aborts before any second-sweep acquisition",
          len(saved) == 1 and np.isnan(saved[0]['signal'][0, 0, :, 1:, 0, 0]).all()
          and 'planned positions do not fit' in last_log() and m.flipmount.p == 2 and not m.h5_file)

    ui.stage1Step1NO.setValue(2); ui.rotary2Step.setValue(30); ui.rotary2StepNO.setValue(2)
    saved = repeat_run()
    check("each stage1/polarization context gets searches before Stage2 repeats 2 and 3",
          len(search_calls) == 2 * (1 + 2 * 2 * 2)
          and all(f['positions'].shape == (2, 1, 3, 2, 1, 3) and np.isfinite(f['positions']).all() for f in saved))

    lockin.peak, lockin.get_x = old_peak, old_get_x
    m.compensate_temperature_drift = old_compensate

if ANGLE_PEAK_RULES:
    # A real angular dependence exposes both missing first-sweep searches and searches
    # that silently return the rotaries to the original polarization.
    setup_1d(); ui.ScanT.setChecked(False); ui.AutoBlock.setChecked(True)
    ui.driftComp.setChecked(True); ui.repeatPeak.setChecked(True)
    ui.scanRepNO2.setValue(2); ui.ScanRepNO_R1.setValue(1); ui.ScanRepNO_R2.setValue(1)
    ui.Rot_stages_couple.setChecked(True)
    for n, start, step in ((1, 10, 10), (2, 20, 5), (3, 30, 5)):
        getattr(ui, f'activeRot{n}').setChecked(n != 3)
        setattr(m, f'rotary{n}', FakeStage())
        getattr(ui, f'iRot{n}').setValue(start)
        getattr(ui, f'rotary{n}Step').setValue(step)
        getattr(ui, f'rotary{n}StepNO').setValue(3 if n != 3 else 99)
    lockin.peak = lambda: P0 + (m.rotary1.pos - 10) * 0.0004 + (
        (m.rotary3.pos - 30) * 0.0004 if ui.activeRot3.isChecked() else 0)
    angle_searches = []
    original_search = m.get_TDS_peak_pos
    def capture_angle_search(*args, **kwargs):
        angle_searches.append((m.rotary1.pos, m.rotary2.pos, m.rotary3.pos))
        return original_search(*args, **kwargs)
    m.get_TDS_peak_pos = capture_angle_search

    def angle_run():
        angle_searches.clear(); reset_positions()
        run()
        saved = []
        for path in sorted(glob.glob(os.path.join(TMP, '*.h5'))):
            with h5py.File(path, 'r') as h:
                saved.append((h['lockin1_X'][()], h['repeat_scan_positions_mm'][()] if 'repeat_scan_positions_mm' in h else None))
        return saved

    expected_angles = [(10, 20, 0), (20, 25, 0), (30, 30, 0)]
    saved = angle_run()
    check('angle change: three angles x two sweeps search at every correct angle',
          angle_searches == [angle for angle in expected_angles for _ in range(2)])
    check('angle change: first and repeat acquisitions remain at the physical peak',
          len(saved) == 1 and np.allclose(saved[0][0], 1, atol=2e-3))
    check('angle change: log distinguishes new angles from Stage2 repeats',
          last_log().count('Angle peak search:') == 2 and last_log().count('Repeat peak search:') == 3)
    check('angle change: each sweep saves its peak and compensated Stage2 start',
          saved[0][1] is not None and np.allclose(saved[0][1][0, 0, :, :, 0, 0], [[P0, P0 + .004, P0 + .008]] * 2)
          and np.allclose(saved[0][1][0, 0, :, :, 0, 1], [[IPOS2_0, IPOS2_0 - .004, IPOS2_0 - .008]] * 2))
    check('angle change: no added beam pass, temperature or soak wait',
          EVENTS.count('pass') == 1 and not BEAM_WAITS and EVENTS.count('soak') == 0)

    ui.repeatPeak.setChecked(False)
    saved = angle_run()
    check('Re-peak OFF still searches once per new angle and saves all coordinates',
          angle_searches == expected_angles and np.allclose(saved[0][0], 1, atol=2e-3)
          and saved[0][1] is not None and 'Repeat peak search:' not in last_log())
    ui.scanRepNO2.setValue(1)
    saved = angle_run()
    check('one Stage2 sweep still searches before every changed angle',
          angle_searches == expected_angles and np.allclose(saved[0][0], 1, atol=2e-3) and saved[0][1] is not None)
    ui.ScanRepNO_R2.setValue(2)
    saved = angle_run()
    check('polarization repeat searches again when returning from last to first angle',
          angle_searches == expected_angles * 2 and np.allclose(saved[0][0], 1, atol=2e-3))
    ui.ScanRepNO_R2.setValue(1); ui.ScanT.setChecked(True)
    saved = angle_run()
    check('temperature points each start searching at the first planned angle',
          angle_searches == expected_angles * 2 and len(saved) == 2
          and all(np.allclose(signal, 1, atol=2e-3) for signal, _ in saved))
    ui.ScanT.setChecked(False); ui.driftComp.setChecked(False)
    saved = angle_run()
    check('Drift OFF disables angular and repeat search', not angle_searches and saved[0][1] is None)
    ui.driftComp.setChecked(True); ui.repeatPeak.setChecked(True); ui.scanRepNO2.setValue(2)
    ui.Rot_stages_couple.setChecked(False)
    ui.rotary1StepNO.setValue(2); ui.rotary2StepNO.setValue(2)
    ui.rotary3StepNO.setValue(1)
    saved = angle_run()
    independent = [(10, 20, 0), (10, 25, 0), (20, 20, 0), (20, 25, 0)]
    check('independent angular states search in acquisition order at their actual angles',
          angle_searches == [angle for angle in independent for _ in range(2)]
          and np.allclose(saved[0][0], 1, atol=2e-3))

    # Calibration's first angle can differ from the UI starting angle.
    ui.Rot_stages_couple.setChecked(True); ui.pol_cali_mode.setChecked(True)
    m.cali_table = {'rot1_cali': [15, 25], 'rot2_cali': [20, 25], 'rot3_cali': []}
    saved = angle_run()
    check('calibrated scan searches at interpolated angles, including its initial search',
          angle_searches == [(15, 20, 0)] * 2 + [(25, 25, 0)] * 2
          and np.allclose(saved[0][0], 1, atol=2e-3))
    ui.pol_cali_mode.setChecked(False); m.cali_table = None
    ui.activeRot3.setChecked(True); ui.rotary3StepNO.setValue(2)
    saved = angle_run()
    check('checked Rot3 participates in each search at the current angle',
          angle_searches == [(10, 20, 30)] * 2 + [(20, 25, 35)] * 2
          and np.allclose(saved[0][0], 1, atol=2e-3))
    ui.activeRot3.setChecked(False); ui.rotary3StepNO.setValue(1)

    # Other scan modes retain the initial search only.
    for mode in ('THz_Scan', '2D_THz', 'POL_2D'):
        ui.scanMode.setCurrentText(mode)
        saved = angle_run()
        check(f'{mode}: angular change adds no new search', len(angle_searches) == 1 and saved[0][1] is None)
    setup_1d(); ui.scanRepNO2.setValue(1); ui.repeatPeak.setChecked(False)
    lockin.stop_at = 122 + 3 + 20
    saved = angle_run(); lockin.stop_at = None
    check('stop during angular search keeps first-angle data and leaves later data NaN',
          len(saved) == 1 and np.isfinite(saved[0][0][:, :, :, :, 0, :]).all()
          and np.isnan(saved[0][0][:, :, :, :, 1:, :]).all() and not m.h5_file and m.flipmount.p == 2)
    m.get_TDS_peak_pos = original_search

print(f"\n{sum(ok for _, ok in results)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)
