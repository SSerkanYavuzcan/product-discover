from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SourceEvidence(BaseModel):
    source_id: str | None = None
    source_name: str
    source_type: str
    source_url: str | None = None
    field_name: str
    raw_value: str | int | float | bool | None
    normalized_value: str | int | float | bool | None = None
    confidence: float
    extracted_at: datetime

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0 <= value <= 1:
            msg = "confidence must be between 0 and 1"
            raise ValueError(msg)
        return value


class ProductImage(BaseModel):
    url: str
    image_type: str = "main"
    source_url: str | None = None
    confidence: float = 1.0

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0 <= value <= 1:
            msg = "confidence must be between 0 and 1"
            raise ValueError(msg)
        return value


class ConfidenceScore(BaseModel):
    overall: float
    field_scores: dict[str, float] = Field(default_factory=dict)

    @field_validator("overall")
    @classmethod
    def validate_overall(cls, value: float) -> float:
        if not 0 <= value <= 1:
            msg = "overall must be between 0 and 1"
            raise ValueError(msg)
        return value

    @field_validator("field_scores")
    @classmethod
    def validate_field_scores(cls, value: dict[str, float]) -> dict[str, float]:
        for field_name, score in value.items():
            if not 0 <= score <= 1:
                msg = f"field score for '{field_name}' must be between 0 and 1"
                raise ValueError(msg)
        return value
