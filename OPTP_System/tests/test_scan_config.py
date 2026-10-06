"""Latest-system JSON recipes: real Qt UI, temporary files, no instrument access.

Run with optp/mo/img/thz; --native-preview also checks the Windows layout.
"""
import copy
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

if '--native-preview' not in sys.argv:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
SYSTEM = next((arg for arg in sys.argv[1:] if not arg.startswith('--')), 'optp')
FILES = {
    'optp': ('OPTP_System/OPTP_system_iTC_v3.9.py', 'OPTP.scan_config', '3.9'),
    'mo': ('MO_System/MO_system_iTC_v2.7.py', 'MO.scan_config', '2.7'),
    'img': ('OPTP_image_System/OPTP_iTC_image_v1.8.py', 'OPTP_Image.scan_config', '1.8'),
    'thz': ('THz_emission_system/THz_emission_system_iTC_v1.6.py', 'THz_Emission.scan_config', '1.6'),
}
SRC = Path(__file__).resolve().parents[2] / FILES[SYSTEM][0]
ROOT = SRC.parent
os.chdir(ROOT)  # Imaging loads its UI relative to the working directory.
sys.path.insert(0, str(ROOT))
ns = {'__file__': str(SRC), '__name__': 'scan_config_test'}
source = SRC.read_text(encoding='utf-8-sig')
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)

import numpy as np
from PySide6.QtCore import QSettings, QSignalBlocker, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QCheckBox, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox

TMP = Path(tempfile.mkdtemp(prefix=f'{SYSTEM}_config_test_'))
ns['QSettings'] = lambda org, name: QSettings(str(TMP / f'{org}.{name}.ini'), QSettings.IniFormat)


def data_folder(self):
    self.dataSave_path = str(TMP)
    self.ui.dataSavePath.setText(str(TMP))
    return str(TMP)


ns['moSys'].setup_data_folder = data_folder
app = QApplication.instance() or QApplication([])
m = ns['moSys']()
ui = m.ui
warnings, results, hardware_calls = [], [], []
QMessageBox.warning = staticmethod(lambda *args: warnings.append(args[2]))


def check(name, condition):
    results.append(bool(condition))
    print(('PASS ' if condition else 'FAIL ') + name)


class UntouchedInstrument:
    def __getattr__(self, name):
        def forbidden(*args, **kwargs):
            hardware_calls.append(name)
            raise AssertionError(f'Configuration must not access hardware: {name}')
        return forbidden


for name in ('lockin1', 'lockin2', 'stage1', 'stage2', 'rotary1', 'rotary2', 'rotary3',
             'mercuryiTC', 'flipmount', 'powermeter'):
    setattr(m, name, UntouchedInstrument())
for name, index in (('sensitivity1', 12), ('sensitivity2', 15), ('timeConst1', 6), ('timeConst2', 10)):
    box = getattr(ui, name)
    with QSignalBlocker(box):
        box.setCurrentIndex(index)
m.show_lockin_phase('lockin1', 37.42); m.show_lockin_phase('lockin2', -125.75)
position_readback = 1.234 if SYSTEM == 'thz' else 201.234
ui.stage1CurrPos.setValue(position_readback)
initial = m.collect_scan_config()
excluded = {name: getattr(ui, name).value() if name.startswith('phase') else getattr(ui, name).currentIndex()
            for name in ('phase1', 'phase2', 'sensitivity1', 'sensitivity2', 'timeConst1', 'timeConst2')}
check('schema excludes instrument settings, manual actions, paths and live readouts',
      not (set(excluded) | {'stage1CurrPos', 'dataSavePath', 'dataFileName', 'fmManual', 'autoPID',
                            'Lockin1_res', 'pmWavelength', 'pmRange'}) & set(initial['parameters']))
if SYSTEM != 'optp':
    check('system recipe excludes absent OPTP peak/beam-settle controls',
          not {'driftComp', 'TDS_Ppos', 'repeatPeak', 'stage2CompDir', 'passOrder', 'beamSettle'} & set(initial['parameters']))
if SYSTEM == 'img':
    image_view = ui.imgChannel.currentIndex(), ui.imgMetric.currentIndex(), ui.imgPoint.value()
    check('imaging recipe has no missing soak/suffix fields or image-display selectors',
          not {'WaitSamStable', 'ext_info', 'imgChannel', 'imgMetric', 'imgPoint'} & set(initial['parameters']))

calibration = TMP / ('calibration.txt' if SYSTEM == 'img' else 'calibration.csv')
calibration.write_text('12 0 50 0.1\n22 10 60 0.2\n' if SYSTEM == 'img' else
                      'Point_Idx,Stage1,Stage2,Stage3,Power,Stable\n'
                      '0,12,0,50,0.1,1\n1,22,10,60,0.2,1\n', encoding='utf-8')
