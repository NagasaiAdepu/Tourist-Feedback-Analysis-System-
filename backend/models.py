"""Pydantic models for API requests."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

VisitorType = Literal["family", "friends", "solo", "couple", "school_trip", "foreign_tourist"]


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=3, max_length=5000)


class ReviewIn(BaseModel):
    attraction_id: int = Field(gt=0)
    reviewer_name: Optional[str] = Field(None, max_length=60)
    visitor_type: VisitorType = "family"
    rating: int = Field(ge=1, le=5)
    visit_date: Optional[date] = None
    text: str = Field(min_length=10, max_length=3000)

    @field_validator("text")
    @classmethod
    def text_has_words(cls, v: str) -> str:
        if len(v.split()) < 3:
            raise ValueError("Please write at least a few words about your visit")
        return v.strip()

    @field_validator("visit_date")
    @classmethod
    def not_in_future(cls, v: Optional[date]) -> Optional[date]:
        if v and v > date.today():
            raise ValueError("Visit date cannot be in the future")
        return v
