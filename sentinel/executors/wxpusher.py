"""
WxPusher notification executor

Sends notifications via WxPusher service with:
- Retry mechanism
- Message formatting
- Error handling
- Rate limiting
"""

import asyncio
from datetime import datetime
from typing import List, Optional, Union

from wxpusher import WxPusher

from ..core.actions import Action
from ..core.base import Executor
from ..logger import logger


class WxPusherExecutor(Executor):
    __component_name__ = "wxpusher"

    def __init__(
        self,
        app_token: str,
        uids: Union[str, List[str]],
        default_summary: Optional[str] = None,
        retry_times: int = 3,
        retry_delay: int = 1,
    ):
        """初始化 WxPusher 执行器"""
        super().__init__()

        # 验证必要参数
        if not app_token or len(app_token) < 10:
            raise ValueError("Invalid app_token")

        self.app_token = app_token
        self.uids = [uids] if isinstance(uids, str) else uids

        if not self.uids:
            raise ValueError("At least one uid is required")

        self.default_summary = default_summary or "新消息通知"
        self.retry_times = retry_times
        self.retry_delay = retry_delay

        logger.info(f"Initialized WxPusher executor with {len(self.uids)} recipients")

    async def execute(self, action: Action) -> bool:
        """执行消息推送动作"""
        message = self._format_message(action)

        for attempt in range(self.retry_times):
            try:
                result = await self._send_message(message)
                if result:
                    return True

                logger.warning(
                    f"Failed to send message, attempt {attempt + 1}/{self.retry_times}"
                )
                await asyncio.sleep(self.retry_delay)

            except Exception as e:
                logger.error(f"Error sending message (attempt {attempt + 1}): {str(e)}")
                if attempt < self.retry_times - 1:
                    await asyncio.sleep(self.retry_delay)

        return False

    async def _send_message(self, message: str) -> bool:
        """发送消息的具体实现"""
        try:
            result = WxPusher.send_message(
                content=message,
                uids=self.uids,
                token=self.app_token,
                summary=self.default_summary,
            )

            if result.get("success", False):
                logger.info(f"Successfully sent message: {message[:100]}...")
                return True

            logger.error(f"Failed to send message: {result}")
            return False

        except Exception as e:
            logger.error(f"Error in _send_message: {str(e)}")
            raise

    def _format_message(self, action: Action) -> str:
        """格式化消息内容"""
        try:
            return (
                f"【{self.default_summary}】\n\n"
                f"类型: {action.type}\n"
                f"数据: {action.data}\n"
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            logger.error(f"Error formatting message: {str(e)}")
            return str(action)
