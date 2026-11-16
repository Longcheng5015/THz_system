# Polarization Calibration Development Change Log

This document records the overall development and debugging history for the Polarization & Power Calibration project (`Polarization_cali`), including version updates, bug fixes, and functional changes.

---

## Version History

### v1.0
- **Date**: 2026-08-06
- **Main Change**: Initial release of the Polarization & Power Calibration UI program (`Polarization_cali_v1.0.py` and `Polarization_cali_v1.0.ui`).
- **Details**:
  - Developed a standalone PySide6 GUI for automated optical polarization and power calibration.
  - Connected instruments: 3 x Thorlabs Rotary Stages (Stage 1: 1/2 HWP, Stage 2: Polarizer, Stage 3: Aux) and 1 x Thorlabs PM100D Power Meter.
  - Implemented auto-discovery for VISA resources (PM100D) and populated default OPTP stage serial numbers (`"27004364"`, `"27255894"`).
  - Designed the power stability detection function (`check_power_stability`), requiring 3 consecutive wait intervals (4 consecutive power readings) to have variation $\le \text{Tolerance}$ before declaring stability.
  - Added two calibration modes:
    1. **`power` Mode**: Fixed Stage 2 angle, scans Stage 1 angles, waits for power stability, and records Stage 1, 2, 3 positions and power.
    2. **`Polar` Mode**: Target power specified by user. For each Stage 1 angle, searches Stage 2 to achieve target power within tolerance.
  - Integrated Stage 2 polar search algorithms: **Sequential Step (方案A, default)** and **Binary Search (方案B)**.
  - Handled disabled/unchecked stages by recording `NaN` in MAT/HDF5 data files and leaving entries blank in CSV files.
  - Added manual debugging controls for each stage (Move To absolute angle and Step + / Step - relative moves).
  - Integrated real-time data plotting using `pyqtgraph.PlotWidget`.
  - Exported calibration data simultaneously into `.mat`, `.csv`, and `.h5` (HDF5 via `h5py`) files.
  - Preserved strict core reusability: reused existing `func_cores` and `inst_libs` without modifying any shared codebase.

### v1.0.1
- **Date**: 2026-08-06
- **Main Change**: Fixed LedIndicator widget attribute error during instrument connection.
- **Details**:
  - Corrected `led.setChecked()` call to `led.status = True / False` to match `MyWidget.py` custom `LedIndicator` property setter.

### v1.0.2
- **Date**: 2026-08-06
- **Main Change**: Reorganized Stage controls into 3 side-by-side GroupBoxes and ensured Step+ / Step- buttons.
- **Details**:
  - Arranged Stage 1, Stage 2, and Stage 3 into three distinct `QGroupBox` panels aligned horizontally from left to right (`grp_stage1`, `grp_stage2`, `grp_stage3`).
  - Positioned individual `Step +` (`btn_stageX_step_plus`) and `Step -` (`btn_stageX_step_minus`) buttons alongside `Move To` controls within each Stage panel.

### v1.0.3
- **Date**: 2026-08-06
- **Main Change**: Replaced Stop angle setting with Step NO. (number of steps) for each Rotary Stage.
- **Details**:
  - Changed stage parameter inputs from `[Start, Step, Stop]` to `[Start (°), Step (°), Step NO.]` in UI (`spin_stageX_no` QSpinBox).
  - Updated sequence generator `build_seq` to generate angle array as `[start + i * step for i in range(no)]`, perfectly aligning with OPTP `ScanPlanner` logic.

### v1.0.4
- **Date**: 2026-08-06
- **Main Change**: Reordered UI layout: moved Calibration Settings below the 3 Stage boxes and above the real-time PlotWidget chart.
- **Details**:
  - Adjusted vertical component hierarchy in `Polarization_cali_v1.0.ui` to place `grp_config` below `layout_three_stages` and directly above execution controls and `powerChart`.

### v1.0.5
- **Date**: 2026-08-06
- **Main Change**: Renamed Calibration Mode options to `Power` and `Polarization`.
- **Details**:
  - Updated UI dropdown (`combo_scan_mode`) options to `Power` and `Polarization`.
  - Updated tooltips and worker thread branch detection to support `Power` and `Polarization` mode names.

### v1.0.6
- **Date**: 2026-08-06
- **Main Change**: Swapped relative step buttons position: placed `Step -` on the left and `Step +` on the right.
- **Details**:
  - Adjusted button layout in Stage 1, Stage 2, and Stage 3 panels so `btn_stageX_step_minus` (`Step -`) is placed on column 3 and `btn_stageX_step_plus` (`Step +`) is placed on column 4.

### v1.0.7
- **Date**: 2026-08-06
- **Main Change**: Added PM100D CheckBox, unified device connection buttons, and removed Scan Devices button matching OPTP v1.7.
- **Details**:
  - Added CheckBox for PM100D (`chk_pm100d_enable`, default: checked) so users can enable/disable power meter connection and readings.
  - Replaced individual device connect buttons with unified **`Connect Enabled Devices`** (`btn_connect_all`) and **`Disconnect All`** (`btn_disconnect_all`) buttons.
  - Automatically iterates and connects all checked instruments (PM100D, Stage 1, Stage 2, Stage 3) in order, homing each stage upon connection.
  - Removed the `Scan Devices` button as requested.

### v1.0.8
- **Date**: 2026-08-06
- **Main Change**: Removed leftover `scan_connected_devices` call in `__init__`.
- **Details**:
  - Removed outdated `self.scan_connected_devices()` method call from `PolarizationCaliApp.__init__()`, resolving `AttributeError` during startup.

### v1.0.9
- **Date**: 2026-08-06
- **Main Change**: Implemented OPTP v1.7 guarded temporary instance connection & automatic cleanup flow.
- **Details**:
  - Implemented temporary local instances (`stg_temp` / `pm_temp`) inside `connect_all_devices()`.
  - If homing or enabling fails, the exception block immediately executes `stg_temp.close()`, preventing locked Kinesis handles/DLL sessions and allowing clean retries.

### v1.0.10
- **Date**: 2026-08-06
- **Main Change**: Added Exit button and implemented default disconnect-before-close logic.
- **Details**:
  - Added `Exit Program` button (`btn_exit`) in the top connection panel of `Polarization_cali_v1.0.ui`.
  - Implemented `exit_app()` slot and overridden `closeEvent()` window close handler to automatically stop calibration scans and execute `disconnect_all_devices()` before exiting the application window.

### v1.0.11
- **Date**: 2026-08-06
- **Main Change**: Added exit confirmation dialog, active device detection before disconnect, and fixed event loop bug.
- **Details**:
  - Added `QMessageBox.question` confirmation dialog on exit ("Are you sure you want to exit the application?").
  - Fixed infinite recursion loop between `exit_app()` and `closeEvent()`.
  - Added `has_connected_devices` check in `disconnect_all_devices()` and `closeEvent()` so disconnect cleanup only runs if at least one instrument is actually connected.

### v1.0.12
- **Date**: 2026-08-06
- **Main Change**: Fixed PySide6 QUiLoader window close target (`self.ui.closeEvent`).
- **Details**:
  - Bound `self.ui.closeEvent` directly to `self.on_ui_close_event`.
  - Updated `exit_app()` to trigger `self.ui.close()`, bringing up the confirmation box (`QMessageBox.question`) and calling `QApplication.quit()` cleanly when confirmed.

### v1.0.13
- **Date**: 2026-08-06
- **Main Change**: Added initial system welcome and readiness log messages upon startup.
- **Details**:
  - Automatically emits initialization log messages into `txt_log` as soon as the main window opens so users immediately see system readiness status.

### v1.0.14
- **Date**: 2026-08-06
- **Main Change**: Converted all code comments, tooltips, UI text options, and log messages to English.
- **Details**:
  - Translated all remaining Chinese comments, algorithm option labels, tooltips, and log text strings to pure English across both `Polarization_cali_v1.0.py` and `Polarization_cali_v1.0.ui`.

### v1.1.0
- **Date**: 2026-08-06
- **Main Change**: Created standalone Data Fitting & Analysis application (`Polarization_fit_v1.0.py` and `Polarization_fit_v1.0.ui`).
- **Details**:
  - Implemented file parsers for `.mat`, `.csv`, and `.h5` files exported from calibration scans.
  - Implemented Power Mode fitting (Malus Law $\cos^2$, Sine Wave, Polynomial, Linear models) to convert Stage 1/2 angles directly into predicted optical power.
  - Implemented Polarization Mode fitting to calculate required Stage 1 relative step ($\Delta \theta_1$) for constant optical power given any Stage 2 angle change ($\Delta \theta_2$).
  - Built interactive prediction calculator and real-time `pyqtgraph` scatter + smooth fitted curve display.
  - Formatted LaTeX/mathematical equations, $R^2$ scores, and RMSE parameters in the text output box.

### v1.1.1
- **Date**: 2026-08-06
- **Main Change**: Removed external `pandas` dependency in favor of Python standard library `csv` module.
- **Details**:
  - `pandas` is a third-party Python library for data manipulation/CSV handling.
  - Replaced `pd.read_csv()` with Python's built-in `csv.DictReader`, so `Polarization_fit_v1.0.py` zero-depends on external `pandas` package and runs out of the box in standard python environments.

