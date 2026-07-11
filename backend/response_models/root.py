from pydantic import BaseModel


class RootResponse(BaseModel):
    """Health-check payload returned by GET /."""

    status: str
    message: str
    version: str
