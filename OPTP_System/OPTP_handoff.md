# OPTP System - Handoff / Outstanding Work

Companion to `OPTP_dev_log.md`. The dev log records **what was changed**; this file records
**what is still open**. Every item here should either get done or get an explicit decision to
drop it - do not let items rot silently.

Last updated: 2026-10-06 (v4.01 display-only live scan progress)

**Working rules for this folder**
- All `.py` and `.ui` files here are **CRLF throughout**. `sed -i` under MSYS/Git-Bash silently
  rewrites the whole file as LF, turning a two-line change into a whole-file diff. `sed -n 'Np'`
  also strips the CR when printing, so it cannot be used to check line endings - read the file as
  bytes instead. (`.md` files in `inst_libs/backup_*/` are LF; `OPTP_dev_log.md` is CRLF.)
- No feature is complete until `OPTP_dev_log.md` has an entry for it (see `CLAUDE.md`).
- Shared libraries live in `inst_libs/` and are used by MO_System and OPTP_image_System too.
  Back them up to `inst_libs/backup_before_<reason>/` with a README before changing them.

---

## v4.01 - Early rotary peak-search progress - IMPLEMENTED, lab check open

Current entry point: OPTP_system_iTC_v4.01.py with OPTP_iTC_main_v4.01.ui; v4.0 is preserved.
After turning to a search angle, actual positions and rotary Curr. NO are signalled before peak
acquisition. Initial/current-angle/repeat searches keep their previous physical order and conditions.
- [ ] On the next v4.01 scan, confirm the lower Live Progress box mirrors terminal output while
  the upper ScanLog retains its normal saved key events. Live Progress is display-only and resets on Run.
- [ ] Launch v4.01 and confirm Run refreshes Save Name before any preparation wait; screenshots
  during preparation and acquisition have fresh capture timestamps and do not overwrite earlier PNGs.
- [ ] On hardware, scan coupled Rot1/Rot2 states in 1D_THz. During the first search at each new angle,
  confirm Curr. NO and rotary positions already identify that angle, including Re-peak and angle-cycle restarts.
- [ ] Diagnose Stage2 relative arrows on the shared controller/different channel: Stage1 relative moves
  and Stage2 Move to work, but Stage2 arrow logs show unchanged position. Root cause is not established;
  the absolute-target workaround has not been implemented.
- [ ] Verify automatic/manual Home final physical position and refreshed readback after the 1-second wait.
  Do not assume the user-reported 0/110 difference was only cached position.

## v4.0 - Goto T thread replacement - IMPLEMENTED, lab check open

New entry point: OPTP_system_iTC_v4.0.py with OPTP_iTC_main_v4.0.ui; v3.9 is preserved.
The old stabilization thread must exit before a new setpoint is sent or its QThread is replaced.
Polling waits are interruptible; blocked communication rejects replacement without losing the worker.
Stabilized(bool) is separate from native QThread.finished; scans join the temperature worker.
- [ ] On hardware, with a 5-10 second temperature polling interval, repeat Goto T and confirm no
  crash, correct latest accepted setpoint, and normal temperature indicator/scan progression.
- [ ] On hardware, check both new manual Home buttons perform actual re-homing (including an
  already-homed axis), update Curr. Pos., and remain disabled during scanning.
- [ ] Window-close/application-exit thread cleanup remains a separate outstanding issue; this
  change addresses the reported Goto T crash path only.

## v3.9 - Local simplification - VERIFIED with simulated instruments

Current OPTP entry point: OPTP_system_iTC_v3.9.py with OPTP_iTC_main_v3.9.ui. v3.8 is preserved.
The update combines repetitive display code, removes the redundant movement-result wrapper and unused
imports/obsolete commented examples, and reduces duplicate console output. Stage2 manual-move messages
now use mm. Scan/peak/temperature logic, timing settings, instrument connection/cleanup and HDF5/JSON
formats are retained. Only the UI window title changes. JSON schema remains 1 (same fields as v3.8).

Application Python: 4059 -> 3985 lines (-74, including 27 pure-comment and 4 blank lines). Tests and
records are separate. Functional checks: drift 84, failures 30, rotary 20, Lock-in/native UI 52,
JSON/native UI 36 and screenshot/native UI 14; all 236 pass. The comparison test additionally passes
17 checks spanning 7531 input cases and verifies unchanged non-display method structure under the
explicitly allowed simplifications. No real instruments were operated.
- [ ] Run the next ordinary lab scan with v3.9 and confirm normal UI progress, current-angle/repeat
  tracking and saved data. The earlier hardware-check items below also apply to the inherited features.