### v1.1.2
- **Date**: 2026-08-06
- **Main Change**: Installed `pandas` in active conda environment (`opto_test`) and cleared pip cache.
- **Details**:
  - Installed `pandas` into `opto_test` environment via `pip install pandas`.
  - Executed `pip cache purge` to remove cached wheel files (freed 365.3 MB of cache).
  - Restored `pandas` DataFrame parsing for data import in `Polarization_fit_v1.0.py`.

### v1.1.3
- **Date**: 2026-08-06
- **Main Change**: Registered `pg.PlotWidget` custom widget with `uiLoader` in `Polarization_fit_v1.0.py` and executed automated smoke tests.
- **Details**:
  - Registered `pg.PlotWidget` with PySide6 `QUiLoader` via `uiLoader.registerCustomWidget(pg.PlotWidget)`.
  - Resolved `AttributeError: 'PySide6.QtWidgets.QWidget' object has no attribute 'setBackground'` when rendering the main chart.
  - Passed automated smoke testing for UI instantiation, custom widget registration, fitting math, and clean exit.

### v1.1.4
- **Date**: 2026-09-29
- **Main Change**: `inst_libs/thorlabs_PM100D.py` now talks to the PM100D over pyvisa (SCPI) instead of the Thorlabs TLPM DLL. The meter (P0020951) was switched to its NI-VISA driver with the Thorlabs Power Meter Driver Switcher; on the TLPM driver pyvisa does not see it, and on the NI-VISA driver the old TLPM code no longer finds it.
- **Details**:
  - Transport: `open()` / `close()` / `write()` / `query()` use pyvisa like `stanford_SR830` (read/write termination `
`, `timeout_ms`, `query_delay_s`; `close()` leaves the shared ResourceManager open). `query()` honours `retry_count` / `retry_delay_s`. `idn()`, `set/get_wavelength_nm()`, `measure_power()` are now SCPI (`*IDN?`, `SENS:CORR:WAV`, `MEAS:POW?`). All the SCPI methods that used to raise ("Raw SCPI ... not supported by the TLPM driver transport") now work.
  - `list_resources()` asks VISA for `USB?*::0x1313::0x8078::?*::INSTR` only (0.06 s; a full VISA scan of the serial/GPIB ports took 6-30 s on this PC). `list_resources_with_idn()` returns the real `*IDN?`.
  - No `viClear()` on open or before a retry: measured on this meter, the first query after a clear timed out 15/15 times (8/15 within a running session), which made the first connect take 12.5 s. A query that gets no reply recovers without a clear.
  - "Busy" is now detected with pyvisa's `error_resource_busy`; the old constant `-1073807343` was actually VI_ERROR_RSRC_NFOUND, so a wrong address was reported as "PM100D is busy".
  - SCPI headers corrected after the firmware (2.6.0) answered "Undefined header": line frequency `SYST:LFR`, zeroing `SENS:CORR:COLL:ZERO:INIT/ABOR/STAT/MAGN`, responses `SENS:CORR:POW:PDI:RESP`, `SENS:CORR:POW:THER:RESP`, `SENS:CORR:ENER:PYRO:RESP`, delta state `SENS:<mode>:REF:STAT`, photodiode low-pass `INP:PDI:FILT:LPAS:STAT`. Display brightness/contrast are 0..1 floats (were parsed as int and raised).
  - Interface used by `Polarization_cali_v1.0.py` is unchanged (constructor arguments, `open`, `idn`, `measure_power`, `close`). Its `query_delay_s=0.1` is now applied, so one power reading takes ~100 ms (the meter itself answers in ~3 ms).
  - `inst_libs/test_PM00D.py`: "not found" message now points at the VISA driver instead of TLPM.
  - Verified on the PM100D P0020951 with the S302C thermal sensor (opto_test env): connect flow 3x (0.15 s each), 96 calls each followed by `SYST:ERR?` with no error, set -> read back -> restore for unit, averaging, wavelength, auto range, range, attenuation, beam diameter, delta state, low-pass and brightness; settings left as found (W, 525 nm, avg 1, auto range, POW). Not supported by this sensor (instrument reports "Wrong sensor type"/"Illegal parameter"): energy range, energy, energy density, temperature. `zero_initiate()` / `set_line_frequency()` not executed (zeroing needs the sensor covered).

### Polarization_cali v1.1
- **Date**: 2026-11-02
- **Main Change**: Copied `Polarization_cali_v1.0.py` / `Polarization_cali_v1.0.ui` to `Polarization_cali_v1.1.py` / `Polarization_cali_v1.1.ui` as the base for the next changes. The v1.0 files are unchanged.
- **Details**:
  - Only the version strings differ from v1.0: the loaded UI file (`Polarization_cali_v1.1.ui`), the module docstring, the class docstring, the startup log line and the window title / header label in the UI.
  - Checked in the opto_test env (offscreen): the window loads with the title "Polarization & Power Calibration System v1.1".

### Polarization_cali v1.1 (tab layout)
- **Date**: 2026-11-02
- **Main Change**: The main window now uses a `QTabWidget` like `OPTP_iTC_main_v4.01.ui`. Every control of the previous main window is in tab 1; tab 2 is empty.
- **Details**:
  - UI (`Polarization_cali_v1.1.ui`): `centralwidget` holds a new `centralLayout` that contains `tabWidget`. It has two tabs: `tab` "Calibration", whose layout is the old `mainLayout` with every item unchanged (title, connection box, three stage boxes, settings, run controls, progress bar, `powerChart`, `txt_log`), and `tab_2` "Tab 2", which is empty. The tab bar uses the same stylesheet as OPTP (bold 11 pt, grey unselected text).
  - No Python changes were needed: widgets are still found by object name, and `lbl_current_power` is still added to `layout_pm100d`, so it sits inside tab 1.
  - Checked with the Windows platform plugin at 1380x920 (opto_test env): all widgets are inside `tab`, `tab_2` has no children, and nothing is clipped. The tab bar makes `powerChart` about 50 px shorter (217 px instead of 269 px). The selected tab is drawn dark, not red: the windows11 style ignores the `:selected` colour, and OPTP v4.01 renders the same way.

### Polarization_cali v1.1 (Inst. Config. tab)
- **Date**: 2026-11-02
- **Main Change**: The title is back above the tabs, as in OPTP v4.01. The instrument addresses/serials and a new **Scan devices** button are in tab 2, which is now "Inst. Config." and follows OPTP's Instrument Connections panel. The addresses are still editable drop-down lists.
- **Details**:
  - UI (`Polarization_cali_v1.1.ui`):
    - `lbl_title` moved from tab 1 to `centralLayout`, above `tabWidget`.
    - `combo_pm100d_res` and `combo_stage1/2/3_serial` were taken out of the tab 1 boxes; their enable checkboxes, LEDs, Home buttons and Connect / Disconnect / Exit stay in tab 1.
    - The `tab_2` title is now "Inst. Config." (was "Tab 2"). It holds `connGroup` "Instrument Connections", laid out like OPTP's `connGroup`: `btn_scan_devices` at the top right, an "Instrument" / "Address / Serial" header row, then one row per instrument with the same combo object names and the same editable behaviour (min width 200 px, tooltips as in OPTP). Spacers keep the box at the top left.
  - Python (`Polarization_cali_v1.1.py`): new `scan_devices()`, connected to `btn_scan_devices`, works like OPTP `scan_devices()`: it fills each list with what the scan finds and keeps the value already in the box, so a scan never changes the setting. The stage lists use `InstrumentTools.list_kinesis_serials()` (newly imported from `inst_tools`). The PM100D list uses `PM100D.list_resources()`, which only asks VISA for PM100D USB resources, instead of OPTP's full VISA scan, which took 6-30 s on this PC (see v1.1.4). Scan results and failures go to the log box. Connect still reads the same combos, so nothing else changed.
  - Not ported from OPTP: saving/restoring the addresses with `QSettings`; the defaults still come from `init_device_defaults()`.
  - Checked with the Windows platform plugin at 1380x920 (opto_test env): the title is outside the tabs, all connection widgets are in `tab_2`, nothing is clipped, and the defaults appear in the boxes. A real Scan devices click took 0.14 s and logged "PM100D (VISA) devices found: none" and "Kinesis devices found: ['27255354']". Every box kept its value (P0020951 / 27004364 / 27255894 / 27255894), and the stage lists offered 27255354.

