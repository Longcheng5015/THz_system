# Backup: thorlabs_PM100D.py before the switch from TLPM to pyvisa

Date: 2026-09-29

`thorlabs_PM100D.py` in this directory is a verbatim copy of the library as it was **before** its
transport was changed from the Thorlabs TLPM DLL (ctypes, `TLPM_64.dll`) to pyvisa / SCPI.

## Why the change was made

The PM100D (P0020951) was switched to its NI-VISA driver with the Thorlabs Power Meter Driver
Switcher, so it can be listed and opened like the other VISA instruments. On the NI-VISA driver the
TLPM DLL no longer finds the meter (it lists `USB0::0x1313::0x8078::::INSTR` without a serial), so
this version cannot connect any more.

It also only worked partly on the TLPM driver: `write()` / `query()` raised on purpose, so every
SCPI method (unit, range, averaging, zeroing, ...) failed; only connect, `idn()`, the wavelength and
`measure_power()` called TLPM directly. See `Polarization_cali/Polarization_cali_dev_log.md` v1.1.4.

## Restoring

Copy the file in this directory back over its original in `inst_libs/`, and switch the meter back to
its TLPM driver with the Power Meter Driver Switcher.
