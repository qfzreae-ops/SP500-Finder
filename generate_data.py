import io
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf


# =========================================================
# 기본 설정
# =========================================================

OUTPUT = Path("data.json")

SP500_URL = (
    "https://en.wikipedia.org/wiki/"
    "List_of_S%26P_500_companies"
)

# S&P 500 구성종목 최소 확인 수
MIN_CONSTITUENTS = 500

# Yahoo Finance 한 번에 조회할 종목 수
BATCH_SIZE = 40

# Yahoo Finance 재시도 횟수
RETRIES = 4

# HTTP 요청 timeout
TIMEOUT = 30

# 배치 사이 대기시간
BATCH_SLEEP = 2

# 전체 데이터 최소 성공률
MIN_SUCCESS_RATE = 0.95


# =========================================================
# 재시도 대기
# =========================================================

def sleep_backoff(attempt):
    """
    Yahoo Finance 또는 Wikipedia 요청 실패 시
    재시도 전에 점진적으로 대기합니다.
    """

    base = 3 * (2 ** (attempt - 1))

    wait = base + random.uniform(0, 2)

    print(
        f"{wait:.1f}초 후 재시도합니다."
    )

    time.sleep(wait)


# =========================================================
# S&P 500 구성종목 가져오기
# =========================================================

def load_sp500_list():

    print()
    print("=" * 60)
    print("S&P 500 구성종목을 가져옵니다.")
    print("=" * 60)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
    }

    last_error = None

    for attempt in range(1, RETRIES + 1):

        try:

            print(
                f"S&P 500 목록 요청 "
                f"{attempt}/{RETRIES}"
            )

            response = requests.get(
                SP500_URL,
                headers=headers,
                timeout=TIMEOUT
            )

            response.raise_for_status()

            # HTML을 문자열로 변환
            html = io.StringIO(
                response.text
            )

            tables = pd.read_html(
                html,
                flavor=[
                    "lxml",
                    "bs4"
                ]
            )

            if not tables:

                raise RuntimeError(
                    "HTML 테이블을 찾을 수 없습니다."
                )

            target = None

            # =================================================
            # 필요한 컬럼을 가진 테이블 찾기
            # =================================================

            for table in tables:

                columns = {
                    str(c).strip()
                    for c in table.columns
                }

                required = {
                    "Symbol",
                    "Security",
                    "GICS Sector"
                }

                if required.issubset(columns):

                    target = table

                    break

            if target is None:

                raise RuntimeError(
                    "S&P 500 구성종목 테이블을 "
                    "찾지 못했습니다."
                )

            # =================================================
            # 구성종목 변환
            # =================================================

            rows = []

            for _, row in target.iterrows():

                ticker = str(
                    row["Symbol"]
                ).strip()

                name = str(
                    row["Security"]
                ).strip()

                sector = str(
                    row["GICS Sector"]
                ).strip()

                if not ticker:
                    continue

                if ticker.lower() == "nan":
                    continue

                # Wikipedia:
                #
                # BRK.B
                #
                # Yahoo Finance:
                #
                # BRK-B

                ticker = ticker.replace(
                    ".",
                    "-"
                )

                rows.append({
                    "ticker": ticker,
                    "name": name,
                    "sector": sector
                })

            # =================================================
            # 중복 제거
            # =================================================

            unique = {}

            for item in rows:

                unique[
                    item["ticker"]
                ] = item

            rows = list(
                unique.values()
            )

            # =================================================
            # 구성종목 수 확인
            # =================================================

            count = len(rows)

            print(
                f"S&P 500 구성종목 확인: "
                f"{count}개"
            )

            if count < MIN_CONSTITUENTS:

                raise RuntimeError(
                    "S&P 500 구성종목 수가 "
                    f"비정상적으로 적습니다: "
                    f"{count}개"
                )

            return rows

        except Exception as e:

            last_error = e

            print(
                f"S&P 500 목록 조회 실패: {e}"
            )

            if attempt < RETRIES:

                sleep_backoff(
                    attempt
                )

    raise RuntimeError(
        "S&P 500 구성종목을 가져오지 못했습니다: "
        f"{last_error}"
    )


# =========================================================
# Yahoo Finance 배치 다운로드
# =========================================================

