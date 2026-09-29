"""OPTP image v1.5: XY image scans (THz_Scan / 2D_IMG / 1D_THz), POL_2D loop order, TDS chart and live XY image.

X / Y linear stages sit on Rotary1 / Rotary2 (Independent mode = XY grid). Headless, fake instruments,
QSettings in a temp ini file, data in a temp folder.

    python OPTP_System/tests/test_image_modes.py        (run with the opto_test conda env)
"""
import os, sys, tempfile, time, glob
os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SYS_DIR = os.path.join(ROOT, "OPTP_image_System")
SRC = os.path.join(SYS_DIR, "OPTP_iTC_image_v1.5.py")
os.chdir(SYS_DIR); sys.path.insert(0, SYS_DIR)
import numpy as np, h5py
from PySide6.QtCore import QSettings
TMP = tempfile.mkdtemp()
src = open(SRC, encoding="utf-8").read()
src = src[: src.rindex("app = QApplication()")]
ns = {"__file__": SRC, "__name__": "img15"}
exec(compile(src, SRC, "exec"), ns)
ns['QSettings'] = lambda org, app: QSettings(os.path.join(TMP, "x.ini"), QSettings.IniFormat)
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

READS = []
results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name)


class Linear:
    def __init__(self, hi=25.0): self.pos = 0.0; self.hi = hi
    def move_to(self, p): self.pos = p
    def position(self): return self.pos
    def travel_limits(self): return (0.0, self.hi)
    def close(self): pass


class Lockin:
    stop_at = None           # press Stop from the scan thread at this read
    def get_x(self):
        READS.append((m.rotary1.pos, m.rotary2.pos, m.stage1.pos, m.stage2.pos))
        if self.stop_at is not None and len(READS) == self.stop_at:
            m.scan_Thread.request_stop()
        return m.rotary1.pos * 100 + m.rotary2.pos * 10 + (m.stage1.pos - 110.0) * 1000 + (m.stage2.pos - 117.3) * 100
    def get_y(self): return 0.0
    def close(self): pass


m = ns['moSys'](); ui = m.ui
m.dataSave_path = TMP
check("combobox modes are THz_Scan, 1D_THz, POL_2D, 2D_THz, 2D_IMG",
      [ui.scanMode.itemText(i) for i in range(ui.scanMode.count())] == ['THz_Scan', '1D_THz', 'POL_2D', '2D_THz', '2D_IMG'])
tip = ui.scanMode.toolTip()
check("scanMode tooltip names the same five modes and the XY grid",
      all(f"'{n}'" in tip for n in ('THz_Scan', '1D_THz', 'POL_2D', '2D_THz', '2D_IMG')) and 'XY image' in tip
      and 'POL_1D' not in tip and '1D_Scan' not in tip and 'TDS_Scan' not in tip)

for box in ("activeLockin1", "activeLockin2", "activeStage1", "activeStage2", "activeRot1", "activeRot2",
            "activeRot3", "activeiTC", "activeFlipMount", "ScanT", "AutoBlock"):
    getattr(ui, box).setChecked(False)
ui.activeLockin1.setChecked(True); m.lockin1 = Lockin()
ui.activeStage1.setChecked(True); m.stage1 = Linear(220.0)
ui.activeStage2.setChecked(True); m.stage2 = Linear(220.0)
ui.activeRot1.setChecked(True); m.rotary1 = Linear()
ui.activeRot2.setChecked(True); m.rotary2 = Linear()
ui.wait1.setValue(0); ui.wait2.setValue(0)
ui.iPos1.setValue(110.0); ui.iPos2.setValue(117.3)
ui.stage1Step2NO.setValue(0); ui.stage1Step3NO.setValue(0); ui.stage2Step2NO.setValue(0); ui.stage2Step3NO.setValue(0)
ui.iRot1.setValue(1.0); ui.rotary1Step.setValue(0.5); ui.rotary1StepNO.setValue(3)     # X 1.0 / 1.5 / 2.0
ui.iRot2.setValue(2.0); ui.rotary2Step.setValue(0.2); ui.rotary2StepNO.setValue(4)     # Y 2.0 .. 2.6
ui.scanRepNO1.setValue(1); ui.scanRepNO2.setValue(1); ui.ScanRepNO_R1.setValue(1); ui.ScanRepNO_R2.setValue(1)
ui.Rot_stages_couple.setChecked(False)

