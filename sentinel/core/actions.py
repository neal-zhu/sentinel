from typing import Any, Dict
from pydantic import BaseModel

class Action(BaseModel):
    """动作基类，用于在策略和执行器之间传递数据"""
    type: str
    data: Dict[str, Any]
    
    def __str__(self) -> str:
        """格式化动作内容为字符串"""
        return f"Action(type={self.type}, data={self.data})"

    class Config:
        """Pydantic配置"""
        frozen = True  # 使Action实例不可变