def download_batch(tickers):

    for attempt in range(1, RETRIES + 1):

        try:

            print(
                f"Yahoo Finance 요청: "
                f"{len(tickers)}개 "
                f"({attempt}/{RETRIES})"
            )

            df = yf.download(
                tickers=tickers,

                period="5d",

                interval="1d",

                group_by="ticker",

                auto_adjust=False,

                progress=False,

                threads=False,

                timeout=TIMEOUT
            )

            if df is not None and not df.empty:

                return df

            print(
                "Yahoo Finance에서 "
                "빈 데이터를 반환했습니다."
            )

        except Exception as e:

            print(
                f"Yahoo Finance 오류: {e}"
            )

        if attempt < RETRIES:

            sleep_backoff(
                attempt
            )

    return None


# =========================================================
# 개별 티커 데이터 추출
# =========================================================

def extract(df, ticker):

    try:

        if df is None:
            return None

        if df.empty:
            return None

        # =================================================
        # MultiIndex 처리
        # =================================================

        if isinstance(
            df.columns,
            pd.MultiIndex
        ):

            level0 = set(
                df.columns.get_level_values(0)
            )

            level1 = set(
                df.columns.get_level_values(1)
            )

            # ---------------------------------------------
            # 구조:
            #
            # AAPL
            #   Close
            #   High
            #   Low
            # ---------------------------------------------

            if ticker in level0:

                x = df[ticker]

            # ---------------------------------------------
            # 반대 구조
            # ---------------------------------------------

            elif ticker in level1:

                x = df.xs(
                    ticker,
                    axis=1,
                    level=1
                )

            else:

                return None

        else:

            x = df

        # =================================================
        # Close 확인
        # =================================================

        if "Close" not in x.columns:

            return None

        close = x["Close"]

        if isinstance(
            close,
            pd.DataFrame
        ):

            close = close.iloc[:, 0]

        close = close.dropna()

        if close.empty:

            return None

        # =================================================
        # 현재 가격
        # =================================================

        price = float(
            close.iloc[-1]
        )

        # =================================================
        # 전일 종가
        # =================================================

        if len(close) >= 2:

            previous_close = float(
                close.iloc[-2]
            )

        else:

            previous_close = None

        # =================================================
        # 등락
        # =================================================

        if (
            previous_close is not None
            and previous_close != 0
        ):

            change = (
                price
                - previous_close
            )

            change_pct = (
                change
                / previous_close
                * 100
            )

        else:

            change = None

            change_pct = None

        # =================================================
        # 거래량
        # =================================================

        volume = None

        if "Volume" in x.columns:

            vol = x["Volume"]

            if isinstance(
                vol,
                pd.DataFrame
            ):

                vol = vol.iloc[:, 0]

            vol = vol.dropna()

            if not vol.empty:

                try:

                    volume = int(
                        vol.iloc[-1]
                    )

                except Exception:

                    volume = None

        return {

            "price":
                price,

            "previous_close":
                previous_close,

            "change":
                change,

            "change_pct":
                change_pct,

            "volume":
                volume
        }

    except Exception as e:

        print(
            f"{ticker} 데이터 처리 실패: {e}"
        )

        return None


# =========================================================
# 메인
# =========================================================

