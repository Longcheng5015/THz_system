"""Native Qt checks for display-only terminal mirroring and unchanged ScanLog."""
import io
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = ROOT / 'OPTP_system_iTC_v4.01.py'
source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'live_progress_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)
from PySide6.QtCore import QObject, QPoint, QSettings, QThread, Qt, Slot
from PySide6.QtWidgets import QApplication, QTabWidget
app = QApplication.instance() or QApplication([])

# The original ScanLog widget, including tooltip and readOnly state, is untouched.
def signature(node):
    return node.tag, node.attrib, (node.text or '').strip(), tuple(signature(c) for c in node)
old = ET.parse(ROOT / 'OPTP_iTC_main_v4.0.ui').find(".//widget[@name='ScanLog']")
new = ET.parse(ROOT / 'OPTP_iTC_main_v4.01.ui').find(".//widget[@name='ScanLog']")
assert signature(old) == signature(new)
print('PASS original ScanLog widget properties and contents preserved')

with tempfile.TemporaryDirectory(prefix='optp_live_progress_') as tmp:
    folder = Path(tmp)
    ns['QSettings'] = lambda org, name: QSettings(str(folder / f'{org}.{name}.ini'), QSettings.IniFormat)
    def setup_folder(self):
        self.dataSave_path = str(folder)
        self.ui.dataSavePath.setText(str(folder))
    ns['moSys'].setup_data_folder = setup_folder
    m = ns['moSys']()
    ui = m.ui
    ui.setAttribute(Qt.WA_DontShowOnScreen, True)
    ui.resize(1661, 973)
    for tabs in ui.findChildren(QTabWidget):
        if tabs.indexOf(ui.tab_2) >= 0:
            tabs.setCurrentWidget(ui.tab_2)
    ui.show()
    app.processEvents()
    for size in ((1661, 973), (1800, 1100)):
        ui.resize(*size)
        app.processEvents()
        assert abs(ui.ScanLog.height() - ui.scanProgressGroup.height()) <= 1
        assert ui.ScanLog.width() == ui.scanProgressGroup.width()
        assert ui.scanProgressGroup.mapTo(ui, QPoint()).y() >= ui.ScanLog.mapTo(ui, QPoint()).y() + ui.ScanLog.height()
    assert ui.scanProgressText.isReadOnly() and ui.scanLogText.isReadOnly()
    assert ui.scanProgressText.maximumBlockCount() == 1000
    print('PASS equal-height stacked log boxes, readonly progress and bounded history')

    gui_threads = []
    class Observer(QObject):
        @Slot()
        def changed(self): gui_threads.append(QThread.currentThread())
    observer = Observer()
    ui.scanProgressText.textChanged.connect(observer.changed)
    m.is_custom_save_path = True
    m.check_instruments_ready = lambda: []
    m.prepare_scan_plan = lambda: {}
    m.drift_comp_active = lambda: False
    m.auto_block_after_scan = lambda thread: print('DISPLAY_ONLY cleanup')
    seen_log = ''
    for mode in ('success', 'stop', 'error'):
        started, release = threading.Event(), threading.Event()
        out, err = io.StringIO(), io.StringIO()
        normal_out, normal_err = sys.stdout, sys.stderr
        def worker(thread):
            print(f'DISPLAY_ONLY {mode} ', end='')
            print('partial line', flush=True)
            helper = threading.Thread(target=lambda: print('DISPLAY_ONLY helper thread'))
            helper.start(); helper.join()
            print('DISPLAY_ONLY stderr', file=sys.stderr)
            thread.scan_log.emit(f'KEY_EVENT {mode}')
            started.set()
            if not release.wait(5): raise RuntimeError('test release timeout')
            if mode == 'error': raise RuntimeError('SIMULATED_PROGRESS_ERROR')
        m._execute_scan_logic = worker
        sys.stdout, sys.stderr = out, err
        try:
            m.runScan()
            assert started.wait(2)
            deadline = time.monotonic() + 2
            while 'DISPLAY_ONLY stderr' not in ui.scanProgressText.toPlainText() and time.monotonic() < deadline:
                app.processEvents(); time.sleep(0.01)
            text = ui.scanProgressText.toPlainText()
            assert f'DISPLAY_ONLY {mode} partial line' in text
            assert 'DISPLAY_ONLY helper thread' in text and 'DISPLAY_ONLY stderr' in text
            assert f'DISPLAY_ONLY {mode} partial line' in out.getvalue() and 'DISPLAY_ONLY stderr' in err.getvalue()
            if mode != 'success': assert 'DISPLAY_ONLY success' not in text
            assert all(t == app.thread() for t in gui_threads)
            if mode == 'stop': m.scan_Thread.request_stop()
            release.set()
            deadline = time.monotonic() + 3
            while (m.scan_Thread.isRunning() or m._progress_streams) and time.monotonic() < deadline:
                app.processEvents(); time.sleep(0.01)
            assert m.scan_Thread.wait(1000)
            app.processEvents(); app.processEvents()
            assert not m._progress_streams and sys.stdout is out and sys.stderr is err
            if mode == 'error':
                assert 'Traceback' in ui.scanProgressText.toPlainText()
                assert 'SIMULATED_PROGRESS_ERROR' in ui.scanProgressText.toPlainText()
            else:
                assert 'Scan finished' in ui.scanProgressText.toPlainText()
            log = Path(m._scan_log_path).read_text(encoding='utf-8')
            assert log.startswith(seen_log) and f'KEY_EVENT {mode}' in log
            assert ui.scanLogText.toPlainText().strip() == log.strip()
            assert 'DISPLAY_ONLY' not in log
            seen_log = log
            before = ui.scanProgressText.toPlainText()
            print('AFTER_SCAN_NOT_CAPTURED')
            app.processEvents()
            assert ui.scanProgressText.toPlainText() == before
        finally:
            release.set()
            if m.scan_Thread.isRunning():
                m.scan_Thread.request_stop()
                assert m.scan_Thread.wait(4000)
            app.processEvents()
            m.stop_scan_progress()
            sys.stdout, sys.stderr = normal_out, normal_err
        print(f'PASS {mode}: live mirroring, terminal retention, GUI thread, ScanLog persistence, stream restoration')

    assert len(list(folder.glob('ScanLog_*.txt'))) == 1
    assert not [p for p in folder.iterdir() if p.suffix not in ('.ini', '.txt')]
    m.append_scan_progress(''.join(f'line {i}\n' for i in range(1100)))
    assert ui.scanProgressText.document().blockCount() <= 1000
    assert 'line 1099' in ui.scanProgressText.toPlainText() and 'line 0\n' not in ui.scanProgressText.toPlainText()
    assert Path(m._scan_log_path).read_text(encoding='utf-8') == seen_log
    print('PASS no progress file, memory history capped without changing ScanLog')
    preview = Path(tempfile.gettempdir()) / 'optp_v401_live_progress.png'
    ui.grab().save(str(preview))
    print(f'Preview: {preview}')
    ui.close()
print('All live progress checks passed.')
