"""급똥 서울 MCP - 로직/파이프라인 검증.

실제 스마트서울맵 스키마(77컬럼, '상세 제목N/내용N' 쌍 구조)를 그대로 본뜬
합성 xlsx/zip을 만들어 파싱·질의·다운로드(mock)·캐시 저장을 검증한다.
"""

from __future__ import annotations

import io
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seoul_toilet import data as D  # noqa: E402
from seoul_toilet.data import KST, ToiletStore  # noqa: E402

# --- 실제 데이터와 동일한 헤더(첫 줄 + 줄바꿈 보조문구) 구성 ---------------
_FIXED_HEADER = [
    "콘텐츠 ID\n(필수 입력)", "사용유무\n(필수입력)", "콘텐츠명\n(필수 입력)",
    "서브카테고리 명\n(선택 입력)", "시군\n(선택입력)", "구명\n(선택입력)",
    "새주소[도로명 주소]\n(조건부 선택 입력)", "지번주소", "키워드",
    "다국어\n(필수 입력)", "좌표[X]\n(조건부 선택 입력)", "좌표[Y]\n(조건부 선택 입력)",
    "공간객체타입\n(조건부 선택 입력)", "라인 색상", "라인 패턴", "라인두께",
    "면 색상", "면 패턴", "면 패턴크기", "전화번호\n(선택 입력)", "웹URL\n(선택 입력)",
    "동영상 웹 링크 URL", "음성파일 웹 링크 URL", "사진 정보1", "사진 정보2",
    "사진 정보3", "사진 정보4", "사진 정보5",
]


def _build_header() -> list[str]:
    """28개 고정 컬럼 + 상세 제목/내용 쌍으로 정확히 77컬럼을 만든다."""
    header = list(_FIXED_HEADER)  # 28개
    k = 1
    while len(header) < 76:
        header.append(f"상세 제목{k}\n(선택 입력)")
        header.append(f"상세 내용{k}\n(선택 입력)")
        k += 1
    header.append("상세 제목99\n(선택 입력)")  # 짝 없는 제목(파서가 무시해야 함) -> 77
    assert len(header) == 77
    return header


# 상세쌍에 들어갈 (제목, 내용) 순서 — 실제 데이터 순서와 동일
_DETAILS = [
    "개방주체", "개방시간", "휴관일", "화장실구분", "장애인화장실구분",
    "편의시설", "안전시설", "건물용도", "관리기관",
]


def _row(content_id, name, sub, gu, road, jibun, lon, lat, phone, details):
    """details: {제목: 내용} -> 전체 77칸 행 생성."""
    row = [None] * 77
    row[0] = content_id
    row[1] = "Y"
    row[2] = name
    row[3] = sub
    row[5] = gu
    row[6] = road
    row[7] = jibun
    row[8] = "#공중화장실"
    row[10] = lon
    row[11] = lat
    row[19] = phone
    # 상세 제목/내용: 28부터 쌍으로
    for i, title in enumerate(_DETAILS):
        ti = 28 + i * 2
        ci = ti + 1
        row[ti] = title
        row[ci] = details.get(title, "")
    return row


