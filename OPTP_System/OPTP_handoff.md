# OPTP System - Handoff / Outstanding Work

Companion to `OPTP_dev_log.md`. The dev log records **what was changed**; this file records
**what is still open**. Every item here should either get done or get an explicit decision to
drop it - do not let items rot silently.

Last updated: 2026-09-26 (after v3.1)

**Working rules for this folder**
- All `.py` and `.ui` files here are **CRLF throughout**. `sed -i` under MSYS/Git-Bash silently
  rewrites the whole file as LF, turning a two-line change into a whole-file diff. `sed -n 'Np'`
  also strips the CR when printing, so it cannot be used to check line endings - read the file as
  bytes instead. (`.md` files in `inst_libs/backup_*/` are LF; `OPTP_dev_log.md` is CRLF.)
- No feature is complete until `OPTP_dev_log.md` has an entry for it (see `CLAUDE.md`).
- Shared libraries live in `inst_libs/` and are used by MO_System and OPTP_image_System too.
  Back them up to `inst_libs/backup_before_<reason>/` with a README before changing them.

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
- [ ] **v3.1 Instrument Connections tab** - on the lab PC: press Scan devices and check the VISA
  and Kinesis lists show the real instruments; connect everything with the defaults (must behave
  exactly like v3.0); restart and confirm the values come back. Rotary serials were verified by the
  user on 2026-09-26 (open question closed).

---

## P2 - Known code issues, deliberately not fixed

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
