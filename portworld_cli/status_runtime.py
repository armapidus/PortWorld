from __future__ import annotations

# Compatibility facade: keep historical imports stable while
# status behavior lives in portworld_cli.services.status.service.
from portworld_cli.services.status.service import COMMAND_NAME, run_status

__all__ = ("COMMAND_NAME", "run_status")
