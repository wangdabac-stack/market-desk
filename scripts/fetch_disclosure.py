"""
DART 공시검색 API에서 당일 공시를 받아 data/disclosure.json으로 저장한다.

인증키는 코드에 적지 않고 환경변수 DART_API_KEY에서 읽는다.
(GitHub Actions에서는 Secrets에 넣어두고 워크플로가 넣어준다)

로컬에서 직접 돌려볼 때:
    export DART_API_KEY="발급받은40자리키"     # 윈도우는 set DART_API_KEY=...
    python scripts/fetch_disclosure.py
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

API_URL = "https://opendart.fss.or.kr/api/list.json"
DOC_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
KST = ZoneInfo("Asia/Seoul")
OUT_PATH = Path("data/disclosure.json")
MAX_ITEMS = 40          # 사이트에 저장할 최대 공시 수
LOOKBACK_DAYS = 5       # 당일 공시가 없으면 며칠 전까지 거슬러 올라갈지 (주말·공휴일 대비)

# 공시 제목에 이 단어가 들어가면 해당 분류로 잡는다. 위에 있는 규칙이 우선.
# tag: 화면에 뜨는 라벨, cls: 색상 (up/dn/warn/ok/vio 중 하나)
RULES = [
    (["상장폐지", "관리종목", "횡령", "배임", "소송", "감사의견"], "위험", "up"),
    (["유상증자", "전환사채", "신주인수권", "교환사채", "무상감자", "감자"], "자금조달", "vio"),
    (["영업(잠정)실적", "매출액또는손익구조", "실적"], "실적", "warn"),
    (["단일판매", "공급계약", "수주"], "계약", "ok"),
    (["자기주식", "자사주"], "자사주", "dn"),
    (["합병", "분할", "영업양수", "영업양도", "주식교환"], "구조개편", "vio"),
    (["대량보유상황보고서", "소유상황보고서"], "지분", "dn"),
    (["무상증자", "주식배당", "배당"], "배당", "ok"),
    (["공개매수", "자율공시", "정정"], "기타", "warn"),
]


def classify(title: str):
    """공시 제목을 보고 (분류명, 색상)을 돌려준다. 해당 없으면 None."""
    clean = title.replace(" ", "")
    for keywords, tag, cls in RULES:
        for kw in keywords:
            if kw.replace(" ", "") in clean:
                return tag, cls
    return None


def fetch_day(api_key: str, day: str, corp_cls: str):
    """하루치 공시를 시장(corp_cls)별로 모두 받아온다. Y=코스피, K=코스닥"""
    items, page = [], 1
    while True:
        params = {
            "crtfc_key": api_key,
            "bgn_de": day,
            "end_de": day,
            "corp_cls": corp_cls,
            "page_no": page,
            "page_count": 100,
        }
        res = requests.get(API_URL, params=params, timeout=20)
        res.raise_for_status()
        body = res.json()
        status = body.get("status")

        if status == "013":          # 조회된 데이터가 없음 (휴장일 등)
            return []
        if status != "000":
            raise RuntimeError(f"DART 오류 {status}: {body.get('message')}")

        items.extend(body.get("list", []))
        if page >= int(body.get("total_page", 1)):
            return items
        page += 1
        time.sleep(0.2)              # 연속 호출 사이 약간의 간격


def main():
    api_key = os.environ.get("DART_API_KEY", "").strip()
    if not api_key:
        print("DART_API_KEY 환경변수가 비어 있습니다.", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(KST).date()
    raw, used_day = [], None

    # 당일 공시가 없으면 (주말·공휴일) 직전 영업일까지 거슬러 올라간다
    for back in range(LOOKBACK_DAYS):
        day = (today - timedelta(days=back)).strftime("%Y%m%d")
        found = []
        for corp_cls in ("Y", "K"):
            found.extend(fetch_day(api_key, day, corp_cls))
        if found:
            raw, used_day = found, day
            break
        print(f"{day}: 공시 없음, 하루 전으로 이동")

    picked = []
    for it in raw:
        result = classify(it.get("report_nm", ""))
        if result is None:
            continue
        tag, cls = result
        picked.append({
            "name": it.get("corp_name", ""),
            "code": it.get("stock_code", ""),
            "market": "코스피" if it.get("corp_cls") == "Y" else "코스닥",
            "title": it.get("report_nm", "").strip(),
            "filer": it.get("flr_nm", ""),
            "tag": tag,
            "cls": cls,
            "url": DOC_URL.format(it.get("rcept_no", "")),
            "rcept_no": it.get("rcept_no", ""),
        })

    # 접수번호가 클수록 늦게 접수된 것 → 최신순 정렬
    picked.sort(key=lambda x: x["rcept_no"], reverse=True)
    picked = picked[:MAX_ITEMS]

    payload = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "base_date": used_day or today.strftime("%Y%m%d"),
        "total_fetched": len(raw),
        "items": picked,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"전체 {len(raw)}건 중 {len(picked)}건 저장 → {OUT_PATH}")


if __name__ == "__main__":
    main()
