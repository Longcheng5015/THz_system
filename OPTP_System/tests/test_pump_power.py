"""Headless check of the power meter box (OPTP v3.3, ported to MO v2.5, OPTP image v1.6, THz v1.4): live display,
PM config tab, Zero, Realtime, and Record of the pump power.

Runs the real runScan() -> ScanThread path with fake lock-in / stage / iTC / flip mount / power meter;
no hardware and no window are needed. Data and log files go to temporary folders.

    python OPTP_System/tests/test_pump_power.py            (OPTP)
    python OPTP_System/tests/test_pump_power.py mo         (or img / thz)

The 'Pass -> Soak' beam order and Drift comp. exist in OPTP only; that part is skipped elsewhere.
Prints PASS/FAIL per check and "N/N passed"; exits 1 on any failure. Update FILES for a new version.
"""
import os, sys, tempfile, threading, time, glob
os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FILES = {'optp': 'OPTP_System/OPTP_system_iTC_v3.3.py',
         'mo': 'MO_System/MO_system_iTC_v2.5.py',
         'img': 'OPTP_image_System/OPTP_iTC_image_v1.6.py',
         'thz': 'THz_emission_system/THz_emission_system_iTC_v1.4.py'}
SYSTEM = sys.argv[1] if len(sys.argv) > 1 else 'optp'
SRC = os.path.join(ROOT, FILES[SYSTEM])
SYS_DIR = os.path.dirname(SRC)
os.chdir(SYS_DIR)
sys.path.insert(0, SYS_DIR)

try:  # THz imports the PI driver; without pipython a placeholder lets it import (the PI stage is a fake here)
    import pipython  # noqa: F401
except ImportError:
    import types
    _pi = types.ModuleType('pipython'); _pi.GCSDevice = object; _pi.GCSError = Exception
    _pit = types.ModuleType('pipython.pitools'); _pit.waitontarget = _pit.waitonreferencing = lambda *a, **k: None
    sys.modules['pipython'] = _pi; sys.modules['pipython.pitools'] = _pit

src = open(SRC, encoding="utf-8").read()
src = src[: src.rindex("app = QApplication()")]  # drop the app start-up at the bottom
ns = {"__file__": SRC, "__name__": "optp_under_test"}
exec(compile(src, SRC, "exec"), ns)

from PySide6.QtCore import QSettings
_INI_DIR = tempfile.mkdtemp()
# QSettings(org, app) reads/writes the Windows registry (and creates the key); keep the test in a temp ini file
ns['QSettings'] = lambda org, app: QSettings(os.path.join(_INI_DIR, f"{org}.{app}.ini"), QSettings.IniFormat)

import h5py
import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication([])

SETTLE_S, N, REFRESH_MS = 1, 3, 100


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
    def __init__(self): self.io_lock = threading.RLock(); self.T = 300.0
    def set_temp_point(self, uid, T): self.T = T; return T
    def read_temperature(self, uid): return self.T
    def __getattr__(self, name):  # PID and heater calls: accept anything
        return lambda *a, **k: True


class FakeMount:
    """Position 1 = pass, 2 = block (fmPassCh on CH1). Every move is time-stamped."""
    def __init__(self, p=1): self.p = p; self.moves = []
    def move_to(self, p): self.p = p; self.moves.append((time.monotonic(), p))
    def position(self): return self.p
    def close(self): pass


