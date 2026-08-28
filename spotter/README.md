# How to Use ThoughtSpot Spotter via API

This guide walks you through querying ThoughtSpot Spotter using the REST API v2.0.
No SDKs required — just HTTP calls.

---

## Prerequisites

- A ThoughtSpot Cloud instance (e.g. `https://mycompany.thoughtspot.cloud`)
- A ThoughtSpot username and password (or a secret key for token-based auth)
- Any HTTP client: `curl`, Python `requests`, Postman, etc.

---

## Step 1 — Get an Auth Token

Every API call requires a Bearer token. Get one first.

**Request:**
```http
POST https://<TS_HOST>/api/rest/2.0/auth/token/full
Content-Type: application/json

{
  "username": "your_username",
  "password": "your_password",
  "validity_time_in_sec": 3600
}
```

**Response:**
```json
{
  "token": "eyJhbGciOiJSUzI1NiIs...",
  "token_expiry_duration": 3600
}
```

Save the `token` value. Use it as `Authorization: Bearer <token>` on all subsequent calls.

**curl example:**
```bash
curl -X POST "https://<TS_HOST>/api/rest/2.0/auth/token/full" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"yourpassword","validity_time_in_sec":3600}'
```

---

## Step 2 — (Optional) Find a Data Source

If you already know your worksheet GUID, skip to Step 3.

To let Spotter suggest relevant data sources for your question:

**Request:**
```http
POST https://<TS_HOST>/api/rest/2.0/ai/data-source-suggestions
Authorization: Bearer <token>
Content-Type: application/json

{
  "query": "revenue by region"
}
```

**Response:** Returns a list of matching worksheets with their GUIDs.

Use a GUID from the response in Step 3, or use `AUTO_MODE` to let Spotter decide automatically.

---

## Step 3 — Create a Conversation Session

A session holds the context for your conversation with Spotter.

**Option A — Let Spotter auto-select the data source (recommended for first use):**
```http
POST https://<TS_HOST>/api/rest/2.0/ai/agent/conversation/create
Authorization: Bearer <token>
Content-Type: application/json

{
  "metadata_context": {
    "type": "AUTO_MODE"
  },
  "conversation_settings": {
    "enable_save_chat": true
  }
}
```

**Option B — Target a specific worksheet:**
```http
POST https://<TS_HOST>/api/rest/2.0/ai/agent/conversation/create
Authorization: Bearer <token>
Content-Type: application/json

{
  "metadata_context": {
    "type": "WORKSHEET",
    "worksheet_id": "<your-worksheet-guid>"
  },
  "conversation_settings": {
    "enable_save_chat": true
  }
}
```

**Response:**
```json
{
  "conversation_identifier": "conv_abc123xyz"
}
```

Save the `conversation_identifier`. You will use it in every message you send.

---

## Step 4 — Ask a Question

Send a natural language question to your conversation session.

### Option A — Synchronous (get the full answer at once)

```http
POST https://<TS_HOST>/api/rest/2.0/ai/agent/conversation/<conversation_identifier>/send
Authorization: Bearer <token>
Content-Type: application/json

{
  "messages": [
    "What are the top 10 customers by revenue in 2025?"
  ]
}
```

**Response:** Returns the complete answer with data and visualization metadata.

### Option B — Streaming via SSE (real-time, for chat UIs)

```http
POST https://<TS_HOST>/api/rest/2.0/ai/agent/conversation/<conversation_identifier>/send/stream
Authorization: Bearer <token>
Content-Type: application/json
Accept: text/event-stream

{
  "messages": [
    "What are the top 10 customers by revenue in 2025?"
  ]
}
```

**Response:** Streams answer tokens incrementally using Server-Sent Events (SSE).

---

## Step 5 — Continue the Conversation

Repeat Step 4 with the same `conversation_identifier` to ask follow-up questions.
Spotter retains context across messages in the same session.

```json
{
  "messages": [
    "Now break that down by product category"
  ]
}
```

---

## Full Python Example

```python
import requests

TS_HOST = "https://mycompany.thoughtspot.cloud"

# Step 1: Auth
auth = requests.post(f"{TS_HOST}/api/rest/2.0/auth/token/full", json={
    "username": "admin",
    "password": "yourpassword",
    "validity_time_in_sec": 3600
})
token = auth.json()["token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Step 3: Create conversation
conv = requests.post(
    f"{TS_HOST}/api/rest/2.0/ai/agent/conversation/create",
    headers=headers,
    json={"metadata_context": {"type": "AUTO_MODE"}}
)
conv_id = conv.json()["conversation_identifier"]

# Step 4: Ask a question
answer = requests.post(
    f"{TS_HOST}/api/rest/2.0/ai/agent/conversation/{conv_id}/send",
    headers=headers,
    json={"messages": ["Top 10 customers by revenue in 2025"]}
)
print(answer.json())

# Step 5: Follow-up
followup = requests.post(
    f"{TS_HOST}/api/rest/2.0/ai/agent/conversation/{conv_id}/send",
    headers=headers,
    json={"messages": ["Break that down by region"]}
)
print(followup.json())
```

---

## API Reference Summary

| Step | Method | Endpoint |
|------|--------|----------|
| 1. Auth | `POST` | `/api/rest/2.0/auth/token/full` |
| 2. Find data source | `POST` | `/api/rest/2.0/ai/data-source-suggestions` |
| 3. Create session | `POST` | `/api/rest/2.0/ai/agent/conversation/create` |
| 4a. Ask (sync) | `POST` | `/api/rest/2.0/ai/agent/conversation/{id}/send` |
| 4b. Ask (stream) | `POST` | `/api/rest/2.0/ai/agent/conversation/{id}/send/stream` |

---

## Rate Limits

| Operation | Limit |
|-----------|-------|
| Create conversation | 10 requests / min per user |
| Send message | 30 messages / min per conversation |

---

## Troubleshooting

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `401 Unauthorized` | Token missing or expired | Re-run Step 1 to get a fresh token |
| `403 Forbidden` | User lacks access to the worksheet | Grant view access to the data source in ThoughtSpot |
| `429 Too Many Requests` | Rate limit hit | Wait and retry; implement exponential backoff |
| Empty answer | No matching data for the query | Try `AUTO_MODE` or use `/ai/data-source-suggestions` |

---

## Additional Resources

- [ThoughtSpot Developer Docs — Spotter APIs](https://developers.thoughtspot.com/docs/spotter-api)
- [AI APIs (Spotter Agent and Spotter 3)](https://developers.thoughtspot.com/docs/spotter-agent-apis)
- [REST API v2.0 Reference](https://developers.thoughtspot.com/docs/rest-apiv2-reference)
- [REST API v2.0 Playground](https://developers.thoughtspot.com/docs/rest-apiv2-getstarted)
