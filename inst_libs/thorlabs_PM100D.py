from __future__ import annotations

from ctypes import WinDLL, byref, c_bool, c_double, c_uint32, create_string_buffer
from pathlib import Path
from typing import Optional, Literal, Tuple, Dict
import time

TLPM_DLL_PATH = Path(r"C:\Program Files\IVI Foundation\VISA\Win64\Bin\TLPM_64.dll")
TLPM_BUFFER_SIZE = 1024
VI_ERROR_RSRC_BUSY = -1073807343

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
        self._tlpm = self._load_tlpm()
        self._session: Optional[c_uint32] = None

    @staticmethod
    def _load_tlpm():
        if not TLPM_DLL_PATH.is_file():
            raise PM100DError(
                f"Thorlabs TLPM driver was not found at {TLPM_DLL_PATH}."
            )
        return WinDLL(str(TLPM_DLL_PATH))

    @staticmethod
    def _check_status(status: int, operation: str) -> None:
        if status == VI_ERROR_RSRC_BUSY:
            raise PM100DError(
                "PM100D is busy. Close any Thorlabs power-meter software, NI MAX, "
                "or other process using the device, then reconnect its USB cable."
            )
        if status < 0:
            raise PM100DError(f"{operation} failed with TLPM status {status}.")

    @classmethod
    def _resource_manager(cls):
        tlpm = cls._load_tlpm()
        session = c_uint32()
        # TLPM uses an empty resource name to create a resource-manager session.
        tlpm.TLPM_init(b"", c_bool(False), c_bool(False), byref(session))
        return tlpm, session

    # ---------- discovery ----------
    @classmethod
    def list_resources(cls) -> Tuple[str, ...]:
        tlpm, session = cls._resource_manager()
        count = c_uint32()
        try:
            cls._check_status(tlpm.TLPM_findRsrc(session, byref(count)), "TLPM_findRsrc")
            resources = []
            for index in range(count.value):
                resource = create_string_buffer(TLPM_BUFFER_SIZE)
                cls._check_status(
                    tlpm.TLPM_getRsrcName(session, index, resource),
                    "TLPM_getRsrcName",
                )
                resources.append(resource.value.decode())
            return tuple(resources)
        finally:
            if session.value:
                tlpm.TLPM_close(session)

    @classmethod
    def list_resources_with_idn(
        cls, timeout_ms: int = 300
    ) -> Tuple[Tuple[str, str], ...]:
        del timeout_ms
        return tuple((resource, "Thorlabs PM100D") for resource in cls.list_resources())

    # ---------- connection ----------
    def open(self) -> str:
        if self._session is not None:
            return ""
        session = c_uint32()
        status = self._tlpm.TLPM_init(
            self.resource.encode(), c_bool(True), c_bool(False), byref(session)
        )
        self._check_status(status, f"TLPM_init({self.resource})")
        self._session = session
        return ""

    def close(self) -> None:
        if self._session is not None:
            self._tlpm.TLPM_close(self._session)
            self._session = None

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
        raise PM100DError(
            "Raw SCPI writes are not supported by the TLPM driver transport."
        )

    def query(self, cmd: str) -> str:
        raise PM100DError(
            "Raw SCPI queries are not supported by the TLPM driver transport."
        )

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
        if self._session is None:
            raise PM100DError("Instrument not open. Call open() or use context manager.")
        manufacturer = create_string_buffer(TLPM_BUFFER_SIZE)
        device = create_string_buffer(TLPM_BUFFER_SIZE)
        serial = create_string_buffer(TLPM_BUFFER_SIZE)
        firmware = create_string_buffer(TLPM_BUFFER_SIZE)
        self._check_status(
            self._tlpm.TLPM_identificationQuery(
                self._session, manufacturer, device, serial, firmware
            ),
            "TLPM_identificationQuery",
        )
        return ",".join(
            value.value.decode() for value in (manufacturer, device, serial, firmware)
        )

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
        self.write(f"SYST:LFREQ {freq_hz}")

    def get_line_frequency(self) -> int:
        return int(self.query("SYST:LFREQ?"))

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
        if self._session is None:
            raise PM100DError("Instrument not open. Call open() or use context manager.")
        self._check_status(
            self._tlpm.TLPM_setWavelength(self._session, c_double(wavelength_nm)),
            "TLPM_setWavelength",
        )

    def get_wavelength_nm(self) -> float:
        if self._session is None:
            raise PM100DError("Instrument not open. Call open() or use context manager.")
        wavelength = c_double()
        self._check_status(
            self._tlpm.TLPM_getWavelength(self._session, 0, byref(wavelength)),
            "TLPM_getWavelength",
        )
        return wavelength.value

    def zero_initiate(self) -> None:
        self.write("SENS:ZERO:INIT")

    def zero_abort(self) -> None:
        self.write("SENS:ZERO:ABOR")

    def get_zero_state(self) -> bool:
        return self._query_bool("SENS:ZERO:STAT?")

    def get_zero_magnitude(self) -> float:
        return self._query_float("SENS:ZERO:MAGN?")

    # ---------- response factors ----------
    def set_photodiode_response_aw(self, response_aw: float) -> None:
        self.write(f"SENS:POW:PDIO:RESP {response_aw}")

    def get_photodiode_response_aw(self) -> float:
        return self._query_float("SENS:POW:PDIO:RESP?")

    def set_thermopile_response_vw(self, response_vw: float) -> None:
        self.write(f"SENS:POW:THER:RESP {response_vw}")

    def get_thermopile_response_vw(self) -> float:
        return self._query_float("SENS:POW:THER:RESP?")

    def set_pyro_response_vj(self, response_vj: float) -> None:
        self.write(f"SENS:ENER:PYRO:RESP {response_vj}")

    def get_pyro_response_vj(self) -> float:
        return self._query_float("SENS:ENER:PYRO:RESP?")

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
        self.write(f"SENS:{mode}:STAT {1 if on else 0}")

    def get_delta_state(self, mode: DeltaMode) -> bool:
        return self._query_bool(f"SENS:{mode}:STAT?")

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
        self.write(f"INP:PDIO:FILT:LPAS {1 if on else 0}")

    def get_photodiode_lowpass(self) -> bool:
        return self._query_bool("INP:PDIO:FILT:LPAS?")

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
    def set_display_brightness(self, value: int) -> None:
        self.write(f"DISP:BRIG {value}")

    def get_display_brightness(self) -> int:
        return int(self.query("DISP:BRIG?"))

    def set_display_contrast(self, value: int) -> None:
        self.write(f"DISP:CONT {value}")

    def get_display_contrast(self) -> int:
        return int(self.query("DISP:CONT?"))

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
        if self._session is None:
            raise PM100DError("Instrument not open. Call open() or use context manager.")
        power = c_double()
        self._check_status(
            self._tlpm.TLPM_measPower(self._session, byref(power)),
            "TLPM_measPower",
        )
        return power.value

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
