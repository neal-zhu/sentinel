from telegram import Bot
from telegram.error import TelegramError

from ..core.base import Executor
from ..core.actions import Action
from ..logger import logger

class TelegramExecutor(Executor):
    __component_name__ = "telegram"

    def __init__(self, bot_token: str, chat_id: str):
        """
        初始化 Telegram 执行器
        
        Args:
            bot_token: Telegram Bot Token
            chat_id: 目标聊天 ID
        """
        super().__init__()
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        
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
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info(f"Successfully sent message to Telegram: {message[:100]}...")
            return True
            
        except TelegramError as e:
            logger.error(f"Failed to send message to Telegram: {str(e)}")
            return False
            
    def _format_message(self, action: Action) -> str:
        """
        格式化消息内容
        
        Args:
            action: 动作对象
            
        Returns:
            str: 格式化后的消息
        """
        # 这里可以根据实际需求自定义消息格式
        return f"<b>New Action</b>\n\n{str(action)}"
