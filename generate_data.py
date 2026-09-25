import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

OUTPUT = Path("data.json")
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def get_sp500_list():
    tables = pd.read_html(WIKI_URL)
    table = tables[0]

    # Wikipedia의 컬럼명 기준
    cols = {str(c).strip(): c for c in table.columns}
    symbol_col = cols.get("Symbol")
    name_col = cols.get("Security")
    sector_col = cols.get("GICS Sector")

    if not symbol_col or not name_col:
        raise RuntimeError("S&P 500 구성종목 표의 컬럼을 찾지 못했습니다.")

    out = pd.DataFrame({
        "ticker": table[symbol_col].astype(str).str.replace(".", "-", regex=False),
        "name": table[name_col].astype(str),
        "sector": table[sector_col].astype(str) if sector_col else "",
    })
    out = out.drop_duplicates("ticker").reset_index(drop=True)
    return out


def download_prices(tickers):
    # 500개를 한 번에 받되, 실패 시 100개 단위로 재시도합니다.
    try:
        df = yf.download(
            tickers=tickers,
            period="5d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
        if not df.empty:
            return df
    except Exception as e:
        print("일괄 다운로드 실패:", e)

    frames = []
    for i in range(0, len(tickers), 100):
        batch = tickers[i:i+100]
        try:
            x = yf.download(
                tickers=batch,
                period="5d",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
            if not x.empty:
                frames.append(x)
        except Exception as e:
            print(f"{i}~{i+len(batch)} 실패:", e)
        time.sleep(1)

    if not frames:
        raise RuntimeError("가격 데이터를 하나도 받지 못했습니다.")

    # 재시도 결과는 ticker별로 다시 합칩니다.
    result = {}
    for frame in frames:
        if isinstance(frame.columns, pd.MultiIndex):
            for ticker in frame.columns.get_level_values(0).unique():
                result[ticker] = frame[ticker]
        else:
            result[tickers[0]] = frame

    return result


def extract_rows(sp500, prices):
    rows = []

    for _, r in sp500.iterrows():
        ticker = r["ticker"]
        p = None

        try:
            if isinstance(prices, dict):
                p = prices.get(ticker)
            elif isinstance(prices.columns, pd.MultiIndex):
                if ticker in prices.columns.get_level_values(0):
                    p = prices[ticker]
                elif ticker in prices.columns.get_level_values(1):
                    p = prices.xs(ticker, axis=1, level=1)
            else:
                p = prices
        except Exception:
            p = None

        if p is None or getattr(p, "empty", True):
            continue

        try:
            close = pd.to_numeric(p["Close"], errors="coerce").dropna()
            volume = pd.to_numeric(p["Volume"], errors="coerce").dropna()
            if len(close) == 0:
                continue

            price = float(close.iloc[-1])
            previous = float(close.iloc[-2]) if len(close) >= 2 else None
            change = price - previous if previous is not None else None
            change_pct = (change / previous * 100) if previous not in (None, 0) else None
            vol = int(volume.iloc[-1]) if len(volume) else None

            rows.append({
                "ticker": ticker,
                "name": r["name"],
                "sector": r["sector"],
                "exchange": "US",
                "price": price,
                "previous_close": previous,
                "change": change,
                "change_pct": change_pct,
                "volume": vol,
            })
        except Exception as e:
            print(ticker, "처리 실패:", e)

    return rows


def main():
    print("S&P 500 구성종목을 가져옵니다.")
    sp500 = get_sp500_list()
    tickers = sp500["ticker"].tolist()
    print("종목 수:", len(tickers))

    print("가격 데이터를 가져옵니다.")
    prices = download_prices(tickers)

    rows = extract_rows(sp500, prices)
    print("가격 확보 종목 수:", len(rows))

    if len(rows) < 400:
        raise RuntimeError(f"가격 데이터가 너무 적습니다: {len(rows)}개")

    now = datetime.now(timezone.utc).astimezone()
    data = {
        "service": "SP500 Finder",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "updated_at_kst": now.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(rows),
        "stocks": rows,
    }

    OUTPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{OUTPUT} 생성 완료")


if __name__ == "__main__":
    main()
