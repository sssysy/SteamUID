from gsuid_core.sv import Plugins

from .utils.register import register_backup_hints

Plugins(
    name="SteamUID",
    force_prefix=["steam"],
    allow_empty_prefix=False,
)

register_backup_hints()