tds = []
m.update_TDS_FDS_chart = lambda d: tds.append(d)
GRID = [(x, y) for x in (1.0, 1.5, 2.0) for y in (2.0, 2.2, 2.4, 2.6)]


def run(mode, s1_no, s2_no):
    READS.clear(); tds.clear()
    for f in glob.glob(os.path.join(TMP, "*.h5")): os.remove(f)
    ui.stage1Step1.setValue(1); ui.stage1Step1NO.setValue(s1_no)
    ui.stage2Step1.setValue(10); ui.stage2Step1NO.setValue(s2_no)
    ui.scanMode.setCurrentText(mode)
    m.runScan(); t0 = time.time()
    while m.scan_Thread.isRunning() or time.time() - t0 < 0.3:
        app.processEvents(); time.sleep(0.005)
    for _ in range(40):
        app.processEvents(); time.sleep(0.005)
    files = glob.glob(os.path.join(TMP, "*.h5"))
    if not files:
        return None
    with h5py.File(files[0], 'r') as h:
        return h['lockin1_X'][()]


def image():
    """Image currently drawn (nx, ny), or None when the chart is empty."""
    return None if m.img_item.image is None else np.array(m.img_item.image)


def set_view(channel, metric, point=1):
    ui.imgChannel.setCurrentText(channel); ui.imgMetric.setCurrentText(metric); ui.imgPoint.setValue(point)
    app.processEvents()


def grid_order():
    g = []
    for r in READS:
        k = (round(r[0], 3), round(r[1], 3))
        if not g or g[-1] != k: g.append(k)
    return g


# XY image with a full TDS at every grid point
for mode in ('THz_Scan', '2D_IMG'):
    d = run(mode, 5, 1)
    check(f"{mode} XY image: X slow / Y fast, a 5-point TDS at every grid point, data (5,1,1,1,12,1)",
          grid_order() == GRID and len(READS) == 60 and d.shape == (5, 1, 1, 1, 12, 1)
          and np.allclose(d[4, 0, 0, 0, 7, 0], 1.5 * 100 + 2.6 * 10 + 4.0))
    check(f"{mode}: TDS chart {'once per grid point, 5-point traces' if mode == 'THz_Scan' else 'not used'}",
          (len(tds) == 12 and {len(t['tds_x']) for t in tds} == {5}) if mode == 'THz_Scan' else not tds)

# live XY image after the 2D_IMG run above (3 x 4 grid, 5-point TDS per point)
XS, YS = np.array([1.0, 1.5, 2.0]), np.array([2.0, 2.2, 2.4, 2.6])
base = XS[:, None] * 100 + YS[None, :] * 10
check("image grid: 3 x 4, X = Rotary1 positions, Y = Rotary2 positions, all 12 pixels measured",
      m.img_grid['nx'] == 3 and m.img_grid['ny'] == 4 and np.allclose(m.img_grid['x'], XS)
      and np.allclose(m.img_grid['y'], YS) and len(m.img_blocks) == 12)
set_view('L1 X', 'Max')
check("pixel Max(L1 X) of each grid point is right", image() is not None and np.allclose(image(), base + 4.0))
set_view('L1 X', 'Peak-Peak')
check("Peak-Peak(L1 X) = 4 everywhere (TDS span of the fake signal)", np.allclose(image(), 4.0))
set_view('L1 X', 'At point', 1)
check("At point 1 = first TDS point; the point box is only enabled for 'At point'",
      np.allclose(image(), base) and ui.imgPoint.isEnabled())
