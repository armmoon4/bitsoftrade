# BitsOfTrade — Complete API Documentation

> **Base URL:** `http://localhost:8000`  
> **Auth (user endpoints):** `Authorization: Bearer <access_token>`  
> **Auth (admin endpoints):** `X-Admin-Id: <admin_uuid>`

---

## Quick Start — First Run

### 1. Create the first Super Admin (run once on the server)
```bash
python manage.py create_super_admin \
  --email admin@bitsoftrade.com \
  --name "Super Admin" \
  --password Str0ngP@ss!
```

### 2. Register a user and get a token
```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"trader1","email":"trader1@test.com","password":"Pass1234!"}'
```
Save the `access` token from the response — use it as `Bearer <token>` in all user API calls.

---

## 🔐 1. Authentication — `/api/auth/`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/register/` | None | Register new user |
| POST | `/api/auth/login/` | None | Login, get JWT tokens |
| POST | `/api/auth/token/` | None | Get JWT pair (SimpleJWT) |
| POST | `/api/auth/token/refresh/` | None | Refresh access token |
| POST | `/api/auth/logout/` | Bearer | Blacklist refresh token |
| GET | `/api/auth/me/` | Bearer | Get current user info |
| GET/PUT/PATCH | `/api/auth/profile/` | Bearer | View or update profile |

### Register
```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "trader1",
    "email": "trader1@example.com",
    "password": "Pass1234!"
  }'
```
**Response 201:**
```json
{
  "message": "User registered successfully",
  "user": { "id": "...", "username": "trader1", "email": "trader1@example.com" },
  "tokens": { "access": "eyJ...", "refresh": "eyJ..." }
}
```

### Login
```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "trader1", "password": "Pass1234!"}'
```

### Refresh Token
```bash
curl -X POST http://localhost:8000/api/auth/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<refresh_token>"}'
```

### Logout
```bash
curl -X POST http://localhost:8000/api/auth/logout/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<refresh_token>"}'
```

### Get Current User
```bash
curl http://localhost:8000/api/auth/me/ \
  -H "Authorization: Bearer <access_token>"
```

### Update Profile
```bash
curl -X PATCH http://localhost:8000/api/auth/profile/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"first_name": "John", "last_name": "Doe"}'
```

---

## 🛡️ 2. Admin Panel — `/api/admin/`

> All admin endpoints require `X-Admin-Id: <admin_uuid>` header.  
> Super-admin-only endpoints are marked with 🔒.

| Method | Endpoint | Level | Description |
|--------|----------|-------|-------------|
| POST | `/api/admin/auth/login/` | None | Admin login |
| GET | `/api/admin/dashboard/stats/` | Any admin | Platform stats |
| GET | `/api/admin/users/` | Any admin | List all users |
| PUT | `/api/admin/users/<uuid>/toggle/` | Any admin | Toggle user active |
| DELETE | `/api/admin/users/<uuid>/delete/` | Any admin | Soft-delete user |
| GET | `/api/admin/admins/` | Any admin | List all admins |
| POST | `/api/admin/admins/create/` | 🔒 Super | Create new admin |
| PUT/DELETE | `/api/admin/admins/<uuid>/` | 🔒 Super | Edit/delete admin |
| GET/POST | `/api/admin/courses/` | Any admin | List/create courses |
| GET/PUT/DELETE | `/api/admin/courses/<uuid>/` | Any admin | Course detail |
| GET/POST | `/api/admin/rules/` | Any admin | List/create global rules |
| PUT/DELETE | `/api/admin/rules/<uuid>/` | Any admin | Edit/delete global rule |

### Admin Login
```bash
curl -X POST http://localhost:8000/api/admin/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@bitsoftrade.com", "password": "Str0ngP@ss!"}'
```
**Response 200:**
```json
{
  "admin_id": "550e8400-e29b-...",
  "full_name": "Super Admin",
  "email": "admin@bitsoftrade.com",
  "access_level": "super_admin",
  "message": "Login successful."
}
```
> Save `admin_id` — send it as `X-Admin-Id` header in all subsequent admin calls.

### Dashboard Stats
```bash
curl http://localhost:8000/api/admin/dashboard/stats/ \
  -H "X-Admin-Id: <admin_uuid>"
```
**Response:**
```json
{
  "total_users": 120,
  "todays_new_users": 5,
  "total_subscribers": 80,
  "total_course_views": 340,
  "total_trade_imports": 210,
  "total_earned": 15000.00
}
```

