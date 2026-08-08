from __future__ import annotations

from typing import Iterable, Sequence, Dict

import numpy as np


class ScanDataCore:
    """Pure data helpers shared by scan workflows without Qt or hardware dependencies."""

    @staticmethod
    def build_step_array(
        step_sizes: Sequence[float],
        step_counts: Sequence[int],
        *,
        input_unit: str = "mm",
    ) -> np.ndarray:
        """Build the standard two-row scan step array used by ScanPlanner."""
        if len(step_sizes) != len(step_counts):
            raise ValueError("step_sizes and step_counts must have the same length.")

        normalized_unit = input_unit.lower()
        if normalized_unit not in {"mm", "um", "deg"}:
            raise ValueError("input_unit must be 'mm', 'um', or 'deg'.")

        converted_steps = np.asarray(step_sizes, dtype="f8")
        if normalized_unit == "um":
            converted_steps = converted_steps / 1000.0

        counts = np.asarray(step_counts, dtype="i8")
        if np.any(counts < 0):
            raise ValueError("step_counts cannot contain negative values.")

        return np.array([converted_steps, counts], dtype="f8")

    @staticmethod
    def build_peak_tracking_positions(
        center_position_mm: float,
        step_mm: float,
        *,
        points_before_center: int = 10,
        points_after_center: int = 10,
        decimals: int = 3,
    ) -> list[float]:
        """Return a local position window for Stage1 peak tracking."""
        if step_mm <= 0:
            raise ValueError("step_mm must be positive.")
        if points_before_center < 0 or points_after_center < 0:
            raise ValueError("Peak-tracking point counts cannot be negative.")

        offsets = np.arange(-points_before_center, points_after_center, dtype=float) * step_mm
        return np.round(float(center_position_mm) + offsets, decimals).tolist()

    @staticmethod
    def analyze_peak_samples(
        samples: Iterable[tuple[float, Sequence[float]]],
    ) -> dict:
        """Average repeated values per position and return the strongest finite peak."""
        averaged_samples: list[tuple[float, float]] = []
        for position, readings in samples:
            values = np.asarray(list(readings), dtype=float)
            finite_values = values[np.isfinite(values)]
            if finite_values.size == 0:
                continue
            averaged_samples.append((float(position), float(np.mean(finite_values))))

        if not averaged_samples:
            return {
                "status": "failed",
                "max_position": None,
                "max_lockin1X": None,
                "positions": [],
                "lockin1X": [],
            }

        max_position, max_lockin1x = max(averaged_samples, key=lambda item: item[1])
        return {
            "status": "ok",
            "max_position": max_position,
            "max_lockin1X": max_lockin1x,
            "positions": [position for position, _ in averaged_samples],
            "lockin1X": [value for _, value in averaged_samples],
        }

    @staticmethod
    def parse_calibration_file(cali_file_path: str) -> np.ndarray | None:
        """
        Parses calibration files in either CSV or legacy whitespace-separated formats.
        Returns a (N, 4) numpy array of [rot1, rot2, rot3, power], or None if no valid data found.
        """
        rows = []
        if cali_file_path.lower().endswith('.csv'):
            import csv
            with open(cali_file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)  # skip header
                for row in reader:
                    if len(row) < 5:
                        continue
                    try:
                        # format: Point_Idx,Stage1,Stage2,Stage3,Power,Stable
                        rot1_str = row[1].strip()
                        rot2_str = row[2].strip()
                        rot3_str = row[3].strip()
                        power_str = row[4].strip()
                        
                        rot1 = float(rot1_str) if rot1_str else 0.0
                        rot2 = float(rot2_str) if rot2_str else 0.0
                        rot3 = float(rot3_str) if rot3_str else 0.0
                        power = float(power_str) if power_str else 0.0
                        
                        rows.append([rot1, rot2, rot3, power])
                    except ValueError:
                        continue
        else:
            with open(cali_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # skip empty lines and comments starting with '#'
                    if not line or line.startswith('#'):
                        continue
                    
                    parts = line.split()  # split by whitespace
                    if len(parts) < 4:
                        continue  # skip lines with insufficient data
                    
                    try: # incase of non-numeric data, title or non-# comment lines
                        current_row = [float(p) for p in parts[:4]]
                        rows.append(current_row)     
                    except ValueError:
                        continue  # skip lines with non-numeric data

        if not rows:
            return None

        return np.array(rows, dtype=float)

    @staticmethod
    def build_cali_table(
        rot1: np.ndarray,
        rot2: np.ndarray,
        rot3: np.ndarray,
        power: np.ndarray,
        interp_cali_data: bool = False,
    ) -> Dict[str, np.ndarray]:
        """
        Build calibration table from raw rot1/rot2/rot3/power arrays.

        1) Round rot2 to 0.1 degree.
        2) Sort all rows by rot2.
        3) Remove duplicated rot2 entries (keep first occurrence).
        4) Optionally interpolate to a uniform 0.1-degree rot2 grid.

        Returns a dictionary with keys:
        - rot2_cali, rot1_cali, rot3_cali, power_cali
        """
        rot2 = np.round(rot2, 1)
        sort_idx = np.argsort(rot2)

        rot2_sorted = rot2[sort_idx]
        rot1_sorted = rot1[sort_idx]
        rot3_sorted = rot3[sort_idx]
        power_sorted = power[sort_idx]

        rot2_unique, unique_idx = np.unique(rot2_sorted, return_index=True)
        rot1_unique = rot1_sorted[unique_idx]
        rot3_unique = rot3_sorted[unique_idx]
        power_unique = power_sorted[unique_idx]

        if not interp_cali_data:
            return {
                "rot2_cali": rot2_unique,
                "rot1_cali": rot1_unique,
                "rot3_cali": rot3_unique,
                "power_cali": power_unique,
            }

        start = float(rot2_unique.min())
        stop = float(rot2_unique.max())
        n_step = int(np.round((stop - start) / 0.1))
        rot2_grid = start + np.arange(n_step + 1) * 0.1
        rot2_grid = np.round(rot2_grid, 1)

        rot1_interp = np.round(np.interp(rot2_grid, rot2_unique, rot1_unique), 2)
        rot3_interp = np.round(np.interp(rot2_grid, rot2_unique, rot3_unique), 2)
        power_interp = np.round(np.interp(rot2_grid, rot2_unique, power_unique), 3)

        return {
            "rot2_cali": rot2_grid,
            "rot1_cali": rot1_interp,
            "rot3_cali": rot3_interp,
            "power_cali": power_interp,
        }
