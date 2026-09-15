# THz Emission System Development Change Log

This document records the overall development and debugging history for the THz emission system project, including version updates, bug fixes, and major functional changes.

## Version history

### v1.0
- Date: 2026-09-15
- Main change: created the THz emission system test code as a copy of the OPTP system v2.8 baseline.
- Details:
  - copied `OPTP_System/OPTP_system_iTC_v2.8.py` to `THz_emission_system/THz_emission_system_iTC_v1.0.py`,
  - copied `OPTP_System/OPTP_iTC_main_v2.8.ui` to `THz_emission_system/THz_emission_system_iTC_v1.0.ui`,
  - copied the supporting files needed to run standalone: `proj_tools.py`, `mo_icon.png`, `mo_icon.ico`, `.vscode/settings.json`,
  - updated the UI loading path in the Python file to point to `THz_emission_system_iTC_v1.0.ui`,
  - measurement logic and UI layout are otherwise identical to OPTP v2.8; shared modules under `inst_libs/` and `func_cores/` are still imported from the repository root,
  - changed the data saving folder from `OPTP_Data` to `THz_emission_Data` (created next to the system folder, under the repository root),
  - updated the main window title to the THz emission system name (done manually in the .ui file),
  - pending: replacement of the Stage1 related parameters for the THz emission setup.

### v1.0 - Stage1 replaced by PI N-565.360 / E-861
- Date: 2026-09-15
- Main change: replaced the Thorlabs BBD202 stage1 with the PI N-565.360 high-precision linear stage driven by an E-861 PiezoWalk controller.
- Details:
  - installed PIPython 2.9.0.4 (from the `PI_C-990_CD1\PIPython\PIPython.zip` product CD) plus its `pyusb`/`pyserial` dependencies into the `opto_test` conda environment (`C:\Users\Longch\.conda\envs\opto_test`, Python 3.13.13) used to run the measurement code; it drives the already-installed `C:\ProgramData\PI\GCSTranslator\PI_GCS2_DLL_x64.dll`,
  - added `inst_libs/physik_E861.py` with a `LinearStage` class exposing the same API as `thorlabs_LinearStage_BBD202.LinearStage` (`move_to`, `move_by`, `position`, `home_with_guard`, `stop`, `get_velocity`, `set_velocity`, `is_homed`, `close`), so the scan logic is unchanged,
  - the class connects over USB by controller serial, verifies the GCS axis, reports the loaded stage type and travel limits, switches the servo on, references the axis only when it is not referenced yet, rejects targets outside the travel range, and serializes all GCS I/O with a lock because the GUI thread reads positions while the scan thread moves,
  - in `THz_emission_system_iTC_v1.0.py`: imported the PI class as `PILinearStage` alongside the Thorlabs one (stage2 still uses BBD202), and changed the stage1 connection block to `PILinearStage("0119001337", axis="1", servo_on=True, reference_if_needed=True)`,
  - verified against the real hardware (read-only): E-861 firmware 7.2.0, axis '1' = N-565.360, referenced, travel -26 .. +26 mm, velocity 5 mm/s, acceleration 50 mm/s^2,
  - narrowed the stage1 spin boxes in the .ui to the PI travel range: `stage1SetPos`, `stage1CurrPos` and `stage1JogStep` now run -26 .. +26 mm, and `iPos1` runs -26 .. +26 mm with default 0 (it previously had no minimum and defaulted to 110); `stage1Step1~3` are in um and were left unchanged,
  - verified the edited .ui still loads through QUiLoader with the expected ranges.
  - added `inst_libs/test_pi_stage.py`, a standalone check of the E-861 driver: read-only by default, `--move` also exercises reference + relative/absolute moves + the travel-limit guard, `--force-ref` forces a new FRF reference move.
  - motion test passed on the real stage: relative +0.1 mm, relative -0.2 mm and an absolute move back to the start all read back exactly on target, and a target beyond the travel range is rejected before any GCS command is sent.
  - set the Lock-in1 VISA address to `GPIB0::3::INSTR` (was `GPIB0::2::INSTR` inherited from OPTP); confirmed by a VISA scan that the only GPIB device present is `GPIB0::3::INSTR` = Stanford_Research_Systems,SR830,s/n21725,ver1.01. Lock-in2 is not connected yet; its address was moved to the free `GPIB0::6::INSTR` so it cannot collide with Lock-in1 when it is added later.