### List Users (with filters)
```bash
# All users
curl "http://localhost:8000/api/admin/users/" -H "X-Admin-Id: <admin_uuid>"

# Filter by subscription type
curl "http://localhost:8000/api/admin/users/?subscription_type=tool" -H "X-Admin-Id: <admin_uuid>"

# Search by username or email
curl "http://localhost:8000/api/admin/users/?search=john" -H "X-Admin-Id: <admin_uuid>"
```

### Toggle User Active/Inactive
```bash
curl -X PUT http://localhost:8000/api/admin/users/<user_uuid>/toggle/ \
  -H "X-Admin-Id: <admin_uuid>"
```

### Delete User (Soft)
```bash
curl -X DELETE http://localhost:8000/api/admin/users/<user_uuid>/delete/ \
  -H "X-Admin-Id: <admin_uuid>"
```

### 🔒 Create Admin
```bash
curl -X POST http://localhost:8000/api/admin/admins/create/ \
  -H "X-Admin-Id: <super_admin_uuid>" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Jane Admin",
    "email": "jane@bitsoftrade.com",
    "password": "JaneP@ss123",
    "access_level": "admin"
  }'
```

### 🔒 Edit Admin
```bash
curl -X PUT http://localhost:8000/api/admin/admins/<target_admin_uuid>/ \
  -H "X-Admin-Id: <super_admin_uuid>" \
  -H "Content-Type: application/json" \
  -d '{"access_level": "super_admin"}'
```

### 🔒 Delete Admin
```bash
curl -X DELETE http://localhost:8000/api/admin/admins/<target_admin_uuid>/ \
  -H "X-Admin-Id: <super_admin_uuid>"
```

### Create a Global Rule (Admin)
```bash
curl -X POST http://localhost:8000/api/admin/rules/ \
  -H "X-Admin-Id: <admin_uuid>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "Max Daily Loss 3%",
    "description": "Stop trading if daily loss exceeds 3%",
    "category": "risk",
    "rule_type": "hard",
    "trigger_scope": "per_day",
    "trigger_condition": {"maxDailyPercent": 3},
    "action": "lock"
  }'
```

---

## 📊 3. Trade Log — `/api/tradelog/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/tradelog/trades/` | List or create trades |
| GET/PUT/PATCH/DELETE | `/api/tradelog/trades/<uuid>/` | Trade detail |
| POST | `/api/tradelog/trades/import/` | Import CSV/Excel file |

### List Trades (with filters)
```bash
# All trades
curl http://localhost:8000/api/tradelog/trades/ \
  -H "Authorization: Bearer <access_token>"

# Only winning trades
curl "http://localhost:8000/api/tradelog/trades/?filter=wins" \
  -H "Authorization: Bearer <access_token>"

# filter options: wins | losses | disciplined | violations
```

### Create a Trade
```bash
curl -X POST http://localhost:8000/api/tradelog/trades/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "RELIANCE",
    "trade_date": "2026-02-25",
    "trade_time": "09:30:00",
    "direction": "long",
    "quantity": "10",
    "entry_price": "2900.00",
    "exit_price": "2950.00",
    "fees": "20.00",
    "market_type": "indian_stocks"
  }'
```

### Import Trades from CSV
```bash
curl -X POST http://localhost:8000/api/tradelog/trades/import/ \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/trades.csv" \
  -F "broker_name=Zerodha"
```
**CSV columns expected:** `symbol, date, time, direction, quantity, entry_price, exit_price, fees`  
**Supported formats:** `.csv`, `.xlsx`, `.xls`

**Response:**
```json
{
  "imported": 45,
  "failed": 2,
  "errors": [{"row": 3, "error": "Invalid date format", "data": {...}}],
  "message": "45 trades imported successfully."
}
```

### Update Trade
```bash
curl -X PATCH http://localhost:8000/api/tradelog/trades/<uuid>/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"exit_price": "2970.00"}'
```

### Delete Trade (Soft)
```bash
curl -X DELETE http://localhost:8000/api/tradelog/trades/<uuid>/ \
  -H "Authorization: Bearer <access_token>"
```

---

## 📝 4. Journal — `/api/journal/`

