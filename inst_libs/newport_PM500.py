# pm500.py
from __future__ import annotations
from typing import Optional, Literal
import time
import pyvisa

Axis = Literal["X", "Y", "Z", "A", "B", "C"]

class PM500Error(Exception):
    pass

class PM500:
    """
    Minimal Newport PM500-C controller helper (GPIB or RS-232 via PyVISA).

    Example:
        from pm500 import PM500
        pm = PM500("GPIB0::1::INSTR")  # or "ASRL3::INSTR" for RS-232
        with pm.connect():
            print(pm.idn())
            pm.comopt3()                  # recommended for RS-232; can skip for GPIB
            pm.motor_on("X")
            pm.set_high_speed("X", v_mm_s=5.0, accel_mm_s2=50.0, decel_mm_s2=50.0)
            pm.move_abs("X", 12.345)      # absolute move in um
            pm.wait_done("X", timeout=20)  # in seconds
            print("X pos =", pm.read_pos("X"), "um")
    """

    def __init__(self, resource: str, timeout_ms: int = 10000):
        self.resource = resource
        self.timeout_ms = timeout_ms
        self._rm: Optional[pyvisa.ResourceManager] = None
        self._inst: Optional[pyvisa.resources.MessageBasedResource] = None

    # ---------- connection ----------
    def open(self):
        if self._inst:
            return
        self._rm = pyvisa.ResourceManager()
        inst = self._rm.open_resource(self.resource)

        # Common settings:
        # - GPIB usually needs no extra tweaks here.
        # - For RS-232 you may want to configure termination/baud on the VISA resource itself.
        inst.timeout = self.timeout_ms
        
        # set termination characters
        inst.read_termination = "\r\n"
        inst.write_termination = "\r\n"

        # if RS-232, enable echo and 'done' responses for easier parsing
        if "ASRL" in self.resource:
            try:
                inst.write("COMOPT3\r")
            except:
                pass
            
            inst.baud_rate = 19200  # ensure baud rate is set appropriately
            inst.data_bits = 7     # PM500 uses 7 data bits
            inst.parity = pyvisa.constants.Parity.even  # even parity
            inst.stop_bits = pyvisa.constants.StopBits.two  # 2 stop bits
        
        # clear I/O buffers
        try:
            inst.clear()
        except:
            pass

        self._inst = inst

    def close(self):
        """Close this instrument's VISA session.

        The ResourceManager is deliberately NOT closed here. pyvisa.ResourceManager() is a
        process-wide singleton, so every instrument in the application holds the same object;
        closing it would invalidate the sessions of all the other instruments (and raise
        VI_ERROR_INV_OBJECT while walking resources that are already dead). It is released at
        interpreter exit.
        """
        try:
            if self._inst:
                self._inst.close()
        finally:
            self._inst = None
            self._rm = None   # drop our reference only; the shared manager stays alive

    def __enter__(self) -> "PM500":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def connect(self) -> "PM500":
        """Allow `with PM500(...).connect():` usage."""
        self.open()
        return self

    # ---------- low-level ----------
    def write(self, cmd: str):
        if not self._inst:
            raise PM500Error("Not connected")
        self._inst.write(cmd)

    def query(self, cmd: str) -> str:
        if not self._inst:
            raise PM500Error("Not connected")
        return self._inst.query(cmd).strip()

    # ---------- basics / system ----------
    def idn(self) -> str:
        """
        Query firmware/info string. Manual uses `SVN?`.
        """
        try:
            resp = self.query("SVN?")
        except Exception as e:
            raise PM500Error(f"SVN? failed: {e}")
        return resp

    def comopt3(self):
        """
        Recommended on RS-232 after power-up: enable echo and 'done' responses
        to make parsing easier. (GPIB can skip this.)
        """
        self.write("COMOPT3")

    # ---------- status / helpers ----------
    @staticmethod
    def _parse_status_char(s: str) -> Optional[str]:
        """
        STAT? responses often end with a single status letter:
        B=busy, D=done, L=limit, E=error, M=motor off.
        Try to extract that letter from the response.
        """
        for ch in ("B", "D", "L", "E", "M"):
            if s.endswith(ch):
                return ch
        for ch in ("B", "D", "L", "E", "M"):
            if ch in s:
                return ch
        return None

    def stat(self, axis: Axis) -> str:
        resp = self.query(f"{axis}STAT?")
        ch = self._parse_status_char(resp)
        if not ch:
            raise PM500Error(f"Unrecognized STAT response: {resp}")
        return ch

    def wait_done(self, axis: Axis, timeout: float = 45.0, poll: float = 0.05):
        """
        Poll STAT? until 'D' (done) or raise on limit/error/motor-off.
        """
        t0 = time.time()
        last = ""
        while True:
            st = self.stat(axis)
            if st == "D":
                return
            if st in ("L", "E", "M"):
                raise PM500Error(f"Axis {axis} status={st} (L=limit, E=error, M=motor off)")
            if time.time() - t0 > timeout:
                raise PM500Error(f"wait_done timeout; last status={st} (prev={last})")
            last = st
            time.sleep(poll)

    # ---------- motor power ----------
    def motor_on(self, axis: Axis):
        """
        Bring motor online. Some firmware supports M0/M1 for motor power;
        here we try `M0` as a best-effort 'motor on'. Replace with the exact
        command if your unit supports a specific 'motor on' instruction.
        """
        try:
            self.write(f"{axis}M0")
        except Exception:
            pass

    def motor_off(self, axis: Axis):
        """
        Motor off. Many examples use 'M' for motor off at the programming port.
        """
        self.write(f"{axis}M")

    # ---------- Motor auto-zero/Save to NV memory ----------
    def motor_auto_zero(self, axis: Axis):
        """
        AZ: motor auto-zero (set current position as zero).
        """
        self.write(f"{axis}AZ")
        
    def save_to_nvm(self, axis: Axis):  # save calibrated position to non-volatile memory
        """
        Save current position to non-volatile memory.
        """
        self.write(f"{axis}SAVEAX")

    # ---------- homing / reference ----------
    def fiducial_center(self, axis: Axis):
        """
        F0: seek fiducial (reference) to the center (depending on sensor).
        """
        self.write(f"{axis}F0")

    # ---------- motion: absolute / relative ----------
    def move_abs(self, axis: Axis, pos_um: float):
        """G <abs um>: absolute move in um."""
        self.write(f"{axis}G {pos_um}")

    def move_rel(self, axis: Axis, delta_um: float):
        """GR <rel um>: relative move in um (high-speed loop)."""
        self.write(f"{axis}GR {delta_um}")

    def move_rel_low(self, axis: Axis, delta_um: float):
        """LGR <rel µm>: relative move in µm (low-speed loop)."""
        self.write(f"{axis}LGR {delta_um}")

    # ---------- speed loops ----------
    def set_high_speed(self, axis: Axis,
                       v_mm_s: Optional[float] = None,
                       accel_mm_s2: Optional[float] = None,
                       decel_mm_s2: Optional[float] = None):
        """
        High-speed loop parameters:
          V (mm/s), ACCEL (mm/s²), DECEL (mm/s²).
        """
        if v_mm_s is not None:
            self.write(f"{axis}V {v_mm_s}")
        if accel_mm_s2 is not None:
            self.write(f"{axis}ACCEL {accel_mm_s2}")
        if decel_mm_s2 is not None:
            self.write(f"{axis}DECEL {decel_mm_s2}")

    def set_low_speed(self, axis: Axis,
                      v_um_s: Optional[float] = None,
                      accel_um_s2: Optional[float] = None,
                      decel_um_s2: Optional[float] = None):
        """
        Low-speed loop parameters:
          LV (µm/s), LACCEL (µm/s²), LDECEL (µm/s²).
        """
        if v_um_s is not None:
            self.write(f"{axis}LV {v_um_s}")
        if accel_um_s2 is not None:
            self.write(f"{axis}LACCEL {accel_um_s2}")
        if decel_um_s2 is not None:
            self.write(f"{axis}LDECEL {decel_um_s2}")

    def set_low_speed_threshold(self, axis: Axis, lsize_um: float):
        """
        LSIZE <µm>: moves shorter than or equal to this threshold use the low-speed loop.
        """
        self.write(f"{axis}LSIZE {lsize_um}")

    # ---------- position / limits ----------
    def read_pos(self, axis: Axis) -> float:
        """
        R: read current position (um for linear stages, arc-sec for rotary).
        Responses may contain status prefix/suffix; extract the trailing numeric value.
        """
        resp = self.query(f"{axis}R")
        # Extract the last numeric token (simple right-to-left scan).
        for i in range(len(resp)-1, -1, -1):
            if resp[i] in "+-0123456789":
                start = i
                while start > 0 and resp[start-1] in "+-0123456789.":
                    start -= 1
                try:
                    return float(resp[start:])
                except ValueError:
                    break
        raise PM500Error(f"Unrecognized R response: {resp}")

    def set_soft_limits(self, axis: Axis, neg_um: float, pos_um: float):
        """
        Set software limits relative to the fiducial: NSLIM (negative) and PSLIM (positive), in µm.
        """
        self.write(f"{axis}NSLIM {neg_um}")
        self.write(f"{axis}PSLIM {pos_um}")

    # ---------- convenience: init_pos/go and wait ----------
    def init_pos(self, axis: Axis):
        """
        Initialize position to fiducial location.
        And save fiducial center position as zero.
        It is better to wait for `10` seconds after calling this function before any further move commands.
        """
        self.fiducial_center(axis)
    
    def go_and_wait_abs(self, axis: Axis, pos_um: float, timeout: float = 10.0):
        self.move_abs(axis, pos_um)
        self.wait_done(axis, timeout=timeout)

    def go_and_wait_rel(self, axis: Axis, delta_um: float, timeout: float = 10.0):
        self.move_rel(axis, delta_um)
        self.wait_done(axis, timeout=timeout)
        
        
