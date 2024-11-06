from pydantic import BaseModel

class Action(BaseModel):
    type: str
    data: dict
