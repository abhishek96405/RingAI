# RingAI - AI Phone Order Management Platform for Restaurants

## Overview
RingAI is a comprehensive SaaS platform that provides AI-powered phone reception and order management for restaurants. Inspired by slang.ai, it handles incoming calls, books reservations, processes takeout/delivery orders, and provides analytics — all using AI voice technology.

## Tech Stack
- **Frontend**: React.js, Tailwind CSS, shadcn/ui, Recharts, Framer Motion
- **Backend**: Python FastAPI, Motor (async MongoDB driver)
- **Database**: MongoDB
- **AI**: Google Gemini 2.5 Flash (via Emergent LLM Gateway)
- **Design System**: Custom HSL token-based (teal primary + warm coral accent)
- **Typography**: Space Grotesk (headings), Inter (body)

## Current Status: Test Mode Ready

The application is fully functional with Test Mode infrastructure. All features work using:
- **Gemini AI**: Active via Emergent gateway (real AI responses)
- **Twilio**: Simulated (awaiting API keys)
- **Stripe**: Simulated (awaiting API keys)
- **Clerk**: Demo mode (awaiting API keys)

## Application Structure

### Landing Page (`/`)
- Hero section with animated call card visualization
- Logo bar with scrolling restaurant names
- 8 feature cards in bento grid
- 3-step "How it Works" process
- Interactive phone demo simulation
- 6 integration partner cards
- Testimonial carousel with navigation
- 3-tier pricing with monthly/annual toggle
- 7-item FAQ accordion
- Final CTA section + Footer

### Dashboard (`/dashboard`)
- 4 KPI stat cards (calls, revenue, quality score, containment rate)
- Call Volume & Revenue bar chart (Recharts)
- Hourly call distribution area chart
- Recent calls list with status badges
- Top ordered items ranking
- "Simulate Call" button for generating demo data

### Call History (`/calls`)
- Searchable, filterable call list with pagination
- Status filter (All, Completed, Escalated, Failed)
- Click-to-open detail sheet with:
  - Caller info, duration, quality score
  - Full order summary with items and totals
  - AI analysis (highlights, issues, summary)
  - Chat-style transcript view

### Menu Manager (`/menu`)
- Menu items grouped by category (21 items, 6 categories)
- CRUD operations: Add, Edit, Delete items
- Availability toggle switches
- Category filtering and search
- Allergen badges display
- Dialog form for add/edit with allergen selector

### Live Monitor / Test Mode (`/live`)
- **NEW**: Test Mode UI with predefined scenarios
- 6 test scenarios: Simple Pickup, Delivery with Upsell, Reservation, Complex Order, Allergy Question, Escalation
- Real-time animated transcript display
- Live cart that updates as items are ordered
- Call info panel (status, duration, AI model, mode)
- Quality score and AI analysis display after completion

### Settings (`/settings`)
- **General**: Restaurant info, timezone, phone number
- **Voice & AI**: Persona selection, 5 voice options, greeting, upsell/delivery toggles
- **Rules**: Business rules CRUD, Escalation triggers CRUD
- **Integrations**: NEW tab showing status of all integrations with required API keys
- **Billing**: Plan info, usage stats, subscription management

### Onboarding (`/onboarding`)
- 4-step wizard with animated progress bar
- Step 1: Restaurant info form
- Step 2: Menu text parsing (AI-powered with Gemini)
- Step 3: AI persona & voice configuration
- Step 4: Activation with demo data seeding

## Backend API Endpoints

### Core APIs
- `GET/POST /api/restaurants` - Restaurant CRUD
- `GET/PUT /api/restaurants/{id}/config` - AI configuration
- `GET/POST /api/restaurants/{id}/menu` - Menu management
- `PUT/DELETE/PATCH /api/menu/{id}` - Item operations
- `GET /api/restaurants/{id}/calls` - Call history with filters
- `GET /api/calls/{id}` - Call detail with transcript
- `POST /api/calls/{id}/analyse` - Re-run AI analysis
- `GET /api/restaurants/{id}/analytics/summary` - Dashboard analytics

