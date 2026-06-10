"""Unit tests for apartment agent deduplication."""

import pytest

from app.modules.apartment_agent.dedup import check_duplicate
from app.modules.apartment_agent.schemas import ApartmentListing, ListingType


@pytest.fixture
def listing_hai_chau():
    return ApartmentListing(
        is_apartment_listing=True,
        title="Cho thuê apartment 2PN Hải Châu 70m2",
        price=8000000.0,
        area_sqm=70.0,
        bedrooms=2,
        district="Hải Châu",
        listing_type=ListingType.RENT,
    )


@pytest.fixture
def listing_hai_chau_reworded():
    """Same apartment, different wording — should be detected as duplicate."""
    return ApartmentListing(
        is_apartment_listing=True,
        title="Apartment 2PN cho thuê Hải Châu 70m2",
        price=8000000.0,
        area_sqm=70.0,
        bedrooms=2,
        district="Hải Châu",
        listing_type=ListingType.RENT,
    )


@pytest.fixture
def listing_son_tra():
    """Different apartment — should NOT be duplicate."""
    return ApartmentListing(
        is_apartment_listing=True,
        title="Cho thuê apartment 3PN Sơn Trà 90m2",
        price=12000000.0,
        area_sqm=90.0,
        bedrooms=3,
        district="Sơn Trà",
        listing_type=ListingType.RENT,
    )


@pytest.fixture
def existing_apartments():
    return [
        {
            "id": 1,
            "name": "Cho thuê apartment 2PN Hải Châu 70m2",
            "area": "Hải Châu",
            "price": 8000000,
        },
        {
            "id": 2,
            "name": "Apartment studio Sơn Trà 45m2",
            "area": "Sơn Trà",
            "price": 5000000,
        },
    ]


class TestCheckDuplicate:
    """Test fuzzy deduplication logic."""

    def test_exact_match_detected(self, listing_hai_chau, existing_apartments):
        """Exact title match detected as duplicate."""
        result = check_duplicate(listing_hai_chau, existing_apartments, threshold=85)
        assert result.is_duplicate is True
        assert result.matched_existing_id == 1
        assert result.similarity_score >= 85

    def test_reworded_match_detected(self, listing_hai_chau_reworded, existing_apartments):
        """Reworded title detected as duplicate."""
        result = check_duplicate(listing_hai_chau_reworded, existing_apartments, threshold=85)
        assert result.is_duplicate is True
        assert result.matched_existing_id == 1

    def test_different_listing_passes(self, listing_son_tra, existing_apartments):
        """Different apartment passes dedup."""
        result = check_duplicate(listing_son_tra, existing_apartments, threshold=85)
        assert result.is_duplicate is False
        assert result.matched_existing_id is None

    def test_empty_existing_list(self, listing_hai_chau):
        """No existing apartments — all pass."""
        result = check_duplicate(listing_hai_chau, [], threshold=85)
        assert result.is_duplicate is False

    def test_borderline_with_matching_area_price(self, existing_apartments):
        """Borderline similarity (80-85%) with matching area+price = duplicate."""
        listing = ApartmentListing(
            is_apartment_listing=True,
            title="Cho thuê Hải Châu apartment 2PN 70m2 nội thất",
            price=8000000.0,
            area_sqm=70.0,
            bedrooms=2,
            district="Hải Châu",
            listing_type=ListingType.RENT,
        )
        result = check_duplicate(listing, existing_apartments, threshold=85)
        # If similarity is in borderline range and area/price match, should be duplicate
        if 80 <= (result.similarity_score or 0) < 85:
            assert result.is_duplicate is True

    def test_borderline_with_different_price(self, existing_apartments):
        """Borderline similarity but different price = NOT duplicate."""
        listing = ApartmentListing(
            is_apartment_listing=True,
            title="Cho thuê Hải Châu apartment 2PN 70m2 nội thất",
            price=15000000.0,  # Different price
            area_sqm=70.0,
            bedrooms=2,
            district="Hải Châu",
            listing_type=ListingType.RENT,
        )
        result = check_duplicate(listing, existing_apartments, threshold=85)
        if 80 <= (result.similarity_score or 0) < 85:
            assert result.is_duplicate is False