---

## v3.8 - First sweep after changing angle - IMPLEMENTED, lab check open

With Drift comp. ON, 1D_THz now searches before the first sweep at each changed active rotary angle,
even with Re-peak OFF or Stage2 Repeat = 1. Re-peak controls later same-angle Stage2 repeats. All searches
use the current planned polarization, including calibration angles; the initial search resets to the
first planned angle at each temperature. No extra temperature/soak/beam waits are introduced. Drift OFF
and other scan modes retain their documented behavior. Per-sweep coordinates are saved for angular
tracking even when repeated searches are off. New log events distinguish Angle from Repeat searches.

The previous controller failed 12 of the 17 new angular cases. Updated drift/angle tests pass 84/84,
scan-failure checks 30/30 and selected-axis coupling 20/20; all use simulated instruments. No real hardware
was operated. v3.7 and older files are preserved. Other systems have no applicable enabled OPTP-style
workflow; MO's legacy temperature calibration stays unchanged under the user's earlier MO exclusion.
- [ ] On hardware, run 1D_THz over multiple coupled angles with Stage2 Repeat = 2. Confirm the sequence
  search A -> A1 -> search A -> A2 -> search B -> B1 -> search B -> B2, with each search at that angle.
- [ ] With Re-peak OFF (or Repeat = 1), confirm search before each changed angle and verify corrected
  Stage1/Stage2 values against repeat_scan_positions_mm, including a polarization-cycle restart.

---

## v3.8 - Scan recipe JSON and connection readback - IMPLEMENTED, lab check open

Imp. Conf. / Exp. Conf. restore/save scan inputs, temperature lists and calibration-file references.
JSON format OPTP.scan_config / schema 1 excludes hardware settings and live readouts. Import validates
everything before updating the UI/model with signals blocked. It never connects, moves, heats or sends
instrument settings; scan-time import is disabled. Export is available during scanning and saves current
UI positions, including re-peak updates. Calibration files must remain accessible when importing.

Conn. Instr. now queries SENS?, OFLT? and PHAS? on each selected SR830, including already-connected
devices. Display updates cannot echo commands. Disconnected defaults stay unchanged; failed reads show
unknown fields. At the user's request, connection preserves the current/imported Wait(ms) and multipliers
rather than recalculating them from the hardware time constant.

Hidden native/fake-instrument checks: JSON configuration 36/36, Lock-in controls/readback 52/52.
Acquisition and peak-search methods are unchanged. Older versions and the other three systems are unchanged.
- [ ] Export a typical lab recipe, change its inputs, then import it and compare stage/rotary settings,
  ordered temperature points, search controls and loaded calibration data before running it.
- [ ] Set different sensitivity, time constant and phase values on the two SR830 panels, connect, and
  confirm both displays match without altering the panels or the configured acquisition waits.

---

## v3.8 - Immediate 1-degree Phase arrows - IMPLEMENTED, lab check open

The new OPTP v3.8 Python/UI pair is copied from v3.7, which remains unchanged. Both Phase controls
show arrows with 1-degree steps; clicks write and read back immediately. Typed decimal edits still
commit on Enter or focus loss, with 0.01-degree precision and the automatic degree suffix. Connection
and programmatic readback do not write settings. Controls remain disabled during scanning.

Only one functional Python line was added, connecting committed value changes to the existing handler.
The Phase/X minimum widths now accommodate native Windows arrow buttons and full numeric values.
Hidden native/fake-instrument checks: test_lockin_controls.py optp --native-preview 45/45;
the unchanged v3.7 also passes its 28/28 non-layout checks. Acquisition methods are identical to v3.7.
- [ ] On each connected SR830, click both Phase arrows and compare the immediate panel/readback
  change with the 1-degree step. Type a decimal and confirm Enter and focus loss both apply it.
  Confirm no setting is sent while typing or merely connecting, including around phase wrapping.

---

## v3.7 - Peak tracking and selected-axis coupling - IMPLEMENTED, lab check open

