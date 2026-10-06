"""Check progress emission order before peak acquisition in v4.01."""
import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'OPTP_system_iTC_v4.01.py'
tree = ast.parse(SRC.read_text(encoding='utf-8-sig'))
controller = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'moSys')
method = next(n for n in controller.body if isinstance(n, ast.FunctionDef) and n.name == 'compensate_temperature_drift')
ns = {}
exec(compile(ast.Module(body=[method], type_ignores=[]), str(SRC), 'exec'), ns)
compensate = ns['compensate_temperature_drift']

for counts, target in [({'rotary1_NO': 1, 'rotary2_NO': 1, 'rotary3_NO': 1}, (10, 20, 0)),
                       ({'rotary1_NO': 2, 'rotary2_NO': 2, 'rotary3_NO': 1}, (20, 25, 0)),
                       ({'rotary1_NO': 2, 'rotary2_NO': 2, 'rotary3_NO': 1}, (20, 25, 0)),
                       (None, (10, 20, 0))]:
    events = []
    thread = SimpleNamespace(position_update=SimpleNamespace(emit=lambda p: events.append(('position', p))),
                             stepNO_update=SimpleNamespace(emit=lambda p: events.append(('number', p))))
    def move(positions):
        events.append(('move', positions))
        # Distinguish actual readback from the commanded angles.
        return True, (110, 117, positions[2] + 0.001, positions[3] + 0.002, positions[4])
    def peak(thread, reference):
        assert events[0] == ('move', (110, 117, *target))
        assert events[1][0] == 'position'
        assert events[1][1]['rotary1_pos'] == target[0] + 0.001
        assert events[1][1]['rotary2_pos'] == target[1] + 0.002
        if counts is not None:
            assert events[2] == ('number', counts)
        else:
            assert len(events) == 2
        events.append(('peak', reference))
        return {'status': 'stopped'}
    m = SimpleNamespace(move_active_stages=move, get_TDS_peak_pos=peak)
    result = compensate(m, thread, 110, 117, 188, target, counts)
    assert result == (110, 117, 188, True)
    print(f'PASS move -> actual position -> rotary Curr. NO -> peak: {target}, {counts}')

# Stopped/failed searches must still identify the angle at which they were attempted.
for status in ('failed', 'stopped'):
    events = []
    m.get_TDS_peak_pos = lambda *args: {'status': status}
    m.scan_log_event = lambda *args: None
    result = compensate(m, thread, 110, 117, 188, target, {'rotary1_NO': 3})
    assert events[0][0] == 'move' and events[1][0] == 'position' and events[2] == ('number', {'rotary1_NO': 3})
    assert result[-1] == (status == 'stopped')
    print(f'PASS {status} search preserves early angle progress and existing result')
print('All v4.01 peak progress checks passed.')
