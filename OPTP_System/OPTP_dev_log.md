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

## Summary
The overall objective of this debug/development branch is to make the OPTP scan workflow more stable under temperature variation and to improve reliability during real experimental runs.

## Notes
- This is the project-wide development record for the OPTP debugging workflow, not a v1.5-only log.
- Open work - anything not yet done, and every change still waiting on a real-hardware run - is tracked
  separately in `OPTP_handoff.md`. This log is the history of what changed; that file is the to-do list.
- Future changes should be added here with the corresponding version number and description.