def main():

    print()
    print("=" * 60)
    print("S&P 500 Finder 시작")
    print("=" * 60)

    # =====================================================
    # 1. 최신 S&P 500 목록
    # =====================================================

    rows = load_sp500_list()

    total = len(rows)

    print()
    print(
        f"최종 수집 대상: {total}개"
    )

    # =====================================================
    # 2. 현재 시간
    # =====================================================

    now_utc = datetime.now(
        timezone.utc
    )

    now_kst = (
        now_utc.astimezone()
    )

    # =====================================================
    # 3. 결과 저장
    # =====================================================

    result = []

    failed = []

    # =====================================================
    # 4. 배치 처리
    # =====================================================

    for start in range(
        0,
        total,
        BATCH_SIZE
    ):

        batch = rows[
            start:
            start + BATCH_SIZE
        ]

        tickers = [
            item["ticker"]
            for item in batch
        ]

        end = min(
            start + len(batch),
            total
        )

        print()
        print("-" * 60)

        print(
            f"[진행] "
            f"{start + 1} ~ {end} "
            f"/ {total}"
        )

        df = download_batch(
            tickers
        )

        # =================================================
        # 개별 종목 처리
        # =================================================

        for item in batch:

            ticker = item["ticker"]

            value = extract(
                df,
                ticker
            )

            if value is None:

                failed.append(
                    ticker
                )

                continue

            result.append({

                "ticker":
                    ticker,

                "name":
                    item["name"],

                "sector":
                    item["sector"],

                "exchange":
                    "US",

                "price":
                    value["price"],

                "previous_close":
                    value["previous_close"],

                "change":
                    value["change"],

                "change_pct":
                    value["change_pct"],

                "volume":
                    value["volume"],

                "as_of_kst":
                    now_kst.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
            })

        print(
            f"성공: "
            f"{len(result)} / {total}"
        )

        print(
            f"실패: "
            f"{len(failed)}"
        )

        # =================================================
        # 다음 배치 전 대기
        # =================================================

        if end < total:

            time.sleep(
                BATCH_SLEEP
            )

    # =====================================================
    # 5. 최종 검증
    # =====================================================

    success_count = len(result)

    failed_count = len(failed)

    success_rate = (
        success_count / total
        if total > 0
        else 0
    )

    required_count = int(
        total * MIN_SUCCESS_RATE
    )

    print()
    print("=" * 60)
    print("최종 결과")
    print("=" * 60)

    print(
        f"전체: {total}"
    )

    print(
        f"성공: {success_count}"
    )

    print(
        f"실패: {failed_count}"
    )

    print(
        f"성공률: "
        f"{success_rate * 100:.2f}%"
    )

    print(
        f"최소 필요: "
        f"{required_count}"
    )

    # =====================================================
    # 6. 성공률 부족
    # =====================================================

    if success_count < required_count:

        print()
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )

        print(
            "데이터 수집 성공률 부족"
        )

        print(
            "기존 data.json을 유지합니다."
        )

        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )

        if failed:

            print()
            print(
                "실패 종목:"
            )

            print(
                ", ".join(failed)
            )

        raise RuntimeError(
            "S&P 500 데이터 수집 성공률 부족: "
            f"{success_count}/{total}"
        )

    # =====================================================
    # 7. 중복 티커 확인
    # =====================================================

    ticker_set = set()

    duplicate_tickers = []

    for item in result:

        ticker = item["ticker"]

        if ticker in ticker_set:

            duplicate_tickers.append(
                ticker
            )

        ticker_set.add(
            ticker
        )

    if duplicate_tickers:

        raise RuntimeError(
            "중복 티커가 발견되었습니다: "
            + ", ".join(
                duplicate_tickers
            )
        )

    # =====================================================
    # 8. data.json 생성
    # =====================================================

    data = {

        "service":
            "SP500 Finder",

        "updated_at_utc":
            now_utc.isoformat(),

        "updated_at_kst":
            now_kst.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

        "count":
            success_count,

        "total":
            total,

        "success_rate":
            round(
                success_rate,
                4
            ),

        "stocks":
            result
    }

    # =====================================================
    # 9. 임시 파일 저장
    # =====================================================

    tmp = OUTPUT.with_suffix(
        ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        ),
        encoding="utf-8"
    )

    # =====================================================
    # 10. 최종 파일 교체
    # =====================================================

    tmp.replace(
        OUTPUT
    )

    # =====================================================
    # 11. 완료
    # =====================================================

    print()
    print("=" * 60)
    print("정상 완료")
    print("=" * 60)

    print(
        "data.json 저장 완료"
    )

    print(
        f"저장 종목: "
        f"{success_count}개"
    )

    print(
        f"성공률: "
        f"{success_rate * 100:.2f}%"
    )

    if failed:

        print()
        print(
            f"일부 종목 실패: "
            f"{len(failed)}개"
        )

        print(
            ", ".join(failed)
        )


# =========================================================
# 실행
# =========================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "사용자가 실행을 중단했습니다."
        )

        raise

    except Exception as e:

        print()
        print("=" * 60)
        print("실행 실패")
        print("=" * 60)

        print(
            str(e)
        )

        raise
