// Defaults to the live FastAPI backend deployed on Azure Container Apps.
// For local development against `uvicorn api:app --reload`, set
// VITE_API_BASE=http://127.0.0.1:8000 in frontend/.env.local.
export const API_BASE = (
  import.meta.env.VITE_API_BASE ||
  "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io"
).replace(/\/+$/, "");

// NHL Intelligence (intelligence/, on Azure Container Apps) owns the AI provider
// keys and prompt logic. Overridable so local development can point at a local
// service (e.g. VITE_NHL_INTELLIGENCE_URL=http://localhost:8001).
export const INTELLIGENCE_BASE = (
  import.meta.env.VITE_NHL_INTELLIGENCE_URL ||
  "https://nhl-intelligence.bravecoast-a5240643.westus2.azurecontainerapps.io"
).replace(/\/+$/, "");

export const DIVISION_ORDER = ["Atlantic", "Metropolitan", "Central", "Pacific"];
