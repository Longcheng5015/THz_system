"""Check v4.0 Home controls with Qt layout and simulated Kinesis axes."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = ROOT / 'OPTP_system_iTC_v4.0.py'
source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'home_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory(prefix='optp_home_') as tmp:
    ns['QSettings'] = lambda org, name: QSettings(str(Path(tmp) / f'{org}.{name}.ini'), QSettings.IniFormat)
    def folder(self):
        self.dataSave_path = tmp
        self.ui.dataSavePath.setText(tmp)
    ns['moSys'].setup_data_folder = folder
    m = ns['moSys']()
    ui = m.ui
    ui.setAttribute(Qt.WA_DontShowOnScreen, True)
    ui.show()
    app.processEvents()

    for n in (1, 2):
        frame = getattr(ui, f'stage{n}Manual')
        assert frame.property('mytype') == 'inst_manu'
        assert getattr(ui, f'stage{n}MoveTo').parentWidget() is frame
        assert getattr(ui, f'stage{n}JogL').parentWidget() is frame
    print('PASS original manual-control frames and border styling retained')

    class Stage:
        def __init__(self):
            self.calls = []
            self.fail = False
            self._chan = SimpleNamespace(Home=self.home_command)
        def ensure_enabled(self): self.calls.append('enabled')
        def home_command(self, timeout):
            self.calls.append(('Home', timeout))
            if self.fail: raise RuntimeError('simulated home timeout')
        def position(self):
            self.calls.append('position')
            return 0.125

    for size in ((1661, 973), (1400, 900)):
        ui.resize(*size)
        app.processEvents()
        for n in (1, 2):
            home, move = getattr(ui, f'stage{n}Home'), getattr(ui, f'stage{n}MoveTo')
            ipos = getattr(ui, f'iPos{n}')
            hy, my = home.mapTo(ui, QPoint()).y(), move.mapTo(ui, QPoint()).y()
            print(f'GEOMETRY size={size} stage={n} Home={home.height()}@{hy} Move={move.height()}@{my}')
            assert home.height() == move.height() and hy == my
            assert home.mapTo(ui, QPoint()).x() >= ipos.mapTo(ui, QPoint()).x() + ipos.width()
            assert home.isVisible()
    print('PASS Home buttons match Move to height/alignment at both window sizes')
    for n in (1, 2):
        stage = Stage()
        setattr(m, f'stage{n}', stage)
        initial = getattr(ui, f'iPos{n}').value()
        original_wait = m.qwait_time
        m.qwait_time = lambda ms: stage.calls.append(('wait', ms))
        try:
            getattr(ui, f'stage{n}Home').click()
        finally:
            m.qwait_time = original_wait
        assert stage.calls == ['enabled', ('Home', 60000), ('wait', 1000), 'position']
        assert getattr(ui, f'stage{n}CurrPos').value() == 0.125
        assert getattr(ui, f'iPos{n}').value() == initial
    print('PASS each Home commands the correct axis and refreshes current position')
    m.set_ControlsEnabledDuringScan(True)
    for n in (1, 2):
        stage = getattr(m, f'stage{n}')
        count = len(stage.calls)
        button = getattr(ui, f'stage{n}Home')
        assert not button.isEnabled()
        button.click()
        assert not m.home_stage(f'stage{n}') and len(stage.calls) == count
    m.set_ControlsEnabledDuringScan(False)
    assert ui.stage1Home.isEnabled() and ui.stage2Home.isEnabled()
    print('PASS scan disables homing and completion restores controls')
    m.stage1.fail = True
    assert not m.home_stage('stage1')
    m.stage2 = None
    assert not m.home_stage('stage2')
    print('PASS homing failure and disconnected stage are handled')
    preview = Path(tempfile.gettempdir()) / 'optp_v40_home_preview.png'
    ui.grab().save(str(preview))
    print(f'Preview: {preview}')
    ui.close()
print('All stage Home checks passed.')