Drift comp. now enables peak search independently of ScanT. Re-peak controls later Stage2 repeats
in 1D_THz, still under the Drift comp. master switch. A fixed-Stage1 1D_THz scan follows the found
peak directly; Stage2 compensates the actual Stage1 correction, including any removed initial offset.
Other modes retain the scan-window offset. Beam/soak ordering and temperature-observer replacement
are unchanged. With ScanT off, a manual temperature ramp does not block the ordinary scan.

Selected-axis coupled planning is enabled in OPTP v3.7, MO v2.7, Imaging v1.8 and THz Emission v1.6.
Unchecked axes do not constrain coupled point counts and are not moved. Independent scans and older
planner callers retain their previous behavior. MO and the other two systems have no new peak workflow.

Fake-instrument checks: drift 67/67, failures 30/30, coupled scans 20/20 in each system (177/177 total).
The old v3.5 drift suite passes 58/58. Remaining hardware checks:
- [ ] With ScanT off, Drift comp. ON and Re-peak ON, a 1D_THz Stage2 repeat of 3 searches before
  each sweep. Re-peak OFF searches only initially; Drift comp. OFF performs no automatic search.
- [ ] With an intentionally offset fixed iPos1, confirm the acquired 1D_THz target follows the found
  peak and Stage2 follows the full correction with the proper mounting sign. Compare saved
  repeat_scan_positions_mm coordinates with the physical stages and the measured waveform.
- [ ] Confirm ordinary THz_Scan / 2D_THz / POL_2D initial searches keep the intended window offset.
- [ ] On each setup, check Rot1 and Rot2 with matching counts and different angular steps while Rot3
  is unchecked with a different count. Confirm paired positions and no Rot3 movement. Check that
  enabling Rot3 with a mismatched count rejects the plan, and matching counts include all three.

---

## v3.7 - Interface PNG screenshots - IMPLEMENTED and checked without instruments

Current versions are OPTP v3.7, MO v2.7, OPTP Imaging v1.8 and THz Emission v1.6.
Each was copied from its previous Python/UI pair; the prior files are unchanged.
Screenshot is available during/after scans and saves the visible interface beside the current/latest
HDF5 file using the same basename. Repeated clicks replace the PNG; before any scan file exists,
it follows that system's time/mode/suffix naming in the selected data folder. Failed writes retain
the previous PNG. Hidden native Qt checks: `tests/test_ui_screenshot.py`: optp 14/14,
mo/img/thz 12/12 each. Acquisition methods and shared drivers are unchanged.
The pending instrument checks and deferred temperature-thread issue below still apply.

---

## v3.6 - Lock-in X Auto Zero and Phase - IMPLEMENTED, lab check open

The same Lock-in controls are now present in MO v2.6, OPTP Imaging v1.7 and THz Emission v1.5.
The three previous Python/UI versions were preserved. Run the Lock-in hardware checks below on
all four setups. Multiline tips and number-only Phase entry (automatic degree suffix) were checked
with fake VISA and hidden native layouts: optp 32/32; mo/img/thz 31/31 each.
MO scan/peak behavior stays unchanged at the user's request; image peak search stays disabled,
and THz Emission's available modes still do not enter its inherited 1D_THz peak-search branch.

Copied from current v3.5; see `OPTP_dev_log.md`. Fake-instrument/native-layout checks:
`test_lockin_controls.py --native-preview` 30/30, `test_scan_failures.py 3.6` 30/30,
`test_drift_comp.py 3.6` 58/58. Existing v3.5 files and the shared SR830 driver are unchanged.
- [ ] Connect each SR830 with a known phase: its new field matches the panel, without changing phase.
  Enter a decimal phase and compare the panel and returned GUI value, including wrapped values.
- [ ] With a stable baseline, Auto Zero issues X Auto Offset only. Compare the SR830 panel X,
  the refreshed GUI X and the normal `OUTP? 1` readback; confirm the following scan records the
  intended offset reading. No real-hardware check of OUTP vs panel offset semantics has run yet.
- [ ] Confirm noise leaves only a plausible residual and Y/phase/other Lock-in settings are unchanged.
  Check both controls remain disabled during a formal scan and are restored afterwards.

---

## v3.5 - Beam settle and 1D repeat peak search - IMPLEMENTED, lab check open

