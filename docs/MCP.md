# CollectIQ MCP server

CollectIQ exposes its collections brain to other AI agents through the
[Model Context Protocol](https://modelcontextprotocol.io). Claude Desktop, Claude Code or any
MCP client can read invoices and client behaviour from PayPal and **propose** actions.

**Nothing is executed through MCP.** Every proposal goes through the same checks as CollectIQ's own
agent and waits for a person to approve it in the CollectIQ app (Approvals page).

## Tools

| Tool | Type | What it does |
|---|---|---|
| `get_invoice_analysis` | read | All PayPal invoices with state, days overdue, priority, allowed action, last reminder |
| `get_invoice_details` | read | The same analysis for one invoice |
| `get_client_insights` | read | On-time rate, average days late, risk level, 30-day collections forecast |
| `get_payment_link` | read | PayPal's own payment page for a sent, unpaid invoice (validated URL) |
| `list_pending_approvals` | read | Actions waiting for a human decision |
| `propose_action` | propose | Proposes `send_invoice` or `send_reminder`. It is rejected unless it is the invoice's allowed action, respects the 3-day reminder cooldown and passes the message safety check |

There is no execute or approve tool. Every MCP call is written to the audit log as `MCP client: ...`.

## Endpoint and auth

- URL: `https://<your-host>/mcp/` (Streamable HTTP, note the trailing slash)
- Header: `Authorization: Bearer <MCP_API_TOKEN>`
- `MCP_API_TOKEN` empty → the MCP server is disabled (503). Wrong or missing token → 401.

Generate a token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Connect a client

**Claude Code**

```bash
claude mcp add --transport http collectiq https://<your-host>/mcp/ \
  --header "Authorization: Bearer $COLLECTIQ_MCP_TOKEN"
```

**Claude Desktop** (`claude_desktop_config.json`, through `mcp-remote`)

```json
{
  "mcpServers": {
    "collectiq": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://<your-host>/mcp/", "--header", "Authorization:${COLLECTIQ_AUTH}"],
      "env": { "COLLECTIQ_AUTH": "Bearer <MCP_API_TOKEN>" }
    }
  }
}
```

**MCP Inspector**

```bash
npx @modelcontextprotocol/inspector
```

Choose *Streamable HTTP*, enter the URL and add the `Authorization` header.

## Try it

> "Which CollectIQ invoices are overdue? Propose a reminder for the most overdue one."

The agent reads the invoices and proposes the reminder. The proposal then appears in CollectIQ →
Approvals as pending, and only a person can approve and send it through PayPal.