### v1.1 - Verified stage1 arrival before lock-in reading
- Date: 2026-09-15
- Main change: created v1.1 from v1.0 and made the Stage1 (PI N-565.360 / E-861) arrival explicit, after stage1 moves during a scan looked suspiciously fast.
- Details:
  - copied `THz_emission_system_iTC_v1.0.py` to `THz_emission_system_iTC_v1.1.py` and `THz_emission_system_iTC_v1.0.ui` to `THz_emission_system_iTC_v1.1.ui`, and pointed the UI loading path in the new file to `THz_emission_system_iTC_v1.1.ui`,
  - investigation result: the scan thread is strictly serial (`move_active_stages()` -> `stage1.move_to()` -> `time.sleep(wait1)` -> `lockin1.get_x()`), so the lock-in can never be read before `move_to()` returns; the weak point was that `move_to()` could return before the axis had actually arrived,
  - root cause 1: `pipython.pitools.waitontarget()` starts polling qONT immediately after MOV, and the controller can still report the *previous* move's on-target flag for a few milliseconds, so the wait loop exits at once and the move looks instantaneous,
  - root cause 2: on-target is judged by the controller's settling-window parameter, which can be wider than the scan step, so ONT alone does not prove the axis is within the step resolution of the target,
  - `inst_libs/physik_E861.py`: `move_to()` now sleeps `move_predelay_s` (default 0.05 s) before `waitontarget()` to skip the stale-ONT window, and afterwards polls qPOS until `|qPOS - target| <= on_target_tolerance_mm` (default 0.001 mm), raising `RuntimeError` if the axis is still off target after `settle_timeout_ms` (default 1000 ms); it returns the verified position. All three values are constructor parameters, and `move_to`/`move_by` accept a per-call `tolerance_mm`,
  - `THz_emission_system_iTC_v1.1.py`: restored the `continue` in the scan loop's movement-error branch (it was commented out), so a failed or unverified move no longer writes a lock-in point at that scan index; a stop-flag check was added to that branch because the loop otherwise only checks the flag at its end, which would make the scan unstoppable if the stage kept failing,
  - verified with a simulated controller that reproduces the stale-ONT race: the patched `move_to()` returns only after the fake axis really arrives (133 ms instead of immediately), and a stuck axis raises `RuntimeError` after ~1.1 s instead of hanging for the full move timeout,
  - verified `THz_emission_system_iTC_v1.1.ui` still loads through QUiLoader with the PI travel range (-26 .. +26 mm),
  - note: `inst_libs/physik_E861.py` is shared, and `THz_emission_system_iTC_v1.0.py` is the only other importer, so v1.0 also gets the stricter arrival check,
  - not yet verified on the real hardware; on the setup, compare the target with the `Move successful! Actual positions:` log line, and lower `on_target_tolerance_mm` if the scan step is smaller than 1 um.

### v1.1 - Rotation stage 27005114 assigned to Rotary2
- Date: 2026-09-15
- Main change: pointed Rotary2 at the rotation stage actually installed on the THz emission setup.
- Details:
  - in `THz_emission_system_iTC_v1.1.py`, the Rotary2 controller serial was changed from `27255894` (inherited from the OPTP setup) to `27005114`,
  - the serial was first put on Rotary1 and then moved to Rotary2: the polarization scan logic treats Rotary2 as the master axis (the polar chart plots `rotary2_pos`, and the manual calibration path interpolates Rotary1/Rotary3 from Rotary2), so the single rotation stage of the THz setup belongs on Rotary2,
  - Rotary1 was set back to its OPTP serial `27004364` and Rotary3 is still `27255894` ch 2; neither stage exists on the THz emission setup, so both are meant to stay unchecked,
  - known limitation, not fixed here: `build_pol_states()` is called with `polarization_policy='coupled'` ([:1791]), which requires Rotary1, Rotary2 and Rotary3 to have the *same* number of states and ignores the active checkboxes. Scanning Rotary2 alone therefore aborts before the first data point unless the manual calibration path is used or the policy is switched to `'independent'` for POL_1D,
  - not yet verified against the hardware: connect with `activeRot2` checked and confirm homing and position readout, and check whether the `rot2SetPos` / `rot2CurrPos` / `rot2JogStep` ranges in the .ui match the travel of the new stage.

