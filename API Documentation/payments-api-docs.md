# Payments API Documentation

Base path: `/api/payments/`  
Admin base path: `/api/admin/`

---

## Table of Contents

1. [Data Models](#data-models)
2. [Endpoints](#endpoints)
   - [Create Order](#1-create-order)
   - [Webhook](#2-webhook)
   - [Payment History](#3-payment-history)
   - [Admin — All Payments](#4-admin--all-payments)
3. [Plan Types & Pricing](#plan-types--pricing)
4. [Transaction Statuses](#transaction-statuses)
5. [Error Responses](#error-responses)
6. [Settings Reference](#settings-reference)

---

## Data Models

### PaymentTransaction

| Field                  | Type        | Description                                                        |
|------------------------|-------------|--------------------------------------------------------------------|
| `id`                   | UUID        | Auto-generated primary key                                         |
| `user`                 | FK → User   | The authenticated user who made the payment                        |
| `razorpay_order_id`    | string      | Order ID returned by Razorpay on order creation                    |
| `razorpay_payment_id`  | string      | Payment ID from Razorpay (set on webhook success)                  |
| `amount`               | decimal     | Amount in INR (rupees, not paise)                                  |
| `currency`             | string      | Always `INR`                                                       |
| `plan_type`            | string      | One of `tool`, `learning`, `both`                                  |
| `card_key`             | string      | CMS `PricingPlan.card_key` that was purchased (e.g. `discipline_tools`) |
| `billing_cycle`        | string      | One of `monthly`, `yearly`, `biannual`, `annual`                   |
| `status`               | string      | One of `pending`, `success`, `failed`, `refunded`                  |
| `paid_at`              | datetime    | Timestamp of successful payment (nullable)                         |
| `created_at`           | datetime    | Record creation timestamp                                          |

---

## Endpoints

### 1. Create Order

Creates a Razorpay order and a pending `PaymentTransaction` record.  
**Prices are fetched live from the CMS `PricingPlan` table** — not hardcoded.

```
POST /api/payments/create-order/
```

**Authentication:** Required (Bearer token / session)

**Request Body**

| Field            | Type   | Required | Description                                                                 |
|------------------|--------|----------|-----------------------------------------------------------------------------|
| `card_key`       | string | Yes      | CMS card identifier. One of `discipline_tools`, `learning_hub`, `combo_monthly`, `combo_annual` |
| `billing_cycle`  | string | No       | `monthly` or `yearly`. Only relevant for `discipline_tools`. Ignored for all other cards — billing cycle is read from the CMS record automatically. |

**Example Requests**

```json
// discipline_tools — monthly
{
  "card_key": "discipline_tools",
  "billing_cycle": "monthly"
}

// discipline_tools — yearly
{
  "card_key": "discipline_tools",
  "billing_cycle": "yearly"
}

// learning_hub — no billing_cycle needed
{
  "card_key": "learning_hub"
}

// combo_monthly
{
  "card_key": "combo_monthly"
}

// combo_annual
{
  "card_key": "combo_annual"
}
```

**Success Response — `201 Created`**

```json
{
  "order_id": "order_QxYzABC123",
  "amount": 99900,
  "amount_display": 999.0,
  "currency": "INR",
  "key": "rzp_live_xxxxxxxxxxxx",
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "plan_name": "Discipline Tools",
  "plan_type": "tool"
}
```

| Field            | Description                                                        |
|------------------|--------------------------------------------------------------------|
| `order_id`       | Razorpay order ID — pass to the Razorpay checkout SDK              |
| `amount`         | Amount in **paise** — pass directly to Razorpay JS SDK             |
| `amount_display` | Amount in **rupees** — use for UI display (e.g. "₹999")            |
| `currency`       | Always `INR`                                                       |
| `key`            | Razorpay public key ID for the frontend SDK                        |
| `transaction_id` | Internal UUID for this transaction                                 |
| `plan_name`      | Human-readable plan name from CMS (e.g. `"Discipline Tools"`)      |
| `plan_type`      | Resolved subscription type: `tool`, `learning`, or `both`          |

**Error Responses**

| Status | Condition                              | Body                                                      |
|--------|----------------------------------------|-----------------------------------------------------------|
| `400`  | Missing `card_key`                     | `{"error": "card_key is required."}`                      |
| `400`  | Invalid `card_key`                     | `{"error": "Invalid card_key."}`                          |
| `401`  | Unauthenticated request                | Standard DRF 401                                          |
| `404`  | Plan not found or marked inactive      | `{"error": "Plan not found or inactive."}`                |
| `500`  | Razorpay SDK not installed             | `{"error": "Razorpay SDK not installed."}`                |

---

### 2. Webhook

Receives Razorpay payment event notifications. On a `payment.captured` event, marks the transaction as successful and activates the user's subscription for the correct duration based on the `card_key` and `billing_cycle`.

```
POST /api/payments/webhook/
```

**Authentication:** None (public endpoint). Requests are verified using an HMAC-SHA256 signature when `RAZORPAY_WEBHOOK_SECRET` is configured.

**Headers**

| Header                    | Description                                                                              |
|---------------------------|------------------------------------------------------------------------------------------|
| `X-Razorpay-Signature`    | HMAC-SHA256 hex digest of the raw body, signed with `RAZORPAY_WEBHOOK_SECRET`            |

**Expected Payload (Razorpay standard format)**

```json
{
  "event": "payment.captured",
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_QxYzABC456",
        "order_id": "order_QxYzABC123"
      }
    }
  }
}
```

**Supported Events**

| Event               | Behaviour                                                                                      |
|---------------------|------------------------------------------------------------------------------------------------|
| `payment.captured`  | Sets transaction `status` → `success`, records `paid_at`, activates user subscription for the correct duration |
| `payment.failed`    | Sets transaction `status` → `failed` (only if currently `pending`)                             |
| Any other event     | Ignored — returns `200 OK`                                                                     |

**Subscription Duration by Plan**

| `card_key`          | `billing_cycle` | Duration   |
|---------------------|-----------------|------------|
| `discipline_tools`  | `monthly`       | 30 days    |
| `discipline_tools`  | `yearly`        | 365 days   |
| `learning_hub`      | `biannual`      | 180 days   |
| `combo_monthly`     | `monthly`       | 30 days    |
| `combo_annual`      | `annual`        | 365 days   |

> If the `card_key` + `billing_cycle` combination is not found in the duration map, the subscription defaults to **365 days**.

**Success Response — `200 OK`**

```json
{ "status": "ok" }
```

Razorpay expects a `200` response; any non-`200` triggers a retry. The endpoint is **idempotent** — duplicate `payment.captured` events for an already-successful transaction are safely ignored.

**Error Responses**

| Status | Condition                    | Body                              |
|--------|------------------------------|-----------------------------------|
| `400`  | Signature verification fails | `{"error": "Invalid signature"}`  |

> **Note:** Configure `RAZORPAY_WEBHOOK_SECRET` in your Django settings to enable signature verification. Without it, all webhook requests are accepted without validation.

---

### 3. Payment History

Returns a list of all payment transactions for the authenticated user, ordered most-recent first.

```
GET /api/payments/history/
```

**Authentication:** Required (Bearer token / session)

**Success Response — `200 OK`**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "razorpay_order_id": "order_QxYzABC123",
    "razorpay_payment_id": "pay_QxYzABC456",
    "amount": "999.00",
    "currency": "INR",
    "plan_type": "tool",
    "card_key": "discipline_tools",
    "billing_cycle": "monthly",
    "status": "success",
    "paid_at": "2025-01-15T10:30:00Z",
    "created_at": "2025-01-15T10:28:00Z"
  }
]
```

The `user` field is excluded from the response (server-side only).

**Error Responses**

| Status | Condition               |
|--------|-------------------------|
| `401`  | Unauthenticated request |

---

### 4. Admin — All Payments

Returns all payment transactions across all users. Intended for internal admin dashboards.

```
GET /api/admin/payments/
```

**Authentication:** Custom admin auth (`IsAdminAuthenticated`). Standard user tokens are not accepted.

**Success Response — `200 OK`**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_name": "Jane Doe",
    "email": "jane@example.com",
    "amount": 999.0,
    "plan_type": "tool",
    "card_key": "discipline_tools",
    "billing_cycle": "monthly",
    "status": "success",
    "paid_at": "2025-01-15T10:30:00Z",
    "created_at": "2025-01-15T10:28:00Z"
  }
]
```

| Field            | Description                                               |
|------------------|-----------------------------------------------------------|
| `id`             | Transaction UUID                                          |
| `user_name`      | Full name of the user, falls back to email if blank       |
| `email`          | User's email address                                      |
| `amount`         | Amount in INR as a float                                  |
| `plan_type`      | One of `tool`, `learning`, `both`                         |
| `card_key`       | CMS card key that was purchased                           |
| `billing_cycle`  | Billing cycle of the purchased plan                       |
| `status`         | Transaction status                                        |
| `paid_at`        | Payment confirmation timestamp (null if not paid)         |
| `created_at`     | Order creation timestamp                                  |

Results are ordered by `created_at` descending (newest first).

---

## Plan Types & Pricing

Prices are **dynamic** — managed via the CMS `PricingPlan` model and editable by admins at any time. The table below reflects the default seed values.

| `card_key`         | `plan_type` | Label                        | Default Price (INR) | Billing Cycle |
|--------------------|-------------|------------------------------|---------------------|---------------|
| `discipline_tools` | `tool`      | Discipline Tools (monthly)   | ₹999                | Monthly       |
| `discipline_tools` | `tool`      | Discipline Tools (yearly)    | ₹9,999              | Yearly        |
| `learning_hub`     | `learning`  | Learning Hub                 | ₹2,999              | 6 Months      |
| `combo_monthly`    | `both`      | Complete System – Monthly    | ₹1,399              | Monthly       |
| `combo_annual`     | `both`      | Complete System – Annual     | ₹12,999             | Annual        |

> Prices shown above are illustrative defaults. Always fetch live prices from `GET /api/cms/pricing/` before displaying them to users.

---

## Transaction Statuses

| Status     | Description                                                          |
|------------|----------------------------------------------------------------------|
| `pending`  | Order created; payment not yet confirmed                             |
| `success`  | Payment captured via webhook; subscription activated                 |
| `failed`   | Payment failed (only set if previously `pending`)                    |
| `refunded` | Payment refunded (set manually or via future refund flow)            |

---

## Settings Reference

The following Django settings are required for the payments app:

| Setting                    | Description                                                        |
|----------------------------|--------------------------------------------------------------------|
| `RAZORPAY_KEY_ID`          | Razorpay public API key                                            |
| `RAZORPAY_KEY_SECRET`      | Razorpay secret API key                                            |
| `RAZORPAY_WEBHOOK_SECRET`  | Webhook signing secret (optional but strongly recommended)         |
