from typing import Any, Dict

from pydantic import BaseModel


class Action(BaseModel):
    """
    Base class for actions that are passed between strategies and executors

    An action represents a task to be performed by executors, such as sending
    notifications, storing data, or making API calls.
    """

    type: str  # Action type identifier
    data: Dict[str, Any]  # Action payload data

    def __str__(self) -> str:
        """
        Format action content as human-readable string

        Returns:
            str: Formatted action information
        """
        return f"Action(type={self.type}, data={self.data})"

    class Config:
        """Pydantic configuration"""

        frozen = True  # Make Action instances immutable
