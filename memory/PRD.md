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

### Live Monitor (`/live`)
- Real-time call simulation with chat bubbles
- Live cart that updates as items are ordered
- Call info panel (status, duration, model, voice)
- Action buttons (Take Over, Whisper, Mute)
- Sound wave animation during active calls

### Settings (`/settings`)
- **General**: Restaurant info, timezone, phone number
- **Voice & AI**: Persona selection, 5 voice options, greeting, upsell/delivery toggles
- **Rules**: Business rules CRUD, Escalation triggers CRUD
- **Billing**: Plan info, usage stats, subscription management

### Onboarding (`/onboarding`)
- 4-step wizard with animated progress bar
- Step 1: Restaurant info form
- Step 2: Menu text parsing (AI-powered)
- Step 3: AI persona & voice configuration
- Step 4: Activation with demo data seeding

## Backend API Endpoints
- `GET/POST /api/restaurants` - Restaurant CRUD
- `GET/PUT /api/restaurants/{id}/config` - AI configuration
- `GET/POST /api/restaurants/{id}/menu` - Menu management
- `PUT/DELETE/PATCH /api/menu/{id}` - Item operations
- `GET /api/restaurants/{id}/calls` - Call history with filters
- `GET /api/calls/{id}` - Call detail with transcript
- `GET /api/restaurants/{id}/analytics/summary` - Dashboard analytics
- `POST /api/demo/simulate-call` - Generate demo call (uses Gemini)
- `POST /api/demo/seed` - Seed historical data
- `POST /api/onboarding/menu/parse` - AI menu parsing (uses Gemini)
- `POST /api/onboarding/activate` - Activate restaurant
- `POST /api/calls/{id}/analyse` - Re-run Gemini analysis on existing call
- `GET /api/status` - Service health check

## Completed Work

### Feb 21, 2026 - P0/P1 Bug Fixes
- **P0 FIXED**: Post-call analysis JSON parsing errors
  - Added `_repair_json()` function to handle truncated strings and malformed JSON
  - Added `_extract_json_fields()` regex fallback for complete parse failures
  - Strengthened system prompt for JSON-only output
  - Increased max_tokens to 500 to prevent truncation
  - All tests passing (100% success rate on 5 consecutive simulate-call runs)

- **P1 FIXED**: "Budget Exceeded" errors in long conversations
  - Added `_summarize_conversation_context()` to limit transcript to 6 most relevant turns
  - Condensed system prompt for conversation calls
  - Truncated individual messages to max 300 chars
  - No budget exceeded errors in testing

### Previous Session Work
- Landing Page & Dashboard UI complete
- Backend Foundation with FastAPI
- AI Stack pivot to Gemini 2.5 Flash (from Claude/Deepgram/ElevenLabs)
- Gemini Integration for text-based call simulation
- Status endpoint for integration health monitoring

## Current Status

### Working Features
- ✅ Complete frontend UI (Landing, Dashboard, Calls, Menu, Live, Settings, Onboarding)
- ✅ Backend API fully operational
- ✅ MongoDB database with demo data seeding
- ✅ Gemini-powered call simulation with valid JSON analysis
- ✅ Menu parsing with Gemini
- ✅ Re-analysis of existing calls
- ✅ All CRUD operations functional
- ✅ Charts and analytics rendering correctly

### Mocked/Pending Features
- ⏳ **Twilio telephony** - Endpoints stubbed, awaiting API keys
- ⏳ **Pipecat audio pipeline** - Library installed, not integrated
- ⏳ **Clerk authentication** - Not integrated, using demo restaurant
- ⏳ **Stripe billing** - Not integrated
- ⏳ **POS integrations** - Not integrated

## Upcoming Tasks (Priority Order)

### P0 - Critical
None currently - all P0 bugs resolved

### P1 - High Priority
1. **Pipecat Real-time Audio Pipeline**: Bridge Twilio audio to Gemini Live Audio API
2. **Twilio Integration**: Enable live phone calls when API keys provided
3. **Clerk Authentication**: Secure dashboard routes with user auth

### P2 - Medium Priority
1. **Stripe Billing**: Subscription and payment integration
2. **Database Migration**: Consider PostgreSQL + Redis migration per original PRD

### P3 - Low Priority
1. **POS Integrations**: Toast, Square, Clover connectivity

## Files of Reference
- `/app/backend/gemini_service.py` - All Gemini AI logic (JSON repair, analysis, conversation)
- `/app/backend/server.py` - Main FastAPI application
- `/app/backend/call_pipeline.py` - Pipecat integration (stubbed)
- `/app/frontend/src/pages/` - All React page components
- `/app/test_reports/iteration_1.json` - Latest test results (all passing)

## Test Credentials
- **Restaurant ID**: demo-restaurant-001
- **Restaurant Name**: Bella Cucina
- **API URL**: https://ringai-preview.preview.emergentagent.com