### v1.1 - Rotary connections use the guarded temp-object pattern
- Date: 2026-09-15
- Main change: Rotary1/2/3 now follow the same "temp object, release and reset to None on failure" connection pattern as Stage1/Stage2.
- Details:
  - before: the rotary blocks assigned `self.rotaryX = RotaryStage(...)` first and called `home(60000)` afterwards inside the same `try`. If the constructor succeeded but homing failed, the exception was caught and only printed, leaving `self.rotaryX` holding a live but un-homed object,
  - consequence of the old behaviour: `check_instruments_ready()` saw a non-None attribute and reported the stage as ready, and `move_active_stages()` then sent `move_to()` commands to a stage that had never been referenced,
  - after: each block builds `rotaryX_temp`, homes it, and only then assigns `self.rotaryX = rotaryX_temp`; the `except` branch closes the temp object (errors during close are swallowed), sets `self.rotaryX = None` and prints the failure, so a half-initialised rotary can no longer be mistaken for a connected one,
  - this mirrors the Stage1 (PI) and Stage2 (BBD202) blocks, which already used this pattern,
  - only the connection blocks were touched; the serials, homing timeout, poll interval, LED updates and print messages are unchanged,
  - verified by syntax check; the failure branch itself is not runtime-tested because it needs the real controllers.

### v1.2 - Created from v1.1, scan-mode tooltip aligned with the real modes
- Date: 2026-09-15
- Main change: opened v1.2 as the next development version and corrected the `scanMode` combobox tooltip, which still described the OPTP scan modes.
- Details:
  - copied `THz_emission_system_iTC_v1.1.py` / `.ui` to `THz_emission_system_iTC_v1.2.py` / `.ui`, pointed the UI loading path at `THz_emission_system_iTC_v1.2.ui` and added the v1.2 line to the version history block,
  - the tooltip of the `scanMode` `QComboBox` in the .ui (not in the .py) was inherited from OPTP and still used the OPTP naming: `'TDS_Scan'`, `'1D_TDS'`, `'2D_TDS'`, plus a `'1D_POL'` entry that has never existed in this system,
  - renamed all five `TDS` occurrences to `THz`, deleted the `'1D_POL'` entry, and reordered the remaining four to match `_init_scanMode_combobox()`: `THz_Scan`, `1D_THz`, `POL_1D`, `2D_THz`,
  - corrected `'1D_THz'` from "here stage1 beam act as pump" to "here stage2 beam act as pump". Verified against the code rather than the old comment: in `1D_THz` the TDS chart is fed with `stage2_pos_sequence` and stage1 is held at the THz peak by the peak-tracking routine, so stage2 is the swept pump delay line,
  - `'POL_1D'` was likewise rewritten to the description used in the Python docstring ("polarization dependent scan at specific delay point, here stage2 beam act as pump") instead of the OPTP wording "scan polarization at each 1D position",
  - the `_init_scanMode_combobox()` docstring in the .py was already correct and was left untouched; the tooltip now matches it word for word,
  - verified by loading the .ui through QUiLoader and reading `scanMode.toolTip()` back: four modes, correct names, no `TDS` string left anywhere in the file.

### v1.2 - 2D_THz scan order: stage1 made the innermost axis
- Date: 2026-09-15
- Main change: in `2D_THz`, one full stage1 time-domain trace is now recorded at each stage2 pump delay, instead of sweeping stage2 at each stage1 point.
- Details:
  - the shared `ScanPlanner.build_scan_iterator()` yields `itertools.product(pol, stage1, stage2)` for every non-POL_2D mode, and `product` varies its last argument fastest, so stage2 was the innermost axis. The nesting was therefore polarization (slowest) -> stage1 -> stage2 (fastest), i.e. a full pump-delay sweep at each THz delay point - the opposite of what the mode means and of what the scanMode tooltip says,
  - two consequences of the old order: a single time-domain trace took as long as the whole 2D scan to accumulate, so slow laser drift showed up as waveform distortion rather than point-to-point noise; and the live TDS chart, gated on `stage1_idx == stage1_NO - 1`, only fired at the very end of each polarization block and then emitted `stage2_NO` times in a row,
  - `func_cores/scan_func_core.py` is shared by OPTP, OPTP image and MO, all of which also define a `2D_THz` mode, so it was deliberately left untouched. The reordering is done in `THz_emission_system_iTC_v1.2.py` only: right after `build_scan_iterator()` returns, a `2D_THz` run replaces `scan_iterator` with a locally built generator nested `pol -> stage2 -> stage1`, using the `pol_total` / `stage2_total` / `stage1_total` values the planner already returns,
  - the tuple layout is unchanged - `(stage1_flat_idx, stage2_flat_idx, pol_flat_idx)` - so `decode_scan_indices()`, the HDF5 index tuple and every display slot are untouched. Only `2D_THz` is affected; all other modes still use the planner's iterator verbatim,
  - verified by driving the real planner plus the new override with 3 stage1 points x 2 stage2 points x 2 polarization states: the emitted order is stage1 0,1,2 at stage2=0, then stage1 0,1,2 at stage2=1, then the same for the second polarization state, and the TDS chart condition fires exactly 4 times (once per pump delay per polarization state) instead of bursting at the end. The chart's data slice `ds_lockin1_X[:, rep, stage2_idx, ...]` is complete at every emit,
  - the same local override was afterwards applied to `OPTP_System/OPTP_system_iTC_v2.8.py` and `OPTP_image_System/OPTP_iTC_image_v1.2.py`, which have the same layout (their `2D_THz` TDS chart is also fed with `stage1_pos_sequence`); see their own dev logs,
  - MO v2.2 was deliberately left unchanged: its `2D_THz` feeds the TDS chart with `stage2_pos_sequence`, so stage2 is the THz delay line on that setup and the existing stage2-innermost order is already correct there.

