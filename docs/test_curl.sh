curl --noproxy "*" -X POST http://localhost:8079/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "send_text_message",
      "arguments": {
        "recv_id": "6122258426",
        "text": "Hello from wwt-aiops, this is a test message.",
        "session_type": 1
      }
    }
  }'


event: message
data: {"jsonrpc":"2.0","id":1,"result":{"_meta":{"fastmcp":{"wrap_result":true}},"content":[{"type":"text","text":"{\"success\": true, \"server_msg_id\": \"944d642fffaec0a6b055a15c40287cd6\", \"errCode\": 0}"}],"structuredContent":{"result":"{\"success\": true, \"server_msg_id\": \"944d642fffaec0a6b055a15c40287cd6\", \"errCode\": 0}"},"isError":false}}


