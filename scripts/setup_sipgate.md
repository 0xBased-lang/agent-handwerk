# sipgate Integration Guide

This guide explains how to configure sipgate (German VoIP provider) with the Phone Agent.

## Prerequisites

1. sipgate account (basic or team)
2. Phone number configured
3. Phone Agent running with webhook endpoint accessible

## Step 1: Get sipgate Credentials

1. Log in to https://app.sipgate.com
2. Go to **Account** → **API Credentials**
3. Create new credentials with "webhooks" scope
4. Note down:
   - Token ID
   - Token

## Step 2: Configure Webhooks

1. Go to **Routing** → **Webhooks**
2. Add new webhook with these settings:

| Setting | Value |
|---------|-------|
| URL | `https://your-server.example.com/api/v1/webhooks/sipgate/call` |
| Events | `newCall`, `answer`, `hangup` |
| Direction | `in` (incoming calls) |

3. Test the webhook

## Step 3: Update Phone Agent Config

Edit `configs/production.yaml`:

```yaml
telephony:
  enabled: true
  backend: webhook

integrations:
  sipgate:
    enabled: true
    token_id: "your-token-id"
    token: "your-token"
    webhook_secret: "your-webhook-secret"
```

## Step 4: Configure Routing

In sipgate:
1. Go to **Routing** → **Number**
2. Select your phone number
3. Set destination to **Webhook**
4. Select your configured webhook

## Webhook Payloads

### Incoming Call (newCall)

```json
{
  "event": "newCall",
  "callId": "123456789",
  "from": "+4930123456789",
  "to": "+4940987654321",
  "direction": "in",
  "user": ["w0"],
  "xcid": "abc123"
}
```

### Call Answered (answer)

```json
{
  "event": "answer",
  "callId": "123456789",
  "user": "w0",
  "answeringNumber": "+4940987654321"
}
```

### Call Ended (hangup)

```json
{
  "event": "hangup",
  "callId": "123456789",
  "cause": "normalClearing"
}
```

## Response Actions

The Phone Agent responds with actions:

### Accept Call

```json
{
  "action": "accept"
}
```

### Reject Call

```json
{
  "action": "reject",
  "reason": "busy"
}
```

### Transfer Call

```json
{
  "action": "transfer",
  "destination": "+4930123456789"
}
```

## Audio Streaming

sipgate supports audio streaming via WebSocket:

1. Return `audio_stream` URL in webhook response
2. sipgate connects to your WebSocket endpoint
3. Bidirectional audio flows via WebSocket

```json
{
  "action": "accept",
  "audio_stream": "wss://your-server.example.com/ws/audio/123456789"
}
```

## Testing

1. Start Phone Agent with webhook backend:
   ```bash
   uvicorn phone_agent.main:app --host 0.0.0.0 --port 8080
   ```

2. Expose via ngrok for testing:
   ```bash
   ngrok http 8080
   ```

3. Update sipgate webhook URL with ngrok URL

4. Make test call to your sipgate number

## Troubleshooting

### Webhook not receiving calls

- Check URL is accessible from internet
- Verify webhook is enabled in sipgate
- Check sipgate API logs

### Audio issues

- Ensure WebSocket endpoint is reachable
- Check firewall allows WebSocket connections
- Verify SSL certificate is valid

### Call drops immediately

- Check Phone Agent logs for errors
- Verify webhook response format
- Check sipgate routing configuration

## Support

- sipgate Documentation: https://www.sipgate.io/docs
- sipgate API Reference: https://api.sipgate.com/v2/doc
