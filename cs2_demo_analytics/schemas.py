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
    parse_source: str


class AnalyticsResponse(BaseModel):
    match_id: int
    match_info: dict
    players: list[dict]
    selected_player: str
    overview: dict
    round_stats: list[dict]
    engagement_stats: dict
    custom_metrics: dict
    charts: dict
