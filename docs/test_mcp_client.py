import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    # 1. 建立连接并获取会话
    async with streamablehttp_client("http://localhost:8079/mcp") as (read_stream, write_stream, _):
        # 2. 创建客户端会话并自动完成初始化
        async with ClientSession(read_stream, write_stream) as session:
            # 3. 调用工具
            result = await session.call_tool(
                "send_text_message",
                arguments={
                    "recv_id": "6122258426",
                    "text": "Hello from wwt-aiops, test message.",
                    "session_type": 1
                }
            )
            print(result)

if __name__ == "__main__":
    asyncio.run(main())
