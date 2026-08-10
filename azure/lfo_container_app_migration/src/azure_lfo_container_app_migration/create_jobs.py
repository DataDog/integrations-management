
from .steps import Step

from az_shared.errors import ResourceNotFoundError
from az_shared.execute_cmd import execute
from azure_logging_install.az_cmd import AzCmd


def job_exists(subscription_id: str, resource_group: str, job_name: str) -> bool:
    try:
        execute(
            AzCmd("containerapp", "job show")
            .param("--name", job_name)
            .param("--resource-group", resource_group)
            .param("--subscription", subscription_id)
        )
        return True
    except ResourceNotFoundError:
        return False


class CreateContainerAppJob(Step):
    subscription_id: str
    resource_group: str
    env_name: str
    job_name: str

    secret_refs: list[str]
    env_vars: list[str]

    def __init__(self, subscription_id: str, resource_group: str, env_name: str, job_name: str, secret_refs: list[str], env_vars: list[str]):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.env_name = env_name
        self.job_name = job_name

        self.secret_refs = secret_refs
        self.env_vars = env_vars

        super().__init__(f"create_{self.job_name}")

    def execute(self) -> None:
        if job_exists(self.subscription_id, self.resource_group, self.job_name):
            return

        # if not exists, create it
        pass

    def rollback(self) -> None:
        if not job_exists(self.subscription_id, self.resource_group, self.job_name):
            return
        # check if CAJ already exists

        # if exists, delete it
        pass