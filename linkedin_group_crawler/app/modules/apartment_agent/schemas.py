"""Pydantic models for the apartment agent pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from typing import Literal

from pydantic import BaseModel, Field


class ListingType(str, Enum):
    RENT = "rent"
    SALE = "sale"


class ApartmentListing(BaseModel):
    """Structured apartment data extracted from a Zalo message."""

    is_apartment_listing: bool = Field(
        default=False,
        description="Whether the message is actually an apartment listing",
    )
    title: str = Field(
        default="",
        description=(
            "Short professional listing title, formatted as '<Project> <Unit>' "
            "(e.g. 'Sunshine Riverside A1205', 'Monarchy Bach Dang 2001', "
            "'FPT City 801'). Strip leading all-caps prefixes like 'CHO THUE' / "
            "'CAN CHO THUE' / 'BAN' / 'CAN BAN', strip emoji and marketing "
            "fluff. Use Title Case with Vietnamese diacritics. Fall back to "
            "'<Project>' or '<District> apartment' if no project name is "
            "detected. Never invent a unit code."
        ),
    )
    price: Optional[float] = Field(default=None, description="Price in VND")
    area_sqm: Optional[float] = Field(default=None, description="Area in square meters")
    bedrooms: Optional[int] = Field(default=None, description="Number of bedrooms")
    district: Optional[str] = Field(
        default=None,
        description="Da Nang district (Hải Châu, Sơn Trà, Ngũ Hành Sơn, etc.)",
    )
    listing_type: Optional[ListingType] = Field(
        default=None, description="rent or sale"
    )
    contact_name: Optional[str] = Field(default=None, description="Contact person name")
    contact_phone: Optional[str] = Field(default=None, description="Contact phone number")
    amenities: list[str] = Field(default_factory=list, description="List of amenities")
    images: list[str] = Field(
        default_factory=list,
        description=(
            "Image URLs. The extractor should pass through any URLs the "
            "caller appended to the user message — do not invent URLs."
        ),
    )
    is_rented: bool = Field(default=False, description="Whether the room/unit is currently rented/occupied")
    address: Optional[str] = Field(default=None, description="Full address for dedup matching (street, floor, room number)")


class ExtractionStatus(str, Enum):
    SUCCESS = "success"
    NOT_LISTING = "not_listing"
    EXTRACTION_FAILED = "extraction_failed"


class ExtractionResult(BaseModel):
    """Result of LLM extraction for a single message."""

    raw_message_id: str = Field(description="Original message ID from crawl")
    status: ExtractionStatus = Field(description="Extraction outcome")
    listing: Optional[ApartmentListing] = Field(default=None)
    error_message: Optional[str] = Field(default=None)


class DedupResult(BaseModel):
    """Result of deduplication check for a single listing."""

    listing: ApartmentListing = Field(description="The extracted listing")
    is_duplicate: bool = Field(description="Whether this is a duplicate")
    matched_existing_id: Optional[int] = Field(
        default=None, description="ID of matching existing apartment"
    )
    similarity_score: Optional[float] = Field(
        default=None, description="Token sort ratio score"
    )


class SyncStatus(str, Enum):
    INSERTED = "inserted"
    UPDATED = "updated"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_NOT_LISTING = "skipped_not_listing"
    FAILED = "failed"


class SyncResult(BaseModel):
    """Final result for a single message through the full pipeline."""

    message_id: str = Field(description="Original message ID")
    extraction_status: ExtractionStatus
    is_duplicate: bool = False
    sync_status: SyncStatus
    apartment_id: Optional[int] = Field(
        default=None, description="ID of inserted apartment"
    )
    error_message: Optional[str] = None


class ClassificationResult(BaseModel):
    """Result of the classifier step for a single message."""

    is_listing: bool = Field(description="Whether this message is an apartment listing")
    reason: str = Field(default="", description="Classifier reasoning")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")


class ApartmentAgentError(BaseModel):
    """Typed error envelope for the apartment agent module."""

    kind: Literal["missing_config", "llm_auth", "llm_schema", "llm_rate_limit", "godanang_rest", "validation"]
    message: str
    missing: list[str] = Field(default_factory=list)
    status: int | None = None
    request_id: str = ""


class PipelineResult(BaseModel):
    """Aggregate result for a batch of messages."""

    total_processed: int = 0
    extracted: int = 0
    duplicates: int = 0
    inserted: int = 0
    failed: int = 0
    results: list[SyncResult] = Field(default_factory=list)
