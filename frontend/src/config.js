// Defaults to the live FastAPI backend deployed on Azure Container Apps.
// For local development against `uvicorn api:app --reload`, set
// VITE_API_BASE=http://127.0.0.1:8000 in frontend/.env.local.
export const API_BASE = (
  import.meta.env.VITE_API_BASE ||
  "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io"
).replace(/\/+$/, "");

// The AI service owns the model key and prompt logic. Keeping the URL overridable
// lets preview environments point at a different Cloud Run service when needed.
export const INTELLIGENCE_BASE = (
  import.meta.env.VITE_NHL_INTELLIGENCE_URL ||
  "https://nhl-intelligence.bravecoast-a5240643.westus2.azurecontainerapps.io"
).replace(/\/+$/, "");

export const DIVISION_ORDER = ["Atlantic", "Metropolitan", "Central", "Pacific"];
