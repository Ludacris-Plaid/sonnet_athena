from pydantic import BaseModel


class SetSettingRequest(BaseModel):
    key: str
    value: str
