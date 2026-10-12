from typing import Literal

from pydantic import BaseModel


class ConnectivityResponse(BaseModel):
    backend: Literal["ok"] = "ok"
    ai_server: Literal["ok", "unreachable"]
