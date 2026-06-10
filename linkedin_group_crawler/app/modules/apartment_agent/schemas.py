"""Pydantic models for the apartment agent pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Optional

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
    title: str = Field(default="", description="Listing title")
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
    images: list[str] = Field(default_factory=list, description="Image URLs")


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


class PipelineResult(BaseModel):
    """Aggregate result for a batch of messages."""

    total_processed: int = 0
    extracted: int = 0
    duplicates: int = 0
    inserted: int = 0
    failed: int = 0
    results: list[SyncResult] = Field(default_factory=list)
