# Backup: Oxford_mercuryiTC_Thread.py before the HSET / loop-percentage fix

Date: 2026-08-28

This is a verbatim copy of `Oxford_mercuryiTC_Thread.py` as it was **before** correcting
`set_heater_manual()` and adding `get_heater_manual()` / `get_pid_control_state()`.

## Why the change was made

Reported from OPTP_System v2.8: the heater percentage set in the GUI did not match the percentage
displayed - "it showed about half".

The GUI was not using a percentage command at all. It converted the UI percentage to a voltage
(`V = percent/100 x VLIM`) and wrote `HTR:SIG:VOLT`, then derived the displayed percentage by
inverting the same linear formula. Set and display therefore agreed with *each other* but not with
the controller: heater power scales as `V^2/R`, so a UI setting of 50 % drives the heater to
`(0.5)^2 = 25 %` of full power, which is what the front panel reports.

The driver did have a percentage command, `set_heater_manual()`, but it was addressed wrongly and
had never been called:

    SET:DEV:<uid>:HTR:SIG:HSET:<percent>      # wrong - heater device path, heater UID
    SET:DEV:<temp_uid>:TEMP:LOOP:HSET:<pct>   # correct - loop parameter, temperature sensor UID

HSET is a parameter of the temperature control *loop*, not of the heater device. Every other loop
parameter already in this driver - `TSET`, `P`, `I`, `D`, `ENAB`, `PIDT`, and the heater assignment
in `assign_heater_to_loop()` - uses the `DEV:<temperature uid>:TEMP:LOOP:<param>` form. The old form
mixed the two subsystems.

## What changed

- `set_heater_manual(uid, percent)` -> `set_heater_manual(temp_uid, percent)`, now sending
  `SET:DEV:<temp_uid>:TEMP:LOOP:HSET:<percent>`.
- Added `get_heater_manual(temp_uid)` -> `READ:DEV:<temp_uid>:TEMP:LOOP:HSET`.
- Added `get_pid_control_state(uid)` -> `READ:DEV:<uid>:TEMP:LOOP:ENAB`, so the GUI can read the
  loop state back on connect instead of assuming it.

Nothing else was touched. `set_heater_manual()` had **no callers anywhere in the project** (verified
by grep across all systems) and the other two methods are new, so MO_System and OPTP_image_System
are unaffected by this change.

## Status

The corrected command path has been verified only against a fake VISA session, which confirmed the
literal strings sent and that the responses parse. **It has not yet been executed against the real
instrument** - no manual-heater command in this project ever has. If the controller rejects
`TEMP:LOOP:HSET`, restore from this directory and re-investigate the command form against the
Mercury iTC manual before trying again.

## Restoring

Copy `Oxford_mercuryiTC_Thread.py` from this directory back over the original in `inst_libs/`.
