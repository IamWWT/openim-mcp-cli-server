"""
CLI — 命令行直接调用 OpenIM 工具，无需启动 MCP 服务

用法:
  openim-cli send-text --recv-id user001 --text "Hello" --sender-id bot001 --session-type 1
  openim-cli send-biz-notification --send-user-id sys001 --recv-user-id user001 --key alert --data '{"msg":"disk full"}'
  openim-cli get-user-info --user-ids user001,user002
  openim-cli get-online-status --user-ids user001,user002
  openim-cli list-users --page-number 1 --show-number 50
  openim-cli get-group-info --group-ids 123456,789012
  openim-cli list-group-members --group-id 123456
  openim-cli create-group --owner-user-id user001 --group-name "告警响应群" --member-user-ids user002,user003
  openim-cli invite-to-group --group-id 123456 --invited-user-ids user004,user005
  openim-cli kick-from-group --group-id 123456 --kicked-user-ids user004
  openim-cli revoke-message --user-id user001 --conversation-id si_user001_user002 --seq 42
  openim-cli list-conversations --user-id user001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Optional

from .config import settings
from .openim_client import OpenIMClient, Pagination


def _parse_list(value: str) -> list[str]:
    """解析逗号分隔的列表"""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


async def _run_cmd(cmd_name: str, kwargs: dict) -> None:
    """异步执行命令并输出结果"""
    client = OpenIMClient()
    try:
        if cmd_name == "send-text":
            allowed, err = client.check_private_chat_policy(kwargs.get("session_type", 1), kwargs.get("recv_id", ""))
            if not allowed:
                print(json.dumps({"success": False, "error": err}))
                await client.close()
                sys.exit(1)
            ok, mid = await client.send_text(**kwargs)
            print(json.dumps({"success": ok, "server_msg_id": mid}, ensure_ascii=False))

        elif cmd_name == "send-image":
            allowed, err = client.check_private_chat_policy(kwargs.get("session_type", 1), kwargs.get("recv_id", ""))
            if not allowed:
                print(json.dumps({"success": False, "error": err}))
                await client.close()
                sys.exit(1)
            ok, mid = await client.send_image(**kwargs)
            print(json.dumps({"success": ok, "server_msg_id": mid}, ensure_ascii=False))

        elif cmd_name == "send-group-at":
            ok, mid = await client.send_at(**kwargs)
            print(json.dumps({"success": ok, "server_msg_id": mid}, ensure_ascii=False))

        elif cmd_name == "send-biz-notification":
            allowed, err = client.check_notification_policy()
            if not allowed:
                print(json.dumps({"success": False, "error": err}))
                await client.close()
                sys.exit(1)
            ok, data = await client.send_business_notification(**kwargs)
            print(json.dumps({"success": ok, "detail": data}, ensure_ascii=False))

        elif cmd_name == "revoke-message":
            ok, data = await client.revoke_message(**kwargs)
            print(json.dumps({"success": ok, "detail": data}, ensure_ascii=False))

        elif cmd_name == "get-user-info":
            ok, data = await client.get_users_info(**kwargs)
            print(json.dumps({"success": ok, "data": data}, ensure_ascii=False))

        elif cmd_name == "get-online-status":
            ok, data = await client.get_users_online_status(**kwargs)
            print(json.dumps({"success": ok, "data": data}, ensure_ascii=False))

        elif cmd_name == "list-users":
            ok, data = await client.get_all_users(**kwargs)
            print(json.dumps({"success": ok, "data": data}, ensure_ascii=False))

        elif cmd_name == "get-group-info":
            ok, data = await client.get_groups_info(**kwargs)
            print(json.dumps({"success": ok, "data": data}, ensure_ascii=False))

        elif cmd_name == "list-group-members":
            pagination = kwargs.pop("pagination", None)
            ok, data = await client.get_group_member_list(pagination=pagination, **kwargs)
            print(json.dumps({"success": ok, "data": data}, ensure_ascii=False))

        elif cmd_name == "create-group":
            allowed, err = client.check_create_group_policy()
            if not allowed:
                print(json.dumps({"success": False, "error": err}))
                await client.close()
                sys.exit(1)
            ok, data = await client.create_group(**kwargs)
            print(json.dumps({"success": ok, "data": data}, ensure_ascii=False))

        elif cmd_name == "invite-to-group":
            ok, data = await client.invite_to_group(**kwargs)
            print(json.dumps({"success": ok, "detail": data}, ensure_ascii=False))

        elif cmd_name == "kick-from-group":
            ok, data = await client.kick_group_member(**kwargs)
            print(json.dumps({"success": ok, "detail": data}, ensure_ascii=False))

        elif cmd_name == "list-conversations":
            pagination = kwargs.pop("pagination", None)
            conversation_ids = kwargs.pop("conversation_ids", None)
            ok, data = await client.get_conversation_list(
                pagination=pagination, conversation_ids=conversation_ids, **kwargs
            )
            print(json.dumps({"success": ok, "data": data}, ensure_ascii=False))

        elif cmd_name == "lookup-user":
            ok, data = await client.lookup_user(**kwargs)
            print(json.dumps({"success": ok, "data": data}, ensure_ascii=False))

        elif cmd_name == "lookup-group":
            ok, data = await client.get_groups_info(**kwargs)
            print(json.dumps({"success": ok, "data": data}, ensure_ascii=False))

        else:
            print(json.dumps({"success": False, "error": f"Unknown command: {cmd_name}"}))
            sys.exit(1)
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(
        prog="openim-cli",
        description="OpenIM CLI — 命令行直接调用 OpenIM 工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- send-text ----
    p = sub.add_parser("send-text", help="发送文本消息")
    p.add_argument("--recv-id", required=True, help="接收者 userID 或 groupID")
    p.add_argument("--text", required=True, help="消息文本")
    p.add_argument("--sender-id", default="", help="发送方 userID（默认读取 OPENIM_SENDER_ID）")
    p.add_argument("--session-type", type=int, default=1, help="1=单聊 3=群聊")

    # ---- send-image ----
    p = sub.add_parser("send-image", help="发送图片消息")
    p.add_argument("--recv-id", required=True, help="接收者 userID 或 groupID")
    p.add_argument("--image-url", required=True, help="图片 URL")
    p.add_argument("--sender-id", default="", help="发送方 userID（默认读取 OPENIM_SENDER_ID）")
    p.add_argument("--session-type", type=int, default=1, help="1=单聊 3=群聊")

    # ---- send-group-at ----
    p = sub.add_parser("send-group-at", help="群聊 @ 消息")
    p.add_argument("--group-id", required=True, help="群 ID")
    p.add_argument("--text", required=True, help="消息文本")
    p.add_argument("--at-user-ids", required=True, help="要 @ 的用户 ID，逗号分隔")
    p.add_argument("--sender-id", default="", help="发送方 userID（默认读取 OPENIM_SENDER_ID）")

    # ---- send-biz-notification ----
    p = sub.add_parser("send-biz-notification", help="发送业务通知")
    p.add_argument("--send-user-id", required=True, help="通知发送者 ID")
    p.add_argument("--key", required=True, help="业务分类 key")
    p.add_argument("--data", required=True, help="业务数据")
    p.add_argument("--recv-user-id", default="", help="接收者用户 ID")
    p.add_argument("--recv-group-id", default="", help="接收群 ID")
    p.add_argument("--send-msg", action="store_true", help="是否以消息形式发送")
    p.add_argument("--reliability-level", type=int, default=1, help="1=在线推送 2=必达通知")

    # ---- revoke-message ----
    p = sub.add_parser("revoke-message", help="撤回消息")
    p.add_argument("--user-id", required=True, help="撤回者 userID")
    p.add_argument("--conversation-id", required=True, help="会话 ID")
    p.add_argument("--seq", type=int, required=True, help="消息 seq")

    # ---- get-user-info ----
    p = sub.add_parser("get-user-info", help="获取用户详情")
    p.add_argument("--user-ids", required=True, help="用户 ID 列表，逗号分隔")

    # ---- get-online-status ----
    p = sub.add_parser("get-online-status", help="获取用户在线状态")
    p.add_argument("--user-ids", required=True, help="用户 ID 列表，逗号分隔")

    # ---- list-users ----
    p = sub.add_parser("list-users", help="获取所有已注册用户")
    p.add_argument("--page-number", type=int, default=1, help="页码")
    p.add_argument("--show-number", type=int, default=100, help="每页数量")

    # ---- get-group-info ----
    p = sub.add_parser("get-group-info", help="获取群组详情")
    p.add_argument("--group-ids", required=True, help="群 ID 列表，逗号分隔")

    # ---- list-group-members ----
    p = sub.add_parser("list-group-members", help="获取群成员列表")
    p.add_argument("--group-id", required=True, help="群 ID")
    p.add_argument("--page-number", type=int, default=1, help="页码")
    p.add_argument("--show-number", type=int, default=100, help="每页数量")
    p.add_argument("--keyword", default="", help="搜索关键词")

    # ---- create-group ----
    p = sub.add_parser("create-group", help="创建群组")
    p.add_argument("--owner-user-id", required=True, help="群主 userID")
    p.add_argument("--group-name", required=True, help="群名称")
    p.add_argument("--member-user-ids", default="", help="初始成员 userID，逗号分隔（不含群主）")
    p.add_argument("--admin-user-ids", default="", help="管理员 userID，逗号分隔")
    p.add_argument("--group-type", type=int, default=2, help="群类型")
    p.add_argument("--introduction", default="", help="群介绍")
    p.add_argument("--need-verification", type=int, default=0, help="进群是否需要验证")

    # ---- invite-to-group ----
    p = sub.add_parser("invite-to-group", help="邀请用户进群")
    p.add_argument("--group-id", required=True, help="目标群 ID")
    p.add_argument("--invited-user-ids", required=True, help="被邀请用户 ID，逗号分隔")
    p.add_argument("--reason", default="", help="邀请说明")

    # ---- kick-from-group ----
    p = sub.add_parser("kick-from-group", help="移除群成员")
    p.add_argument("--group-id", required=True, help="群 ID")
    p.add_argument("--kicked-user-ids", required=True, help="要移除的用户 ID，逗号分隔")
    p.add_argument("--reason", default="", help="移除原因")

    # ---- list-conversations ----
    p = sub.add_parser("list-conversations", help="获取会话列表")
    p.add_argument("--user-id", required=True, help="当前用户 ID")
    p.add_argument("--page-number", type=int, default=1, help="页码")
    p.add_argument("--show-number", type=int, default=20, help="每页数量")
    p.add_argument("--conversation-ids", default="", help="指定会话 ID，逗号分隔（可选）")

    # ---- lookup-user ----
    p = sub.add_parser("lookup-user", help="用户查询：ID→名称 / 名称→ID")
    p.add_argument("--user-id", default="", help="按 userID 查询（与 --nickname 二选一）")
    p.add_argument("--nickname", default="", help="按昵称模糊查询（与 --user-id 二选一）")

    # ---- lookup-group ----
    p = sub.add_parser("lookup-group", help="群组查询：groupID → 群名称")
    p.add_argument("--group-id", required=True, help="群 ID")
    p.add_argument("--summary", action="store_true", help="仅返回摘要信息（名称、人数、群主）")

    args = parser.parse_args()

    kwargs = {}
    cmd = args.command

    if cmd == "send-text":
        kwargs = {"send_id": args.sender_id or settings.sender_id, "recv_id": args.recv_id, "text": args.text, "session_type": args.session_type}
    elif cmd == "send-image":
        kwargs = {"send_id": args.sender_id or settings.sender_id, "recv_id": args.recv_id, "image_url": args.image_url, "session_type": args.session_type}
    elif cmd == "send-group-at":
        kwargs = {"send_id": args.sender_id or settings.sender_id, "group_id": args.group_id, "text": args.text, "at_user_ids": _parse_list(args.at_user_ids)}
    elif cmd == "send-biz-notification":
        kwargs = {
            "send_user_id": args.send_user_id, "recv_user_id": args.recv_user_id,
            "recv_group_id": args.recv_group_id, "key": args.key, "data": args.data,
            "send_msg": args.send_msg, "reliability_level": args.reliability_level,
        }
    elif cmd == "revoke-message":
        kwargs = {"user_id": args.user_id, "conversation_id": args.conversation_id, "seq": args.seq}
    elif cmd == "get-user-info":
        kwargs = {"user_ids": _parse_list(args.user_ids)}
    elif cmd == "get-online-status":
        kwargs = {"user_ids": _parse_list(args.user_ids)}
    elif cmd == "list-users":
        kwargs = {"pagination": Pagination(page_number=args.page_number, show_number=args.show_number)}
    elif cmd == "get-group-info":
        kwargs = {"group_ids": _parse_list(args.group_ids)}
    elif cmd == "list-group-members":
        kwargs = {
            "group_id": args.group_id,
            "pagination": Pagination(page_number=args.page_number, show_number=args.show_number),
            "keyword": args.keyword,
        }
    elif cmd == "create-group":
        kwargs = {
            "owner_user_id": args.owner_user_id, "group_name": args.group_name,
            "member_user_ids": _parse_list(args.member_user_ids),
            "admin_user_ids": _parse_list(args.admin_user_ids),
            "group_type": args.group_type, "introduction": args.introduction,
            "need_verification": args.need_verification,
        }
    elif cmd == "invite-to-group":
        kwargs = {
            "group_id": args.group_id, "invited_user_ids": _parse_list(args.invited_user_ids),
            "reason": args.reason,
        }
    elif cmd == "kick-from-group":
        kwargs = {
            "group_id": args.group_id, "kicked_user_ids": _parse_list(args.kicked_user_ids),
            "reason": args.reason,
        }
    elif cmd == "list-conversations":
        kwargs = {
            "user_id": args.user_id,
            "pagination": Pagination(page_number=args.page_number, show_number=args.show_number),
            "conversation_ids": _parse_list(args.conversation_ids) if args.conversation_ids else None,
        }
    elif cmd == "lookup-user":
        kwargs = {"user_id": args.user_id, "nickname": args.nickname}
    elif cmd == "lookup-group":
        kwargs = {"group_ids": [args.group_id]}

    asyncio.run(_run_cmd(cmd, kwargs))


if __name__ == "__main__":
    main()