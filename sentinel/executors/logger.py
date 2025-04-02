from ..core.actions import Action
from ..core.base import Executor
from ..logger import logger


class LoggerExecutor(Executor):
    __component_name__ = "logger"

    async def execute(self, action: Action):
        logger.info(f"Executing action: {action}")
