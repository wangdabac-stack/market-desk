"""
거래소 마감 데이터를 모아 data/market.json으로 저장한다.
같은 폴더의 krx_common.py, krx_rankings.py 를 함께 사용한다.

로컬에서 돌려볼 때:
    pip install pykrx pandas
    python scripts/fetch_market.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from krx_common import KST, build_indices, build_ohlcv, build_summary, latest_business_day
from krx_rankings import (
    build_52week,
    build_investor_flow,
    build_limits,
    build_top_value,
    build_volume_surge,
)

OUT_PATH = Path("data/market.json")


def main():
    day = latest_business_day()
    print(f"기준일: {day}")

    df = build_ohlcv(day)
    print(f"전 종목 {len(df)}개 수집 완료")

    payload = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "base_date": day,
        "indices": build_indices(day),
        "summary": build_summary(df, day),
        "top_value": build_top_value(df),
        "investor": build_investor_flow(day),
        "week52": build_52week(df, day),
        "volume_surge": build_volume_surge(df, day),
        "limits": build_limits(df),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"저장 완료 → {OUT_PATH}\n"
        f"  거래대금 상위 {len(payload['top_value'])}건\n"
        f"  신고가 {len(payload['week52']['high'])}건 / 신저가 {len(payload['week52']['low'])}건\n"
        f"  거래량 급증 {len(payload['volume_surge'])}건\n"
        f"  상한가 {len(payload['limits']['up'])}건 / 하한가 {len(payload['limits']['down'])}건"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"실패: {e}", file=sys.stderr)
        sys.exit(1)