### Polarization_cali v1.1 (Power mode: Stage 2 fixed)
- **Date**: 2026-11-02
- **Main Change**: Power mode scans Stage 1 only again. Stage 2 and Stage 3 go to their Start angle once and stay there, so the result is a power vs Stage 1 (HWP) curve, which is what the Power fit in `Polarization_fit_v1.0.py` expects. A Stage 2/3 that is not enabled **or not connected** is not moved and is recorded as NaN, so Power mode runs with only Stage 1 (+ PM100D) connected.
- **Details**:
  - Removed the Stage 1 / Stage 2 1-to-1 coupled movement and the padding of the shorter sequence (added 2026-08-09, see `Pol_Cali_dev_log.md`). With the UI defaults it produced 91 points, and the last 72 had Stage 1 at 90° while only Stage 2 moved. Number of points = Stage 1 Step NO.; Stage 2 Step / Step NO. are not used in Power mode.
  - Before: a stage that was checked but not connected was not moved, but its commanded angle was recorded. Now Stage 2/3 positions are recorded as their Start angle only when the stage is enabled and connected, otherwise as NaN (blank in CSV, NaN in MAT/HDF5). The log states the fixed values, e.g. `Power mode: Stage 2 = 30.0°, Stage 3 = nan° (NaN = not enabled or not connected)`. Stage 1 recording is unchanged.
  - The Power mode tooltip now describes this behaviour.
  - Tested without hardware (opto_test env): the real app ran Start Calibration with fake stages and a fake PM (power = 10 mW·cos²(2θ1)), Wait Time 0, and saved the data. Stage 1 0..40° in 10° steps, Stage 2 Start 30° (Step NO. 91), Stage 3 Start 15°. (A) All connected: Stage 1 moved 0, 10, 20, 30, 40; Stage 2 moved once to 30; Stage 3 moved once to 15; 5 points; CSV/MAT hold 30 / 15. (B) Stage 2/3 unchecked and not connected and (C) checked but not connected: only Stage 1 moved, 5 points, Stage 2/3 NaN in the points and MAT, blank in the CSV, no error. Not yet tested on the real stages and PM100D.

### Polarization_cali v1.1 (Power mode needs Stage 1)
- **Date**: 2026-11-02
- **Main Change**: In Power mode, Start Calibration refuses to start if Stage 1 is not enabled or not connected. It shows a "Cannot Start Scan" warning and writes the reason to the log.
- **Details**:
  - `start_calibration()` checks before it clears the chart or builds the worker, so a refused start leaves the previous data and curve on screen. The two messages: "Stage 1 is not enabled. Check 'Enable Stage 1' and connect it first." and "Stage 1 is not connected. Click 'Connect Enabled Devices' first.", each followed by "Scan not started."
  - Polarization mode is not affected.
  - Tested without hardware (opto_test env, real app, dialog captured): Power + Stage 1 unchecked (even while connected) → warning on the main window, no worker, Start button still enabled. Power + Stage 1 checked but not connected → warning, no worker. Power + Stage 1 connected → scan ran, 5 points. Polarization + Stage 1 not connected → started as before, 3 points.

