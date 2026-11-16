# OPTP Development Change Log

This document records the overall development and debugging history for the OPTP project, including version updates, bug fixes, and major functional changes.

## Version history

### v1.3
- Date: 2026-07-29
- Main change: fixed the MercuryiTC connection issue.
- Details:
  - broadened the exception handling to catch VisaIOError,
  - reset the MercuryiTC instance on connection failure,
  - refreshed device UIDs when the instrument was already connected but the UIDs were missing,
  - reset UIDs correctly during close.

### v1.4
- Date: 2026-07-30
- Main change: resolved the QThread lifecycle issue during temperature stabilization and scan execution.
- Details:
  - ensured the temperature stabilization thread is properly waited on before being overwritten,
  - added proper thread shutdown handling after scan execution.

### v1.5
- Date: 2026-08-04
- Main change: added temperature-aware Stage1 peak tracking for 1D_THz scans.
- Details:
  - added a local peak-tracking calibration step before the formal 1D_THz scan,
  - used the current Stage1 position as the scan center and scanned around it locally,
  - sampled each point three times and averaged the values to improve robustness,
  - updated the UI with the calibrated peak position,
  - made the formal scan proceed only after successful peak tracking,
  - stopped the scan sequence immediately when a stop request or failed calibration occurred.

### v1.6
- Date: 2026-08-04
- Main change: started modularizing the scan workflow while preserving existing shared core and instrument-library APIs.
- Details:
  - created independent v1.6 Python and UI copies,
  - added `func_cores/scan_data_core.py` for scan-step conversion, peak-tracking position generation, and repeated-sample peak analysis,
  - added `func_cores/scan_storage_core.py` for the standard Lock-in HDF5 dataset creation and single-point writes,
  - kept thread lifecycle, Qt signals, UI access, and hardware movement in the v1.6 main controller,
  - changed v1.6 to reuse the existing shared FFT implementation from `scan_func_core.py`, removing the duplicated main-program FFT method,
  - did not modify or remove functions in existing `func_cores` or `inst_libs` files,
  - corrected the default measurement-data root from `TPOP_Data` to `OPTP_Data`, while preserving manual save-path selection,
  - fixed the iTC shutdown race: `closeInstruments()` now requests and waits for an active stabilization thread before closing and clearing the MercuryiTC instance,
### v1.7
- Date: 2026-08-06
- Main change: Added guarded stage enable flow and safer stage object assignment for BBD202 connections.
- Details:
  - Used guarded temporary stage instances during initial connection and homing.
  - Ensured hardware handle `.close()` is called on failure to prevent locked sessions.

### v1.8
- Date: 2026-08-06
- Main change: Initialized v1.8 version copies (`OPTP_system_iTC_v1.8.py` and `OPTP_iTC_main_v1.8.ui`) from v1.7.
- Details:
  - Duplicated main executable script and Qt UI layout file for v1.8 development.
  - Linked `OPTP_system_iTC_v1.8.py` to load `OPTP_iTC_main_v1.8.ui`.

### v1.9
- Date: 2026-08-08
- Main change: Fixed UI freezing issue caused by blocking I/O on the main thread when updating iTC parameters.
- Details:
  - Refactored `MercuryiTC_Updater` to inherit from `QThread` instead of using a `QTimer` on the main thread.
  - Implemented thread-safe UI updates using the `display_updated` Qt Signal.
  - Updated `closeInstruments()` to gracefully stop and wait for the `MercuryiTC_Updater` background thread before closing the instrument to prevent crashes on termination.

### v1.91
- Date: 2026-08-08
- Main change: Upgraded wait time multiplier input to support decimal values.
- Details:
  - Replaced `QSpinBox` with `QDoubleSpinBox` for `wait1multip` and `wait2multip` in the Qt UI file, allowing float multipliers (e.g., 1.2, 3.5).
  - Updated `apply_lockin_parameter` calculation to properly `round` the multiplied float result before converting to an integer millisecond wait time.

### v2.0
- Date: 2026-08-08
- Main change: Initialized v2.0 version copies (`OPTP_system_iTC_v2.0.py` and `OPTP_iTC_main_v2.0.ui`) from v1.91, and modified 1D THz peak tracking logic.
- Details:
  - Duplicated main executable script and Qt UI layout file for v2.0 development.
  - Linked `OPTP_system_iTC_v2.0.py` to load `OPTP_iTC_main_v2.0.ui`.
  - Moved the `get_TDS_peak_pos` logic inside the main `scan_iterator` loop and removed the `ScanT.isChecked()` dependency. The system will now automatically re-track and calibrate the THz peak at the start of *every* 1D THz sweep (e.g. for every polarization/pump power change or repeat cycle), preventing peak drift issues caused by optical path variations during the experiment.
  - Added a new HDF5 dataset `dynamic_THz_peak_pos` (specifically for `1D_THz` mode) to seamlessly record the tracked Stage1 peak position at each sweep. This ensures the precise zero-delay coordinate is logged for post-processing.

### v2.1
- Date: 2026-08-08
- Main change: Upgraded OPTP polarization calibration parser to natively support `.csv` file format.
- Details:
  - Duplicated OPTP v2.0 files to v2.1.
  - Rewrote `import_calibration_file()` to safely read standard comma-separated `.csv` files using Python's `csv` module, aligning with MO v2.0 logic.
  - Added robust fallback for missing/empty columns (e.g. `Stage3_deg`) to default to `0.0`, avoiding parsing `ValueError`.
  - Maintained backward compatibility for legacy `.txt` whitespace-separated calibration files.

### v2.2
- Date: 2026-08-10
- Main change: Fixed missing "curr NO" / current-position display updates during the TDS (1D_THz) peak-tracking calibration scan.
- Details:
  - Duplicated OPTP v2.1 files to v2.2 (`OPTP_system_iTC_v2.2.py`, `OPTP_iTC_main_v2.2.ui`), and linked the script to load the v2.2 UI file.
  - `get_TDS_peak_pos()` moves Stage1 directly via `self.stage1.move_to(pos)` during peak-tracking calibration, but previously never emitted `stepNO_update`/`position_update`, so the `stage1CurrStepNO` and `stage1CurrPos` displays stayed frozen for the whole calibration sweep.
  - Added `thread.stepNO_update.emit({'stage1_NO': idx})` and `thread.position_update.emit({'stage1_pos': ...})` inside the peak-tracking loop so both displays now refresh in real time during TDS peak calibration.

