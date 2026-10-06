"""Native Qt naming checks with isolated settings/files and no hardware."""
import hashlib
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = ROOT / 'OPTP_system_iTC_v4.01.py'
source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'naming_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)
from PySide6.QtCore import QObject, QSettings, QThread, Qt, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
class Clock(datetime):
    value = datetime(2026, 10, 6, 12, 0, 0)
    @classmethod
    def now(cls): return cls.value
ns['datetime'] = Clock
warnings = []
QMessageBox.warning = staticmethod(lambda *args: warnings.append(args[-1]))
with tempfile.TemporaryDirectory(prefix='optp_naming_') as tmp:
    folder = Path(tmp)
    ns['QSettings'] = lambda org, name: QSettings(str(folder / f'{org}.{name}.ini'), QSettings.IniFormat)
    def setup_folder(self):
        self.dataSave_path = str(folder)
        self.ui.dataSavePath.setText(str(folder))
    ns['moSys'].setup_data_folder = setup_folder
    m = ns['moSys']()
    ui = m.ui
    ui.setAttribute(Qt.WA_DontShowOnScreen, True)
    ui.show()
    app.processEvents()
    ui.scanMode.setCurrentText('1D_THz')
    ui.ext_info.setText('sample:one')
    first_text = ui.dataFileName.text()
    first = Path(m.save_ui_screenshot())
    second = Path(m.save_ui_screenshot())
    assert first != second and not QImage(str(first)).isNull() and not QImage(str(second)).isNull()
    assert '_screenshot_20261006_120000_000000' in first.stem
    assert second.stem.endswith('_2') and ui.dataFileName.text() == first_text
    print('PASS capture timestamp and same-timestamp collision create separate valid images')

    old_data = folder / 'old scan' / '11h00m00s_1D_THz_sample.h5'
    old_data.parent.mkdir()
    old_data.write_bytes(b'measurement placeholder')
    data_hash = hashlib.sha256(old_data.read_bytes()).hexdigest()
    m.fullFilePath = str(old_data)
    Clock.value = datetime(2026, 10, 6, 12, 1, 0)
    associated = Path(m.save_ui_screenshot())
    assert associated.parent == old_data.parent and associated.stem.startswith(old_data.stem + '_screenshot_20261006_120100')
    assert hashlib.sha256(old_data.read_bytes()).hexdigest() == data_hash
    print('PASS capture retains latest data association with current screenshot time')

    # Pause a real scan worker in preparation, before it can generate a data filename.
    started, release = threading.Event(), threading.Event()
    worker_names, gui_threads = [], []
    class Observer(QObject):
        @Slot(str)
        def changed(self, text): gui_threads.append(QThread.currentThread())
    observer = Observer()
    ui.dataFileName.textChanged.connect(observer.changed)
    m.is_custom_save_path = True
    m.check_instruments_ready = lambda: []
    m.prepare_scan_plan = lambda: {}
    m.drift_comp_active = lambda: False
    m.auto_block_after_scan = lambda thread: None
    def worker(thread):
        started.set()
        if not release.wait(3): raise RuntimeError('test preparation timeout')
        worker_names.append(m.setup_dataFile_Name('1D_THz', thread))
    m._execute_scan_logic = worker
    Clock.value = datetime(2026, 10, 6, 12, 2, 0)
    try:
        m.runScan()
        assert started.wait(1)
        assert ui.dataFileName.text() == '12h02m00s' and m.fullFilePath is None
        assert ui.saveScreenshot.isEnabled()
        preparation_png = Path(m.save_ui_screenshot())
        assert preparation_png.parent == folder and preparation_png.stem.startswith('12h02m00s_1D_THz_sample_one_screenshot_')
        print('PASS scan start immediately refreshes Save Name and preparation screenshot avoids old scan')
        Clock.value = datetime(2026, 10, 6, 12, 3, 0)
        release.set()
        deadline = time.monotonic() + 3
        while m.scan_Thread.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert m.scan_Thread.wait(1000)
        app.processEvents()
        assert worker_names == ['12h03m00s_1D_THz_sample_one']
        assert ui.dataFileName.text() == '12h03m00s'
        assert gui_threads and all(t == app.thread() for t in gui_threads)
        print('PASS file-creation timestamp reaches Save Name exclusively on the GUI thread')
    finally:
        release.set()
        m.scan_Thread.request_stop()
        assert m.scan_Thread.wait(4000)
        app.processEvents()

    # A failed image encoder must leave every previous screenshot intact.
    previous = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*.png')}
    class FailedPixmap:
        def isNull(self): return False
        def save(self, device, format):
            device.write(b'partial')
            return False
    original_grab = ui.grab
    ui.grab = lambda: FailedPixmap()
    try:
        assert m.save_ui_screenshot() is None and warnings
        assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in previous.items())
        assert len(list(folder.rglob('*.png'))) == len(previous)
        print('PASS failed screenshot preserves previous images and leaves no partial PNG')
    finally:
        ui.grab = original_grab
        ui.close()
print('All v4.01 naming checks passed.')