set_view('L2 X', 'Mean')
check("channel switch redraws at once (Lock-in 2 not used -> 0); point box disabled again",
      np.allclose(image(), 0.0) and not ui.imgPoint.isEnabled())
r = m.img_item.mapRectToParent(m.img_item.boundingRect())
check("image placed in stage coordinates: X 0.75 .. 2.25 mm, Y 1.9 .. 2.7 mm",
      np.allclose([r.left(), r.right(), r.top(), r.bottom()], [0.75, 2.25, 1.9, 2.7]))
m.set_ControlsEnabledDuringScan(True)
check("during a scan the image channel / metric stay enabled, Run is disabled",
      ui.imgChannel.isEnabled() and ui.imgMetric.isEnabled() and not ui.runButton.isEnabled())
m.set_ControlsEnabledDuringScan(False)
set_view('L1 X', 'Max')

# live update: stop after 32 reads -> 6 grid points complete, the rest of the image stays empty
m.lockin1.stop_at = 32
run('THz_Scan', 5, 1)
m.lockin1.stop_at = None
img = image()
check("live update: after 6 of 12 grid points the image has exactly those 6 pixels, the others empty",
      img is not None and np.isfinite(img).sum() == 6
      and np.allclose([img[0, 0], img[0, 3], img[1, 1]], [base[0, 0] + 4, base[0, 3] + 4, base[1, 1] + 4])
      and np.isnan(img[1, 2]))

# 1D pump-probe image: stage1 fixed at the peak, stage2 trace at every grid point
d = run('1D_THz', 1, 5)
check("1D_THz XY image: stage1 fixed, a 5-point stage2 trace at every grid point, data (1,1,5,1,12,1)",
      grid_order() == GRID and len(READS) == 60 and {round(r[2], 3) for r in READS} == {110.0}
      and d.shape == (1, 1, 5, 1, 12, 1) and np.allclose(d[0, 0, 3, 0, 6, 0], 1.5 * 100 + 2.4 * 10 + 3.0))
check("1D_THz: TDS chart shows the stage2 trace once per grid point (12 x 5 points)",
      len(tds) == 12 and {len(t['tds_x']) for t in tds} == {5} and tds[0]['tds_x'][0] == 117.3)
set_view('L1 X', 'Max')
check("1D_THz image: pixel = max of the stage2 trace", np.allclose(image(), base + 4.0))

# Coupled mode: X and Y step together -> one row (coupled needs equal step NOs on all three rotaries,
# the unticked Rotary3 included)
ui.Rot_stages_couple.setChecked(True); ui.rotary2StepNO.setValue(3); ui.rotary3StepNO.setValue(3)
run('THz_Scan', 5, 1)
check("Coupled: image is one row of 3 pixels", m.img_grid['nx'] == 3 and m.img_grid['ny'] == 1
      and image().shape == (3, 1) and np.isfinite(image()).all())
ui.Rot_stages_couple.setChecked(False); ui.rotary2StepNO.setValue(4); ui.rotary3StepNO.setValue(1)

# POL_2D: rotation stages innermost at each stage2 point, polar chart fed
ui.activeRot1.setChecked(False); ui.rotary1StepNO.setValue(1)   # an unticked rotary still multiplies N_pol by its step NO
ui.iRot2.setValue(0.0); ui.rotary2Step.setValue(10); ui.rotary2StepNO.setValue(36)
m.rotary2.hi = 360.0
d = run('POL_2D', 1, 2)
angles = [round(r[1], 3) for r in READS]
check("POL_2D: 36 angles swept at each of the 2 stage2 points (rotation innermost)",
      angles == [float(10 * i) for i in range(36)] * 2 and [round(r[3], 3) for r in READS[:36]] == [117.3] * 36)
check("POL_2D: no XY image (chart cleared)", m.img_grid is None and image() is None)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
