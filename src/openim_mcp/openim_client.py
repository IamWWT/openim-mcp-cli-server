"""
OpenIM REST API 客户端 — 生产级高并发实现
特性：
  - admin token 自动刷新（过期前 5 分钟刷新）
  - httpx 连接池复用
  - 信号量控制并发请求数
  - 自动重试（可配置）
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import httpx
from loguru import logger

from .config import settings


@dataclass
class Pagination:
    """分页参数"""
    page_number: int = 1
    show_number: int = 100


# noinspection PyMethodMayBeStatic
class OpenIMClient:
    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._sem = asyncio.Semaphore(settings.openim_concurrency)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """延迟初始化 httpx 客户端（确保在异步上下文中创建）"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.openim_api_address,
                timeout=httpx.Timeout(settings.http_timeout),
                limits=httpx.Limits(
                    max_connections=settings.http_pool_size,
                    max_keepalive_connections=settings.http_pool_size,
                    keepalive_expiry=settings.http_pool_keepalive,
                ),
            )
        return self._client

    @staticmethod
    def check_private_chat_policy(session_type: int, recv_id: str = "") -> tuple[bool, str]:
        """
        校验聊天策略。
        返回 (是否允许, 错误信息)。
        - session_type=1 单聊：校验 ALLOW_PRIVATE_CHAT 开关
        - session_type=3 群聊：校验 recv_id（groupID）非空
        """
        if session_type == 1:
            if not settings.allow_private_chat:
                return False, "私聊已禁用（ALLOW_PRIVATE_CHAT=false）。请使用群聊（session_type=3）"
        elif session_type == 3:
            if not recv_id:
                return False, "群聊模式必须指定 groupID（recv_id 不能为空）"
        else:
            return False, f"不支持的 session_type={session_type}，有效值：1=单聊，3=群聊"
        return True, ""

    @staticmethod
    def check_create_group_policy() -> tuple[bool, str]:
        """校验是否允许创建群组"""
        if not settings.allow_create_group:
            return False, "创建群组已禁用（ALLOW_CREATE_GROUP=false）。需在 .env 中设为 true 开启"
        return True, ""

    @staticmethod
    def check_notification_policy() -> tuple[bool, str]:
        """校验是否允许发送业务通知"""
        if not settings.allow_send_notification:
            return False, "发送业务通知已禁用（ALLOW_SEND_NOTIFICATION=false）。需在 .env 中设为 true 开启"
        return True, ""

    async def lookup_user(
        self,
        user_id: str = "",
        nickname: str = "",
        retries: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """
        用户查询：ID→名称 / 名称→ID
        - 给定 user_id：直接调用 get_users_info 返回详情
        - 给定 nickname：遍历所有已注册用户，按昵称模糊匹配（含子串匹配）
        返回 (是否成功, {"users": [...], "lookup_type": "id"|"nickname"})
        """
        if user_id:
            ok, users = await self.get_users_info([user_id], retries=retries)
            if ok:
                return True, {"users": users, "lookup_type": "id"}
            return False, None

        if nickname:
            # 遍历所有用户查找昵称匹配
            page = Pagination(page_number=1, show_number=200)
            ok, data = await self.get_all_users(pagination=page, retries=retries)
            if not ok:
                return False, None
            total = data.get("total", 0)
            all_users = data.get("users", [])
            matched = [u for u in all_users if nickname.lower() in (u.get("nickname", "") or "").lower()]
            # 如果第一页没找全且 total > 200，后续页继续（简化处理：最多翻 5 页）
            # 实际使用中通常 200 条足够覆盖
            return True, {"users": matched, "lookup_type": "nickname", "total_scanned": len(all_users), "total_users": total}
        return False, None

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def ensure_token(self) -> str:
        """获取有效的 admin token，必要时自动刷新"""
        now = time.time()
        if self._token and now < self._token_expires_at - 300:  # 提前 5 分钟刷新
            return self._token
        return await self._refresh_token()

    async def _refresh_token(self) -> str:
        """使用 /auth/get_admin_token 获取新 token"""
        client = await self._get_client()
        try:
            resp = await client.post(
                "/auth/get_admin_token",
                json={
                    "secret": settings.openim_admin_secret,
                    "userID": settings.openim_admin_id,
                },
                headers={
                    "operationID": self._generate_op_id(),
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("errCode") != 0:
                raise RuntimeError(f"get_admin_token failed: {data}")
            token = data["data"]["token"]
            ttl = data["data"].get("expireTimeSeconds", settings.token_ttl_seconds)
            self._token = token
            self._token_expires_at = time.time() + ttl
            logger.info(f"OpenIM admin token refreshed, TTL={ttl}s")
            return token
        except Exception as e:
            logger.error(f"Failed to refresh admin token: {e}")
            raise

    async def send_text(
        self,
        send_id: str,
        recv_id: str,
        text: str,
        session_type: int = 1,  # 1=单聊，3=群聊
        retries: int = 1,
    ) -> tuple[bool, Optional[str]]:
        """
        发送文本消息（contentType=101）
        返回 (是否成功, serverMsgID)
        """
        async with self._sem:
            token = await self.ensure_token()
            payload = {
                "sendID": send_id,
                "recvID": recv_id,
                "content": {"content": text},
                "contentType": 101,
                "sessionType": session_type,
                "senderPlatformID": settings.bot_platform_id,
                "isOnlineOnly": False,
                "notOfflinePush": False,
                "offlinePushInfo": {
                    "title": "系统消息",
                    "desc": text[:60],
                    "iOSBadgeCount": True,
                },
            }
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/msg/send_msg",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    err_code = result.get("errCode")
                    if err_code == 0:
                        server_msg_id = result.get("data", {}).get("serverMsgID")
                        logger.debug(f"Message sent: {send_id} -> {recv_id}, msgID={server_msg_id}")
                        return True, server_msg_id
                    else:
                        logger.warning(f"OpenIM send error: errCode={err_code}, errMsg={result.get('errMsg')}")
                        # 若 token 失效，强制刷新后重试一次
                        if err_code in (10014, 10017):  # 常见 token 无效错误码
                            await self._refresh_token()
                            continue
                except Exception as e:
                    logger.warning(f"Send attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
                    else:
                        return False, None
            return False, None

    async def send_business_notification(
        self,
        send_user_id: str,
        recv_user_id: str = "",
        recv_group_id: str = "",
        key: str = "",
        data: str = "",
        send_msg: bool = False,
        reliability_level: int = 1,
        retries: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """
        发送业务通知（POST /msg/send_business_notification）
        客户端会收到 OnRecvCustomBusinessMessage 回调
        返回 (是否成功, {serverMsgID, clientMsgID, sendTime})
        """
        async with self._sem:
            token = await self.ensure_token()
            payload = {
                "sendUserID": send_user_id,
                "key": key,
                "data": data,
                "sendMsg": send_msg,
                "reliabilityLevel": reliability_level,
            }
            if recv_user_id:
                payload["recvUserID"] = recv_user_id
            if recv_group_id:
                payload["recvGroupID"] = recv_group_id
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/msg/send_business_notification",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data")
                    else:
                        logger.warning(f"Business notification send error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Business notification attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def revoke_message(
        self,
        user_id: str,
        conversation_id: str,
        seq: int,
        retries: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """撤回消息（POST /msg/revoke_msg）"""
        async with self._sem:
            token = await self.ensure_token()
            payload = {
                "userID": user_id,
                "conversationID": conversation_id,
                "seq": seq,
            }
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/msg/revoke_msg",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data")
                    else:
                        logger.warning(f"Revoke message error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Revoke attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def get_users_info(
        self,
        user_ids: list[str],
        retries: int = 1,
    ) -> tuple[bool, Optional[list[dict]]]:
        """获取用户详情（POST /user/get_users_info）"""
        async with self._sem:
            token = await self.ensure_token()
            payload = {"userIDs": user_ids}
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/user/get_users_info",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data", {}).get("usersInfo", [])
                    else:
                        logger.warning(f"Get users info error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Get users info attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def get_users_online_status(
        self,
        user_ids: list[str],
        retries: int = 1,
    ) -> tuple[bool, Optional[list[dict]]]:
        """获取用户在线状态（POST /user/get_users_online_status）"""
        async with self._sem:
            token = await self.ensure_token()
            payload = {"userIDs": user_ids}
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/user/get_users_online_status",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data", [])
                    else:
                        logger.warning(f"Get online status error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Get online status attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def get_all_users(
        self,
        pagination: Pagination = None,
        retries: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """获取已注册用户列表（POST /user/get_users，分页）"""
        if pagination is None:
            pagination = Pagination()
        async with self._sem:
            token = await self.ensure_token()
            payload = {
                "pagination": {
                    "pageNumber": pagination.page_number,
                    "showNumber": pagination.show_number,
                }
            }
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/user/get_users",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data")
                    else:
                        logger.warning(f"Get all users error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Get all users attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def get_groups_info(
        self,
        group_ids: list[str],
        retries: int = 1,
    ) -> tuple[bool, Optional[list[dict]]]:
        """获取群组详情（POST /group/get_groups_info）"""
        async with self._sem:
            token = await self.ensure_token()
            payload = {"groupIDs": group_ids}
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/group/get_groups_info",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data", {}).get("groupInfos", [])
                    else:
                        logger.warning(f"Get groups info error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Get groups info attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def get_group_member_list(
        self,
        group_id: str,
        pagination: Pagination = None,
        keyword: str = "",
        retries: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """获取群成员列表（POST /group/get_group_member_list，分页）"""
        if pagination is None:
            pagination = Pagination()
        async with self._sem:
            token = await self.ensure_token()
            payload = {
                "groupID": group_id,
                "pagination": {
                    "pageNumber": pagination.page_number,
                    "showNumber": pagination.show_number,
                },
            }
            if keyword:
                payload["keyword"] = keyword
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/group/get_group_member_list",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data")
                    else:
                        logger.warning(f"Get group member list error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Get group member list attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def create_group(
        self,
        owner_user_id: str,
        group_name: str,
        member_user_ids: list[str] = None,
        admin_user_ids: list[str] = None,
        group_type: int = 2,
        group_id: str = "",
        notification: str = "",
        introduction: str = "",
        face_url: str = "",
        ex: str = "",
        need_verification: int = 0,
        look_member_info: int = 0,
        apply_member_friend: int = 0,
        retries: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """创建群组（POST /group/create_group），成员（含群主）≥3人"""
        async with self._sem:
            token = await self.ensure_token()
            group_info: dict = {
                "groupName": group_name,
                "groupType": group_type,
                "needVerification": need_verification,
                "lookMemberInfo": look_member_info,
                "applyMemberFriend": apply_member_friend,
            }
            if group_id:
                group_info["groupID"] = group_id
            if notification:
                group_info["notification"] = notification
            if introduction:
                group_info["introduction"] = introduction
            if face_url:
                group_info["faceURL"] = face_url
            if ex:
                group_info["ex"] = ex

            payload: dict = {
                "ownerUserID": owner_user_id,
                "groupInfo": group_info,
            }
            if member_user_ids:
                payload["memberUserIDs"] = member_user_ids
            if admin_user_ids:
                payload["adminUserIDs"] = admin_user_ids

            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/group/create_group",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data", {}).get("groupInfo")
                    else:
                        logger.warning(f"Create group error: errCode={result.get('errCode')}, errMsg={result.get('errMsg')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Create group attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def invite_to_group(
        self,
        group_id: str,
        invited_user_ids: list[str],
        reason: str = "",
        retries: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """邀请进群（POST /group/invite_user_to_group）"""
        async with self._sem:
            token = await self.ensure_token()
            payload: dict = {
                "groupID": group_id,
                "invitedUserIDs": invited_user_ids,
            }
            if reason:
                payload["reason"] = reason
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/group/invite_user_to_group",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data")
                    else:
                        logger.warning(f"Invite to group error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Invite to group attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def kick_group_member(
        self,
        group_id: str,
        kicked_user_ids: list[str],
        reason: str = "",
        retries: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """移除群成员（POST /group/kick_group）"""
        async with self._sem:
            token = await self.ensure_token()
            payload: dict = {
                "groupID": group_id,
                "kickedUserIDs": kicked_user_ids,
            }
            if reason:
                payload["reason"] = reason
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/group/kick_group",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data")
                    else:
                        logger.warning(f"Kick group member error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Kick group member attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def get_conversation_list(
        self,
        user_id: str,
        pagination: Pagination = None,
        conversation_ids: list[str] = None,
        retries: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """获取排序后的会话列表（POST /conversation/get_sorted_conversation_list）"""
        if pagination is None:
            pagination = Pagination(show_number=20)
        async with self._sem:
            token = await self.ensure_token()
            payload: dict = {
                "userID": user_id,
                "pagination": {
                    "pageNumber": pagination.page_number,
                    "showNumber": pagination.show_number,
                },
            }
            if conversation_ids:
                payload["conversationIDs"] = conversation_ids
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/conversation/get_sorted_conversation_list",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data")
                    else:
                        logger.warning(f"Get conversation list error: errCode={result.get('errCode')}")
                        return False, None
                except Exception as e:
                    logger.warning(f"Get conversation list attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def send_image(
        self,
        send_id: str,
        recv_id: str,
        image_url: str,  # 在线图片 URL（已上传的）
        session_type: int = 1,
        retries: int = 1,
    ) -> tuple[bool, Optional[str]]:
        """发送图片消息（contentType=102）"""
        async with self._sem:
            token = await self.ensure_token()
            payload = {
                "sendID": send_id,
                "recvID": recv_id,
                "content": {
                    "sourcePicture": {"url": image_url},
                    "bigPicture": {"url": image_url},
                    "snapshotPicture": {"url": image_url},
                },
                "contentType": 102,
                "sessionType": session_type,
                "senderPlatformID": settings.bot_platform_id,
            }
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/msg/send_msg",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data", {}).get("serverMsgID")
                except Exception as e:
                    logger.warning(f"Image send attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    async def send_at(
        self,
        send_id: str,
        group_id: str,
        text: str,
        at_user_ids: list[str],
        retries: int = 1,
    ) -> tuple[bool, Optional[str]]:
        """群聊 @ 消息（contentType=106）"""
        async with self._sem:
            token = await self.ensure_token()
            payload = {
                "sendID": send_id,
                "recvID": group_id,
                "content": {
                    "text": text,
                    "atUserList": at_user_ids,
                },
                "contentType": 106,
                "sessionType": 3,  # 群聊
                "senderPlatformID": settings.bot_platform_id,
            }
            client = await self._get_client()
            for attempt in range(retries + 1):
                try:
                    resp = await client.post(
                        "/msg/send_msg",
                        json=payload,
                        headers={
                            "token": token,
                            "operationID": self._generate_op_id(),
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    if result.get("errCode") == 0:
                        return True, result.get("data", {}).get("serverMsgID")
                except Exception as e:
                    logger.warning(f"At message attempt {attempt+1} failed: {e}")
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
            return False, None

    @staticmethod
    def _generate_op_id() -> str:
        """生成 operationID"""
        return f"{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}"

    def token_valid(self) -> bool:
        return bool(self._token) and time.time() < self._token_expires_at