### Test Mode APIs (NEW)
- `GET /api/status` - Service health with integration statuses
- `GET /api/test-mode/status` - Detailed integration status for all services
- `GET /api/test-mode/scenarios` - Available test call scenarios
- `POST /api/test-mode/run-scenario` - Execute test scenario with Gemini AI

### Onboarding & Demo APIs
- `POST /api/onboarding/menu/parse` - AI menu parsing (uses Gemini)
- `POST /api/onboarding/activate` - Activate restaurant
- `POST /api/demo/simulate-call` - Legacy demo call generation
- `POST /api/demo/seed` - Seed historical data

## Completed Work

### Feb 21, 2026 - Test Mode Infrastructure
- **Test Mode Backend**: Created `/app/backend/test_mode.py` with IntegrationStatus class
- **6 Test Scenarios**: Simple Pickup, Delivery, Reservation, Complex Order, Allergy Question, Escalation
- **New APIs**: `/api/test-mode/status`, `/api/test-mode/scenarios`, `/api/test-mode/run-scenario`
- **LiveMonitor.js**: Completely rewritten for Test Mode UI with animated transcript
- **Settings Integrations Tab**: Shows status of Gemini, Twilio, Stripe, Clerk with API key instructions
- **API Client**: Added new functions for test mode in `/app/frontend/src/lib/api.js`

### Feb 21, 2026 - P0/P1 Bug Fixes
- **P0 FIXED**: Post-call analysis JSON parsing errors with `_repair_json()` function
- **P1 FIXED**: "Budget Exceeded" errors with conversation context summarization

### Previous Session
- Landing Page & Dashboard UI complete
- Backend Foundation with FastAPI
- AI Stack pivot to Gemini 2.5 Flash
- All CRUD operations functional

## API Keys Required for Live Features

When ready to go live, add these environment variables to `/app/backend/.env`:

```bash
# Twilio (for live phone calls)
TWILIO_ACCOUNT_SID=ACxxxxxx
TWILIO_AUTH_TOKEN=xxxxxx
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx

# Stripe (for billing)
STRIPE_SECRET_KEY=sk_test_xxxxx  # Use sk_test_ for sandbox
STRIPE_PUBLISHABLE_KEY=pk_test_xxxxx

# Clerk (for authentication)
CLERK_PUBLISHABLE_KEY=pk_test_xxxxx
CLERK_SECRET_KEY=sk_test_xxxxx
```

## Files of Reference
- `/app/backend/server.py` - Main FastAPI application with all endpoints
- `/app/backend/gemini_service.py` - Gemini AI integration with JSON repair
- `/app/backend/test_mode.py` - Test mode infrastructure and scenarios
- `/app/backend/call_pipeline.py` - Pipecat integration (ready for Twilio)
- `/app/frontend/src/pages/LiveMonitor.js` - Test Mode UI
- `/app/frontend/src/pages/Settings.js` - Settings with Integrations tab
- `/app/frontend/src/lib/api.js` - API client functions
- `/app/test_reports/iteration_2.json` - Latest test results (all passing)

## Test Credentials
- **Restaurant ID**: demo-restaurant-001
- **Restaurant Name**: Bella Cucina
- **API URL**: https://ringai-preview.preview.emergentagent.com

## Upcoming Tasks (When API Keys Available)

### With Twilio Keys
1. Connect Pipecat audio pipeline for real-time calls
2. Configure webhook endpoints for incoming calls
3. Provision and assign phone numbers

### With Stripe Keys
1. Create subscription checkout flow
2. Implement customer portal for billing management
3. Add usage-based metering

### With Clerk Keys
1. Add authentication middleware
2. Protect dashboard routes
3. Replace demo restaurant with user-specific data
