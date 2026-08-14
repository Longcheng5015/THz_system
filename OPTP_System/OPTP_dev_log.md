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

## Summary
The overall objective of this debug/development branch is to make the OPTP scan workflow more stable under temperature variation and to improve reliability during real experimental runs.

## Notes
- This is the project-wide development record for the OPTP debugging workflow, not a v1.5-only log.
- Future changes should be added here with the corresponding version number and description.
