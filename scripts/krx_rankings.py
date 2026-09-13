"""종목별 집계. 거래대금 상위, 수급, 신고가, 거래량 급증, 상하한가."""

from datetime import datetime, timedelta

import pandas as pd
from pykrx import stock

from krx_common import eok, row_basic

TOP_VALUE = 20           # 거래대금 상위 종목 수
TOP_FLOW = 5             # 그 외 목록 길이
VOLUME_SURGE_MIN = 200   # 거래량 급증 최소 기준 (5일 평균 대비 %)
MIN_VALUE_EOK = 50       # 잡주 제외용 최소 거래대금 (억원)
SCAN_LIMIT = 300         # 과거 데이터를 뒤질 상위 종목 수


def build_top_value(df):
    out = []
    for code, r in df.nlargest(TOP_VALUE, "거래대금").iterrows():
        item = row_basic(code, r)
        item["value"] = eok(r["거래대금"])
        out.append(item)
    return out


def build_investor_flow(day):
    """외국인·기관의 순매수/순매도 상위."""
    targets = {"frn": "외국인", "ins": "기관합계"}
    flows = {}

    for key, investor in targets.items():
        merged = []
        for market in ("KOSPI", "KOSDAQ"):
            try:
                d = stock.get_market_net_purchases_of_equities(day, day, market, investor)
            except Exception as e:
                print(f"{market} {investor} 수급 조회 실패: {e}")
                continue
            if d.empty:
                continue
            d = d.copy()
            d["시장"] = "코스피" if market == "KOSPI" else "코스닥"
            merged.append(d)

        if not merged:
            flows[key] = {"buy": [], "sell": []}
            continue

        m = pd.concat(merged)
        m["금액"] = m["순매수거래대금"].apply(eok)

        def pack(frame):
            return [{
                "name": r.get("종목명", code),
                "code": code,
                "market": r["시장"],
                "amount": int(r["금액"]),
            } for code, r in frame.iterrows()]

        flows[key] = {
            "buy": pack(m.nlargest(TOP_FLOW, "금액")),
            "sell": pack(m.nsmallest(TOP_FLOW, "금액")),
        }
    return flows


def build_52week(df, day):
    """1년치 고가·저가와 당일 종가를 비교해 신고가·신저가를 가린다."""
    start = (datetime.strptime(day, "%Y%m%d") - timedelta(days=365)).strftime("%Y%m%d")
    highs, lows = [], []

    for code, r in df.nlargest(SCAN_LIMIT, "거래대금").iterrows():
        try:
            hist = stock.get_market_ohlcv(start, day, code)
        except Exception:
            continue
        if hist.empty or len(hist) < 30:
            continue
        close = float(r["종가"])
        if close >= float(hist["고가"].max()):
            highs.append(row_basic(code, r))
        elif close <= float(hist["저가"].min()):
            lows.append(row_basic(code, r))
        if len(highs) >= TOP_FLOW and len(lows) >= TOP_FLOW:
            break

    return {"high": highs[:TOP_FLOW], "low": lows[:TOP_FLOW]}


def build_volume_surge(df, day):
    """직전 5거래일 평균 거래량 대비 급증 종목."""
    start = (datetime.strptime(day, "%Y%m%d") - timedelta(days=20)).strftime("%Y%m%d")
    pool = df[df["거래대금"] >= MIN_VALUE_EOK * 1e8]
    rows = []

    for code, r in pool.nlargest(200, "거래대금").iterrows():
        try:
            hist = stock.get_market_ohlcv(start, day, code)
        except Exception:
            continue
        if len(hist) < 7:
            continue
        avg = float(hist["거래량"].iloc[-6:-1].mean())   # 당일 제외 직전 5거래일
        if avg <= 0:
            continue
        ratio = float(r["거래량"]) / avg * 100
        if ratio < VOLUME_SURGE_MIN:
            continue
        item = row_basic(code, r)
        item["ratio"] = round(ratio)
        rows.append(item)

    rows.sort(key=lambda x: x["ratio"], reverse=True)
    return rows[:TOP_FLOW]


def build_limits(df):
    """상한가·하한가. 제도상 ±30%이나 여유를 둬 ±29.0%로 잡는다."""
    up, down = [], []
    for code, r in df.iterrows():
        rate = float(r["등락률"])
        if rate >= 29.0:
            up.append(row_basic(code, r))
        elif rate <= -29.0:
            down.append(row_basic(code, r))
    up.sort(key=lambda x: x["rate"], reverse=True)
    down.sort(key=lambda x: x["rate"])
    return {"up": up[:10], "down": down[:10]}
