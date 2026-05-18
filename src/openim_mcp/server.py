"""
MCP 服务主入口 — 定义 tools 并启动 HTTP 服务
"""

import os
import json
from typing import Annotated, Optional, List
from pydantic import Field
from fastmcp import FastMCP
from loguru import logger
from dataclasses import asdict

from .config import settings
from .openim_client import OpenIMClient, Pagination

# 全局 OpenIM 客户端（单例，复用连接池）
openim_client = OpenIMClient()

# 创建 MCP 服务实例
mcp = FastMCP("OpenIM Message Service")


@mcp.tool()
async def send_text_message(
    recv_id: Annotated[str, Field(description="接收者 userID（单聊）或 groupID（群聊）")],
    text: Annotated[str, Field(description="消息文本内容")],
    session_type: Annotated[int, Field(description="会话类型：1=单聊，3=群聊")] = 1,
) -> str:
    """
    发送文本消息。支持单聊(1)和群聊(3)。
    发送者身份由环境变量 OPENIM_SENDER_ID 统一指定，不可伪造。
    """
    # 私聊策略校验
    allowed, err_msg = openim_client.check_private_chat_policy(session_type, recv_id)
    if not allowed:
        return json.dumps({"success": False, "error": err_msg, "errCode": -1})

    try:
        success, msg_id = await openim_client.send_text(
            send_id=settings.sender_id,
            recv_id=recv_id,
            text=text,
            session_type=session_type,
        )
        if success:
            return json.dumps({"success": True, "server_msg_id": msg_id, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "OpenIM send failed", "errCode": -1})
    except Exception as e:
        logger.exception("send_text_message failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def send_picture_message(
    recv_id: Annotated[str, Field(description="接收者 userID 或 groupID")],
    image_url: Annotated[str, Field(description="图片的在线 URL（需已上传到 OpenIM 或其他可访问地址）")],
    session_type: Annotated[int, Field(description="1=单聊,3=群聊")] = 1,
) -> str:
    """
    发送图片消息。注意：图片必须已经可公开访问，本服务不负责上传。
    发送者身份由环境变量 OPENIM_SENDER_ID 统一指定，不可伪造。
    """
    # 私聊策略校验
    allowed, err_msg = openim_client.check_private_chat_policy(session_type, recv_id)
    if not allowed:
        return json.dumps({"success": False, "error": err_msg, "errCode": -1})

    try:
        success, msg_id = await openim_client.send_image(
            send_id=settings.sender_id,
            recv_id=recv_id,
            image_url=image_url,
            session_type=session_type,
        )
        if success:
            return json.dumps({"success": True, "server_msg_id": msg_id, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Image send failed", "errCode": -1})
    except Exception as e:
        logger.exception("send_picture_message failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def send_group_at_message(
    group_id: Annotated[str, Field(description="群聊 ID")],
    text: Annotated[str, Field(description="消息文本")],
    at_user_ids: Annotated[List[str], Field(description="要 @ 的用户 userID 列表，例如 ['user1','user2']")],
) -> str:
    """
    在群聊中发送 @ 消息。发送者身份由环境变量 OPENIM_SENDER_ID 统一指定。
    """
    try:
        success, msg_id = await openim_client.send_at(
            send_id=settings.sender_id,
            group_id=group_id,
            text=text,
            at_user_ids=at_user_ids,
        )
        if success:
            return json.dumps({"success": True, "server_msg_id": msg_id, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "At message send failed", "errCode": -1})
    except Exception as e:
        logger.exception("send_group_at_message failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def send_business_notification(
    send_user_id: Annotated[str, Field(description="系统通知号ID，或用户ID")],
    key: Annotated[str, Field(description="业务分类 key，客户端以此区分处理逻辑")],
    data: Annotated[str, Field(description="业务数据（JSON 字符串或纯文本）")],
    recv_user_id: Annotated[str, Field(description="接收者用户ID（与 recv_group_id 二选一）")] = "",
    recv_group_id: Annotated[str, Field(description="接收群ID（与 recv_user_id 二选一）")] = "",
    send_msg: Annotated[bool, Field(description="是否以消息形式发送")] = False,
    reliability_level: Annotated[int, Field(description="可靠性级别：1=在线推送，2=必达通知")] = 1,
) -> str:
    """
    发送业务通知。客户端通过 OnRecvCustomBusinessMessage 回调接收，适用于 AIOps 告警推送等场景。
    """
    # 发送通知策略校验
    allowed, err_msg = openim_client.check_notification_policy()
    if not allowed:
        return json.dumps({"success": False, "error": err_msg, "errCode": -1})
    try:
        success, result = await openim_client.send_business_notification(
            send_user_id=send_user_id,
            recv_user_id=recv_user_id,
            recv_group_id=recv_group_id,
            key=key,
            data=data,
            send_msg=send_msg,
            reliability_level=reliability_level,
        )
        if success:
            return json.dumps({"success": True, "detail": result, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Notification send failed", "errCode": -1})
    except Exception as e:
        logger.exception("send_business_notification failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def revoke_message(
    user_id: Annotated[str, Field(description="撤回者 userID（发送者或管理员）")],
    conversation_id: Annotated[str, Field(description="会话ID，如 si_userA_userB")],
    seq: Annotated[int, Field(description="要撤回消息的 seq 序号")],
) -> str:
    """
    撤回一条已发送的消息。需启用 ALLOW_REVOKE_MESSAGE 环境变量。
    """
    allowed, err_msg = openim_client.check_revoke_policy()
    if not allowed:
        return json.dumps({"success": False, "error": err_msg, "errCode": -1})
    try:
        success, result = await openim_client.revoke_message(
            user_id=user_id,
            conversation_id=conversation_id,
            seq=seq,
        )
        if success:
            return json.dumps({"success": True, "detail": result, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Revoke failed", "errCode": -1})
    except Exception as e:
        logger.exception("revoke_message failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def get_users_info(
    user_ids: Annotated[List[str], Field(description="要查询的用户 ID 列表，如 ['user1','user2']")],
) -> str:
    """
    获取指定用户的详细信息（昵称、头像、注册时间等）。
    """
    try:
        success, users = await openim_client.get_users_info(user_ids=user_ids)
        if success:
            return json.dumps({"success": True, "data": users, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Get users info failed", "errCode": -1})
    except Exception as e:
        logger.exception("get_users_info failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def get_users_online_status(
    user_ids: Annotated[List[str], Field(description="要查询的用户 ID 列表")],
) -> str:
    """
    获取指定用户的在线状态和终端详情。
    """
    try:
        success, data = await openim_client.get_users_online_status(user_ids=user_ids)
        if success:
            return json.dumps({"success": True, "data": data, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Get online status failed", "errCode": -1})
    except Exception as e:
        logger.exception("get_users_online_status failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def get_all_users(
    page_number: Annotated[int, Field(description="页码，从 1 开始")] = 1,
    show_number: Annotated[int, Field(description="每页数量")] = 100,
) -> str:
    """
    获取所有已注册用户列表（分页）。
    """
    try:
        pagination = Pagination(page_number=page_number, show_number=show_number)
        success, data = await openim_client.get_all_users(pagination=pagination)
        if success:
            return json.dumps({"success": True, "data": data, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Get all users failed", "errCode": -1})
    except Exception as e:
        logger.exception("get_all_users failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def get_groups_info(
    group_ids: Annotated[List[str], Field(description="群ID 列表，如 ['123456','789012']")],
) -> str:
    """
    获取指定群组的详细信息（群名、人数、群主、创建时间等）。
    """
    try:
        success, groups = await openim_client.get_groups_info(group_ids=group_ids)
        if success:
            return json.dumps({"success": True, "data": groups, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Get groups info failed", "errCode": -1})
    except Exception as e:
        logger.exception("get_groups_info failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def get_group_member_list(
    group_id: Annotated[str, Field(description="群ID")],
    page_number: Annotated[int, Field(description="页码，从 1 开始")] = 1,
    show_number: Annotated[int, Field(description="每页数量")] = 100,
    keyword: Annotated[str, Field(description="搜索关键词（userID 或昵称）")] = "",
) -> str:
    """
    分页获取群成员列表，按群主→管理员→普通成员排序。
    """
    try:
        pagination = Pagination(page_number=page_number, show_number=show_number)
        success, data = await openim_client.get_group_member_list(
            group_id=group_id,
            pagination=pagination,
            keyword=keyword,
        )
        if success:
            return json.dumps({"success": True, "data": data, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Get group member list failed", "errCode": -1})
    except Exception as e:
        logger.exception("get_group_member_list failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def create_group(
    owner_user_id: Annotated[str, Field(description="群主 userID")],
    group_name: Annotated[str, Field(description="群名称")],
    member_user_ids: Annotated[List[str], Field(description="初始群成员 userID 列表（不含群主）")] = None,
    admin_user_ids: Annotated[List[str], Field(description="群管理员 userID 列表")] = None,
    group_type: Annotated[int, Field(description="群类型，固定为 2")] = 2,
    introduction: Annotated[str, Field(description="群介绍")] = "",
    need_verification: Annotated[int, Field(description="进群是否需要验证，0=否 1=是")] = 0,
) -> str:
    """
    创建群组。成员总数（含群主）不能少于 3 人。适用于动态创建告警响应群。
    """
    # 创建群组策略校验
    allowed, err_msg = openim_client.check_create_group_policy()
    if not allowed:
        return json.dumps({"success": False, "error": err_msg, "errCode": -1})
    try:
        success, group_info = await openim_client.create_group(
            owner_user_id=owner_user_id,
            group_name=group_name,
            member_user_ids=member_user_ids or [],
            admin_user_ids=admin_user_ids or [],
            group_type=group_type,
            introduction=introduction,
            need_verification=need_verification,
        )
        if success:
            return json.dumps({"success": True, "data": group_info, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Create group failed", "errCode": -1})
    except Exception as e:
        logger.exception("create_group failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def invite_to_group(
    group_id: Annotated[str, Field(description="目标群 ID")],
    invited_user_ids: Annotated[List[str], Field(description="被邀请的用户 ID 列表")],
    reason: Annotated[str, Field(description="邀请说明")] = "",
) -> str:
    """
    邀请用户进群。需启用 ALLOW_INVITE_TO_GROUP 环境变量。若群设置需要验证，则需群主或管理员同意。
    """
    allowed, err_msg = openim_client.check_invite_policy()
    if not allowed:
        return json.dumps({"success": False, "error": err_msg, "errCode": -1})
    try:
        success, result = await openim_client.invite_to_group(
            group_id=group_id,
            invited_user_ids=invited_user_ids,
            reason=reason,
        )
        if success:
            return json.dumps({"success": True, "detail": result, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Invite failed", "errCode": -1})
    except Exception as e:
        logger.exception("invite_to_group failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def kick_group_member(
    group_id: Annotated[str, Field(description="群 ID")],
    kicked_user_ids: Annotated[List[str], Field(description="要移除的用户 ID 列表")],
    reason: Annotated[str, Field(description="移除原因")] = "",
) -> str:
    """
    将群成员从群组中移除。需启用 ALLOW_KICK_MEMBER 环境变量。若移除群主，需先转让群主身份。
    """
    allowed, err_msg = openim_client.check_kick_policy()
    if not allowed:
        return json.dumps({"success": False, "error": err_msg, "errCode": -1})
    try:
        success, result = await openim_client.kick_group_member(
            group_id=group_id,
            kicked_user_ids=kicked_user_ids,
            reason=reason,
        )
        if success:
            return json.dumps({"success": True, "detail": result, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Kick failed", "errCode": -1})
    except Exception as e:
        logger.exception("kick_group_member failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def get_conversation_list(
    user_id: Annotated[str, Field(description="当前用户 ID")],
    page_number: Annotated[int, Field(description="页码，从 1 开始")] = 1,
    show_number: Annotated[int, Field(description="每页数量")] = 20,
    conversation_ids: Annotated[List[str], Field(description="指定会话 ID 列表（可选）")] = None,
) -> str:
    """
    获取排序后的会话列表（按置顶、最新消息时间排序）。
    """
    try:
        pagination = Pagination(page_number=page_number, show_number=show_number)
        success, data = await openim_client.get_conversation_list(
            user_id=user_id,
            pagination=pagination,
            conversation_ids=conversation_ids or [],
        )
        if success:
            return json.dumps({"success": True, "data": data, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Get conversation list failed", "errCode": -1})
    except Exception as e:
        logger.exception("get_conversation_list failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def lookup_user(
    user_id: Annotated[str, Field(description="按 userID 查询（与 nickname 二选一）")] = "",
    nickname: Annotated[str, Field(description="按昵称模糊查询（与 user_id 二选一）")] = "",
) -> str:
    """
    用户查询：userID → 昵称/详情，或昵称 → userID。
    - 给定 user_id：直接返回该用户详情
    - 给定 nickname：遍历所有注册用户，按昵称模糊匹配（含子串）
    """
    if not user_id and not nickname:
        return json.dumps({"success": False, "error": "请提供 user_id 或 nickname", "errCode": -1})
    try:
        success, result = await openim_client.lookup_user(
            user_id=user_id,
            nickname=nickname,
        )
        if success:
            return json.dumps({"success": True, "data": result, "errCode": 0})
        else:
            return json.dumps({"success": False, "error": "Lookup user failed", "errCode": -1})
    except Exception as e:
        logger.exception("lookup_user failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


@mcp.tool()
async def lookup_group(
    group_id: Annotated[str, Field(description="按 groupID 查询群名称及详情")],
) -> str:
    """
    群组查询：groupID → 群名称/详情。
    注意：OpenIM 不支持按群名称反向查询 groupID，请确保提供正确的 groupID。
    """
    try:
        # 直接复用 get_groups_info
        success, groups = await openim_client.get_groups_info(group_ids=[group_id])
        if success and groups:
            group = groups[0]
            summary = {
                "groupID": group.get("groupID"),
                "groupName": group.get("groupName"),
                "introduction": group.get("introduction"),
                "memberCount": group.get("memberCount"),
                "ownerUserID": group.get("ownerUserID"),
                "createTime": group.get("createTime"),
                "status": group.get("status"),
            }
            return json.dumps({"success": True, "data": summary, "errCode": 0})
        elif success:
            return json.dumps({"success": False, "error": f"群组 {group_id} 不存在", "errCode": -1})
        else:
            return json.dumps({"success": False, "error": "Lookup group failed", "errCode": -1})
    except Exception as e:
        logger.exception("lookup_group failed")
        return json.dumps({"success": False, "error": str(e), "errCode": -1})


def main():
    """服务启动入口"""
    # 配置 loguru 输出格式
    logger.add(
        sink=lambda msg: print(msg, end=""),  # 简单输出到 stdout
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=settings.log_level,
    )
    logger.info(f"Starting OpenIM MCP Server with transport '{settings.mcp_transport}'")
    logger.info(f"OpenIM API: {settings.openim_api_address}")

    # 根据配置选择传输模式
    transport = settings.mcp_transport.lower()
    if transport == "http":
        # stateless_http=True 使得每个请求独立，无需会话 ID
        mcp.run(
            transport="http",
            host=settings.mcp_host,
            port=settings.mcp_port,
            stateless_http=True,
            log_level=settings.log_level.lower(),
        )
    elif transport == "sse":
        mcp.run(
            transport="sse",
            host=settings.mcp_host,
            port=settings.mcp_port,
            log_level=settings.log_level.lower(),
        )
    else:  # stdio
        mcp.run(transport="stdio", log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()