"""공통 도구. 날짜 계산과 전 종목 시세 수집을 담당한다."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from pykrx import stock

KST = ZoneInfo("Asia/Seoul")
LOOKBACK_DAYS = 7
INDEX_CODES = [("1001", "코스피"), ("2001", "코스닥"), ("1028", "코스피200")]


def eok(value):
    """원 단위를 억원으로 변환."""
    return round(float(value) / 1e8)


def latest_business_day():
    """오늘부터 거슬러 올라가며 시세가 있는 마지막 영업일을 찾는다."""
    today = datetime.now(KST).date()
    for back in range(LOOKBACK_DAYS):
        day = (today - timedelta(days=back)).strftime("%Y%m%d")
        try:
            if not stock.get_index_ohlcv(day, day, "1001").empty:
                return day
        except Exception as e:
            print(f"{day} 확인 중 오류: {e}")
    raise RuntimeError(f"최근 {LOOKBACK_DAYS}일 내 영업일을 찾지 못했습니다.")


def prev_business_day(day):
    """주어진 날짜의 직전 영업일."""
    base = datetime.strptime(day, "%Y%m%d").date()
    for back in range(1, LOOKBACK_DAYS + 1):
        d = (base - timedelta(days=back)).strftime("%Y%m%d")
        try:
            if not stock.get_index_ohlcv(d, d, "1001").empty:
                return d
        except Exception:
            continue
    return None


def build_ohlcv(day):
    """코스피·코스닥 전 종목 시세를 하나의 표로 합친다."""
    frames = []
    for market in ("KOSPI", "KOSDAQ"):
        df = stock.get_market_ohlcv(day, market=market).copy()
        df["시장"] = "코스피" if market == "KOSPI" else "코스닥"
        frames.append(df)

    all_df = pd.concat(frames)
    all_df = all_df[all_df["거래대금"] > 0]

    names = []
    for code in all_df.index:
        try:
            names.append(stock.get_market_ticker_name(code))
        except Exception:
            names.append(code)
    all_df["종목명"] = names
    return all_df


def row_basic(code, r):
    """목록에 공통으로 들어가는 기본 항목."""
    return {
        "name": r["종목명"],
        "code": code,
        "market": r["시장"],
        "close": int(r["종가"]),
        "rate": round(float(r["등락률"]), 2),
    }


def build_indices(day):
    """지수 종가와 전일 대비 등락."""
    out = []
    prev_day = prev_business_day(day)
    for code, name in INDEX_CODES:
        df = stock.get_index_ohlcv(day, day, code)
        if df.empty:
            continue
        close = float(df.iloc[0]["종가"])
        prev_close = close
        if prev_day:
            pdf = stock.get_index_ohlcv(prev_day, prev_day, code)
            if not pdf.empty:
                prev_close = float(pdf.iloc[0]["종가"])
        diff = close - prev_close
        out.append({
            "name": name,
            "close": round(close, 2),
            "diff": round(diff, 2),
            "rate": round(diff / prev_close * 100, 2) if prev_close else 0.0,
        })
    return out


def build_summary(df, day):
    """시장 전체 거래대금과 투자자별 순매수 합계."""
    net = {}
    for label, key in (("외국인", "net_foreign"), ("기관합계", "net_institution")):
        total = 0
        for market in ("KOSPI", "KOSDAQ"):
            try:
                t = stock.get_market_trading_value_by_investor(day, day, market)
                if label in t.index:
                    total += int(t.loc[label, "순매수"])
            except Exception as e:
                print(f"{market} {label} 합계 조회 실패: {e}")
        net[key] = eok(total)

    return {
        "total_value": eok(df["거래대금"].sum()),
        "kospi_value": eok(df[df["시장"] == "코스피"]["거래대금"].sum()),
        "kosdaq_value": eok(df[df["시장"] == "코스닥"]["거래대금"].sum()),
        **net,
    }
