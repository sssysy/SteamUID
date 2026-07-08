from gsuid_core.aps import scheduler

from ..SteamConfig import SteamConfig
from . import poll_service


@scheduler.scheduled_job(
    'interval',
    seconds=SteamConfig.get_config("PollInterval").data,
)
async def get_user_Summaries_job():
    await poll_service.poll_and_push_game_status()


@scheduler.scheduled_job(
    'interval',
    seconds=SteamConfig.get_config("ArchivementsPollInterval").data,
)
async def check_archivement():
    await poll_service.poll_and_push_achievements()