### Polarization_cali v1.1 (dated save folders, PM100D Config, run buttons)
- **Date**: 2026-11-02
- **Main Change**: Data is saved in a dated folder `cali_data/<Month>/<Month>_<dd>` (OPTP's `OPTP_Data` logic). Tab 2 has a **PM100D Config** box (wavelength, power range, refresh) ported from OPTP's PM config. Connect / Disconnect / Exit moved under Start / Stop Calibration, and both rows are now inside the "Calibration Settings & Parameters" box.
- **Details**:
  - Save folder: new `setup_data_folder()` creates `Polarization_cali/cali_data/<full month name>/<month>_<dd>` (e.g. `cali_data/November/November_02`) and puts it in Save Dir. It is called at startup and at every Start Calibration (so a scan after midnight goes into the new day's folder), unless Browse picked a folder (`is_custom_save_path`), as in OPTP. File names are unchanged (`<prefix>_<YYYYmmdd_HHMMSS>.mat/.csv/.h5`). A path typed into Save Dir by hand is replaced at the next scan; only Browse keeps a custom folder (same as OPTP). The unused `import os` was removed.
  - PM100D Config (`grp_pm_config` in tab 2, under Instrument Connections): `spin_pm_wavelength` (nm, default 800, 185-20000, limited to the sensor on connect), `combo_pm_range` (Auto + the meter's real ranges), `spin_pm_refresh` (ms, default 500, 100-10000). Same widgets, limits and tooltips as OPTP `pmWavelength` / `pmRange` / `pmRefresh`. `load_pm_settings()`, `probe_pm_ranges()`, `show_pm_ranges()`, `set_pm_range()`, `set_pm_wavelength()` are ported from OPTP v4.01, logging to the log box instead of the terminal. On connect the wavelength box is sent to the meter and the ranges are read from it (inside the guarded connect, so a failure closes the session). Wavelength is sent when editing finishes; a range choice is applied at once. Refresh sets the idle monitor timer (power + stage positions), which was a fixed 500 ms. The box is disabled while a scan runs, because the scan thread is then reading the meter (OPTP uses a lock instead).
  - Layout (tab 1): `layout_run` is now a grid inside `grid_config` (row 1, spanning all 10 columns). Its row 0 holds Start, Stop and the save-dir row (`layout_save`); row 1 holds Connect Enabled Devices under Start, Disconnect under Stop, and Exit Program. "Hardware Instrument Connections" keeps the PM100D checkbox, its LED and the power readout.
  - Checked with the Windows platform plugin: Connect/Start both 145 px, Disconnect/Stop both 97 px, all six inside `grp_config`; `powerChart` is 187 px high at 1380x920 (was 217) and 307 px at 1920x1040.
  - Tested without hardware (opto_test env, real app, fake SCPI meter with the S302C ranges and error queue). Connect sent 800 nm and the box range became 185-20000. The range box showed Auto / 3.695 mW / 34.99 mW / 347.9 mW / 3.477 W on Auto, and the error queue was emptied. Picking 34.99 mW fixed the meter at 0.03499 W; Auto set auto range; wavelength 1030 was sent; Refresh 1000 set the monitor interval to 1000 ms. Startup created and showed `cali_data/November/November_02`. With the date moved to 1 December, a scan saved its .csv/.h5/.mat into `cali_data/December/December_01`, and after Browse into the chosen folder. PM100D Config was disabled during the scan and enabled after it. Not yet tested on the real PM100D.

### Polarization_cali v1.1 (PM100D settings in tab 1, one-row buttons)
- **Date**: 2026-11-02
- **Main Change**: The three PM100D settings moved from tab 2 into the tab 1 PM100D row, between the PM100D LED and the red power readout (this is where they were wanted; the tab 2 box was a misunderstanding). The instrument and run buttons are now on one row with shorter labels: **Conn. Inst. / Close Inst. / Exit** left of **Start / Stop**, then Save Dir, Browse and a narrower Prefix box.
- **Details**:
  - UI, PM100D row (`layout_pm100d`): checkbox, LED, then `lbl_pm_wavelength` "Wavelength (nm):" + `spin_pm_wavelength`, `lbl_pm_range` "Power range:" + `combo_pm_range`, `lbl_pm_refresh` "Refresh (ms):" + `spin_pm_refresh`, then a stretch; the power readout is still appended at runtime, so it sits at the right end. Same widget names, limits and tooltips as before. The two spin boxes and the combo have a Fixed size policy; the combo has `minimumContentsLength` 8, so range labels added at connect still fit. Fixed spacers (20 / 12 / 12 px) separate the pairs. `grp_pm_config` was removed from tab 2, which again holds only Instrument Connections.
  - `led_pm100d` is fixed at 28x28. With the Fixed controls next to it, the row had no spare width, so the LED shrank to its 10 px minimum (a dot). 28 px matches the stage LEDs' cell height, so it draws the same 20 px circle.
  - UI, run row: `layout_run` is now one QHBoxLayout inside `grid_config` (`layout_save` removed): `btn_connect_all` "Conn. Inst.", `btn_disconnect_all` "Close Inst.", `btn_exit` "Exit", a 16 px gap, `btn_start_scan` "Start", `btn_stop_scan` "Stop", Save Dir, Browse, Prefix. `line_file_prefix` has a 100 px maximum width. The five buttons have a 70 px minimum width; with the global QPushButton stylesheet they otherwise shrink to their text (Exit 30 px, Start/Stop 36 px).
  - Python: during a scan only `spin_pm_wavelength` and `combo_pm_range` are disabled (they talk to the meter); Refresh stays editable. Removed the runtime `btn_disconnect_all.setText("Disconnect")`; the label now comes from the .ui. The startup hint and the Power-mode "not connected" message now name 'Conn. Inst.'.
  - Checked with the Windows platform plugin at 1380x920 and 1920x1040:
    - Nothing is clipped, also with the widest values (20000 nm, 10000 ms, "347.9 mW", "Power: 3477.0000 mW").
    - Buttons are 70 px each; the Save Dir box is 656 / 1196 px wide and the default path needs 344 px; Prefix is 100 px and "pol_cali" needs 40 px.
    - `powerChart` is 217 / 337 px high.
  - All earlier functional tests re-run and pass, with the same fake instruments as before:
    - PM settings: connect, range, wavelength and refresh.
    - Dated folders and Browse.
    - Power-mode Stage 1 check, including the new 'Conn. Inst.' message.
    - Power-mode NaN cases.
    - Wavelength and range are disabled during a scan and re-enabled after it; Refresh stays enabled.

### Polarization_cali v1.1 (power readout position)
- **Date**: 2026-11-02
- **Main Change**: The red power readout in the PM100D row moved slightly left: a 40 px fixed spacing is added after it (`layout_pm100d.addSpacing(40)` in `setup_ui_events()`, right after the readout is appended).
- **Details**: Checked with the Windows platform plugin: the readout's right end is now 50 px from the box's inner right edge at both 1380x920 and 1920x1040. Before, it touched the edge.

### Polarization_cali v1.1 (Polarization: Model Tracking, split tolerance)
- **Date**: 2026-11-02
- **Main Change**: New default Polarization search **Model Tracking (Option C)**: one coarse Stage 1 scan builds a model, then every Stage 2 angle is predicted and corrected with the measured power. Tolerance is split into **Stability Tol** and **Target Tol**. Hover texts explain the logic. Polarization mode now needs Stage 1, Stage 2 and the PM100D before it starts.
- **Details**:
  - Model Tracking (`CalibrationWorker.run_model_tracking()`):
    1. Coarse scan of Stage 1 (its Start / Step / Step NO.) at the first Stage 2 angle. Fit P = A·cos²(2(θ1 − θ0)) + B as P = c0 + c1·cos4θ1 + c2·sin4θ1 by linear least squares (`fit_hwp_model()`), which needs no start values.
    2. The scan stops with a message (`CalibrationAbort`, no traceback) if Target Power is outside B + 5 % .. 90 % of A.
    3. Start on the falling slope at the solution nearest the middle of the coarse range.
    4. For each Stage 2 angle, predict Stage 1: the previous solution, then a straight line through the last two. This learns the sign of dθ1/dθ2, so the stage mounting direction does not matter.
    5. Measure, then correct by Δθ1 = (x_target − x_measured)/2 with x = arccos√((P − B)/A) (`hwp_phase_deg()`), at most 3° per step (`MT_MAX_STEP_DEG`), up to 5 corrections (`MT_MAX_CORRECTIONS`).
    6. Accept when |P − target| ≤ Target Tol and stable. Otherwise record the closest measurement with Stable = False and go on. An angle interrupted by Stop is not recorded.
  - UI:
    - `combo_polar_search` has "Model Tracking (Option C)" as the first (default) item; A and B are kept.
    - `lbl_power_tol` / `spin_power_tol` "Tolerance" are now `lbl_stability_tol` / `spin_stability_tol` "Stability Tol (mW)" (4 readings, Wait Time apart, differ ≤ this; both modes). New `lbl_target_tol` / `spin_target_tol` "Target Tol (mW)" (|P − Target Power| ≤ this; Polarization mode). Both default 0.050 and have tooltips.
    - Wait Time moved to columns 10-11 and the button row now spans 12 columns. Target Power, the two tolerances and Wait Time have a 95 px minimum width; without it the extra column pair made the window at least 1467 px wide (now 1361 px).
  - Tooltips: the Polarization mode item and the Option C item show `POLAR_MODEL_TRACKING_TIP` (light path, the 5 steps, limits). A and B have short descriptions with their limits. The algorithm box's own tooltip follows the selected item.
  - Option A/B use Stability Tol for the stability check and Target Tol for the match. Power mode uses Stability Tol.
  - Start check (`scan_start_problem()`, replaces the Power-only check): Power mode needs Stage 1. Polarization mode (all options) needs Stage 1, Stage 2 and the PM100D, each enabled and connected. Model Tracking also needs Stage 1 to cover |Step| × (Step NO. − 1) ≥ 90° with at least 5 points. Messages read "<mode> mode needs <device>, but … Scan not started."
  - Saving:
    - New per-point `measurements` (Model Tracking; NaN / blank otherwise): MAT and HDF5 dataset, and a CSV column added last, so `ScanDataCore.parse_calibration_file()` (columns 1-4) is unaffected.
    - Model Tracking also saves `coarse_stage1_deg` and `coarse_power_mW` (MAT and HDF5 datasets) and `model_A_mW`, `model_B_mW`, `model_theta0_deg`, `model_rms_mW` (MAT variables, HDF5 root attributes). Scalars are attributes because `Polarization_fit_v1.0.py` reads every HDF5 dataset with `[:]`. The model arrives through `sig_model` → `on_model_ready()`.
  - Defaults kept: Stage 1 0° / 5° / 19 (= 0-90°, one full period; the Stage 1 boxes are shared with Power mode, so 5° steps were kept instead of 10°); Stage 2 0° / 2° / 91 (0-180°, the polarizer period).
  - Tested without hardware (opto_test env, real app, Wait Time 0). The fake optics use Jones calculus: HWP retardance 0.97π, stage zero offsets 3° / −5°, polarization-dependent loss up to 6 % after the polarizer, leakage 1e-3, ±5 µW reading noise, 2 % laser drift over the run.
    - Default parameters, target 5 mW: 91/91 angles matched within ±0.05 mW; 1.19 measurements per angle (max 2); 127 measurements in total including the 19-point coarse scan. θ1 vs θ2 slope +0.497; largest θ1 step between neighbours 1.18°.
    - Polarizer stage mounted reversed: 91/91 matched, slope −0.496.
    - Target at about 92 % of A: stopped after the coarse scan with the reachable range in the log; nothing saved.
    - Start checks: all five device cases and the too-short coarse range are refused; a 10° / 10-point coarse scan runs.
    - Options A and B still run. With 5° steps, A matched nothing, which is its known limit.
    - Stop during the scan: stopped after 5 points, nothing saved, buttons and PM settings re-enabled.
    - Files: the CSV has the Measurements column and is read by `ScanDataCore`; the MAT/HDF5 keys and attributes are present; HDF5 loads the way the fit tool reads it.
    - The earlier Power-mode, PM-settings and dated-folder tests still pass.
    - Windows platform plugin rendering: nothing is clipped at 1380x920 or 1920x1040, including 999.999 / 10.000 / 3600.0.
    - Not yet tested on the real stages and PM100D.

### Polarization_cali v1.1 (Detector: PM100D or lock-in)
- **Date**: 2026-11-02
- **Main Change**: The power reading can come from the PM100D or from an SR830 lock-in. The lock-in reads a fast detector (APD, PMT, one channel of a balanced detector) at the laser's 1 kHz trigger, connected to REF IN with the reference on External. The tab 1 checkbox is now **Detector**, followed by a PM100D / Lock-in drop-down; settings, units, connection, Scan devices and saving follow the selection.
- **Details**:
  - Readers: `PowerMeterReader` (PM100D, mW) and `LockinReader` (SR830 R, mV; R does not depend on the phase). Each has `read()`, `name`, `quantity` (Power / Signal) and `unit`.
    - `check_power_stability()` and the worker read through the reader (`detector` replaces `pm_inst`).
    - `LockinReader` keeps the sensitivity full scale chosen at the scan start and writes one warning to the log if a reading exceeds it.
    - Worker log lines use the unit from `config["signal_unit"]`.
  - UI, detector row:
    - `chk_detector_enable` "Detector" (was `chk_pm100d_enable`), then new `combo_detector` (PM100D / Lock-in, with a tooltip on how the lock-in option works), then `led_detector` (was `led_pm100d`).
    - The PM100D settings are in `widget_pm_settings`; the new `widget_lockin_settings` holds `combo_lockin_sens` "Sensitivity" and `combo_lockin_tc` "Time const.", with SR830 labels and OPTP defaults of 100 mV / 100 ms. Only the selected detector's settings are shown. Refresh stays.
    - `layout_pm100d` was renamed `layout_detector`.
  - UI, Inst. Config.: new row "Lock-in (SR830)" `combo_lockin_res` under the PM100D row (default GPIB0::2::INSTR, OPTP's Lock-in 1); the stage rows moved down one.
  - Switching the detector (`on_detector_changed()`):
    - shows that detector's settings;
    - relabels Target Power (mW) ↔ Target Signal (mV), Stability Tol and Target Tol, the chart's left axis and the readout;
    - sets the LED to whether that detector is connected.
  - Connect (Conn. Inst.) connects only the selected detector. The lock-in connects as in OPTP (`SR830(addr).open()`, `*IDN?`). Its sensitivity and time constant are read into the boxes with signals blocked, so nothing is sent. The reference mode and frequency are read and logged, with a warning if the reference is internal (not locked to the laser); nothing is changed on the lock-in. Changing a box applies it at once (`SENS` / `OFLT`).
  - Close Inst. with Detector checked closes both detector options. Exit closes the lock-in too.
  - Monitor: the readout shows `Signal: x mV (y % FS)` for the lock-in, as a guide for choosing the sensitivity.
  - During a scan `combo_detector`, the PM100D wavelength / range and the lock-in sensitivity / time constant are disabled.
  - Start check: Polarization mode needs "the Detector (<selection>)" enabled and connected.
  - Scan devices: the lock-in list is `list_lockin_resources()`, i.e. VISA `GPIB?*::INSTR` + `ASRL?*::INSTR`. Both took 0.14 s / 0.02 s on this PC, against 6-30 s for a full VISA scan.
  - Saving: the reading is stored as `power_mW` (PM100D, unchanged) or `signal_mV` (lock-in), and the CSV column is `Power_mW` / `Signal_mV`. The coarse scan and model keys follow the same pattern: `coarse_power_mW` / `coarse_signal_mV`, `model_A_mW` / `model_A_mV`, and so on. New `detector` field (MAT variable, HDF5 attribute): "PM100D" or "Lock-in R". `sig_model` now sends unit-free keys (`coarse_reading`, `A`, `B`, `rms`).
  - Tests (opto_test env, real app):
    - PM100D path: the Model Tracking, start-check, A/B and stop tests give the same results as before; file keys are unchanged.
    - Lock-in path, with a fake SR830 subclass: 2 mV/mW detector, 10 µV noise, same Jones-matrix optics as the PM100D test.
      - Switching relabels everything to mV and shows the lock-in settings.
      - Connect logs reference external / 1000 Hz and reads 10 mV / 30 ms into the boxes with no command sent. Changing the boxes sends `SENS 22`, `OFLT 8`.
      - Readout "Signal: 19.7112 mV (39 % FS)", and 197 % at 10 mV FS.
      - Start refused while the lock-in is selected but not connected.
      - Model Tracking with target 10 mV and tolerances 0.1 mV: 91/91 matched, 1.19 measurements per angle, slope +0.497. The full-scale warning appeared once.
      - Files hold `Signal_mV` / `signal_mV` / `model_A_mV` / detector "Lock-in R", and HDF5 still loads the way the fit tool reads it.
      - An internal reference gives the warning at connect.
      - Close Inst. closes both detector options.
    - Scan devices on this PC: PM100D none, lock-in candidates ['ASRL14::INSTR'], Kinesis ['27255354']; the typed lock-in address was kept.
    - Rendering (Windows platform plugin, 1380x920 and 1920x1040): both detector rows fit with no clipping (e.g. "500 mV nA", "Signal: 19.7112 mV (39 % FS)"); the window minimum width is 1361 / 1348 px.
    - Not yet tested with a real SR830 and detector.

### Polarization_cali v1.1 (stability timeout, saving incomplete scans, ScanLog)
- **Date**: 2026-11-02
- **Main Change**: Fixes the two known issues: a reading that never settled was reported as stable, and a stopped scan was not saved. Adds a **ScanLog** in tab 2 as in OPTP: test conditions and key events of every scan, shown live and appended to `ScanLog_YYYY-MM-DD.txt` in the data save folder.
- **Details**:
  - `check_power_stability()`:
    - Gives up after `STABILITY_MAX_READINGS` = 15 readings (was 45 attempts, i.e. 7.5 min at Wait Time 10 s; now at most 140 s) and returns `is_stable = False` (it returned True before).
    - Returns the mean of the last 4 readings (the 4 that met the tolerance, or the last 4 at the timeout) instead of the last single reading. A stop request still returns the last reading, not stable.
  - Effect of the timeout fix:
    - Power mode records the point with Stable = False.
    - Polarization A/B/C do not accept an unstable reading (Model Tracking keeps correcting and records the closest measurement as not matched).
  - Worker:
    - New `measure(where)` (used by Power, A, B and Model Tracking) writes "Not stable after 15 readings at <where> (mean of the last 4: …)" to the ScanLog.
    - New `scan_event()` sends key events to the log box and, through the new `sig_scan_log`, to the ScanLog.
    - Key events: the Power-mode fixed stages; the Model Tracking model and start; angles where the target was not reached; readings that did not settle; the lock-in full-scale warning.
    - `run_model_tracking()` no longer takes wait_time / stability_tol (it reads them from the config).
    - The unused `pm_enabled` variable and the `detector_enabled` config key were removed.
  - Finish status: `sig_finished` is now (status, message) with status "finished" / "stopped" / "aborted" (CalibrationAbort) / "error".
  - Saving:
    - `on_scan_finished()` saves whatever was measured in every case: a finished scan as before, a stopped scan as `<prefix>_<time>_stopped.*`, an aborted or failed one as `<prefix>_<time>_aborted.*`.
    - A Model Tracking scan stopped because the target is out of reach still saves its coarse scan and model (0 points).
    - `save_data(suffix)` returns the file name.
  - ScanLog (UI): `grp_scan_log` "ScanLog" with a read-only `txt_scan_log` (QPlainTextEdit, Consolas 9, tooltip) at `tab2Layout` (0,1), rowspan 2, in place of `connHSpacer`; `tab2Layout` columnstretch 0,1, as OPTP. OPTP's "Live Progress" box was not added: its terminal mirror is the log on the Calibration tab here.
  - ScanLog (logic, after OPTP `start_scan_log` / `scan_log_event` / `append_scan_log` / `end_scan_log`):
    - At Start: a block with the start time, mode (+ algorithm), save folder, detector (PM100D wavelength / range, or lock-in address / sensitivity / time constant), target and Target Tol (Polarization), Stability Tol / Wait Time / reading limit, and every enabled and connected stage (scanned range, coarse scan, or fixed angle).
    - During the scan: timestamped key events.
    - At the end: "Data files: <name>.mat / .csv / .h5", then "Scan finished: N points, M with Stable = False", "Scan stopped by user after N points", "Scan aborted: <reason>" or "Scan error: <first line>", with the duration.
    - Each line is appended to the day's file at once. Point-by-point readings stay in the Calibration tab log only.
  - Tests (opto_test env, real app, fake instruments):
    - Stability check: settling at reading 6 returns the mean of readings 3-6, True; a reading alternating ±0.2 mW gives up after 15 readings, False.
    - Power mode with a reading that never settles at Stage 1 = 20°: that point saved with Stable = False; ScanLog "Not stable after 15 readings at Stage 1 = 20.0° …"; end line "5 points, 1 with Stable = False".
    - Model Tracking finished run: start block, model, start angle, data files, end line.
    - Target out of reach: `_aborted` files with the coarse scan and model and 0 points; ScanLog "Scan aborted: Target … outside …".
    - Stage 2 failing at its 4th move: `_aborted` files with the 2 finished points; ScanLog "Scan error: Calibration Worker Error: Kinesis: device not responding".
    - Stop during Model Tracking: `_stopped` files.
    - The ScanLog file equals the box text.
    - All earlier tests still pass (PM100D and lock-in Model Tracking 91/91 matched; Power mode; start checks; A/B).
    - Windows platform plugin: tab 2 at 1380x920 / 1920x1040 has Instrument Connections 400 px wide and the ScanLog filling the rest; window minimum width 1361 px.
    - Not yet tested on the real instruments.

### Polarization_cali v1.1 (Detector unchecked = not read)
- **Date**: 2026-11-02
- **Main Change**: With Detector unchecked the detector is not read, even while it is connected: neither by the readout nor by a scan. Before, `active_reader()` ignored the checkbox, so a connected detector was read anyway.
- **Details**:
  - Background (unchanged): without a detector, `check_power_stability()` returns (0.0, stable) at once, so Wait Time is not applied and every Power-mode point is recorded as 0. The ScanLog block says "Detector : none (readings recorded as 0)". Polarization mode does not start without a detector.
  - `active_reader()` returns None when `chk_detector_enable` is unchecked.
    - Power mode then records 0 without reading.
    - Polarization mode is refused with "… needs the Detector (…), but … is not enabled".
    - The monitor does not read the detector.
  - `update_detector_led()` no longer uses `active_reader()`. The LED shows whether the selected detector is connected, checked or not, like the stage LEDs.
  - `chk_detector_enable.toggled` → `on_detector_changed()`, so unchecking resets the readout to "-- mW" / "-- mV" instead of leaving the last value.
  - Tests (opto_test env, fake PM100D counting its reads):
    - Checked: a monitor tick reads once; a 3-point Power scan reads 12 times and records 5 mW.
    - Unchecked: readout "Power: -- mW", LED still on, a monitor tick reads 0 times, the Power scan reads 0 times and records 0 with ScanLog "Detector : none"; Polarization refused (not enabled).
    - Checked again: reads resume.
    - The lock-in and ScanLog tests still pass.

### Polarization_cali v1.1 (program logo)
- **Date**: 2026-11-02
- **Main Change**: New program logo, used as the window and taskbar icon: a polarizer / wave plate in a rotation mount (navy disc with a white angle scale, a white optic ring, a red double arrow for the polarization direction). Navy and red like the lab's `mo_icon.png`.
- **Details**:
  - Files in `Polarization_cali/`:
    - `pol_cali_icon.svg`: source.
    - `pol_cali_icon_small.svg`: simplified variant for 16 / 24 px (4 thick scale marks, no optic ring).
    - `pol_cali_icon.png`: 256 px.
    - `pol_cali_icon.ico`: 16, 24, 32, 48, 64, 128 and 256 px. Each size is rendered from the SVG (QSvgRenderer), not scaled down from 256 px; 16 / 24 px use the small variant.
  - The arrow is 22 px wide on the 256 px canvas, so it stays visible at 16 px (checked in an 8x nearest-neighbour zoom of the 16 / 24 / 32 px frames, on light and dark backgrounds).
  - Code (`main()`):
    - `app.setWindowIcon(QIcon(str(Path(__file__).with_name("pol_cali_icon.ico"))))`. The path is relative to the script, so it also works when started from another folder; MO / OPTP use `QIcon('mo_icon.png')`, which depends on the working directory.
    - On Windows, `SetCurrentProcessExplicitAppUserModelID("GUI_pyqt.PolarizationCali")` gives the process its own taskbar entry, so the taskbar shows this icon instead of python.exe's.
    - New import `QIcon` (PySide6.QtGui).
  - Checked (opto_test env, started from `C:\`): QIcon loads all 7 ICO sizes, the main window's icon has them, and the AppUserModelID is set.

### Polarization_cali v1.1 (exit confirmation)
- **Date**: 2026-11-02
- **Main Change**: Exit, the title-bar X and Alt+F4 now ask "Exit the program and close all instruments?" (OPTP's wording; default No) to prevent closing by mistake. On Yes, a running scan is stopped and saved and every instrument is closed.
- **Details**:
  - Bug found: the confirmation written in v1.0.11/12 never ran. `self.ui.closeEvent = self.on_ui_close_event` assigns a Python attribute to a window created by QUiLoader in C++, so Qt never calls it. The window closed at once without asking and without closing the instruments. Checked before the fix: Exit and the window's close both closed it with no dialog.
  - Fix:
    - `self.ui.installEventFilter(self)`.
    - `eventFilter()` catches `QEvent.Close` on `self.ui`. If `confirm_exit()` is False it calls `event.ignore()` and returns True: a close event starts out accepted, so returning True alone still closed the window (found in testing).
    - Other events return False directly, not `super().eventFilter()`, which raised at interpreter shutdown once this object was deleted.
  - `confirm_exit()` replaces `on_ui_close_event()`:
    - While a scan runs, the dialog adds "A scan is running. It will be stopped and the data measured so far saved."
    - Yes: stop the scan, `worker.wait()`, process events so `on_scan_finished` saves the `_stopped` files and closes the ScanLog block, then `disconnect_all_devices()` and `QApplication.quit()`.
    - No: logs "Exit cancelled." and the window stays open.
  - `check_power_stability()` now waits Wait Time in 0.1 s steps and checks for a stop request at each step. Stop and Exit therefore take effect within 0.1 s (or after the current stage move) instead of after up to a full Wait Time.
  - New import `QEvent` (PySide6.QtCore).
  - Tests (opto_test env, real app, dialog answer injected):
    - Exit button / window close + No: dialog shown on the main window, window still open, no quit, "Exit cancelled.".
    - Exit + Yes: both fake stages closed, quit called.
    - Stop during a 5 s Wait Time: worker finished 0.05 s later, `_stopped` files saved.
    - Exit during a Model Tracking scan: the dialog mentions the running scan; exit took 0.06 s; the 2 finished points were saved as `_stopped` with the ScanLog line "Scan stopped by user after 2 points"; instruments closed.
    - No traceback at shutdown.
    - All earlier tests still pass.

### Polarization_cali v1.2 (stability check: fast sampling, Stable Window)
- **Date**: 2026-11-03
- **Main Change**: Copied `Polarization_cali_v1.1.py` / `.ui` to `Polarization_cali_v1.2.py` / `.ui`; v1.1 is unchanged. The stability check now reads the detector every **Refresh (ms)**. A measurement is stable as soon as all readings in the last **Stable Window (s)** lie within Stability Tol (max − min); their mean is recorded. Stable Window replaces Wait Time and defaults to 3 s. Time per measurement: detector settle time + window, instead of at least 3 × Wait Time (30 s at the v1.1 default).
- **Details**:
  - Why: in v1.1 Wait Time was both the settle time and the spacing between readings, and 4 readings were needed. That meant at least 3 × Wait Time per measurement even when the sensor had settled after 1-2 s. The neighbour-to-neighbour check also accepted a slow drift in one direction.
  - `check_power_stability(detector, window_s, tolerance_mw, interval_s, stop_flag_check, logger)`:
    - Reads every `interval_s`. The last n = ceil(window / interval) + 1 readings cover at least the window: 3 s / 500 ms = 7 readings.
    - Stable as soon as max − min of these n readings ≤ Stability Tol; it returns their mean. Right after a move the readings still change, so no separate wait is needed.
    - The next reading starts `interval_s` after the start of the previous one, or at once if the read took longer. A slow read therefore never squeezes the window.
    - Stop / Exit are still checked every 0.1 s.
    - Timeout `STABILITY_TIMEOUT_S` = 60 s (replaces `STABILITY_MAX_READINGS` = 15): it returns the mean of the last n readings with Stable = False.
    - Once the window is full, it logs one line per reading (Power mode, as before): elapsed time, the reading, and max − min of the window.
    - The unused `pm_enabled` parameter was removed.
  - Scope: every measurement goes through `CalibrationWorker.measure()`, so the new check applies to Power mode and to Polarization A / B / Model Tracking, including its coarse scan.
  - Config: `stable_window` and `sample_interval` (Refresh at Start, in s) replace `wait_time`. Refresh stays editable during a scan; a change applies from the next scan, like the other scan settings.
  - ScanLog:
    - Start block: "Stability : Tol 0.05 mW (max - min), Stable Window 3 s, a reading every 500 ms (Refresh), at most 60 s per measurement".
    - Timeout event: "Not stable within 60 s at <where> (mean of the last 3 s: …)".
  - UI:
    - `lbl_wait_time` / `spin_wait_time` became `lbl_stable_window` / `spin_stable_window` "Stable Window (s):": 0.5-30.0 s, step 0.5, default 3.0, with a tooltip.
    - The spin box minimum width is 70 px (was 95; the maximum is now 30.0). The longer label therefore keeps the window minimum width at 1361 px; with 95 px it was 1386 px.
    - Tooltips updated: Stability Tol (max − min over the window), Refresh (also the scan sampling interval), and the lock-in time constant (Stable Window ≥ 5 × time constant, Refresh ≥ time constant).
    - Version strings changed to v1.2.
  - Tests (opto_test env):
    - Function level:
      - Constant + 5 µW noise, 0.5 s / 100 ms: 6 readings 0.10 s apart, stable after 0.50 s.
      - Settling 5 + 2·exp(−t/0.3 s) mW: stable after 1.51 s, mean 0.037 mW above the final value.
      - Drift +0.4 mW/s, i.e. 0.04 mW per reading, below Tol 0.05: not stable, ended at the timeout. The v1.1 check accepted the same drift after 4 readings.
      - Reads of 0.25 s at a 100 ms interval: readings 0.25 s apart, with no burst.
      - A Stop request is seen within 0.05 s.
      - No detector: (0, stable).
      - Defaults: 7 readings, 3.1 s.
      - Readings per window with a virtual clock: 1.0 s / 300 ms gives 5 readings over 1.2 s; 1.1 s / 100 ms gives 12; 0.5 s / 1000 ms gives 2.
    - Power mode, real app, default settings. Fake thermal sensor: τ = 0.8 s exponential response to each move, 0.1 s per read (the PM100D `query_delay_s`), 5° steps.
      - 3.1 / 4.6 / 5.6 / 5.7 s per point (the first point has no power change).
      - All points stable, recorded within 0.016 mW of the true value.
      - v1.1 needs at least 30 s per point at its default Wait Time of 10 s.
    - Power mode with the reading drifting +0.2 mW/s, timeout patched to 3 s: both points have Stable = False, and the ScanLog has "Not stable within 3 s at Stage 1 = …".
    - Stop during a measurement: the worker ended at once and `_stopped` files were saved.
    - Model Tracking, Jones-matrix fake optics as in v1.1, Refresh 100 ms, window 0.5 s:
      - 91/91 matched, 1.42 measurements per angle (max 2).
      - The v1.1 test gave 1.19. With the fake laser drift off, v1.1 gives 1.41 and v1.2 gives 1.24. The count depends on where the earlier solutions fall inside Target Tol, not on the version.
      - With a virtual clock, default settings and instant reads, a full Model Tracking scan takes 6.7 min against 63.5 min for v1.1 (Wait Time 10 s).
    - Polarization Options A and B, same fake optics, 10 Stage 2 angles, Stage 1 0-45° (virtual clock, v1.2 default window vs v1.1 Wait Time 0):
      - A (1° steps): 0/10 matched in both versions, with 460 measurements each.
      - B: 1/10 matched in both versions.
      - Model Tracking: 91/91 in both.
      - v1.2 takes 7 readings per measurement instead of 4; the decisions are the same. The low A / B match rate is their known limit: A's step is too coarse for Target Tol, and B needs the power to rise with Stage 1, but here it falls over 0-45°.
    - Windows platform plugin: window minimum width 1361 px at 1380x920 and 1920x1040; at 1380 px the Stable Window box is 77 px wide and "30.0" fits.
    - Not yet tested on the real PM100D / S302C. The default window should be checked against a measured step response once P0009634 is on the NI-VISA driver.

### Polarization_cali v1.2 (Stability Tol: absolute or % of the reading)
- **Date**: 2026-11-03
- **Main Change**: Stability Tol now has two parts: an absolute value and a new percentage of the reading. A window is stable when max − min ≤ the larger of the two. The power can now go down to the µW level while the top of a Power scan is at mW. A single absolute Tol could not cover that range: 50 µW is larger than the signal at the bottom, and a few µW is smaller than the laser fluctuation at the top, so every high-power point would wait the full 60 s. Both Tol boxes now have 4 decimals (0.1 µW steps).
- **Details**:
  - `check_power_stability(..., tolerance_pct=0.0, ...)`:
    - The effective tolerance is `max(tolerance_mw, tolerance_pct / 100 · |mean of the window|)`.
    - The `[Power Stability]` log line shows the effective tolerance and both parts, e.g. "Tol: 0.0500 mW = max(0.002 mW, 0.5 %)".
    - Applies to every measurement (Power mode and Polarization A / B / Model Tracking), through `measure()` and the new config key `stability_tol_pct`.
  - Target Tol stays absolute: the target is fixed during a Polarization scan, so a percentage adds nothing. Its tooltip now says to keep it at least the Stability Tol at the target.
  - UI (`grid_config` column 7 is now `layout_stability_tol`):
    - `spin_stability_tol` (absolute, label "Stability Tol (mW):" / "(mV):" as before): 4 decimals, default **0.0020 mW** (was 0.050).
    - New label `lbl_stability_tol_or` "or".
    - New `spin_stability_tol_pct`: suffix " %", 0-10.00, 2 decimals, step 0.1, default **0.50 %**, no arrow buttons, 50 px wide.
    - The three widgets share one tooltip. It explains the rule, how to choose the two values, and how to measure the noise: Power mode, Stage 1 Step NO. 1, both values 0, so the point never passes and the log shows max − min of every window for 60 s.
    - `spin_target_tol`: 4 decimals (default 0.0500 unchanged).
  - ScanLog start block: "Stability : Tol 0.002 mW or 0.5 % of the reading, whichever is larger (max - min), Stable Window 3 s, …".
  - The defaults 2 µW / 0.5 % are a starting point. The absolute value must be above the detector's max − min at the lowest power, and the percentage above the laser's at the highest. Both still need to be measured on the real detector.
  - Layout: the window minimum width rises from 1361 to 1430 px, so the window now opens 1430 px wide instead of the .ui's 1380. This PC's screen is 1920x1080. All values fit, including the maxima "10000.000", "100.0000", "10.00 %" and "30.0". `powerChart` is unchanged (217 px at 920 px window height).
  - Tests (opto_test env, virtual clock). Fake detector noise: 0.3 µW + 0.1 % of the reading; window 3 s, Refresh 500 ms.
    - Constant power, three settings:

      | Power | 50 µW, 0 % | 2 µW, 0 % | 2 µW, 0.5 % |
      |---|---|---|---|
      | 10 mW | stable at 3.0 s | timeout (60 s) | stable at 3.0 s |
      | 1 mW | stable at 3.0 s | 7.0 s | stable at 3.0 s |
      | 100 µW down to 2 µW | stable at 3.0 s | stable at 3.0 s | stable at 3.0 s |

    - A reading still settling, 5 µW + 4 µW·exp(−t/2 s), with 2 µW / 0.5 %: stable after 4.0 s, recorded 6.3 µW, i.e. at low power the accuracy is set by the absolute value.
    - Power scan 0-45° (10 mW·cos²(2θ1) + 2 µW leakage), 10 points, real app:
      - 2 µW / 0.5 %: all 10 stable, 30 s in total.
      - 2 µW / 0 %: 6 high-power points not stable, 397 s, 6 ScanLog events.
      - 50 µW / 0 %: all stable, 30 s.
      - The ScanLog line and the log line read as above.
    - Polarization, Jones-matrix fake optics from the v1.1 tests, with 5 µW constant noise:
      - With the new default floor of 2 µW, below that noise: Model Tracking still 91/91 matched but 11.1 min instead of 6.7. A and B slow down a lot, because low-power readings never pass and wait 60 s.
      - With the floor at 0.02 mW (about 4x the noise) and 0.5 %, the results equal the earlier ones: A 0/10 in 23.4 min, B 1/10 in 4.6 min, Model Tracking 91/91 in 6.7 min.
      - So an absolute value below the real noise makes the scan slow, not wrong.
    - Windows platform plugin at 1380x920 (opens at 1430) and 1920x1040: nothing clipped.

### Polarization_cali v1.3 (Wait Time + Avg. No.: stability check, then a separate averaged reading; plot x = angle)
- **Date**: 2026-11-03
- **Files**: `Polarization_cali_v1.3.py` / `.ui`, copied from v1.2 including its uncommitted Tol % change. v1.2 is kept unchanged for comparison.
- **Background**: the first real S302C scans at 0-30 µW were rougher with v1.2 than with v1.1.
  - Point-to-point noise: about 1 µW with v1.1 versus 2-4 µW with v1.2 Tol 1 µW.
  - Near extinction the readings jumped between about −2 and +4 µW.
  - A 20 s Stable Window did not help.
  - The cause is not settled yet.
  - The user asked for an explicit, simple sequence in which the number of averaged readings is set directly, not derived from Window / Refresh.
- **Main Change**: every measurement, in Power mode and in Polarization A / B / Model Tracking (`measure()`), now runs these steps:
  1. **Wait Time** (s) after the stage move has finished (`move_to` blocks until the stage arrives).
  2. **Stability check**:
     - Readings are taken every **Refresh + 0.1 s**, counted from the end of the previous reading. The PM100D query itself adds its own 0.1 s query delay, so at Refresh 500 ms the readings are about 0.7 s apart.
     - The check passes when max − min of the last **Avg. No.** readings ≤ max(Tol, % × reading).
     - If not, one more reading is taken and the last Avg. No. are checked again, at most 60 s.
  3. **Reading**: Avg. No. **new** readings are taken, and their mean is the recorded value.
     - If the check timed out, the reading is still taken and the point is recorded with Stable = False plus a ScanLog event ("Not stable within 60 s at …, recorded the mean of N readings").
- **Details**:
  - `check_power_stability(detector, wait_s, n_avg, interval_s, tolerance_mw, tolerance_pct, stop_flag_check, logger)`:
    - New constant `READ_EXTRA_WAIT_S = 0.1`.
    - A Stop during Wait Time reads once and returns that reading. A Stop during the check or the reading returns the last reading. In every case Stable = False and the Stop is seen within 0.1 s.
    - The `[Power Stability]` log line's time now counts from the end of Wait Time.
    - New log line `[Power Reading] mean of N readings: … (max - min …)`.
  - Config keys `wait_time`, `n_avg` replace `stable_window`; `sample_interval` = Refresh.
  - UI (`grid_config` row 0):
    - Columns 10-11: `lbl_wait_time` "Wait Time (s):" and `spin_wait_time` (0-60 s, step 0.5, default **2.0**, min 70 px). These replace `lbl_stable_window` / `spin_stable_window`.
    - Columns 12-13: new `lbl_avg_no` "Avg. No.:" and `spin_avg_no` (2-100, default **5**, min 60 px).
    - The run row's colspan goes from 12 to 14.
    - Tooltips updated: Wait Time, Avg. No., Stability Tol (4 copies), Refresh, lock-in time constant (keep Wait Time ≥ 5 × TC).
  - ScanLog start block: "Stability : Wait Time 2 s after each move, then a reading every 500 ms (Refresh) + 0.1 s; stable when max - min of the last 5 readings <= Tol … (at most 60 s); then the mean of 5 new readings is recorded (Avg. No.)".
  - Live plot x-axis: the scanned angle instead of the point index.
    - Power mode: Stage 1, label "Stage 1 Angle (°)".
    - Polarization mode: Stage 2, label "Stage 2 Angle (°)".
    - Before a scan the label is "Angle (°)".
  - Defaults: Wait 2 s, Avg. No. 5, Refresh 500 ms. That is about 2 + 9 × 0.7 ≈ 8.3 s per point plus the move.
    - The v1.1 "Wait 3 s" timing can be reproduced: Refresh 2900 ms, Wait Time 0 and Avg. No. 4 give 4 check readings 3 s apart, then 4 more.
- **Tests** (opto_test env, virtual clock, fake read time 0.1 s):
  - Function:
    - Constant power: readings at 2.1, 2.8, … 8.4 s, i.e. 0.7 s apart end to end. Stable at the 5th reading, then 5 new readings; recorded value = their mean.
    - Settling 10 µW·exp(−t/1 s) with Wait 0: the check passes at reading 8; the recorded value is the mean of readings 9-13 only.
    - Noise 5 µW with Tol 1 µW: Stable False after 60 s, then the 5 new readings (65.8 s, 92 readings).
    - % term: 100 mW with 0.05 % noise passes at 2 µW / 0.5 % and times out at 2 µW / 0 %.
    - Stop at 1 s (in Wait), 3 s (in check) and 6 s (in reading): returns within 0.1 s with Stable False.
    - No detector: (0.0, True).
  - App with fake stages and PM100D:
    - Power 0-45° (10 points): all stable, 9.5 s/point, 100 reads. Plot x = Stage 1 angles, label "Stage 1 Angle (°)".
    - Polarization Model Tracking 4/4 matched, B 4/4.
    - A 0/4: its 5° grid does not reach Target Tol in this fake, unrelated to this change.
    - In all Polarization runs the plot x = Stage 2 angles. ScanLog lines as above.
  - Windows platform plugin: the window minimum width rises from 1430 to 1526 px (opens 1526 wide; screen 1920). At 1380 and 1920 nothing is clipped, including "60.0" and "100".
  - Not yet run on the real PM100D / S302C.
- **Stage 1 default serial**: `init_device_defaults` now puts **27255354** in the Stage 1 serial box (was 27004364, OPTP's). Stage 2 / 3 (27255894) are unchanged. The Scan button still offers every Kinesis serial found on the PC.
- **One Tolerance for both modes (Target Tol removed)**: Stability Tol and Target Tol were two tolerances for the same reading, so the user asked to merge them. The UI label is now **"Tolerance (mW):"** / "(mV):"; it keeps the absolute value and the %.
  - The stability check is unchanged: max − min of the last Avg. No. readings ≤ max(absolute, % × reading).
  - Polarization mode (A, B, Model Tracking), target reached: the reading is stable and |P − Target Power| ≤ max(absolute, % × Target Power).
    - The worker computes `target_tol` once from `stability_tol` / `stability_tol_pct` at the start of the scan.
    - The config key `target_tol` is gone.
    - With the defaults (0.002 mW / 0.5 %) and a 5 mW target, the match window is ±0.025 mW (Target Tol was 0.05 mW).
  - Object names (`spin_stability_tol`, `spin_stability_tol_pct`, `lbl_stability_tol`, config `stability_tol`) are kept, to limit the change.
  - UI:
    - `lbl_target_tol` and `spin_target_tol` removed.
    - Wait Time / Avg. No. move to columns 8-11; the run row colspan goes back to 12.
    - The Tolerance tooltip (4 copies) describes both uses; the Avg. No. tooltip says "within Tolerance".
  - ScanLog:
    - The Target line is now "Target : 5 mW, reached when |P - target| <= Tolerance (0.025 mW at the target)".
    - The Stability line reads "<= Tolerance …".
  - Model Tracking log line: "target 5.0 ± 0.025 mW". The Model Tracking and Option A tooltips say "Tolerance".
  - Tests (virtual clock, fake optics):
    - Power: 10/10 stable.
    - Model Tracking: 4/4 matched, all at ±0.025 mW.
    - B: 4/4 matched.
    - A: 0/4, its 5° grid as before.
    - Plot x = angles; ScanLog lines as above.
  - Windows platform plugin: the window minimum width drops from 1526 to 1321 px, so the window opens at the .ui's 1380 again. Nothing is clipped.
- **Stability check on a fixed 5 readings; Avg. No. only for the recorded mean**: the user wants Avg. No. to mean just the readings averaged after the reading is stable.
  - New constant `STABILITY_N = 5`. The check passes when max − min of the last 5 readings ≤ Tolerance, whatever Avg. No. is. There is no UI box for it.
  - Avg. No. is used only in step 3: after the check, Avg. No. new readings are averaged.
    - No max − min is computed on them: the `[Power Reading]` log line is now just "mean of N readings: …".
    - `spin_avg_no` minimum lowered from 2 to 1 (a single reading is allowed).
  - Tooltips: Avg. No. rewritten; Tolerance (4 copies) now says "the last 5 readings".
  - ScanLog Stability line: "stable when max - min of the last 5 readings <= Tolerance …; then the mean of N new readings is recorded (Avg. No.)".
  - Tests (virtual clock):
    - With Avg. No. 1 / 5 / 10, a steady reading passes the check at the 5th reading, then takes 1 / 5 / 10 more, and the recorded value is their mean.
    - Settling 10 µW·exp(−t/1 s) with Avg. No. 10: the check passes at reading 8 on its 5-reading window.
    - App: Power 10/10, Model Tracking 4/4, B 4/4, A 0/4 as before.
- **Stable No. in the UI**: the number of readings in the stability check can now be set, replacing the constant `STABILITY_N`.
  - `check_power_stability(detector, wait_s, n_stable, n_avg, interval_s, tolerance_mw, tolerance_pct, ...)`; new config key `n_stable`.
  - UI (`grid_config` row 0):
    - Columns 10-11: new `lbl_stable_no` "Stable No.:" and `spin_stable_no` (2-100, default **5**, min 60 px), with its own tooltip.
    - Avg. No. moves to columns 12-13; the run row colspan goes to 14.
    - Order on screen: Wait Time → Stable No. → Avg. No., the order in which they act.
  - Tooltips: Tolerance (4 copies) and Avg. No. now say "the last Stable No. readings".
  - ScanLog Stability line: "stable when max - min of the last 5 readings (Stable No.) <= Tolerance …".
  - Tests (virtual clock, read 0.1 s):
    - Stable No. / Avg. No. = 2/1, 3/5, 5/5, 8/3 and 10/10: exactly Stable No. + Avg. No. readings, and the recorded value is the mean of the last Avg. No. (Wait 2 s, Refresh 500 ms: 3.5 s up to 15.4 s per point).
    - Settling 10 µW·exp(−t/1 s), Wait 0, Tol 2 µW: Stable No. 3 / 5 / 8 pass after reading 5 / 8 / 11. The recorded value is then 0.105 / 0.013 / 0.002 µW above the final value.
    - Timeout and Stop as before.
    - App: Power 10/10, Model Tracking 4/4, B 4/4, A 0/4.
  - Windows platform plugin: the window minimum width rises from 1321 to 1450 px (opens 1450 wide; screen 1920). "60.0" and "100" fit in all three boxes.
- **Run row order**: Exit moves to the right of Stop, and the five buttons move to the right of Prefix (.ui only, `layout_run`).
  - New order: Save Dir: [path] Browse... Prefix: [pol_cali] | Conn. Inst. Close Inst. | Start Stop Exit.
  - New 16 px `prefix_gap_spacer` between the Prefix box and Conn. Inst. `run_gap_spacer` (16 px) still separates Close Inst. from Start.
  - The path box still takes the spare width, so the buttons sit at the right end of the row.
  - Windows platform plugin: the minimum width stays 1450 px, and every label fits. At 1450 px Exit ends at x 1392; at 1920 px it ends at x 1862.
- **Stable No. / Avg. No. moved to the second row; narrower path box**: the top row was too crowded (.ui only).
  - `lbl_stable_no` / `spin_stable_no` / `lbl_avg_no` / `spin_avg_no` move from `grid_config` row 0 (columns 10-13) to the start of `layout_run`. A 16 px `stable_gap_spacer` follows them. Row 0 now has 10 columns, and the run row colspan goes back to 10.
  - The second row now reads: Stable No. [5] Avg. No. [5] | Save Dir: [path] Browse... Prefix: [pol_cali] | Conn. Inst. Close Inst. | Start Stop Exit.
  - `line_save_dir`: at most **400 px** wide. Before, it took all the spare width, 710 px at 1450 px. The longest default path, `...\September\September_30`, needs 346 px.
  - `layout_run` stretch: only `line_save_dir` is 1, so the path box takes the spare width first, up to 400 px.
  - `prefix_gap_spacer` is now `MinimumExpanding` (at least 16 px). It takes the width beyond that, so the buttons stay at the right end.
  - `spin_stable_no` / `spin_avg_no`: at most 70 px. In the box layout they would otherwise take their 99 px size hint.
  - Windows platform plugin:
    - The minimum width drops from 1450 to about 1345 px, so the window opens at the .ui size of 1380 px.
    - Path box: 361 px at 1380, 400 px at 1450 and 1920.
    - The default path (344 px) and "100" in both number boxes fit at all three widths.
  - App test (fake devices): Power 10/10, Model Tracking 4/4, B 4/4, A 0/4, as before.
- **Raw Avg. No. readings saved with the mean**: each point keeps the Avg. No. readings its value is the mean of. The mean stays where it was; the raw readings are appended. The live plot still shows the mean.
  - `check_power_stability` now returns `(reading, is_stable, raw)`:
    - Normally, `raw` is the n_avg readings whose mean is `reading`.
    - After a Stop (in Wait, the check or the averaging), `raw` is `[reading]`, the one reading that is recorded.
    - Without a detector, `raw` is `[]`.
  - `measure()` passes `raw` on. Each point dict gets `"raw"`:
    - Power mode: the point's readings.
    - Option A / B: those of the matched measurement, or of the last one if not matched, like `power_mw`.
    - Model Tracking: those of the recorded (matched or closest) measurement.
    - The Model Tracking coarse scan saves only its means, as before.
  - `start_calibration` stores `self.scan_n_avg` (Avg. No. of the scan). `save_data` builds `raw_arr`, points × Avg. No., NaN-padded.
  - Files:
    - **CSV**: the existing columns `Point_Idx,…,Power_mW,Stable,Measurements` are unchanged. Avg. No. columns `Power_mW_raw1 … Power_mW_rawN` follow (`Signal_mV_raw…` with the lock-in), 4 decimals like the mean. Blank where a point cut short by Stop has only one reading.
    - **MAT / HDF5**: new 2-D `power_mW_raw` (`signal_mV_raw`), points × Avg. No., NaN-padded. The existing variables are unchanged.
  - Readers:
    - `ScanDataCore.parse_calibration_file` reads columns 0-4 by position, so the extra columns don't affect it.
    - `Polarization_fit_v1.0.py` loads every HDF5 dataset with `[:]`, so the 2-D dataset loads.
  - Tests (opto_test env, virtual clock, fake devices):
    - Function, Avg. No. 1 / 3 / 5 / 10: `raw` is the last Avg. No. readings and their mean equals the reading exactly. A Stop in Wait / check / averaging gives `raw == [reading]`.
    - App scans:
      - Power (Avg. No. 3); Power stopped in the 5th point's check and after 2 of its 5 averaged readings; Model Tracking / A / B (Avg. No. 4).
      - In every scan: the mean of `raw` equals the recorded value and the plot shows the mean.
      - The CSV header and widths are right. MAT / HDF5 `power_mW_raw` has shape points × Avg. No. and its NaN-mean equals `power_mW`. `ScanDataCore` and the fit tool's HDF5 load still work.
      - The stopped point's CSV row: `4,20.00,0.00,,5.8765,False,,5.8765,,,,`.
    - Stable No. test unchanged.

---

## Summary
The primary objective of the `Polarization_cali` program is to provide precise, automated polarization angle and power calibration for OPTP/MO experimental optical setups.

## Notes
- Future modifications, bug fixes, and feature additions should be appended to this log with date, version number, and detailed change descriptions.