All journal endpoints require `Authorization: Bearer <access_token>`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/journal/daily/` | Daily journals |
| GET/PUT/DELETE | `/api/journal/daily/<uuid>/` | Daily journal detail |
| GET/POST | `/api/journal/trade-notes/` | Trade-specific notes |
| GET/PUT/DELETE | `/api/journal/trade-notes/<uuid>/` | Trade note detail |
| GET/POST | `/api/journal/psychology/` | Psychology logs |
| GET/PUT/DELETE | `/api/journal/psychology/<uuid>/` | Psychology log detail |
| GET/POST | `/api/journal/recaps/` | Session recaps |
| GET/PUT/DELETE | `/api/journal/recaps/<uuid>/` | Session recap detail |
| GET/POST | `/api/journal/learning-notes/` | Learning notes |
| GET/PUT/DELETE | `/api/journal/learning-notes/<uuid>/` | Learning note detail |

### Create Daily Journal
```bash
curl -X POST http://localhost:8000/api/journal/daily/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "journal_date": "2026-02-25",
    "pre_market_note": "Feeling focused today. Plan to trade NIFTY breakout.",
    "post_market_note": "Followed my rules. Missed one entry due to slippage.",
    "mood_score": 4,
    "focus_score": 5
  }'
```
> ⚠️ Only one journal is allowed per date per user.

### Create Trade Note
```bash
curl -X POST http://localhost:8000/api/journal/trade-notes/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "trade_id": "<trade_uuid>",
    "note": "Entered late, missed the optimal entry by 2 points.",
    "emotion_tag": "greedy"
  }'
```

### Create Psychology Log
```bash
curl -X POST http://localhost:8000/api/journal/psychology/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "log_date": "2026-02-25",
    "emotion": "fear",
    "intensity": 3,
    "trigger": "Big red candle at open scared me out of the position.",
    "reflection": "Should have trusted my plan."
  }'
```

### List All Journals (Paginated)
```bash
curl "http://localhost:8000/api/journal/daily/?page=1" \
  -H "Authorization: Bearer <access_token>"
```

---

## 📏 5. Rules — `/api/rules/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/rules/` | List (global + own) / create user rule |
| GET/PUT/DELETE | `/api/rules/<uuid>/` | Rule detail (own rules only) |

### List All Rules (global admin rules + own custom rules)
```bash
curl http://localhost:8000/api/rules/ \
  -H "Authorization: Bearer <access_token>"
```
**Response** returns both `is_admin_defined: true` (global) and `is_admin_defined: false` (user's own) rules.

### Create a Custom Rule
```bash
curl -X POST http://localhost:8000/api/rules/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "No Revenge Trading",
    "description": "Never enter a trade after 2 consecutive losses",
    "category": "psychology",
    "rule_type": "soft",
    "trigger_scope": "per_day",
    "trigger_condition": {"consecutive_losses": 2},
    "action": "warn"
  }'
```
> The `user` field is **read-only** — it is always set to the authenticated user automatically. You cannot create rules for other users.

### Update a Rule
```bash
curl -X PATCH http://localhost:8000/api/rules/<uuid>/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

### Delete a Rule
```bash
curl -X DELETE http://localhost:8000/api/rules/<uuid>/ \
  -H "Authorization: Bearer <access_token>"
```
> Admin-defined rules cannot be deleted by users — returns **403 Forbidden**.

---

## 🚦 6. Discipline — `/api/discipline/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/discipline/current-session/` | Today's session state |
| GET | `/api/discipline/sessions/` | Full session history |
| POST | `/api/discipline/unlock/` | Attempt to unlock session |
| GET | `/api/discipline/violations-timeline/` | Per-day state timeline |

**Session states:** `green` (normal) → `yellow` (soft violation) → `red` (hard violation / locked)

### Get Today's Session
```bash
curl http://localhost:8000/api/discipline/current-session/ \
  -H "Authorization: Bearer <access_token>"
```
**Response:**
```json
{
  "id": "...",
  "session_date": "2026-02-25",
  "session_state": "yellow",
  "violations_count": 1,
  "hard_violations": 0,
  "soft_violations": 1,
  "journal_completed": false,
  "trade_review_completed": false,
  "cooldown_ends_at": null
}
```

### Unlock a Session
```bash
curl -X POST http://localhost:8000/api/discipline/unlock/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"action": "complete_journal"}'
```
**Action values:**
- `complete_journal` — mark journal as done
- `complete_trade_review` — mark trade review as done  
- `complete_all` — complete both at once

