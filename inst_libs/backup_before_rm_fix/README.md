# Backup: instrument libraries before the shared-ResourceManager fix

Date: 2026-08-15

These are verbatim copies of the four instrument libraries as they were **before** removing
`self._rm.close()` from their `close()` methods.

## Why the change was made

`pyvisa.ResourceManager()` is a process-wide singleton - constructing it twice returns the same
object (verified: `pyvisa.ResourceManager() is pyvisa.ResourceManager()` -> True, pyvisa 1.16.2).
Every instrument library therefore held a reference to the *same* manager, and each `close()` did:

    self._inst.close()      # close this instrument's own resource  (correct)
    self._rm.close()        # tear down the SHARED manager           (wrong)

So closing any one instrument invalidated the VISA sessions of all the others. Symptoms:

- `pyvisa.errors.VisaIOError: VI_ERROR_INV_OBJECT` while closing instruments, because
  `rm.close()` walks every resource it created - including ones already dead - and raises on the
  first bad one, leaving the remaining instruments unclosed.
- Selective close ("close only the ticked instruments") could not work: closing one instrument
  silently killed the sessions of the ones the user wanted to keep.

The fix keeps `self._inst.close()` and drops `self._rm.close()`. The manager is left alive for the
lifetime of the process, which is how pyvisa is designed to be used; it is released at interpreter
exit.

## Restoring

Copy the files in this directory back over their originals in `inst_libs/`.