### v1.2 - Scan mode list reduced to the three modes this setup uses
- Date: 2026-09-15
- Main change: the `scanMode` combobox now offers `THz_Scan`, `2D_THz` and `THz_pol`; `1D_THz` was dropped and `POL_1D` was renamed to `THz_pol`.
- Details:
  - `scan_modes` in `_init_scanMode_combobox()` changed from `['THz_Scan', '1D_THz', 'POL_1D', '2D_THz']` to `['THz_Scan', '2D_THz', 'THz_pol']`,
  - the docstring of that method and the `scanMode` tooltip in the .ui were rewritten to the same three entries, each now stating its loop nesting explicitly: `THz_Scan` and `2D_THz` run rotation stages (outermost) -> stage2 -> stage1 (swept innermost), `THz_pol` runs stage2 (outermost) -> stage1 -> rotation stages (innermost),
  - the rename was applied to the two places where the mode string is actually used, so the mode keeps working under its new name: `iterator_mode = 'POL_2D' if scan_mode == 'THz_pol' else scan_mode`, and the TDS-chart branch `elif scan_mode == "THz_pol"`. No `POL_1D` string is left in the file,
  - the stale comment `# default to first mode 1D Scan` on the `test_mode` line was corrected to `THz_Scan`,
  - verified: the .ui loads through QUiLoader and `scanMode.toolTip()` reads back the three modes; the .py docstring and the tooltip are word for word identical.
- State after this change - the menu and the comments describe the target behaviour, and the loop logic does not implement all of it yet:
  - resolved: `THz_pol` got its own local override in the same block, nested stage2 (outermost) -> stage1 -> polarization (innermost). The shared planner's POL_2D branch had polarization innermost already, but nested stage1 outside stage2; the override swaps those two. Verified against the planner with 2 stage1 x 2 stage2 x 3 polarization states: the override visits stage1 0 then 1 at stage2=0, then the same at stage2=1, with all three polarization states swept inside each, and it covers exactly the same set of points as the planner - only the visiting order differs.
  - `iterator_mode = 'POL_2D' if scan_mode == 'THz_pol' else scan_mode` was left in place. Its iterator is now discarded for `THz_pol`, but the dimension totals it returns are independent of the mode and are what the override is built from.
  - resolved: the local scan-order override now covers both time-domain modes, `if scan_mode in ('THz_Scan', '2D_THz')`. Verified that with 3 stage1 points and 2 stage2 points `THz_Scan` now runs stage1 0,1,2 at stage2=0 then stage1 0,1,2 at stage2=1 (the planner interleaved them as (0,0),(0,1),(1,0),(1,1),...), and that the two orderings stay byte-identical when stage2 has a single position, so the normal single-delay THz_Scan is unaffected.
  - stage1 peak tracking is now permanently disabled, and this is deliberate, not a gap: the THz emission setup does not need it for now (unlike OPTP). `peak_tracking_enabled`, the `dynamic_THz_peak_pos` dataset and the `get_TDS_peak_pos()` call site are all gated on `scan_mode == '1D_THz'`, which no longer exists in the combobox, so none of them can run. The code is kept in the file unchanged so the feature can be re-enabled later by attaching those gates to a mode that does exist.
  - resolved: the polar chart gate was changed from `scan_mode == "POL_2D"` - a string that has never been in the combobox, so the branch was dead code - to `scan_mode == "THz_pol"`, so the live polarization plot now runs during the rotation sweep. The `enable_pol_chart = (N_pol >= 2)` guard and the emitted payload are unchanged; the angle it plots is `rotary2_pos`, which is correct on this setup because the single rotation stage (serial 27005114) is wired as Rotary2.
  - verified by simulation with 2 stage1 x 2 stage2 x 3 polarization states: the chart is fed at every scan point, and its `rotary2_idx == 0` clear condition fires once per polarization sweep, i.e. one fresh polar curve for each (stage2, stage1) delay combination.
  - the only `POL_2D` string left in the file is `iterator_mode = 'POL_2D' if scan_mode == 'THz_pol' else scan_mode`, which names a branch of the shared planner and is not a scan mode of this system.

