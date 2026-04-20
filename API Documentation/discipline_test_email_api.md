# Discipline Report Email API

## Send Discipline Report

Calculates the discipline risk result and sends it to the user's email. No data is stored in the database.

---

### Endpoint

```
POST /api/notifications/discipline-report/send/
```

---

### Authentication

None required. This is a public endpoint.

---

### Request

**Headers**

```
Content-Type: application/json
```

**Body**

```json
{
  "email": "user@example.com",
  "risk_level": "high"
}
```

**Fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | Yes | Recipient email address |
| `risk_level` | string | Yes | Must be `low`, `moderate`, or `high` |

---

### Responses

**200 OK — Email sent successfully**

```json
{
  "detail": "Report sent successfully."
}
```

**400 Bad Request — Missing or invalid fields**

```json
{
  "detail": "Valid email and risk_level required."
}
```

**500 Internal Server Error — Email sending failed**

```json
{
  "detail": "Failed to send email.",
  "error": "Connection refused"
}
```

---

### Examples

**curl**

```bash
curl -X POST http://localhost:13025/api/notifications/discipline-report/send/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "risk_level": "high"}'
```

**JavaScript (Frontend)**

```javascript
const res = await fetch("/api/notifications/discipline-report/send/", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "test@example.com", risk_level: "moderate" }),
});

const data = await res.json();
console.log(data); // { detail: "Report sent successfully." }
```

---

### Risk Level Behavior

| `risk_level` | Email Subject | Summary |
|---|---|---|
| `low` | Your Discipline Profile Report | Discipline patterns are stable |
| `moderate` | Your Discipline Profile Report | Discipline holds under normal pressure |
| `high` | Your Discipline Profile Report | Trading behavior is likely harming results |

---

### Notes

- No data is saved to the database. This endpoint only sends an email.
- The email is HTML formatted with the risk level, title, key points, and advice.
- For local testing use smtp4dev at `http://localhost:5010`.
