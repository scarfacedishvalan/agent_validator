from datetime import date
from typing import Annotated

from pydantic import Field, FiniteFloat, field_validator

from app.schemas.common import ApiModel


class EvidenceSnapshotCreate(ApiModel):
    name: Annotated[str, Field(min_length=1, max_length=150)]
    as_of: date
    values: dict[str, FiniteFloat]

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Snapshot name must not be blank.")
        return cleaned

    @field_validator("values")
    @classmethod
    def values_must_not_be_empty(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("Snapshot must contain at least one numeric field.")
        return value


class EvidenceSnapshotResponse(ApiModel):
    id: str
    name: str
    as_of: date
    values: dict[str, float]
    created_at: str


class EvidenceSnapshotList(ApiModel):
    snapshots: list[EvidenceSnapshotResponse]
    total: int


class MetricDefinition(ApiModel):
    key: str
    label: str
    group: str
    unit: str
    display_scale: FiniteFloat = 1
    precision: int = Field(ge=0, le=12)
    mutation_eligible: bool
    description: str
