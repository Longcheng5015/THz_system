from __future__ import annotations

import itertools
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np


class DataProcess:
	@staticmethod
	def interp_rotary_by_rot2(
		pol_rot2_list: List[float],
		cali_rot2: np.ndarray,
		cali_rot1: np.ndarray,
		cali_rot3: np.ndarray,
	) -> Tuple[List[float], List[float]]:
		"""Interpolate rot1/rot3 from rot2 positions using calibration arrays."""
		pol_rot1_list = np.round(np.interp(pol_rot2_list, cali_rot2, cali_rot1), 2).tolist()
		pol_rot3_list = np.round(np.interp(pol_rot2_list, cali_rot2, cali_rot3), 2).tolist()
		return pol_rot1_list, pol_rot3_list

	@staticmethod
	def validate_scan_repetitions(
		stage1_rep: int,
		stage2_rep: int,
		rotary1_rep: int,
		rotary2_rep: int,
	) -> Dict[str, Any]:
		"""
		Validate repetition constraints used by scan execution logic.

		This method mirrors the same validation rules from the main scan loop:
		1) stage1_rep and stage2_rep cannot both be greater than 1.
		2) rotary1_rep and rotary2_rep cannot both be greater than 1.

		Returns a dictionary for direct integration with existing calling style:
		- is_valid: bool
		- error_msg: str | None
		- pol_rep: int (max(rotary1_rep, rotary2_rep), minimum 1 when valid)
		"""
		if stage1_rep > 1 and stage2_rep > 1:
			return {
				"is_valid": False,
				"error_msg": f"Error: stage1_rep = {stage1_rep} and stage2_rep = {stage2_rep} cannot both be greater than 1.",
				"pol_rep": None,
			}

		if rotary1_rep > 1 and rotary2_rep > 1:
			return {
				"is_valid": False,
				"error_msg": f"Error: rotary1_rep = {rotary1_rep} and rotary2_rep = {rotary2_rep} cannot both be greater than 1.",
				"pol_rep": None,
			}

		pol_rep = max(int(rotary1_rep), int(rotary2_rep), 1)
		return {
			"is_valid": True,
			"error_msg": None,
			"pol_rep": pol_rep,
		}

	@staticmethod
	def decode_scan_indices(
		stage1_flat_idx: int,
		stage2_flat_idx: int,
		pol_flat_idx: int,
		stage1_NO: int,
		stage2_NO: int,
		N_pol: int,
		rotary1_rep: int,
		rotary2_rep: int,
	) -> Dict[str, int]:
		"""
		Decode flattened scan indices to point/repetition indices.

		The main scan loop stores iterator values as flattened indices. This helper
		reproduces the same `divmod` decoding logic and also computes rotary current
		repetition values used by UI displays.

		Returned keys:
		- stage1_rep_idx, stage1_idx
		- stage2_rep_idx, stage2_idx
		- pol_rep_idx, pol_idx
		- rotary1_curr_rep, rotary2_curr_rep
		"""
		stage1_rep_idx, stage1_idx = divmod(stage1_flat_idx, stage1_NO)
		stage2_rep_idx, stage2_idx = divmod(stage2_flat_idx, stage2_NO)
		pol_rep_idx, pol_idx = divmod(pol_flat_idx, N_pol)

		rotary1_curr_rep = pol_rep_idx + 1 if rotary1_rep > 1 else 1
		rotary2_curr_rep = pol_rep_idx + 1 if rotary2_rep > 1 else 1

		return {
			"stage1_rep_idx": stage1_rep_idx,
			"stage1_idx": stage1_idx,
			"stage2_rep_idx": stage2_rep_idx,
			"stage2_idx": stage2_idx,
			"pol_rep_idx": pol_rep_idx,
			"pol_idx": pol_idx,
			"rotary1_curr_rep": rotary1_curr_rep,
			"rotary2_curr_rep": rotary2_curr_rep,
		}

	@staticmethod
	def resolve_rotary_step_indices(
		pol_idx: int,
		rotary1_step_sequence: List[float],
		rotary2_step_sequence: List[float],
		rotary3_step_sequence: List[float],
	) -> Dict[str, int]:
		"""
		Resolve safe step indices for rotary1/2/3 based on current pol_idx.

		This helper keeps the same modulo strategy currently used in the main code
		to avoid out-of-range indexing when `N_pol` is larger than a single rotary
		step sequence length.

		Returned keys:
		- rotary1_idx, rotary2_idx, rotary3_idx
		"""
		rotary1_idx = (pol_idx % len(rotary1_step_sequence)) if len(rotary1_step_sequence) > 0 else 0
		rotary2_idx = (pol_idx % len(rotary2_step_sequence)) if len(rotary2_step_sequence) > 0 else 0
		rotary3_idx = (pol_idx % len(rotary3_step_sequence)) if len(rotary3_step_sequence) > 0 else 0

		return {
			"rotary1_idx": rotary1_idx,
			"rotary2_idx": rotary2_idx,
			"rotary3_idx": rotary3_idx,
		}

	@staticmethod
	def build_temp_sequence(start_T: float, step_T: float, NO_T: int) -> List[float]:
		"""
		Build a temperature sequence using the same variable names as TempPointsManager.

		The sequence rule is identical to main program behavior:
		new_points = [start_T + i * step_T for i in range(NO_T)]
		"""
		if NO_T <= 0:
			return []
		return [start_T + i * step_T for i in range(NO_T)]



	@staticmethod
	def thz_fft_calc(position_mm: np.ndarray, TDS_amplitude: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
		"""
		Compute THz FFT from position-domain TDS data.

		Algorithm (consistent with main program implementation):
		1) Convert stage position (mm) to delay time (ps) using round-trip path.
		2) Ensure time axis is ascending.
		3) Use smallest time interval as uniform step for interpolation.
		4) Run FFT and keep non-negative frequency bins.

		Returns:
		- freq: frequency bins (THz-scale consistent with time_ps unit)
		- amp_FDS: complex FFT amplitude on positive frequency side
		"""
		c = 3e8
		time_ps = 2 * position_mm * 1e-3 / c * 1e12

		if time_ps[0] > time_ps[-1]:
			time_ps = time_ps[::-1]
			TDS_amplitude = TDS_amplitude[::-1]

		time_step_min = np.min(np.abs(np.diff(time_ps)))
		time_step_uniform = np.arange(time_ps.min(), time_ps.max(), time_step_min)
		TDS_amplitude_interp = np.interp(time_step_uniform, time_ps, TDS_amplitude)

		Num_amp = len(TDS_amplitude_interp)
		amp_FDS = np.fft.fft(TDS_amplitude_interp)
		freq = np.fft.fftfreq(Num_amp, time_step_uniform[1] - time_step_uniform[0])

		idx = np.where(freq >= 0)
		return freq[idx], amp_FDS[idx]

class ScanPlanner:
	def generate_position_sequence(self, iPos: float, step_array: np.ndarray) -> Tuple[List[float], List[float], List[int]]:
		"""
		Build position/step/stepNO sequences from iPos and a step_array.

		step_array format should match the main program:
		- row 0: step_sizes
		- row 1: steps_NO
		"""
		position_sequence: List[float] = []
		step_sequence: List[float] = []
		stepNO_sequence: List[int] = []

		if not isinstance(step_array, np.ndarray):
			step_array = np.array(step_array, dtype="f8")

		if step_array.ndim != 2 or step_array.shape[0] < 2:
			raise ValueError("step_array must be a 2D array with at least 2 rows: [step_sizes, steps_NO].")

		num_step_size = step_array.shape[1]

		for step_idx in range(num_step_size):
			step_size = float(step_array[0, step_idx])
			step_NO = int(step_array[1, step_idx])

			# Skip invalid step definitions.
			if step_size == 0 or step_NO == 0:
				continue

			if len(position_sequence) == 0:
				new_positions = iPos + np.arange(step_NO) * step_size
			else:
				new_positions = iPos + (np.arange(step_NO) + 1) * step_size

			new_positions = np.round(new_positions, 3)
			position_sequence.extend(new_positions.tolist())
			step_sequence.extend([step_size] * step_NO)
			current_len = len(stepNO_sequence)
			stepNO_sequence.extend(list(range(current_len + 1, current_len + step_NO + 1)))
			iPos = position_sequence[-1]

		# Fallback to static point if no valid step exists.
		if len(position_sequence) == 0:
			position_sequence = [float(iPos)]
			step_sequence = [0.0]
			stepNO_sequence = [0]

		return position_sequence, step_sequence, stepNO_sequence

	def build_pol_states(
		self,
		iRot1: float,
		iRot2: float,
		iRot3: float,
		rotary1_pos_sequence: List[float],
		rotary2_pos_sequence: List[float],
		rotary3_pos_sequence: List[float],
		rotary1_NO: int,
		rotary2_NO: int,
		rotary3_NO: int,
		polarization_policy: str = "independent",
		pol_cali_mode: bool = False,
		cali_table: Dict[str, Any] | None = None,
	) -> Dict[str, Any]:
		"""
		Build polarization state lists with the same variable naming as the main program.

		polarization_policy:
		- "coupled": build one-to-one coupled rotary states. In calibration mode,
		  rotary2 is the master and rotary1/3 are interpolated from calibration table.
		- "independent": build cartesian-product rotary states (three rotary independent).

		Returns a dict with:
		- pol_rot1_list, pol_rot2_list, pol_rot3_list
		- N_pol
		- manu_cali_active
		- error_msg (None if no error)
		"""
		result: Dict[str, Any] = {
			"pol_rot1_list": [],
			"pol_rot2_list": [],
			"pol_rot3_list": [],
			"N_pol": 0,
			"manu_cali_active": False,
			"error_msg": None,
		}

		policy = str(polarization_policy).strip().lower()
		if policy not in ("coupled", "independent"):
			result["error_msg"] = f"Unknown polarization_policy '{polarization_policy}', fallback to 'independent'."
			policy = "independent"

		manu_cali_active = bool(pol_cali_mode and cali_table)

		if policy == "coupled" and manu_cali_active and cali_table is not None:
			try:
				cali_rot2 = np.array(cali_table.get("rot2_cali", []), dtype=float)
				cali_rot1 = np.array(cali_table.get("rot1_cali", []), dtype=float)
				cali_rot3 = np.array(cali_table.get("rot3_cali", []), dtype=float)
				if cali_rot2.size == 0 or cali_rot1.size == 0 or cali_rot3.size == 0:
					manu_cali_active = False
				else:
					pol_rot2_list = rotary2_pos_sequence if rotary2_NO > 0 else [iRot2]
					pol_rot1_list, pol_rot3_list = DataProcess.interp_rotary_by_rot2(
						pol_rot2_list, cali_rot2, cali_rot1, cali_rot3
					)

					result["pol_rot1_list"] = pol_rot1_list
					result["pol_rot2_list"] = pol_rot2_list
					result["pol_rot3_list"] = pol_rot3_list
					result["N_pol"] = len(pol_rot2_list)
					result["manu_cali_active"] = True
					return result
			except Exception as exc:
				manu_cali_active = False
				result["error_msg"] = f"Calibration parsing failed: {exc}"

		if policy == "coupled":
			rot1_vals = rotary1_pos_sequence if rotary1_NO > 0 else [iRot1]
			rot2_vals = rotary2_pos_sequence if rotary2_NO > 0 else [iRot2]
			rot3_vals = rotary3_pos_sequence if rotary3_NO > 0 else [iRot3]

			if not (len(rot1_vals) == len(rot2_vals) == len(rot3_vals)):
				result["error_msg"] = (
					f"Error: Rotary1, Rotary2 and Rotary3 must have the same number of states in coupled mode. "
					f"Currently: Rotary1 NO={len(rot1_vals)}, Rotary2 NO={len(rot2_vals)}, Rotary3 NO={len(rot3_vals)}."
				)
				return result

			result["pol_rot1_list"] = list(rot1_vals)
			result["pol_rot2_list"] = list(rot2_vals)
			result["pol_rot3_list"] = list(rot3_vals)
			result["N_pol"] = len(rot1_vals)
			result["manu_cali_active"] = False
			return result

		# Auto mode logic (same behavior as the main program).
		rot1_vals = rotary1_pos_sequence if rotary1_NO > 1 else ([rotary1_pos_sequence[0]] if rotary1_NO > 0 else [iRot1])
		rot2_vals = rotary2_pos_sequence if rotary2_NO > 1 else ([rotary2_pos_sequence[0]] if rotary2_NO > 0 else [iRot2])
		rot3_vals = rotary3_pos_sequence if rotary3_NO > 1 else ([rotary3_pos_sequence[0]] if rotary3_NO > 0 else [iRot3])

		pol_rot1_list: List[float] = []
		pol_rot2_list: List[float] = []
		pol_rot3_list: List[float] = []

		for rot3_pos in rot3_vals:
			for rot1_pos in rot1_vals:
				for rot2_pos in rot2_vals:
					pol_rot1_list.append(rot1_pos)
					pol_rot2_list.append(rot2_pos)
					pol_rot3_list.append(rot3_pos)

		result["pol_rot1_list"] = pol_rot1_list
		result["pol_rot2_list"] = pol_rot2_list
		result["pol_rot3_list"] = pol_rot3_list
		result["N_pol"] = len(pol_rot1_list)
		result["manu_cali_active"] = manu_cali_active
		return result

	def build_scan_iterator(
		self,
		scan_mode: str,
		stage1_NO: int,
		stage1_rep: int,
		stage2_NO: int,
		stage2_rep: int,
		N_pol: int,
		pol_rep: int,
	) -> Dict[str, Any]:
		"""
		Build scan_iterator and dimension totals with the same naming used in the main program.

		Returns a dict with:
		- stage1_total, stage2_total, pol_total
		- scan_iterator

		Loop priority rule:
		- POL_2D: stage-first, polarization as innermost (fastest).
		- Others: polarization outermost (slowest), then stage loops inside.
		"""
		stage1_total = stage1_NO * stage1_rep
		stage2_total = stage2_NO * stage2_rep
		pol_total = N_pol * pol_rep

		if scan_mode == "POL_2D":
			scan_iterator = itertools.product(range(stage1_total), range(stage2_total), range(pol_total))
		else:
			# Keep polarization as the outermost (slowest) loop.
			scan_iterator = (
				(x[1], x[2], x[0])
				for x in itertools.product(range(pol_total), range(stage1_total), range(stage2_total))
			)

		return {
			"stage1_total": stage1_total,
			"stage2_total": stage2_total,
			"pol_total": pol_total,
			"scan_iterator": scan_iterator,
		}