def _make_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(_build_header())
    rows = [
        _row("rest2025_0448", "강동구민회관", "정시", "강동구",
             "서울특별시 강동구 상암로 168", "서울특별시 강동구 천호동 41",
             "127.141222548", "37.545731457", "02-2045-7617",
             {"개방주체": "공공개방|", "개방시간": "정시(08:00~21:00)|",
              "화장실구분": "남자|여자|", "장애인화장실구분": "남자|여자|",
              "편의시설": "기저귀교환대(남)|기저귀교환대(여)|",
              "안전시설": "비상벨(여)|", "건물용도": "공공시설|",
              "관리기관": "강동구도시관리공단"}),
        _row("rest2025_24h", "24시 개방화장실", "상시", "강동구",
             "서울특별시 강동구 상암로 170", "서울특별시 강동구 천호동 43",
             "127.141500000", "37.545900000", "02-0000-0000",
             {"개방주체": "공공개방|", "개방시간": "상시(00:00~24:00)|",
              "화장실구분": "남자|여자|", "건물용도": "공원|",
              "관리기관": "강동구"}),
        _row("rest2025_night", "심야 공원화장실", "정시", "송파구",
             "서울특별시 송파구 올림픽로 240", "서울특별시 송파구 잠실동 10",
             "127.073000000", "37.515000000", "02-1111-2222",
             {"개방시간": "정시(22:00~06:00)|", "화장실구분": "남자|여자|",
              "관리기관": "송파구"}),
        _row("rest2025_wd", "평일전용 화장실", "정시", "마포구",
             "서울특별시 마포구 월드컵로 100", "서울특별시 마포구 성산동 1",
             "126.901000000", "37.566000000", "02-3333-4444",
             {"개방시간": "평일(09:00~18:00) 주말휴무|", "화장실구분": "남자|여자|",
              "장애인화장실구분": "남녀공용|", "관리기관": "마포구"}),
        _row("rest2025_nocoord", "좌표없는 화장실", "정시", "강동구",
             "서울특별시 강동구 천호대로 1", "서울특별시 강동구 길동 1",
             "", "", "02-5555-6666",
             {"개방시간": "정시(08:00~21:00)|", "화장실구분": "남자|", "관리기관": "강동구"}),
    ]
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_zip_bytes() -> bytes:
    xlsx = _make_xlsx_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("contents.xlsx", xlsx)
        zf.writestr("coord.xlsx", b"dummy")  # 점 데이터라 실제로는 거의 비어있음
    return buf.getvalue()


# ===========================================================================
# 파싱
# ===========================================================================


def test_parse_basic_fields():
    recs = D.parse_xlsx(_make_xlsx_bytes())
    assert len(recs) == 5
    a = next(r for r in recs if r["content_id"] == "rest2025_0448")
    assert a["name"] == "강동구민회관"
    assert a["district"] == "강동구"
    assert a["in_use"] is True
    assert abs(a["lat"] - 37.545731457) < 1e-6
    assert abs(a["lon"] - 127.141222548) < 1e-6
    assert a["phone"] == "02-2045-7617"
    # 다중값 파이프 분해
    assert a["toilet_types"] == ["남자", "여자"]
    assert a["disabled_toilet"] == ["남자", "여자"]
    assert a["amenities"] == ["기저귀교환대(남)", "기저귀교환대(여)"]
    assert a["safety"] == ["비상벨(여)"]
    assert a["manager"] == "강동구도시관리공단"
    assert a["building_use"] == "공공시설"
    # 원문 상세 보존
    assert a["details"]["개방시간"] == "정시(08:00~21:00)"


def test_unpaired_title_ignored():
    # '상세 제목99'는 짝(내용)이 없으므로 무시되어도 에러가 없어야 한다
    recs = D.parse_xlsx(_make_xlsx_bytes())
    assert all("99" not in (r.get("details") or {}) for r in recs)


# ===========================================================================
# 개방시간 파싱 / open_now
# ===========================================================================


def test_open_hours_parse():
    assert D.parse_open_hours("정시(08:00~21:00)|")["ranges"] == [[480, 1260]]
    assert D.parse_open_hours("상시(00:00~24:00)|")["is_24h"] is True
    assert D.parse_open_hours("정시(22:00~06:00)|")["ranges"] == [[1320, 360]]
    # 해석 불가 시 note 부여
    assert D.parse_open_hours("관계자 문의")["note"]


def test_is_open_now():
    at_10 = datetime(2026, 6, 20, 10, 0, tzinfo=KST)
    at_23 = datetime(2026, 6, 20, 23, 0, tzinfo=KST)
    day = D.parse_open_hours("정시(08:00~21:00)|")
    night = D.parse_open_hours("정시(22:00~06:00)|")
    always = D.parse_open_hours("상시(00:00~24:00)|")
    assert D.is_open_now(day, at_10) is True
    assert D.is_open_now(day, at_23) is False
    assert D.is_open_now(night, at_23) is True       # 자정 넘김 구간
    assert D.is_open_now(night, at_10) is False
    assert D.is_open_now(always, at_23) is True
    assert D.is_open_now({"is_24h": False, "ranges": []}, at_10) is None  # 불명


# ===========================================================================
# 거리 / 최근접
# ===========================================================================


def test_haversine_known():
    # 강동구민회관 <-> 약 200m 이내 인접 좌표
    d = D.haversine_m(37.545731457, 127.141222548, 37.545900000, 127.141500000)
    assert 0 < d < 60


