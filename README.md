# 아파트 면적대 × 준공연대별 개별난방 판매량 분석

작성: 배경호 (마케팅팀 기획) · 2026-11-20
결과물
- `output/아파트_면적대_준공연대별_개별난방_판매량분석_20261120.xlsx` (팀장님 보고용, 산정방식 시트 포함)
- `app/app.py` 스트림릿 탐색 앱 (구간·이상치 기준을 바꿔가며 보기 + 탐색적 분석) — `app/실행.bat` 더블클릭

## 1. 목적
아파트 세대의 **전용면적**과 **준공연대**에 따라 개별난방 연간 판매량이 어떻게 다른지 파악.
(영업 타깃 분석, 유사 단지 판매량 추정, 신규 단지 판매량 예측 등에 재사용)

## 2. 핵심 결과 (2025년, 이상치 제외 ㎡당 판매량)
| 1980년대 | 1990년대 | 2000년대 | 2010년대 | 2020년대 |
|---:|---:|---:|---:|---:|
| 9.24 | 9.04 | 8.67 | 8.08 | 6.65 ㎥/㎡ |

- 오래된 아파트일수록 ㎡당 사용량이 많음. 2020년대 아파트는 1980년대보다 약 28% 적게 씀.
- 이상치(빈집·거의 미사용)를 포함하거나 세대당으로 보면 이 패턴이 흐려짐
  → 오래된 단지는 빈집 비중이 높고 실제 면적도 작기 때문. **준공연대 비교는 '이상치 제외 ㎡당' 기준**.
- 판매량 예측·사업계획에는 **이상치 포함** 값을 쓸 것 (빈집도 실제 판매량에 반영됨).

## 3. 빅쿼리 테이블 (dse-marketing.sales)
| 테이블 | 내용 | 만드는 방법 |
|---|---|---|
| `pbi_ref_apt_unit_area` | 세대별(단지코드·동·호) 전용면적 830,596세대 | 전산팀 요청 → `01_prepare_unit_area.py` → 업로드 |
| `pbi_ref_apt_built_year` | 단지별 준공연도 2,911개 단지 | `02_build_built_year.py` → 업로드 |
| `sale` | 월별 판매량 (기존) | 빅쿼리용스트림릿에서 매월 업데이트 |

## 4. 계산 규칙 (요약 — 자세한 건 엑셀 `2_산정방식` 시트)
1. 상품: **취사난방용 → 개별난방용**으로 바꿔 하나로 집계. 취사용·중앙난방용 제외.
2. 아파트만: `sale.industry_name = '아파트'` (연립·다세대·다가구 제외)
3. 세대: 지번주소 끝 "○○동 ○○호" 정규식 → 공동주택코드+동+호
4. 연간 판매량: 판매연도별 합계, **판매기록 10개월 이상 & 판매량>0** 세대만
5. 면적 매칭: 공동주택코드+동+호 (매칭률 99.94%), 면적 미등록 제외
6. **이상치: ㎡당 연 2.5㎥ 미만** 세대 (60~85㎡ ≈ 200㎥, 40㎡ ≈ 100㎥). 고정 200㎥는 소형 세대를 과도하게 잘라 사용 안 함
7. 면적대: 40㎡ 이하 / 40~60 / 60~85 / 85~102 / 102~135 / 135㎡ 초과 (상한 포함)
8. 준공연대: K-apt 사용승인일(세대 기준 89%) → 없으면 최초공급연도 추정(11%)

## 5. 스트림릿 탐색 앱 (app/)
- 실행: `app\실행.bat` 더블클릭 또는 `cd app` → `streamlit run app.py`
- 데이터: `data/unit_year.parquet` (세대×연도 277만 행, 38MB)만 읽음 → **앱 사용 중 빅쿼리 조회·비용 없음**
  - 동·호 등 세대 식별정보는 저장하지 않음(세대 키는 해시값)
- 사이드바: 기준연도 / 아파트만 / 시군구 / K-apt 준공연도만 / 준공구간(10년·5년·직접입력) / 면적구간(기본·주택형·10㎡·직접입력) / 이상치 기준(㎡당, 기본 2.5) / 표본 경고 기준
- 탭: 개요(세대당=면적×㎡당 분해) · 면적×준공 히트맵 · 시군구별 · 연도별 추이 · 단지별 산점도(추세선 대비 많이/적게 쓰는 단지) · 탐색적 분석(분포·박스플롯·면적-판매량 관계·이상치 비중·기술통계) · 데이터(집계 CSV 다운로드)
- 데이터 갱신(새 연도 반영 등)할 때만: `sql/05_unit_year_extract.sql` 기간 수정 → `python scripts/00_extract_unit_data.py` (빅쿼리 1회 조회, 임시테이블·GCS 파일 자동 삭제)

