"""Native Qt checks for the Live Process file (OPTP v4.3, THz Emission v1.8).

Everything the Live Process box shows is also appended at once to LiveProcess_YYYY-MM-DD.txt in the
data folder, from program start until it quits.

    python OPTP_System/tests/test_v43_live_process_file.py [path to the GUI .py, default OPTP v4.3]

No hardware. QSettings and the data folder go to a temporary directory.
"""
import io
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'OPTP_system_iTC_v4.3.py'
sys.path.insert(0, str(SRC.parent))
REAL = sys.__stdout__


def report(msg):  # results go straight to the real console, not through the mirror
    REAL.write(msg + "\n")
    REAL.flush()


source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'live_process_file_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
report(f'GUI under test: {SRC.name}')

TODAY = f'{datetime.now():%Y-%m-%d}'
HEADER = '=' * 72


def pump(until, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not until() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return until()


terminal = []  # everything the mirror passes on to the terminal, stdout and stderr in order


class Terminal(io.StringIO):
    def write(self, text):
        terminal.append(text)
        return super().write(text)


with tempfile.TemporaryDirectory(prefix='live_process_file_') as tmp:
    folder = Path(tmp)
    ns['QSettings'] = lambda org, name: QSettings(str(folder / f'{org}.{name}.ini'), QSettings.IniFormat)

    def setup_folder(self):
        self.dataSave_path = str(folder)
        self.ui.dataSavePath.setText(str(folder))
        print(f"Data save path set in UI: {folder}")  # as the real method, right after setting the path
    ns['moSys'].setup_data_folder = setup_folder

    today_file = folder / f'LiveProcess_{TODAY}.txt'
    today_file.write_text('OLDER SESSION LINE\n', encoding='utf-8')  # the file is appended, never replaced

    out, err = Terminal(), Terminal()
    sys.stdout, sys.stderr = out, err
    try:
        m = ns['moSys']()
        ui = m.ui
        box = ui.scanProgressText
        tip = box.toolTip()
        assert 'LiveProcess_YYYY-MM-DD.txt' in tip and 'since it started' in tip and '1000 lines' in tip
        report('PASS tooltip names the LiveProcess_YYYY-MM-DD.txt file and the 1000-line box')

        # ---- startup: text printed before the data folder was known is in the file, in order ----
        text = today_file.read_text(encoding='utf-8')
        session = f'Session started {TODAY}'
        assert text.startswith('OLDER SESSION LINE\n\n' + HEADER + '\n' + session), text[:300]
        assert text.splitlines()[3].endswith(' - ' + ui.windowTitle()), text.splitlines()[3]
        body = text.split('-' * 72 + '\n', 1)[1]
        assert body == ''.join(terminal), 'file differs from the terminal output'
        assert 'Data save path set in UI' in body and len(body.splitlines()) > 3
        assert pump(lambda: box.toPlainText().rstrip('\n') == body.rstrip('\n'))
        report(f'PASS startup: older content kept, session header, {len(body.splitlines())} startup lines '
               'equal to the terminal and to the box')

        # ---- idle prints reach the file at once, without the event loop ----
        print('IDLE_MARK gui ', end='')
        print('partial line', flush=True)
        t = threading.Thread(target=lambda: print('IDLE_MARK helper thread'))
        t.start()
        t.join()
        print('IDLE_MARK stderr', file=sys.stderr)
        text = today_file.read_text(encoding='utf-8')
        assert 'IDLE_MARK gui partial line\n' in text and 'IDLE_MARK helper thread\n' in text
        assert 'IDLE_MARK stderr\n' in text
        assert text.split('-' * 72 + '\n', 1)[1] == ''.join(terminal)
        report('PASS GUI thread, helper thread and stderr prints are on disk before the box updates')

        # ---- many threads at once: nothing lost, same order as the terminal ----
        def burst(n):
            for i in range(250):
                print(f'BURST {n}-{i}')
        threads = [threading.Thread(target=burst, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        text = today_file.read_text(encoding='utf-8')
        assert all(f'BURST {n}-{i}' in text for n in range(4) for i in range(250))
        assert text.split('-' * 72 + '\n', 1)[1] == ''.join(terminal)
        report('PASS 4 threads x 250 prints: all 1000 lines in the file, same order as the terminal')

        # ---- the box keeps 1000 lines, the file keeps everything ----
        print('BURST_DONE')
        assert pump(lambda: 'BURST_DONE' in box.toPlainText())
        assert box.document().blockCount() <= 1000 and 'IDLE_MARK helper thread' not in box.toPlainText()
        assert 'IDLE_MARK helper thread' in today_file.read_text(encoding='utf-8')
        report('PASS box capped at 1000 lines while the file has the full history')

        # ---- a scan that fails: its traceback is in the file, ScanLog stays separate ----
        m.is_custom_save_path = True
        m.check_instruments_ready = lambda: []
        m.prepare_scan_plan = lambda: {}
        m.drift_comp_active = lambda: False
        m.auto_block_after_scan = lambda thread: None

        def worker(thread):
            print('SCAN_MARK inside the scan')
            thread.scan_log.emit('KEY_EVENT error')
            raise RuntimeError('SIMULATED_SCAN_ERROR')
        m._execute_scan_logic = worker
        m.runScan()
        assert pump(lambda: not m.scan_Thread.isRunning(), 3) and m.scan_Thread.wait(1000)
        assert pump(lambda: 'Scan error' in ui.scanLogText.toPlainText())
        text = today_file.read_text(encoding='utf-8')
        assert 'SCAN_MARK inside the scan' in text and 'Traceback' in text and 'SIMULATED_SCAN_ERROR' in text
        log = Path(m._scan_log_path).read_text(encoding='utf-8')
        assert 'KEY_EVENT error' in log and 'KEY_EVENT' not in text and 'SCAN_MARK' not in log
        report('PASS failed scan: print and traceback in the Live Process file; ScanLog file kept separate')

        # ---- another data folder: a new file there, the old one gets nothing more ----
        other = folder / 'other'
        other.mkdir()
        m.dataSave_path = str(other)
        print('IN_OTHER_FOLDER')
        other_text = (other / f'LiveProcess_{TODAY}.txt').read_text(encoding='utf-8')
        assert other_text.startswith('\n' + HEADER + '\n' + session) and other_text.endswith('IN_OTHER_FOLDER\n')
        assert 'IN_OTHER_FOLDER' not in today_file.read_text(encoding='utf-8')
        m.dataSave_path = str(folder)
        print('BACK_IN_FOLDER')
        text = today_file.read_text(encoding='utf-8')
        assert text.count(session) == 2 and text.endswith('BACK_IN_FOLDER\n')
        report('PASS the file follows the data folder; going back appends with a second session header')

        # ---- a new day: a new file named by the date of writing ----
        tomorrow = datetime.now() + timedelta(days=1)

        class Tomorrow(datetime):
            @classmethod
            def now(cls, tz=None):
                return tomorrow
        ns['datetime'] = Tomorrow
        try:
            print('NEXT_DAY_LINE')
        finally:
            ns['datetime'] = datetime
        next_file = folder / f'LiveProcess_{tomorrow:%Y-%m-%d}.txt'
        assert next_file.read_text(encoding='utf-8').endswith('NEXT_DAY_LINE\n')
        assert 'NEXT_DAY_LINE' not in today_file.read_text(encoding='utf-8')
        print('TODAY_AGAIN')
        assert today_file.read_text(encoding='utf-8').endswith('TODAY_AGAIN\n')
        report('PASS after midnight the text goes to the next day\'s file')

        # ---- a folder that cannot be written: one warning, no exception, recovery afterwards ----
        missing = folder / 'missing' / 'deeper'
        m.dataSave_path = str(missing)
        before = len(terminal)
        print('LOST_LINE_1')
        print('LOST_LINE_2')
        warnings = [s for s in terminal[before:] if 'could not write Live Process file' in s]
        assert len(warnings) == 1 and str(missing) in warnings[0], terminal[before:]
        assert 'LOST_LINE_2' in out.getvalue()
        assert pump(lambda: 'could not write Live Process file' in box.toPlainText() and 'LOST_LINE_2' in box.toPlainText())
        assert not missing.exists()
        m.dataSave_path = str(folder)
        print('RECOVERED_LINE')
        text = today_file.read_text(encoding='utf-8')
        assert text.endswith('RECOVERED_LINE\n') and 'LOST_LINE' not in text
        report('PASS unwritable folder: one warning on the terminal and in the box, prints go on, file resumes')

        # ---- quit: file closed, later prints reach only the terminal ----
        app.aboutToQuit.emit()
        assert sys.stdout is out and sys.stderr is err and m._console_file is None
        print('AFTER_QUIT_NOT_IN_FILE')
        assert 'AFTER_QUIT_NOT_IN_FILE' not in today_file.read_text(encoding='utf-8')
        files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob('LiveProcess_*.txt'))
        report(f'PASS aboutToQuit closes the file; files written: {files}')
        ui.close()
    finally:
        if 'm' in globals():
            m.stop_console_mirror()  # also after a failed check, so the temporary folder can be removed
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
report('All Live Process file checks passed.')
