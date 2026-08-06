from __future__ import annotations

from typing import Iterable, Sequence

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
