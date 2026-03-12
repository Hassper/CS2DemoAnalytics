from pydantic import BaseModel


class UploadResponse(BaseModel):
    match_id: int
    message: str


class MatchSummary(BaseModel):
    id: int
    demo_filename: str
    map_name: str
    uploaded_at: str
    total_rounds: int


class AnalyticsResponse(BaseModel):
    match_id: int
    overview: dict
    round_stats: list[dict]
    engagement_stats: dict
    custom_metrics: dict
    charts: dict
