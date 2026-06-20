<p align="center">
  <img src="assets/icon-256.png" alt="급똥 서울 (Geup-Ddong Seoul)" width="140" height="140" />
</p>

<h1 align="center">급똥 서울 (geup-ddong-seoul-mcp)</h1>

서울시 공중화장실 데이터(스마트서울맵 테마 `theme_id=100106`)를 조회하는 **MCP 서버**입니다.
급할 때 내 위치에서 가까운, 지금 열려 있는 화장실을 찾는 것이 핵심 기능입니다.

- 전송 방식: **Streamable HTTP** (`http://{HOST}:{PORT}/mcp`)
- 데이터 출처: 스마트서울맵 갤러리 (공중화장실, 약 4,500개소)
- 다운로드는 **로그인/인증 불필요** (공개 엔드포인트)

## 동작 개요

```
POST https://map.seoul.go.kr/smgis/webs/contents/contents.do
     ?mode=downloadGeomFormatXLSX&down_type=xlsx&lan_type=KOR&conts_type=A&theme_id=100106
  -> contents.zip  ->  contents.xlsx (데이터)  ->  파싱하여 메모리 적재
```

## 원본 데이터 구조 (contents.xlsx)

`contents.xlsx`는 스마트서울맵 테마 업로드 공통 양식으로 **77개 컬럼**이며, 공중화장실은
약 **4,538행**입니다. 77컬럼 중 실제로 값이 들어있는 컬럼은 45개이고 나머지는 빈
스타일/예비 컬럼입니다. 헤더 1행은 `콘텐츠 ID\n(필수 입력)`처럼 안내문구가 붙어 있어
**첫 줄만** 컬럼명으로 사용합니다. (채움률은 실제 데이터 기준 근삿값)

### 고정 컬럼

| 원본 컬럼(첫 줄) | 내부 필드 | 채움률 | 예시 |
| --- | --- | --- | --- |
| 콘텐츠 ID | `content_id` | 100% | `rest2025_0448` |
| 사용유무 | `in_use` (Y→true) | 100% | `Y` |
| 콘텐츠명 | `name` | 100% | 강동구민회관 |
| 서브카테고리 명 | `subcategory` | 100% | 정시 / 상시 |
| 구명 | `district` | 100% | 강동구 |
| 새주소[도로명 주소] | `road_address` | 92% | 서울특별시 강동구 상암로 168 |
| 지번주소 | `jibun_address` | 99% | 서울특별시 강동구 천호동 41 |
| 키워드 | `keyword` | 99% | #공중화장실 |
| 좌표[X] | `longitude` (경도) | 99% | 127.141222548 |
| 좌표[Y] | `latitude` (위도) | 99% | 37.545731457 |
| 전화번호 | `phone` | 99% | 02-2045-7617 |
| 웹URL | `web_url` | <1% | (대부분 비어있음) |

### 상세 속성 (제목/내용 쌍 구조)

상세 정보는 `상세 제목N` / `상세 내용N` 컬럼 **쌍**으로 저장됩니다. 예를 들어 `상세 제목2`칸에
`개방시간`, `상세 내용2`칸에 `정시(08:00~21:00)`이 들어갑니다. 서버는 컬럼 위치(N)가 아니라
**제목 텍스트**로 매핑하므로 순서가 바뀌어도 안전합니다. 다중값은 `|`로 구분되며(`남자|여자|`)
끝의 `|`는 정리합니다.

| 상세 제목 | 내부 필드 | 타입 | 채움률 | 예시 |
| --- | --- | --- | --- | --- |
| 개방주체 | `open_subject` | 문자열 | ~100% | 공공개방 |
| 개방시간 | `open_hours` | 문자열 | ~100% | 정시(08:00~21:00) |
| 휴관일 | `closed_days` | 리스트 | 11% | ["토요일","일요일"] |
| 화장실구분 | `toilet_types` | 리스트 | 99% | ["남자","여자"] |
| 장애인화장실구분 | `disabled_toilet` | 리스트 | 52% | ["남자","여자"] |
| 편의시설 | `amenities` | 리스트 | 28% | ["기저귀교환대(남)"] |
| 안전시설 | `safety` | 리스트 | 64% | ["비상벨(여)"] |
| 건물용도 | `building_use` | 문자열 | ~100% | 공공시설 |
| 관리기관 | `manager` | 문자열 | ~100% | 강동구도시관리공단 |

