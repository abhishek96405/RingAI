# RingAI (Local / Emergent-free)

This version has been updated to run without any EmergentAI dependency.

## What changed
- Removed the Emergent gateway from Gemini calls.
- Switched Gemini to the official Google OpenAI-compatible endpoint.
- Removed the `emergentintegrations` backend dependency.
- Removed Emergent scripts and branding from the frontend.
- Disabled Emergent visual-edit tooling by default.
- Added local defaults for backend/frontend URLs.
- Added `.env.example` files for local setup.

## Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB running locally on `mongodb://localhost:27017`

## Backend setup
```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
uvicorn server:app --reload --host 0.0.0.0 --port 8001
```

## Frontend setup
```bash
cd frontend
npm install
cp .env.example .env
npm start
```

The frontend will run on `http://localhost:3000` and call the backend at `http://localhost:8001`.

## API keys
### Required for real AI responses
- `GOOGLE_API_KEY` (or `GOOGLE_GENAI_API_KEY`)

### Required only for real phone calls / SMS / Telnyx integration
- `TELNYX_API_KEY`
- `TELNYX_PUBLIC_KEY`
- `TELNYX_MESSAGING_PROFILE_ID`
- `TELNYX_TEXML_APP_ID`
- `TELNYX_CONNECTION_ID`
- `TELNYX_PHONE_NUMBER`

If you do not provide a Gemini key, the app still runs using mock AI responses for demo/testing flows.

## Notes
- Live phone-call audio uses Pipecat + Gemini Live + Telnyx. That is not an Emergent dependency.
- If MongoDB is not installed locally, you can point `MONGO_URL` to MongoDB Atlas instead.
