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
  - its tooltip in the .ui had been copy-pasted from `pol_cali_mode` and still described `'Auto Cali.'` / `'Cali. Data'`. Replaced with a description of the two coupling states: `Independent` - each rotation stage follows its own angle sequence and a stage with step number 1 stays at its initial angle and never moves; `Coupled` - Rotary1/2/3 step together, one angle each per polarization point, so all three need the same number of steps. A closing line records that importing a calibration file forces coupled for that scan whatever the button shows,
  - this tooltip had to be written twice: the first edit was verified through QUiLoader and then reverted, because the .ui was open in Qt Designer and a later save from there restored the old property. The `label_57` removal and the `scanMode` tooltip in the same file survived. When editing this .ui from both sides, close or reload it in Designer first,
  - verified by loading the .ui and driving the real handler: the button reads `Independent` at startup, `Coupled` when checked and `Independent` again when unchecked, and the tooltip reads back as written.
- Wiring (done in the same version): `build_pol_states()` is now called with `polarization_policy='coupled' if rot_stages_coupled else 'independent'`, where `rot_stages_coupled = self.ui.Rot_stages_couple.isChecked()`. The hardcoded `'coupled'` is gone, and `func_cores/scan_func_core.py` was not touched - the `'independent'` branch already existed there and had simply never been selected.
  - `Independent` (default, button unchecked): the three rotary axes form a cartesian product, so an axis whose step number is 1 holds its initial angle and does not move. This is what makes it possible to scan the single rotation stage of this setup (Rotary2) without giving Rotary1 and Rotary3 matching step counts.
  - `Coupled` (button checked): unchanged behaviour - the three axes step together, one angle each per polarization point, and the scan aborts if their step counts differ.
  - manual calibration overrides the button: `manu_cali_active = pol_cali_mode.isChecked() and self.cali_table`, and `rot_stages_coupled = Rot_stages_couple.isChecked() or manu_cali_active`. `build_pol_states()` only consults the calibration table on the coupled path, so without the override an imported table would be silently ignored whenever the button read `Independent`. When the override actually changes the outcome a note is printed, so the run log says why the stages ran coupled while the button said otherwise.
  - verified against the real planner with the current setup (only Rotary2 given steps: 4 x 30 deg, Rotary1/3 left at step number 1), driving the exact decision the scan now makes: button `Independent` with no calibration -> independent, N_pol=4, rot1 pinned at its initial 10 deg; button `Independent` with `Manu. Cali.` and a loaded table -> overridden to coupled, N_pol=4, rot1 interpolated to 0/13.33/26.67/40 deg; button `Coupled` with no calibration file -> aborts with the equal-step-count error, as before; button `Coupled` with a table -> coupled and interpolated; button `Independent` with `Manu. Cali.` pressed but no file imported -> stays independent, since the override needs an actual table, not just the button.

### v1.2 - Calibration-button tooltip renamed to the caption it actually shows
- Date: 2026-09-15
- Main change: the `pol_cali_mode` tooltip now names `'Manu. Cali.'`, the caption the button really switches to, instead of `'Cali. Data'`.
- Details:
  - `on_pol_cali_mode_toggled()` sets the button text to `'Auto Cali.'` or `'Manu. Cali.'`, but its tooltip still described the second state as `'Cali. Data'`, a caption that appears nowhere in the UI,
  - replaced that one string inside the `pol_cali_mode` widget block; the rest of the tooltip, and every other widget, is untouched,
  - the `Rot_stages_couple` tooltip had to be written a third time in the same session: the .ui was open in Qt Designer and each save from there restored the old copy-pasted text. Both tooltips were finally written in a single pass and verified in the same command, then re-verified afterwards. If the .ui is edited from both sides again, close or reload it in Designer first.

