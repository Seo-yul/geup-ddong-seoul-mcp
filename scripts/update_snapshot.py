#!/usr/bin/env python3
"""시드 스냅샷 갱신.

스마트서울맵에서 최신 공중화장실 데이터를 받아 `seoul_toilet/seed/contents.xlsx` 에 저장한다.
이 파일은 repo/이미지에 포함되어, 애플리케이션 기동 시 다운로드가 실패하면 폴백 데이터로 쓰인다.

실행:
    python scripts/update_snapshot.py
    (requests, openpyxl 필요. 없으면 컨테이너로:  README의 '데이터 스냅샷' 참고)

갱신 후 변경분을 커밋하면 된다:
    git add seoul_toilet/seed/contents.xlsx && git commit -m "데이터 스냅샷 갱신"
"""

from __future__ import annotations

from pathlib import Path

from seoul_toilet.data import download_zip, extract_inner_xlsx, parse_xlsx

SEED = Path(__file__).resolve().parent.parent / "seoul_toilet" / "seed" / "contents.xlsx"


def main() -> None:
    xlsx = extract_inner_xlsx(download_zip())
    records = parse_xlsx(xlsx)  # 파싱 가능한지 검증
    SEED.parent.mkdir(parents=True, exist_ok=True)
    SEED.write_bytes(xlsx)
    print(f"스냅샷 갱신 완료: {len(xlsx):,} bytes, {len(records)}건 -> {SEED}")


if __name__ == "__main__":
    main()
