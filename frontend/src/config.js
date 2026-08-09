// Points at the live FastAPI backend deployed on Azure Container Apps.
// For local development against `uvicorn api:app --reload`, swap this
// back to "http://127.0.0.1:8000".
export const API_BASE = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io";

// The AI service owns the model key and prompt logic. Keeping the URL overridable
// lets preview environments point at a different Cloud Run service when needed.
export const INTELLIGENCE_BASE = (
  import.meta.env.VITE_NHL_INTELLIGENCE_URL ||
  "https://nhl-intelligence-kaxll7b4fq-uk.a.run.app"
).replace(/\/+$/, "");

export const DIVISION_ORDER = ["Atlantic", "Metropolitan", "Central", "Pacific"];