class FakePM:
    """Readings cycle 10, 11, 12 mW; each read remembers where the flip mount was.
    Ranges as measured on the S302C: they move with the wavelength and are not exact decades."""
    RANGES = {800: (0.00369471, 0.0349854, 0.347892, 3.47696),
              1030: (0.00375193, 0.0355272, 0.35328, 3.53081)}
    LIMITS = {"SENS:CORR:WAV? MIN": "1.850000E+02", "SENS:CORR:WAV? MAX": "2.000000E+04"}
    def __init__(self, mount, fail=False, auto=True, range_index=0):
        self.mount, self.fail = mount, fail
        self.reads = []  # (time, mount position, value)
        self.wavelength = 800.0
        self.zero_calls, self.zero_until = 0, 0.0
        self.auto, self.idx, self.errors = auto, range_index, []
    def ranges(self): return self.RANGES.get(int(self.wavelength), self.RANGES[800])
    def query(self, cmd): return self.LIMITS[cmd]
    def write(self, cmd):
        assert cmd == "SENS:POW:RANG:UPP MIN", cmd
        self.idx = 0
    def get_error(self): return self.errors.pop(0) if self.errors else (0, "No error")
    def get_power_auto_range(self): return self.auto
    def set_power_auto_range(self, on): self.auto = bool(on)
    def get_power_range_upper(self): return self.ranges()[self.idx]
    def set_power_range_upper(self, w):  # the meter moves any value up to the next range; above the top it refuses
        # like the real meter, the reported value is rounded and can lie a hair above the range itself
        fits = [i for i, r in enumerate(self.ranges()) if r * (1 - 1e-8) >= w]
        if fits:
            self.idx = fits[0]
        else:
            self.errors.append((-222, "Data out of range"))
    def measure_power(self):
        if self.fail:
            raise RuntimeError("fake PM read failure")
        value = 0.010 + 0.001 * (len(self.reads) % 3)
        self.reads.append((time.monotonic(), self.mount.p, value))
        return value
    def open(self): return ""
    def idn(self): return "Fake,PM100D,0,0"
    def get_wavelength_nm(self): return self.wavelength
    def set_wavelength_nm(self, nm): self.wavelength = float(nm)
    def zero_initiate(self): self.zero_calls += 1; self.zero_until = time.monotonic() + 0.4
    def get_zero_state(self): return time.monotonic() < self.zero_until
    def get_zero_magnitude(self): return -2.1e-4
    def close(self): pass


results = []
def check(name, cond):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)


m = ns["moSys"]()
ui = m.ui
check("wavelength box defaults to 800 nm", ui.pmWavelength.value() == 800)
check("Realtime (PM_realDisp) is released by default", not ui.PM_realDisp.isChecked())
m.is_custom_save_path = True
m.save_connection_settings = lambda: None  # never touch the saved connection settings


def configure(temperature: bool, autoblock: bool, record: bool, pass_first: bool = False, mount_p: int = 1, pm_fail=False):
    """Fresh data folder, fake instruments and a short THz_Scan; returns (tmp, mount, pm)."""
    tmp = tempfile.mkdtemp()
    m.dataSave_path = tmp
    m.stop_flag = False  # runScan resets it; the direct record_pump_power() calls below do not
    for box in ("activeLockin1", "activeLockin2", "activeStage1", "activeStage2", "activeRot1", "activeRot2",
                "activeRot3", "activeiTC", "activeFlipMount", "activePowerMeter", "ScanT", "AutoBlock", "pmRecord"):
        getattr(ui, box).setChecked(False)
    ui.activeLockin1.setChecked(True); m.lockin1 = FakeLockin()
    # both lock-ins: MO v2.5 still reads l2x unset when lock-in 2 is not connected (UnboundLocalError), unrelated here
    ui.activeLockin2.setChecked(True); m.lockin2 = FakeLockin()
    ui.activeStage1.setChecked(True); m.stage1 = FakeStage()
    ui.wait1.setValue(0); ui.wait2.setValue(0)
    ui.iPos1.setValue(10.0)
    ui.stage1Step1.setValue(10); ui.stage1Step1NO.setValue(3)
    ui.stage1Step2NO.setValue(0); ui.stage1Step3NO.setValue(0)
    ui.scanRepNO1.setValue(1); ui.scanRepNO2.setValue(1)
    ui.ScanRepNO_R1.setValue(1); ui.ScanRepNO_R2.setValue(1)
    if getattr(ui, 'WaitSamStable', None) is not None:
        ui.WaitSamStable.setValue(0)
    ui.scanMode.setCurrentText("THz_Scan")
    ui.fmPassCh.setCurrentIndex(0)
    mount = FakeMount(mount_p)
    ui.activeFlipMount.setChecked(True); m.flipmount = mount
    m._fm_blocked_since = None
    pm = FakePM(mount, fail=pm_fail)
    ui.activePowerMeter.setChecked(True); m.powermeter = pm
    ui.pmSettle.setValue(SETTLE_S); ui.pmAvgNO.setValue(N); ui.pmRefresh.setValue(REFRESH_MS); ui.pmWavelength.setValue(800)
    ui.AutoBlock.setChecked(autoblock); ui.pmRecord.setChecked(record)
    if getattr(ui, 'passOrder', None) is not None:  # OPTP only
        ui.passOrder.setChecked(pass_first)
    if getattr(ui, 'driftComp', None) is not None:  # OPTP only; on by default, needs a TDS Ppos, would stop at a dialog
        ui.driftComp.setChecked(False)
    if temperature:
        ui.activeiTC.setChecked(True); m.mercuryiTC = FakeITC(); m.uid_TEMP = "T"; m.uid_HTR = "H"
        ui.ScanT.setChecked(True); ui.T_stab_cnt.setValue(1); ui.waitiTC.setValue(0)
        m.tp_manager.clear_all(); m.tp_manager.add_sequence(10, 10, 2)
    return tmp, mount, pm


