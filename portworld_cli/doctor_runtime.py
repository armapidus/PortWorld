from __future__ import annotations

# Compatibility facade: keep historical imports stable while
# doctor behavior lives in portworld_cli.services.doctor.service.
from portworld_cli.services.doctor.service import COMMAND_NAME, DoctorOptions, run_doctor

__all__ = ("COMMAND_NAME", "DoctorOptions", "run_doctor")
