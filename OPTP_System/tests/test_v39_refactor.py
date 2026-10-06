"""Compare v3.9 simplifications with v3.8 without loading instruments or a GUI.

Checks ordered UI updates (including zero, missing and None values), unchanged
UI properties and unchanged controller logic outside the explicit simplifications.
"""
import ast
import copy
import itertools
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
def version_file(name):
    path = ROOT / name
    return path if path.is_file() else ROOT / 'old_version' / name


SOURCES = {version: version_file(f'OPTP_system_iTC_v{version}.py').read_text(encoding='utf-8')
           for version in ('3.8', '3.9')}
TREES = {version: ast.parse(source) for version, source in SOURCES.items()}
results = []


def check(label, condition):
    results.append(bool(condition))
    print(('PASS ' if condition else 'FAIL ') + label)


def methods(tree):
    return {f'{cls.name}.{fn.name}': fn for cls in tree.body if isinstance(cls, ast.ClassDef)
            for fn in cls.body if isinstance(fn, ast.FunctionDef)}


old, new = (methods(TREES[version]) for version in ('3.8', '3.9'))
slots = ('update_curr_repeat', 'update_curr_pos', 'update_curr_step',
         'update_curr_stepNOs', 'update_lockin_charts')
check('only one small UI helper added; all original methods retained',
      set(new) - set(old) == {'moSys._update_scan_values'} and set(old) <= set(new))


class Normalize(ast.NodeTransformer):
    """Ignore permitted output/version/icon changes and the two redundant wrappers."""
    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == 'self.ui.saveScreenshot.setIcon':
            assert ast.unparse(node.value.args[0]) in (
                'self.ui.saveScreenshot.style().standardIcon(QStyle.SP_DialogSaveButton)',
                "QIcon(str(Path(__file__).with_name('camera.svg')))",
            )
            return None  # The later Screenshot camera-icon change is display-only.
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'print':
            return None
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            node.value = node.value.replace('v3.8.ui', 'VERSION.ui').replace('v3.9.ui', 'VERSION.ui')
            if node.value in ('3.8', '3.9'):
                node.value = 'VERSION'
        return node

    def visit_Import(self, node):
        # The removed local import duplicated the unchanged global os import.
        return None if len(node.names) == 1 and node.names[0].name == 'os' else node

    def visit_Name(self, node):
        if node.id == 'move_success':
            node.id = '_'
        return node

    def visit_Assign(self, node):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'unit':
            assert ast.unparse(node.value) in (
                "'mm' if stage_name == 'stage1' else 'deg'",
                "'mm' if stage_name in ('stage1', 'stage2') else 'deg'",
            )
            node.value = ast.Constant('DISPLAY_UNIT')
        return self.generic_visit(node)

    def visit_If(self, node):
        if ast.unparse(node.test) == 'move_success and curr_pos_sets is not None':
            # Proven below: the driver wrapper either returns True plus a tuple, or raises.
            return [value for statement in node.body if (value := self.visit(statement)) is not None]
        if ast.unparse(node.test) == 'widget in always_enabled' and isinstance(node.body[0], ast.If):
            branch = node.body[0]
            while isinstance(branch, ast.If):
                assert len(branch.body) == 1 and ast.unparse(branch.body[0]) == 'widget.setEnabled(True)'
                branch = branch.orelse[0] if branch.orelse else None
            node.body = [ast.parse('widget.setEnabled(True)').body[0], *node.body[1:]]
        return self.generic_visit(node)


unexpected = []
for name in old:
    if name in {f'moSys.{slot}' for slot in slots}:
        continue
    baseline = Normalize().visit(copy.deepcopy(old[name]))
    candidate = Normalize().visit(copy.deepcopy(new[name]))
    if ast.dump(baseline, include_attributes=False) != ast.dump(candidate, include_attributes=False):
        unexpected.append(name)
check('all other method logic matches after the explicitly allowed changes', not unexpected)
if unexpected:
    print('Unexpected differences:', unexpected)
move = new['moSys.move_active_stages']
returns = [ast.unparse(n.value) for n in ast.walk(move) if isinstance(n, ast.Return)]
check('movement API and exception path unchanged; no False/None return exists',
      returns == ['(True, currPositions)']
      and ast.dump(move, include_attributes=False) == ast.dump(old['moSys.move_active_stages'], include_attributes=False))