## 6. 폴더 구조
```
README.md
app/
  app.py                    스트림릿 탐색 앱
  실행.bat                  앱 실행 (더블클릭)
scripts/
  00_extract_unit_data.py   앱용 세대×연도 데이터 1회 추출 (빅쿼리 → GCS parquet → data/)
  common.py                 빅쿼리·GCS 클라이언트 (키: D:\Project\빅쿼리용스트림릿\*.json 사용, 복사 안 함)
  upload_to_bigquery.py     CSV → GCS(daesung_marketing) → 빅쿼리 (WRITE_TRUNCATE)
  01_prepare_unit_area.py   전산팀 면적 엑셀 → 업로드용 CSV
  02_build_built_year.py    K-apt 사용승인일 ↔ 당사코드 매칭 → 준공연도 CSV
  03_build_report.py        집계 SQL 실행 → 보고서 엑셀 생성
  requirements.txt
sql/
  01_ddl_pbi_ref_apt_unit_area.sql   면적 테이블 DDL (자동감지 금지 — 코드 앞자리 0 보존)
  02_ddl_pbi_ref_apt_built_year.sql  준공연도 테이블 DDL
  03_agg_area_decade.sql             보고서 원자료 집계 쿼리 (연도 범위는 WHERE에서 수정)
  04_check_sale_unit_match.sql       판매 세대 ↔ 면적 매칭률 점검
  05_unit_year_extract.sql           앱용 세대×연도 원자료 추출 쿼리
data/
  원본/20261120_공동주택세대별면적_전산팀.xlsx   전산팀 원본
  apt_unit_area_20261120.csv        pbi_ref_apt_unit_area 업로드본
  apt_built_year_20261120.csv       pbi_ref_apt_built_year 업로드본
  agg_area_decade.csv               03 쿼리 결과(2021~2025)
  unit_year.parquet                 앱용 세대×연도 데이터(2021~2025)
output/
  아파트_면적대_준공연대별_개별난방_판매량분석_20261120.xlsx
```

## 7. 다시 돌리기 (예: 내년에 2026년까지 반영)
```bash
cd scripts
pip install -r requirements.txt

# (면적 자료를 새로 받았을 때만)
python 01_prepare_unit_area.py "..\data\원본\새파일.xlsx" 20271120
python upload_to_bigquery.py ..\data\apt_unit_area_20271120.csv pbi_ref_apt_unit_area
#   → sql/04_check_sale_unit_match.sql 로 매칭률 확인

# (K-apt 단지기본정보를 새로 받았을 때만 — 공공데이터포털)
python 02_build_built_year.py "D:\Project\10_아파트지도\data\기본정보\<새 K-apt 매칭본>.csv" 20271120
python upload_to_bigquery.py ..\data\apt_built_year_20271120.csv pbi_ref_apt_built_year

# 보고서: sql/03_agg_area_decade.sql 의 기간(WHERE sales_ym BETWEEN ...)을 바꾼 뒤
python 03_build_report.py 20271120

# 스트림릿 앱 데이터: sql/05_unit_year_extract.sql 기간 수정 후
python 00_extract_unit_data.py
```
- 보고서 엑셀의 3·4·5·7 시트는 노란 칸에 연도를 넣으면 해당 연도로 바뀜.
- `1_요약`의 '주요 결과' 문구는 2026-11 분석 기준으로 작성된 고정 문구 → 새로 돌리면 숫자 보고 직접 수정.
- 02 스크립트의 K-apt 입력은 '시스템매칭완료' 형식(최종_시스템코드·위도·경도 포함)이어야 함.
  새 K-apt 원본만 있으면 기존 매칭표 없이 B~E 단계(주소·좌표·단지명)로만 매칭됨.

## 8. 한계
- 최초공급연도 추정치는 실제 준공보다 늦을 수 있음(중앙→개별 전환 단지). 1983은 데이터 하한값.
- 세대수 300 미만 칸은 참고용. 2020년대 단지는 2021~2022년 표본이 작음.
- 거주 인원·공실 자료가 없어 이상치의 원인(빈집·고령 1인가구 등)은 추정.
- 기온 보정 전 실적치.

## 9. 관련 위치
- 빅쿼리 업로드 앱: `D:\Project\빅쿼리용스트림릿` (02_데이터업로드 페이지와 같은 방식)
- K-apt 원본·기존 매칭: `D:\Project\10_아파트지도\data\기본정보`
- 예전 로컬 면적별 판매량(파워BI mart): `D:\marketing\data\아파트면적별판매량`, `D:\marketing\power_bi\mart`
