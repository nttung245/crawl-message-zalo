"""FastAPI router for the apartment agent pipeline."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from app.modules.apartment_agent.config import settings, validate_settings
from app.modules.apartment_agent.pipeline import process_messages
from app.modules.apartment_agent.schemas import (
    ApartmentAgentError,
    PipelineResult,
)

router = APIRouter(prefix="/api/apartment-agent", tags=["apartment-agent"])


class ProcessRequest(BaseModel):
    """Request to process specific messages or all messages from a group."""

    message_ids: Optional[list[str]] = None
    group_name: Optional[str] = None


class ProcessAllRequest(BaseModel):
    """Request to reprocess all unprocessed messages."""

    limit: int = 100


class TestExtractRequest(BaseModel):
    """Request to test extraction only (no dedup/sync)."""

    group_name: Optional[str] = None
    texts: Optional[list[str]] = None


class TestExtractListing(BaseModel):
    """Extracted listing data for test response."""

    apartment_name: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    bedrooms: Optional[int] = None
    price_vnd: Optional[float] = None
    area_m2: Optional[float] = None
    contact_phone: Optional[str] = None
    contact_zalo: Optional[str] = None
    image_count: int = 0
    images: list[str] = Field(default_factory=list)
    raw_text: str = ""


class TestExtractResult(BaseModel):
    """Result of extraction test for a single message."""

    raw_message_id: str
    raw_text: str = ""
    status: str  # "extracted" | "not_listing" | "failed"
    listing: Optional[TestExtractListing] = None
    error_message: Optional[str] = None


class TestExtractResponse(BaseModel):
    """Aggregate response for test extraction."""

    total: int = 0
    extracted: int = 0
    not_listing: int = 0
    failed: int = 0
    results: list[TestExtractResult] = Field(default_factory=list)


class PreviewListing(BaseModel):
    """Per-listing preview with the exact payload that would be written."""

    raw_message_id: str = ""
    raw_text: str = ""
    title: str = ""
    district: Optional[str] = None
    bedrooms: Optional[int] = None
    price_vnd: Optional[float] = None
    area_m2: Optional[float] = None
    image_count: int = 0
    payload: dict = Field(default_factory=dict, description="Exact body for GoDaNang POST/PUT")
    operation: str = ""  # "insert" | "update" | "skip"
    existing_villa_id: Optional[str] = None


class PreviewResponse(BaseModel):
    """Result of a preview (no-write) run."""

    total_messages_seen: int = 0
    classified_listing: int = 0
    extracted_ok: int = 0
    would_insert: int = 0
    would_update: int = 0
    would_skip: int = 0
    listings: list[PreviewListing] = Field(default_factory=list)


@router.post("/process", response_model=PipelineResult)
async def process_endpoint(req: ProcessRequest) -> PipelineResult:
    """Process crawled Zalo messages through the apartment agent pipeline.

    Provide either message_ids to process specific messages,
    or group_name to process all messages from a crawled group.
    """
    request_id = str(uuid4())
    missing = validate_settings()
    if missing:
        raise HTTPException(
            status_code=500,
            detail=ApartmentAgentError(
                kind="missing_config",
                message="Missing required settings",
                missing=missing,
                request_id=request_id,
            ).model_dump(),
        )

    # Fetch messages from Zalo Supabase
    from app.modules.zalo.services.supabase_service import _rest

    if req.message_ids:
        # Fetch specific messages by ID
        messages = []
        for mid in req.message_ids:
            try:
                rows = await _rest(
                    "GET",
                    "zalo_messages",
                    params={
                        "select": "id,content,group_name",
                        "id": f"eq.{mid}",
                        "limit": "1",
                    },
                ) or []
                if rows:
                    messages.append(
                        {"id": rows[0]["id"], "text": rows[0]["content"]}
                    )
            except Exception as exc:
                logger.warning(f"Failed to fetch message {mid}: {exc}")
    elif req.group_name:
        try:
            rows = await _rest(
                "GET",
                "zalo_messages",
                params={
                    "select": "id,content,group_name",
                    "group_name": f"eq.{req.group_name}",
                    "limit": "500",
                },
            ) or []
            messages = [
                {"id": row["id"], "text": row["content"]} for row in rows
            ]
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to fetch messages: {exc}"
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide message_ids or group_name",
        )

    if not messages:
        return PipelineResult()

    return await process_messages(messages)


@router.post("/process-all", response_model=PipelineResult)
async def process_all_endpoint(req: ProcessAllRequest) -> PipelineResult:
    """Reprocess all crawled Zalo messages (up to limit)."""
    request_id = str(uuid4())
    missing = validate_settings()
    if missing:
        raise HTTPException(
            status_code=500,
            detail=ApartmentAgentError(
                kind="missing_config",
                message="Missing required settings",
                missing=missing,
                request_id=request_id,
            ).model_dump(),
        )

    from app.modules.zalo.services.supabase_service import _rest

    try:
        rows = await _rest(
            "GET",
            "zalo_messages",
            params={
                "select": "id,content",
                "limit": str(req.limit),
            },
        ) or []
        messages = [
            {"id": row["id"], "text": row["content"]} for row in rows
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch messages: {exc}"
        )

    if not messages:
        return PipelineResult()

    return await process_messages(messages)


@router.post("/test-extract", response_model=TestExtractResponse)
async def test_extract_endpoint(req: TestExtractRequest) -> TestExtractResponse:
    """Test extraction only (no dedup/sync) for debugging.

    Provide either group_name to test with crawled messages,
    or texts to test with raw text directly.
    """
    request_id = str(uuid4())
    missing = validate_settings()
    if missing:
        raise HTTPException(
            status_code=400,
            detail=ApartmentAgentError(
                kind="missing_config",
                message="Missing required settings",
                missing=missing,
                request_id=request_id,
            ).model_dump(),
        )
    from app.modules.apartment_agent.pipeline import extract_only

    if req.texts:
        messages = [{"id": f"text_{i}", "text": t} for i, t in enumerate(req.texts)]
    elif req.group_name:
        from app.modules.zalo.services.supabase_service import _rest

        try:
            rows = await _rest(
                "GET",
                "zalo_messages",
                params={
                    "select": "id,content,group_name",
                    "group_name": f"eq.{req.group_name}",
                    "limit": "50",
                },
            ) or []
            messages = [
                {"id": row["id"], "text": row["content"]} for row in rows
            ]
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to fetch messages: {exc}"
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide texts or group_name",
        )

    if not messages:
        return TestExtractResponse()

    return await extract_only(messages)


@router.post("/preview", response_model=PreviewResponse)
async def preview_endpoint(req: TestExtractRequest) -> PreviewResponse:
    """Preview extraction without writing to GoDaNang.

    Runs classifier + extractor + dedup-read, and returns the exact
    payloads that would be sent to GoDaNang's villas table.
    Does NOT write any data.
    """
    request_id = str(uuid4())
    missing = validate_settings()
    if missing:
        raise HTTPException(
            status_code=400,
            detail=ApartmentAgentError(
                kind="missing_config",
                message="Missing required settings",
                missing=missing,
                request_id=request_id,
            ).model_dump(),
        )
    from app.modules.apartment_agent.pipeline import preview_only

    if req.texts:
        messages = [{"id": f"text_{i}", "text": t} for i, t in enumerate(req.texts)]
    elif req.group_name:
        from app.modules.zalo.services.supabase_service import _rest

        try:
            rows = await _rest(
                "GET",
                "zalo_messages",
                params={
                    "select": "id,content,group_name",
                    "group_name": f"eq.{req.group_name}",
                    "limit": "200",
                },
            ) or []
            messages = [
                {"id": row["id"], "text": row["content"]} for row in rows
            ]
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to fetch messages: {exc}"
            )
    else:
        raise HTTPException(
            status_code=400, detail="Provide texts or group_name"
        )

    if not messages:
        return PreviewResponse()

    return await preview_only(messages)


# ── Fake test data ──────────────────────────────────────────────────────────

FAKE_GROUPS = [
    {
        "group_name": "Cho thuê căn hộ Đà Nẵng",
        "messages": [
            {
                "id": "fake_001",
                "text": "CHO THUÊ CĂN HỘ SUNSHINE RIVERSIDE\n- Tòa A, tầng 12, căn 1205\n- 2 phòng ngủ, 2 WC, diện tích 72m²\n- Nội thất full: máy giặt, tủ lạnh, điều hòa, sofa\n- Giá: 12 triệu/tháng (đã bao gồm phí quản lý)\n- Liên hệ: Anh Hùng 0905.123.456 (Zalo)\n- Ảnh đính kèm bên dưới 👇",
                "images": ["sunshine_riverside_1205_1.png", "sunshine_riverside_1205_2.png", "sunshine_riverside_1205_3.png"],
            },
            {
                "id": "fake_002",
                "text": "Cần cho thuê gấp căn hộ Monarchy đường Bạch Đằng\n- 3PN, 2WC, 95m², tầng 20 view sông Hàn\n- Giá: 18 triệu/tháng\n- Nội thất cao cấp, ban công rộng\n- LH: Chị Linh 0935.789.012",
                "images": ["monarchy_bachdang_2001_1.jpg"],
            },
            {
                "id": "fake_003",
                "text": "Mọi người ơi cho em hỏi Đà Nẵng mùa này mưa nhiều không ạ? Em đang tính vào du lịch 😄",
                "images": [],
            },
        ],
    },
    {
        "group_name": "Mua bán nhà đất Hải Châu",
        "messages": [
            {
                "id": "fake_004",
                "text": "BÁN NHÀ MẶT TIỀN ĐƯỜNG LÊ DUẨN\n- Diện tích: 5x20m = 100m²\n- 1 trệt, 2 lầu, sân thượng\n- 4 phòng ngủ, 4 WC\n- Giá: 4.5 tỷ (thương lượng)\n- Sổ hồng riêng, thổ cư 100%\n- LH: 0905.222.333 (A. Tuấn)",
                "images": ["leduan_house_1.jpg", "leduan_house_2.jpg"],
            },
            {
                "id": "fake_005",
                "text": "Cho thuê mặt bằng kinh doanh đường Nguyễn Văn Linh\n- Diện tích: 80m², mặt tiền 6m\n- Phù hợp: quán café, shop thời trang\n- Giá: 25 triệu/tháng\n- Đặt cọc 3 tháng\n- LH Zalo: 0913.444.555",
                "images": ["ngvl_shop_1.png"],
            },
        ],
    },
    {
        "group_name": "Căn hộ sinh viên Ngũ Hành Sơn",
        "messages": [
            {
                "id": "fake_006",
                "text": "PHÒNG TRỌ SINH VIÊN GẦN ĐẠI HỌC DUY TÂN\n- Phòng 25m², có gác lửng\n- Điều hòa, nóng lạnh, wifi free\n- Giá: 2.5 triệu/tháng (điện 3.5k/số, nước 100k/người)\n- Ở được 2 người\n- LH: Cô Mai 0905.666.777",
                "images": ["sv_duytan_1.jpg", "sv_duytan_2.jpg"],
            },
            {
                "id": "fake_007",
                "text": "Ai biết quán bún bùi hữu gần đây không recommend cho mình với ạ 🍜",
                "images": [],
            },
            {
                "id": "fake_008",
                "text": "CHO THUÊ CĂN HỘ FPT CITY\n- 1PN, 1WC, 45m², tầng 8\n- Nội thất cơ bản: giường, tủ, bếp\n- Giá: 5 triệu/tháng\n- Free wifi + gym\n- Gửi xe: 100k/tháng\n- Liên hệ: 0978.888.999 (Zalo)",
                "images": ["fpt_city_801_1.png", "fpt_city_801_2.png"],
            },
        ],
    },
]


class FakeDataResponse(BaseModel):
    """Response after creating fake test data."""
    groups: list[dict]
    total_messages: int
    total_images: int


@router.post("/create-fake-data", response_model=FakeDataResponse)
async def create_fake_data() -> FakeDataResponse:
    """Create fake apartment listing data for testing the Agent.

    Creates 3 groups with realistic Vietnamese apartment messages,
    including listings and non-listing messages.
    """
    total_images = sum(
        len(msg["images"])
        for group in FAKE_GROUPS
        for msg in group["messages"]
    )

    logger.info(
        f"Created fake test data: {len(FAKE_GROUPS)} groups, "
        f"{sum(len(g['messages']) for g in FAKE_GROUPS)} messages, "
        f"{total_images} images"
    )

    return FakeDataResponse(
        groups=FAKE_GROUPS,
        total_messages=sum(len(g["messages"]) for g in FAKE_GROUPS),
        total_images=total_images,
    )
