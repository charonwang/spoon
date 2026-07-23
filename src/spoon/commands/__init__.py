from . import (
    action_cmd,
    adopt_plan_cmd,
    archive_cmd,
    board_cmd,
    config_cmd,
    export_cmd,
    handoff_cmd,
    init_cmd,
    prompts_cmd,
    run_cmd,
    skills_cmd,
    snapshot_cmd,
)

COMMAND_MODULES = [
    init_cmd,
    snapshot_cmd,
    adopt_plan_cmd,
    prompts_cmd,
    board_cmd,
    handoff_cmd,
    archive_cmd,
    run_cmd,
    action_cmd,
    export_cmd,
    skills_cmd,
    config_cmd,
]
