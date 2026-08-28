from datetime import datetime

from pydantic import BaseModel


class MetaResponse(BaseModel):
    app: str
    environment: str
    server_time: datetime
    database: str