### v1.2 - Thorlabs stages skip homing when already homed
- Date: 2026-09-15
- Main change: the Thorlabs drivers now skip the homing move when the controller already reports the axis as homed, matching what the PI E-861 driver has always done. Connecting instruments after a Python restart no longer re-runs the full homing travel.
- Details:
  - `physik_E861.LinearStage.home()` has always checked `qFRF()` and returned early, but the three Thorlabs drivers called `Home(timeout_ms)` unconditionally, so every connect cost a full homing move per axis,
  - all three already exposed `is_homed()`, and nothing in the project had ever called it - the only call sites were two prints in `inst_libs/test_pi_stage.py`,
  - **`is_homed()` was broken and this change was what exposed it.** All three read `bool(<device>.IsHomed)`, but Kinesis does not put that property on the device object: the first real connection attempt failed with `'KCubeDCServo' object has no attribute 'IsHomed'`, and the rotary was correctly left as `None` by the guarded connection pattern,
  - the correct location was then confirmed by reflecting over the installed Kinesis assemblies (no hardware needed): `KCubeDCServo` and `BrushlessMotorChannel` both expose only `CanHome` ("this axis supports homing"), while the motion state lives on their `Status` property of type `GenericMotorCLI.StatusBase`, which carries `IsHomed` alongside `IsHoming`, `IsEnabled`, `IsInMotion`, `IsAtHWLimit` and so on,
  - `is_homed()` was rewritten to read `Status.IsHomed`, with a `not NeedsHoming` fallback for Kinesis builds that expose that instead (the installed version does not), and `False` if neither is reachable - so an unreadable status makes the caller home normally instead of skipping,
  - added the same three-line guard to `thorlabs_LinearStage_BBD202.home()` **and** `home_with_guard()` (that method does not delegate to `home()`, it repeats the homing call, so both needed it), to `thorlabs_LinearStage.home()` and to `thorlabs_RotaryStage.home()`,
  - in the BBD202 methods the guard is placed *after* `ensure_enabled()`, so the motor is still enabled on the skip path; only the homing travel is avoided,
  - the homed flag lives in the controller firmware, not in the Python process, and none of the drivers' `close()` methods call `DisableDevice()` - they only `StopPolling()` and `Disconnect()`. So the flag survives closing and restarting the Python program, and is cleared by a controller power cycle or a limit/error condition, where the guard falls through and homes normally,
  - this is a change to the shared `inst_libs/` drivers, so it affects every system. No main program was modified: they all call `home()` / `home_with_guard()` exactly as before,
  - affected on this setup: Stage2 (BBD202, via `home_with_guard`) and Rotary1/2/3 (KDC101). Stage1 is the PI N-565.360, which already skipped its reference move,
  - verified by extracting the patched methods with `ast` and running them against stubs: with `is_homed()` True, `Home()` is called 0 times and the skip message is printed; with False, `Home()` is called exactly once; the BBD202 enable guard runs in both branches. The rewritten `is_homed()` was then driven with four backing shapes per driver - a device with no `IsHomed` anywhere (the shape that crashed on hardware), `Status.IsHomed` True and False, and `NeedsHoming` - 12 checks, all returning the expected value with no exception,
  - the skip path itself is still not confirmed on hardware: connect once, close the program, reconnect without power-cycling the controllers, and check that each axis prints `[Kinesis] Axis already homed, skipping homing move.` If the status object is not readable at that point the axis will simply home as before, which is the safe direction.

### v1.2 - Rotation angles wrapped into the travel; travel limits exposed
- Date: 2026-09-15
- Main change: a rotation target outside the stage travel is now wrapped into one turn instead of being rejected by the controller mid-scan, and every stage driver can report its configured travel.
- Details:
  - symptom: a THz scan died on every point with `Cannot move to requested position` from `GenericMotorCLI.VerifyDeviceMovement`, at the planned point `(5.135, 110.0, 3.0, 367.0, 4.0)`. The offending value was Rotary2 at **367 deg** on a 360 deg stage,
  - nothing in the chain validated angles: the UI spin boxes allow up to 1000 deg, `generate_position_sequence()` just accumulates `iRot + n*step` with no wrap, and `RotaryStage.move_to()` passed the value straight to `MoveTo()`. Only the Kinesis firmware refused it, with a .NET stack trace that does not name the axis,
  - it also wasted the whole run: the rotation stages sit in the outer loop, so the bad angle stayed put while the inner axis kept stepping, and every point of that sweep was skipped. Rotary3 never moved either, because the exception aborts `move_active_stages()` before it,
  - `thorlabs_RotaryStage`: the constructor now reads `AdvancedMotorLimits.LengthMinimum/LengthMaximum` into `min_pos` / `max_pos` (printed on connect). New `resolve_target()` maps a requested angle onto that travel - inside the travel it is returned unchanged; outside a full-turn travel it is wrapped (`lo + (target - lo) % span`) and the wrap is printed; on an axis whose travel is not a full turn there is nothing sensible to wrap to, so it raises `ValueError` naming the limits. `move_to()` now goes through it. Wrapping is lossless: 367 deg and 7 deg are the same optical configuration,
  - `thorlabs_LinearStage_BBD202`, `thorlabs_LinearStage` and `physik_E861` gained a read-only `travel_limits()` so the scan code can treat every axis alike. The linear `move_to()` calls were deliberately NOT given a new guard: Kinesis already rejects an out-of-range target, and narrowing it here could refuse moves the controller would accept,
  - known side effect of wrapping: crossing the seam (350 deg -> 370 deg) becomes an absolute move to 10 deg, so the stage turns the long way back rather than 20 deg forward. Harmless, once per revolution, and avoidable by planning the sweep inside 0..360,
  - verified with the real `resolve_target()` against stub stages: on a 0..360 axis 7/360/350 pass through unchanged, 367 and 727 wrap to 7, -30 wraps to 330; with unreadable limits everything falls back to modulo 360; on a 0..180 axis 90 passes and 200 raises `ValueError` naming the range. Not yet exercised against real hardware.

