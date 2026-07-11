// Points at the live FastAPI backend deployed on Azure Container Apps.
// For local development against `uvicorn api:app --reload`, swap this
// back to "http://127.0.0.1:8000".
export const API_BASE = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io";

export const DIVISION_ORDER = ["Atlantic", "Metropolitan", "Central", "Pacific"];
