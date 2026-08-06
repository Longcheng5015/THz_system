from __future__ import annotations
from typing import Tuple, Optional, List
import time     # for sleep delays, if needed, but it's better not to use it in the class, because it can block I/O, especially in GUIs
import pyvisa


class SR830Error(Exception):
    """Generic error for SR830 operations."""
    pass


class SR830:
    """
    Minimal SR830 controller.

    Usage:
        sr = SR830("GPIB0::8::INSTR")
        with sr.connect():
            print(sr.idn())
            sr.set_ref_mode(1)         # 1=internal, 0=external
            sr.set_ref_freq(1000.0)    # 1 kHz
            sr.set_phase(0.0)
            sr.set_sensitivity(10)     # index 10 (5 µV/pA)
            sr.set_time_constant(12)   # index 12 (10 s)
            x = sr.get_x()
            y = sr.get_y()
            r = sr.get_r()
            th = sr.get_theta()
            print(x, y, r, th)
    """

    # Sensitivity (index -> value in V/A-like units; see manual SENS)
    _SENS_VALUES_V = [
        2e-9, 5e-9, 1e-8, 2e-8, 5e-8, 1e-7, 2e-7, 5e-7,
        1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5,
        1e-4, 2e-4, 5e-4, 1e-3, 2e-3, 5e-3,
        1e-2, 2e-2, 5e-2, 1e-1, 2e-1, 5e-1, 1.0
    ]  # len = 27, indices 0..26

    # Time constants (index -> seconds) for OFLT
    _TC_VALUES_S = [
        10e-6, 30e-6, 100e-6, 300e-6,
        1e-3, 3e-3, 10e-3, 30e-3,
        100e-3, 300e-3, 1.0, 3.0,
        10.0, 30.0, 100.0, 300.0,
        1000.0, 3000.0, 10000.0, 30000.0
    ]  # indices 0..19

    # Sample rates (index -> Hz or "Trigger")
    _SRAT = {
        0: 0.0625, 1: 0.125, 2: 0.25, 3: 0.5,
        4: 1, 5: 2, 6: 4, 7: 8,
        8: 16, 9: 32, 10: 64, 11: 128,
        12: 256, 13: 512, 14: "Trigger"
    }

    def __init__(self, resource: str, timeout_ms: int = 1000):
        """
        Create a controller.
        :param resource: VISA resource string (e.g., "GPIB0::8::INSTR")
        :param timeout_ms: VISA I/O timeout in milliseconds
        """
        self._rm: Optional[pyvisa.ResourceManager] = None  
        self._inst: Optional[pyvisa.resources.MessageBasedResource] = None
        self.resource = resource   
        self.timeout_ms = timeout_ms

    # ----------------------- connection helpers -----------------------

    def open(self) -> str:   
        """Open VISA session."""
        if self._inst is not None:
            return
        
        try:
            self._rm = pyvisa.ResourceManager()
            self._inst = self._rm.open_resource(self.resource)
            self._inst.timeout = self.timeout_ms
            
            # set termination characters
            self._inst.read_termination = "\n"
            self._inst.write_termination = "\n"
            
            # clear I/O buffers
            self._inst.clear()

            #self._inst.write("OUTX 1")  # Recommended by manual: direct responses to active interface (GPIB=1, RS232=0)
            return ""

        except Exception as e:
            return str(e)

        # Recommended by manual: direct responses to active interface (GPIB=1, RS232=0)
        # We don't force-set OUTX here to avoid side effects; queries work on current interface. OUTX 0: RS232, 1: GPIB

    def close(self) -> None:
        """Close VISA session."""
        try:
            if self._inst is not None:
                self._inst.close()
        finally:
            self._inst = None
            if self._rm is not None:
                self._rm.close()
                self._rm = None

    def __enter__(self) -> "SR830":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # Convenient context method
    def connect(self) -> "SR830": 
        """Alias to allow `with sr.connect(): ...` usage."""
        self.open()
        return self

    # ----------------------- low-level I/O -----------------------

    def write(self, cmd: str) -> None:
        if self._inst is None:
            raise SR830Error("Instrument not open. Call open() or use context manager.")
        self._inst.write(cmd)

    def query(self, cmd: str) -> str:
        if self._inst is None:
            raise SR830Error("Instrument not open. Call open() or use context manager.")
        return self._inst.query(cmd).strip()

    # ----------------------- identification -----------------------

    def idn(self) -> str:
        """Return *IDN? string."""
        try:
            return self.query("*IDN?")
        except Exception as e:
            raise SR830Error(f"Failed to query *IDN?: {e}")

    def check_is_sr830(self) -> bool:
        """Quick check for expected IDN substring."""
        return "SR830" in self.idn()

    # ----------------------- basic getters -----------------------

    def get_x(self) -> float:
        return float(self.query("OUTP? 1"))

    def get_y(self) -> float:
        return float(self.query("OUTP? 2"))

    def get_r(self) -> float:
        return float(self.query("OUTP?3 "))

    def get_theta(self) -> float:
        return float(self.query("OUTP? 4"))

    def snap(self, *params: int) -> List[float]:
        """
        SNAP? read multiple values simultaneously.
        Allowed params: 1=X, 2=Y, 3=R, 4=θ, 5..8=Aux 1..4, 9=Ref Freq, 10=CH1 display, 11=CH2 display
        """
        if not (2 <= len(params) <= 6):
            raise ValueError("SNAP requires 2..6 parameters")
        if any(p not in range(1, 12) for p in params):
            raise ValueError("SNAP parameters must be in 1..11")
        resp = self.query("SNAP? " + ",".join(str(p) for p in params))
        return [float(x) for x in resp.split(",")]

    # ----------------------- reference settings -----------------------

    def set_ref_mode(self, mode: int) -> None:
        """FMOD i: 1=internal, 0=external"""
        if mode not in (0, 1):
            raise ValueError("ref mode must be 0 (external) or 1 (internal)")
        self.write(f"FMOD {mode}")

    def get_ref_mode(self) -> int:
        return int(self.query("FMOD?"))

    def set_ref_freq(self, freq_hz: float) -> None:
        """FREQ f (internal reference only)."""
        self.write(f"FREQ {freq_hz}")

    def get_ref_freq(self) -> float:
        return float(self.query("FREQ?"))

    def set_phase(self, deg: float) -> None:
        """PHAS x: set phase shift (deg)."""
        self.write(f"PHAS {deg}")

    def get_phase(self) -> float:
        return float(self.query("PHAS?"))

    # ----------------------- sensitivity / reserve -----------------------

    def set_sensitivity(self, index: int) -> None:
        """SENS i: 0..26"""
        if not (0 <= index <= 26):
            raise ValueError("sensitivity index must be 0..26")
        self.write(f"SENS {index}")

    def get_sensitivity_index(self) -> int:
        return int(self.query("SENS?"))

    def get_sensitivity_volts(self) -> float:
        """Return sensitivity full-scale in Volts using lookup."""
        idx = self.get_sensitivity_index()
        return self._SENS_VALUES_V[idx]

    def set_reserve(self, mode: int) -> None:
        """RMOD i: 0=High Reserve, 1=Normal, 2=Low Noise"""
        if mode not in (0, 1, 2):
            raise ValueError("reserve must be 0,1,2")
        self.write(f"RMOD {mode}")

    def get_reserve(self) -> int:
        return int(self.query("RMOD?"))

    # ----------------------- time constant / filtering -----------------------

    def set_time_constant(self, index: int) -> None:
        """OFLT i: 0..19"""
        if not (0 <= index <= 19):
            raise ValueError("time constant index must be 0..19")
        self.write(f"OFLT {index}")

    def get_time_constant_index(self) -> int:
        return int(self.query("OFLT?"))

    def get_time_constant_seconds(self) -> float:
        return self._TC_VALUES_S[self.get_time_constant_index()]

    def set_filter_slope(self, db_per_oct_index: int) -> None:
        """OFSL i: 0=6, 1=12, 2=18, 3=24 dB/oct."""
        if db_per_oct_index not in (0, 1, 2, 3):
            raise ValueError("slope index must be 0..3")
        self.write(f"OFSL {db_per_oct_index}")

    def get_filter_slope(self) -> int:
        return int(self.query("OFSL?"))

    def set_sync_filter(self, on: bool) -> None:
        """SYNC i: 0=Off, 1=On (below 200 Hz)."""
        self.write(f"SYNC {1 if on else 0}")

    def get_sync_filter(self) -> int:
        return int(self.query("SYNC?"))

    # ----------------------- autos / handy ops -----------------------

    def auto_phase(self) -> None:
        """APHS"""
        self.write("APHS")

    def auto_gain(self) -> None:
        """AGAN (ignored if time constant > 1 s)"""
        self.write("AGAN")

    def auto_offset(self, which: int) -> None:
        """AOFF i, where i=1(X),2(Y),3(R)"""
        if which not in (1, 2, 3):
            raise ValueError("which must be 1(X), 2(Y) or 3(R)")
        self.write(f"AOFF {which}")

    # ----------------------- display / outputs -----------------------

    def set_display(self, ch: int, item_index: int, ratio_index: int = 0) -> None:
        """
        DDEF i,j,k
          i: 1=CH1, 2=CH2
          j: CH1: 0=X,1=R,2=X Noise,3=Aux1,4=Aux2
             CH2: 0=Y,1=θ,2=Y Noise,3=Aux3,4=Aux4
          k: 0=None, 1=Aux1/3, 2=Aux2/4
        """
        if ch not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        self.write(f"DDEF {ch},{item_index},{ratio_index}")

    def get_display(self, ch: int) -> Tuple[int, int]:
        """Return (j, k)."""
        if ch not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        j, k = self.query(f"DDEF? {ch}").split(",")
        return int(j), int(k)

    def get_display_value(self, ch: int) -> float:
        """OUTR? i -> float; i=1 (CH1) or 2 (CH2)"""
        if ch not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        return float(self.query(f"OUTR?{ch}"))

    # ----------------------- data buffer -----------------------

    def set_sample_rate(self, index: int) -> None:
        """SRAT i: 0..14 (14=Trigger)"""
        if index not in self._SRAT:
            raise ValueError("invalid sample rate index 0..14")
        self.write(f"SRAT {index}")

    def get_sample_rate_index(self) -> int:
        return int(self.query("SRAT?"))

    def get_sample_rate(self):
        """Return numeric Hz or 'Trigger' for current SRAT."""
        idx = self.get_sample_rate_index()
        return self._SRAT[idx]

    def set_eob_mode(self, loop: bool) -> None:
        """SEND i: 0=One Shot, 1=Loop"""
        self.write(f"SEND {1 if loop else 0}")

    def get_eob_mode(self) -> int:
        return int(self.query("SEND?"))

    def start_storage(self) -> None:
        """STRT: start/resume storage."""
        self.write("STRT")

    def pause_storage(self) -> None:
        """PAUS: pause storage."""
        self.write("PAUS")

    def reset_buffers(self) -> None:
        """REST: clear X/Y buffers."""
        self.write("REST")

    def get_buffer_count(self) -> int:
        """SPTS? -> number of stored points (same for both channels)."""
        return int(self.query("SPTS?"))

    def read_trace(self, ch: int, start: int, length: int) -> List[float]:
        """
        TRCA? i, m, n
          i: 1=CH1, 2=CH2
          m: start index (0..N-1)
          n: number of points to read (1..)
        Returns a list of floats.
        """
        if ch not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        resp = self.query(f"TRCA? {ch},{start},{length}")
        return [float(x) for x in resp.split(",") if x]

    # ----------------------- misc -----------------------

    def trigger(self) -> None:
        """TRIG: software trigger."""
        self.write("TRIG")

    def reset(self) -> None:
        """*RST: reset instrument to defaults."""
        self.write("*RST")

    def clear_status(self) -> None:
        """*CLS: clear status."""
        self.write("*CLS")

    # ----------------------- get labels for multiple paras -----------------------
    @staticmethod
    def get_sensitivity_labels():
        """Return list of sensitivity labels for UI display."""
        labels = []
        for i, val in enumerate(SR830._SENS_VALUES_V):
            if val >= 1.0:
                label = f"{val:.0f} V µA"
            elif val >= 1e-3:
                label = f"{val*1e3:.0f} mV nA"
            elif val >= 1e-6:
                label = f"{val*1e6:.0f} µV pA"
            else:
                label = f"{val*1e9:.1f} nV fA"
            labels.append(label)
        return labels
    
    @staticmethod
    def get_time_constant_labels():
        """Return list of time constant labels for UI display."""
        labels = []
        for i, val in enumerate(SR830._TC_VALUES_S):
            if val >= 1.0:
                if val >= 1000:
                    label = f"{val/1000:.0f} ks"
                else:
                    label = f"{val:.0f} s"
            elif val >= 1e-3:
                label = f"{val*1e3:.0f} ms"
            else:
                label = f"{val*1e6:.0f} µs"
            labels.append(label)
        return labels