원문 상세 전체(제목→내용)는 `get_toilet` 결과의 `details`에 그대로 담깁니다.

### coord.xlsx

zip에 함께 들어오지만 공중화장실은 점(공간객체타입=1) 데이터라 좌표가 `contents.xlsx`에
모두 있어 사용하지 않습니다.

## 프로젝트 구조

```
geup-ddong-seoul-mcp/
├─ seoul_toilet/
│  ├─ __init__.py
│  ├─ data.py        # 다운로드/압축해제/파싱/질의 + ToiletStore(메모리·캐시)
│  └─ server.py      # FastMCP 서버(tool 4종) + /refresh, /health
├─ tests/
│  └─ test_logic.py  # 파싱·개방시간·거리·검색·다운로드(mock)·캐시 검증
├─ data_cache/       # 실행 시 생성: contents.zip, contents.xlsx 캐시
├─ requirements.txt
├─ pyproject.toml
└─ README.md
```

## 설치

```bash
pip install -r requirements.txt
# 또는 패키지로 설치
pip install -e .
```

요구사항: Python 3.10+, `mcp`, `requests`, `openpyxl`

## 실행

```bash
python -m seoul_toilet.server
# -> http://127.0.0.1:8000/mcp 에서 MCP 제공
```

환경변수로 설정합니다.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `SEOUL_TOILET_HOST` | `127.0.0.1` | 바인드 호스트 |
| `SEOUL_TOILET_PORT` | `8000` | 포트 |
| `SEOUL_TOILET_CACHE_DIR` | `./data_cache` | xlsx/zip 캐시 디렉터리 |
| `SEOUL_TOILET_DOWNLOAD_ON_START` | `1` | 시작 시 캐시가 없으면 1회 다운로드(`0`이면 비활성) |
| `SEOUL_TOILET_PUBLIC_HOST` | (없음) | 리버스 프록시 뒤 공개 도메인. 지정 시 MCP `/mcp`의 Host/Origin 허용 목록에 추가. **쉼표로 여러 개** 지정 가능(예: `techsummit.asia,foo.playmcp-endpoint.kakaocloud.io`). PlayMCP 등 프록시가 보내는 Host도 함께 넣어야 421을 피한다 |
| `SEOUL_TOILET_ALLOWED_HOSTS` | (자동) | 허용 Host 헤더 목록(쉼표 구분). 비우면 localhost 계열 + `PUBLIC_HOST` 자동 구성 |
| `SEOUL_TOILET_ALLOWED_ORIGINS` | (자동) | 허용 Origin 목록(쉼표 구분, 브라우저 클라이언트용) |
| `SEOUL_TOILET_DNS_REBINDING_PROTECTION` | `1` | MCP DNS 리바인딩 보호(`0`이면 비활성) |
| `SEOUL_TOILET_REFRESH_TOKEN` | (없음) | 설정 시 `/refresh` 호출에 토큰 일치 요구(공개 배포 보호용). 미설정이면 공개 |

> 도메인(리버스 프록시) 뒤에서 `/mcp`를 서비스할 때 `SEOUL_TOILET_PUBLIC_HOST`를 지정하지 않으면
> MCP의 DNS 리바인딩 보호가 외부 Host 헤더를 `421 Invalid Host header`로 막는다. `/health`·`/refresh`는
> 영향받지 않는다.

시작 시 캐시가 있으면 캐시를 읽고(네트워크 없음), 없으면 1회 다운로드합니다.

## MCP 클라이언트 등록

Streamable HTTP를 지원하는 클라이언트에서 아래처럼 URL로 등록합니다.