**Unlock conditions:**
- `yellow` → complete journal → unlocks to `green`
- `red` → complete journal + trade review → unlocks to `green`

### Violations Timeline
```bash
# Filter by date range
curl "http://localhost:8000/api/discipline/violations-timeline/?from=2026-02-01&to=2026-02-25" \
  -H "Authorization: Bearer <access_token>"
```
**Response:**
```json
[
  {"session_date": "2026-02-01", "session_state": "green", "violations_count": 0, "hard_violations": 0, "soft_violations": 0},
  {"session_date": "2026-02-03", "session_state": "yellow", "violations_count": 1, "hard_violations": 0, "soft_violations": 1}
]
```

---

## 📈 7. Strategies — `/api/strategies/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/strategies/` | List/create own strategies |
| GET/PUT/DELETE | `/api/strategies/<uuid>/` | Strategy detail |
| GET | `/api/strategies/community/` | Public strategies (not own) |
| GET | `/api/strategies/templates/` | Admin-created templates |
| POST | `/api/strategies/<uuid>/add-to-mine/` | Copy public strategy |

### List My Strategies
```bash
curl http://localhost:8000/api/strategies/ \
  -H "Authorization: Bearer <access_token>"
```
**Response includes computed performance metrics:**
```json
[
  {
    "id": "...",
    "strategy_name": "ORB Breakout",
    "total_trades": 30,
    "win_rate": 63.33,
    "total_pnl": "12500.00",
    "profit_factor": 1.8,
    "sample_size_progress": 60.0
  }
]
```

### Create a Strategy
```bash
curl -X POST http://localhost:8000/api/strategies/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_name": "ORB Breakout",
    "description": "Trade the opening range breakout on Nifty 50.",
    "tags": ["breakout", "nifty", "morning"],
    "market_types": ["indian_stocks"],
    "trade_type": "long",
    "sample_size_threshold": 50,
    "is_public": false
  }'
```

### Browse Community Strategies
```bash
curl http://localhost:8000/api/strategies/community/ \
  -H "Authorization: Bearer <access_token>"
```

### Copy a Community Strategy to Mine
```bash
curl -X POST http://localhost:8000/api/strategies/<uuid>/add-to-mine/ \
  -H "Authorization: Bearer <access_token>"
```
Creates a private copy with `(Copy)` appended to the name.

### Browse Admin Templates
```bash
curl http://localhost:8000/api/strategies/templates/ \
  -H "Authorization: Bearer <access_token>"
```

---

## 🧪 Testing Guide

### Option A — Postman / Insomnia
1. Import the base URL `http://localhost:8000`
2. Create an **environment** with two variables:
   - `user_token` — paste the JWT `access` token after login
   - `admin_id` — paste the `admin_id` after admin login
3. Set headers globally:
   - User requests: `Authorization: Bearer {{user_token}}`
   - Admin requests: `X-Admin-Id: {{admin_id}}`

### Option B — cURL (as shown in every section above)

### Option C — HTTPie (more readable than cURL)
```bash
pip install httpie

# User login
http POST localhost:8000/api/auth/login/ username=trader1 password=Pass1234!

# Authenticated request
http localhost:8000/api/tradelog/trades/ "Authorization: Bearer eyJ..."
```

### Typical Test Flow
```
1. Create super admin via manage.py (once)
2. POST /api/auth/register/         → get user access token
3. POST /api/admin/auth/login/      → get admin_id
4. POST /api/tradelog/trades/       → create a trade
5. GET  /api/discipline/current-session/ → check discipline state
6. POST /api/rules/                 → create a custom rule
7. POST /api/journal/daily/         → write today's journal
8. POST /api/strategies/            → create a strategy
9. GET  /api/admin/dashboard/stats/ → verify counts have increased
```

---

## ⚠️ Common Errors

| HTTP Code | Meaning | Fix |
|-----------|---------|-----|
| 401 | Missing or expired token | Re-login and get a fresh access token |
| 403 | Insufficient permission | Use super_admin account for admin-management endpoints |
| 400 | Validation error | Check the response body for field-level errors |
| 404 | Resource not found | Verify the UUID is correct and belongs to the user |
| 409/400 `journal_date` | Duplicate journal | Only one daily journal per date is allowed |
