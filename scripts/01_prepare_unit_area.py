"""① 전산팀 세대별 면적 엑셀 → 빅쿼리 업로드용 CSV
입력: 전산팀 추출 엑셀 (공동주택코드, 공동주택명, 동, 호, 평형, 면적)
처리: 완전 중복 행만 제거(그 외 원본 그대로), 면적대·정렬순서 컬럼 추가, 면적 공란은 '면적 미등록'
출력: data/apt_unit_area_YYYYMMDD.csv  → upload_to_bigquery.py 로 pbi_ref_apt_unit_area 에 적재

사용: python 01_prepare_unit_area.py <전산팀엑셀.xlsx> [YYYYMMDD]
"""
import sys, datetime
import pandas as pd
from common import DATA

BINS = [0, 40, 60, 85, 102, 135, 10000]
LABELS = ["40㎡ 이하", "40~60㎡", "60~85㎡", "85~102㎡", "102~135㎡", "135㎡ 초과"]

def main(xlsx, tag):
    df = pd.read_excel(xlsx, dtype=str)            # 코드 앞자리 0 보존을 위해 문자열로 읽음
    n0 = len(df); df = df.drop_duplicates()
    print(f"완전중복 제거 {n0-len(df)}행 → {len(df):,}행")
    out = pd.DataFrame({
        "apartment_code": df["공동주택코드"], "apartment_name": df["공동주택명"],
        "dong": df["동"], "ho": df["호"],
        "pyeong": pd.to_numeric(df["평형"]).astype("Int64"),
        "area_m2": pd.to_numeric(df["면적"]),
    })
    out["area_band"] = pd.cut(out.area_m2, BINS, labels=LABELS, right=True).astype(object).fillna("면적 미등록")
    order = {l: i + 1 for i, l in enumerate(LABELS)}; order["면적 미등록"] = 99
    out["area_band_order"] = out.area_band.map(order)
    print(out.area_band.value_counts())
    path = DATA / f"apt_unit_area_{tag}.csv"
    out.to_csv(path, index=False, encoding="utf-8"); print("saved", path)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else f"{datetime.date.today():%Y%m%d}")