Implemented 2026-10-03; see `OPTP_dev_log.md`. Fake-instrument checks:
`tests/test_drift_comp.py` 58/58 and `tests/test_scan_failures.py` 30/30.
- [ ] Both beam orders: the configured Beam settle is added in full after temperature stabilization,
  sample soak and Pass; the default adds 5 minutes before the initial peak search at each temperature.
- [ ] 1D_THz temperature scan with Drift comp. and Stage2 repeat 3: Re-peak ON searches before
  repeats 2 and 3 without repeating the waits; OFF searches only once per temperature. Check the
  tracked TDS peak and Stage2 correction against an actual drifting sample.
- [ ] Check per-repeat absolute coordinates in `repeat_scan_positions_mm` when analyzing data
  with re-peaking; the existing iPos1/iPos2 scalars describe the first sweep only.
- [ ] Confirm Stop during repeat search preserves earlier sweeps, closes the file and applies
  end-of-scan AutoBlock. Confirm the Lock-in Realtime buttons remain off after scanning.
- [ ] Check that an invalid scan plan reports its error before changing temperature or beam state;
  valid compensated plans still scan normally. Scan entry now validates repeat counts, polarization
  states and initial travel; shifted linear paths are checked again after each peak search.

Deferred by agreement: old temperature-observer replacement after the 2-second stop wait is
unchanged. A future fix must wait for the old observer to exit safely, without requiring a manual
temperature ramp to finish before an ordinary ScanT-off scan. Use interruptible polling waits and
keep the old observer if it cannot exit within the timeout; stopping this observer must not set the
main scan stop flag. Configuration-only plan validation has now been moved before scan startup.

---

## P0 - v3.3: pump power Record - IMPLEMENTED, lab check open

Recorded and implemented 2026-09-29 (see `OPTP_dev_log.md`, headless test `tests/test_pump_power.py`
48/48; the power meter part also ran against the real PM100D with a fake flip mount). On the lab PC:
- [ ] 2-point temperature scan with AutoBlock + Record: each data file has `pump_power_W`, and it
  matches the pump power shown in the box while the flip mount is on Block.
- [ ] Both beam orders (`Pass -> Soak`, `Soak -> Pass`): the power is read while blocked, then the beam passes.
- [ ] Settle time: after a manual Block, the reading has stopped rising before Record takes it (15 s
  default for the S302C, time constant 3.8 s); adjust `pmSettle` if not.
- [ ] Zero with the flip mount on Pass: the offset (about -0.21 mW at the moment) goes to ~0.
- [ ] Wavelength: the PM config value (default 800 nm) is sent to the meter on every connect; check the
  meter's display shows it, and change the default in the .ui if the pump is not at 800 nm.
- [ ] Power range: pick a fixed range, change the wavelength, and check the meter's own display shows
  the same range as the box.
- [ ] The same power meter features are in MO v2.5, OPTP image v1.6 and THz v1.4 (identical code and
  widgets, tested headless and against the meter): run the checks above there too.

---

## P0 - v3.2: temperature drift shifts the pump-THz delay (stage1 / stage2 coupling) - IMPLEMENTED, lab check open

Recorded 2026-09-28; implemented the same day in v3.2 (see `OPTP_dev_log.md`, headless test
`tests/test_drift_comp.py` 25/25). Still to do on the lab PC:
- [ ] 1D_THz temperature scan (2-3 points): ScanLog shows one `Peak search` line per point with a
  plausible delta; the 1D response onset / peak stays at the same position RELATIVE to each file's
  iPos2 (that is the direct proof that 1:1 Reverse compensation is right).
- [ ] 2D_THz temperature scan: the TDS window follows the peak (peak at the same index in every file).
- [ ] Both beam orders with AutoBlock (`Pass -> Soak`, `Soak -> Pass`): beam state matches.
- [ ] Round-1 window: with a real drift the maximum must not sit on the window edge; widen R1 if it does.

Design record (as implemented):

**Problem.** Stage1 (THz TDS delay) and stage2 (pump delay) are coupled: in this setup, when the
stage1 THz peak position decreases, the stage2 position of the same pump-THz delay increases
(stage2 is mounted in reverse). A temperature change that moves the stage1 peak therefore also
moves the pump-THz time zero on stage2, but the code only ever corrects stage1:
- `1D_THz` + temperature: stage1 is re-peaked before every stage2 sweep (`iPos1`,
  `stage1_pos_sequence[0]`, `dynamic_THz_peak_pos`), but `stage2_pos_sequence` is built once per
  file from the UI `iPos2` and never shifted, so every temperature's 1D trace is offset in pump
  delay by the stage1 drift. Recoverable afterwards only by realigning the traces.
