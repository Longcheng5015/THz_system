from __future__ import annotations

from typing import Mapping, Sequence

import h5py


class ScanStorageCore:
    """HDF5 storage helpers for the scan worker; independent of Qt and instruments."""

    LOCKIN_DATASET_NAMES = (
        "lockin1_X",
        "lockin1_Y",
        "lockin2_X",
        "lockin2_Y",
    )

    @classmethod
    def create_lockin_datasets(
        cls,
        h5_file: h5py.File,
        shape: Sequence[int],
    ) -> dict[str, h5py.Dataset]:
        """Create the four standard lock-in datasets with one-point chunks."""
        if len(shape) != 6 or any(int(size) <= 0 for size in shape):
            raise ValueError("Lock-in dataset shape must contain six positive dimensions.")

        dataset_shape = tuple(int(size) for size in shape)
        chunk_shape = (1, 1, 1, 1, 1, 1)
        return {
            name: h5_file.create_dataset(name, shape=dataset_shape, chunks=chunk_shape, dtype="f8")
            for name in cls.LOCKIN_DATASET_NAMES
        }

    @staticmethod
    def write_lockin_point(
        datasets: Mapping[str, h5py.Dataset],
        index: tuple[int, int, int, int, int, int],
        readings: Mapping[str, float],
    ) -> None:
        """Write all lock-in channels at one scan index."""
        for name, dataset in datasets.items():
            if name not in readings:
                raise KeyError(f"Missing reading for dataset '{name}'.")
            dataset[index] = float(readings[name])