def test_find_nearest_order_and_filters():
    recs = D.parse_xlsx(_make_xlsx_bytes())
    at_10 = datetime(2026, 6, 20, 10, 0, tzinfo=KST)
    # 강동구민회관 바로 옆에서 검색
    res = D.find_nearest(recs, 37.5457, 127.1412, limit=10, now=at_10)
    ids = [r["content_id"] for r in res]
    # 좌표 없는 항목은 제외
    assert "rest2025_nocoord" not in ids
    # 가장 가까운 두 곳이 강동구 인접 좌표
    assert ids[0] in ("rest2025_0448", "rest2025_24h")
    assert "distance_m" in res[0]
    # 반경 제한
    near = D.find_nearest(recs, 37.5457, 127.1412, radius_m=100, now=at_10)
    assert all(r["distance_m"] <= 100 for r in near)
    # open_now=True (10시): 야간(22~06)은 제외돼야 함
    open_res = D.find_nearest(recs, 37.5457, 127.1412, open_now=True, now=at_10)
    assert "rest2025_night" not in [r["content_id"] for r in open_res]
    # require_disabled: 장애인화장실 있는 강동구민회관만 통과(24h점은 제외)
    dis = D.find_nearest(recs, 37.5457, 127.1412, require_disabled=True, now=at_10)
    assert "rest2025_0448" in [r["content_id"] for r in dis]
    assert "rest2025_24h" not in [r["content_id"] for r in dis]


# ===========================================================================
# 검색 / 단건 조회
# ===========================================================================


def test_search_and_get():
    recs = D.parse_xlsx(_make_xlsx_bytes())
    by_gu = D.search(recs, district="강동구")
    assert {r["content_id"] for r in by_gu} >= {"rest2025_0448", "rest2025_24h", "rest2025_nocoord"}
    by_q = D.search(recs, query="회관")
    assert by_q and by_q[0]["content_id"] == "rest2025_0448"
    one = D.get_by_id(recs, "rest2025_0448")
    assert one and one["name"] == "강동구민회관"
    assert "details" in one  # 상세 원문 포함
    assert D.get_by_id(recs, "없는ID") is None


# ===========================================================================
# 다운로드 -> 추출 -> 파싱 -> 캐시 (네트워크 mock)
# ===========================================================================


def test_extract_inner_xlsx():
    xlsx = D.extract_inner_xlsx(_make_zip_bytes())
    assert xlsx[:2] == b"PK"  # xlsx도 zip(PK)
    recs = D.parse_xlsx(xlsx)
    assert len(recs) == 5


def test_store_refresh_with_mock(monkeypatch, tmp_path):
    zip_bytes = _make_zip_bytes()

    class _Resp:
        content = zip_bytes
        def raise_for_status(self):
            return None

    def fake_post(url, params=None, headers=None, timeout=None):
        assert url == D.DOWNLOAD_URL
        assert params["theme_id"] == "100106"
        assert params["mode"] == "downloadGeomFormatXLSX"
        return _Resp()

    monkeypatch.setattr(D.requests, "post", fake_post)
    store = ToiletStore(cache_dir=tmp_path)
    info = store.refresh()
    assert info["count"] == 5
    assert store.count == 5
    # 캐시 파일 저장 확인
    assert (tmp_path / "contents.xlsx").exists()
    assert (tmp_path / "contents.zip").exists()
    # 캐시에서 재적재
    store2 = ToiletStore(cache_dir=tmp_path)
    assert store2.load_from_cache() is True
    assert store2.count == 5
    # info의 구 목록
    assert "강동구" in store.info()["districts"]


def test_download_zip_rejects_non_zip(monkeypatch):
    class _Resp:
        content = b"<html>login</html>"
        def raise_for_status(self):
            return None

    monkeypatch.setattr(D.requests, "post", lambda *a, **k: _Resp())
    try:
        D.download_zip()
        assert False, "ZIP이 아닌 응답은 예외여야 한다"
    except ValueError:
        pass


# ===========================================================================
# 서버 와이어링 (포트 바인딩 없이 tool 등록 확인)
# ===========================================================================


def test_server_tools_registered():
    import asyncio
    from seoul_toilet import server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"find_nearest_toilets", "search_toilets", "get_toilet", "dataset_info"} <= names