- `2D_THz` + temperature: no peak search at all (gate is `scan_mode == '1D_THz'`). The stage1 window
  and every stage2 point stay where they were set, so each temperature samples different pump-THz
  delays. With sparse stage2 points this cannot be interpolated back.
- Size of the effect: the peak search was designed for drifts up to ~90 um. With double-pass
  stages 5 um = 33 fs; the measured response (2026-09-28, 12h55m29s) has FWHM ~42 um and changes by
  ~11-13 % of the peak per 5 um around +0.3 ps. A few um of uncompensated drift already fakes a
  "temperature dependence" of that size.

**Physics (confirmed by the user, 2026-09-28):** the drift comes from thermal expansion of the
sample holder / sample, which changes the collinear THz and pump paths together; the probe (gate)
path is stable. So the drift itself does not change the pump-THz delay at the sample. What does
change it is the stage1 correction: stage1 is coupled to the pump-THz delay, so moving stage1 by
delta to re-peak must be undone by moving stage2 by s * delta (s = -1, stage2 mounted in reverse).
1:1 in mm holds as long as both delay lines have the same number of passes.

**Agreed plan (v3.2, first version):**
- Peak search tab (`peakSearchTab`): `TDS Ppos` (editable), Round1 step + +/- points, Round2 step +
  +/- points, stage2 direction button (Forward / Reverse, default Reverse); tooltips on all.
  `TDS Ppos` is set by hand (from the manual TDS optimisation) and by the peak search only - no
  automatic write from THz_Scan.
- One rule for EVERY mode whenever the scan is a temperature scan (ScanT + iTC connected + points):
  at every temperature point, with the beam passing (AutoBlock) and all stages at the scan start
  configuration, search around `TDS Ppos`; delta = new_peak - `TDS Ppos`; `iPos1 += delta`,
  `iPos2 += s * delta`, `TDS Ppos = new_peak`; then build the sequences and the data file from these
  values. In 1D_THz / POL_2D `iPos1` is the peak itself, in THz_Scan / 2D_THz it is the window start -
  the same formula covers all modes.
- Stored `iPos1` / `iPos2` are therefore already the compensated values: no offset dataset. The
  per-polarization in-loop search is removed (confirmed by the user); `dynamic_THz_peak_pos` goes
  with it unless a processing script needs it.
- Start of a temperature scan: refuse when `TDS Ppos` is not set; otherwise a confirmation dialog
  shows Ppos / iPos1 / iPos2 / direction / search parameters and the scan starts only on Yes.
- A failed search (no finite reading, or the Round1 maximum on the window edge) keeps the previous
  values, the measurement continues, and ScanLog gets a warning (confirmed by the user).
- Beam timing is a toggle on the Peak search tab: `Pass -> Soak` (default; the soak also absorbs the
  pump heating) or `Soak -> Pass` (for light-sensitive samples). A local flag makes sure the beam
  is passed exactly once before the search on every path (incl. no stabilisation / no soak).
- `Drift comp.` checkbox on the Peak search tab, default on; off = no search, no dialog, no
  compensation (for scans without Stage1 / Lock-in1, or weak signal).

---

## P0 - v2.8 heater / PID on the real instrument - DONE

**2026-09-26: verified on the real iTC by the user - no problems.** Checklist kept below for reference.

The whole v2.8 heater path was verified only against stubs and a fake VISA session. **No
manual-heater command in this project has ever been executed against the real controller**, so the
command form itself is unproven. Do these in order; stop at the first failure.

- [ ] **1. HSET command is accepted at all.** *(highest risk - everything below depends on it)*
  Connect the iTC. Turn Auto PID **off**. Type `40` into `HeaterSetPercent` and press Enter.
  - Pass: terminal prints `MercuryiTC heater output set to 40.00 % successfully.`
  - Fail: `Error setting MercuryiTC heater output: Invalid command` (or `UID not found`). The
    controller rejected `SET:DEV:<temp uid>:TEMP:LOOP:HSET:<percent>`. **Restore the driver from
    `inst_libs/backup_before_hset_fix/`**, then re-check the command form against the Mercury iTC
    manual before trying again. Record the exact rejection string in the dev log.

