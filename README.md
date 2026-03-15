# BitsOfTrade 📈

A professional trading journal and discipline management platform for Indian retail traders. BitsOfTrade helps traders track their trades, analyze performance, enforce trading rules, and build long-term discipline through a data-driven approach.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Local Setup (Without Docker)](#local-setup-without-docker)
- [Docker Setup (Recommended)](#docker-setup-recommended)
- [Environment Variables](#environment-variables)
- [Running the Project](#running-the-project)
- [API Overview](#api-overview)
- [API Documentation](#api-documentation)
- [Postman Collections](#postman-collections)
- [Default Ports](#default-ports)

---

## Features

- **Trade Log** — Manual trade entry and bulk CSV/Excel import (Zerodha, Upstox, Groww, Generic)
- **Discipline Guard** — Automatic rule evaluation after every trade save. Session states: GREEN → YELLOW → RED
- **Rules Engine** — Configurable hard/soft trading rules (max daily loss, position size, max trades, consecutive losses)
- **Journal** — Daily journals, trade notes, psychology logs, session recaps, learning notes
- **Reports** — Performance, Risk, Behavior, Strategy, Journal, Mistakes, and Overview reports
- **Insights** — 12 proprietary metrics: DIS, VMI, DRT, TPR, FIE, OVR, ECI, CAS, DAE, SMI, DDR, CPI
- **Strategies** — Strategy library with community sharing, templates, and trade assignment
- **Mistakes** — Mistake library with analytics, trend tracking, and P&L impact analysis
- **JWT Authentication** — Email-based auth with Google OAuth2 support

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.0, Django REST Framework |
| Auth | JWT via `djangorestframework-simplejwt`, Google OAuth2 |
| Database | PostgreSQL |
| Containerisation | Docker, Docker Compose |
| Media Storage | Local filesystem (`/media/`) |

---

## Project Structure

```
bitsoftrade/
├── config/                  # Django project settings & root URLs
│   ├── settings.py
│   └── urls.py
├── accounts/                # User auth, registration, profile, subscriptions
├── tradelog/                # Core trade model, import engine, CRUD views
├── discipline/              # DisciplineSession, ViolationsLog, unlock flow
├── rules/                   # Rule model, rule evaluation engine
├── journal/                 # DailyJournal, TradeNote, PsychologyLog, SessionRecap, LearningNote
├── strategies/              # Strategy model, community, templates, trade assignment
├── mistakes/                # Mistake model, TradeMistake links, analytics
├── insights/                # 12 proprietary metrics, UserMetricSnapshot
├── reports/                 # Performance, Risk, Behavior, Strategy, Journal, Mistakes, Overview
├── trade_intelligence/      # (In development)
├── admin_panel/             # Custom admin management
├── API Documentation/       # Markdown docs for every module
├── Postman Collections/     # Postman JSON collections for every module
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── Pipfile
├── manage.py
└── .env_example
```

---

## Prerequisites

### For Local Setup (Without Docker)

- Python 3.11+
- PostgreSQL 14+
- pip

### For Docker Setup

- Docker Desktop (or Docker Engine + Docker Compose)

---

## Local Setup (Without Docker)

### 1. Clone the repository

```bash
git clone https://github.com/armmoon4/bitsoftrade.git
cd bitsoftrade
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up PostgreSQL

Create a database and user in PostgreSQL:

```sql
CREATE DATABASE bitsoftrade_db;
CREATE USER postgres WITH PASSWORD 'postgres_password';
GRANT ALL PRIVILEGES ON DATABASE bitsoftrade_db TO postgres;
```

### 5. Configure environment variables

Copy the example env file and fill in your values:

```bash
cp .env_example .env
```

Edit `.env` with your database credentials, email settings, and Google OAuth2 client ID. See [Environment Variables](#environment-variables) for all required values.

### 6. Apply database migrations

```bash
python manage.py migrate
```

### 7. Create a superuser (optional)

```bash
python manage.py createsuperuser
```

### 8. Run the development server

```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000`.

---

## Docker Setup (Recommended)

Docker handles the database, migrations, and server startup automatically.

### 1. Clone the repository

```bash
git clone https://github.com/armmoon4/bitsoftrade.git
cd bitsoftrade
```

### 2. Configure environment variables

```bash
cp .env_example .env
```

Edit `.env` with your values. The database host must be `db` (the Docker service name) — do not change it to `localhost`.

### 3. Build and start all services

```bash
docker-compose up --build
```

This will:
- Build the Django application image
- Start a PostgreSQL container (`db` service)
- Run `manage.py migrate` automatically
- Start the Django development server

### 4. Access the API

The API will be available at `http://localhost:13025`.

### Useful Docker commands

```bash
# Start services in the background
docker-compose up -d

# Stop all services
docker-compose down

# Stop and remove all volumes (wipes the database)
docker-compose down -v

# View live logs
docker-compose logs -f

# View logs for a specific service
docker-compose logs -f web

# Run a management command inside the container
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
docker-compose exec web python manage.py shell

# Rebuild after changing requirements.txt
docker-compose up --build

# Check running containers
docker-compose ps
```

---

## Environment Variables

Copy `.env_example` to `.env` and set the following values:

```env
# Database
DATABASE_NAME=bitsoftrade_db
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password_here
DATABASE_HOST=db          # use 'db' for Docker, 'localhost' for local setup
DATABASE_PORT=5432

# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
FRONTEND_URL=http://localhost:3000

# Email (Gmail SMTP)
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password_here

# Google OAuth2
GOOGLE_OAUTH2_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

> **Gmail App Password:** If using Gmail, generate an App Password from your Google account (Security → 2-Step Verification → App Passwords) rather than using your regular password.

> **Google OAuth2:** Get your client ID from the [Google Cloud Console](https://console.cloud.google.com/) under APIs & Services → Credentials.

---

## Running the Project

### Apply migrations after pulling new changes

**Local:**
```bash
python manage.py migrate
```

**Docker:**
```bash
docker-compose exec web python manage.py migrate
```

### Create a superuser

**Local:**
```bash
python manage.py createsuperuser
```

**Docker:**
```bash
docker-compose exec web python manage.py createsuperuser
```

### Collect static files (for production)

**Local:**
```bash
python manage.py collectstatic
```

**Docker:**
```bash
docker-compose exec web python manage.py collectstatic
```

---

## API Overview

All API endpoints are prefixed with `/api/`. JWT access token must be included in the `Authorization` header for all protected endpoints:

```
Authorization: Bearer <access_token>
```

| Module | Base URL | Description |
|--------|----------|-------------|
| Accounts | `/api/auth/` | Registration, login, logout, profile, password reset, Google login |
| Tradelog | `/api/tradelog/` | Trade CRUD and CSV/Excel import |
| Discipline | `/api/discipline/` | Session state, unlock flow, violations timeline |
| Rules | `/api/rules/` | Rule management and evaluation engine |
| Journal | `/api/journal/` | Daily journals, trade notes, psychology logs, recaps, learning notes |
| Strategies | `/api/strategies/` | Strategy library, community, templates, trade assignment |
| Mistakes | `/api/mistakes/` | Mistake library, trade links, analytics |
| Insights | `/api/insights/` | 12 proprietary metrics |
| Reports | `/api/reports/` | Performance, Risk, Behavior, Strategy, Journal, Mistakes, Overview |

### JWT Token Lifetime

| Token | Lifetime |
|-------|----------|
| Access Token | 15 days |
| Refresh Token | 30 days |

---

## API Documentation

Full Markdown documentation for every module is in the `API Documentation/` folder:

| File | Module |
|------|--------|
| `Account_API_Documentation.md` | Accounts |
| `Tradelog_API_Documentation.md` | Tradelog |
| `Discipline_API_Documentation.md` | Discipline |
| `Rules_API_Documentation.md` | Rules |
| `Journal_API_Documentation.md` | Journal |
| `Strategies_API_Documentation.md` | Strategies |
| `Mistakes_API_Documentation.md` | Mistakes |
| `Insights_API_Documentation.md` | Insights |
| `Reports_API_Documentation.md` | Reports |

---

## Postman Collections

Ready-to-use Postman collections are in the `Postman Collections/` folder. Import any `.json` file directly into Postman.

After importing, set these collection variables:

| Variable | Value |
|----------|-------|
| `baseUrl` | `http://localhost:13025` (Docker) or `http://localhost:8000` (local) |
| `access_token` | Your JWT access token from the login response |

### How to get your access token

1. Import `Account_API_postman_collection.json`
2. Send the **Login** request with your email and password
3. Copy the `access_token` from the response
4. Set it as the `access_token` collection variable

---

## Default Ports

| Service | Port |
|---------|------|
| Django API (Docker) | `13025` |
| Django API (Local) | `8000` |
| PostgreSQL | `5432` |

---

## Notes

- **Media files** (profile pictures) are stored in `/media/profiles/`. In development, Django serves them automatically when `DEBUG=True` and the media URL config is set in `config/urls.py`.
- **CORS** is currently open (`CORS_ALLOW_ALL_ORIGINS = True`) for development. Restrict this for production.
- **Rule Engine** fires automatically via Django `post_save` signal on every trade save — no manual trigger needed.
- **Discipline session** is auto-created for each trade date the first time a trade is saved for that date.
- The `trade_intelligence` app is currently in development and not yet documented.
