"""Exercise each new screenshot action with real Qt rendering and no instruments.

Run with optp/mo/img/thz; optional --native-preview uses the Windows Qt platform.
All settings and output files are isolated in a temporary directory.
"""
import hashlib
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if '--native-preview' not in sys.argv:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
SYSTEM = next((a for a in sys.argv[1:] if not a.startswith('--')), 'optp')
REPO = Path(__file__).resolve().parents[2]
FILES = {
    'optp': 'OPTP_System/OPTP_system_iTC_v3.9.py',
    'mo': 'MO_System/MO_system_iTC_v2.7.py',
    'img': 'OPTP_image_System/OPTP_iTC_image_v1.8.py',
    'thz': 'THz_emission_system/THz_emission_system_iTC_v1.6.py',
}
src = REPO / FILES[SYSTEM]
os.chdir(src.parent)
sys.path.insert(0, str(src.parent))
source = src.read_text(encoding='utf-8-sig')
ns = {'__file__': str(src), '__name__': 'screenshot_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(src), 'exec'), ns)

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox, QTabWidget

TMP = Path(tempfile.mkdtemp(prefix=f'{SYSTEM}_screenshot_'))
data_dir = TMP / '\u622a\u56fe data'
data_dir.mkdir()
ns['QSettings'] = lambda org, name: QSettings(str(TMP / f'{org}.{name}.ini'), QSettings.IniFormat)
warnings = []
QMessageBox.warning = staticmethod(lambda *args: warnings.append(args[2]))


class FixedDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 10, 4, 12, 34, 56)


ns['datetime'] = FixedDateTime


def isolated_data_folder(self):
    self.dataSave_path = str(data_dir)
    self.ui.dataSavePath.setText(self.dataSave_path)
    return self.dataSave_path


ns['moSys'].setup_data_folder = isolated_data_folder
app = QApplication.instance() or QApplication([])
m = ns['moSys']()
ui = m.ui
ui.setAttribute(Qt.WA_DontShowOnScreen, True)
ui.resize(1661, 973)
ui.show()
app.processEvents()
results = []


def check(name, condition):
    results.append(bool(condition))
    print(('PASS ' if condition else 'FAIL ') + name)


def valid_image(path):
    img = QImage(str(path))
    return not img.isNull() and img.size() == ui.grab().size()


check('button visible, enabled and labelled', ui.saveScreenshot.isVisible()
      and ui.saveScreenshot.isEnabled() and ui.saveScreenshot.text() == 'Screenshot')
tip = ui.saveScreenshot.toolTip()
check('tooltip has bold heading, separate paragraph and line breaks',
      '<p><b>Screenshot</b></p><p>' in tip and '<br/>' in tip)
if SYSTEM == 'optp':
    clear_pos = ui.clearLockinDisplay.mapTo(ui, QPoint(0, 0))
    save_pos = ui.saveScreenshot.mapTo(ui, QPoint(0, 0))
    check('screenshot button immediately right of Clear Display',
          save_pos.x() >= clear_pos.x() + ui.clearLockinDisplay.width()
          and abs(save_pos.y() - clear_pos.y()) <= 4)
    check('rotary input range inherited from v3.6',
          all(getattr(ui, f'iRot{i}').maximum() == 360 for i in (1, 2, 3)))

ui.scanMode.setCurrentText('THz_Scan')
if hasattr(m, 'get_ext_info'):
    ui.ext_info.setText('sample:one')
expected_stem = '12h34m56s_THz_Scan' + ('_sample_one' if hasattr(m, 'get_ext_info') else '')
original_time_text = ui.dataFileName.text()
ui.saveScreenshot.click()
pre_scan_png = data_dir / (expected_stem + '.png')
check('click before first scan saves valid PNG using system naming', valid_image(pre_scan_png))
check('screenshot leaves filename display unchanged', ui.dataFileName.text() == original_time_text)

scan_dir = data_dir / 'temperature run'
scan_dir.mkdir()
data_file = scan_dir / '11h22m33s_THz_Scan_300.0K_sample.1.h5'
data_file.write_bytes(b'unchanged measurement placeholder')
data_hash = hashlib.sha256(data_file.read_bytes()).hexdigest()
m.fullFilePath = str(data_file)
expected = data_file.with_suffix('.png')
m.set_ControlsEnabledDuringScan(True)
check('screenshot remains enabled while scan inputs are locked',
      ui.saveScreenshot.isEnabled() and not ui.runButton.isEnabled())
ui.saveScreenshot.click()
check('during scan PNG matches data directory/name including temperature and dots', valid_image(expected))
check('data file and scan state are untouched', m.fullFilePath == str(data_file) and m._scanning
      and hashlib.sha256(data_file.read_bytes()).hexdigest() == data_hash)
m.set_ControlsEnabledDuringScan(False)
check('screenshot remains enabled after scan', ui.saveScreenshot.isEnabled())

# Editing settings for the next scan must not rename the last scan's image.
m.dataSave_path = str(data_dir / 'next run')
ui.dataSavePath.setText(m.dataSave_path)
if hasattr(m, 'get_ext_info'):
    ui.ext_info.setText('next sample')
for tabs in ui.findChildren(QTabWidget):
    if tabs.count() > 1:
        tabs.setCurrentIndex(1)
app.processEvents()
expected.write_bytes(b'replace this old PNG')
returned = m.save_ui_screenshot()
check('after scan repeats replace same PNG despite edited next-run settings',
      returned == str(expected) and valid_image(expected) and not Path(m.dataSave_path).exists())
check('success path is reported in status bar', str(expected) in ui.statusbar.currentMessage())
preview_hash = hashlib.sha256(expected.read_bytes()).hexdigest()

# Simulate an encoder/disk write failure after partial bytes have been written.
real_grab = ui.grab


class FailedPixmap:
    def isNull(self):
        return False

    def save(self, device, image_format):
        device.write(b'partial image')
        return False


ui.grab = lambda: FailedPixmap()
check('failed PNG write reports failure and preserves previous image',
      m.save_ui_screenshot() is None and len(warnings) == 1
      and hashlib.sha256(expected.read_bytes()).hexdigest() == preview_hash)
ui.grab = real_grab
invalid_parent = data_dir / 'not a folder'
invalid_parent.write_text('keep this file', encoding='utf-8')
m.fullFilePath = str(invalid_parent / 'invalid.h5')
check('invalid output folder reports failure without affecting data',
      m.save_ui_screenshot() is None and len(warnings) == 2
      and invalid_parent.read_text(encoding='utf-8') == 'keep this file'
      and hashlib.sha256(data_file.read_bytes()).hexdigest() == data_hash)
ui.hide()
print(f'PREVIEW {expected}')
print(f'RESULT {SYSTEM}: {sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
