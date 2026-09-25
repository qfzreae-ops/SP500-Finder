import csv, json, time
from datetime import datetime, timezone
from pathlib import Path
import yfinance as yf

LIST=Path("sp500_list.csv")
OUTPUT=Path("data.json")
MIN_SUCCESS=20
RETRIES=3
BATCH_SIZE=40

def load_list():
    rows=[]
    with LIST.open(encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    if not rows: raise RuntimeError("sp500_list.csv가 비어 있습니다.")
    return rows

def download_batch(tickers):
    for attempt in range(1,RETRIES+1):
        try:
            df=yf.download(tickers=tickers,period="5d",interval="1d",
                           group_by="ticker",auto_adjust=False,progress=False,
                           threads=False,timeout=20)
            if not df.empty: return df
        except Exception as e:
            print(f"다운로드 실패 {attempt}/{RETRIES}: {e}")
        time.sleep(3*attempt)
    return None

def extract(df,ticker):
    try:
        if df is None or df.empty: return None
        if hasattr(df.columns,"levels"):
            if ticker in df.columns.get_level_values(0):
                x=df[ticker]
            elif ticker in df.columns.get_level_values(1):
                x=df.xs(ticker,axis=1,level=1)
            else: return None
        else: x=df
        close=x["Close"].dropna()
        if close.empty:return None
        price=float(close.iloc[-1])
        prev=float(close.iloc[-2]) if len(close)>1 else None
        change=price-prev if prev is not None else None
        pct=(change/prev*100) if prev not in (None,0) else None
        vol=x["Volume"].dropna()
        return price,prev,change,pct,(int(vol.iloc[-1]) if len(vol) else None)
    except Exception as e:
        print(ticker,"처리 실패:",e);return None

def main():
    rows=load_list(); result=[]; now=datetime.now(timezone.utc).astimezone()
    for start in range(0,len(rows),BATCH_SIZE):
        batch=rows[start:start+BATCH_SIZE]
        tickers=[r["ticker"] for r in batch]
        print(f"가격 조회 {start+1}~{start+len(batch)} / {len(rows)}")
        df=download_batch(tickers)
        for r in batch:
            v=extract(df,r["ticker"])
            if v:
                price,prev,ch,pct,vol=v
                result.append({"ticker":r["ticker"],"name":r["name"],"sector":r["sector"],
                               "exchange":"US","price":price,"previous_close":prev,
                               "change":ch,"change_pct":pct,"volume":vol,
                               "as_of_kst":now.strftime("%Y-%m-%d %H:%M:%S")})
        time.sleep(1)

    print("성공:",len(result)," / 전체:",len(rows))
    if len(result)<MIN_SUCCESS:
        raise RuntimeError("수집된 종목 수가 너무 적어 기존 data.json을 유지합니다.")

    data={"service":"SP500 Finder","updated_at_utc":datetime.now(timezone.utc).isoformat(),
          "updated_at_kst":now.strftime("%Y-%m-%d %H:%M:%S"),"count":len(result),"stocks":result}
    tmp=OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(OUTPUT)
    print("data.json 갱신 완료")

if __name__=="__main__": main()
