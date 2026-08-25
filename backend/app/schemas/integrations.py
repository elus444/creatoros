from pydantic import BaseModel, Field


class VideoProviderOption(BaseModel):
    id: str
    label: str


class VideoProviderPublic(BaseModel):
    provider: str
    supported_providers: list[VideoProviderOption]
    model_id: str | None = None
    has_key: bool = False
    configured: bool = False
    source: str | None = None


class VideoProviderSave(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    model_id: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=512)


class VideoProviderTestRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    api_key: str | None = Field(default=None, max_length=512)


class VideoProviderTestResult(BaseModel):
    ok: bool
    provider: str
    account: str | None = None
    message: str
