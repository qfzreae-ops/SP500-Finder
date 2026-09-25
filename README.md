# SP500 Finder
S&P 500 종목 검색 및 최신 가격 조회 웹앱입니다.

- `index.html`: 웹페이지
- `sp500_list.csv`: 종목 목록
- `generate_data.py`: 가격 수집 및 data.json 생성
- `data.json`: 웹페이지용 데이터
- `.github/workflows/update-data.yml`: 30분마다 자동 갱신

GitHub Pages: Settings → Pages → Deploy from a branch → main / root
수동 실행: Actions → Update SP500 Prices → Run workflow

주의: 제공 데이터는 Yahoo Finance의 최신 데이터이며 실시간 체결가와 동일하지 않을 수 있습니다.
