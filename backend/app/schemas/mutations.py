from typing import Literal

from pydantic import Field, FiniteFloat, model_validator

from app.schemas.common import ApiModel

MutationStrategy = Literal["explicit", "range", "random"]
CombinationMode = Literal["one-at-a-time", "cartesian"]


class MutationSettings(ApiModel):
    strategy: MutationStrategy
    explicit_values: list[FiniteFloat] = Field(default_factory=list, max_length=1000)
    range_start: FiniteFloat = 0
    range_end: FiniteFloat = 1
    range_step: FiniteFloat = 0.1
    random_spread: FiniteFloat = 0.5
    random_count: int = Field(default=5, ge=1, le=1000)
    seed: int = 41


class MutationProfileFields(ApiModel):
    name: str = Field(min_length=1, max_length=150)
    field_keys: list[str] = Field(min_length=1, max_length=100)
    settings: MutationSettings
    combination_mode: CombinationMode

    @model_validator(mode="after")
    def validate_name(self) -> "MutationProfileFields":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Profile name must not be blank.")
        return self


class MutationProfileCreate(MutationProfileFields):
    pass


class MutationProfileUpdate(MutationProfileFields):
    pass


class MutationProfileResponse(MutationProfileFields):
    id: str
    created_at: str
    updated_at: str


class MutationProfileList(ApiModel):
    profiles: list[MutationProfileResponse]
    total: int


class MutationProfileValidation(ApiModel):
    compatible: bool
    issues: list[dict[str, str]]


class EvidenceVariant(ApiModel):
    id: str
    values: dict[str, FiniteFloat]
    changed_fields: list[str]


class VariantPreviewRequest(ApiModel):
    snapshot_id: str
    field_keys: list[str] = Field(min_length=1, max_length=100)
    settings: MutationSettings
    combination_mode: CombinationMode


class VariantPreviewResponse(ApiModel):
    variants: list[EvidenceVariant]
    total_count: int
    preview_limit: int


class VariantGenerateRequest(ApiModel):
    snapshot_id: str
    profile_id: str | None = None
    field_keys: list[str] | None = Field(default=None, min_length=1, max_length=100)
    settings: MutationSettings | None = None
    combination_mode: CombinationMode | None = None

    @model_validator(mode="after")
    def require_configuration(self) -> "VariantGenerateRequest":
        if self.profile_id is None and (
            self.field_keys is None or self.settings is None or self.combination_mode is None
        ):
            raise ValueError("Provide profileId or all of fieldKeys, settings, and combinationMode.")
        return self


class VariantGenerateResponse(ApiModel):
    batch_id: str
    variant_ids: list[str]
    total_generated: int
    generator_version: str
    created_at: str


class VariantBatchResponse(ApiModel):
    id: str
    snapshot_id: str
    profile_id: str | None
    profile_snapshot: dict | None
    mutation_config: dict
    generator_version: str
    total_generated: int
    created_at: str
    variants: list[EvidenceVariant]


class VariantBatchList(ApiModel):
    batches: list[VariantBatchResponse]
    total: int
