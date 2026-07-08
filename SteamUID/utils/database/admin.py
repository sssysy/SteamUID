from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site

from .models import SteamIDInfo, SteamBind, SteamArchivementInfo


@site.register_admin
class SteamIDInfoAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="steamid轮询记录",
        icon="fa fa-database",
    )  # type: ignore

    model = SteamIDInfo


@site.register_admin
class SteamBindAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="steam绑定管理",
        icon="fa fa-database",
    )  # type: ignore

    model = SteamBind


@site.register_admin
class SteamArchivementInfoAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="Steam成就记录",
        icon="fa fa-database",
    )  # type: ignore

    model = SteamArchivementInfo