used = {n.id for n in ast.walk(TREES['3.8']) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
check('removed imported names have no executable references',
      not used.intersection({'QVBoxLayout', 'QWidgetItem', 'QPen', 'random', 'sio'}))


class Probe:
    def __init__(self, name, events):
        self.name, self.events = name, events

    def setValue(self, value):
        self.events.append((self.name, 'value', value))

    def update(self, **kwargs):
        self.events.append((self.name, 'chart', kwargs))


class UIProbe:
    def __init__(self, events):
        self.events = events

    def __getattr__(self, name):
        return Probe(name, self.events)


def controller(version):
    selected = [copy.deepcopy(fn) for name, fn in methods(TREES[version]).items()
                if name in {f'moSys.{slot}' for slot in slots} | {'moSys._update_scan_values'}]
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), '<slots>', 'exec'), namespace)
    return type('DisplayController', (), {name: namespace[name] for name in (*slots, '_update_scan_values') if name in namespace})


controllers = {version: controller(version) for version in SOURCES}
fields = {
    'update_curr_repeat': ('stage1_curr_rep', 'stage2_curr_rep', 'rotary1_curr_rep', 'rotary2_curr_rep'),
    'update_curr_pos': ('stage1_pos', 'stage2_pos', 'rotary1_pos', 'rotary2_pos', 'rotary3_pos'),
    'update_curr_step': ('stage1_step', 'stage2_step'),
    'update_curr_stepNOs': ('stage1_NO', 'stage2_NO', 'rotary1_NO', 'rotary2_NO', 'rotary3_NO'),
    'update_lockin_charts': ('l1x', 'l1y', 'l2x', 'l2y'),
}


def trace(version, method, payload):
    events = []
    obj = controllers[version]()
    obj.ui = UIProbe(events)
    obj.chart_updaters = {name: Probe(name, events) for name in
                          ('lockin1XChart', 'lockin1YChart', 'lockin2XChart', 'lockin2YChart')}
    error = None
    try:
        getattr(obj, method)(payload)
    except Exception as exc:
        error = type(exc).__name__
    return events, error


missing = object()
case_count = 0
for method, names in fields.items():
    equal = True
    for values in itertools.product((missing, None, 0, -0.0015, 1.2345), repeat=len(names)):
        payload = dict(reversed([(name, value) for name, value in zip(names, values) if value is not missing]))
        payload.update(ignored=99, rotary1_step=15, rotary2_step=20, rotary3_step=25)
        equal &= trace('3.8', method, payload) == trace('3.9', method, payload)
        case_count += 1
    check(f'{method}: ordered writes and missing/None/zero/negative/decimal behavior identical', equal)
for field in fields['update_curr_step']:
    for value in (float('nan'), float('inf'), 'invalid'):
        payload = dict(stage1_step=.003, stage2_step=.004)
        payload[field] = value
        check(f'bad step value {field} {value!r}: same exception and preceding writes',
              trace('3.8', 'update_curr_step', payload) == trace('3.9', 'update_curr_step', payload))
        case_count += 1

old_ui = ET.parse(version_file('OPTP_iTC_main_v3.8.ui'))
new_ui = ET.parse(ROOT / 'OPTP_iTC_main_v3.9.ui')
title = new_ui.find(".//property[@name='windowTitle']/string")
check('new UI identifies v3.9', title is not None and 'v3.9' in title.text)
title.text = title.text.replace('v3.9', 'v3.8')
screenshot = new_ui.find(".//widget[@name='saveScreenshot']")
icon = screenshot.find("property[@name='icon']")
assert icon is not None and icon.findtext('iconset/normaloff') == 'camera.svg'
screenshot.remove(icon)
# The later borderless display-actions row changes only its container and spacing.
container = new_ui.find(".//widget[@name='displayActionsGroup']")
assert container is not None and container.get('class') == 'QWidget'
assert container.find("property[@name='title']") is None
assert container.find("property[@name='checkable']") is None
row = container.find("layout[@name='horizontalLayout_clearDisplay']")
assert row is not None
for side in ('left', 'top', 'right', 'bottom'):
    prop = row.find(f"property[@name='{side}Margin']")
    assert prop is not None and prop.findtext('number') == '6'
    row.remove(prop)
for height in row.findall("item/spacer/property[@name='sizeHint']/size/height"):
    assert height.text == '30'
    height.text = '36'
parents = {child: parent for parent in new_ui.iter() for child in parent}
item = parents[container]
container.remove(row)
item.remove(container)
item.append(row)
column = new_ui.find(".//layout[@name='verticalLayout_49']")
for name, value in (('spacing', '2'), ('topMargin', '8')):
    prop = column.find(f"property[@name='{name}']")
    assert prop is not None and prop.findtext('number') == value
    column.remove(prop)


def ui_shape(element):
    return (element.tag, element.attrib, (element.text or '').strip(),
            [ui_shape(child) for child in element])


check('all other UI controls, defaults, connections and layout match v3.8',
      ui_shape(old_ui.getroot()) == ui_shape(new_ui.getroot()))
print(f'{case_count} differential input cases; {sum(results)}/{len(results)} checks passed')
raise SystemExit(0 if all(results) else 1)
