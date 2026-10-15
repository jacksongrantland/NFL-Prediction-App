"""Source lineage contract for future immutable raw downloads."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class SourceManifest(BaseModel):
    """Retrieval and source publication are deliberately independent facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["source-manifest/1"] = "source-manifest/1"
    dataset: str = Field(min_length=1)
    season: int = Field(ge=1999, le=2100)
    source_url: HttpUrl
    retrieved_at: AwareDatetime
    source_published_at: AwareDatetime | None = None
    source_updated_at: AwareDatetime | None = None
    available_at: AwareDatetime | None = None
    availability_evidence: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checksum_scope: Literal["full_artifact", "sample_prefix"]
    byte_count: int = Field(gt=0)
    source_schema_version: str = Field(min_length=1)
    coverage: Literal["sample_only", "partial_season", "season_validated"]
    attribution_url: HttpUrl
    redistribution_status: Literal["review_required", "attribution_required"]

    @model_validator(mode="after")
    def require_availability_evidence(self) -> "SourceManifest":
        if self.available_at is not None and not self.availability_evidence:
            raise ValueError("available_at requires explicit availability_evidence")
        if self.available_at is not None and self.available_at > self.retrieved_at:
            raise ValueError("available_at cannot be later than retrieved_at")
        if self.checksum_scope == "sample_prefix" and self.coverage != "sample_only":
            raise ValueError("A prefix checksum cannot establish season coverage")
        return self
