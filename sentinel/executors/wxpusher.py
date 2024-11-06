from typing import Optional, List, Union
from wxpusher import WxPusher

from ..core.base import Executor
from ..core.events import Action
from ..logger import logger

class WxPusherExecutor(Executor):
    __component_name__ = "wxpusher"

    def __init__(
        self, 
        app_token: str, 
        uids: Union[str, List[str]],
        default_summary: Optional[str] = None
    ):
        """
        初始化 WxPusher 执行器

        Args:
            app_token: WxPusher 应用的 APP_TOKEN
            uids: 接收消息的用户 ID 或 ID 列表
            default_summary: 默认消息摘要
        """
        super().__init__()
        self.app_token = app_token
        self.uids = [uids] if isinstance(uids, str) else uids
        logger.info(f"WxPusher uids: {self.uids} {self.app_token}")
        self.default_summary = default_summary or "新消息通知"

    async def execute(self, action: Action) -> bool:
        """
        执行消息推送动作

        Args:
            action: 包含消息内容的动作对象

        Returns:
            bool: 发送是否成功
        """
        try:
            message = self._format_message(action)
            
            result = WxPusher.send_message(
                content=message,
                uids=self.uids,
                token=self.app_token,
            )
            
            if result.get('success', False):
                logger.info(f"Successfully sent message to WxPusher: {message[:100]}...")
                return True
            else:
                logger.error(f"Failed to send message to WxPusher: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message to WxPusher: {e}")
            return False

    def _format_message(self, action: Action) -> str:
        """
        格式化消息内容

        Args:
            action: 动作对象

        Returns:
            str: 格式化后的消息
        """
        return action.model_dump_json()
