
from typing import List
from sentinel.core.base import Strategy
from sentinel.core.events import Action, Event


class DummyStrategy(Strategy):
    """Dummy strategy"""
    __component_name__ = "dummy"

    async def process_event(self, event: Event) -> List[Action]:
        return [event]
