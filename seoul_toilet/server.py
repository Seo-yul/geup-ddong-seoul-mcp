"""급똥 서울 MCP 서버 (Streamable HTTP).

LLM에 노출하는 tool:
  - find_nearest_toilets : 내 위치(위경도) 기준 가까운 공중화장실 (거리순)
  - search_toilets       : 구/이름/키워드 검색
  - get_toilet           : content_id 상세 조회
  - dataset_info         : 데이터 메타(건수/갱신시각/구 목록 등)

LLM에 노출하지 않는 운영용 HTTP 엔드포인트:
  - POST|GET /refresh    : 원격 데이터 재다운로드 (사용자가 직접 호출)
  - GET      /health     : 상태 확인

실행:
  python -m seoul_toilet.server         # 또는 server.py 직접 실행
  -> http://{HOST}:{PORT}/mcp 에서 MCP(Streamable HTTP) 제공
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Icon, ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import data as D
from .data import ToiletStore

logger = logging.getLogger("geup-ddong-seoul")

# ---------------------------------------------------------------------------
# 설정 (환경변수)
# ---------------------------------------------------------------------------

HOST = os.environ.get("SEOUL_TOILET_HOST", "127.0.0.1")
PORT = int(os.environ.get("SEOUL_TOILET_PORT", "8000"))
CACHE_DIR = os.environ.get("SEOUL_TOILET_CACHE_DIR")
DOWNLOAD_ON_START = os.environ.get("SEOUL_TOILET_DOWNLOAD_ON_START", "1") != "0"
# /refresh 보호 토큰. 미설정이면 공개(cron/timer가 없는 환경에서 유일한 갱신 수단이므로
# 엔드포인트 자체는 항상 유지). 공개 배포에선 토큰을 설정해 외부 남용(DoS 증폭)을 막는다.
REFRESH_TOKEN = os.environ.get("SEOUL_TOILET_REFRESH_TOKEN", "").strip()


def _csv_env(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


# 리버스 프록시(도메인) 뒤에서 서비스하면 MCP Streamable HTTP의 DNS 리바인딩 보호가
# Host 헤더를 검사해 기본적으로 localhost 외 도메인을 421(Invalid Host header)로 막는다.
# 공개 호스트를 SEOUL_TOILET_PUBLIC_HOST 로 지정하면 허용 목록에 추가한다(도메인 비하드코딩).
# 쉼표로 여러 공개 호스트 지원(예: 자체 도메인 + PlayMCP 프록시 엔드포인트 호스트).
# PlayMCP 등 프록시가 우리 백엔드로 포워딩할 때 보내는 Host도 여기 넣어야 421을 피한다.
PUBLIC_HOSTS = _csv_env("SEOUL_TOILET_PUBLIC_HOST")
DNS_REBINDING_PROTECTION = os.environ.get("SEOUL_TOILET_DNS_REBINDING_PROTECTION", "1") != "0"

_allowed_hosts = _csv_env("SEOUL_TOILET_ALLOWED_HOSTS") or [
    "localhost", "127.0.0.1", "localhost:*", "127.0.0.1:*", HOST, f"{HOST}:*",
]
_allowed_origins = _csv_env("SEOUL_TOILET_ALLOWED_ORIGINS")
for _h in PUBLIC_HOSTS:
    _allowed_hosts += [_h, f"{_h}:*"]
    _allowed_origins += [f"https://{_h}", f"http://{_h}"]

_transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=DNS_REBINDING_PROTECTION,
    allowed_hosts=sorted(set(_allowed_hosts)),
    allowed_origins=sorted(set(_allowed_origins)),
)

# 서비스 아이콘: 공개 repo의 raw URL을 기본값으로 두고 환경변수로 재정의 가능.
# 서버(serverInfo)와 각 tool에 연결되어 MCP 클라이언트 UI에 노출된다.
ICON_BASE_URL = os.environ.get(
    "SEOUL_TOILET_ICON_BASE_URL",
    "https://raw.githubusercontent.com/Seo-yul/geup-ddong-seoul-mcp/main/assets",
).rstrip("/")
ICONS = [
    Icon(src=f"{ICON_BASE_URL}/icon.svg", mimeType="image/svg+xml", sizes=["any"]),
    Icon(src=f"{ICON_BASE_URL}/icon-256.png", mimeType="image/png", sizes=["256x256"]),
]

store = ToiletStore(cache_dir=CACHE_DIR) if CACHE_DIR else ToiletStore()

mcp = FastMCP(
    "geup-ddong-seoul",
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    stateless_http=True,  # PlayMCP 권장: 세션 없는 stateless 전송
    icons=ICONS,
    transport_security=_transport_security,
    instructions=(
        "서울시 공중화장실(스마트서울맵 theme_id=100106) 조회 서버. "
        "급한 상황에서 가까운 화장실을 찾을 때는 find_nearest_toilets에 사용자의 "
        "위도(latitude)·경도(longitude)를 넣어 호출한다. 지금 이용 가능한 곳만 원하면 "
        "open_now=true 를 사용한다. 위경도를 모르면 search_toilets(district/query)로 찾는다. "
        "유효한 구 이름 목록과 데이터 갱신 시점은 dataset_info로 확인한다."
    ),
)


def _records() -> list[dict]:
    return store.records


def _empty_notice() -> dict:
    return {
        "error": "데이터가 비어 있습니다. 운영용 엔드포인트 POST /refresh 로 먼저 데이터를 받아주세요.",
        "count": 0,
    }


# ---------------------------------------------------------------------------
# Tools (LLM 노출)
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Find the nearest public toilets to a location, ordered by distance, using "
        "Geup-Ddong Seoul(급똥 서울), a Seoul public-toilet finder built on SmartSeoulMap "
        "theme_id=100106. Use this first when a user urgently needs a toilet: pass their "
        "WGS84 latitude and longitude. Optional: open_now=true keeps only toilets open now "
        "(KST), require_disabled=true keeps wheelchair-accessible ones, radius_m caps the "
        "search radius in meters, limit sets how many to return. Each result carries "
        "distance_m plus open hours, open_now, toilet/accessible types, amenities, safety "
        "facilities, manager and phone."
    ),
    icons=ICONS,
    annotations=ToolAnnotations(
        title="Find nearest toilets",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def find_nearest_toilets(
    latitude: float,
    longitude: float,
    limit: int = 5,
    radius_m: Optional[float] = None,
    open_now: bool = False,
    require_disabled: bool = False,
) -> list[dict]:
    """내 위치에서 가까운 공중화장실을 거리순으로 찾는다 (급할 때 최우선 사용).

    Args:
        latitude: 사용자 위치 위도 (예: 37.5547). WGS84.
        longitude: 사용자 위치 경도 (예: 126.9706). WGS84.
        limit: 반환 개수 (기본 5).
        radius_m: 반경 제한(미터). None이면 제한 없음.
        open_now: True면 현재(KST) 개방 중으로 판단되는 곳만.
        require_disabled: True면 장애인 화장실이 있는 곳만.

    Returns:
        거리(distance_m)가 포함된 화장실 목록. 각 항목에 개방시간/개방여부(open_now)/
        화장실구분/편의시설/안전시설/관리기관/전화번호 등이 포함된다.
    """
    if store.count == 0:
        return [_empty_notice()]
    return D.find_nearest(
        _records(), latitude, longitude,
        limit=limit, radius_m=radius_m,
        open_now=open_now, require_disabled=require_disabled,
    )


@mcp.tool(
    description=(
        "Search public toilets by free text or administrative district(구) using "
        "Geup-Ddong Seoul(급똥 서울), a Seoul public-toilet finder built on SmartSeoulMap "
        "theme_id=100106. Use when latitude/longitude are unknown. 'query' is a "
        "case-insensitive partial match over name, road and lot-number address, manager "
        "and keyword; 'district' filters by gu name. Optional: open_now=true keeps only "
        "toilets open now (KST), require_disabled=true keeps wheelchair-accessible ones, "
        "limit caps results. Call dataset_info for the list of valid district names."
    ),
    icons=ICONS,
    annotations=ToolAnnotations(
        title="Search toilets",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def search_toilets(
    query: Optional[str] = None,
    district: Optional[str] = None,
    open_now: bool = False,
    require_disabled: bool = False,
    limit: int = 20,
) -> list[dict]:
    """이름/주소/키워드 또는 구(district)로 공중화장실을 검색한다.

    위경도를 모를 때 사용한다. query는 이름·도로명/지번주소·관리기관·키워드에 대한
    부분일치(대소문자 무시)이다.

    Args:
        query: 검색어(예: "시민회관", "한강공원"). 생략 가능.
        district: 자치구 이름(예: "강동구"). 부분일치. 생략 가능.
        open_now: True면 현재(KST) 개방 중인 곳만.
        require_disabled: True면 장애인 화장실이 있는 곳만.
        limit: 최대 반환 개수 (기본 20).

    Returns:
        조건에 맞는 화장실 목록(거리 없음). 유효한 구 이름은 dataset_info 참고.
    """
    if store.count == 0:
        return [_empty_notice()]
    return D.search(
        _records(), query=query, district=district,
        open_now=open_now, require_disabled=require_disabled, limit=limit,
    )


@mcp.tool(
    description=(
        "Get full details of a single public toilet by its content_id using "
        "Geup-Ddong Seoul(급똥 서울), a Seoul public-toilet finder built on SmartSeoulMap "
        "theme_id=100106. Pass a content_id taken from another tool's result (for example "
        "'rest2025_0448'). Returns the toilet's fields plus a raw 'details' map (original "
        "title to content)."
    ),
    icons=ICONS,
    annotations=ToolAnnotations(
        title="Get toilet detail",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def get_toilet(content_id: str) -> dict:
    """content_id로 화장실 1건의 상세 정보를 조회한다(원문 상세 details 포함).

    Args:
        content_id: 콘텐츠 ID (예: "rest2025_0448"). 다른 tool 결과의 content_id 사용.
    """
    if store.count == 0:
        return _empty_notice()
    rec = D.get_by_id(_records(), content_id)
    if rec is None:
        return {"error": f"해당 content_id를 찾을 수 없습니다: {content_id}"}
    return rec


@mcp.tool(
    description=(
        "Get dataset metadata for Geup-Ddong Seoul(급똥 서울), a Seoul public-toilet finder "
        "built on SmartSeoulMap theme_id=100106: total toilet count, last refresh time, "
        "data source, and per-district counts (the list of valid district/구 names to pass "
        "to the other tools)."
    ),
    icons=ICONS,
    annotations=ToolAnnotations(
        title="Dataset info",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def dataset_info() -> dict:
    """데이터셋 메타 정보: 총 건수, 갱신 시각, 출처, 자치구별 개수(유효한 구 이름 목록)."""
    return store.info()


# ---------------------------------------------------------------------------
# 운영용 HTTP 엔드포인트 (LLM 비노출) — 사용자가 직접 호출
# ---------------------------------------------------------------------------


def _refresh_authorized(request: Request) -> bool:
    """REFRESH_TOKEN 미설정이면 공개. 설정 시 헤더/쿼리의 토큰 일치를 요구한다."""
    if not REFRESH_TOKEN:
        return True
    auth = request.headers.get("authorization", "")
    bearer = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
    provided = (
        request.headers.get("x-refresh-token")
        or bearer
        or request.query_params.get("token", "")
    )
    return bool(provided) and provided == REFRESH_TOKEN


@mcp.custom_route("/refresh", methods=["POST", "GET"])
async def refresh_endpoint(request: Request) -> JSONResponse:
    """원격에서 데이터를 다시 받아 캐시를 갱신한다. (cron/timer 또는 사용자가 직접 호출)

    SEOUL_TOILET_REFRESH_TOKEN 이 설정돼 있으면 `Authorization: Bearer <t>`,
    `X-Refresh-Token: <t>`, 또는 `?token=<t>` 중 하나로 토큰을 제시해야 한다.
    """
    if not _refresh_authorized(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        info = store.refresh()
        return JSONResponse({"ok": True, **info})
    except Exception as exc:  # noqa: BLE001
        logger.exception("refresh failed")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@mcp.custom_route("/health", methods=["GET"])
async def health_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "count": store.count, "loaded_at": store.loaded_at})


# ---------------------------------------------------------------------------
# 시작 시 데이터 적재
# ---------------------------------------------------------------------------


def init_store() -> None:
    """캐시 -> (옵션)다운로드 순으로 초기 적재. 실패해도 서버는 계속 뜬다."""
    try:
        store.ensure_loaded(allow_download=DOWNLOAD_ON_START)
        logger.info("데이터 적재 완료: %s건 (source=%s)", store.count, store.source)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "초기 데이터 적재 실패(%s). /refresh 로 수동 적재하세요.", exc
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_store()
    logger.info("Streamable HTTP MCP 시작: http://%s:%s/mcp", HOST, PORT)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