```json
{
  "mcpServers": {
    "geup-ddong-seoul": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## 노출 Tool (LLM이 호출)

| Tool | 용도 | 주요 인자 |
| --- | --- | --- |
| `find_nearest_toilets` | 내 위치 기준 가까운 화장실(거리순) | `latitude`, `longitude`, `limit`, `radius_m`, `open_now`, `require_disabled` |
| `search_toilets` | 구/이름/주소/키워드 검색 | `query`, `district`, `open_now`, `require_disabled`, `limit` |
| `get_toilet` | content_id 상세(원문 details 포함) | `content_id` |
| `dataset_info` | 건수·갱신시각·자치구 목록 등 메타 | (없음) |

> "지금 개방 중"은 별도 tool 대신 `open_now` 필터 + 결과의 `open_now`/`open_hours` 필드로 통합했습니다.
> LLM이 거리·개방·시설 조건을 조합해 판단하기 쉽도록, 각 결과에 개방시간(원문)·개방여부·
> 화장실구분·장애인화장실·편의시설·안전시설·관리기관·전화번호를 함께 담아 반환합니다.

### 결과 필드 예시

```json
{
  "content_id": "rest2025_0448",
  "name": "강동구민회관",
  "district": "강동구",
  "road_address": "서울특별시 강동구 상암로 168",
  "latitude": 37.545731457, "longitude": 127.141222548,
  "phone": "02-2045-7617",
  "open_hours": "정시(08:00~21:00)", "open_now": true, "is_24h": false,
  "toilet_types": ["남자", "여자"],
  "disabled_toilet": ["남자", "여자"],
  "amenities": ["기저귀교환대(남)", "기저귀교환대(여)"],
  "safety": ["비상벨(여)"],
  "manager": "강동구도시관리공단",
  "distance_m": 12.3
}
```

### 반환 필드 레퍼런스

원본 필드(위 데이터 구조 표) 외에 서버가 계산해 넣는 파생 필드입니다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `open_now` | bool / null | 현재(KST) 개방 여부. 형식 해석 불가 시 `null` |
| `is_24h` | bool | 상시/24시간 개방 여부 |
| `distance_m` | number | `find_nearest_toilets` 한정. 입력 좌표로부터 직선거리(m) |
| `open_hours_note` | string / null | 요일·공휴일 차이 등 자동해석 한계 안내 |
| `details` | object | `get_toilet` 한정. 원문 상세(제목→내용) 전체 |

빈 값은 단일 필드는 `null`, 리스트 필드는 `[]`로 반환합니다.

## 데이터 갱신 (사용자가 직접 호출)

새로고침은 **MCP tool로 노출하지 않고** 운영용 HTTP 엔드포인트로만 제공합니다.

```bash
curl -X POST http://127.0.0.1:8000/refresh   # 원격에서 다시 받아 캐시 갱신
curl http://127.0.0.1:8000/health            # 상태 확인
```

월 1회 자동화 예시(cron):

```
0 6 1 * *  curl -fsS -X POST http://127.0.0.1:8000/refresh
```

공개 배포 등에서 `/refresh` 남용을 막으려면 `SEOUL_TOILET_REFRESH_TOKEN`을 설정하고 호출 시
토큰을 함께 보냅니다(미설정이면 공개 — cron이 없는 서버에서 그대로 호출 가능).

```bash
export SEOUL_TOILET_REFRESH_TOKEN=$(openssl rand -hex 24)
curl -fsS -X POST -H "X-Refresh-Token: $SEOUL_TOILET_REFRESH_TOKEN" http://127.0.0.1:8000/refresh
# 또는: -H "Authorization: Bearer $TOKEN"  /  "...?token=$TOKEN"
```

## 개방시간 해석 한계

`개방시간` 원문은 `정시(08:00~21:00)`, `상시(00:00~24:00)`, `평일(09:00~18:00) 주말휴무` 등
형식이 다양합니다. 서버는 시간 구간을 추출해 `open_now`(KST 기준)를 계산하되, 요일/공휴일별
차이는 완전히 반영하지 못할 수 있어 그런 경우 `open_hours_note`로 표시하고 원문(`open_hours`)을
함께 제공합니다. 최종 판단 시 원문을 함께 참고하세요.

## 왜 FastMCP인가

읽기 전용 조회 서버(다운로드→캐시→질의)라 저수준 SDK의 세밀한 제어가 불필요합니다.
공식 `mcp` SDK의 FastMCP는 `@mcp.tool` 데코레이터로 타입힌트 기반 입력 스키마를 자동
생성하고, `@mcp.custom_route`로 운영용 엔드포인트(`/refresh`)를 같은 앱에 손쉽게 붙일 수
있어 본 용도에 가장 적합합니다.

## 테스트

```bash
pip install pytest
python -m pytest tests/ -q
```

실제 스키마(77컬럼, `상세 제목/내용` 쌍 구조)를 본뜬 합성 데이터로 파싱·개방시간·거리·검색·
다운로드(mock)·캐시까지 검증합니다.

## 라이선스/출처 표기

데이터: 서울특별시 스마트서울맵 (이용허락: 저작자표시 BY). 출처를 표기해 사용하세요.
