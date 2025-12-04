from az_shared.az_cmd import execute
from common.shell import Cmd


def set_dynamic_install_without_prompt() -> None:
    execute(Cmd(["az", "config", "set"]).arg("extension.use_dynamic_install=yes_without_prompt"))