- [ ] **2. Set value, GUI display and front panel all agree.** This is the defect that started
  v2.8: the old code made the UI a percentage of *voltage* while the instrument uses a percentage
  of *power*, so 50 % in the GUI was 25 % on the panel.
  Set 25 %, 50 %, 75 % in turn and record all three readings each time:

  | Set in GUI | `HeaterBar` shows | iTC front panel shows |
  |---|---|---|
  | 25 % | | |
  | 50 % | | |
  | 75 % | | |

  - Pass: all three columns equal within read-back tolerance.
  - Fail: if the panel is consistently the *square* of the GUI fraction, HSET is not being applied
    and the loop is still running on the old voltage setting - check that Auto PID really is off.

- [ ] **3. Auto PID state is read back on connect.** Leave the iTC in PID mode, close the
  application, reopen it and connect.
  - Pass: terminal prints `MercuryiTC PID loop is currently ON (Auto); Auto PID button synced.`,
    the Auto PID button comes up **pressed** and its LED lit, without the user touching it.
  - Fail: button comes up released while the controller is still regulating - the old behaviour.

- [ ] **4. Manual setting is refused with the right message while Auto PID is on.** Turn Auto PID
  on, then set a heater percentage.
  - Pass: `MercuryiTC is in Auto PID mode - manual heater setting skipped. Turn off Auto PID first.`
  - Fail: `MercuryiTC device not connected.` means an old build is running - that was the original
    v2.8 bug report.

- [ ] **5. Auto PID button never disagrees with the instrument.** Toggle Auto PID on and off a few
  times and confirm the button, its LED and the controller's own display always match. The
  rejection path (button reverts when the instrument refuses) is hard to provoke deliberately;
  checking the normal path is enough unless a mismatch shows up.

---

## P1 - Hardware-verification backlog inherited from v2.4-v2.7

Every one of these is marked *"Not yet exercised against real hardware"* in `OPTP_dev_log.md`.
They are not suspected broken; they have simply never been run for real.

- [ ] **v2.4/2.5 peak tracking** - chart refresh after `processEvents()` was removed. Confirm the
  charts still update smoothly during a scan rather than freezing or tearing. (dev log line ~151)
- [ ] **v2.5 `wait_sample_stable()`** - the 10 min sample soak. Confirm the countdown prints at 5 s
  intervals, the total duration is right, and **Stop is honoured within 5 s** mid-soak. (~line 164)
- [ ] **v2.6 selective "Close Instr."** - untick some instruments, press Close, confirm exactly the
  ticked ones close and the rest stay usable. Then confirm application exit releases everything,
  including unticked-but-connected instruments (no locked ports afterwards). (~line 187)
- [ ] **v2.7 shared-ResourceManager fix** - the original crash report. Take the iTC controller out
  of remote/unlock mode at the front panel, return to the software, exit. Confirm no
  `VI_ERROR_INV_OBJECT`, every instrument closes, and the failure (if any) is reported as a warning
  rather than aborting the shutdown. (~line 199)
- [ ] **v3.0 flip mount / AutoBlock** - only tested against a simulated mount. On the real MFF:
  (a) ~~confirm serial `37872830` connects~~ (connected, 2026-09-26); confirm `FM_Indicate` matches
  the beam - since v3.1 the LED is **lit = pass, off = blocked**;
  (b) confirm which physical position is CH1 and which is CH2, and set `fmPassCh` accordingly;
  (c) run a 2-point temperature scan with AutoBlock on and watch the beam: blocked during every
  ramp + soak, open during each measurement, blocked again at the end; (d) press Stop mid-ramp and
  mid-measurement - the mount must end up blocked both times.
- [ ] **v3.1 ScanLog** - on the lab PC run one real scan (ideally a 2-point temperature scan) and
  check `ScanLog_<date>.txt` appears in the day's data folder with the conditions and events.
- [ ] **Synced systems (MO v2.4, OPTP image v1.4, THz v1.3)** - built and tested headless only. On
  each setup: connect with the panel defaults (must behave like the previous version); confirm the
  flip mount serial - all three default to the OPTP mount `37872830`; run one AutoBlock temperature
  scan and check the beam and `ScanLog_<date>.txt`. Run with the conda env `opto_test` (it has
  pipython for THz; the system Python 3.13 does not). MO: the pass happens before its per-temperature Stage2
  peak calibration - confirm the peak search sees the beam.
