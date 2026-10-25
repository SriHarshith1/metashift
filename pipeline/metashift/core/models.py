from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Direction = Literal["buff", "nerf", "adjust"]
Verdict = Literal["rise", "fall", "stable"]
Confidence = Literal["low", "medium", "high"]


class Change(BaseModel):
    entity: str
    entity_type: str
    target: str
    stat: str
    old: str | None
    new: str | None
    direction: Direction
    source_quote: str = Field(min_length=1)


class ChangesFile(BaseModel):
    game: str
    patch: str
    changes: list[Change]


class EntityStats(BaseModel):
    entity: str
    win_rate: float | None = Field(ge=0, le=100)
    pick_rate: float | None = Field(ge=0, le=100)
    ban_rate: float | None = Field(ge=0, le=100)
    tier: str | None


class HistoryEntry(BaseModel):
    patch: str
    direction: Direction
    summary: str


class BaselineEntity(BaseModel):
    win_rate: float | None
    pick_rate: float | None
    ban_rate: float | None
    tier: str | None
    history: list[HistoryEntry] = []


class BaselineFile(BaseModel):
    stats_patch: str | None
    stats_source: str
    entities: dict[str, BaselineEntity]


class PreviousStats(BaseModel):
    win_rate: float | None
    pick_rate: float | None
    ban_rate: float | None
    tier: str | None


class EntityVerdict(BaseModel):
    entity: str
    entity_type: str
    verdict: Verdict
    confidence: Confidence
    previous: PreviousStats | None
    reason: str
    change_refs: list[Annotated[int, Field(ge=0)]]
    icon_url: str | None = None
    # Optional so reports written before impact analysis still load.
    impact: str | None = None
    build_shift: str | None = None


class RippleEntity(BaseModel):
    entity: str
    entity_type: str
    icon_url: str | None = None


class Ripple(BaseModel):
    title: str
    explanation: str
    entities: list[RippleEntity]


class ReportFile(BaseModel):
    game: str
    patch: str
    compared_to: str | None
    generated_at: datetime
    llm: str
    headline: str
    themes: list[str]
    entities: list[EntityVerdict]
    changes: list[Change]
    warnings: list[str]
    ripples: list[Ripple] = []


class IndexEntry(BaseModel):
    patch: str
    patch_date: date | None
    headline: str
    buffs: int
    nerfs: int
    llm: str


class IndexFile(BaseModel):
    games: dict[str, list[IndexEntry]]


class StageLog(BaseModel):
    stage: str
    llm: str | None
    duration_s: float
    retries: int
    warnings: list[str]


class RunLog(BaseModel):
    game: str
    patch: str
    patch_date: date | None = None
    stages: list[StageLog] = []


class ExtractDraft(BaseModel):
    changes: list[Change]


class VerdictDraft(BaseModel):
    entity: str
    verdict: Verdict
    confidence: Confidence
    reason: str
    impact: str
    build_shift: str | None = None


class RippleDraft(BaseModel):
    title: str
    explanation: str
    entities: list[str]


class AnalysisDraft(BaseModel):
    headline: str
    themes: list[str]
    entities: list[VerdictDraft]
    ripples: list[RippleDraft]
