from gsuid_core.utils.database.startup import exec_list

exec_list.extend(
    [
        "ALTER TABLE steamidinfo ADD COLUMN steamid64 VARCHAR",
        "ALTER TABLE steamidinfo ADD COLUMN steamuserinfo VARCHAR",
        'ALTER TABLE steambind ADD COLUMN steamid64 VARCHAR',
        'ALTER TABLE steambind ADD COLUMN bot_id VARCHAR',
        'ALTER TABLE steambind ADD COLUMN user_id VARCHAR',
        'ALTER TABLE steambind ADD COLUMN "WS_BOT_ID" VARCHAR',
        'ALTER TABLE steambind ADD COLUMN group_id VARCHAR',
        'ALTER TABLE steambind ADD COLUMN bot_self_id VARCHAR',
        'ALTER TABLE steambind ADD COLUMN user_type VARCHAR',
        'ALTER TABLE steambind ADD COLUMN push_start_game BOOLEAN DEFAULT 1',
        'ALTER TABLE steambind ADD COLUMN push_end_game BOOLEAN DEFAULT 1',
        'ALTER TABLE steambind ADD COLUMN push_archivement BOOLEAN DEFAULT 1',
        'ALTER TABLE steambind ADD COLUMN is_main_id BOOLEAN DEFAULT 0',
    ]
)