- [ ] **v3.1 Instrument Connections tab** - on the lab PC: press Scan devices and check the VISA
  and Kinesis lists show the real instruments; connect everything with the defaults (must behave
  exactly like v3.0); restart and confirm the values come back. Rotary serials were verified by the
  user on 2026-09-26 (open question closed).

---

## P2 - Known code issues, deliberately not fixed

- [ ] **Unchanged axes are re-commanded at every data point (OPTP v3.2, MO v2.4, THz v1.3).**
  `move_active_stages()` calls `move_to()` on every active axis for every point, also when that axis
  does not move (e.g. stage2 during a TDS, the rotaries during a sweep). OPTP image already skips an
  axis within 1e-4 mm of its target. Measure the time per point on the hardware; if it matters, port
  the image system's position check (about 5 lines per axis).
- [ ] **`set_heater_limit()` pumps the Qt event loop while holding the instrument lock.** It calls
  `qwait_time(50)` *inside* its `io_lock` block. `io_lock` is an `RLock`, so a UI action during
  that window re-enters on the same thread without blocking and can interleave VISA traffic.
  `set_heater_percent()` was fixed in v2.8 (the wait sits between two separate lock blocks);
  `set_heater_limit()` was left alone as out of scope. Apply the same shape when convenient.
- [ ] **PID is not reset on shutdown.** The `setup_pid_mode(False)` call in `closeInstruments()` is
  still commented out, so the controller keeps whatever mode the session ended in. Since v2.8 reads
  the state back on connect the UI at least reports it correctly, so this is now a preference
  question - decide whether leaving the heater under PID control after exit is wanted, and record
  the decision either way.
- [ ] **Peak search has no failure detection.** The coarse-to-fine search uses a plain `max()` with
  no test for whether a real peak was found, so a drift beyond the coarse range, or a window
  sitting in noise, silently returns a boundary or random point instead of reporting failure. The
  bracketing / prominence / amplitude-regression criteria ("option B") were designed but deferred
  until live running shows whether they are needed. Revisit after the P1 peak-tracking run.
  (~line 150)
- [ ] **`tests/test_scanlog.py` does not finish on v3.2 / v3.3.** Written for v3.1 (17/17 there). Its
  temperature part stops at the modal 'Drift comp.' confirmation (on by default since v3.2), which
  never closes headless, and 'one peak-tracking summary line' fails (v3.2 log lines differ). Untick
  `driftComp` in its `make_sys()` (as `test_pump_power.py` does), update that check, and point it at
  the current version.

---

## P3 - Housekeeping

- [ ] **The v2.8 stub harness was not kept.** `set_heater_percent`, `setup_pid_mode`,
  `_set_autoPID_button` and `_sync_autoPID_from_instrument` were extracted with `ast` and driven
  through 17 checks, but the script lived in a temp directory and is gone. Earlier entries did the
  same, so this matches existing practice - but if these functions are touched again, consider
  keeping the harness in the repo as a regression test instead of rewriting it each time.
  Since v3.1 regression tests live in `OPTP_System/tests/` (first one: `test_scanlog.py`, headless,
  fake instruments); new harnesses should go there too.
- [ ] **The in-file version list is stale.** The `# region Debugging records` docstring at the top
  of the `.py` still stops at v2.0; v2.5 through v2.8 were only recorded in `OPTP_dev_log.md`.
  Either resume maintaining it or delete it so it stops looking authoritative.

---

## Done - kept for context

- v2.8: `set_heater_percent()` reported `MercuryiTC device not connected.` while connected. Cause
  was a three-condition guard sharing one `else`; Auto PID being on took the connection-error path.
- v2.8: heater percentage was a percentage of voltage, not power - now routed through the loop's
  own HSET command. Driver `set_heater_manual()` had also been addressing the wrong subsystem
  (`HTR:SIG` instead of `TEMP:LOOP`) and had no callers.
- v2.8: Auto PID button could latch into a state the instrument never entered; all three writes now
  go through `_set_autoPID_button()` and the state is read back from the controller on connect.
- v2.8: `OPTP_system_iTC_v2.8.py` now loads `OPTP_iTC_main_v2.8.ui`.