### v2.3
- Date: 2026-08-10
- Main change: Initialized v2.3 version copies (`OPTP_system_iTC_v2.3.py` and `OPTP_iTC_main_v2.3.ui`) from v2.2, and fixed `get_TDS_peak_pos()` running only a single local-window pass instead of the intended 3-round converging peak search.
- Details:
  - Duplicated main executable script and Qt UI layout file for v2.3 development.
  - Linked `OPTP_system_iTC_v2.3.py` to load `OPTP_iTC_main_v2.3.ui`.
  - Refactored `get_TDS_peak_pos()` to extract the local-window scan (20 positions, 3-sample averaging per point) into an inner `run_single_pass()` helper.
  - The calibration now runs 3 converging rounds: each round re-centers the local search window on the previous round's found peak position, then returns the final round's converged peak. Previously only one pass ran before the scan proceeded, so drift/noise on a single pass could mis-locate the peak.
  - Fixed occasional UI freeze when clicking "Goto T" after a scan finished: `iTC_goto_targetT()` (called directly on the GUI thread from the `iTCgoT` button) previously called `self.itc_stab_thread.wait()` with no timeout, which blocked the whole UI indefinitely whenever the previous `iTCstabilizeThread` was still actively polling (hadn't reached its stability condition yet). Now it sets the stale thread's own `stop_flag` (without touching the shared scan `self.stop_flag`) and waits with a bounded 2 s timeout before starting the new stabilization thread.

### v2.4
- Date: 2026-08-10
- Main change: Initialized v2.4 version copies (`OPTP_system_iTC_v2.4.py` and `OPTP_iTC_main_v2.4.ui`) from v2.3, and fixed a `ValueError` crash in `update_TDS_FDS_chart()` when the TDS trace contains only a single point (fix applied to both v2.3 and v2.4).
- Details:
  - Duplicated main executable script and Qt UI layout file for v2.4 development.
  - Linked `OPTP_system_iTC_v2.4.py` to load `OPTP_iTC_main_v2.4.ui`.
  - Crash trace: `DataProcess.thz_fft_calc()` → `np.min(np.abs(np.diff(time_ps)))` raised `ValueError: zero-size array to reduction operation minimum which has no identity`. A 1-element position array makes `np.diff` return an empty array, so `np.min` has nothing to reduce.
  - Root cause: `update_TDS_FDS_chart()` only guarded against *empty* data (`len(x) == 0`), so a single-point trace passed the guard, plotted fine on the TDS chart, then crashed in the FFT step. Single-point traces arise when the scanned stage has no valid step configuration — `ScanPlanner.generate_position_sequence()` (`func_cores/scan_func_core.py`) falls back to a static single position when every step size / step NO is 0 — and, less commonly, when nearly all Lock-in readings during peak tracking are NaN so `analyze_peak_samples()` retains only one finite point.
  - Fix: added a `len(x) < 2` guard before the FFT call. The TDS curve is still drawn, the FDS/FFT update is skipped, and a warning naming the likely step-size/step-NO misconfiguration is printed instead of raising.
  - Routed the peak-search sweep to the correct chart (also applied to both v2.3 and v2.4). The local peak-tracking window is an alignment sweep, not a THz time-domain trace, so running FFT over it and pushing it into the TDS/FDS charts was wrong.
    - Removed the `thread.tds_update.emit(tds_data)` call from the 1D_THz peak-calibration block in `_execute_scan_logic()`, so the peak-search window no longer overwrites the TDS chart nor feeds the FDS/FFT chart. The `tds_update` signal remains in use by the two genuine TDS paths (`THz_Scan`/`2D_THz` and `1D_THz` sweeps).
    - `get_TDS_peak_pos()` now emits `thread.lockin_update.emit({'l1x': <averaged reading>})` once per stage position, so the peak search is displayed live, point by point, in the realtime Lock-in 1 X chart as it progresses.
    - Side effect: this also removes the peak-tracking path as a source of the single-point FFT crash above, since the peak window no longer reaches `thz_fft_calc()`.
  - Removed the per-position 3× repeat sampling from `get_TDS_peak_pos()` (also applied to both v2.3 and v2.4). Each stage position is now read once from Lock-in 1, and noise rejection is handled entirely by the 3 converging rounds added earlier in v2.3.
    - Rationale: the per-point averaging (originally from v1.5) and the 3-round convergence (added in v2.3) were stacking, giving 3 rounds × 20 positions × 3 samples = 180 readings per calibration — and this calibration runs before every 1D_THz sweep.
    - Total readings per calibration drop from 180 to 60 (3 × 20 × 1), roughly a 3× speedup, and the per-sample `wait1` settling delays between repeats are gone as well.
    - `ScanDataCore.analyze_peak_samples()` in `func_cores/scan_data_core.py` was left unchanged: the call site now passes a single-element reading list `(pos, [x_val])`, which the existing averaging/finite-filtering logic already handles (verified — a NaN-only position is still dropped, and an all-NaN sweep still returns `status: failed`).

### v2.4 (feature/bugfix round 2 - v2.4 only)
- Date: 2026-08-10
- Main change: Widened the peak-search window to 40 points, fixed the silent application crash when scanning with no instruments connected, and added an `ext_info` filename suffix with a placeholder hint. These changes are applied to v2.4 only; v2.3 is not updated.
- Details:
  - **Peak-search window widened to +/-20 steps (40 points).** The call in `get_TDS_peak_pos()` now passes `points_before_center=20, points_after_center=20` explicitly instead of relying on the shared default of 10/10 (which produced only 20 points). `ScanDataCore.build_peak_tracking_positions()` in `func_cores/scan_data_core.py` is left untouched so other systems keep their existing behaviour. Verified the window is exactly 40 positions (offsets -20 .. +19, centre included). Cost: readings per calibration rise from 60 to 120 (3 rounds x 40 points), roughly doubling peak-search time.
  - **Peak tracking remains restricted to `1D_THz` mode** - unchanged by request; other scan modes still skip it silently.
  - **Fixed silent UI shutdown when starting a scan with no instruments connected.** Root cause: every scan-update slot (`update_curr_repeat`, `update_curr_pos`, `update_curr_step`, `update_curr_stepNOs`, `update_lockin_charts`, `update_pol_chart`, `update_TDS_FDS_chart`, `update_iPos1_from_tds_peak`) ended with `QApplication.processEvents()`. Those slots already run on the GUI thread via queued connections, so `processEvents()` re-entered the event loop and dispatched the next queued scan signal from inside the current slot. With no instruments there is no hardware latency to throttle the scan loop, so the nesting depth grew without bound until the stack overflowed and the process was killed by the OS - no Python traceback, the window just vanished.
    - Confirmed empirically in the target environment (PySide6 6.11.0 / Python 3.13.13): a minimal worker-emits-fast + `processEvents()`-in-slot reproduction reached nesting depth 100+ and then died silently, matching the reported symptom. Also verified in the same environment that an unhandled exception inside a slot only prints a traceback and does *not* terminate the app, ruling that out as the cause.
    - Fix: removed `QApplication.processEvents()` from all high-frequency scan-signal slots. The calls in `connectInstruments()`, `closeInstruments()`, `iTC_goto_targetT()` (button path) and `set_ControlsEnabledDuringScan()` are kept - those are main-thread user actions, not flooded. The calls in `update_temp_hightlight()` / `on_temp_done()` are also kept: they fire once per temperature point, so they cannot produce unbounded nesting.
  - **Added a pre-scan instrument check.** New `check_instruments_ready()` returns the display names of devices ticked "active" but not actually connected (and flags the case where nothing is active at all). `runScan()` now refuses to start, prints the list and shows a `QMessageBox` warning, instead of running the whole loop against `None` devices and writing a file full of zeros.
  - **Hardened `itc_stab_thread` lifecycle.** It is now initialised to `None` in `__init__` (previously it simply did not exist until the first `iTC_goto_targetT()` call). `iTC_goto_targetT()` returns a bool indicating whether a stabilization thread was really started, and the temperature loop in `_execute_scan_logic()` only builds the `QEventLoop` and waits when that is true. Previously, with `ScanT` ticked but the iTC disconnected, `iTC_goto_targetT()` returned early and the caller still touched `self.itc_stab_thread`, raising `AttributeError` on the first run or - worse - blocking the scan thread forever on a stale thread whose `finished` signal had already been emitted. The `hasattr()` guards in `on_tolerance_changed()` and `stopscan()` were switched to `is not None` checks accordingly.
  - **`ext_info` box wired into the data file name.** New `get_ext_info()` reads `self.ui.ext_info`, strips whitespace, replaces the Windows-illegal characters `\ / : * ? " < > |` with underscores and trims trailing spaces/dots, logging the substitution when one occurs. `setup_dataFile_Name()` appends it, giving `{timestamp}_{scan_mode}[_{T}K]_{ext_info}.h5`. Sanitizing is required, not cosmetic: an entry such as `50%/2` would otherwise make `h5py.File()` fail and abort the scan. Verified against the real implementation extracted from the source file. `import re` was added.
  - **Placeholder hint on the `ext_info` box.** `setPlaceholderText("Please input extra info.")` is set during UI initialisation, giving the greyed-out hint requested. `text()` does not return placeholder content, so an untouched box correctly yields no suffix.
  - **Peak tracking is now skipped when nothing can move the peak.** Previously the calibration ran before every 1D_THz sweep unconditionally. It is now gated on `peak_tracking_enabled`, computed once per temperature point: it requires `1D_THz` mode *and* either `temperature_varies` or `polarization_varies`. For a single-polarization, non-temperature run the manually aligned peak is used as-is and the 3-round / 40-point search is skipped entirely, saving 120 lock-in readings per sweep. A log line states when and why tracking is disabled, so the skip is never silent.
    - `temperature_varies` uses the existing `has_temperature` flag, i.e. `activeiTC` ticked AND the iTC connected AND `ScanT` ticked AND a non-empty temperature list. This satisfies both requirements at once: unticking `ScanT` disables tracking while the temperature points stay in the list (they are deliberately kept there while going back to calibrate the zero point), and a ticked `ScanT` with the iTC unticked/disconnected also skips tracking instead of searching for a temperature sweep that cannot happen.
    - `polarization_varies` requires the *same* rotary to be both ticked active and have step NO > 1, checked per rotary against `rotary1_NO` / `rotary2_NO` / `rotary3_NO`. An unticked rotary's step NO is irrelevant because it never moves. Pairing matters: an earlier draft used "any rotary ticked" AND "N_pol > 1" as independent conditions, which wrongly enabled tracking when, say, rot1 was ticked with NO=1 while an unticked rot2 had NO=8. Note also that `N_pol` alone is not a valid signal, since the rotary position sequences are built from the UI spin boxes regardless of the active checkboxes.
  - **Peak search restructured into a two-round coarse-to-fine sweep** to survive the large thermal expansion that comes with a wide temperature range, where the peak could drift outside the old fixed window and the search would fail.
    - Round 1 (coarse) sweeps at `COARSE_STEP_FACTOR = 3` x the configured step; round 2 (fine) re-centres on the coarse result and refines at the normal step. The window is `+/-30` points per round, so each round takes 60 readings and the whole search is 120 - unchanged from the previous 3 x 40.
    - With a 1 um step this covers `+/-90 um` on the coarse round (up from `+/-20 um`), a 4.5x increase in search range, and `+/-30 um` on the fine round.
    - The coarse factor is deliberately small: this is an ultra-broadband THz pulse of roughly 40 fs FWHM, which is only ~6 um of stage travel, so a large coarse step would sample straight over the top of the peak and miss it entirely. At factor 3 the coarse round still lands ~2 points within the FWHM. (An earlier proposal of factor 15 was based on a wrong 500 fs pulse-width assumption and would have stepped clean over the peak.)
    - Verified by simulation against a synthetic 40 fs THz waveform with oscillatory side lobes at +/-12 um plus noise: drifts of 0, 5, 20, 50 and 85 um were all located exactly, with the side lobes correctly rejected in favour of the main peak. A 120 um drift falls outside the coarse coverage and fails, as expected for the chosen range.
    - Known limitation (accepted for now): the search still uses a plain `max()` with no test for whether a real peak was found, so a drift beyond the coarse range, or a window sitting in noise, returns a boundary/random point silently rather than reporting failure. Adding the bracketing / prominence / amplitude-regression criteria ("option B") would make such failures visible; deferred until live running shows whether it is needed.
- Verification: `python -m py_compile` passes; the coarse-to-fine search, the filename sanitization and the crash reproduction were each checked by direct execution, and the peak-tracking gate was checked against a truth table covering all seven combinations of scan mode / temperature scan / rotary-active / `N_pol`. Not yet exercised against real hardware - the chart refresh behaviour after removing `processEvents()` still needs a live run to confirm it stays smooth.

### v2.5
- Date: 2026-08-10
- Main change: Initialized v2.5 version copies (`OPTP_system_iTC_v2.5.py` and `OPTP_iTC_main_v2.5.ui`) from v2.4, and added an extra sample-soak wait after temperature stabilization.
- Details:
  - Duplicated main executable script and Qt UI layout file for v2.5 development; linked `OPTP_system_iTC_v2.5.py` to load `OPTP_iTC_main_v2.5.ui`.
  - **Added `wait_sample_stable()`**, an extra hold after the iTC reports the sensor temperature stable and before the scan starts. The iTC sensor reaching its setpoint does not mean the sample has - the sample lags behind, and scanning too early leaves residual thermal expansion/contraction that shifts the THz peak during the sweep.
    - Duration comes from the `WaitSamStable` spin box (already present in the UI, unit minutes, default 10).
    - Counts down in 5 s steps, printing `Sample soak countdown: MM:SS remaining (n/total s)` on each tick.
    - Checks the stop flag on every tick via the existing `_check_scan_stop()`, so Stop is honoured within 5 s instead of blocking for the full soak period. Returns False on stop, and the temperature loop breaks out rather than scanning anyway.
    - A value of 0 min short-circuits immediately, so the feature can be disabled without code changes.
  - Call site: placed in `_execute_scan_logic()` immediately after the stabilization `QEventLoop` completes and the temperature-done LED is set, inside the branch that only runs when a stabilization thread was actually started.
- Verification: `python -m py_compile` passes. `wait_sample_stable()` was extracted and executed directly against three cases - a normal countdown (15 s stand-in for the 10 min default, correct total duration and 5 s tick spacing), a mid-wait stop request (exited early with the remaining time reported, returned False), and a 0 min setting (returned immediately). Not yet exercised against real hardware.

### v2.5 (abort scan on failed temperature stabilization)
- Date: 2026-08-10
- Main change: The scan no longer continues after temperature stabilization has failed. Found during a review of the v2.4 -> v2.5 delta.
- Details:
  - Problem: `iTCstabilizeThread.finished` is a `Signal(bool)` emitted with `False` on four different failure paths (iTC not connected, temperature UID missing, an exception inside the poll loop such as a failed `read_temperature()`, and a user stop) and with `True` only when the temperature genuinely settled. The temperature loop connected it as `finished.connect(loop_for_Tstab.quit)`, and `quit()` takes no arguments, so **the bool was silently discarded**. A single raising `read_temperature()` therefore ended the wait immediately, lit the temperature-done LED green unconditionally, and the scan proceeded at an uncontrolled temperature while the file name still claimed `..._{target_T}K`.
  - The v2.5 soak wait made the consequence worse rather than causing it: the pre-existing behaviour was to scan wrongly straight away, whereas the soak first burned the full wait (10 min by default) per temperature point and *then* scanned wrongly.
  - Fix: `iTCstabilizeThread` now also records its outcome as plain state (`self.stab_success`, reset at the top of `run()` and set to True only immediately before `finished.emit(True)`). The temperature loop reads that after the wait, emits `temp_done_led` with the real result instead of a hardcoded `True`, and `break`s out of the temperature loop with an explicit message when stabilization failed - measuring at an uncontrolled temperature is worse than stopping.
  - State is used rather than the signal payload deliberately: the caller connects to `finished` only *after* `iTC_goto_targetT()` has already started the thread, so a thread that fails immediately can emit `finished` before the connection exists. The payload would never arrive, and - worse - `loop_for_Tstab.exec()` would then block forever. The event loop is now entered only `if self.itc_stab_thread.isRunning()`, closing that deadlock, and the outcome is read from the attribute either way.
  - Not changed: no temperature re-check was added after the soak wait. It is unnecessary - the MercuryiTC regulates in hardware (`enable_auto_pid_table` / `enable_pid_control` are one-shot writes, the stabilization thread only observes), and `MercuryiTC_Updater` keeps polling in its own thread with `realtimeDispT` whitelisted in `set_ControlsEnabledDuringScan()`, so the temperature stays controlled and visibly displayed throughout the soak.
- Verification: `python -m py_compile` passes. All five `run()` exit paths were simulated against the caller's decision logic: only a genuine settle proceeds to the soak and the scan; iTC-not-connected, missing UID, a read exception and a user stop all abort.

### v2.6
- Date: 2026-08-14
- Main change: Initialized v2.6 version copies (`OPTP_system_iTC_v2.6.py` and `OPTP_iTC_main_v2.6.ui`) from v2.5, and fixed "Close Instr." closing every instrument regardless of its 'active' checkbox.
- Details:
  - Duplicated main executable script and Qt UI layout file for v2.6 development; linked `OPTP_system_iTC_v2.6.py` to load `OPTP_iTC_main_v2.6.ui`.
  - Problem: every block in `closeInstruments()` tested only `if self.<device>:` - i.e. "is it connected" - and never the matching `active*` checkbox, unlike `connectInstruments()` which gates each block on `if self.ui.activeXxx.isChecked():`. Unticking a box and pressing "Close Instr." therefore also dropped the instruments the user intended to keep.
  - Fix: added a `should_close(active_box_name)` helper and gated each device on it, mirroring the `connectInstruments()` convention.
  - `closeInstruments()` gained an `only_active: bool = True` parameter. The button closes only ticked instruments; `exitApp()` now calls `closeInstruments(only_active=False)` so that anything still open is released on exit - otherwise a connected but unticked instrument would keep its handle and leave the port locked after the application quit.
  - The `iTCstabilizeThread` shutdown at the top of the function is now gated on actually closing the MercuryiTC (`closing_itc`). It calls `request_stop()`, which also raises the main `stop_flag` and would abort a running scan; that must not happen merely because some unrelated instrument is being closed.
  - The button connection was rewritten as `clicked.connect(lambda: self.closeInstruments(only_active=True), False)`. This is required, not cosmetic: `clicked` emits a `checked` bool, and with the old direct connection Qt passes it into the slot's first parameter. Verified empirically - a direct connection sets `only_active=False`, silently defeating the whole fix, while the lambda keeps it True.
- Verification: `python -m py_compile` passes. The real `closeInstruments()` was extracted from the source and executed against stub instruments in three scenarios: with only Stage1 and Lock-in 1 ticked the button closed exactly those two and left the other six connected; with `only_active=False` (the exit path) all eight were released even though only one box was ticked; and with nothing ticked the button closed nothing. Not yet exercised against real hardware.

### v2.7
- Date: 2026-08-15
- Main change: Initialized v2.7 version copies (`OPTP_system_iTC_v2.7.py` and `OPTP_iTC_main_v2.7.ui`) from v2.6, and fixed `VI_ERROR_INV_OBJECT` on closing instruments after the iTC controller is taken out of remote/unlock mode. The root cause was in the shared instrument libraries, so `inst_libs/` was changed too (backed up first).
- Details:
  - Reported symptom: taking the MercuryiTC controller out of remote/unlock mode and then returning to the software produced, on exit, `pyvisa.errors.VisaIOError: VI_ERROR_INV_OBJECT (-1073807346)` raised from `self.lockin1.close()` -> `stanford_SR830.close()` -> `self._rm.close()`. Note the crash was in **Lock-in 1**, not the iTC, which is what made the cause non-obvious.
  - **Root cause: every instrument library closed the shared VISA ResourceManager.** `pyvisa.ResourceManager()` is a process-wide singleton - verified empirically that `pyvisa.ResourceManager() is pyvisa.ResourceManager()` returns True (pyvisa 1.16.2). All instruments therefore held the *same* manager object, and each `close()` did `self._inst.close()` (correct) followed by `self._rm.close()` (wrong). `rm.close()` walks every resource the manager ever created and closes it; once the iTC session had been killed at the controller, that walk hit the dead resource and raised - from inside Lock-in 1's close, before any other instrument had been closed. Everything after it stayed open with its port locked.
  - This also silently broke the v2.6 selective-close feature: closing one instrument tore down the manager that the instruments the user wanted to *keep* were still using, leaving them connected in software but dead at the VISA level.
  - **Fix (shared libraries):** removed `self._rm.close()` from `close()` in `stanford_SR830.py`, `Oxford_mercuryiTC_Thread.py`, `Oxford_mercuryiTC.py` and `newport_PM500.py`; each now closes only its own resource and drops its reference to the manager. The manager stays alive for the process, which is how pyvisa is meant to be used, and is released at interpreter exit.
  - The originals were copied to `inst_libs/backup_before_rm_fix/` first, with a `README.md` recording the reasoning and restore instructions. These libraries are shared with MO_System and OPTP_image_System, which carry the same defect and benefit from the same fix.
  - **Fix (v2.7 `closeInstruments`):** each instrument is now closed through a `close_one()` helper that isolates failures - a raising `close()` is logged as a warning and the sequence continues, and the reference plus LED are cleared in a `finally` block since the session is gone either way. The MercuryiTC block got the same treatment with a message pointing at remote mode as the likely cause. Previously a single failure aborted the whole shutdown.
- Verification: `python -m py_compile` passes for the v2.7 script and all four libraries; no `_rm.close()` remains outside the backup directory. The real `closeInstruments()` was extracted and run against stubs with the MercuryiTC rigged to raise `VI_ERROR_INV_OBJECT`: the call no longer propagates an exception, the other seven instruments all close normally, the failure is reported as a warning, and every reference plus `uid_HTR`/`uid_TEMP` is cleared. Not yet exercised against real hardware.

### v2.8
- Date: 2026-08-28
- Main change: Initialized v2.8 version copies (`OPTP_system_iTC_v2.8.py` and `OPTP_iTC_main_v2.8.ui`) from v2.7, linked `OPTP_system_iTC_v2.8.py` to load `OPTP_iTC_main_v2.8.ui`, and fixed `set_heater_percent()` reporting "MercuryiTC device not connected." while the iTC was in fact connected.
- Details:
  - Reported symptom: setting the heater percentage in the UI printed `MercuryiTC device not connected.` to the terminal and the value was never applied, even though the iTC was connected and the real-time temperature display was updating.
  - **Root cause: a three-condition guard sharing one misleading error message.** `set_heater_percent()` was written as `if activeiTC.isChecked() and self.parent.mercuryiTC and not autoPID.isChecked(): ... else: print("MercuryiTC device not connected.")`. The third condition is a deliberate policy - manual heater control must be blocked while the PID loop owns the heater - but it fell through to the same `else` as the two genuine connection checks. With Auto PID engaged the function therefore reported a connection failure that had not happened. The sibling `set_heater_limit()` has only the two connection conditions, which is why it was unaffected and why the asymmetry pinpointed the cause.
  - Ruled out during diagnosis, recorded so they are not re-investigated: `MercuryiTC` defines no `__bool__`/`__len__`, so a live object is always truthy; `io_lock` is a `threading.RLock`, so the nested `query()` inside `set_heater_voltage()` cannot self-deadlock; no code path calls `activeiTC.setChecked()` or `autoPID.setChecked()`; and both the connect-failure and close paths reset `self.mercuryiTC = None`, so an object with a dead `_inst` (which would raise the driver's *different* message, `Not connected. Call open() first.`) is not reachable in normal use.
  - Fix: the guard was split into three sequential early returns, each with its own message - `MercuryiTC device not connected.` for the connection checks, `MercuryiTC is in Auto PID mode - manual heater setting skipped. Turn off Auto PID first.` for the PID case, and the pre-existing `MercuryiTC heater UID not available.` for a missing UID. The instrument communication inside the `try` block is byte-for-byte unchanged; only its indentation changed as a consequence of removing the enclosing `if`.
  - Also linked `OPTP_system_iTC_v2.8.py` to `OPTP_iTC_main_v2.8.ui` (line 68), following the per-version convention of v2.5-v2.7. The two `.ui` files are byte-identical for now; the v2.8 copy exists so that future layout edits do not disturb v2.7.
  - Convention note for future edits: **every `.py` and `.ui` file in this folder uses CRLF line endings throughout.** `sed -i` under MSYS/Git-Bash silently rewrites the whole file as LF, which turns a two-line change into a whole-file diff; `sed -n 'Np'` likewise strips the CR when printing, so it cannot be used to verify line endings. Both edits in this entry were applied by reading the file as bytes and writing CRLF back explicitly.
- Known issues found during this diagnosis but deliberately NOT fixed in this entry (scope was limited to the error reporting):
  - The `autoPID` `QPushButton` is `checkable` and latches on click, but `setup_pid_mode()` never reverts it when `setup_autoPID_mode()` returns False - it only drives `autoPID_led` from the result, and prints `iTC PID mode set to Auto.` unconditionally without consulting it. The button, the LED and the instrument can therefore disagree, and `set_heater_percent()` reads the *button*.
  - `set_heater_percent()` writes `HTR:SIG:VOLT` via `set_heater_voltage()` rather than the driver's dedicated percentage command `set_heater_manual()` (`HTR:SIG:HSET`), which is unused project-wide. If the instrument-side PID loop is still active, a direct voltage write is overridden by the control loop.
  - Unlike `set_heater_limit()`, which waits `qwait_time(50)` between write and read-back, `set_heater_percent()` verifies immediately inside the same lock, making a spurious "verification failed" warning likely.
  - The percent-to-voltage mapping is linear (`percent/100 * vlim`) while heater power scales as V^2/R, so the UI percentage is a percentage of voltage, not of power. The display path uses the same linear formula so the UI is self-consistent, but it will disagree with the instrument front panel.
  - Nothing reads the instrument's actual PID state on connect, and the PID-reset call in `closeInstruments()` remains commented out, so the `autoPID` button can start a session out of sync with the hardware.
- Verification: `python -m py_compile` passes. `diff -u` against v2.7 reduces to exactly two hunks - the `.ui` filename on line 68 and the `set_heater_percent()` body - with no incidental whitespace or line-ending changes; both files were confirmed 100% CRLF with a byte-level count, and the two `.ui` files compare byte-identical under `cmp`. The instrument communication inside the `try` block is unchanged apart from indentation. The four branches were checked by inspection against the reported symptom. Not yet exercised against real hardware - a live run is still needed to confirm that disengaging Auto PID lets the heater percentage apply.

### v2.8 (heater percentage semantics, Auto PID state sync)
- Date: 2026-08-28
- Main change: Fixed the five defects recorded as "known but not fixed" in the entry above. The heater percentage now goes through the control loop's own HSET command instead of being converted to a voltage, and the Auto PID button can no longer disagree with the instrument. The root cause of the percentage defect was in the shared driver, so `inst_libs/Oxford_mercuryiTC_Thread.py` was changed too (backed up to `inst_libs/backup_before_hset_fix/` first).
- Details:
  - Reported symptom: the percentage set in the UI did not match the percentage displayed - "it showed about half".
  - **Root cause: the UI percentage was a percentage of voltage, the instrument's is a percentage of power.** `set_heater_percent()` mapped the UI value linearly onto the voltage limit (`V = percent/100 x VLIM`) and `MercuryiTC_Updater.run()` inverted the same linear formula for the display, so the two agreed *with each other* but not with the controller: heater power scales as V^2/R, so a UI setting of 50 % drives the heater to (0.5)^2 = 25 % of full power, which is what the front panel reports.
  - **Driver fix - `set_heater_manual()` addressed the wrong subsystem.** It sent `SET:DEV:<uid>:HTR:SIG:HSET:<percent>`, mixing the heater device path (`HTR:SIG`) with a loop parameter. Every other loop parameter in the driver - TSET, P, I, D, ENAB, PIDT, and the heater assignment itself - uses `DEV:<temperature uid>:TEMP:LOOP:<param>`. Corrected to `SET:DEV:<temp_uid>:TEMP:LOOP:HSET:<percent>` and the argument renamed `temp_uid`. The method had **no callers anywhere in the project** (verified by grep across all systems), so this cannot regress existing behaviour.
  - Added `get_heater_manual(temp_uid)` (`READ:...:TEMP:LOOP:HSET`) and `get_pid_control_state(uid)` (`READ:...:TEMP:LOOP:ENAB`) to the driver. Both are additive; nothing else in `inst_libs/` was touched, so MO_System and OPTP_image_System are unaffected apart from gaining the two methods and the corrected (previously dead) one.
  - **Percentage semantics:** `set_heater_percent()` now calls `set_heater_manual(uid_TEMP, percent)` and verifies with `get_heater_manual()`, and the display thread reads the same HSET value instead of `read_heater_voltage() / get_heater_voltage_limit()`. UI percentage, verification and front panel are now the same quantity by construction rather than by coincidence, and the voltage conversion is gone entirely. VLIM still caps the output in hardware and `HeaterLim` still drives it, unchanged.
  - **Verification timing:** the read-back now happens after `qwait_time(50)`, mirroring `set_heater_limit()`. The wait is placed *between* two separate `io_lock` blocks rather than inside one, because `qwait_time()` pumps the Qt event loop and holding the instrument lock across that invites re-entrant I/O.
  - **Auto PID button/LED/instrument disagreement:** `setup_autoPID_mode()` returned `auto_PID_status` on success and `False` on failure, so *successfully switching PID off* was indistinguishable from a failure. It now returns whether the instrument accepted the change. `setup_pid_mode()` reverts the button when the change is rejected - the button is `checkable` and latches on click, so it previously kept advertising a mode the instrument never entered, and `set_heater_percent()` reads the **button**, not the LED. The not-connected early return had the same hole and now reverts too. The three places that write the button share a `_set_autoPID_button()` helper that wraps the write in `blockSignals()` so it cannot re-enter the `toggled` handler.
  - **PID state read-back on connect:** new `_sync_autoPID_from_instrument()` reads `TEMP:LOOP:ENAB` and sets the button and LED from it, called on both `connectInstruments()` paths (fresh connect and UID re-fetch). Previously the button was purely local state, so a session starting while the iTC was still in PID mode showed "Manual" while the loop was in fact driving the heater - and would then silently override any manual heater setting. A failed read leaves the button alone and warns rather than guessing.
- Known issues found but NOT fixed here:
  - `set_heater_limit()` still calls `qwait_time(50)` *inside* its `io_lock` block, pumping the Qt event loop while holding the instrument lock. `io_lock` is an `RLock`, so a UI action during that window re-enters on the same thread without blocking and can interleave VISA traffic. Left alone as out of scope; `set_heater_percent()` no longer does this.
  - The PID reset on shutdown in `closeInstruments()` remains commented out, so the controller is left in whatever mode the session ended in. The new connect-time read-back means the UI at least reports that state correctly on the next run.
- Verification: `python -m py_compile` passes for both the v2.8 script and the driver; the driver diff against its backup is confined to one corrected command string, one renamed argument, two new methods and their docstrings. A stub harness extracted the real `set_heater_percent`, `setup_pid_mode`, `_set_autoPID_button` and `_sync_autoPID_from_instrument` via `ast` and ran 17 checks, all passing: the four guard branches each report their own message; a 42 % set issues exactly `HSET` then `READ HSET` against the temperature UID with no voltage conversion; a rejected command is caught and reported; set and displayed percentages agree exactly at 25/50/75/100 %; the button and LED are reverted both when disconnected and when the instrument rejects the change, switching PID off is no longer misread as a failure, and the connect-time sync sets button and LED from the instrument's ENAB without firing the `toggled` handler. The driver was additionally driven through a fake VISA session to confirm the literal strings `SET:DEV:MB1.T1:TEMP:LOOP:HSET:42`, `READ:DEV:MB1.T1:TEMP:LOOP:HSET` and `READ:DEV:MB1.T1:TEMP:LOOP:ENAB`, and that the responses parse to 42.0 and True. **Not yet exercised against real hardware** - the HSET command path and the resulting percentage scale must be confirmed on the instrument, since no manual-heater command in this project has ever been executed against it.

### v2.8 (rotary connection failure handling)
- Date: 2026-09-15
- Main change: Rotary1/2/3 now follow the same "temp object, release and reset to `None` on failure" connection pattern already used by the linear stages, so a half-initialised rotary can no longer be mistaken for a connected one.
- Details:
  - Found while fixing the same defect in `THz_emission_system/THz_emission_system_iTC_v1.1.py`; this system carries an identical copy of the three rotary blocks.
  - Before: each block did `self.rotaryX = RotaryStage(...)` first and called `home(60000)` afterwards inside the same `try`. If the controller connected but homing failed, the exception was caught and only printed, leaving `self.rotaryX` holding a live but un-referenced object.
  - Consequence: `check_instruments_ready()` saw a non-`None` attribute and reported the rotary as ready and `move_active_stages()` then issued `move_to()` commands to a stage that had never been homed, so every recorded position for that axis was meaningless. The USB handle was also never released, keeping the port locked until the application exited.
  - After: each block builds `rotaryX_temp`, homes it, and assigns `self.rotaryX = rotaryX_temp` only once both steps succeeded. The `except` branch closes the temp object (errors during close are swallowed), sets `self.rotaryX = None`, and prints the same failure message as before.
  - Only the three connection blocks were touched: serials, channels, homing timeout, poll interval, `qwait_time()` calls, LED updates and all print messages are unchanged.
  - Stage1 and Stage2 in this file already used the guarded pattern, so they needed no change.
- Verification: `python -m ast` parses the patched file. The patch was applied by a line-based script that locates each `try` / `except Exception as e:` pair by its `✗ RotaryN connection failed` message and rewrites only the lines inside; running the same script against the already-fixed THz v1.2 file correctly reported "already patched" for all three blocks, confirming it does not double-apply. The failure branch itself is not runtime-tested because it needs the real controllers.

### v2.8 (2D_THz scan order: stage1 made the innermost axis)
- Date: 2026-09-15
- Main change: in `2D_THz`, one full stage1 time-domain trace is now recorded at each stage2 pump delay, instead of sweeping stage2 at each stage1 point.
- Details:
  - the shared `ScanPlanner.build_scan_iterator()` yields `itertools.product(pol, stage1, stage2)` for every non-POL_2D mode, and `product` varies its last argument fastest, so stage2 was the innermost axis. The nesting was polarization (slowest) -> stage1 -> stage2 (fastest), i.e. a full pump-delay sweep at each THz delay point - the opposite of what the mode means and of what the scanMode tooltip says,
  - two consequences of the old order: a single time-domain trace took as long as the whole 2D scan to accumulate, so slow laser drift appeared as waveform distortion rather than point-to-point noise; and the live TDS chart, gated on `stage1_idx == stage1_NO - 1`, only fired at the very end of each polarization block and then emitted `stage2_NO` times in a row,
  - `func_cores/scan_func_core.py` is shared by this system, OPTP, OPTP image and MO, so it was deliberately left untouched. The reordering is done in `OPTP_system_iTC_v2.8.py` only: right after `build_scan_iterator()` returns, a `2D_THz` run replaces `scan_iterator` with a locally built generator nested `pol -> stage2 -> stage1`, using the totals the planner already returns via `iterator_plan['pol_total']` / `['stage2_total']` / `['stage1_total']`,
  - the tuple layout is unchanged - `(stage1_flat_idx, stage2_flat_idx, pol_flat_idx)` - so `decode_scan_indices()`, the HDF5 index tuple and every display slot are untouched. Only `2D_THz` is affected; `THz_Scan`, `1D_THz` and `POL_1D` still use the planner's iterator verbatim,
  - confirmed this system needs the change: its `2D_THz` TDS chart is fed with `stage1_pos_sequence`, so stage1 is the THz delay line here. MO v2.2 was deliberately left alone - there `2D_THz` feeds the chart with `stage2_pos_sequence`, so stage2 is its delay line and the existing stage2-innermost order is already correct,
  - verified by driving the real planner plus the same override with 3 stage1 points x 2 stage2 points x 2 polarization states: the order is stage1 0,1,2 at stage2=0, then stage1 0,1,2 at stage2=1, then the same for the second polarization state, and the TDS chart condition fires exactly 4 times (once per pump delay per polarization state) instead of bursting at the end. The chart's data slice `ds_lockin1_X[:, rep, stage2_idx, ...]` is complete at every emit. Not yet exercised against real hardware.

### v2.9 (rotation stage coupling button)
- Date: 2026-09-15
- Main change: created OPTP_system_iTC_v2.9.py / OPTP_iTC_main_v2.9.ui from OPTP_system_iTC_v2.8.py / OPTP_iTC_main_v2.8.ui, and added the `Rot_stages_couple` button that selects whether the three rotation stages move independently or coupled. Ported from THz emission v1.2.
- Details:
  - the new .py loads the new .ui; nothing else was renamed, and the scan-mode list of this system was deliberately left untouched,
  - .ui: a checkable `QPushButton name="Rot_stages_couple"` was inserted as the first item of the layout that already held `pol_cali_mode` inside `rotary3Group`, so the row now reads Rot_stages_couple / pol_cali_mode / load_cali_file. Default caption `Independent`, `checked=false`, same sizePolicy / font / `mytype` as the neighbouring buttons,
  - its tooltip describes the two states: `Independent` - each rotation stage follows its own angle sequence and a stage whose step number is 1 stays at its initial angle and never moves; `Coupled` - Rotary1/2/3 step together, one angle each per polarization point, so all three must be given the same number of steps; plus a line recording that importing a calibration file forces coupled,
  - .py: added `on_rot_stages_couple_toggled()` next to `on_pol_cali_mode_toggled()` (it only flips the caption between `Coupled` and `Independent`), connected it next to the calibration-mode button and called it once at startup so the caption is right before the user touches anything,
  - .py: before the `build_pol_states()` call, `manu_cali_active = pol_cali_mode.isChecked() and self.cali_table` and `rot_stages_coupled = Rot_stages_couple.isChecked() or manu_cali_active`. Manual calibration overrides the button because `build_pol_states()` only consults the calibration table on the coupled path, so an imported table would otherwise be silently ignored; when the override actually changes the outcome a note is printed,
  - **behaviour change**: `polarization_policy` was hardcoded to `'coupled'` in v2.8 and is now `'coupled' if rot_stages_coupled else 'independent'`. With the button at its default `Independent`, the three rotary axes now form a cartesian product instead of being zipped index by index, so an axis whose step number is 1 holds its initial angle and the scan no longer aborts when the three step counts differ. To reproduce v2.8 exactly, press the button so it reads `Coupled`,
  - `func_cores/scan_func_core.py` was NOT touched - the `'independent'` branch already existed there and simply had never been selected from this system,
  - verified: the .py parses, the .ui loads through QUiLoader, the button comes up checkable / unchecked / captioned `Independent` with the new tooltip, it shares its parent with `pol_cali_mode` inside `rotary3Group`, the .py points at the new .ui, and `rot_stages_coupled` is assigned before every use. Not yet exercised against real hardware.

### v2.9 - Thorlabs stages skip homing when already homed
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
  - affected on this setup: Stage1 and Stage2 (BBD202, via `home_with_guard`) and Rotary1/2/3 (KDC101) - every motorised axis of this system,
  - verified by extracting the patched methods with `ast` and running them against stubs: with `is_homed()` True, `Home()` is called 0 times and the skip message is printed; with False, `Home()` is called exactly once; the BBD202 enable guard runs in both branches. The rewritten `is_homed()` was then driven with four backing shapes per driver - a device with no `IsHomed` anywhere (the shape that crashed on hardware), `Status.IsHomed` True and False, and `NeedsHoming` - 12 checks, all returning the expected value with no exception,
  - the skip path itself is still not confirmed on hardware: connect once, close the program, reconnect without power-cycling the controllers, and check that each axis prints `[Kinesis] Axis already homed, skipping homing move.` If the status object is not readable at that point the axis will simply home as before, which is the safe direction.

### v2.9 - Rotation angles wrapped into the travel; travel limits exposed
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

### v2.9 - Pre-scan travel check and per-axis movement errors
- Date: 2026-09-15
- Main change: ported the pre-scan travel check and the per-axis movement error message from THz emission v1.2, so a position that does not fit an axis stops the run before anything moves instead of failing mid-scan.
- Details:
  - the check was lifted verbatim from `THz_emission_system_iTC_v1.2.py` and inserted right after the polarization states are built, so the three copies cannot drift apart,
  - for each active and connected axis it asks the driver for `travel_limits()`; for an axis that also offers `resolve_target()` (the rotaries) it asks the driver to resolve each planned target instead of comparing against the raw limits, so a wrappable angle such as 367 deg on a full-turn stage is not reported as an error,
  - if anything is unreachable the scan stops before the first move and reports the axis, how many of the planned positions fail, the travel and the first few offending values; the HDF5 file is closed on that path like the other early-exit errors,
  - an axis that is unticked, not connected, or whose controller reports no travel is skipped - the move itself still guards those,
  - `move_active_stages()` now records which axis it is commanding, so a driver exception reads `Error moving Rotary2 to 367.0 deg: ...` instead of the anonymous `Error moving active stages: ...`. The five moves still share one `try`; only the message changed,
  - all five axes of this system expose `travel_limits()` (Stage1/Stage2 through the BBD202 driver, Rotary1/2/3 through the KDC101 driver), so every one of them is covered,
  - verified: the file parses, the check block matches the THz original, and all five axis labels are in place with the error line rewired. Not yet exercised against real hardware.

### v2.9 - rotary3 panel synced with THz emission v1.2
- Date: 2026-09-15
- Main change: the whole `rotary3Group` panel was replaced with the one from THz emission v1.2, so the four systems now share an identical rotary3 / calibration panel.
- Details:
  - the earlier port only inserted the `Rot_stages_couple` button next to `pol_cali_mode`; the rest of the panel was still the older layout. Three differences remained: the `Cali. file` caption was still a separate `label_57` above the path box, the button row sat above the path box instead of below it, and `rotary3Step` with its `label_53` was still on the second row rather than beside `iRot3` on the first,
  - the group's own container also differed - `QFormLayout formLayout_5` here against the `QVBoxLayout` pair THz was restructured to,
  - fix: the single child `<layout>` of `rotary3Group` was replaced wholesale with the corresponding block from `THz_emission_system_iTC_v1.2.ui`. The group box's own properties (`sizePolicy`, `title`) were left untouched, and the panel only ever contained widget names shared by all four systems, so nothing system-specific was lost. `label_57` disappears with the old block,
  - no object-name collisions in this file, so the incoming block was inserted unchanged,
  - `.py`: added `self.ui.cali_file_path.setPlaceholderText("Cali. file")` so the caption now shows greyed-out inside the path box, the way the THz system does it. Placeholder text is not returned by `text()`, so an untouched box still counts as "no calibration file",
  - verified by loading all four .ui through QUiLoader and comparing the `rotary3Group` widget tree (layout names excluded): the three ported panels are now structurally identical to THz v1.2, `label_57` is gone everywhere, every key widget (`Rot_stages_couple`, `pol_cali_mode`, `load_cali_file`, `cali_file_path`, `rotary3Step`, `rotary3StepNO`, `rot3CurrPos`, `iRot3`, `activeRot3`) resolves, the coupling button reads `Independent` with the coupling tooltip, and the calibration box shows the `Cali. file` placeholder while `text()` stays empty. Not yet exercised against real hardware.

### v2.9 - Superseded versions archived into `old_version/`
- Date: 2026-09-23
- Main change: moved the v2.6, v2.7 and v2.8 code and UI files out of `OPTP_System/` into `OPTP_System/old_version/`, so only the current v2.9 pair sits at the top level.
- Details:
  - moved with `git mv` (history preserved): `OPTP_system_iTC_v2.6/2.7/2.8.py` and `OPTP_iTC_main_v2.6/2.7/2.8.ui`,
  - this continues the existing convention - `old_version/` already held everything up to v2.5,
  - each version's `.py` resolves its `.ui` through `os.path.dirname(os.path.abspath(__file__))`, so the pairs still load correctly from their new location; no path edits were needed,
  - nothing outside the dev logs and `OPTP_handoff.md` referenced the moved files, so no imports or configs were touched. The mentions in `OPTP_handoff.md` and `THz_emission_dev_log.md` are historical prose and were left as they are,
  - `OPTP_System/` now contains only `OPTP_system_iTC_v2.9.py` + `OPTP_iTC_main_v2.9.ui` alongside the logs, icons and `proj_tools.py`.

### v3.0 - Stage1/Stage2 step-row spinboxes aligned
- Date: 2026-09-26
- Main change: the three spinboxes of the `Step(um)` row and the `Step NO.` row in `stage1Group` / `stage2Group` now line up vertically.
- Details:
  - cause: each row is its own grid (`gridLayout_7` / `gridLayout_8` in Stage1, `gridLayout_6` / `gridLayout_10` in Stage2), so columns are not shared between the rows. Every column was sized from its widget's sizeHint, and those differ - spinbox width follows the digit count of its range (46 px for -100..99, 53 px for 0..10000, 58 px for -10000..10000) and the two labels are 49 / 47 px - which put the rows 5-7 px out of line,
  - fix (`OPTP_iTC_main_v3.0.ui` only): added `minimumSize` width 56 to `label_24`, `label_25`, `label_29`, `label_27`, and width 58 (the widest sizeHint) to `stage1Step1-3`, `stage1Step1NO-3NO`, `stage2Step1-3`, `stage2Step1NO-3NO`. No layout was restructured,
  - verified by loading the .ui through QUiLoader at 1000x700 and 1800x1100: both rows now share identical x positions (Stage1 81 / 148 / 215, Stage2 528 / 595 / 662 at the larger size).

### v3.0 - `OPTP_system_iTC_v3.0.py` created for the v3.0 UI
- Date: 2026-09-26
- Main change: `OPTP_system_iTC_v3.0.py` is a copy of `OPTP_system_iTC_v2.9.py` whose only change is the loaded UI file (`OPTP_iTC_main_v2.9.ui` -> `OPTP_iTC_main_v3.0.ui`, line 68).
- Details:
  - all 110 `self.ui.<name>` references in the code resolve in the v3.0 UI; the names that disappeared from the UI are layouts only, none referenced by code,
  - the v3.0 UI adds a `tabWidget` (`Scan` / `Inst. Config. && Log`) and new, not yet wired widgets: `FlipMount` group (`activeFlipMount`, `FMLed`, `FM_Block`), `activePowerMeter` / `PMLed` / `PowerMeterDisp`, and `Lockin1_res`. No code drives them yet; `set_ControlsEnabledDuringScan` disables / re-enables them generically like every other input,
  - verified by a headless (`QT_QPA_PLATFORM=offscreen`) construction of `moSys`: the UI loads, all charts initialise, and both tabs are present. Not yet run against hardware.

### v3.0 - Flip mount (MFF) beam block with AutoBlock
- Date: 2026-09-26
- Main change: the Thorlabs MFF flip mount is now connectable, and with `AutoBlock` pressed it keeps the beam off temperature-sensitive samples while the temperature changes, opening only for the measurement.
- Details:
  - UI (`OPTP_iTC_main_v3.0.ui`): added the `fmPassCh` combobox (`Pass: CH1` / `Pass: CH2`) in the Flip Mount group, in place of `horizontalSpacer_2`, to choose which mount position lets the beam through (the other one blocks). Replaced the `AutoBlock` tooltip, which had been copied from `Rot_stages_couple`, with a description of what AutoBlock does,
  - connect / close: `activeFlipMount` connects `FilterFlipper` (serial `37872830`, taken from `inst_libs/test_MFF0102.py`) through `connectInstruments()` and closes through `close_one()` like the other instruments. The mount is deliberately **not homed** on connect, because homing flips it and could expose the sample. `FM_connect` shows the connection, `FM_Indicate` shows the beam state (on = blocked),
  - changing `fmPassCh` only re-reads the position to update `FM_Indicate`; it never moves the mount,
  - scan flow with AutoBlock on, per temperature point: block -> go to T -> iTC stabilisation -> sample soak -> pass -> (peak tracking) -> measurement. A failed block only warns; a failed pass aborts the scan, since measuring with the beam blocked would produce a useless data set. Without a temperature scan it just passes before measuring,
  - end of scan: `ScanThread.run()` calls `auto_block_after_scan()` on normal finish, on Stop, and on an exception, before `scan_finished` / `error_occurred` re-enable the controls,
  - `check_instruments_ready()` now includes the flip mount, and refuses to start a scan when AutoBlock is on but no mount is connected, so the sample is never left unprotected silently,
  - a move counts as done only when the read-back position equals the target; the LED is updated from the scan thread through the new `ScanThread.fm_block_led` signal,
  - hover tooltips in one format (bold title + explanation) on `FM_connect`, `AutoBlock`, `fmManual`, `fmPassCh` and `FM_Indicate`, stating what each LED state means and what each control does. (The first version of these tooltips was lost to a Designer save of an older copy at 19:00 and was re-applied together with `fmManual`.)
  - manual Block/Pass button `fmManual` (checkable, between `AutoBlock` and `fmPassCh`; grid `columnstretch` is now `1,1,3,3,4,1`) for alignment and testing outside a scan: pressed = block, released = pass, with the pass position taken from `fmPassCh`. Its text shows the current state (`Blocked` / `Pass`, or `Block / Pass` when not connected). `show_flipmount_state()` now drives both `FM_Indicate` and the button with signals blocked, so AutoBlock moves during a scan, remapping CH1/CH2 and connect/close all keep the button in step without triggering another move. Pressing it while disconnected, or a failed move, puts the button back to the real state. Like every input it is disabled during a scan,
  - the power meter group (`activePowerMeter`, `PMLed`, `PowerMeterDisp`) is intentionally left without code for now,
  - verified headless against a simulated mount (10/10 checks): scan refused with AutoBlock on and no mount, block/pass positions and LED for both CH1 and CH2 mappings, remapping does not move the mount, the scan-thread signal path, AutoBlock off leaves the mount alone after a scan, a failed move returns False without raising. The scan-loop insertion points and the real MFF are not yet exercised - tracked in `OPTP_handoff.md` P1.

### v3.1 - Instrument connection parameters moved to the Inst. Config. tab
- Date: 2026-09-26
- Main change: `OPTP_system_iTC_v3.1.py` + `OPTP_iTC_main_v3.1.ui` (copied from v3.0). Every VISA address, Kinesis serial and stage channel that was hard-coded in `connectInstruments()` is now set in an **Instrument Connections** panel on tab 2, can be picked from a device scan or typed in, and is remembered between sessions.
- Details:
  - UI: tab 2's placeholder (`label_57` "Sensitivity" + `Lockin1_res`) replaced by the `connGroup` panel: one row per instrument with an editable combobox `<name>_res` - `Lockin1_res`, `Lockin2_res`, `Stage1_res`, `Stage2_res`, `Rot1_res`, `Rot2_res`, `Rot3_res`, `FM_res`, `iTC_res`, `PM_res` - plus `Stage1_ch` / `Stage2_ch` spinboxes, and a `scanDevices` button. Defaults are the values that were hard-coded, so connecting behaves exactly as before,
  - rotary rows deliberately have no channel box: `RotaryStage(serial, ...)` is single-channel and never received the old `chan = 1/2`, which was only printed. The dead `chan` lines were removed from the three rotary blocks rather than wired to a control that would do nothing,
  - `connectInstruments()` reads each address/serial with `currentText().strip()` and the stage channels with `value()`,
  - `scan_devices()`: offers `InstrumentTools.list_visa_resources()` in the VISA boxes and the new `InstrumentTools.list_kinesis_serials()` in the Kinesis boxes; the entered values are kept, a failing scan only prints,
  - `inst_libs/inst_tools.py`: added `list_kinesis_serials()` (`DeviceManagerCLI.BuildDeviceList/GetDeviceList`). pythonnet/Kinesis are imported inside the function, so importing `inst_tools` still works on a PC without Kinesis. Purely additive for the other systems using this module,
  - persistence: `QSettings("OPTP_System", "InstrumentConnections")` (Windows registry, `HKCU\Software\OPTP_System`). Saved on every Conn. Instr., loaded at start-up; anything never saved falls back to the .ui default. Note: once saved, the stored value wins over a later change of the default in Designer,
  - `PM_res` is stored but not used yet (power meter logic still deferred),
  - fix: `check_instruments_ready()` counted a ticked flip mount as an "active instrument", so ticking only the flip mount got past the "no instrument is marked active at all" guard and ran an empty all-zero scan. The flip mount no longer counts towards `any_active` (it still must be connected when ticked). Introduced in v3.0 with the flip mount; fixed in v3.1 only,
  - end-to-end scan simulation (8/8, fake lock-in + fake mount, real `runScan()` -> `ScanThread` path, data written to a temp folder): no flip mount + AutoBlock off runs normally; AutoBlock on without a mount is refused; a ticked but unconnected mount is refused like any instrument; a connected mount with AutoBlock off is never moved; AutoBlock on moves pass -> block and the LED/button end on Blocked; a mount that fails to open aborts before any data file is created and stays blocked; flip mount alone is refused; Stop mid-measurement ends blocked. The temperature branch (block before each ramp) needs the iTC and was checked by reading only,
  - verified headless (9/9): .ui defaults on a clean start, edited values reach `SR830` / `LinearStage` (serial + channel) / `RotaryStage` / `FilterFlipper` / `MercuryiTC` (captured with stand-in classes), scan fills both lists without overwriting typed values, a failing scan is caught, and a new window restores the saved values. Tests used a temporary ini file, the real registry was not touched. Not yet run on the lab PC.

### v3.1 - Flip mount beam-state LED inverted (lit = pass)
- Date: 2026-09-26
- Main change: `FM_Indicate` now lights when the beam passes to the sample and is off when it is blocked, the reverse of v3.0.
- Details:
  - requested after the first real MFF connection: the lab expects the LED to mean "beam on sample",
  - the only place that writes the LED is `show_flipmount_state()`; it now sets `status = blocked is False`, so blocked (`True`) and unknown / not connected (`None`) are both off, and only a confirmed pass is lit. The scan-thread `fm_block_led` signal still carries "blocked" and was left unchanged,
  - the `fmManual` button (pressed = block, text `Blocked` / `Pass`) is unchanged,
  - `FM_Indicate` tooltip in `OPTP_iTC_main_v3.1.ui` and the init comment in the .py were updated to the new meaning,
  - verified: `py_compile` passes; mapping True -> off, False -> on, None -> off; the .ui is still CRLF throughout. Not yet checked on the real mount.

### v3.1 - ScanLog: live scan-condition log, appended to a per-day file
- Date: 2026-09-26
- Main change: a `ScanLog` group box to the right of Instrument Connections on tab 2 shows each scan's test conditions and key events as they happen, and every line is appended at once to `ScanLog_YYYY-MM-DD.txt` in the data save folder.
- Details:
  - UI (`OPTP_iTC_main_v3.1.ui`): the `connHSpacer` at `tab2Layout` (0,1) was replaced by `QGroupBox ScanLog` (rowspan 2, so it fills the tab's stretching column) holding a read-only `QPlainTextEdit scanLogText` (Consolas 9) with a tooltip. `set_ControlsEnabledDuringScan` does not touch `QPlainTextEdit`, so the box stays scrollable during a scan,
  - log file: `<dataSave_path>/ScanLog_<date of scan start>.txt`, i.e. the day folder, or the custom folder when one was chosen. The path is fixed at scan start, so a scan running past midnight stays in one block. The file is opened in append mode per write, so everything written is on disk even if the program dies,
  - each scan is one block, separated by a blank line and a `=` rule. Header (`start_scan_log()`, GUI thread, called in `runScan()` after the instrument check): start time, mode, extra info, save folder, then only instruments that are ticked and connected - Lock-in sens / TC / wait, Stage start / non-zero step groups / repeat, Rotary start / step, rotation Coupled / Independent (with the same "calibration forces coupled" rule as the scan) and R1 / R2 repeats, temperature list with tolerance and sample soak (or "no temperature scan"), AutoBlock with its pass channel,
  - timestamped events (`scan_log_event()`, routed from the scan thread through the new `ScanThread.scan_log` signal so that only the GUI thread writes the box and the file): T point reached, T point measured without stabilization, data file name of every temperature point, peak tracking off (1D_THz), one peak-tracking summary per data file, and the end line with duration,
  - peak tracking in 1D_THz runs before every stage2 sweep, so logging each result would add hundreds of lines per scan; the per-sweep values are already in the HDF5 `dynamic_THz_peak_pos`. The log gets one line per data file instead: `N sweeps, peak min .. max mm, K found no peak` - enough to see drift and failures,
  - end line: `Scan finished`, `Scan stopped by user`, `Scan aborted: <reason>` (temperature stabilization failed other than by Stop, or AutoBlock could not pass the beam), or `Scan error: <message>`. The early error returns inside `_execute_scan_logic()` emit `error_occurred` and then `run()` still emits `scan_finished`; `end_scan_log()` only honours the first call, so an error is never followed by a false "finished",
  - deliberately not logged: point readings, moves, countdowns, peak-search progress and other prints,
  - verified by a headless end-to-end run (17/17) through the real `runScan()` -> `ScanThread` with fake lock-in / stages / iTC / flip mount: dated file created; header lists only active instruments; box and file identical; no point readings; two scans form two separated blocks; 1D_THz with a rotary gives exactly one peak summary line; Stop -> "stopped by user"; both-stage-repeats error -> one "Scan error" line and no "finished"; 2-point temperature scan with AutoBlock -> both T points, both data files, finished; failing temperature read -> "aborted: temperature stabilization failed at 10 K". Not yet run on the lab PC.
  - the check is kept as a regression test: `OPTP_System/tests/test_scanlog.py` (headless, no hardware, writes to a temp folder; run `python OPTP_System/tests/test_scanlog.py`, exit code 0 = all pass). It execs the v3.1 source, so it must be pointed at the new file when the version is bumped,
  - confirmed with the user: one log file per day (`ScanLog_<date>.txt` in that day's data folder, appended by every scan of the day), and one peak-tracking summary line per data file instead of one line per sweep.

### v3.1 - v2.9 and v3.0 archived into `old_version/`
- Date: 2026-09-26
- Main change: moved `OPTP_system_iTC_v2.9.py` / `OPTP_iTC_main_v2.9.ui` and `OPTP_system_iTC_v3.0.py` / `OPTP_iTC_main_v3.0.ui` into `OPTP_System/old_version/`, so only the current v3.1 pair sits at the top level.
- Details:
  - v2.9 was tracked and moved with `git mv` (history preserved); v3.0 had never been committed and was moved with a plain `mv`,
  - each archived `.py` still finds its `.ui` through `os.path.dirname(os.path.abspath(__file__))`. As with the earlier archived versions, `proj_tools.py` stays at the top level, so an archived version cannot be run directly from `old_version/` without it,
  - no code outside `old_version/` referenced the moved files; `tests/test_scanlog.py` targets v3.1 only.

### v3.1 - v3.0/v3.1 features synced into MO, OPTP image and THz emission
- Date: 2026-09-26
- Main change: MO v2.4, OPTP image v1.4 and THz emission v1.3 were created with this system's v3.0/v3.1 layout, flip mount / AutoBlock, Inst. Config. panel and ScanLog, so the four systems share widget names again. Details in each system's dev log.
- Details:
  - each new .ui is built from `OPTP_iTC_main_v3.1.ui` with the system's own values (title, stage ranges, defaults, connection addresses) re-applied; each .py is this system's v3.0/v3.1 change set merged in, with every system's instruments, addresses, scan modes and stage order kept,
  - each system saves its connection settings under its own QSettings name (`MO_System`, `OPTP_image_System`, `THz_emission_system`),
  - regression test for all three: `OPTP_System/tests/test_system_sync.py <mo|img|thz>` (headless, stand-in instruments, temp ini file instead of the registry). Run it with the `opto_test` conda env, the environment the systems run in: MO 28/28, OPTP image 26/26, THz 26/26 (real pipython), and `tests/test_scanlog.py` 17/17.

### v3.2
- Date: 2026-09-28
- Main change: `OPTP_system_iTC_v3.2.py` + `OPTP_iTC_main_v3.2.ui` created as copies of v3.1 for further development; the .py now loads the v3.2 .ui.
- Details:
  - the .ui is a byte-for-byte copy of `OPTP_iTC_main_v3.1.ui` (CRLF); the .py differs from v3.1 only in the .ui file name on line 70 (the v3.1 .py is LF throughout, and the copy keeps that),
  - verified: `py_compile` passes in the `opto_test` env, and a headless start loads the v3.2 .ui with both tabs, ScanLog and the FlipMount group present,
  - `tests/test_scanlog.py` still targets v3.1; point it at v3.2 once v3.2 starts to diverge.

### v3.2 - Sub-tab widget under Instrument Connections
- Date: 2026-09-28
- Main change: `OPTP_iTC_main_v3.2.ui`, tab `Inst. Config. && Log`: a `QTabWidget configTabs` now sits under the `connGroup` panel, with pages `peakSearchTab` (title `Peak search`) and `configTab2` (title `Tab 2`, placeholder). Both pages are empty for now.
- Details:
  - it replaces `connVSpacer` at `tab2Layout` (1,0), so it takes the column width of the connection panel and the remaining height down to the bottom of `ScanLog`; `connGroup` and `ScanLog` are unchanged,
  - no code references the new widgets yet; the .py is unchanged,
  - verified: the .ui stays CRLF; a headless start of v3.2 loads it, `configTabs` has the two pages in order, and the rendered tab shows it directly under the connection panel at the same width (462 px).

### v3.2 - Temperature drift compensation (stage1 / stage2 coupling), Peak search tab
- Date: 2026-09-28
- Main change: in every temperature scan, of every scan mode, the stage1 THz peak is searched at each temperature point and the drift is applied to both delay lines: `iPos1 += delta`, `iPos2 += s * delta` (delta = new peak - `TDS Ppos`, s = -1 for Reverse). The pump-THz delay therefore stays the same across temperatures. Replaces the old 1D_THz-only, per-sweep peak tracking, which corrected stage1 but left stage2 (and so the pump-THz delay) behind, and did nothing in 2D_THz.
- Why: stage1 and stage2 are coupled - moving stage1 by delta to re-peak the THz changes the pump-THz delay, which stage2 (mounted in reverse) has to undo. The drift itself (sample holder / sample thermal expansion) moves the collinear THz and pump paths together and does not change that delay; the probe path is stable (both confirmed experimentally by the user). With a ~42 um response FWHM, a few um of uncompensated drift already changes the 1D response by >10 %.
- Details:
  - UI (`OPTP_iTC_main_v3.2.ui`, tab `Inst. Config. && Log` -> `configTabs` -> `Peak search`): `driftComp` (checkbox, default on), `TDS_Ppos` (editable, -1 = special value `Not set`, not kept after restart), `R1_step` / `R1_pts` (default 3 um / +/-30), `R2_step` / `R2_pts` (default 1 um / +/-30), `stage2CompDir` (checkable, Reverse (default) / Forward), `passOrder` (checkable, `Pass -> Soak` (default) / `Soak -> Pass`). Tooltips on every control and label,
  - trigger: `temperature_scan_active()` (iTC ticked and connected, ScanT ticked, points in the list; now also used by the ScanLog header and `_execute_scan_logic`) and `driftComp` ticked. Non-temperature scans are never compensated,
  - start of a compensated scan (`confirm_drift_compensation()` in `runScan()`): refused when `TDS Ppos` is `Not set` or Stage1 / Lock-in 1 is not active and connected; otherwise a Yes/No dialog shows TDS Ppos, iPos1, iPos2, direction, both rounds and the beam order, and notes when stage1 is a single fixed point and iPos1 differs from TDS Ppos by more than one Round-2 step,
  - per temperature point: block -> go to T -> stabilise -> [pass, if `Pass -> Soak`] -> soak -> [pass, if not yet] -> all active stages to the scan start (iPos1, iPos2, iRot1-3) -> peak search around TDS Ppos -> compensate -> sequences and data file from the new values -> existing travel check -> scan. A local `beam_passed` flag passes the beam exactly once per point on every path (incl. no stabilisation / no soak),
  - `get_TDS_peak_pos(thread, center_pos)`: centre = TDS Ppos, steps and points from the tab, symmetric windows centre +/- N steps (was -30..+29), single lock-in read per point as before. A round-1 maximum on the window edge now counts as failed (`reason` in the result), as does a window without any finite reading,
  - `compensate_temperature_drift()` returns the new values and the scan uses them directly; the UI (`iPos1`, `iPos2`, `TDS_Ppos`) is only updated through signals (`tds_peak_update`, new `ipos2_update`, new `ppos_update`), because an asynchronous write-back could still be pending when the file is built. `_execute_scan_logic` keeps `scan_iPos1` / `scan_iPos2` / `scan_Ppos` across temperature points instead of reading the UI,
  - failed search: iPos1 / iPos2 / Ppos kept, measurement continues, `WARNING: peak search failed (...)` in ScanLog (user's choice). Stop during the search ends the scan before the data file is created,
  - data: the stored `iPos1` / `iPos2` are the compensated values, so no offset dataset is needed. Removed: `dynamic_THz_peak_pos`, the per-polarization / per-sweep 1D peak tracking inside the scan loop, `peak_tracking_enabled` and the per-file peak summary,
  - ScanLog: header `Drift comp. : on, TDS Ppos ..., R1 ..., R2 ..., stage2 Reverse` (or `off`), `AutoBlock : on (...), Pass -> Soak`; one `Peak search: Ppos a -> b mm (delta +x um); iPos1 -> ..., iPos2 -> ... (Reverse)` line per temperature point,
  - verified headless with `tests/test_drift_comp.py` (25/25, `opto_test` env; fake lock-in = Gaussian stage1 peak drifting -0.4 um/K with the fake iTC temperature): defaults and toggle captions; refusal without Ppos and without Stage1; dialog No stops, Yes runs; mismatch note; 1D_THz over 10/20/30 K: per-file iPos1 = drifted peak, iPos2 moved opposite (+4 um per 10 K), every measured point on the peak, UI ends on the compensated values, one ScanLog line per point, exactly 61 + 61 search reads per point with stage2 at iPos2; Forward sign; 2D_THz, THz_Scan and POL_1D shift iPos1 (window start / fixed point) and iPos2 by the same rule; `Pass -> Soak` gives block, pass, soak, search and `Soak -> Pass` block, soak, pass, search, one pass per point, blocked at the end; NaN readings and a peak outside the window keep the values, continue and log a WARNING; Drift comp. off and non-temperature scans run no search and show no dialog; Stop during the search ends the scan without a data file and with the beam blocked,
  - regression: the v3.1 ScanLog test run against v3.2 (with Drift comp. off) passes 16/17 - the one failure is the per-file peak summary, removed on purpose,
  - `tests/test_scanlog.py` still targets v3.1 (with Drift comp. on by default a v3.2 temperature scan needs TDS Ppos). Not yet run on the lab PC.

### v3.2 - scanMode tooltip matches the modes in the code
- Date: 2026-09-28
- Main change: the `scanMode` tooltip in `OPTP_iTC_main_v3.2.ui` was rewritten to match `_init_scanMode_combobox()`.
- Details:
  - the old tooltip listed a mode that does not exist (`1D_POL`), used the old names `TDS_Scan` / `1D_TDS` / `2D_TDS` instead of `THz_Scan` / `1D_THz` / `2D_THz`, was in a different order from the combobox, and said "stage1 beam act as pump" (in OPTP the pump delay is stage2),
  - new text, in combobox order, with the loop order actually used by the code (outermost -> innermost): `THz_Scan` rotation stages -> stage1 -> stage2; `1D_THz` rotation stages -> stage1 -> stage2 (stage1 fixed at the peak); `POL_1D` stage1 -> stage2 -> rotation stages (planner `POL_2D` branch); `2D_THz` rotation stages -> stage2 -> stage1 (local override); plus one line that every mode is drift-compensated in temperature scans with Drift comp. on,
  - only the tooltip string changed; the .ui stays CRLF and loads through QUiLoader,
  - found but NOT changed in this entry: the polar chart is only fed when `scan_mode == "POL_2D"` (line ~2505), but this system's mode is called `POL_1D`, so the polar chart never updates during a POL_1D scan - fixed in the next entry.

### v3.2 - Polar chart fed during POL_1D scans
- Date: 2026-09-28
- Main change: the polar chart condition in `_execute_scan_logic()` now tests `iterator_mode == "POL_2D"` instead of `scan_mode == "POL_2D"`, so the polar chart is updated during a POL_1D scan again.
- Details:
  - `scan_mode` is the combobox text. This system calls the mode `POL_1D` and only maps it to `iterator_mode = 'POL_2D'` for the shared planner, so `scan_mode == "POL_2D"` was never true and the polar chart never received data. The condition came from MO, whose combobox mode really is called `POL_2D`; it had been like this since OPTP v1.0 and no log records it as intended,
  - `iterator_mode` describes the scan itself (polarization innermost) rather than the combobox name, so the same line is correct in OPTP (`POL_1D` -> `POL_2D`) and in MO (`POL_2D`), which keeps the systems' code in sync,
  - verified headless (v3.2, `opto_test`): a POL_1D scan with Rotary2 0..350 deg in 36 steps sends 36 polar updates with the right angles; THz_Scan, 1D_THz and 2D_THz send none; `tests/test_drift_comp.py` still 25/25.

### v3.2 - Scan mode POL_1D renamed to POL_2D (same name as MO and the shared planner)
- Date: 2026-09-28
- Main change: the polarization-dependent scan mode is now called `POL_2D` in OPTP v3.2 as well, so the combobox, the code and the shared planner use one name. Replaces the previous entry's `iterator_mode` fix.
- Details:
  - why: the same loop logic had two names - `POL_1D` in the combobox, file names and ScanLog, `POL_2D` inside the shared planner (`ScanPlanner.build_scan_iterator`, whose only mode test is `if scan_mode == "POL_2D"`: polarization innermost, every other name puts it outermost) - and the code compared against both. MO already calls this mode `POL_2D`. THz emission (`THz_pol`) and OPTP image (`POL_1D`) keep their own names for now,
  - `_init_scanMode_combobox()`: list is `['THz_Scan', '1D_THz', 'POL_2D', '2D_THz']`; the docstring now states each mode's loop order (it still described the pump as "stage2 beam" loosely and had no loop orders),
  - the `iterator_mode` variable and the `POL_1D -> POL_2D` mapping are gone: `build_scan_iterator(scan_mode=scan_mode, ...)`; the polar chart (`scan_mode == "POL_2D"`) and the TDS branch (`elif scan_mode == "POL_2D"`) use the same name,
  - `scanMode` tooltip in `OPTP_iTC_main_v3.2.ui`: `'POL_2D'` (noted as the MO name); `tests/test_drift_comp.py` uses `POL_2D`,
  - effect on data: polarization scans now produce `..._POL_2D.h5` / `..._POL_2D_<T>K.h5` and `Mode : POL_2D` in ScanLog; earlier files keep `POL_1D` in their names,
  - verified (`opto_test`, headless): POL_2D with stage2 at 2 points and Rotary2 0..350 deg / 36 steps sends 72 polar updates in the order 0..350, 0..350 (polarization innermost); THz_Scan / 1D_THz / 2D_THz send none; `tests/test_drift_comp.py` 25/25; the .py stays LF, the .ui CRLF,
  - found, NOT changed: a TDS trace of exactly two points makes `DataProcess.thz_fft_calc()` (shared `func_cores/scan_func_core.py`) raise `IndexError` at `time_step_uniform[1]` - the uniform time grid has one point - inside `update_TDS_FDS_chart()`, whose guard only rejects fewer than two points. The slot exception is printed and the scan continues; only that FDS update is lost.

### v3.3 - Power meter box: live pump power, wavelength, Zero, and Record into the data files
- Date: 2026-09-29
- Main change: `OPTP_system_iTC_v3.3.py` + `OPTP_iTC_main_v3.3.ui` (copied from v3.2) use the Thorlabs PM100D. The pump reaches the meter while the flip mount is on Block, so outside a scan the box monitors the pump power, and with Record + AutoBlock the pump power is measured at every temperature point right before the beam is let through and saved in that point's data file.
- Details:
  - UI (Power Meter box, between the LED and the display, all with tooltips): `pmWavelength` (nm), `pmRefresh` (ms, display interval and spacing of the Record readings, default 500), `pmSettle` (s, default 15), `pmAvgNO` (N readings, default 10), `pmZero`, `pmRecord` (checkable, like AutoBlock). `PowerMeterDisp` shows plain decimal mW (`-0.206 mW`, was `0.000e0.0`), read-only, max width 110 px; `PMLed` got a tooltip. All of them are locked during a scan by `set_ControlsEnabledDuringScan()` like every other input,
  - connect / close: `activePowerMeter` + `PM_res` (Inst. Config.) -> `PM100D(resource, timeout_ms=3000)`; the wavelength box is read from the meter on connect (the meter holds the setting), the display timer starts; `closeInstruments()` closes it through `close_one()` and resets the display,
  - live display: `QTimer` in the GUI thread -> `measure_power()`; `pm_lock` is shared with Record, and the timer skips a tick instead of waiting while Record holds it. A read error stops the timer (a dead session would otherwise block the GUI for a full timeout on every tick),
  - Zero: confirmation dialog (the sensor must be dark: flip mount on Pass, ~20 s to cool), `zero_initiate()`, then polls `get_zero_state()` (max 30 s) without holding the lock; the display timer is paused meanwhile,
  - Record (`record_pump_power()`, scan thread), only when Record and AutoBlock are both on: called right before AutoBlock's pass - before the early pass for 'Pass -> Soak', otherwise before the pass that precedes drift compensation and the measurement - so once per temperature point, or once before a scan without temperature points. If the beam is not blocked it is blocked first. Settle time counts from the last confirmed block move (`_fm_blocked_since`, set in `set_flipmount_blocked()`); in a temperature scan the beam has been blocked through the stabilization, so normally nothing extra is waited. If the block time is unknown (blocked before the program moved it) the full settle time is waited. Then N readings one refresh interval apart; a stop request is honoured during all waits,
  - storage: after the point's HDF5 file is created, `save_pump_power()` writes `pump_power_W` (mean), `pump_power_std_W`, `pump_power_samples_W`, `pump_power_wavelength_nm`, `pump_power_settle_s`, `pump_power_interval_ms`, `pump_power_time` (datasets, like the other scan parameters). ScanLog: header line `Pump power  : Record on (settle 15 s, N 10 x 500 ms, 800 nm)` (or that Record is on without AutoBlock, so nothing is recorded) and one `Pump power x.xxx mW +- y.yyy mW (N=.., .. nm)` line per point, before its `Data file:` line,
  - a failed reading does not stop the scan: that point's file has no pump power datasets and the ScanLog says `Pump power NOT recorded: ...`,
  - pre-scan check: the meter is in `check_instruments_ready()` (ticked but not connected refuses the scan) and, like the flip mount, does not count as a measuring instrument; Record + AutoBlock without a connected meter refuses the scan with `Power meter (Record is on)`,
  - uses `inst_libs/thorlabs_PM100D.py` on pyvisa (see `Polarization_cali_dev_log.md` v1.1.4; the TLPM version is kept in `inst_libs/backup_before_pm100d_pyvisa/`),
  - verified (`opto_test`): new `tests/test_pump_power.py` 48/48 headless (both beam orders over 2 temperature points, single scan starting on Pass, Record without AutoBlock, AutoBlock without Record = unchanged block/pass sequence, read failure, stop during the settle wait - no pass, no file -, settle timing, pre-scan check, display, wavelength, Zero, close); `tests/test_drift_comp.py` 25/25 against v3.3. Real PM100D P0020951 through the v3.3 code with a fake flip mount: connect 0.10 s, wavelength read on connect and set/restored, display updates, Record in a worker thread while the display timer kept reading (no conflict), datasets read back; meter left as found. Zero was not run on the meter (needs the sensor dark). Not yet run in a real scan with the real flip mount,
  - `tests/test_scanlog.py` (still pinned to v3.1, see the v3.2 entry) run against v3.3: its temperature part stops at the modal 'Drift comp.' confirmation (`confirm_drift_compensation()`, on by default since v3.2, needs a TDS Ppos), which never closes headless, and its check 'one peak-tracking summary line' fails because the v3.2 peak-tracking log lines differ; all its other checks up to there pass. Not changed here. `test_pump_power.py` unticks 'Drift comp.' so it cannot stop at that dialog.

### v3.3 - PM config tab: wavelength, power range, refresh
- Date: 2026-09-29
- Main change: wavelength and refresh interval moved out of the Power Meter box into Inst. Config. > `PM config` (the former empty `Tab 2`, `configTab2`), and a Power range combobox was added there. The box keeps settle, N, Zero, Record and the display.
- Details:
  - which settings are fixed steps (checked on the meter): the power range is - 4 decades set by the sensor (S302C: 3.446 mW, 34.46 mW, 344.6 mW, 3.446 W; any other value is moved up to the next range) - so it is a combobox `pmRange` (Auto + the ranges). The wavelength is continuous (S302C 185 .. 20000 nm) and the refresh interval is the program's own timer, so both stay spin boxes,
  - layout like the Peak search tab: labels `Wavelength (nm)`, `Power range`, `Refresh (ms)` (with the controls' tooltips) and the controls in grid `pmGrid`; the units moved from the spin-box suffixes into the labels,
  - `load_pm_settings()` on connect: wavelength box limited to the sensor (`SENS:CORR:WAV? MIN/MAX`) and set to the meter's value; the range list is built from `SENS:POW:RANG:UPP? MIN/MAX` in decades, and the box shows the meter's state (Auto, or the nearest range) with signals blocked, so connecting never changes the meter,
  - `set_pm_range()`: Auto -> `set_power_auto_range(True)`; a range -> auto off + `set_power_range_upper()`, read back and printed,
  - verified (`opto_test`): `tests/test_pump_power.py` 54/54 (6 new PM config checks: range list, wavelength limits, fixed range and Auto written to the meter, a meter already on a fixed range shown without writing back). Real PM100D P0020951 through the GUI code: list `Auto, 3.446 mW, 34.46 mW, 344.6 mW, 3.446 W`, wavelength box 185 .. 20000 nm, 34.46 mW -> meter auto off at 0.03445766 W, Auto -> meter back on auto; no SCPI errors; meter left on auto.

### v3.3 - Wavelength: default 800 nm, sent to the meter on connect; tooltip
- Date: 2026-09-29
- Main change: the PM config wavelength stays a plain number box (not a combobox), defaults to 800 nm, and is now sent to the meter when it connects instead of being overwritten by the meter's own value.
- Details:
  - why no combobox: checked on the meter, the wavelength is not a fixed set of values - 532, 633.3, 777, 1064, 1550, 2345.6 and 10600 nm were all accepted and read back exactly; 150 and 25000 nm were refused (`-222 Data out of range`) and the old value kept. Preset lists on the front panel or in the Thorlabs software are only shortcuts there,
  - `load_pm_settings()`: box limited to the sensor (185 .. 20000 nm for the S302C, the box value is clamped into it), then `set_wavelength_nm(box)` and the accepted value shown back. Before, connecting copied the meter's value (e.g. 525 nm) into the box, so the 800 nm default never reached the meter. Editing the box still sends it at once, as before,
  - tooltip of the box and its label rewritten: what the wavelength does (correction with the sensor's calibration data, not what is detected), when it is sent, the S302C range and flat response vs. a photodiode sensor, whole nanometres only, front-panel presets are only shortcuts,
  - verified: `tests/test_pump_power.py` 55/55 (default 800 nm; a meter left on 525 nm gets 800 nm on connect). Real PM100D: meter on 525 nm -> connect through the GUI code -> meter 800.0 nm, no error; set back to 525 nm afterwards.

### v3.3 - Power Meter box: plain settle / N boxes, row aligned with the rest
- Date: 2026-09-29
- Main change: `pmSettle` and `pmAvgNO` are plain number boxes (the ` s` suffix and `N ` prefix are gone; the units are in the tooltips), at most 50 px wide, and the Flip Mount / Power Meter row is split 1:1 like the rows above and below.
- Details:
  - the suffix / prefix were display text only (typing just the number always worked), but they were redundant next to the tooltips,
  - `gridLayout_16` columnstretch `0,0,0,0,1,1,1`: the two number boxes keep their size, Zero, Record and the display share the rest,
  - `gridLayout_4` got `columnstretch="1,1"`; without it the two group boxes were sized by their content (Flip Mount 22..394, Power Meter 400..815 px). Now 22..416 and 422..815, the same as Lock-in, Stage and Rotary,
  - verified: rendered offscreen (positions above), `tests/test_pump_power.py` 55/55.

### v3.3 - PM_realDisp: live power display on/off
- Date: 2026-09-29
- Main change: new checkable button `PM_realDisp` ("Realtime", like the lock-in and temperature Realtime buttons, released by default) between Record and the power display. The power is read and shown only while it is pressed and the meter is connected; before, the display ran whenever the meter was connected.
- Details:
  - `sync_pm_display_timer()` is the one place that starts/stops the display timer (pressed and connected -> run, else stop); called on toggle, after connect and after Zero. Pressing it before connecting is allowed, the display then starts on connect. Releasing it stops the reading and shows `-- mW`, so a frozen number cannot pass for a live one,
  - a read error stops the display and releases the button (pressing it again retries; before, only a reconnect helped),
  - stays enabled during a scan like `realtimeDispT` (added to `always_enabled` in `set_ControlsEnabledDuringScan()`); Record and the display share `pm_lock`, so they never read at the same time,
  - layout: Qt gives a push button with text a ~80 px size hint regardless of the text, so three buttons squeezed the display to ~20 px and widened the whole left panel (815 -> 861 px). Zero / Record / Realtime now have fixed widths 44 / 56 / 62 px, the display a minimum of 80 px (max 110), and `gridLayout_16` horizontal spacing 4: the panel is back to 815 px, Flip Mount / Power Meter still split 22..416 / 422..815 like the other rows, and `-0.206 mW` and `1234.567 mW` fit (rendered offscreen). The display tooltip now says it updates only while Realtime is pressed,
  - verified: `tests/test_pump_power.py` 64/64 (9 new/changed checks: default released, connect with it released / pressed, press / release, pressed before connecting, read error releases it, stays enabled during a scan while Zero / Record / settle are locked, close stops it). Real PM100D through the GUI code: released -> no reads and `-- mW`, pressed -> readings, released -> `-- mW`; meter wavelength set back to 525 nm afterwards.

### v3.3 - Power Meter box: settle / N boxes 28 px, Realtime 74 px (checked with the real Windows rendering)
- Date: 2026-09-29
- Main change: `pmSettle` and `pmAvgNO` fixed at 28 px (min = max), about 3/5 of their earlier width; `PM_realDisp` widened from 62 to 74 px because its text was cut off; the power display is unchanged (80 .. 110 px).
- Details:
  - correction: an intermediate step set the two boxes to 22 px, based on offscreen renders (`QT_QPA_PLATFORM=offscreen`). Those use other fonts than the real UI (Segoe UI), so the widths and text fits read from them were wrong: in the real UI the boxes had been 43 / 49 px (not 37), 22 px cut off even "15" / "10", and "Realtime" (50 px of text) did not fit a 62 px button. All numbers below are from the Windows platform plugin with `WA_DontShowOnScreen` (real fonts, nothing shown on screen),
  - at 1920 x 1040 (this PC's screen, maximised): 2-digit values fit the 28 px boxes, 3-digit values (e.g. settle 120 s) are cut off in the box but still accepted; "Realtime" fits pressed and released; the display is 110 px and shows `1234.567 mW` in full. At 1661 px the display is 84 px and cuts the first digit of a reading above 1 W,
  - Flip Mount / Power Meter stay aligned with the Lock-in / Stage rows at both window sizes (1920: 22..479 / 485..942; 1661: 22..436 / 442..855); at 1920 the left panel width is unchanged,
  - `tests/test_pump_power.py` 64/64.

### v3.3 - Power range: the meter's real ranges (fix); power meter test for all systems
- Date: 2026-09-29
- Main change: the Power range list is read from the meter itself, range by range, when it connects and after every wavelength change, and a fixed range is requested 0.1 % below its upper value. Found while porting the power meter to MO v2.5 / OPTP image v1.6 / THz v1.4, which carry the same code.
- Details:
  - bug: the list was built as decades of `SENS:POW:RANG:UPP? MIN`. The ranges are not decades and move with the wavelength: at 800 nm the list read 3.695 / 36.95 / 369.5 mW, the meter's ranges are 3.695 mW, 34.99 mW, 347.9 mW, 3.477 W, so choosing "36.95 mW" put the meter on 347.9 mW. Measured: 800 nm 3.695 mW, 34.99 mW, 347.9 mW, 3.477 W; 1030 nm 3.752 mW, 35.53 mW, 353.3 mW, 3.531 W. The 525 nm ranges also differed from the 3.446 mW .. 3.446 W logged earlier today; by then the meter's reading had gone from -0.21 to about -0.005 mW, so it had apparently been zeroed,
  - `probe_pm_ranges()`: auto range off, `SENS:POW:RANG:UPP MIN`, then 1 % above the current range until the meter stops moving up (the step above the top range leaves error -222, which is cleared); the meter's own setting, auto or its fixed range, is restored. `show_pm_ranges()` fills the box and is called by `load_pm_settings()` and `set_pm_wavelength()`. If the walk fails, the box offers only Auto and the meter still connects,
  - `set_pm_range()` and the restore ask for 0.1 % below the range's upper value: the meter reports a range rounded to 7 digits, which can lie a hair above the range and then selects the next one up (seen on the meter: restoring a read-back range after a wavelength change landed on 353.3 mW instead of 35.53 mW),
  - `pmRange` tooltip (and its label): the ranges are read from the meter and shift with the wavelength, S302C example at 800 nm,
  - `tests/test_pump_power.py` now takes a system argument (`optp` default, `mo`, `img`, `thz`), keeps QSettings in a temp ini file (an earlier run had created empty `HKCU\Software\MO_System` / `OPTP_image_System` keys; both removed), and its FakePM has non-decade, wavelength-dependent ranges with rounded read-back like the meter: 65/65. `tests/test_drift_comp.py` 25/25 on v3.2 and on v3.3. Real meter through the v3.3 code: list at 800 nm = the walked ranges, 34.99 mW -> meter on 0.03498537 W, 1030 nm -> list read again and the meter stays on the same range (0.03552721 W), Auto -> auto; meter left on 525 nm / auto.

### v3.5 - Extra beam-heating settle wait before peak search
- Date: 2026-10-03
- Main change: copied `OPTP_system_iTC_v3.4.py` and `OPTP_iTC_main_v3.4.ui` to v3.5. The new Python entry point loads the v3.5 UI. Each AutoBlock temperature point now waits an additional configurable time with the beam passing after temperature stabilization and the existing sample soak, before peak search or measurement.
- Details:
  - UI: added `Beam settle (min)` / `beamSettle` directly below `Beam / soak` in Inst. Config. > Peak search. Integer minutes, default 5, range 0..1440; 0 skips the extra wait. The label and input have matching tooltips, and the beam-order tooltips describe the extra wait. The input is locked during a scan by the existing control-locking code.
  - `Pass -> Soak`: block -> temperature stabilization -> optional pump-power Record -> pass -> existing sample soak -> full extra beam settle -> peak search (if enabled) -> measurement.
  - `Soak -> Pass`: block -> temperature stabilization -> existing sample soak -> optional pump-power Record -> pass -> full extra beam settle -> peak search (if enabled) -> measurement.
  - The full configured time is added after both soak and confirmed pass; time already spent illuminated during the sample soak is not subtracted. With the defaults, this adds 5 minutes per temperature point. This is a timed hold, not a new temperature-stability measurement.
  - `wait_beam_stable()` prints a countdown every 5 seconds and uses the existing interruptible sleep, checking Stop at most every 0.5 seconds. Stop exits before peak search or data-file creation; the existing scan-thread cleanup blocks the beam. The extra wait also applies with Drift comp. off, before measurement. AutoBlock off and scans without temperature points add no beam settle wait; failed stabilization or a failed pass does not enter it.
  - ScanLog records the configured extra minutes, the start/completion of each wait, and interruption by Stop. The existing drift-compensation confirmation includes the extra wait setting. The v3.4 files are unchanged.
  - UI defaults (2026-10-03): `activeLockin1`, `activeLockin2`, `activeStage1` and `activeStage2` now start checked in v3.5. Connection settings restore only instrument addresses/channels, so they do not override these checkbox defaults.
- Verification: Python compilation and UI XML/widget-reference checks passed. `python OPTP_System/tests/test_drift_comp.py` now targets v3.5 by default (an optional version argument retains older-version checks): 38/38 passed with fake instruments and accelerated beam waits, covering both orders at every temperature point, the full additional 300 seconds, a custom 2-minute value, zero, control locking, ScanLog, Drift comp. off, AutoBlock off, no temperature scan, and Stop during either order before any search/data with the beam blocked. Native Windows UI rendered hidden at 1920 x 1040: the new row is directly below Beam / soak, default 5 is visible, and label/input text fits. No real-instrument scan was run.

### v3.5 - Abort failed acquisition, close scan files, and honor Lock-in controls
- Date: 2026-10-03
- Main change: driver move/readback errors, temperature-sequence startup failures and Lock-in read exceptions now stop the scan and pass through common cleanup. Lock-in Realtime is switched off before every scan; active checkboxes now control acquisition, and Lock-in 2 waits its full configured delay when used alone.
- Details:
  - Movement: `move_active_stages()` propagates a contextual exception instead of returning an ignored failure. This covers initial positioning, repeat resets and positioning before peak search, as well as regular scan points. A move exception during peak search also aborts. No target/readback equality check or position tolerance was introduced; small readback differences remain accepted.
  - Temperature: if an enabled temperature-sequence scan cannot start stabilization (including missing sensor UID), it aborts before pass, soak, peak search or data-file creation. The existing failure-after-start check remains. With ScanT off, a normal scan still runs during a manual Goto T; it does not wait for temperature stability.
  - Lock-ins: X/Y read exceptions abort before the point is written, including Lock-in 1 X read exceptions during peak search. Formal acquisition checks `activeLockin1` / `activeLockin2`; a connected but unchecked device is not read. Lock-in 2 gets its full `wait2` when Lock-in 1 is inactive, including when Lock-in 1 remains connected. Inactive channels retain their existing zero placeholders at completed points.
  - Realtime: both Lock-in Realtime buttons are released and both display timers stopped on scan entry. The buttons are disabled during acquisition by the existing UI locking, then re-enabled in the off state; they are not automatically switched back on. Scan-driven charts continue to update.
  - Cleanup: `ScanThread.run()` always attempts end-of-scan AutoBlock and HDF5 close before emitting one terminal signal. Unexpected exceptions and plan validation failures follow this path; cleanup errors are included in the final error without hiding the original failure. Successfully acquired points are retained.
  - Unacquired data: v3.5 requests NaN fill values for its four Lock-in datasets, so aborted/stopped points cannot look like measured zeros. `ScanStorageCore.create_lockin_datasets()` gained an optional keyword-only `fillvalue`, defaulting to 0.0 for existing callers and other versions; dataset names, dimensions and numeric types are unchanged.
  - Explicitly deferred: old stabilization-thread replacement logic is unchanged. The stabilization observer exits after the required consecutive readings satisfy tolerance, before sample soak; hardware temperature regulation continues independently. The separate risk is replacing an observer that has not exited after the existing 2-second stop wait. A later fix should safely stop/join that observer without requiring a manual temperature ramp to finish. AutoBlock block failure still warns and continues, as requested; a failed pass still aborts.
- Verification: `tests/test_scan_failures.py` 20/20 with fake instruments and temporary files, covering move failures, tiny readback offsets, both Lock-in X/Y failures, inactive connected devices, Lock-in 2 delay, Realtime shutdown, temperature startup/read failures, peak-search failures, allowed block failure, cleanup before terminal signals, preserved partial data, storage errors and invalid plans. It also confirms the stabilization worker exits before soak and a ScanT-off scan completes while manual temperature stabilization is still running. `tests/test_drift_comp.py` 38/38. Python compilation, shared-storage default compatibility and unchanged temperature-thread/soak implementations were checked. No real instruments were operated.

### v3.5 - Optional re-peak before each later 1D_THz Stage2 repeat
- Date: 2026-10-03
- Main change: added a default-on `1D repeat peak` / `Re-peak: ON` toggle below Beam settle in the Peak search tab. During a temperature scan with Drift comp. enabled, 1D_THz now searches again before Stage2 repeats 2, 3, etc. at each temperature, to follow drift that continues after the first sweep.
- Details:
  - The initial temperature-point search serves repeat 1; later searches run immediately before the next Stage2 sweep, once per repeat within each Stage1/polarization context. No search is added after the last sweep. OFF retains only the initial search at each temperature. Non-temperature scans, Drift comp. off, Stage2 repeat count 1 and all other scan modes retain their existing behavior.
  - Reuses the existing two-round search, search step/window settings and Forward/Reverse Stage2 compensation. Each successful search updates the latest local iPos1, iPos2 and TDS Ppos, regenerates both linear position sequences, and checks their travel before acquiring the next sweep. The latest reference carries into the next temperature; queued UI updates are not read back as scan state.
  - Repeat searches keep the beam passing and do not repeat temperature stabilization, sample soak, pump-power Record or Beam settle. The new toggle is locked during acquisition; its state appears in the scan confirmation and ScanLog, and each additional search is logged.
  - HDF5: when repeat re-peaking is enabled, `repeat_scan_positions_mm` records each sweep's commanded Stage1 target, Stage2 start and TDS peak in mm. Dimensions are `(stage1_NO, stage1_rep, stage2_rep, N_pol, pol_rep, 3)`, documented by the dataset's `axes` and `columns` attributes. A row is written with the first acquired point; unstarted sweeps remain NaN. Existing iPos1/iPos2 scalars remain the first sweep's reference. Analysis of later repeats should use their saved coordinates when reconstructing absolute positions; signal dataset names/shapes are unchanged.
  - Stop during a repeat search preserves completed data and follows the existing file-close/AutoBlock cleanup. An invalid/edge peak retains the previous reference with a warning, as before; motor/Lock-in communication exceptions abort. A compensated plan outside travel aborts before the next sweep is acquired.
  - Removed the always-true `should_run_scan` flag and its unreachable skip branch. Retained both Pass code paths: one handles Pass before soak, the other handles Pass after soak (and ordinary scans); `beam_passed` prevents a second Pass at the same temperature. Existing repeated initial-position moves are retained as requested.
  - Validation timing: repetition-count consistency, coupled rotary point counts and the initial travel check still run after temperature stabilization, soak and initial peak search. An invalid configuration can therefore waste the preceding wait/search, though it is rejected before formal acquisition. The existing travel check was extracted into `validate_scan_travel()` for reuse after repeat compensation, without moving its initial timing. Moving configuration-only checks earlier is deferred; compensated positions still need a check after searching.
- Verification: `tests/test_drift_comp.py` 58/58 and `tests/test_scan_failures.py` 20/20, using fake instruments and temporary files. Added ongoing drift between sweeps, default/on/off behavior, both compensation directions, two temperatures, multiple Stage1/polarization contexts, 2D and non-temperature exclusions, per-repeat file coordinates, Stop, invalid peak and travel-limit cases. Python compilation, UI XML/widget references and diff whitespace checks passed. Native Windows UI rendered hidden at 1920 x 1040: the new row is below Beam settle and both texts fit. No real instruments were operated.

### v3.5 - Validate scan plans before starting temperature/beam operations
- Date: 2026-10-03
- Main change: moved configuration-only plan validation to `runScan()`, after instrument readiness and before the drift-reference confirmation, Realtime shutdown, worker creation, temperature changes, beam commands, waits or scan-file creation. Invalid settings now give one immediate warning and leave the current instrument/Realtime/active states unchanged.
- Details:
  - `prepare_scan_plan()` reuses the existing repetition rules, position generator and polarization planner: conflicting linear/rotary repeats, mismatched coupled rotary point counts, and unreachable initial scan paths are rejected immediately. It includes the initial rotary configuration used by search/repeat resets as well as the calibrated polarization targets. Inactive axes remain excluded from travel checks; rotary `resolve_target()` still permits valid wrapped angles.
  - The validated start positions, step arrays, repeat counts and polarization plan are passed to `ScanThread` and reused for acquisition. Removed their former in-temperature-loop validation/planning block rather than maintaining a second set of configuration checks.
  - After every initial temperature-point peak search, the two compensated linear sequences are regenerated and travel-checked before creating that temperature's HDF5 file or acquiring data. The check after each later 1D repeat search remains. These checks cannot all be moved before search because the actual drift is not yet known.
  - Confirmed Realtime means the two checkable `QPushButton` controls `realtimeDisp1/2`: scanning releases these display buttons and stops their timers. It leaves `activeLockin1/2` and `activeStage1/2` checked as configured; scan acquisition/charts still work. Confirmed Beam settle and 1D repeat peak inputs/buttons and both labels already have explanatory tooltips.
  - Reconfirmed the removed `should_run_scan` flag only received True in the prior implementation, so its `if not ...: continue` branch was unreachable. Temperature-observer replacement remains unchanged: the observer exits after enough in-tolerance readings, before soak; a still-running observer can nevertheless be replaced after the current 2-second stop timeout. Proposed future fix: interruptible polling waits, retain/join the old observer before replacement and refuse replacement on timeout, without setting the main scan stop flag or waiting for the physical ramp to finish.
- Verification: `tests/test_scan_failures.py` 30/30 and `tests/test_drift_comp.py` 58/58 with fake instruments. New cases confirm early rejection causes no scan worker, temperature target change, beam command, movement, data/log file or Realtime/active-state change; cover conflicting repeats, coupled counts, linear/rotary endpoints, calibration and initial rotary targets, valid coupled/wrapped plans, inactive axes, and a post-search correction outside travel before file creation. The existing ScanT-off test still completes while manual temperature stabilization runs. Python compilation, UI tooltip/default inspection, unchanged temperature-thread comparison and diff whitespace checks passed. No real instruments were operated.

### v3.6 - X Auto Zero and editable Lock-in reference phase
- Date: 2026-10-03
- Main change: copied the current v3.5 Python/UI into `OPTP_system_iTC_v3.6.py` and `OPTP_iTC_main_v3.6.ui`. The new entry point loads the v3.6 UI, titled OPTP System v3.6. Both Lock-in Auto Phase buttons are replaced by Auto Zero, and each X readout shares its former space with a decimal reference-phase control.
- Details:
  - Auto Zero calls the existing `SR830.auto_offset(1)` for the corresponding instrument, issuing `AOFF 1` for X only. It then reads X through the existing `get_x()` / `OUTP? 1` path, updates the numeric readout and appends that actual reading to the realtime chart, including with Realtime off. There is no software baseline subtraction, fabricated zero, Y/R offset command or phase change. Failed/unverified operations show a warning and `--` instead of a false zero.
  - Phase controls use the existing `get_phase()` / `set_phase()` methods. Connection or a repeated Conn. Instr. reads the current phase without writing any default. Editing is committed on Enter or focus loss, followed by a hardware readback so the displayed value follows the instrument's wrapping/rounding. Fields accept -360.00..729.99 degrees with two decimals and a degree suffix; editing signals caused by readback or an untouched field cannot write a default phase. Unknown/failed readbacks are blank.
  - Added shared Lock-in connection handling for the two rows. Failed open/identification closes the candidate session and leaves the device reference empty, so the new controls cannot act on a failed connection. Closing a selected Lock-in clears/disables its Phase and Auto Zero controls; an unselected connected Lock-in remains available. Both new controls are disabled and their handlers guarded during scanning, then restored according to connection state.
  - UI row proportions split the former numeric area approximately 3:2 between X and Phase. Native Windows at 1920 x 1040: X readouts changed from 157/152 px to 94/90 px, Phase 62/60 px. At the original 1661 x 973 window size, both X fields are 82 px and Phase fields are 60 px. Negative scientific notation and negative two-decimal phases fit. Readouts are read-only and start at `--`; Phase and Auto Zero have explanatory tooltips.
  - Reused all three methods already present in `inst_libs/stanford_SR830.py`; that shared file and both v3.5 files are byte-for-byte unchanged. v3.5 scan planning, beam/temperature timing, repeat peak search and cleanup logic are inherited. The older temperature-observer replacement issue remains deferred.
  - Command semantics checked against the [SRS SR830 manual](https://www.thinksrs.com/downloads/pdfs/manuals/SR830m.pdf), sections 5-4 (PHAS), 5-8/5-11 (AOFF) and 5-15 (OUTP/OUTR). Actual panel vs OUTP readback after Auto Offset remains a lab verification item; tests use a fake VISA session and do not establish real-instrument residual accuracy.
- Verification: `tests/test_lockin_controls.py --native-preview` 30/30, exercising the real SR830 command methods over fake VISA sessions, decimal keyboard entry, no writes on connection/readback/focus-only events, independent devices, X-only offset, residual readback, scan locking, failed writes/reads/connection, partial close/reconnect, formal scan storage and hidden native Windows layout. `tests/test_scan_failures.py 3.6` 30/30 and `tests/test_drift_comp.py 3.6` 58/58. The failure test now accepts an optional version argument, defaulting to v3.5. Python compilation, UI references, original-file hashes and unchanged scan-method comparisons passed. No real instruments were operated.

### v3.6 - Multiline Lock-in tooltips and numeric-only Phase entry
- Date: 2026-10-04
- Main change: rewrote both Phase and Auto Zero tooltips with short explicit lines; the adjacent X readout tips also use two lines. The Python scan/control implementation is unchanged.
- Details:
  - Phase help explicitly says to type a number: the QDoubleSpinBox adds its degree suffix automatically. Enter or focus loss applies the setting and displays the instrument readback. The suffix is display formatting, not a required part of the number typed by the user.
  - Auto Zero help explains X Auto Offset, actual residual readback, unchanged Y/R offsets and phase, and availability outside scans. All lines are at most 60 characters.
  - Synced these Lock-in controls into new MO v2.6, OPTP Imaging v1.7 and THz Emission v1.5 Python/UI pairs. Previous versions were preserved byte for byte. Scope of each system is recorded in its own dev log.
- Verification: test_lockin_controls.py optp --native-preview: 32/32 with fake VISA sessions. Includes typing -12.34 without a degree sign, automatic suffix display, multiline tips, independent instruments, readbacks, scan locking, partial close/reconnect, failed commands and hidden native layouts. No real instruments were operated; Auto Offset panel/readback agreement still requires a hardware check.

### v3.6 - Sample-soak minute suffix and rich Lock-in tooltip headings
- Date: 2026-10-04
- Main change: Phase, Auto Zero and X-readout tooltips now use a bold control-name heading, a separate explanatory paragraph and explicit short line breaks, matching the other rich-text help in the UI.
- Details:
  - Both Lock-in rows use the same rich-text formatting across all four current systems. Phase still accepts numbers alone and adds its degree suffix automatically.
  - WaitSamStable now has the QSpinBox suffix " min". Typing 17 displays "17 min" while value() remains the integer 17 used by the existing minute-based scan wait. Its tooltip uses the same heading/body format and explains the automatic unit and zero-wait setting. Existing defaults and numeric limits are unchanged.
- Verification: loaded all four current UIs with their real controller initialization in a hidden native Windows window, with temporary QSettings and without connecting instruments. Confirmed bold title formatting, visible paragraph separation and short body lines; inspected rendered tooltip images. Where present, typed a bare numeric wait value and checked the automatic min display, unchanged numeric value, and maximum-value fit at 1661 px window width. Updated the existing tooltip-format assertion for rich text. Application Python files and previous UI versions are unchanged; no acquisition or real-hardware test was needed for this presentation-only change.

### v3.6 - Default beam order changed to Soak then Pass
- Date: 2026-10-04
- Main change: the Peak search tab's Beam / soak button now starts at Soak -> Pass (passOrder unchecked). Its Designer text and both button/label tooltips identify the same default.
- Details: with AutoBlock during a temperature scan, keep the beam blocked through temperature stabilization and sample soak, then pass the beam and perform the configured extra Beam settle wait before peak search or measurement. The user can still toggle to Pass -> Soak. Python scan logic and other versions are unchanged.
- Verification: UI XML and existing startup/toggle mapping checked; loaded v3.6 without instrument connections and confirmed the startup label/state and both toggle directions. No real instruments were operated.

### v3.6 - Rotary initial-angle input limits set to 0..360 degrees
- Date: 2026-10-04
- Main change: explicitly set the minimum and maximum of `iRot1`, `iRot2` and `iRot3` in `OPTP_iTC_main_v3.6.ui` to 0 and 360 degrees. The first two previously inherited Qt's default maximum of 99.99; the third had an explicit maximum of 1000. All three now use the requested range.
- Details: retained the existing default values (3, 4 and 4 degrees), decimal precision and scan behavior. The v3.6 Python entry point already loads this UI and does not override these limits, so no Python change was required.
- Verification: parsed the UI XML and loaded it through PySide6 QUiLoader without connecting instruments. Confirmed all three ranges and defaults, and acceptance of 0, 180, 359.5 and 360 degrees. CRLF line endings preserved.

### v3.7 - Save the current interface as PNG beside scan data
- Date: 2026-10-04
- Main change: copied the current v3.6 Python/UI pair to `OPTP_system_iTC_v3.7.py` and `OPTP_iTC_main_v3.7.ui`, updated the loaded UI filename/window title, and added Screenshot immediately to the right of Clear Display. Previous-version files are preserved byte for byte.
- Details:
  - Captures the entire application client area, including visible controls, current tabs and plots, using Qt widget rendering. The button remains available during scans and after completion, with a standard save icon and a multiline tooltip with a bold heading.
  - If a scan file has been assigned in this session, use its exact folder and basename, changing only `.h5` to `.png`. Temperature, mode, extra-info text and dots in the basename are retained. Editing settings for the next scan does not rename or relocate the previous scan's PNG. Repeated clicks replace the same screenshot.
  - Before the first scan file, save in the selected data folder using time, scan mode and the existing sanitized extra-info suffix. Screenshot naming does not change the displayed data filename, data path, HDF5 file or acquisition state.
  - Save through QSaveFile so an encoding/write failure does not destroy an existing PNG. Success reports the path in the status bar and console; failure shows a warning. No instrument reads or commands are issued by the screenshot action.
- Verification: `tests/test_ui_screenshot.py` with this system and `--native-preview`: 14/14 passed, using hidden native Windows Qt windows, temporary settings/files and no instrument connections. Covers actual button wiring, rendered PNG dimensions, pre-scan naming, scan-time availability, exact temperature/dotted filenames, Unicode paths, replacement after editing next-run settings, preservation of data/scan state, partial-write failure and invalid output paths. Across all four systems: 50/50. AST comparison confirms acquisition, temperature, peak search, movement and Lock-in methods are unchanged; all eight prior Python/UI files retain their original hashes. Python syntax and UI XML checks passed.

### v3.7 - Temperature-independent peak tracking and coupled scans of selected axes
- Date: 2026-10-04
- Main change: Drift comp. is now the master peak-search switch whether or not ScanT is enabled. Coupled rotary planning uses only checked axes, allowing Rot1/Rot2 to scan together while Rot3 is unchecked.
- Details:
  - Initial search runs once before acquisition without a temperature sequence, or once at each temperature point with a sequence. Stage1, Lock-in 1 and a valid TDS Ppos reference are required whenever Drift comp. is on. Turning it off disables both initial and repeat searches. An ordinary ScanT-off scan still does not wait for a manual temperature ramp to finish.
  - In 1D_THz with Stage2 Repeat > 1, Re-peak ON searches before repeats 2, 3, etc., regardless of temperature scanning; OFF leaves only the initial search. Other modes, including POL_2D, receive the initial search but no extra Stage2-repeat search. The existing per-sweep coordinate dataset, travel checks and exception cleanup are retained. Re-peaking does not repeat temperature stabilization, sample soak or beam-settle waits.
  - Fixed-Stage1 1D_THz now places Stage1 directly at the newly found peak instead of retaining a stale iPos1-minus-TDS-Ppos offset. This addresses the observed 50 um offset. Stage2 compensates the full actual Stage1 correction, including removal of that offset, with the configured Forward/Reverse sign. Multi-point Stage1 scans and other modes retain their existing window offset. Confirmation text, ScanLog and tooltips explain both cases.
  - In ordinary coupled mode, only checked rotary axes must have equal point counts; each retains its own starting angle and step. Unchecked Rot3 does not constrain the count and is not moved. A single checked axis scans alone; no checked axes produces one fixed state. Independent Cartesian scans retain their existing behavior. Calibration remains Rot2-driven and no longer requires the Rot3 calibration column when Rot3 is unchecked.
  - Added an optional active_rotaries argument to the shared planner, enabled only by the four current entry points. Callers that omit it retain the old three-axis rules. Synced rotary behavior and multiline rich-text help to MO v2.7, Imaging v1.8 and THz Emission v1.6. MO peak behavior stays unchanged per the user's earlier preference; no new peak workflow is enabled in the other systems.
- Verification: fake-instrument tests: test_drift_comp.py 3.7 67/67, test_scan_failures.py 3.7 30/30, and test_rotary_coupling.py optp/mo/img/thz 20/20 each (177/177 for current versions). Covers no-temperature initial/repeat search, Drift/Re-peak exclusions, both compensation directions, stale-offset removal, other-mode window retention, all eight rotary activation combinations, coupled count errors, unchecked-axis movement exclusion, calibration, and legacy planner compatibility. The v3.5 drift suite also passes 58/58. No real instruments were operated; hardware confirmation remains in OPTP_handoff.md.

### v3.8 - Immediate 1-degree Phase arrow controls
- Date: 2026-10-04
- Main change: copied the current v3.7 Python/UI pair to OPTP_system_iTC_v3.8.py and OPTP_iTC_main_v3.8.ui. The new entry point loads the v3.8 UI and its title identifies v3.8. All prior Python/UI versions and the other three systems are unchanged.
- Details:
  - Both Phase QDoubleSpinBoxes show their native up/down arrow buttons and use a 1-degree singleStep. Decimal entry retains 0.01-degree precision, the automatic degree suffix and the existing allowed range. The multiline tooltips describe immediate arrow application and Enter/focus-loss text commits.
  - Added one valueChanged connection per box through the existing two-device initialization loop. keyboardTracking remains false: ordinary typing does not send intermediate digits, while arrow steps and committed edits call the existing guarded Phase write/readback handler. The existing editingFinished connection remains for Enter/focus loss. Signal-blocked instrument readbacks and the edited-state guard prevent recursive or duplicate commands; connection does not write a default phase.
  - Native Windows renders these arrows beside each other. To keep full decimal phases visible, raised the Phase minimum width from 60 to 92 px and set an 80 px minimum for the adjacent X readout. This retains readable values at 1920 px and 1661 px window widths without changing window size or adding controls.
  - Python change size versus v3.7: one new functional line, one explanatory comment and one version-record line (net +3), plus the existing UI filename replacement. UI changes are control properties, tooltip text, minimum widths and window title (net +14 XML lines). No scan, peak-search, rotary-planning, temperature, screenshot or instrument-driver methods were changed.
- Verification: test_lockin_controls.py optp --native-preview: 45/45 with fake VISA sessions, real SR830 command methods and hidden native Windows Qt. Covers actual mouse arrow clicks on both devices, exactly one write/readback per step, Enter and actual focus-loss commits, no intermediate typing writes, pending text plus arrow, wrapped readback, failure handling, scan locking, Auto Zero, formal acquisition and layout. The same suite against the unmodified v3.7 passes 28/28 without native layout checks. AST comparison confirms all controller methods except initialization are unchanged, and hashes confirm all 84 existing top-level system Python/UI and shared-library files are unchanged. No real instruments were operated.

### v3.8 - JSON scan configurations and connection-time Lock-in settings readback
- Date: 2026-10-04
- Main change: added Imp. Conf. and Exp. Conf. beside Screenshot in the existing v3.8 UI. They restore/save scan recipes as readable UTF-8 JSON. Both SR830 connections now read sensitivity, time constant and phase without writing settings back to the instruments.
- Details:
  - Scan recipe scope: scan mode and filename suffix; instrument-active selections; linear/rotary initial positions, step segments, point counts and repeats; rotary coupling/calibration selection; Lock-in acquisition waits and multipliers; actual ordered temperature list, list-builder inputs, stability settings and soak; Drift comp., TDS Ppos, both search rounds, Stage2 compensation, Re-peak, beam order/settle/AutoBlock/pass channel; pump-power Record and its averaging/settling/refresh settings. Export captures current UI values, including positions already updated by re-peaking.
  - Excludes Lock-in sensitivity/time constant/phase, instrument addresses/channels, PM wavelength/range, heater/manual commands, live readouts, realtime toggles, output directory, current data filename and acquired data. Import does not connect/disconnect instruments, move stages, change temperature, pass/block the beam, or read/write hardware settings.
  - JSON declares format OPTP.scan_config, schema_version 1, application version and save time. Validate the complete known field set, types, finite values, widget ranges/precision, temperature list and calibration data before applying anything. Ordered/repeated temperature points are retained. The referenced calibration file is reloaded (relative paths resolve against the JSON folder); missing/invalid files reject the import. Calibration contents are not embedded. Importing a recipe without calibration clears a previously loaded table.
  - Apply inputs with signals blocked, then explicitly synchronize the temperature model/list, button captions, scan mode and software wait timers. Changed beam pass-channel mapping marks the displayed beam state unknown without querying/moving the mount. Existing run-time scan-plan and travel validation remains in place.
  - Import is disabled during scans and guarded in code. Export remains available and captures current UI settings. File dialogs support named presets; missing .json suffixes are added. Atomic QSaveFile writes preserve an existing JSON on a partial write failure. Cancelled or invalid imports leave the previous configuration in place. Tooltips use bold headings and short explanatory lines.
  - The existing SR830 driver already supplies get_sensitivity_index(), get_time_constant_index() and get_phase(); no driver changes were needed. New or repeated Conn. Instr. reads all three for each selected Lock-in. Combo-box updates block signals, so no SENS/OFLT/PHAS writes occur. A failed/out-of-range read clears only the unknown setting and reports it instead of presenting a default as a confirmed hardware value. Unconnected startup displays retain their existing sensitivity/time-constant defaults and unknown Phase state.
  - User choice: keep current/imported Wait(ms) and multiplier settings on connection. Reading a different hardware time constant does not recalculate waits or write the UI defaults into the instrument. Manual setting edits retain their existing behavior.
- Verification: test_scan_config.py --native-preview 36/36 and test_lockin_controls.py optp --native-preview 52/52 (88/88), with temporary files/settings and fake instruments. Covers real button wiring, every saved field, UTF-8/BOM, calibration/path handling, repeated temperature points, invalid-input rejection before mutation, cancellation, atomic-write failure, scan locking/export, zero instrument calls during import/export, independent connection queries without writes, preserved waits, partial/invalid readbacks, Phase arrows, Auto Zero, formal acquisition and hidden native layout. AST comparison confirms scan acquisition, peak search, movement, temperature and instrument-setting application methods are unchanged. Only the v3.8 Python/UI files changed among existing application/shared-library files; all older versions and other systems are unchanged. No real instruments were operated.

### v3.8 - Search before the first 1D_THz sweep at a changed angle
- Date: 2026-10-04
- Problem: in a multi-angle 1D_THz scan, the old condition searched only before Stage2 repeats 2 and later. The first sweep at each new polarization used the preceding angle's peak. Repeat searches also passed the original rotary starting angles to the search routine, so the search could happen at a different polarization from the subsequent measurement.
- Changes:
  - With Drift comp. ON in 1D_THz, a changed active rotary angle now triggers a search before the first Stage2 sweep at that angle, with or without temperature scanning. This also applies when Stage2 Repeat = 1 or Re-peak is OFF. Re-peak continues to control only subsequent same-angle Stage2 repeats; Drift comp. OFF disables all automatic searches.
  - Each angular/repeat search moves the active rotaries to the current planned angles before acquiring its peak samples. Initial searches use the first planned angles (including calibration interpolation), reset at each temperature. Returning from the final angle to the first in a polarization repeat triggers another search when active angles differ. Inactive axes do not cause searches; there is no duplicate search before the first sweep already covered by the initial search.
  - Retained the existing two-round search, fixed-Stage1 direct-peak placement, actual Stage1 correction / Forward-Reverse Stage2 compensation, corrected-travel validation, failed-search fallback, interruption checks and file cleanup. No extra temperature, sample-soak or beam-settle wait is added at an angular/repeat search.
  - The existing repeat_scan_positions_mm dataset is also created for angular tracking with repeats OFF or count 1, retaining its shape/axes/columns. Every sweep records its actual Stage1 target, Stage2 start and peak reference; the original iPos1/iPos2 scalars continue to describe the initial sweep only.
  - Added distinct Angle peak search log events (with current planned angles), updated the startup confirmation / ScanLog description and the Drift comp., Re-peak and scan-mode tooltips. No new controls or JSON fields are required. Other modes (THz_Scan, 2D_THz, POL_2D) retain their initial search only and their existing compensation behavior.
  - Reviewed MO v2.7, Imaging v1.8 and THz Emission v1.6 for applicability. MO retains its older per-temperature Stage2 calibration per the user's prior instruction not to add MO peak functionality; Imaging has peak_search_enabled = False; THz Emission's inherited search requires the unavailable 1D_THz mode. No corresponding enabled workflow is ported or introduced. Their Python/UI files and all older OPTP versions, including v3.7, remain unchanged; each system's devlog records the review.
- Verification: extended test_drift_comp.py with 17 angular scenarios using the real scan worker, a Gaussian Lock-in peak dependent on actual rotary positions, simulated instruments and temporary settings/data. The unmodified controller failed 12 of these checks, reproducing the missing first-angle search and wrong-angle search; the corrected v3.8 passes 84/84. Includes coupled/independent angles, active Rot3, inactive-axis exclusion, calibrated first angle, first/repeat measured peak signals and coordinate metadata, Re-peak OFF, Repeat = 1, repeated polarization cycles, temperature resets, no extra waits, other-mode exclusions and stop during the new search. test_scan_failures.py 3.8 passes 30/30; test_rotary_coupling.py optp passes 20/20 (134/134 total). No real instruments were operated.

### v3.9 - Local simplification with acquisition behavior preserved
- Date: 2026-10-04
- Main change: copied the current v3.8 Python/UI pair to OPTP_system_iTC_v3.9.py and OPTP_iTC_main_v3.9.ui. Updated the loaded UI filename, window title and JSON application_version to 3.9. Preserved all v3.8/older files, the other three systems and shared libraries.
- Simplification:
  - Combined identical scan-time control-enabling branches. The same buttons remain available while scanning and Lock-in connection-dependent enablement still runs afterwards.
  - Added one small ordered UI-value helper for current positions, repeats and point counters. Simplified step and Lock-in chart updates to loops. Missing/None values are skipped, zero remains valid, the existing mm-to-um multiplication/int conversion is retained, and updates occur in their original order. Rotary step-input boxes are still not overwritten by scan progress.
  - Kept move_active_stages and its (True, positions) return format unchanged. Removed only the caller's impossible False/None branch; driver/readback exceptions still abort through the existing scan error and cleanup path. No new position tolerance or equality check was introduced.
  - Removed five unused imported names (QVBoxLayout, QWidgetItem, QPen, random, sio), the duplicated local os import, and obsolete commented plotting/signal-blocking examples.
  - Removed ten redundant console call sites: per-point move success, acquired-value summaries, peak-position progress lines, number-box updates and duplicate TDS/FDS drawing notifications. Measurement values still reach their original displays and files. Errors, warnings, search round/results, angle/repeat events, countdowns and ScanLog records remain.
  - Corrected the manual Stage2 movement message's unit from deg to mm. Its numerical target, driver call and readback are unchanged.
- Preserved behavior: instrument connection/homing and close logic; temperature/thread behavior; initial/current-angle/repeat peak-search conditions and compensation; move/wait/read order; all settling durations; active-instrument checks; HDF5 dataset layout/NaN handling/per-point flush and cleanup; Phase/Auto Zero/readback; Screenshot; JSON import/export and schema version 1. UI properties other than the version title are identical. No broad connection or scan-function rewrite was performed.
- Size versus the copied v3.8 source (application Python only): 4059 -> 3985 physical lines, net -74 (-1.82%). This consists of 43 fewer nonblank/non-comment-only lines, 27 fewer comment-only lines and 4 fewer blank lines. The version-to-version diff has 151 removed and 77 added lines, including the retained scan body being unindented after removal of its redundant wrapper. New verification code/documentation is counted separately; the UI line count is unchanged.
- Verification:
  - test_v39_refactor.py: 17/17 checks, including 7531 differential input cases against v3.8. Compares the order and values of display/chart calls for missing/None/zero/negative/decimal inputs and invalid-step exceptions; verifies the movement return/exception contract, unchanged UI XML apart from its title, and unchanged method structure after normalizing only the documented version/output changes and redundant wrappers.
  - Real controller/scan-worker tests with simulated instruments: test_drift_comp.py 3.9 84/84; test_scan_failures.py 3.9 30/30; test_rotary_coupling.py optp 20/20. Includes initial/angular/repeat tracking, all scan-mode exclusions, temperature/beam waits, compensation, movement/read/storage failures, cleanup and selected-axis coupling.
  - Hidden native Windows Qt: test_lockin_controls.py optp --native-preview 52/52; test_scan_config.py optp --native-preview 36/36; test_ui_screenshot.py optp --native-preview 14/14. Includes connection queries without writes, preserved Wait(ms), Phase arrows/commits, Auto Zero, scan locking, JSON round trips/errors and PNG naming/replacement.
  - Functional regression total: 236/236, plus the 17 comparison checks. Python syntax/UI XML checks and original-file hashes passed. No real instruments were operated; hardware timing/acquisition confirmation remains a lab verification item.

### v3.9 - Screenshot camera icon
- Date: 2026-10-04
- Change: replaced the Screenshot button's standard save icon with a camera SVG in the latest Python/UI pair. The local `camera.svg` is referenced by the UI for Qt Designer and loaded relative to the Python file at runtime. Keep this asset beside the Python/UI files when copying the system.
- Scope: button text, tooltip, size, click handler, PNG folder/naming/replacement behavior and scan availability are unchanged. No instrument or acquisition logic changed; older versions retain their original icons.
- Verification: native Windows screenshot checks plus temporary camera-rendering and button-width checks passed 16/16; all four systems total 58/58. Python syntax, UI/SVG XML and a comparison against the pre-change files confirm only the icon assignment/property changed in application code/UI. No real instruments were operated.
- Regression comparison: updated the existing v3.8/v3.9 comparison to recognize this exact icon change and locate the archived v3.8 baseline in `old_version`; 17/17 checks and 7531 differential input cases passed.

### v3.9 - Frame and lower the display-actions row
- Date: 2026-10-04
- Change: in `OPTP_iTC_main_v3.9.ui`, wrapped Clear Display, Screenshot, Imp. Conf., Exp. Conf. and both horizontal spacers in an untitled `displayActionsGroup` QGroupBox. It uses the same native one-pixel frame as the Mercury iTC group below.
- Layout: added 8 px of top margin to the right-hand column, reduced its layout spacing to 2 px, and added 6 px of padding inside the new frame. The horizontal spacer height hints now match the 30 px buttons. The framed row stretches with the available width and sits closer to the temperature controls.
- Scope: OPTP v3.9 only; the other systems have a different three-button row. All button names, labels, tooltips, icons, signal handlers and scan-time enable rules are retained. No application Python logic changed.
- Verification: native Windows preview confirms matching frame widths, a 2 px layout gap above Mercury iTC, and fully visible buttons. Screenshot tests pass 14/14; scan-configuration tests pass 36/36, including scan-time button availability and zero instrument commands. Updated the existing v3.8/v3.9 comparison for the explicitly allowed frame/layout changes; 17/17 checks and 7531 differential input cases pass. No real instruments were operated.

### v3.9 - Remove the display-actions border
- Date: 2026-10-04
- Change: at the user's request, replaced the new display-actions QGroupBox with a borderless QWidget. Retained the lowered row, layout margins and reduced spacing above the temperature controls; button behavior and application Python are unchanged.
- Verification: native Windows preview confirms the border is gone and all four buttons remain visible. The updated comparison passes 17/17 checks and 7531 differential input cases.

## Summary
The overall objective of this debug/development branch is to make the OPTP scan workflow more stable under temperature variation and to improve reliability during real experimental runs.

## Notes
- This is the project-wide development record for the OPTP debugging workflow, not a v1.5-only log.
- Open work - anything not yet done, and every change still waiting on a real-hardware run - is tracked
  separately in `OPTP_handoff.md`. This log is the history of what changed; that file is the to-do list.
- Future changes should be added here with the corresponding version number and description.


### v4.0 - Safe Goto T thread replacement
- Date: 2026-10-05
- Files: copied the current v3.9 Python/UI to OPTP_system_iTC_v4.0.py and OPTP_iTC_main_v4.0.ui; updated the UI loading path and window title. v3.9 files are preserved.
- Fix: stop and join the previous temperature-stabilization worker before sending a new hardware setpoint or replacing its QThread object. A 2-second timeout retains the old object, rejects a manual request with a console message, and raises a scan error for automated temperature changes.
- Waiting: temperature polling waits check stop/interruption every 50 ms. Communication already in progress must still finish before replacement. Removed explicit processEvents from the Goto T replacement path to avoid nested button handling during replacement.
- Signals: renamed the stabilization-result signal to stabilized(bool), preserving QThread.finished for native thread termination. Temperature scans wait directly for actual worker termination and read stab_success before measuring. The worker is named iTC stabilization for diagnostics.
- Scope: scan point timing, instrument drivers and window-exit cleanup are not changed.
- Verification: test_v40_temperature_threads.py passes repeated Goto T with a 10-second interval, actual blocked-I/O timeout and retained-worker checks, automated-request failure, retry, and separate success/error/stop result and lifecycle signals. Existing scan-failure checks pass 30/30 and temperature/drift-compensation checks pass 84/84 using simulated instruments. Syntax, UI XML, version-title-only UI comparison and CRLF checks pass. No real instruments were operated.


### v4.0 - Manual Stage1 / Stage2 Home buttons
- Date: 2026-10-05
- UI: added stage1Home / stage2Home to the blank area right of each iPos input. The upper stage controls now use a two-row grid so Home and Move to share a row and the same font/height policy. No other stage settings or scan data layout changed.
- Action: each button enables and sends Home(60000) to its own BBD202 channel, then refreshes that stage's current-position display. Initial scan positions remain unchanged. This deliberately performs real homing even when the axis is already marked homed; the shared driver's home() skips that case, so shared drivers are unchanged and the v4.0 manual handler calls the channel directly.
- Scanning: the existing QPushButton scan lock disables both Home controls; the handler also rejects calls while _scanning is true. Controls are restored at scan completion. Disconnected stages and homing errors report to the console. Homing is synchronous, matching existing manual stage moves.
- Verification: test_stage_home.py passes on native Windows Qt with simulated axes. Both Home/Move buttons render at equal 25 px heights and identical vertical positions at requested window sizes 1661x973 and 1400x900. Tests cover correct-axis command routing, refreshed current position, retained iPos, scan disable/restore, homing errors and disconnected axes. Native screenshot inspected; Python syntax, UI XML and CRLF checks pass. No physical instruments were operated.


### v4.0 - Restore original stage manual-control borders
- Date: 2026-10-05
- Correction: restored the original Stage1/Stage2 manual QFrame containers, inst_manu border styling, layout margins and complete jog/Move to contents from v3.9. Their removal during Home alignment was outside the requested change. Home buttons remain outside those original frames, to the right of iPos.
- Verification: XML subtree comparison confirms both restored manual frames exactly match v3.9. Native Windows screenshot confirms borders are visible; Home/Move to remain equal in height and vertically aligned at both tested window sizes. Home functional and scan disable/restore checks pass. Added frame/border regression assertions to test_stage_home.py. No hardware was operated.


### v4.0 - Delay manual Home position readback
- Date: 2026-10-05
- Change: after the manual Stage1/Stage2 Home command completes, call qwait_time(1000) before reading and displaying position, matching the existing connection homing readback delay. No commanded move to 110 mm is introduced; homing configuration and UI layout are unchanged.
- Verification: test_stage_home.py passes, including enable -> Home(60000) -> wait(1000) -> position readback for each axis, original borders, equal Home/Move to height and alignment, scan disable/restore, and failure/disconnection handling. Waiting is substituted only in the command-order test; no real instruments were operated. Hardware verification is needed to determine whether the reported 0 mm was stale readback or an actual homing endpoint.


### v4.0 - Debug review and unresolved hardware observations
- Date: 2026-10-05
- Devlog audit: today's implemented Goto T thread fix, manual Home controls, original-border restoration and 1-second manual Home readback delay were already recorded above. The investigation-only findings below were missing and are now recorded; they do not represent additional behavior changes.
- Scan timing: Lock-in Wait(ms) is only the post-movement settling delay. Point time also includes sequential moves/readbacks of all enabled axes (even unchanged targets), separate X/Y VISA queries with 50 ms between them, per-point HDF5 writes/flush and signal overhead. Equal 300 ms waits for two lock-ins are not summed; fixed sleeps total 400 ms in that case. No timing optimization was implemented or measured on hardware.
- Beam settle: currently requires temperature_stabilized AND beam_passed. Thus AutoBlock Pass in a scan without temperature control does not execute Beam settle before the initial peak search. This condition was confirmed, not changed.
- Power Record: requires Record and AutoBlock, confirms/establishes Block, waits for sensor settling and averages N readings immediately before Pass. It runs once per temperature point, or once at the start of a scan without temperature control, and is not repeated during Pass/acquisition. Realtime reading/display is separate from saved Record data. No change.
- Re-peak: repeat search requires Drift comp. ON, 1D_THz mode, Stage2 repeat > 1 and Re-peak ON. It runs before Stage2 sweeps 2 and later; Stage1 repeats alone do not trigger it. Changed active angles trigger a first-sweep search when Drift comp. is on, independently of Re-peak. No change to these conditions.
- Home observation: the user reports automatic connection homing ends at 110 mm even when not skipped, while manual Home displayed/appeared at 0. Both paths call the channel Home(60000); connection already waits 1 second before position readback. Manual Home now has that same wait. Stale readback is a hypothesis, not a proven cause; no explicit move to 110 was added. Hardware verification remains open.
- Stage2 arrows: corrected the initial misunderstood report: Stage1 relative moves work; Stage2 Move to works but repeated +/-1 mm arrow requests report unchanged 116.0 or 117.5 mm. The user confirms both stages share a controller and use different channels. Native Qt mouse-click checks confirm signed move_by calls are dispatched. Reflection of the installed BrushlessMotorChannel API confirms MoveRelative(MotorDirection, Decimal stepSize, Int32 waitTimeout) exists, and the driver obtains each axis with GetChannel(channel_index). No wrong-parameter or wrong-channel root cause was established. Possible readback/channel-relative-execution issues remain unverified. The suggested Stage2-only absolute-target workaround was not implemented; drivers and arrow handlers are unchanged.
- Angle progress: confirmed that the existing search helper moves to the new rotary angles before searching, but previously emitted the rotary Curr. NO and position updates only after returning to acquisition. This display-order issue is addressed in v4.01 below.

### v4.01 - Show the current rotary angle before peak search
- Date: 2026-10-05
- Files: copied the latest v4.0 Python/UI to OPTP_system_iTC_v4.01.py and OPTP_iTC_main_v4.01.ui. v4.0 is preserved. Updated the loaded UI path, window title and exported application_version to 4.01 (the inherited v4.0 export had still reported 3.9); JSON schema stays 1.
- Fix: after positioning stages/rotaries for a search, emit the actual position readbacks and current rotary step counters before acquiring peak samples. Initial searches reset counters to the first planned states; angle/repeat searches use the same rotary step-index mapping as formal acquisition. Existing Stage1 peak-progress updates continue independently. No processEvents call is added to GUI scan slots.
- Scope: search/motion order, coupled-angle combinations, compensation calculations, per-point timing, Re-peak/Beam settle/Record conditions, shared drivers and UI layout/borders remain unchanged. This is a progress-display timing fix.
- Verification: test_v401_peak_progress.py passes 6 checks for movement/readback/counter/search order across initial/new/repeated angles, optional progress and failed/stopped searches. Existing scan-failure checks pass 30/30 and temperature/drift checks pass 84/84 with simulated instruments. Native Qt signal/slot checks confirm actual rotary Curr. NO and position widgets update before the search callback; Home routing/scan lock and original manual-control borders/alignment also pass on the v4.01 UI. UI comparison confirms only its title changes; Python syntax, UI XML and CRLF checks pass. No hardware was operated.


### v4.01 - Refresh Save Name at scan start and timestamp screenshots
- Date: 2026-10-06
- Problem: Save Name previously refreshed only after temperature/settling/initial peak search, when a data file was created. Screenshots reused the current/latest data filename and overwrote its PNG, including the previous scan during a new scan's preparation.
- Scan naming: after validation/confirmation and before starting the worker, immediately refresh Save Name and clear the previous fullFilePath association. Each actual data file still gets its creation-time timestamp; the worker now emits filename_update(str), connected to dataFileName.setText on the GUI thread, instead of directly modifying that widget. The new connection is disconnected with the other scan signals when replacing the scan worker.
- Screenshots: retain the current/latest data stem and directory when a current data file exists; otherwise use the current scan directory, mode and sanitized suffix. Append _screenshot_YYYYMMDD_HHMMSS_microseconds, adding a numeric suffix on collision, so each capture is separate. New-scan preparation no longer associates with the previous scan. PNG writes remain atomic with QSaveFile; the Screenshot tooltip now describes separate timestamped captures.
- Scope: v4.01 Python plus Screenshot tooltip only; UI layout, instrument commands, scan acquisition order and timing, HDF5 dataset format and earlier versions are retained. Running v4.0 processes are unaffected and require launching v4.01 to use this change.
- Verification: test_v401_naming.py passes 5 native Qt scenarios with isolated settings/files and simulated scan preparation: unique/colliding screenshot timestamps, latest-data association without data modification, immediate Run-time Save Name refresh and preparation screenshot path, actual QThread filename emission with all text changes on the GUI thread, and failed PNG encoding preserving prior screenshots without partial files. test_scan_failures.py 4.01 passes 30/30. Python syntax, UI XML and CRLF checks pass. No real hardware was operated.


### v4.01 - Display-only live scan progress below ScanLog
- Date: 2026-10-06
- UI: split the existing right-hand ScanLog area in Inst. Config. & Log into two equal-height sections. The original ScanLog QGroupBox/QPlainTextEdit subtree is preserved in the upper half. A matching readonly Consolas display titled Live Progress occupies the lower half; equal stretching follows window resizing.
- Behavior: during an accepted scan, mirror stdout/stderr text to the new display through the scan worker's queued Qt progress_output signal while continuing to write the same output to the terminal. This includes print calls from the scan worker, its temperature/helper threads, GUI callbacks and exception tracebacks while the capture is active. The GUI slot appends text fragments and scrolls to the latest output without writing files.
- Lifecycle: clear Live Progress when a new scan starts; retain the finished scan's text until the next run. Restore the original console streams on completion, stop completion or scan error. Retain at most 5000 text blocks and disable undo history to bound display memory.
- ScanLog preservation: start_scan_log, scan_log_event, append_scan_log and end_scan_log are unchanged; the existing per-day ScanLog file and key-event selection retain their behavior. Mirrored progress does not enter ScanLog or a separate progress file. Instrument commands, timing and acquisition logic are unchanged.
- Verification: test_v401_live_progress.py passes native Qt checks of equal-height stacked readonly boxes, exact original ScanLog widget properties, terminal/stdout/stderr forwarding, partial-line text, helper-thread output, GUI-thread-only display updates, new-run clearing and success/stop/error stream restoration. Existing ScanLog text equals its daily file after each scan, and display-only messages are absent from disk. History-limit and no-partial-progress-file checks pass; native screenshot inspected. AST comparison confirms all four original ScanLog methods are unchanged. test_scan_failures.py 4.01 passes 30/30; syntax, UI XML and CRLF checks pass. No real instruments were operated.


### v4.01 - Limit Live Progress history to 1000 lines
- Date: 2026-10-06
- Change: reduced scanProgressText.maximumBlockCount from 5000 to 1000 and updated its tooltip. Older progress lines are discarded automatically; the display remains readonly and is not saved. Existing ScanLog behavior is unchanged.
- Verification: updated and passed test_v401_live_progress.py, including inserting 1100 lines and checking that the latest lines remain within the 1000-block limit, plus console mirroring, completion/stop/error cleanup and unchanged ScanLog persistence. UI XML and CRLF checks pass.

### v4.1 - New version copied from v4.01
- Date: 2026-11-08
- Change: copied OPTP_system_iTC_v4.01.py / OPTP_iTC_main_v4.01.ui to OPTP_system_iTC_v4.1.py / OPTP_iTC_main_v4.1.ui as the base for the next changes. v4.01 is unchanged.
  - Only the version strings differ:
    - the .ui file the program loads;
    - the window title, "OPTP System v4.1";
    - application_version "4.1" in exported scan configurations.
  - schema_version is unchanged and import checks only format and schema_version, so v4.01 and v4.1 configurations stay interchangeable.
  - Instrument connection settings (QSettings "OPTP_System" / "InstrumentConnections") are shared with v4.01.
- Verification:
  - Diff against v4.01: only these three lines.
  - Both files keep CRLF.
  - The .py compiles, and the .ui loads with QUiLoader (title "OPTP System v4.1").

### v4.2 - New version copied from v4.1
- Date: 2026-11-15
- Change: copied OPTP_system_iTC_v4.1.py / OPTP_iTC_main_v4.1.ui to OPTP_system_iTC_v4.2.py / OPTP_iTC_main_v4.2.ui as the base for the next changes. v4.1 is unchanged.
  - Only the version strings differ:
    - the .ui file the program loads;
    - the window title, "OPTP System v4.2";
    - application_version "4.2" in exported scan configurations.
  - schema_version is unchanged, so v4.1 and v4.2 configurations stay interchangeable; instrument connection settings (QSettings "OPTP_System" / "InstrumentConnections") are shared.
- Verification: diff against v4.1 shows only these three lines; both files keep CRLF; the .py compiles and the .ui parses.

### v4.2 - Live Process: always on from program start (as THz Emission v1.7)
- Date: 2026-11-15
- Change: the box below ScanLog on the Inst. Config. & Log tab is renamed Live Process and shows the console output (print messages and errors) for the whole session, from program start until it quits, instead of only during scans. It is no longer cleared when a scan starts. The same change was made in THz Emission v1.7.
- Details:
  - UI: title `Live Progress` -> `Live Process`; tooltip now "Console output of the program (print messages and errors) since it started, shown live; the terminal still gets the same text. Display only; not saved to disk. Keeps the latest 1000 lines." Widget names (`scanProgressGroup`, `scanProgressText`), the 1:1 split with ScanLog, read-only, undo off and `maximumBlockCount` 1000 are unchanged.
  - `moSys.__init__` calls `start_console_mirror()` right after loading the .ui: `sys.stdout` / `sys.stderr` are replaced by `ConsoleMirrorStream` (renamed from `ScanProgressStream`, same code), which writes to the terminal and emits the text through a small `ConsoleSignal(QObject)`; the signal is connected with `Qt.QueuedConnection` to `append_console_text()`, so the box is only updated on the GUI thread whichever thread printed.
  - `stop_console_mirror()` is connected to `QApplication.aboutToQuit` and hands the streams back to the terminal before the widgets are destroyed.
  - Removed the scan-only wiring from v4.01: `ScanThread.progress_output`, `start_scan_progress()` / `stop_scan_progress()` / `append_scan_progress()` and their calls in `runScan()`, `on_scan_finished()`, `on_handle_scan_error()` and `_disconnect_scan_signals()`. Scan logic, instrument commands and the ScanLog methods/file are unchanged. Import added: `QObject`.
  - Realtime lock-in display: with a connected lock-in, `ChartUpdater.update()` prints nothing per update in v4.1 already (unlike THz Emission up to v1.61, whose `Updating number box: ...` print was removed in v1.7), so it adds nothing to the box; no change was needed. Only the warning for a Realtime display without a connected lock-in is printed, once per timer tick.
- Verification:
  - New `tests/test_v42_live_process.py` (native Qt, isolated QSettings and data folder) passes: ScanLog subtree identical to v4.1; title/tooltip; ScanLog and Live Process equal height at 1661x973 and 1800x1100; read-only, undo off, 1000-line cap; the 9 startup lines printed inside `moSys()` appear; idle prints from the GUI thread, a helper thread and stderr appear and still reach the terminal; 5 Realtime lock-in updates with a stub lock-in print nothing and show 2.5000e-06 in the number box; success/stop/error scans keep the earlier text, show partial lines, helper-thread output and the traceback, and the mirror stays installed after each scan; all 78 box updates ran on the GUI thread; the ScanLog box equals its daily file and contains no Live Process text; `aboutToQuit` restores stdout/stderr. Screenshot inspected.
  - `tests/test_scan_failures.py 4.2` passes 30/30. Python compile and UI XML checks pass; both files keep CRLF. No real instruments were operated.
  - `tests/test_v401_live_progress.py` still targets v4.01 (scan-only Live Progress) and does not apply to v4.2.

### v4.2 - Missing lock-in warning once per Realtime switch-on
- Date: 2026-11-15
- Main change: with Realtime lock-in display switched on while that lock-in is not connected, `Warning: Lockin device 'lockinN' is not connected for realDisChartN.` is now printed once per switch-on instead of on every timer tick, so it no longer floods the terminal and the Live Process box.
- Details:
  - `ChartUpdater.__init__` adds `self._warned_missing = False`; `toggle(True)` resets it before starting the timer; `update()` prints the warning only while it is False and then sets it. Switching Realtime off and on again gives one new warning if the lock-in is still missing.
  - Nothing else in `update()` changes: it still returns without reading, and with a connected lock-in it reads and fills the chart and number box as before. Single-shot updates from the scan are not affected.
  - The same change is in THz Emission v1.7.
- Verification: `tests/test_v42_live_process.py` extended and passing: with no lock-in, 5 updates after one switch-on and 3 after a second switch-on print the warning exactly twice, and it appears twice in Live Process; all earlier checks of that test still pass. `tests/test_scan_failures.py 4.2` passes 30/30. Python compile check passes. No real instruments were operated.
