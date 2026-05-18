#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "fastmcp[standard]",
#     "httpx",
#     "python-dotenv",
# ]
# ///
import os
import time
import json
import httpx
from typing import Optional, Annotated
from pathlib import Path
from pydantic import Field
from fastmcp import FastMCP
from httpx import AsyncHTTPTransport
from dotenv import load_dotenv

load_dotenv()  # 加载 .env 文件

# ---------- 配置 ----------
API_ADDRESS = os.getenv("OPENIM_API_ADDRESS", "http://localhost:10002")
ADMIN_SECRET = os.getenv("OPENIM_ADMIN_SECRET", "OpenIM123")
SENDER_ID = os.getenv("OPENIM_SENDER_ID", "5351970893")
PLATFORM_ID = int(os.getenv("OPENIM_PLATFORM_ID", "5"))
REQUEST_TIMEOUT = int(os.getenv("OPENIM_REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("OPENIM_MAX_RETRIES", "3"))
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8081"))

# ---------- 可复用 HTTP 客户端 ----------
def get_http_client() -> httpx.AsyncClient:
    transport = AsyncHTTPTransport(retries=MAX_RETRIES)
    return httpx.AsyncClient(transport=transport, timeout=REQUEST_TIMEOUT)

# ---------- Token 缓存器 ----------
class TokenCache:
    def __init__(self, api_addr: str, secret: str):
        self.api_addr = api_addr
        self.secret = secret
        self._token: Optional[str] = None
        self._expire_at: float = 0.0

    async def get_token(self) -> str:
        # 提前 10 分钟刷新
        if self._token and time.time() < self._expire_at - 600:
            return self._token

        async with get_http_client() as client:
            resp = await client.post(
                f"{self.api_addr}/auth/admin_token",
                json={"secret": self.secret}
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("errCode") != 0:
                raise Exception(f"获取管理员Token失败: {data.get('errMsg')}")
            self._token = data["data"]["adminToken"]
            # Token 有效期通常为 7 天，这里缓存 6 天
            self._expire_at = time.time() + 6 * 24 * 3600
            return self._token

token_cache = TokenCache(API_ADDRESS, ADMIN_SECRET)

# ---------- 文件上传辅助 ----------
async def upload_file(file_path: str) -> str:
    if not Path(file_path).exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    token = await token_cache.get_token()
    async with get_http_client() as client:
        # 初始化上传
        init_resp = await client.post(
            f"{API_ADDRESS}/file/initUpload",
            json={
                "fileName": Path(file_path).name,
                "fileType": "image/jpeg",
                "operationID": str(int(time.time()))
            },
            headers={"token": token}
        )
        init_resp.raise_for_status()
        init_data = init_resp.json()
        if init_data.get("errCode") != 0:
            raise Exception(f"文件上传初始化失败: {init_data.get('errMsg')}")
        upload_url = init_data["data"]["uploadURL"]
        file_uuid = init_data["data"]["uuid"]
        # 上传文件
        with open(file_path, "rb") as f:
            await client.put(upload_url, content=f.read(), headers={"Content-Type": "application/octet-stream"})
        return f"{API_ADDRESS}/file/{file_uuid}"

# ---------- MCP 服务定义 ----------
mcp = FastMCP("OpenIM Message Service")

@mcp.tool()
async def send_text_message(
    recv_id: Annotated[str, Field(description="接收者ID，单聊为userID，群聊为groupID")],
    text: Annotated[str, Field(description="要发送的文本内容")],
    session_type: Annotated[int, Field(description="会话类型：1为单聊，3为群聊")] = 1,
    sender_id: Annotated[str, Field(description="发送者ID，默认为系统账号")] = SENDER_ID
) -> str:
    try:
        token = await token_cache.get_token()
        payload = {
            "sendID": sender_id,
            "recvID": recv_id,
            "content": {"content": text},
            "contentType": 101,
            "sessionType": session_type,
            "senderPlatformID": PLATFORM_ID
        }
        async with get_http_client() as client:
            resp = await client.post(f"{API_ADDRESS}/msg/send_msg", json=payload, headers={"token": token})
            resp.raise_for_status()
            result = resp.json()
            return json.dumps({"errCode": result.get("errCode"), "serverMsgID": result.get("data", {}).get("serverMsgID")}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@mcp.tool()
async def send_picture_message(
    recv_id: Annotated[str, Field(description="接收者ID")],
    image_url_or_path: Annotated[str, Field(description="图片URL或本地路径")],
    session_type: Annotated[int, Field(description="1:单聊,3:群聊")] = 1,
    sender_id: Annotated[str, Field(description="发送者ID")] = SENDER_ID
) -> str:
    try:
        token = await token_cache.get_token()
        file_path = None
        # 判断是本地路径还是URL
        if image_url_or_path.startswith("http://") or image_url_or_path.startswith("https://"):
            img_url = image_url_or_path
        else:
            img_url = await upload_file(image_url_or_path)
        payload = {
            "sendID": sender_id,
            "recvID": recv_id,
            "content": {
                "sourcePicture": {"url": img_url},
                "bigPicture": {"url": img_url},
                "snapshotPicture": {"url": img_url}
            },
            "contentType": 102,
            "sessionType": session_type,
            "senderPlatformID": PLATFORM_ID
        }
        async with get_http_client() as client:
            resp = await client.post(f"{API_ADDRESS}/msg/send_msg", json=payload, headers={"token": token})
            resp.raise_for_status()
            result = resp.json()
            return json.dumps({"errCode": result.get("errCode"), "serverMsgID": result.get("data", {}).get("serverMsgID")}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@mcp.tool()
async def send_at_message(
    recv_id: Annotated[str, Field(description="群聊ID")],
    text: Annotated[str, Field(description="要发送的文本")],
    at_user_id_list: Annotated[str, Field(description="要@的用户ID，逗号分隔")],
    sender_id: Annotated[str, Field(description="发送者ID")] = SENDER_ID
) -> str:
    try:
        token = await token_cache.get_token()
        payload = {
            "sendID": sender_id,
            "recvID": recv_id,
            "content": {
                "text": text,
                "atUserList": [uid.strip() for uid in at_user_id_list.split(',')]
            },
            "contentType": 106,
            "sessionType": 3,
            "senderPlatformID": PLATFORM_ID
        }
        async with get_http_client() as client:
            resp = await client.post(f"{API_ADDRESS}/msg/send_msg", json=payload, headers={"token": token})
            resp.raise_for_status()
            result = resp.json()
            return json.dumps({"errCode": result.get("errCode"), "serverMsgID": result.get("data", {}).get("serverMsgID")}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

def main():
    if "sse" in MCP_TRANSPORT.lower():
        # SSE (Server-Sent Events) 模式
        mcp.run(transport="sse", host=MCP_HOST, port=MCP_PORT)
    elif "http" in MCP_TRANSPORT.lower():
        # 或者 HTTP 流模式
        mcp.run(transport="http", host=MCP_HOST, port=MCP_PORT)
    else:
        mcp.run()

if __name__ == "__main__":
    main()