def run(stop_after=None, timeout=90):
    m.runScan()
    t0 = time.time(); stopped = False
    while m.scan_Thread is not None and (m.scan_Thread.isRunning() or time.time() - t0 < 0.3):
        app.processEvents()
        if stop_after is not None and not stopped and time.time() - t0 > stop_after:
            m.scan_Thread.request_stop(); stopped = True
        if time.time() - t0 > timeout:
            raise RuntimeError("scan did not finish")
        time.sleep(0.01)
    for _ in range(30):
        app.processEvents(); time.sleep(0.01)


def data_files(tmp):
    return sorted(glob.glob(os.path.join(tmp, "*.h5")), key=os.path.getmtime)


def log_text(tmp):
    files = glob.glob(os.path.join(tmp, "ScanLog_*.txt"))
    return open(files[0], encoding="utf-8").read() if files else ""


def check_records(label, tmp, mount, pm, points):
    """Every point's file holds its own N readings; all were taken with the beam blocked, after the settle time."""
    files = data_files(tmp)
    check(f"{label}: {points} data file(s)", len(files) == points)
    check(f"{label}: {N * points} readings, all with the beam blocked", len(pm.reads) == N * points
          and all(pos == 2 for _, pos, _ in pm.reads))
    for i, path in enumerate(files):
        group = pm.reads[i * N:(i + 1) * N]
        values = np.array([v for _, _, v in group])
        with h5py.File(path, "r") as f:
            ok = ("pump_power_W" in f and abs(f["pump_power_W"][()] - values.mean()) < 1e-12
                  and abs(f["pump_power_std_W"][()] - values.std(ddof=1)) < 1e-12
                  and np.allclose(f["pump_power_samples_W"][()], values)
                  and f["pump_power_wavelength_nm"][()] == 800 and f["pump_power_settle_s"][()] == SETTLE_S
                  and f["pump_power_interval_ms"][()] == REFRESH_MS and len(f["pump_power_time"][()]) >= 19)
        check(f"{label}: file {i + 1} holds its point's mean/std/samples and settings", ok)
        block_t = max(t for t, p in mount.moves if t <= group[0][0])
        last_block = [p for t, p in mount.moves if t == block_t][0]
        check(f"{label}: point {i + 1} read {group[0][0] - block_t:.2f} s after the block move (>= {SETTLE_S} s)",
              last_block == 2 and group[0][0] - block_t >= SETTLE_S - 0.02)
        passes_after = [t for t, p in mount.moves if p == 1 and t > group[-1][0]]
        check(f"{label}: point {i + 1} beam passed only after the readings", bool(passes_after))


# 1. temperature scan, AutoBlock 'Soak -> Pass', Record on: one power per temperature point
tmp, mount, pm = configure(temperature=True, autoblock=True, record=True)
run()
check_records("T scan", tmp, mount, pm, 2)
txt = log_text(tmp)
check("T scan: header has the Record settings", f"Pump power  : Record on (settle {SETTLE_S} s, N {N} x {REFRESH_MS} ms, 800 nm)" in txt)
check("T scan: one pump power line per point, before its data file",
      txt.count("Pump power 11.000 mW") == 2 and txt.index("Pump power 11.000 mW") < txt.index("Data file:"))
check("T scan: finished", "Scan finished" in txt)

# 2. AutoBlock 'Pass -> Soak': recorded before the early pass (OPTP only)
if getattr(ui, 'passOrder', None) is not None:
    tmp, mount, pm = configure(temperature=True, autoblock=True, record=True, pass_first=True)
    run()
    check_records("Pass->Soak", tmp, mount, pm, 2)
else:
    print(f"skip Pass->Soak: {SYSTEM} has no beam order setting")

# 3. no temperature points, beam on Pass at the start: blocked first, full settle, once before the scan
tmp, mount, pm = configure(temperature=False, autoblock=True, record=True, mount_p=1)
run()
check_records("single scan", tmp, mount, pm, 1)
check("single scan: blocked again at the end", mount.p == 2)

# 4. Record without AutoBlock: nothing recorded, and the header says why
tmp, mount, pm = configure(temperature=True, autoblock=False, record=True)
run()
with h5py.File(data_files(tmp)[0], "r") as f:
    check("no AutoBlock: no pump power in the files, meter not read", "pump_power_W" not in f and not pm.reads)
check("no AutoBlock: header explains", "Record is on but AutoBlock is off" in log_text(tmp))

