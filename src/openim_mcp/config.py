"""
配置管理 — 从环境变量读取，支持 .env 文件
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenIM 服务配置
    openim_api_address: str = Field(
        default="http://localhost:10002",
        description="OpenIM API 地址，例如 http://192.168.0.127:10002"
    )
    openim_admin_secret: str = Field(
        default="Pwd1Open2#IMD",
        description="OpenIM 管理员密钥（与 config.yaml 中的 secret 一致）"
    )
    openim_admin_id: str = Field(
        default="imAdmin",
        description="OpenIM 超级管理员 userID"
    )
    # 发送者身份 — 由环境变量统一指定，防止调用方伪造身份
    sender_id: str = Field(
        default="",
        description="发送消息时使用的 senderID（由环境变量 OPENIM_SENDER_ID 指定，MCP 工具不可覆盖）"
    )
    # 平台 ID（5=普通用户端，12=机器人，按实际填写）
    bot_platform_id: int = Field(
        default=5,
        description="发送消息时使用的 senderPlatformID"
    )
    # 安全策略
    allow_private_chat: bool = Field(
        default=False,
        description="是否允许发送私聊消息。默认 false：只允许群聊（session_type=3）"
    )
    allow_create_group: bool = Field(
        default=False,
        description="是否允许创建群组。默认 false，需显式开启"
    )
    allow_send_notification: bool = Field(
        default=False,
        description="是否允许发送业务通知。默认 false，需显式开启"
    )

    # Token 缓存
    token_ttl_seconds: int = Field(
        default=3600,
        description="admin token 缓存时间（秒），到期前 5 分钟自动刷新"
    )

    # 性能配置
    openim_concurrency: int = Field(
        default=50,
        description="并发发送 OpenIM 消息的最大协程数"
    )
    http_timeout: float = Field(
        default=30.0,
        description="HTTP 请求超时（秒）"
    )
    http_pool_size: int = Field(
        default=100,
        description="httpx 连接池最大连接数"
    )
    http_pool_keepalive: int = Field(
        default=30,
        description="连接保持活跃时间（秒）"
    )

    # MCP 服务配置
    mcp_transport: str = Field(default="http", description="传输协议：http / sse / stdio")
    mcp_host: str = Field(default="0.0.0.0", description="MCP 服务监听地址")
    mcp_port: int = Field(default=8079, description="MCP 服务监听端口")

    # 日志级别
    log_level: str = Field(default="INFO", description="日志级别")


settings = Settings()
