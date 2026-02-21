# RingAI - AI Phone Order Management Platform for Restaurants

## Overview
RingAI is a comprehensive SaaS platform that provides AI-powered phone reception and order management for restaurants. Inspired by slang.ai, it handles incoming calls, books reservations, processes takeout/delivery orders, and provides analytics — all using AI voice technology.

## Tech Stack
- **Frontend**: React.js, Tailwind CSS, shadcn/ui, Recharts, Framer Motion
- **Backend**: Python FastAPI, Motor (async MongoDB driver)
- **Database**: MongoDB
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
- `POST /api/demo/simulate-call` - Generate demo call
- `POST /api/demo/seed` - Seed historical data
- `POST /api/onboarding/menu/parse` - AI menu parsing
- `POST /api/onboarding/activate` - Activate restaurant

## Mock Data Notice
- **External APIs are MOCKED**: Twilio, Deepgram, ElevenLabs, Claude, POS integrations, Stripe, Clerk auth
- Call simulations generate realistic but synthetic data
- Menu parsing uses basic text parsing (not actual Claude API)
- Voice selection UI is present but audio playback is simulated
- All data is stored in MongoDB and persists between sessions

## Status
- ✅ All 9 test categories passing
- ✅ Mobile responsive on all pages
- ✅ Backend API fully operational with seed data
- ✅ Real-time live call simulation working
- ✅ All CRUD operations functional
- ✅ Charts and analytics rendering correctly
