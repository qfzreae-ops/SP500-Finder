# SP500 Finder

S&P 500 종목을 회사명 또는 티커로 검색하고 최신 가격을 확인하는 GitHub Pages 웹앱입니다.

## 파일

- `index.html` : 웹페이지
- `generate_data.py` : S&P 500 구성종목 및 가격 데이터 생성
- `data.json` : 생성된 가격 데이터
- `.github/workflows/update-data.yml` : 30분마다 자동 갱신

## GitHub Pages

Repository → Settings → Pages → Deploy from a branch → `main` / `/ (root)` 선택

## 수동 실행

Actions → Update SP500 Prices → Run workflow

## 주의

가격 데이터는 Yahoo Finance를 통해 수집되는 최신 데이터이며, 거래소의 실시간 체결가와 동일하지 않을 수 있습니다.
GitHub Actions의 scheduled workflow는 실제 실행 시각이 지연될 수 있습니다.