# 5. AutoBlock without Record: the plain AutoBlock flow is unchanged
tmp, mount, pm = configure(temperature=True, autoblock=True, record=False)
run()
files = data_files(tmp)
with h5py.File(files[0], "r") as f:
    check("no Record: 2 files, no pump power, meter not read", len(files) == 2 and "pump_power_W" not in f and not pm.reads)
check("no Record: block/pass per point and blocked at the end", [p for _, p in mount.moves] == [2, 1, 2, 1, 2])

# 6. meter read failure: scan carries on, failure in the ScanLog
tmp, mount, pm = configure(temperature=True, autoblock=True, record=True, pm_fail=True)
run()
files = data_files(tmp)
with h5py.File(files[0], "r") as f:
    check("read failure: scan finished with 2 files without pump power", len(files) == 2 and "pump_power_W" not in f)
txt = log_text(tmp)
check("read failure: logged per point", txt.count("Pump power NOT recorded: RuntimeError: fake PM read failure") == 2
      and "Scan finished" in txt)

# 7. stop during the settle wait: no pass, no data file, blocked at the end
tmp, mount, pm = configure(temperature=True, autoblock=True, record=True)
ui.pmSettle.setValue(30)
run(stop_after=1.5)
check("stop in settle: no data file, meter not read", not data_files(tmp) and not pm.reads)
check("stop in settle: beam never passed", all(p == 2 for _, p in mount.moves))
check("stop in settle: logged as stopped", "Scan stopped by user" in log_text(tmp))
ui.pmSettle.setValue(SETTLE_S)

# 8. settle counted from the last block move; unknown -> full settle
tmp, mount, pm = configure(temperature=False, autoblock=True, record=True, mount_p=2)
ui.pmSettle.setValue(1)
m._fm_blocked_since = time.monotonic() - 100  # lit for long already
t0 = time.monotonic(); r = m.record_pump_power(); dt = time.monotonic() - t0
check(f"lit long enough: no settle wait ({dt:.2f} s)", r is not None and dt < 0.5)
m._fm_blocked_since = None  # blocked before the program took over: unknown
t0 = time.monotonic(); r = m.record_pump_power(); dt = time.monotonic() - t0
check(f"unknown block time: full settle waited ({dt:.2f} s)", r is not None and dt >= 1.0)
check("no mount move when already blocked", mount.moves == [])

# 9. pre-scan check
ui.pmRecord.setChecked(True); ui.AutoBlock.setChecked(True); m.flipmount = FakeMount()
ui.activePowerMeter.setChecked(False); m.powermeter = None
check("Record + AutoBlock without meter: scan refused", "Power meter (Record is on)" in m.check_instruments_ready())
ui.pmRecord.setChecked(False); ui.activePowerMeter.setChecked(True)
check("meter ticked but not connected: scan refused", "Power meter" in m.check_instruments_ready())
m.powermeter = FakePM(m.flipmount)
check("meter ticked and connected: accepted", m.check_instruments_ready() == [])
for box in ("activeLockin1", "activeLockin2", "activeStage1", "activeFlipMount"):
    getattr(ui, box).setChecked(False)
ui.AutoBlock.setChecked(False)
check("meter alone does not count as a measuring instrument",
      "no instrument is marked active at all" in m.check_instruments_ready())

# 10. live display, wavelength, zero
mount = FakeMount(2); pm = FakePM(mount); m.powermeter = pm
m.update_power_display()
check(f"display is plain decimal mW ({ui.PowerMeterDisp.text()!r})", ui.PowerMeterDisp.text() == "10.000 mW")
m.pm_lock.acquire(); before = len(pm.reads); m.update_power_display(); m.pm_lock.release()
check("display skips a tick while the meter is busy", len(pm.reads) == before)
ui.pmWavelength.setValue(1030); m.set_pm_wavelength()
check("wavelength box sets the meter", pm.wavelength == 1030 and ui.pmWavelength.value() == 1030)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
m.zero_power_meter()
check("zero cancelled: meter untouched", pm.zero_calls == 0)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
ui.PM_realDisp.setChecked(True)
m.zero_power_meter()
check("zero confirmed: zeroed once, waited for it, live display back on",
      pm.zero_calls == 1 and not pm.get_zero_state() and m.pm_timer.isActive() and ui.pmZero.isEnabled())
m.powermeter = FakePM(mount, fail=True)
m.update_power_display()
check("read error: display shows error, stops, Realtime released",
      ui.PowerMeterDisp.text() == "error" and not m.pm_timer.isActive() and not ui.PM_realDisp.isChecked())
