"""Native Qt checks for OPTP v4.2: always-on Live Process box below ScanLog.

The console mirror is installed when moSys is built and stays until the application's aboutToQuit;
it is not cleared between scans. A Realtime lock-in update adds nothing to it.

    python OPTP_System/tests/test_v42_live_process.py
"""
import io
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = ROOT / 'OPTP_system_iTC_v4.2.py'
REAL = sys.__stdout__


def report(msg):  # results go straight to the real console, not through the mirror
    REAL.write(msg + "\n")
    REAL.flush()


source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'live_process_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)
from PySide6.QtCore import QObject, QPoint, QSettings, QThread, Qt, Slot
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])


def signature(node):
    return node.tag, node.attrib, (node.text or '').strip(), tuple(signature(c) for c in node)


old = ET.parse(ROOT / 'OPTP_iTC_main_v4.1.ui').find(".//widget[@name='ScanLog']")
new = ET.parse(ROOT / 'OPTP_iTC_main_v4.2.ui').find(".//widget[@name='ScanLog']")
assert signature(old) == signature(new)
report('PASS original ScanLog widget properties and contents preserved')


def pump(until, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not until() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return until()


with tempfile.TemporaryDirectory(prefix='optp_live_process_') as tmp:
    folder = Path(tmp)
    ns['QSettings'] = lambda org, name: QSettings(str(folder / f'{org}.{name}.ini'), QSettings.IniFormat)

    def setup_folder(self):
        self.dataSave_path = str(folder)
        self.ui.dataSavePath.setText(str(folder))
    ns['moSys'].setup_data_folder = setup_folder

    out, err = io.StringIO(), io.StringIO()  # stand-ins for the terminal
    sys.stdout, sys.stderr = out, err
    try:
        m = ns['moSys']()
        ui = m.ui
        box = ui.scanProgressText

        # ---- layout ----
        ui.setAttribute(Qt.WA_DontShowOnScreen, True)
        ui.resize(1661, 973)
        tabs = ui.tab_2.parentWidget().parentWidget()
        tabs.setCurrentWidget(ui.tab_2)
        ui.show()
        app.processEvents()
        for size in ((1661, 973), (1800, 1100)):
            ui.resize(*size)
            app.processEvents()
            assert abs(ui.ScanLog.height() - ui.scanProgressGroup.height()) <= 1
            assert ui.ScanLog.width() == ui.scanProgressGroup.width()
            assert ui.scanProgressGroup.mapTo(ui, QPoint()).y() >= ui.ScanLog.mapTo(ui, QPoint()).y() + ui.ScanLog.height()
            report(f'  window {size}: ScanLog {ui.ScanLog.width()}x{ui.ScanLog.height()}, '
                   f'Live Process {ui.scanProgressGroup.width()}x{ui.scanProgressGroup.height()}')
        assert ui.scanProgressGroup.title() == 'Live Process'
        assert 'since it started' in box.toolTip() and '1000 lines' in box.toolTip()
        assert box.isReadOnly() and ui.scanLogText.isReadOnly() and not box.isUndoRedoEnabled()
        assert box.maximumBlockCount() == 1000
        report('PASS Live Process title/tooltip, equal-height stacked boxes, readonly, 1000-line cap')

        # ---- startup output (printed inside moSys.__init__) ----
        startup = [line for line in out.getvalue().splitlines() if line.strip()]
        assert startup, 'moSys() printed nothing at startup'
        assert pump(lambda: all(line in box.toPlainText() for line in startup))
        report(f'PASS startup prints shown ({len(startup)} lines, e.g. {startup[0][:50]!r})')

        gui_threads = []

        class Observer(QObject):
            @Slot()
            def changed(self):
                gui_threads.append(QThread.currentThread())
        observer = Observer()
        box.textChanged.connect(observer.changed)

        # ---- idle output, no scan running ----
        print('IDLE_MARK gui ', end='')
        print('partial line', flush=True)
        t = threading.Thread(target=lambda: print('IDLE_MARK helper thread'))
        t.start()
        t.join()
        print('IDLE_MARK stderr', file=sys.stderr)
        assert pump(lambda: 'IDLE_MARK stderr' in box.toPlainText())
        text = box.toPlainText()
        assert 'IDLE_MARK gui partial line' in text and 'IDLE_MARK helper thread' in text
        assert 'IDLE_MARK gui partial line' in out.getvalue() and 'IDLE_MARK stderr' in err.getvalue()
        report('PASS idle prints (GUI thread, helper thread, stderr) shown and kept on the terminal')

        # ---- Realtime lock-in display adds nothing to the console or the box ----
        class FakeLockin:
            def get_x(self):
                return 2.5e-6
        m.lockin1 = FakeLockin()
        app.processEvents()
        before_out, before_box = out.getvalue(), box.toPlainText()
        for _ in range(5):
            m.chart_updaters['realDisChart1'].update()
        app.processEvents()
        assert out.getvalue() == before_out and box.toPlainText() == before_box
        assert ui.realDisChart1Num.text() == '2.5000e-06'
        m.lockin1 = None
        report('PASS Realtime lock-in updates print nothing; number box shows 2.5000e-06')

        # ---- Realtime without a lock-in: the warning is printed once per switch-on ----
        upd = m.chart_updaters['realDisChart1']
        m.lockin1 = None
        app.processEvents()
        before_out = out.getvalue()
        before_box = box.toPlainText().count("Warning: Lockin device 'lockin1' is not connected")
        upd.toggle(True)
        upd.timer.stop()  # drive update() by hand instead of the timer
        for _ in range(5):
            upd.update()
        upd.toggle(False)
        upd.toggle(True)
        upd.timer.stop()
        for _ in range(3):
            upd.update()
        upd.toggle(False)
        warnings = out.getvalue()[len(before_out):].count("Warning: Lockin device 'lockin1' is not connected")
        assert warnings == 2, warnings
        assert pump(lambda: box.toPlainText().count("Warning: Lockin device 'lockin1' is not connected") == before_box + 2)
        report('PASS missing lock-in warning printed once per Realtime switch-on (2 for 8 updates in 2 switch-ons)')

        # ---- scans: not cleared at start, mirror stays installed afterwards ----
        m.is_custom_save_path = True
        m.check_instruments_ready = lambda: []
        m.prepare_scan_plan = lambda: {}
        m.drift_comp_active = lambda: False
        m.auto_block_after_scan = lambda thread: print('DISPLAY_ONLY cleanup')
        mirror_out, mirror_err = sys.stdout, sys.stderr
        assert mirror_out is not out and mirror_err is not err
        seen_log = ''
        for mode in ('success', 'stop', 'error'):
            started, release = threading.Event(), threading.Event()

            def worker(thread):
                print(f'DISPLAY_ONLY {mode} ', end='')
                print('partial line', flush=True)
                helper = threading.Thread(target=lambda: print('DISPLAY_ONLY helper thread'))
                helper.start()
                helper.join()
                print('DISPLAY_ONLY stderr', file=sys.stderr)
                thread.scan_log.emit(f'KEY_EVENT {mode}')
                started.set()
                if not release.wait(5):
                    raise RuntimeError('test release timeout')
                if mode == 'error':
                    raise RuntimeError('SIMULATED_PROGRESS_ERROR')
            m._execute_scan_logic = worker
            try:
                m.runScan()
                assert started.wait(2)
                assert pump(lambda: f'DISPLAY_ONLY {mode} partial line' in box.toPlainText()
                            and 'DISPLAY_ONLY stderr' in box.toPlainText())
                text = box.toPlainText()
                assert 'IDLE_MARK gui partial line' in text  # not cleared when a scan starts
                assert 'DISPLAY_ONLY helper thread' in text
                assert f'DISPLAY_ONLY {mode} partial line' in out.getvalue()
                if mode == 'stop':
                    m.scan_Thread.request_stop()
                release.set()
                assert pump(lambda: not m.scan_Thread.isRunning(), 3) and m.scan_Thread.wait(1000)
                app.processEvents()
                app.processEvents()
                if mode == 'error':
                    assert pump(lambda: 'SIMULATED_PROGRESS_ERROR' in box.toPlainText())
                    assert 'Traceback' in box.toPlainText()
                else:
                    assert pump(lambda: 'Scan finished' in box.toPlainText())
                assert sys.stdout is mirror_out and sys.stderr is mirror_err  # still installed
                print(f'AFTER_SCAN_{mode}')
                assert pump(lambda: f'AFTER_SCAN_{mode}' in box.toPlainText())  # still captured
                log = Path(m._scan_log_path).read_text(encoding='utf-8')
                assert log.startswith(seen_log) and f'KEY_EVENT {mode}' in log
                assert ui.scanLogText.toPlainText().strip() == log.strip()
                assert 'DISPLAY_ONLY' not in log and 'IDLE_MARK' not in log
                seen_log = log
            finally:
                release.set()
                if m.scan_Thread.isRunning():
                    m.scan_Thread.request_stop()
                    assert m.scan_Thread.wait(4000)
                app.processEvents()
            report(f'PASS {mode}: shown live, earlier text kept, mirror still on after the scan, ScanLog file unchanged')
        assert all(t == app.thread() for t in gui_threads), 'Live Process updated off the GUI thread'
        report(f'PASS all {len(gui_threads)} Live Process updates ran on the GUI thread')

        assert len(list(folder.glob('ScanLog_*.txt'))) == 1
        assert not [p for p in folder.iterdir() if p.suffix not in ('.ini', '.txt')]
        m.append_console_text(''.join(f'line {i}\n' for i in range(1100)))
        assert box.document().blockCount() <= 1000
        assert 'line 1099' in box.toPlainText() and 'line 0\n' not in box.toPlainText()
        assert Path(m._scan_log_path).read_text(encoding='utf-8') == seen_log
        report('PASS no extra files, history capped at 1000 lines, ScanLog unchanged')

        ui.resize(1661, 973)
        app.processEvents()
        preview = Path(tempfile.gettempdir()) / 'optp_v42_live_process.png'
        ui.grab().save(str(preview))
        report(f'Preview: {preview}')

        # ---- quit: streams handed back to the terminal ----
        app.aboutToQuit.emit()
        assert sys.stdout is out and sys.stderr is err
        before = box.toPlainText()
        print('AFTER_QUIT_NOT_SHOWN')
        app.processEvents()
        assert box.toPlainText() == before and 'AFTER_QUIT_NOT_SHOWN' in out.getvalue()
        report('PASS aboutToQuit restores stdout/stderr; later prints only reach the terminal')
        ui.close()
    finally:
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
report('All Live Process checks passed.')
