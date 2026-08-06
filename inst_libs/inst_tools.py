"""
inst_tools.py

This module provides common utilities for instrument control.
Current features:
1. A generic InstrumentTools utility class.
2. VISA resource scanning that lists all currently available instrument resources
   (similar to VISA Resource in NI LabVIEW).
3. Non-intrusive VISA resource info discovery without opening devices.

Design goal:
- This file is a reusable utility library for import/call usage in test programs.
- No one-shot execution entry is provided in this module.

Dependencies:
- pyvisa

Install example:
	pip install pyvisa
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence
import pyvisa


class InstrumentTools:
	"""Generic utility class for instrument devices."""

	
	@staticmethod
	def list_visa_resources(backend: str | None = None) -> List[str]:
		"""
		Get all currently available VISA resources.

		Args:
			backend: Optional PyVISA backend string.
				- None: Use the system default backend.
				- "@py": Use the pyvisa-py backend.

		Returns:
			A list of available VISA resource strings.

		Raises:
			RuntimeError: Raised when the resource manager cannot be initialized
				or when VISA scanning fails.
		"""
		try:
			rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
			resources: Sequence[str] = rm.list_resources()
			return list(resources)
		except Exception as exc:  # pragma: no cover - depends on local VISA runtime
			raise RuntimeError(f"VISA resource scan failed: {exc}") from exc

	@staticmethod
	def print_visa_resources(backend: str | None = None) -> List[str]:
		"""
		Print and return all currently available VISA resources.

		Args:
			backend: Optional PyVISA backend string.

		Returns:
			A list of available VISA resource strings.
		"""
		resources = InstrumentTools.list_visa_resources(backend=backend)

		if resources:
			print("Available VISA resources:")
			for idx, resource in enumerate(resources, start=1):
				print(f"  {idx}. {resource}")
		else:
			print("No VISA resources found.")

		return resources

	@staticmethod
	def list_visa_resource_info(backend: str | None = None) -> List[Dict[str, Any]]:
		"""
		Get non-intrusive VISA resource information for all visible resources.

		This method only queries VISA metadata through list_resources_info() and
		does not open any instrument session.

		Args:
			backend: Optional PyVISA backend string.
				- None: Use the system default backend.
				- "@py": Use the pyvisa-py backend.

		Returns:
			A list of dictionaries, one item per VISA resource. Each item includes:
			- resource: VISA resource string.
			- alias: VISA alias if available.
			- interface_type: Interface type such as usb, gpib, tcpip, asrl.
			- interface_board_number: Interface board number if available.
			- resource_class: VISA resource class.

		Raises:
			RuntimeError: Raised when the resource manager cannot be initialized
				or when VISA metadata scan fails.
		"""
		try:
			rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
			resources_info = rm.list_resources_info()

			result: List[Dict[str, Any]] = []
			for resource_name, info in resources_info.items():
				interface_type = getattr(info, "interface_type", None)
				result.append(
					{
						"resource": resource_name,
						"alias": getattr(info, "alias", None),
						"interface_type": str(interface_type).split(".")[-1].lower()
						if interface_type is not None
						else None,
						"interface_board_number": getattr(info, "interface_board_number", None),
						"resource_class": getattr(info, "resource_class", None),
					}
				)

			return result
		except Exception as exc:  # pragma: no cover - depends on local VISA runtime
			raise RuntimeError(f"VISA metadata scan failed: {exc}") from exc

	@staticmethod
	def print_visa_resource_info(backend: str | None = None) -> List[Dict[str, Any]]:
		"""
		Print and return non-intrusive VISA resource information.

		Args:
			backend: Optional PyVISA backend string.

		Returns:
			A list of VISA resource info dictionaries.
		"""
		info_list = InstrumentTools.list_visa_resource_info(backend=backend)

		if info_list:
			print("Available VISA resources (non-intrusive scan):")
			for idx, item in enumerate(info_list, start=1):
				print(
					f"  {idx}. {item['resource']} | alias={item['alias']} | "
					f"interface={item['interface_type']} | board={item['interface_board_number']} | "
					f"class={item['resource_class']}"
				)
		else:
			print("No VISA resources found.")

		return info_list