ui.activePowerMeter.setChecked(True)
m.closeInstruments(only_active=True)
check("close: meter dropped, LED off, display reset",
      m.powermeter is None and not ui.PMLed.status and ui.PowerMeterDisp.text() == "-- mW")

# 11. PM config tab: wavelength limits and power ranges come from the meter
pm = FakePM(FakeMount(2))
pm.wavelength = 525.0  # the meter was left on another wavelength
ui.pmWavelength.setValue(800)
m.load_pm_settings(pm)
items = [ui.pmRange.itemText(i) for i in range(ui.pmRange.count())]
check(f"range choices are the meter's real ranges at 800 nm {items}",
      items == ["Auto", "3.695 mW", "34.99 mW", "347.9 mW", "3.477 W"])
check("meter on auto -> Auto shown; the meter is back on auto and its error queue is empty after the walk",
      ui.pmRange.currentIndex() == 0 and pm.auto and not pm.errors)
check("wavelength box limited to the sensor (185 .. 20000 nm); its 800 nm is sent to the meter on connect",
      (ui.pmWavelength.minimum(), ui.pmWavelength.maximum(), ui.pmWavelength.value()) == (185, 20000, 800)
      and pm.wavelength == 800)
m.powermeter = pm
ui.pmRange.setCurrentIndex(2)
check("choosing 34.99 mW fixes exactly that range (not the next one up)",
      not pm.auto and pm.get_power_range_upper() == FakePM.RANGES[800][1])
ui.pmWavelength.setValue(1030); m.set_pm_wavelength()
items = [ui.pmRange.itemText(i) for i in range(ui.pmRange.count())]
check(f"new wavelength -> ranges read again {items}, the fixed range kept",
      items == ["Auto", "3.752 mW", "35.53 mW", "353.3 mW", "3.531 W"] and ui.pmRange.currentIndex() == 2
      and not pm.auto and pm.idx == 1 and not pm.errors)
ui.pmRange.setCurrentIndex(0)
check("choosing Auto switches the meter back to auto range", pm.auto)
pm2 = FakePM(FakeMount(2), auto=False, range_index=2)
m.powermeter = None
ui.pmWavelength.setValue(800)
m.load_pm_settings(pm2)
check("meter on a fixed range -> that range shown and restored on the meter after the walk",
      ui.pmRange.currentText() == "347.9 mW" and not pm2.auto and pm2.idx == 2 and not pm2.errors)
m.powermeter = None

# 12. PM_realDisp: live display only while pressed and connected; usable during a scan
ns["PM100D"] = lambda resource, timeout_ms=3000: FakePM(FakeMount(2))  # what Conn. Instr. creates
for box in ("activeLockin1", "activeLockin2", "activeStage1", "activeStage2", "activeRot1", "activeRot2",
            "activeRot3", "activeiTC", "activeFlipMount"):
    getattr(ui, box).setChecked(False)
ui.activePowerMeter.setChecked(True)
ui.PM_realDisp.setChecked(False)
m.connectInstruments()
check("connected, Realtime released: no live reading", m.powermeter is not None and not m.pm_timer.isActive())
ui.PM_realDisp.setChecked(True)
check("Realtime pressed: live display runs", m.pm_timer.isActive())
for _ in range(80):
    app.processEvents(); time.sleep(0.01)
check(f"display updated while pressed ({ui.PowerMeterDisp.text()!r})", ui.PowerMeterDisp.text().endswith(" mW")
      and ui.PowerMeterDisp.text() != "-- mW")
ui.PM_realDisp.setChecked(False)
check("Realtime released: stopped, display shows --", not m.pm_timer.isActive() and ui.PowerMeterDisp.text() == "-- mW")
m.closeInstruments(only_active=True)
ui.PM_realDisp.setChecked(True)
check("pressed while not connected: nothing runs yet", m.powermeter is None and not m.pm_timer.isActive())
m.connectInstruments()
check("connecting with Realtime pressed starts the display", m.pm_timer.isActive())
m.set_ControlsEnabledDuringScan(True)
check("during a scan Realtime stays usable, Zero / Record / settle are locked",
      ui.PM_realDisp.isEnabled() and not ui.pmZero.isEnabled() and not ui.pmRecord.isEnabled() and not ui.pmSettle.isEnabled())
m.set_ControlsEnabledDuringScan(False)
m.closeInstruments(only_active=True)
check("close stops the display", m.powermeter is None and not m.pm_timer.isActive())
ui.PM_realDisp.setChecked(False)

print(f"{SYSTEM}: {sum(ok for _, ok in results)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)
