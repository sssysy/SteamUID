from pathlib import Path

from .downloader import DATA_DIR, CACHE_DIR, IMG_CACHE_DIR

_PLUGIN_NAME = "SteamUID"


def register_backup_hints() -> None:
    """向核心备份管理页面登记插件配置与缓存目录提示。"""
    try:
        from gsuid_core.utils.backup.hints import BackupHintKind, register_backup_path
    except ImportError:
        return

    entries: tuple[tuple[Path, BackupHintKind, str, bool | None], ...] = (
        (DATA_DIR / "config.json", "config", "插件配置", True),
        (DATA_DIR / "bg.jpg", "config", "自定义的背景图片", True),
        (CACHE_DIR, "regenerable", "可删除缓存文件", None),
        (IMG_CACHE_DIR, "regenerable", "可删除缓存文件", None),
    )
    for path, kind, desc, default_selected in entries:
        register_backup_path(
            _PLUGIN_NAME,
            path,
            kind,
            desc,
            default_selected=default_selected,
        )
