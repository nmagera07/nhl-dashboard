from pydantic import BaseModel


class RootResponse(BaseModel):
    """Static "the API process is running" payload returned by GET /. Does
    not check the database -- see HealthResponse / GET /health for that."""

    status: str
    message: str
    version: str


class HealthResponse(BaseModel):
    """
    GET /health -- unlike GET /, this actually exercises the database
    connection (a SELECT 1 on the read-only role) rather than just
    confirming the process is up. Meant for Azure Container Apps'
    liveness/readiness probes and any external uptime monitor.

    commit is the git SHA the running image was built from ("unknown"
    for local runs), so deploys and the drift check can confirm
    production is running the code on main.
    """

    status: str
    database: str
    commit: str