### v1.2 - Planned positions checked against stage travel before a run
- Date: 2026-09-15
- Main change: the scan now validates every planned position against the travel of each active axis before anything moves, and a movement error names the axis that failed.
- Details:
  - added a check right after the polarization states are built: for each active and connected axis it asks the driver for `travel_limits()`, and for an axis that provides `resolve_target()` (the rotaries) it asks the driver to resolve each target rather than comparing against the raw limits - otherwise a wrappable angle such as 367 deg would be reported as an error when the driver handles it fine,
  - if anything is unreachable the scan stops before the first move, with a message naming the axis, how many of the planned positions fail, the travel, and the first few offending values; the HDF5 file is closed on that path like the other early-exit errors,
  - an axis that is not ticked active, not connected, or whose controller does not report a travel is skipped - the move itself still guards those,
  - `move_active_stages()` now tracks which axis it is commanding and reports `Error moving Rotary2 to 367.0 deg: ...` instead of `Error moving active stages: ...`. The five moves still share one `try`, so the behaviour is unchanged; only the message gained the axis name and target,
  - verified with the real `resolve_target()` and stub stages: Rotary2 planned at 7/187/367 deg on a 0..360 axis passes (the driver wraps 367 to 7); Stage2 planned at 110/500/999 mm on a 0..220 axis is reported as `2 of 3 outside 0.0 .. 220.0 mm, e.g. [500.0, 999.0]`; a 0..180 rotary asked for 200/260 deg is reported the same way; an unticked axis is skipped entirely. Not yet exercised against real hardware.

### v1.3 - OPTP v3.0/v3.1 sync: tabbed layout, flip mount (AutoBlock), Inst. Config. panel, ScanLog
- Date: 2026-09-26
- Main change: `THz_emission_system_iTC_v1.3.py` + `THz_emission_system_iTC_v1.3.ui` created from v1.2 with the layout, new instruments / controls and flip-mount scan logic of OPTP v3.0-v3.1. This system's instruments, addresses, scan modes (`THz_Scan`, `2D_THz`, `THz_pol`) and their loop orders are unchanged.
- Details:
  - the .py was produced by a 3-way merge (base OPTP v2.9, ours THz v1.2, theirs OPTP v3.1). Checked afterwards: the change set of v1.2 -> v1.3 is identical to OPTP v2.9 -> v3.1 except for this system's own items (addresses, PI Stage1, .ui name, settings name),
  - UI: built from `OPTP_iTC_main_v3.1.ui` so widget names and layout match OPTP. This system's values re-applied: title `THz Emission Measurement System`, Stage1 (PI) ranges +/-26 mm and start 0 for `iPos1` / `stage1JogStep` / `stage1SetPos` / `stage1CurrPos`, `iRot1` / `iRot2` maximum 1000, scan-mode tooltip, rotary2 columns in the rotary1 order,
  - Inst. Config. panel defaults are the former hard-coded values: Lock-in1 `GPIB0::3::INSTR`, Lock-in2 `GPIB0::6::INSTR`, Stage1 `0119001337` axis 1 (row labelled `Stage1 (PI E-861)`; `Stage1_ch` is the GCS axis ID and is passed as a string, as before), Stage2 `73844983` ch 2, Rot1 `27004364`, Rot2 `27005114`, Rot3 `27255894`, iTC `ASRL11::INSTR`, flip mount `37872830` (the OPTP mount). The PI serial is neither VISA nor Kinesis, so Scan devices does not fill that box; it is still saved and restored. Settings key `QSettings("THz_emission_system", "InstrumentConnections")`, separate from OPTP,
  - AutoBlock and ScanLog behave exactly as in OPTP v3.1 (block -> go to T -> stabilisation -> sample soak -> pass -> measurement; blocked again at every end of scan; one ScanLog block per scan in `ScanLog_<date>.txt` in the data folder),
  - runtime environment: the `opto_test` conda env (see the PIPython entry above). The system Python 3.13 on the same PC has no pipython; the test only falls back to a placeholder module when it is run there,
  - verified headless (26/26, `OPTP_System/tests/test_system_sync.py thz`, run in `opto_test` with the real pipython): same checks as MO v2.4 / OPTP image v1.4, plus the PI stage receiving serial `0119001337` and axis `'1'`; registry untouched. Not yet run on the lab PC.

