from __future__ import annotations

from typing import Optional, Literal, Tuple, Dict
import time

import pyvisa

# Thorlabs vendor ID + PM100D product ID; USB only, so listing does not probe the serial/GPIB ports.
PM100D_RESOURCE_QUERY = "USB?*::0x1313::0x8078::?*::INSTR"

MeasurementMode = Literal[
    "POW", "CURR", "VOLT", "ENER", "FREQ", "PDEN", "EDEN", "RES", "TEMP"
]
DeltaMode = Literal["POW", "CURR", "VOLT", "ENER"]
AdapterType = Literal["PHOT", "THER", "PYRO"]
PowerUnit = Literal["W", "DBM"]
StatusGroup = Literal["MEAS", "AUX", "OPER", "QUES"]


class PM100DError(Exception):
    pass


class PM100D:
    """
    Thorlabs PM100D power/energy meter (SCPI over VISA).
    The meter must run on its NI-VISA driver (Thorlabs Power Meter Driver Switcher);
    on the TLPM driver pyvisa does not see it.

    Example:
        pm = PM100D("USB0::0x1313::0x8078::P1234567::INSTR")
        with pm.connect():
            print(pm.idn())
            pm.set_wavelength_nm(1550)
            pm.set_power_unit("W")
            print(pm.measure_power())
    """

    _MEAS_CMDS: Dict[MeasurementMode, str] = {
        "POW": "MEAS:POW?",
        "CURR": "MEAS:CURR?",
        "VOLT": "MEAS:VOLT?",
        "ENER": "MEAS:ENER?",
        "FREQ": "MEAS:FREQ?",
        "PDEN": "MEAS:PDEN?",
        "EDEN": "MEAS:EDEN?",
        "RES": "MEAS:RES?",
        "TEMP": "MEAS:TEMP?",
    }

    _CONF_CMDS: Dict[MeasurementMode, str] = {
        "POW": "CONF:POW",
        "CURR": "CONF:CURR",
        "VOLT": "CONF:VOLT",
        "ENER": "CONF:ENER",
        "FREQ": "CONF:FREQ",
        "PDEN": "CONF:PDEN",
        "EDEN": "CONF:EDEN",
        "RES": "CONF:RES",
        "TEMP": "CONF:TEMP",
    }

    def __init__(
        self,
        resource: str,
        timeout_ms: int = 2000,
        query_delay_s: float = 0.0,
        retry_count: int = 0,
        retry_delay_s: float = 0.2,
    ):
        self.resource = resource
        self.timeout_ms = timeout_ms
        self.query_delay_s = query_delay_s
        self.retry_count = retry_count
        self.retry_delay_s = retry_delay_s
        self._rm: Optional[pyvisa.ResourceManager] = None
        self._inst: Optional[pyvisa.resources.MessageBasedResource] = None

    # ---------- discovery ----------
    @classmethod
    def list_resources(cls) -> Tuple[str, ...]:
        return tuple(pyvisa.ResourceManager().list_resources(PM100D_RESOURCE_QUERY))

    @classmethod
    def list_resources_with_idn(
        cls, timeout_ms: int = 300
    ) -> Tuple[Tuple[str, str], ...]:
        rm = pyvisa.ResourceManager()
        found = []
        for resource in cls.list_resources():
            try:
                inst = rm.open_resource(resource, open_timeout=timeout_ms)
                try:
                    inst.timeout = timeout_ms
                    inst.read_termination = "\n"
                    inst.write_termination = "\n"
                    found.append((resource, inst.query("*IDN?").strip()))
                finally:
                    inst.close()
            except pyvisa.VisaIOError:
                found.append((resource, "<no response>"))
        return tuple(found)

    # ---------- connection ----------
    def open(self) -> str:
        if self._inst is not None:
            return ""
        self._rm = pyvisa.ResourceManager()
        try:
            self._inst = self._rm.open_resource(self.resource)
        except pyvisa.VisaIOError as exc:
            self._rm = None
            if exc.error_code == pyvisa.constants.StatusCode.error_resource_busy:
                raise PM100DError(
                    "PM100D is busy. Close any Thorlabs power-meter software, NI MAX, "
                    "or other process using the device, then reconnect its USB cable."
                ) from exc
            raise PM100DError(
                f"Opening {self.resource} failed: {exc}. If the meter runs on its TLPM driver, "
                "switch it to NI-VISA with the Thorlabs Power Meter Driver Switcher."
            ) from exc
        self._inst.timeout = self.timeout_ms
        self._inst.query_delay = self.query_delay_s
        self._inst.read_termination = "\n"
        self._inst.write_termination = "\n"
        # No device clear here: on this meter the first query after viClear() times out.
        return ""

    def close(self) -> None:
        """Close this instrument's VISA session. The shared ResourceManager stays open (see SR830.close)."""
        try:
            if self._inst is not None:
                self._inst.close()
        finally:
            self._inst = None
            self._rm = None

    def __enter__(self) -> "PM100D":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> "PM100D":
        self.open()
        return self

    # ---------- low-level ----------
    def write(self, cmd: str) -> None:
        if self._inst is None:
            raise PM100DError("Instrument not open. Call open() or use context manager.")
        self._inst.write(cmd)

    def query(self, cmd: str) -> str:
        if self._inst is None:
            raise PM100DError("Instrument not open. Call open() or use context manager.")
        for attempt in range(self.retry_count + 1):
            try:
                return self._inst.query(cmd).strip()
            except pyvisa.VisaIOError:
                if attempt == self.retry_count:
                    raise
                # retried without viClear(): after a clear the next query times out on this meter
                time.sleep(self.retry_delay_s)

    def _query_float(self, cmd: str) -> float:
        return float(self.query(cmd))

    def _query_bool(self, cmd: str) -> bool:
        return bool(int(self.query(cmd)))

    def set_timeout_ms(self, timeout_ms: int) -> None:
        self.timeout_ms = timeout_ms
        if self._inst is not None:
            self._inst.timeout = timeout_ms

    def set_query_delay_s(self, delay_s: float) -> None:
        self.query_delay_s = delay_s
        if self._inst is not None:
            self._inst.query_delay = delay_s

    # ---------- common commands ----------
    def idn(self) -> str:
        return self.query("*IDN?")

    def reset(self) -> None:
        self.write("*RST")

    def clear(self) -> None:
        self.write("*CLS")

    def opc(self) -> None:
        self.write("*OPC")

    def opc_query(self) -> bool:
        return bool(int(self.query("*OPC?")))

    def wait(self) -> None:
        self.write("*WAI")

    def set_event_status_enable(self, value: int) -> None:
        self.write(f"*ESE {value}")

    def get_event_status_enable(self) -> int:
        return int(self.query("*ESE?"))

    def get_event_status_register(self) -> int:
        return int(self.query("*ESR?"))

    def set_service_request_enable(self, value: int) -> None:
        self.write(f"*SRE {value}")

    def get_service_request_enable(self) -> int:
        return int(self.query("*SRE?"))

    def get_status_byte(self) -> int:
        return int(self.query("*STB?"))

    def self_test(self) -> int:
        return int(self.query("*TST?"))

    # ---------- system ----------
    def get_error(self) -> Tuple[int, str]:
        resp = self.query("SYST:ERR?")
        code_str, msg = resp.split(",", 1)
        return int(code_str), msg.strip().strip('"')

    def get_scpi_version(self) -> str:
        return self.query("SYST:VERS?")

    def beep(self) -> None:
        self.write("SYST:BEEP")

    def set_beeper_enabled(self, on: bool) -> None:
        self.write(f"SYST:BEEP:STAT {1 if on else 0}")

    def is_beeper_enabled(self) -> bool:
        return self._query_bool("SYST:BEEP:STAT?")

    def set_time(self, hour: int, minute: int, second: int) -> None:
        self.write(f"SYST:TIME {hour},{minute},{second}")

    def get_time(self) -> Tuple[int, int, int]:
        resp = self.query("SYST:TIME?")
        h, m, s = (int(x) for x in resp.split(","))
        return h, m, s

    def set_date(self, year: int, month: int, day: int) -> None:
        self.write(f"SYST:DATE {year},{month},{day}")

    def get_date(self) -> Tuple[int, int, int]:
        resp = self.query("SYST:DATE?")
        y, m, d = (int(x) for x in resp.split(","))
        return y, m, d

    def set_line_frequency(self, freq_hz: int) -> None:
        if freq_hz not in (50, 60):
            raise ValueError("freq_hz must be 50 or 60.")
        self.write(f"SYST:LFR {freq_hz}")

    def get_line_frequency(self) -> int:
        return int(self.query("SYST:LFR?"))

    def get_sensor_idn(self) -> Dict[str, str]:
        resp = self.query("SYST:SENS:IDN?")
        parts = [p.strip() for p in resp.split(",", 5)]
        if len(parts) != 6:
            raise PM100DError(f"Unexpected sensor IDN format: {resp}")
        name, sn, cal_msg, s_type, subtype, flags = parts
        return {
            "name": name.strip('"'),
            "serial": sn.strip('"'),
            "cal_msg": cal_msg.strip('"'),
            "type": s_type,
            "subtype": subtype,
            "flags": flags,
        }

    # ---------- status ----------
    def status_preset(self) -> None:
        self.write("STAT:PRES")

    def get_status_event(self, group: StatusGroup) -> int:
        return int(self.query(f"STAT:{group}:EVEN?"))

    def get_status_condition(self, group: StatusGroup) -> int:
        return int(self.query(f"STAT:{group}:COND?"))

    def set_status_positive_transition(self, group: StatusGroup, value: int) -> None:
        self.write(f"STAT:{group}:PTR {value}")

    def get_status_positive_transition(self, group: StatusGroup) -> int:
        return int(self.query(f"STAT:{group}:PTR?"))

    def set_status_negative_transition(self, group: StatusGroup, value: int) -> None:
        self.write(f"STAT:{group}:NTR {value}")

    def get_status_negative_transition(self, group: StatusGroup) -> int:
        return int(self.query(f"STAT:{group}:NTR?"))

    def set_status_enable(self, group: StatusGroup, value: int) -> None:
        self.write(f"STAT:{group}:ENAB {value}")

    def get_status_enable(self, group: StatusGroup) -> int:
        return int(self.query(f"STAT:{group}:ENAB?"))

    # ---------- calibration ----------
    def get_calibration_string(self) -> str:
        return self.query("CAL:STR?")

    # ---------- sense / correction ----------
    def set_averaging_count(self, count: int) -> None:
        if count < 1:
            raise ValueError("count must be >= 1")
        self.write(f"SENS:AVER:COUN {count}")

    def get_averaging_count(self) -> int:
        return int(self.query("SENS:AVER:COUN?"))

    def set_attenuation_db(self, db: float) -> None:
        self.write(f"SENS:CORR:LOSS:INP:MAGN {db}")

    def get_attenuation_db(self) -> float:
        return self._query_float("SENS:CORR:LOSS:INP:MAGN?")

    def set_beam_diameter_mm(self, diameter_mm: float) -> None:
        self.write(f"SENS:CORR:BEAM {diameter_mm}")

    def get_beam_diameter_mm(self) -> float:
        return self._query_float("SENS:CORR:BEAM?")

    def set_wavelength_nm(self, wavelength_nm: float) -> None:
        self.write(f"SENS:CORR:WAV {wavelength_nm}")

    def get_wavelength_nm(self) -> float:
        return self._query_float("SENS:CORR:WAV?")

    def zero_initiate(self) -> None:
        self.write("SENS:CORR:COLL:ZERO:INIT")

    def zero_abort(self) -> None:
        self.write("SENS:CORR:COLL:ZERO:ABOR")

    def get_zero_state(self) -> bool:
        return self._query_bool("SENS:CORR:COLL:ZERO:STAT?")

    def get_zero_magnitude(self) -> float:
        return self._query_float("SENS:CORR:COLL:ZERO:MAGN?")

    # ---------- response factors ----------
    def set_photodiode_response_aw(self, response_aw: float) -> None:
        self.write(f"SENS:CORR:POW:PDI:RESP {response_aw}")

    def get_photodiode_response_aw(self) -> float:
        return self._query_float("SENS:CORR:POW:PDI:RESP?")

    def set_thermopile_response_vw(self, response_vw: float) -> None:
        self.write(f"SENS:CORR:POW:THER:RESP {response_vw}")

    def get_thermopile_response_vw(self) -> float:
        return self._query_float("SENS:CORR:POW:THER:RESP?")

    def set_pyro_response_vj(self, response_vj: float) -> None:
        self.write(f"SENS:CORR:ENER:PYRO:RESP {response_vj}")

    def get_pyro_response_vj(self) -> float:
        return self._query_float("SENS:CORR:ENER:PYRO:RESP?")

    # ---------- ranges / units / delta ----------
    def set_power_unit(self, unit: PowerUnit) -> None:
        self.write(f"SENS:POW:UNIT {unit}")

    def get_power_unit(self) -> str:
        return self.query("SENS:POW:UNIT?")

    def set_power_auto_range(self, on: bool) -> None:
        self.write(f"SENS:POW:RANG:AUTO {1 if on else 0}")

    def get_power_auto_range(self) -> bool:
        return self._query_bool("SENS:POW:RANG:AUTO?")

    def set_power_range_upper(self, value_w: float) -> None:
        self.write(f"SENS:POW:RANG:UPP {value_w}")

    def get_power_range_upper(self) -> float:
        return self._query_float("SENS:POW:RANG:UPP?")

    def set_current_auto_range(self, on: bool) -> None:
        self.write(f"SENS:CURR:RANG:AUTO {1 if on else 0}")

    def get_current_auto_range(self) -> bool:
        return self._query_bool("SENS:CURR:RANG:AUTO?")

    def set_current_range_upper(self, value_a: float) -> None:
        self.write(f"SENS:CURR:RANG:UPP {value_a}")

    def get_current_range_upper(self) -> float:
        return self._query_float("SENS:CURR:RANG:UPP?")

    def set_voltage_auto_range(self, on: bool) -> None:
        self.write(f"SENS:VOLT:RANG:AUTO {1 if on else 0}")

    def get_voltage_auto_range(self) -> bool:
        return self._query_bool("SENS:VOLT:RANG:AUTO?")

    def set_voltage_range_upper(self, value_v: float) -> None:
        self.write(f"SENS:VOLT:RANG:UPP {value_v}")

    def get_voltage_range_upper(self) -> float:
        return self._query_float("SENS:VOLT:RANG:UPP?")

    def set_energy_range_upper(self, value_j: float) -> None:
        self.write(f"SENS:ENER:RANG:UPP {value_j}")

    def get_energy_range_upper(self) -> float:
        return self._query_float("SENS:ENER:RANG:UPP?")

    def set_delta_reference(self, mode: DeltaMode, value: float) -> None:
        self.write(f"SENS:{mode}:REF {value}")

    def get_delta_reference(self, mode: DeltaMode) -> float:
        return self._query_float(f"SENS:{mode}:REF?")

    def set_delta_state(self, mode: DeltaMode, on: bool) -> None:
        self.write(f"SENS:{mode}:REF:STAT {1 if on else 0}")

    def get_delta_state(self, mode: DeltaMode) -> bool:
        return self._query_bool(f"SENS:{mode}:REF:STAT?")

    def get_frequency_range(self) -> Tuple[float, float]:
        low = self._query_float("SENS:FREQ:RANG:LOW?")
        high = self._query_float("SENS:FREQ:RANG:UPP?")
        return low, high

    def set_peak_threshold_percent(self, percent: float) -> None:
        self.write(f"SENS:PEAK:THR {percent}")

    def get_peak_threshold_percent(self) -> float:
        return self._query_float("SENS:PEAK:THR?")

    # ---------- input ----------
    def set_photodiode_lowpass(self, on: bool) -> None:
        self.write(f"INP:PDI:FILT:LPAS:STAT {1 if on else 0}")

    def get_photodiode_lowpass(self) -> bool:
        return self._query_bool("INP:PDI:FILT:LPAS:STAT?")

    def set_thermopile_accelerator(self, on: bool) -> None:
        self.write(f"INP:THER:ACC:STAT {1 if on else 0}")

    def get_thermopile_accelerator(self) -> bool:
        return self._query_bool("INP:THER:ACC:STAT?")

    def set_thermopile_accelerator_auto(self, on: bool) -> None:
        self.write(f"INP:THER:ACC:AUTO {1 if on else 0}")

    def get_thermopile_accelerator_auto(self) -> bool:
        return self._query_bool("INP:THER:ACC:AUTO?")

    def set_thermopile_tau(self, tau_s: float) -> None:
        self.write(f"INP:THER:ACC:TAU {tau_s}")

    def get_thermopile_tau(self) -> float:
        return self._query_float("INP:THER:ACC:TAU?")

    def set_adapter_type(self, adapter: AdapterType) -> None:
        self.write(f"INP:ADAP:TYPE {adapter}")

    def get_adapter_type(self) -> str:
        return self.query("INP:ADAP:TYPE?")

    # ---------- display ----------
    def set_display_brightness(self, value: float) -> None:
        """value: 0 .. 1"""
        self.write(f"DISP:BRIG {value}")

    def get_display_brightness(self) -> float:
        return self._query_float("DISP:BRIG?")

    def set_display_contrast(self, value: float) -> None:
        """value: 0 .. 1"""
        self.write(f"DISP:CONT {value}")

    def get_display_contrast(self) -> float:
        return self._query_float("DISP:CONT?")

    # ---------- measurement ----------
    def configure(self, mode: MeasurementMode) -> None:
        self.write(self._CONF_CMDS[mode])

    def get_configuration(self) -> str:
        return self.query("CONF?")

    def initiate(self) -> None:
        self.write("INIT")

    def abort(self) -> None:
        self.write("ABOR")

    def fetch(self) -> float:
        return self._query_float("FETC?")

    def read(self) -> float:
        return self._query_float("READ?")

    def measure(self, mode: MeasurementMode) -> float:
        return self._query_float(self._MEAS_CMDS[mode])

    def measure_power(self) -> float:
        return self.measure("POW")

    def measure_energy(self) -> float:
        return self.measure("ENER")

    def measure_current(self) -> float:
        return self.measure("CURR")

    def measure_voltage(self) -> float:
        return self.measure("VOLT")

    def measure_frequency(self) -> float:
        return self.measure("FREQ")

    def measure_power_density(self) -> float:
        return self.measure("PDEN")

    def measure_energy_density(self) -> float:
        return self.measure("EDEN")

    def measure_resistance(self) -> float:
        return self.measure("RES")

    def measure_temperature(self) -> float:
        return self.measure("TEMP")