payload = copy.deepcopy(initial)
for name, value in payload['parameters'].items():
    box = getattr(ui, name)
    if isinstance(box, (QCheckBox, QPushButton)):
        payload['parameters'][name] = not value
    elif isinstance(box, (QSpinBox, QDoubleSpinBox)):
        payload['parameters'][name] = min(box.maximum(), value + 1)
    elif isinstance(box, QComboBox):
        payload['parameters'][name] = box.itemText((box.currentIndex() + 1) % box.count())
payload['parameters'].update(scanMode='2D_THz', iPos1=1.923 if SYSTEM == 'thz' else 188.923, iPos2=117.221,
    cali_file_path=str(calibration), pol_cali_mode=True, Rot_stages_couple=True,
    wait1=731, wait2=923, wait1multip=2.5, wait2multip=3.5, ScanT=True)
if SYSTEM == 'optp':
    payload['parameters'].update(TDS_Ppos=188.925, stage2CompDir=False, passOrder=True, repeatPeak=False)
if SYSTEM != 'img':
    payload['parameters']['ext_info'] = 'sample \u6837\u54c1 A'
payload['temperature_points_K'] = [300, 280.125, 300, 250]
config = TMP / '\u914d\u7f6e sample.json'
config.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8-sig')
QFileDialog.getOpenFileName = staticmethod(lambda *args, **kwargs: (str(config), ''))
ui.importScanConfig.click()
current = m.collect_scan_config()
check('Imp. Conf. button restores every saved parameter from UTF-8/BOM JSON',
      current['parameters'] == payload['parameters'] and not warnings)
check('temperature order, repeats and fractional values reach both model and UI',
      m.tp_manager.temp_sequence == payload['temperature_points_K']
      and [ui.T_list.item(i).data(Qt.UserRole) for i in range(ui.T_list.count())
           if ui.T_list.item(i).data(Qt.UserRole) is not None] == list(range(4)))
check('import reloads calibration data rather than only showing a filename',
      np.array_equal(m.cali_table['rot1_cali'], [12, 22]) and np.array_equal(m.cali_table['rot2_cali'], [0, 10]))
check('derived mode, toggle captions and wait timers match the imported values',
      m.test_mode == '2D_THz' and ui.Rot_stages_couple.text() == 'Coupled'
      and ui.pol_cali_mode.text() == 'Manu. Cali.'
      and (SYSTEM != 'optp' or (ui.stage2CompDir.text() == 'Forward'
                               and ui.passOrder.isChecked() and ui.repeatPeak.text() == 'Re-peak: OFF'))
      and m.chart_updaters['realDisChart1'].timer.interval() == 731
      and m.chart_updaters['realDisChart2'].timer.interval() == 923
      and m.pm_timer.interval() == ui.pmRefresh.value()
      and m.itc_updater.interval == ui.waitiTC.value() * 1000)
check('import leaves hardware settings, live position and output directory untouched',
      excluded == {name: getattr(ui, name).value() if name.startswith('phase') else getattr(ui, name).currentIndex()
                   for name in excluded}
      and ui.stage1CurrPos.value() == position_readback and m.dataSave_path == str(TMP) and not hardware_calls)
if SYSTEM == 'img':
    check('imaging display selectors remain unchanged on import',
          image_view == (ui.imgChannel.currentIndex(), ui.imgMetric.currentIndex(), ui.imgPoint.value()))

exported = TMP / 'saved scan'
QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: (str(exported), ''))
ui.exportScanConfig.click()
exported = exported.with_suffix('.json')
saved = json.loads(exported.read_text(encoding='utf-8'))
check('Exp. Conf. button saves readable JSON, adds suffix and preserves all values',
      saved['parameters'] == payload['parameters'] and saved['temperature_points_K'] == payload['temperature_points_K']
      and saved['schema_version'] == 1 and saved['format'] == FILES[SYSTEM][1]
      and saved['application_version'] == FILES[SYSTEM][2])
m.apply_scan_config(initial, TMP)
check('restoring a recipe with no calibration clears the previous calibration table', m.cali_table is None)
check('export/import round trip restores all scan values and model state',
      m.import_scan_config(exported) and m.collect_scan_config()['parameters'] == saved['parameters']
      and m.tp_manager.temp_sequence == saved['temperature_points_K'])

relative = copy.deepcopy(saved)
relative['parameters']['cali_file_path'] = calibration.name
config.write_text(json.dumps(relative), encoding='utf-8')
check('relative calibration paths resolve against the JSON folder', m.import_scan_config(config)
      and ui.cali_file_path.text() == str(calibration.resolve()))


def snapshot():
    snap = m.collect_scan_config()
    return snap['parameters'], snap['temperature_points_K'], {k: v.tolist() for k, v in (m.cali_table or {}).items()}