### v1.4 - Power meter from OPTP v3.3: live pump power, PM config tab, Zero, Realtime, Record into the data files
- Date: 2026-09-29
- Main change: `THz_emission_system_iTC_v1.4.py` + `THz_emission_system_iTC_v1.4.ui` created from v1.3 with the power meter features of OPTP v3.3 (same widget names, layout and behaviour).
- Details:
  - UI, copied from `OPTP_iTC_main_v3.3.ui` so widget names, sizes and tooltips are the same (the replaced blocks were first checked to be identical to OPTP v3.2 / v3.1): Power Meter box on the Scan tab = `activePowerMeter`, `PMLed`, `pmSettle` (s, 28 px), `pmAvgNO` (N, 28 px), `pmZero`, `pmRecord`, `PM_realDisp` (Realtime), `PowerMeterDisp` (plain mW, 80 .. 110 px); the Flip Mount / Power Meter row is split 1:1 (`gridLayout_4`) like the Lock-in / Stage rows. Inst. Config.: new sub-tabs `configTabs` under the connection panel, in place of `connVSpacer`: `configTab1` "Tab 1" left empty for later functions (OPTP has Peak search there), `configTab2` "PM config" with `pmWavelength` (default 800 nm), `pmRange` (Auto + the meter's ranges), `pmRefresh` (ms),
  - code: the OPTP v3.2 -> v3.3 changes applied as a patch and checked hunk by hunk: import `PM100D`, `PMLed`, the signals, `powermeter` / `pm_lock` / `_fm_blocked_since`, connect / close, the block time stamp in `set_flipmount_blocked()`, the whole power meter region (live display, `PM_realDisp`, PM config with the meter's real ranges, Zero, Record, `save_pump_power()`), the pre-scan check (`Power meter (Record is on)`), the HDF5 datasets `pump_power_*`, and `PM_realDisp` kept enabled during a scan. The power meter region is now the same text as in OPTP v3.3,
  - by hand, where this system's code differs from OPTP: the `Pump power` line in the ScanLog header; `pump_power = None` at each temperature point; Record right before the one AutoBlock pass (it serves scans with and without temperature points). `_check_scan_stop()` was already there,
  - behaviour as in OPTP v3.3 (see `OPTP_System/OPTP_dev_log.md`, the v3.3 entries): Realtime off by default; wavelength box sent to the meter on connect; Record only with AutoBlock, measured at every temperature point right before the beam is let through (or once before a scan without temperature points), after the settle time, N readings averaged, saved into that point's data file and the ScanLog; a failed reading does not stop the scan. There is no 'Pass -> Soak' beam order here,
  - verified (`opto_test`): `OPTP_System/tests/test_pump_power.py thz` 57/57 (every OPTP check except Pass -> Soak); `tests/test_system_sync.py thz` 25/26 - the one failure is its 'real registry not touched' check: `HKCU\Software\THz_emission_system` holds real connection settings written by a GUI run on this PC at 17:52 today, not by a test; real Windows rendering at 1920 and 1661 px: the Power Meter row lines up with the Lock-in / Stage rows and has the same widths as OPTP, PM config page shown, Tab 1 empty. Real PM100D P0020951 through this version's code: connect (800 nm sent to the meter), Realtime off / on / off, range list at 800 nm = the meter's ranges, 34.99 mW chosen -> meter exactly on it, 1030 nm -> list read again and the range kept, Auto; meter left on 525 nm / auto. The .py and .ui stay CRLF. Not yet run in a real scan.

### v1.5 - Lock-in X Auto Zero and editable reference phase
- Date: 2026-10-04
- Main change: created THz_emission_system_iTC_v1.5.py and THz_emission_system_iTC_v1.5.ui from v1.4; the new entry point loads the matching UI and its title identifies v1.5. The v1.4 files remain byte-for-byte unchanged.
- Details:
  - Both Auto Phase buttons become Auto Zero. Each sends the existing SR830 X Auto Offset command (AOFF 1), then refreshes the actual X readout and chart. No software subtraction or fabricated zero is added; Y/R offset and reference phase are unchanged.
  - Each X display is narrowed to approximately 3/5 of its former width; the adjacent Phase QDoubleSpinBox accepts decimal values, displays an automatic degree suffix, reads the current phase on connection, and writes/reads back on Enter or focus loss. Numeric input alone is sufficient. Untouched fields and programmatic readbacks never write a default phase.
  - Both new controls are enabled only for a connected Lock-in outside scanning. Closing one instrument clears/disables only its controls; failed connection candidates are closed and discarded. Unknown phase readbacks are blank; failed Auto Zero readbacks display --.
  - Phase, Auto Zero and X-readout tooltips have explicit line breaks. Widget names, layout proportions and behavior match OPTP v3.6. Existing active-checkbox defaults, system-specific instruments, connection addresses and scan modes are preserved.
  - PI Stage1 control, arrival checks and THz_Scan / 2D_THz / THz_pol acquisition remain unchanged. The inherited peak-search branch requires 1D_THz, which this system does not offer; no new scan mode or automatic peak search is enabled by this update.
- Verification: test_lockin_controls.py thz --native-preview: 31/31 in opto_test with fake VISA sessions, including a formal THz_Scan acquisition after Auto Zero and numeric-only Phase input. Hidden Windows layout checked at 1920 and 1661 px. AST comparison confirms scan and peak methods unchanged. Shared drivers unchanged; real-instrument Auto Offset/phase checks remain outstanding.

### v1.5 - Sample-soak minute suffix and rich Lock-in tooltip headings
- Date: 2026-10-04
- Main change: Phase, Auto Zero and X-readout tooltips now use a bold control-name heading, a separate explanatory paragraph and explicit short line breaks, matching the other rich-text help in the UI.
- Details:
  - Both Lock-in rows use the same rich-text formatting across all four current systems. Phase still accepts numbers alone and adds its degree suffix automatically.
  - WaitSamStable now has the QSpinBox suffix " min". Typing 17 displays "17 min" while value() remains the integer 17 used by the existing minute-based scan wait. Its tooltip uses the same heading/body format and explains the automatic unit and zero-wait setting. Existing defaults and numeric limits are unchanged.
- Verification: loaded all four current UIs with their real controller initialization in a hidden native Windows window, with temporary QSettings and without connecting instruments. Confirmed bold title formatting, visible paragraph separation and short body lines; inspected rendered tooltip images. Where present, typed a bare numeric wait value and checked the automatic min display, unchanged numeric value, and maximum-value fit at 1661 px window width. Updated the existing tooltip-format assertion for rich text. Application Python files and previous UI versions are unchanged; no acquisition or real-hardware test was needed for this presentation-only change.

### v1.5 - Beam-order alignment with OPTP Soak -> Pass default
- Date: 2026-10-04
- Main change: verified that the existing AutoBlock temperature-scan sequence is already fixed at Block -> temperature stable -> sample soak -> Pass. No passOrder toggle or default change is needed. Updated AutoBlock help to state this order explicitly and identify WaitSamStable as the soak duration.
- Verification: exercised the current pre-acquisition temperature/beam code with fake controller, thread and signal objects, stopping before data-file creation. Confirmed the normal order and no Pass after failed stabilization or interrupted soak. UI comparison confirms only the AutoBlock tooltip changed; application Python and all control defaults are unchanged. No real instruments were operated.

### v1.6 - Save the current interface as PNG beside scan data
- Date: 2026-10-04
- Main change: copied the current v1.5 Python/UI pair to `THz_emission_system_iTC_v1.6.py` and `THz_emission_system_iTC_v1.6.ui`, updated the loaded UI filename/window title, and added Screenshot above the plots, in the existing top spacer area (this system has no Clear Display button). Previous-version files are preserved byte for byte.
- Details:
  - Captures the entire application client area, including visible controls, current tabs and plots, using Qt widget rendering. The button remains available during scans and after completion, with a standard save icon and a multiline tooltip with a bold heading.
  - If a scan file has been assigned in this session, use its exact folder and basename, changing only `.h5` to `.png`. Temperature, mode, extra-info text and dots in the basename are retained. Editing settings for the next scan does not rename or relocate the previous scan's PNG. Repeated clicks replace the same screenshot.
  - Before the first scan file, save in the selected data folder using time, scan mode and the existing sanitized extra-info suffix. Screenshot naming does not change the displayed data filename, data path, HDF5 file or acquisition state.
  - Save through QSaveFile so an encoding/write failure does not destroy an existing PNG. Success reports the path in the status bar and console; failure shows a warning. No instrument reads or commands are issued by the screenshot action.
- Verification: `tests/test_ui_screenshot.py` with this system and `--native-preview`: 12/12 passed, using hidden native Windows Qt windows, temporary settings/files and no instrument connections. Covers actual button wiring, rendered PNG dimensions, pre-scan naming, scan-time availability, exact temperature/dotted filenames, Unicode paths, replacement after editing next-run settings, preservation of data/scan state, partial-write failure and invalid output paths. Across all four systems: 50/50. AST comparison confirms acquisition, temperature, peak search, movement and Lock-in methods are unchanged; all eight prior Python/UI files retain their original hashes. Python syntax and UI XML checks passed.

### v1.6 - Coupled scans use only checked rotary axes
- Date: 2026-10-04
- Main change: synced the selected-axis rotary coupling rule from OPTP v3.7 into the current THz Emission Python/UI pair.
- Details:
  - Ordinary coupled scans pair checked axes with equal point counts while preserving each axis's starting angle and step. Rot1 and Rot2 can scan together with Rot3 unchecked, regardless of Rot3 Step NO. A checked Rot3 participates and must have a matching count. Unchecked axes receive no movement commands; one checked axis scans alone and none checked produces one fixed state.
  - Independent Cartesian planning retains its existing behavior. Calibration still uses Rot2 as master; an unchecked Rot3 no longer requires a Rot3 calibration column. Updated the Coupled tooltip with a bold title, separate explanatory paragraph and short lines.
  - The current entry point passes active_rotaries to the shared planner. Older entry points omit this optional argument and keep their original three-axis rules. Previous Python/UI versions are unchanged.
  - PI Stage1 arrival checks and the available THz_Scan / 2D_THz / THz_pol modes are unchanged. The inherited 1D_THz search branch is still outside the available modes; no automatic peak workflow is enabled.
- Verification: test_rotary_coupling.py thz: 20/20 using the real controller/scan worker with fake instruments and temporary data/settings. Covers unequal inactive-axis counts, checked-axis mismatch rejection, paired acquisition coordinates, no unchecked-axis movements, all eight activation combinations, independent mode, calibration and old-caller compatibility. All four systems total 80/80. No real instruments were operated.

### v1.6 - JSON scan configurations and Lock-in connection readback
- Date: 2026-10-04
- Main change: synchronized the OPTP v3.8 configuration and readback features into the current `THz_emission_system_iTC_v1.6.py` / `THz_emission_system_iTC_v1.6.ui` pair, without creating another version.
- Details:
  - Added **Imp. Conf.** and **Exp. Conf.** beside Screenshot, with standard icons and multiline help using a bold heading and separate body paragraph. Export writes a formatted UTF-8 JSON file; import restores the saved scan inputs and associated software state.
  - Recipes use `THz_Emission.scan_config`, schema version 1 and application version 1.6. Other systems' identifiers are rejected. The explicit field list covers instrument-active choices, mode, stage/rotary starts, steps and repeats, coupling/calibration, temperature inputs and the full ordered temperature list, acquisition Wait(ms)/multipliers, beam controls and power-record options. Repeated and fractional temperature points are retained.
  - Hardware addresses, sensitivity/time constant/phase, power-meter wavelength/range, live readings, realtime toggles, manual instrument actions, data folders and filenames are excluded. Import never moves stages, changes temperature or beam state, or sends instrument settings. A changed Pass-channel selection clears the displayed beam-state indicator to unknown without moving or querying the mount.
  - Validate the complete recipe, numeric types/ranges/precision and finite values before applying it with control signals blocked. Calibration files remain external: export stores their absolute path, import also accepts paths relative to the JSON file, and a missing/invalid referenced file rejects the import. Software calibration tables, button captions, temperature list and timer intervals are restored explicitly. Invalid files and canceled dialogs leave settings unchanged.
  - Import is disabled and guarded during a scan; export remains available and uses the current UI values. QSaveFile replaces a JSON file only after a complete successful write. The .json suffix is added automatically.
  - Connecting either SR830 now reads sensitivity, time constant and phase, including when refreshing an existing selected connection. Signal-blocked display updates do not write defaults back to the instrument. Current/imported Wait(ms) and multipliers stay unchanged. Before connection, existing defaults remain; individual failed queries show unknown values while other successful readings remain available.
  - Includes the existing sample-soak and extra-info inputs. Validation uses the actual PI Stage1 widget limits. PI arrival checks, scan modes and acquisition order are unchanged; no OPTP peak-search controls are added.
  - Existing Auto Zero and Phase editing behavior is retained. OPTP's separate Phase-arrow change is outside this sync. All older Python/UI versions, OPTP v3.8 and shared instrument/scan modules are unchanged.
- Verification: `test_scan_config.py thz --native-preview`: 37/37; `test_lockin_controls.py thz --native-preview`: 38/38, in opto_test with temporary files/settings and simulated instruments. Covers full recipe round-trip, calibration restoration, malformed/cross-system recipes, cancel/write failures, scan-time import/export availability, no instrument calls on import, connection readback without parameter writes, preserved acquisition waits, query failures, Auto Zero/Phase and a simulated acquisition. Native Windows rendering confirms the new buttons fit. Across these three systems: 228/228. Python/UI syntax checks passed; AST comparison confines changes to initialization, connection and scan-control enablement plus the new methods. No real instruments were operated.

### v1.6 - Review of OPTP v3.8 angle-change peak tracking applicability
- Date: 2026-10-04
- Review: checked whether the OPTP correction for the first 1D_THz sweep after an angle change applies to THz Emission.
- Result: the inherited peak-tracking branch requires 1D_THz, while the available modes remain THz_Scan, 2D_THz and THz_pol. There is no accessible corresponding peak workflow to synchronize. No new mode or automatic search is enabled; PI Stage1 and existing acquisition behavior are retained.
- Verification: compared the available scan modes with the peak-tracking condition. The THz Emission v1.6 Python/UI files and older versions remain byte-for-byte unchanged in this update.

### v1.6 - Screenshot camera icon
- Date: 2026-10-04
- Change: replaced the Screenshot button's standard save icon with a camera SVG in the latest Python/UI pair. The local `camera.svg` is referenced by the UI for Qt Designer and loaded relative to the Python file at runtime. Keep this asset beside the Python/UI files when copying the system.
- Scope: button text, tooltip, size, click handler, PNG folder/naming/replacement behavior and scan availability are unchanged. No instrument or acquisition logic changed; older versions retain their original icons.
- Verification: native Windows screenshot checks plus temporary camera-rendering and button-width checks passed 14/14; all four systems total 58/58. Python syntax, UI/SVG XML and a comparison against the pre-change files confirm only the icon assignment/property changed in application code/UI. No real instruments were operated.

### v1.61 - Created from v1.6
- Date: 2026-11-08
- Main change: copied the v1.6 Python/UI pair to `THz_emission_system_iTC_v1.61.py` / `THz_emission_system_iTC_v1.61.ui` as the base for the next round of modifications.
- Details:
  - updated the UI loading path to `THz_emission_system_iTC_v1.61.ui`, the main window title to `THz Emission Measurement System v1.61`, and the exported scan-config `application_version` to `1.61` (import does not check this field, so v1.6 recipes still load),
  - everything else is byte-for-byte identical to v1.6 (CRLF line endings kept); v1.6 and older versions are unchanged.
- Verification: diff against v1.6 shows only the three version lines; Python syntax and UI XML parse checks passed.

### v1.61 - Analysis: sporadic Stage1 stalls during 1 um scans (no code change)
- Date: 2026-11-08
- Symptom (lab use of v1.6): during scans with 1 um Stage1 (PI N-565.360 / E-861) steps, most moves take tens to hundreds of ms, but occasionally the scan pauses for about 3-15 s, then continues by itself. The pauses occur at varying positions, not at one fixed position. No error is printed and the data file is complete.
- Code facts checked:
  - `inst_libs/physik_E861.py` `move_to()`: MOV -> 50 ms predelay -> `pitools.waitontarget()` (polls qONT every 100 ms, timeout 60 s) -> qPOS check (at most 1 s, raises on failure). Inside the move, a silent 3-15 s pause can only come from the ONT wait.
  - The step/position display is refreshed only after a successful move, so a display stuck at point N fits both a stall while moving to N+1 and a stall while acquiring/saving point N. The last console line during a stall (`Move successful! ...` vs `Acquired data point ...`) separates the two.
  - SR830 reads use a 1 s VISA timeout without retry and would print an error, so they are ruled out. `h5_file.flush()` writes to `C:\GUI_pyqt\THz_emission_Data` (local, not OneDrive, git-ignored); a stall there is unlikely but not excluded.
  - No per-step timing is logged, so the stall location is inferred, not measured.
  - `on_target_tolerance_mm` defaults to 0.001 mm, which equals the minimum scan step (positions are rounded to 0.001 mm in `generate_position_sequence`), and the check is `error <= tol`. The qPOS check therefore cannot detect a missed 1 um step; arrival currently relies on ONT alone.
- Most likely cause (hypothesis, not measured): NEXACT step/analog mode switching. Repeated small moves in one direction use up the piezo analog range; the controller then takes a full step, overshoots and corrects back in analog mode. This is usually fast, but occasionally the axis alternates near the mode boundary, and each excursion restarts the controller's settling timer, so ONT stays false for seconds. This fits stalls at varying positions; they should correlate with the distance travelled since the last full step rather than with absolute position.
  - Not excluded: external vibration pushing the settled axis out of the settling window (would correlate with time, e.g. a cryostat compressor or pump, not with position), or a stall outside the stage move (flush/disk).
  - An earlier assumption of a fixed-position mechanical defect was withdrawn after the lab report that stalls occur at multiple positions.
- Planned approach (not implemented):
  1. Diagnosis with unchanged scan behavior: replace `waitontarget()` with an equivalent ONT polling loop that also reads qPOS; log every move longer than 1 s (target, duration, ONT toggles, min/max/final error); time move / lock-in / flush per point and summarize stalls at the end of the scan.
  2. Fix according to the result: (A) hunting within about 0.2 um with ONT toggling -> accept arrival when qPOS stays within 0.2 um for at least 200 ms, and re-check qPOS after the lock-in reading; (B) error stays above 0.2 um while creeping -> no early acceptance; re-issue MOV, or back off a few um and re-approach from the same side; (C) stall outside the move -> investigate disk/antivirus instead. In all cases tighten the qPOS tolerance from 1 um to 0.2 um (about 1.3 fs, using the ~40 fs per ~6 um stage-travel ratio noted in the code).
  - Constraints: no E-861 parameter changes, no pipython changes, tolerance strictly below the scan step.
- Open questions: change the shared `physik_E861.py` (also imported by v1.0-v1.6) or enable the new behavior only in v1.61; on-site check of the last console line during a stall.
- Side note (unrelated to the stalls): if Lock-in Realtime is checked before a scan, its GUI-thread timer keeps querying the same SR830 during the scan, concurrently with the scan thread.

### v1.61 - Measurement: cause of the sporadic Stage1 stalls
- Date: 2026-11-09
- Setup: a standalone probe script (not part of the project) repeated the GUI's per-point sequence on the real instruments with the GUI closed: MOV -> 50 ms -> IsControllerReady/qERR -> qONT polling -> wait1 -> lock-in1 OUTP? 1/2 -> HDF5 write + flush, tracing qONT, qPOS and IsMoving every ~20 ms during each wait. 1000 x 1 um positive steps from 7.571 to 8.571 mm; E-861 VEL 5 mm/s, ACC 50; SR830 (GPIB0::3) time constant 0.3 s -> wait1 600 ms. Only MOV commands and queries were sent; no controller parameter was written; the stage was returned to 7.571 mm afterwards.
- Controller on-target criterion (read only with `SPA?`): Settlewindow 0x36 = 10 counts at 2,000,000 counts/mm (0xE/0xF) = +/-5 nm; Settletime 0x3F = 0.01 s. ONT therefore needs the position within +/-5 nm for 10 ms.
- Results:
  - Move time per step: 89.6 % below 0.3 s (median 0.25 s), 7.8 % 0.3-0.5 s, 1.0 % 0.5-1 s, 0.9 % 1-3 s, 0.5 % 3-10 s, 0.2 % above 10 s (12.2 s, and one move still without ONT after 30 s). Moves of 1 s or longer lost about 87 s of 351 s total move time.
  - In every slow move the stage was already at the target: after 0.3 s the error stayed within +/-20 nm (at most +/-15 nm), but only 0-75 % of the polls were within +/-5 nm and IsMoving stayed mostly true. The NEXACT servo keeps hunting at the nm level and never holds +/-5 nm for 10 ms, so ONT stays false. Some stalls sat at a small static offset (e.g. -8..-5.5 nm, +9..+12.5 nm). No slow creep towards the target was seen.
  - Stalls are irregular in position (spacing 14-209 steps), with no periodic pattern.
  - Lock-in reads took at most 31 ms and the HDF5 flush at most 3.4 ms, so acquisition/disk is ruled out.
  - The first move after connecting took about 4.5 s because pipython sends a one-time `HLP?` query (`HasIsControllerReady()` inside `waitontarget()`); this is not a controller delay.
- Conclusion: case (A) of the 2026-11-08 analysis. The data taken after a stall are fine (+/-15 nm is about +/-0.1 fs); the stall only costs time, but a move beyond the GUI's 60 s timeout skips the point with "Error moving Stage1 ...". The earlier mode-switching hypothesis is not needed to explain the data.

### v1.61 - Stage1 arrival check: ONT or 50 nm position hold (shared `inst_libs/physik_E861.py`)
- Date: 2026-11-09
- Main change: `LinearStage.move_to()` in the shared PI driver no longer waits for ONT alone. An axis that has stayed within 50 nm of the target for 200 ms is accepted as arrived, so the nm-level hunting measured above no longer stalls the scan. The driver is shared, so THz Emission v1.0-v1.61 all use the new check; the v1.61 Python/UI files are not changed by this fix.
- Details:
  - `pipython.pitools.waitontarget()` is replaced by an own loop in the application driver: after MOV and the 50 ms predelay, `checkerror()` once (as `waitontarget()` did through `waitonready()`), then qONT + qPOS every ~20 ms (previously qONT every 100 ms).
  - Arrival: ONT true and |qPOS - target| <= tolerance -> return at once; or |qPOS - target| <= tolerance for `position_hold_ms` (200 ms) in a row while ONT stays false -> return with a `[PI] Axis 1: ONT still false ...` console line giving the time and final error. An excursion beyond the tolerance restarts the 200 ms hold.
  - `on_target_tolerance_mm` default 0.001 mm -> 0.00005 mm (50 nm). The old 1 um equalled the scan step, so a stage that had not moved still passed the qPOS check. 50 nm is strictly below the 1 um minimum step (positions are rounded to 0.001 mm), so an ONT flag left over from the previous move cannot be taken for arrival.
  - Constructor parameter `settle_timeout_ms` (1 s qPOS check after ONT) replaced by `position_hold_ms=200`. No caller passed either parameter.
  - Timeout (default 60 s, unchanged): `checkerror()` first, then `RuntimeError` with the last position, error and ONT state (was pipython's `SystemError: waitontarget() timed out`). The GUI catches both with `except Exception`.
  - `IsControllerReady` and pipython's one-time `HLP?` are no longer queried in moves, so the first move after connecting no longer takes about 4.5 s.
  - Not changed: E-861 parameters (ONT settle window and time), the pipython package, `home()` (still uses `waitonreferencing()`), the 50 ms predelay, the travel-range check, and the device lock.
- Verification:
  - Fake-controller logic test 8/8: normal ONT arrival; stale ONT at the old position; hunting within +/-15 nm accepted after the 200 ms hold; hold restarted by an 70 nm excursion; stuck 80 nm away -> timeout; ONT true but 80 nm away -> timeout; ONT true without moving (1 um away) -> timeout; out-of-range target -> ValueError. No `HLP?` query was sent.
  - Replaying the rule on the 15 recorded slow moves (1.05-30.3 s): all would end within 0.38-0.50 s, saving about 79 s per 1000 steps.
  - Python compile check passed. The new code has not yet been run on the real stage.
