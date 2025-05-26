import re
import tomllib
import os
from typing import Dict, Any
import traceback
import asyncio

import aiohttp
from loguru import logger

from WechatAPI import WechatAPIClient
from utils.decorators import on_text_message
from utils.plugin_base import PluginBase


class DouyinParserError(Exception):
    """抖音解析器自定义异常基类"""
    pass


class DouyinParser(PluginBase):
    description = "抖音无水印解析插件"
    author = "ss"
    version = "1.0"

    def __init__(self):
        super().__init__()
        self.url_pattern = re.compile(r'https?://(.*?(xhslink\.com|douyin\.com|kuaishou\.com)/.*)')

        # 读取配置
        config_path = os.path.join(os.path.dirname(__file__), "config.toml")
        try:
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
                
            # 基础配置
            basic_config = config.get("basic", {})
            self.enable = basic_config.get("enable", True)
            self.is_auto_parse = basic_config.get("is_auto_parse", True)
            self.is_auto_pack = basic_config.get("is_auto_pack", True)
            self.http_proxy = basic_config.get("http_proxy", None)
            
        except (OSError, tomllib.TOMLDecodeError) as e:
            logger.error(f"加载抖音解析器配置文件失败: {str(e)}")
            self.enable = True
            self.is_auto_parse = True
            self.is_auto_pack = True
            self.http_proxy = None

        logger.debug("[抖音] 插件初始化完成，配置：自动解析={}, 自动打包={}, 代理={}", 
                     self.is_auto_parse, self.is_auto_pack, self.http_proxy)

    @on_text_message(priority=80)
    async def handle_douyin_links(self, bot: WechatAPIClient, message: dict):
        if not self.enable:
            return True

        content = message['Content']
        sender = message['SenderWxid']
        chat_id = message['FromWxid']

        # 检查是否是手动解析命令
        if content.startswith("抖音解析"):
            url_match = self.url_pattern.search(content)
            if not url_match:
                await bot.send_text_message(
                    wxid=chat_id,
                    content="请在命令后附带抖音链接",
                    at=[sender] if message['IsGroup'] else None
                )
                return
            url = url_match.group(0)
        # 自动解析模式
        elif self.is_auto_parse:
            url_match = self.url_pattern.search(content)
            if not url_match:
                return
            url = url_match.group(0)
        else:
            return

        try:
            # 解析视频信息
            video_info = await self._parse_douyin(url)
            if not video_info:
                raise DouyinParserError("无法获取视频信息")

            # 获取视频信息
            video_url = video_info.get('video', '')
            title = video_info.get('title', '无标题')
            author = video_info.get('name', '未知作者')
            cover = video_info.get('cover', '')

            if not video_url:
                raise DouyinParserError("无法获取视频地址")

            # 根据配置决定是否打包发送
            if self.is_auto_pack:
                # 发送打包消息
                await bot.send_link_message(
                    wxid=chat_id,
                    url=video_url,
                    title=f"{title[:30]} - {author[:10]}" if author else title[:40],
                    description="点击观看无水印视频",
                    thumb_url=cover
                )
            else:
                # 分开发送文本和视频
                info_text = f"标题：{title}\n作者：{author}"
                await bot.send_text_message(wxid=chat_id, content=info_text)
                await bot.send_video_message(wxid=chat_id, video_url=video_url)

            logger.info(f"已发送解析结果: 标题[{title}] 作者[{author}]")

        except DouyinParserError as e:
            error_msg = str(e) if str(e) else "解析失败"
            logger.error(f"抖音解析失败: {error_msg}")
            if message['IsGroup']:
                await bot.send_text_message(wxid=chat_id, content=f"视频解析失败: {error_msg}\n", at=[sender])
            else:
                await bot.send_text_message(wxid=chat_id, content=f"视频解析失败: {error_msg}")
        except Exception as e:
            error_msg = str(e) if str(e) else "未知错误"
            logger.error(f"抖音解析发生未知错误: {error_msg}")
            if message['IsGroup']:
                await bot.send_text_message(wxid=chat_id, content=f"视频解析失败: {error_msg}\n", at=[sender])
            else:
                await bot.send_text_message(wxid=chat_id, content=f"视频解析失败: {error_msg}")

    async def async_init(self):
        """异步初始化函数"""
        # 可以在这里进行一些异步的初始化操作
        # 比如测试API可用性等
        pass