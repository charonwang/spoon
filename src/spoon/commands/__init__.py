from . import adopt_plan_cmd
from . import action_cmd
from . import archive_cmd
from . import board_cmd
from . import handoff_cmd
from . import init_cmd
from . import prompts_cmd
from . import run_cmd
from . import snapshot_cmd

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
]

