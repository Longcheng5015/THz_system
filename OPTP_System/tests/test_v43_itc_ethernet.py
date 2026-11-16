"""Native Qt checks for the Mercury iTC Ethernet address in Scan devices (OPTP v4.3, THz Emission v1.8).

    python OPTP_System/tests/test_v43_itc_ethernet.py [path to the GUI .py, default OPTP v4.3]

Part 1 needs no hardware: local TCP listeners stand in for Ethernet instruments, and the VISA and
Kinesis scans are replaced by fixed lists. Part 2 runs only when the Mercury iTC answers at
192.168.50.100:7020: Scan devices, pick the Ethernet entry, Conn. Instr. (iTC only), realtime
display, Close Instr. Only reads are sent to the controller. QSettings go to a temporary ini file.
"""
import socket
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'OPTP_system_iTC_v4.3.py'
sys.path.insert(0, str(SRC.parent))
REAL = sys.__stdout__
LIVE = 'TCPIP0::192.168.50.100::7020::SOCKET'


def report(msg):
    REAL.write(msg + "\n")
    REAL.flush()


source = SRC.read_text(encoding='utf-8-sig')
ns = {'__file__': str(SRC), '__name__': 'itc_ethernet_test'}
exec(compile(source[:source.rindex('app = QApplication()')], str(SRC), 'exec'), ns)
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QCheckBox
app = QApplication.instance() or QApplication([])
report(f'GUI under test: {SRC.name}')


def listener():
    """A local TCP port that accepts connections, like the iTC's port 7020."""
    srv = socket.socket()
    srv.bind(('127.0.0.1', 0))
    srv.listen(8)

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                return
    threading.Thread(target=serve, daemon=True).start()
    return srv, f'TCPIP0::127.0.0.1::{srv.getsockname()[1]}::SOCKET'


def closed_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens here any more: a connection is refused at once
    return f'TCPIP0::127.0.0.1::{port}::SOCKET'


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


# ---- tooltips ----
ui_name = next(line.split("'")[1] for line in source.splitlines() if 'ui_path = os.path.join' in line)
tree = ET.parse(SRC.parent / ui_name)
itc_tip = tree.find(".//widget[@name='iTC_res']/property[@name='toolTip']/string").text
scan_tip = tree.find(".//widget[@name='scanDevices']/property[@name='toolTip']/string").text
assert LIVE in itc_tip and 'ASRL11::INSTR' in itc_tip
assert LIVE in scan_tip and 'when its port answers' in scan_tip
report('PASS iTC_res and Scan devices tooltips name the Ethernet address')

with tempfile.TemporaryDirectory(prefix='itc_ethernet_') as tmp:
    ns['QSettings'] = lambda org, name: QSettings(str(Path(tmp) / f'{org}.{name}.ini'), QSettings.IniFormat)
    m = ns['moSys']()
    ui = m.ui
    ui.setAttribute(Qt.WA_DontShowOnScreen, True)
    ui.show()
    app.processEvents()
    assert m.ITC_SOCKETS == (LIVE,)

    # ---- part 1: no hardware ----
    tools = ns['InstrumentTools']
    real_visa, real_kinesis = tools.list_visa_resources, tools.list_kinesis_serials
    tools.list_visa_resources = staticmethod(lambda: ['GPIB0::3::INSTR', 'ASRL11::INSTR'])
    tools.list_kinesis_serials = staticmethod(lambda: ['27004364'])
    srv_a, up_a = listener()
    srv_b, up_b = listener()
    down = closed_port()
    m.ITC_SOCKETS = (up_a, down)  # instance override: the known address plus one that does not answer
    entered = {name: getattr(ui, name).currentText() for name in m.VISA_BOXES}
    ui.PM_res.setCurrentText(up_b)  # a SOCKET address typed into another VISA box is checked too
    ui.Lockin2_res.setCurrentText('TCPIP0::not-a-socket-string')  # ignored, no exception
    try:
        t = time.perf_counter()
        m.scan_devices()
        dt = time.perf_counter() - t
        for name in m.VISA_BOXES:
            box = getattr(ui, name)
            items = [box.itemText(i) for i in range(box.count())]
            assert items == ['GPIB0::3::INSTR', 'ASRL11::INSTR', up_a, up_b], (name, items)
        assert ui.iTC_res.currentText() == entered['iTC_res'] and ui.PM_res.currentText() == up_b
        assert ui.Lockin2_res.currentText() == 'TCPIP0::not-a-socket-string'
        assert dt < 1.5, dt
        report(f'PASS Scan devices lists the answering SOCKET addresses after the VISA list, skips the refused '
               f'and malformed ones, keeps the entered values ({dt:.2f} s)')
        srv_a.close()
        m.scan_devices()
        items = [ui.iTC_res.itemText(i) for i in range(ui.iTC_res.count())]
        assert up_a not in items and up_b in items
        report('PASS an address whose port stops answering is no longer offered')
    finally:
        srv_a.close()
        srv_b.close()
        tools.list_visa_resources, tools.list_kinesis_serials = real_visa, real_kinesis
        m.ITC_SOCKETS = type(m).ITC_SOCKETS
        ui.PM_res.setCurrentText(entered['PM_res'])
        ui.Lockin2_res.setCurrentText(entered['Lockin2_res'])

    # ---- part 2: real Mercury iTC on Ethernet ----
    try:
        socket.create_connection(('192.168.50.100', 7020), timeout=0.5).close()
        online = True
    except OSError:
        online = False
    if not online:
        report('SKIP live check: no answer from 192.168.50.100:7020')
    else:
        ui.iTC_res.setCurrentText('ASRL11::INSTR')
        m.scan_devices()
        items = [ui.iTC_res.itemText(i) for i in range(ui.iTC_res.count())]
        assert LIVE in items, items
        ui.iTC_res.setCurrentIndex(items.index(LIVE))  # pick it from the list, no typing
        for box in ui.findChildren(QCheckBox):
            if box.objectName().startswith('active'):
                box.setChecked(box.objectName() == 'activeiTC')
        m.connectInstruments()
        pump(0.5)
        assert m.mercuryiTC is not None and m.mercuryiTC.resource == LIVE and ui.mercuryiTCLed.status
        assert m.uid_TEMP and m.uid_HTR
        uids = f'{m.uid_TEMP}/{m.uid_HTR}'
        m.itc_updater.update_mercuryiTC_display(True)
        pump(3.5)
        shown = ui.realDispiTC.text()
        m.itc_updater.update_mercuryiTC_display(False)
        m.itc_updater.wait(5000)
        assert shown.endswith(' K') and float(shown[:-2]) > 0, shown
        m.closeInstruments(only_active=False)
        pump(0.3)
        assert m.mercuryiTC is None and not ui.mercuryiTCLed.status
        report(f'PASS live: Scan devices offers {LIVE}; picked from the list, Conn. Instr. reads '
               f'{uids}, realtime display shows {shown}, Close Instr. disconnects')
    app.aboutToQuit.emit()
    ui.close()
report('All iTC Ethernet checks passed.')