### v1.2 - "Cali. file" moved into the path box as placeholder text
- Date: 2026-09-15
- Main change: the `Cali. file` caption is now shown inside the calibration-path box as greyed-out placeholder text, the same way the extra-info box does it, instead of sitting on a separate label above it.
- Details:
  - removed the `QLabel name="label_57"` (text `Cali. file`) and its enclosing `<item>` from `verticalLayout_85` in `THz_emission_system_iTC_v1.2.ui`; the layout now holds only the `cali_file_path` line edit, which frees the row the label occupied,
  - added `self.ui.cali_file_path.setPlaceholderText("Cali. file")` next to the existing `ext_info` placeholder call, so both boxes are initialised in the same place and in the same style,
  - the label had no references anywhere in the Python code, and the caption is not lost from the panel: the import button right above it is already labelled `Cali. File`,
  - `import_calibration_file()` still calls `cali_file_path.setText(...)`, so the placeholder is replaced by the real path once a file is imported and reappears if the text is cleared,
  - verified by loading the .ui through QUiLoader: it loads, `label_57` is gone, `cali_file_path` is still there, the placeholder reads back as `Cali. file`, and `text()` returns an empty string while the box is untouched - so nothing downstream can mistake the caption for a file path.

### v1.2 - Rot_stages_couple button wired up (label + tooltip)
- Date: 2026-09-15
- Main change: the new `Rot_stages_couple` push button now switches its own caption between `Independent` (unchecked, the default) and `Coupled` (checked), and carries a tooltip that describes what those two states mean.
- Details:
  - the button was added to the .ui as a checkable `QPushButton` with `checked=false` and text `Independent`, but had no handler in the Python file and no connection, so its caption never changed,
  - added `on_rot_stages_couple_toggled()` next to `on_pol_cali_mode_toggled()`, with the same one-line body style: `setText('Coupled' if checked else 'Independent')`,
  - connected it next to the calibration-mode button and called it once at startup with the button's current state, mirroring how `pol_cali_mode` is initialised, so the caption is correct before the user touches anything,
  - its tooltip in the .ui had been copy-pasted from `pol_cali_mode` and still described `'Auto Cali.'` / `'Cali. Data'`. Replaced with a description of the two coupling states: `Independent` - each rotation stage sweeps its own angle sequence and a stage with step number 1 stays at its initial angle; `Coupled` - Rotary1/2/3 step together, one angle each per polarization point, so all three need the same number of steps,
  - verified by loading the .ui and driving the real handler: the button reads `Independent` at startup, `Coupled` when checked and `Independent` again when unchecked, and the tooltip reads back as written.
- Wiring (done in the same version): `build_pol_states()` is now called with `polarization_policy='coupled' if rot_stages_coupled else 'independent'`, where `rot_stages_coupled = self.ui.Rot_stages_couple.isChecked()`. The hardcoded `'coupled'` is gone, and `func_cores/scan_func_core.py` was not touched - the `'independent'` branch already existed there and had simply never been selected.
  - `Independent` (default, button unchecked): the three rotary axes form a cartesian product, so an axis whose step number is 1 holds its initial angle and does not move. This is what makes it possible to scan the single rotation stage of this setup (Rotary2) without giving Rotary1 and Rotary3 matching step counts.
  - `Coupled` (button checked): unchanged behaviour - the three axes step together, one angle each per polarization point, and the scan aborts if their step counts differ.
  - the mapping is strictly what the button says, with no hidden override for calibration mode. Because `build_pol_states()` only consults the calibration table on the coupled path, a loaded table is silently ignored while the button is `Independent`, so a warning is printed for exactly that combination, telling the user to switch to `Coupled`.
  - verified against the real planner with the current setup (only Rotary2 given steps: 4 x 30 deg, Rotary1/3 left at step number 1): `Independent` yields N_pol=4 with rot2 sweeping 0/30/60/90 deg; `Coupled` without a calibration file aborts with the equal-step-count error; `Coupled` with a calibration table yields N_pol=4 and interpolates rot1 to 0/13.33/26.67/40 deg and rot3 to 0/6.67/13.33/20 deg; the same table under `Independent` leaves rot1 and rot3 pinned at their initial 10 deg and -5 deg - which is precisely the case the new warning covers.