invalid = []
for title, edit in [
    ('wrong system', lambda p: p.update(format='MO.scan_config' if SYSTEM == 'optp' else 'OPTP.scan_config')),
    ('unsupported format version', lambda p: p.update(schema_version=2)),
    ('boolean format version', lambda p: p.update(schema_version=True)),
    ('missing field', lambda p: p['parameters'].pop('iPos2')),
    ('instrument-setting injection', lambda p: p['parameters'].update(phase1=99)),
    ('wrong numeric type', lambda p: p['parameters'].update(iPos2='100')),
    ('out-of-range position', lambda p: p['parameters'].update(iPos1=1e9)),
    ('NaN position', lambda p: p['parameters'].update(iPos1=float('nan'))),
    ('fractional point count', lambda p: p['parameters'].update(stage1Step1NO=1.5)),
    ('unsupported precision', lambda p: p['parameters'].update(iPos1=188.1234567)),
    ('unknown scan mode', lambda p: p['parameters'].update(scanMode='unknown')),
    ('invalid temperature', lambda p: p.update(temperature_points_K=[300, float('inf')])),
    ('negative tolerance', lambda p: p['parameters'].update(Tolerance=-1)),
    ('missing calibration', lambda p: p['parameters'].update(cali_file_path='missing.csv')),
    ('enabled calibration without file', lambda p: p['parameters'].update(cali_file_path='')),
]:
    bad = copy.deepcopy(saved)
    bad['parameters']['iPos2'] = 120.456  # must not get applied before another field fails
    edit(bad)
    invalid.append((title, json.dumps(bad)))
invalid += [('broken JSON', '{ invalid json'), ('non-object JSON', '[]')]
for title, content in invalid:
    config.write_text(content, encoding='utf-8')
    before = snapshot()
    check(f'{title}: rejected before changing any parameter/model', not m.import_scan_config(config) and snapshot() == before)
bad_cali = TMP / 'bad.csv'; bad_cali.write_text('not a table', encoding='utf-8')
bad = copy.deepcopy(saved); bad['parameters']['cali_file_path'] = str(bad_cali)
config.write_text(json.dumps(bad), encoding='utf-8'); before = snapshot()
check('malformed calibration is rejected without partial application', not m.import_scan_config(config) and snapshot() == before)

before = snapshot()
QFileDialog.getOpenFileName = staticmethod(lambda *args, **kwargs: ('', ''))
QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: ('', ''))
check('cancelled dialogs leave all state untouched', not m.import_scan_config()
      and m.export_scan_config() is None and snapshot() == before)

original_hash = hashlib.sha256(exported.read_bytes()).hexdigest()
real_save_file = ns['QSaveFile']


class FailedWrite:
    def __init__(self, name): self.file = real_save_file(name)
    def open(self, mode): return self.file.open(mode)
    def write(self, data): self.file.write(data[:8]); return -1
    def errorString(self): return 'simulated partial disk write'
    def cancelWriting(self): self.file.cancelWriting()


ns['QSaveFile'] = FailedWrite
check('failed atomic export preserves the previous JSON', m.export_scan_config(exported) is None
      and hashlib.sha256(exported.read_bytes()).hexdigest() == original_hash)
ns['QSaveFile'] = real_save_file
check('invalid export location reports failure', m.export_scan_config(TMP / 'missing folder' / 'scan.json') is None)

m.fullFilePath = str(TMP / 'ongoing measurement.h5')
ui.update()  # no event-loop processing: connected test devices must never be queried
m.set_ControlsEnabledDuringScan(True)
check('import is disabled and direct calls rejected while scanning; export stays available',
      not ui.importScanConfig.isEnabled() and ui.exportScanConfig.isEnabled()
      and not m.import_scan_config(exported))
if SYSTEM == 'img':
    check('imaging selectors stay available during scanning and retain point-selector policy',
          ui.imgChannel.isEnabled() and ui.imgMetric.isEnabled()
          and ui.imgPoint.isEnabled() == (ui.imgMetric.currentText() == 'At point'))
before = snapshot()
check('export during scan captures current UI without changing scan/file state',
      m.export_scan_config(TMP / 'during_scan.json') is not None and m._scanning
      and snapshot() == before and m.fullFilePath == str(TMP / 'ongoing measurement.h5'))
m.set_ControlsEnabledDuringScan(False)
check('import is available again after scan', ui.importScanConfig.isEnabled())
check('all import/export paths issued zero instrument calls', not hardware_calls)

if '--native-preview' in sys.argv:
    ui.setAttribute(Qt.WA_DontShowOnScreen, True)
    ui.resize(1661, 973); ui.show(); app.processEvents()
    buttons = [ui.saveScreenshot, ui.importScanConfig, ui.exportScanConfig]
    check('native buttons are beside Screenshot with fully visible labels',
          all(b.fontMetrics().horizontalAdvance(b.text()) + 38 <= b.width() for b in buttons)
          and all(a.geometry().right() < b.geometry().left() for a, b in zip(buttons, buttons[1:])))
    ui.grab().save(str(TMP / 'config_buttons.png'))
for name in ('lockin1', 'lockin2', 'stage1', 'stage2', 'rotary1', 'rotary2', 'rotary3', 'mercuryiTC', 'flipmount', 'powermeter'):
    setattr(m, name, None)
ui.close()
print(f'RESULT {SYSTEM}: {sum(results)}/{len(results)} passed; {TMP}')
sys.exit(0 if all(results) else 1)
