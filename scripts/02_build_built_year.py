"""② 단지별 준공연도 테이블 생성 (K-apt 사용승인일 → 당사 공동주택코드 매칭)

입력
  - K-apt 단지기본정보(시스템매칭완료본): D:\\Project\\10_아파트지도\\data\\기본정보\\20251212_단지_기본정보_시스템매칭완료.csv
    (컬럼: 단지코드, 단지명, 시군구, 사용승인일, 세대수, 위도, 경도, 도로명주소_정제, 1번_도로명주소, 1번_법정동주소, 최종_시스템코드 …)
  - 빅쿼리 pbi_ref_apt_info / pbi_dim_apartment / pbi_ref_apt_unit_area (당사 단지 목록·주소·좌표·최초공급연도)
매칭 순서 (앞 단계에서 붙은 단지는 다음 단계에서 제외)
  A. 기존 매칭표(최종_시스템코드)
  B. 도로명주소(도로명+건물번호) 일치 + 같은 시군구
  C. 좌표 최근접 K-apt 단지: (200m 이내 & 단지명 유사도≥0.6) 또는 (50m 이내 & 유사도≥0.4)
  D. 지번주소(동/리+번지) 일치 + 같은 시군구
  E. 같은 시군구 안에서 단지명 유사도≥0.9 인 K-apt 단지가 1개
  오매칭 제거: A 이외 방식에서 최초공급연도+2 < 사용승인연도 (준공 전 공급은 불가능) 이면 버림
  매칭 안 된 단지 → 최초공급연도 추정(pbi_dim_apartment.built_year_est) 사용, 1983은 데이터 하한이라 별도 표시
출력: data/apt_built_year_YYYYMMDD.csv → upload_to_bigquery.py 로 pbi_ref_apt_built_year 에 적재

사용: python 02_build_built_year.py <K-apt csv> [YYYYMMDD]
"""
import sys, re, datetime
import numpy as np, pandas as pd
from difflib import SequenceMatcher
from common import DATA, query_df

SQL_OURS = """
SELECT i.apartment_code, i.apt_name, i.address, i.lat, i.lon, d.sigungu, d.built_year_est
FROM `dse-marketing.sales.pbi_ref_apt_info` i
LEFT JOIN `dse-marketing.sales.pbi_dim_apartment` d USING(apartment_code)"""
SQL_BASE = """
SELECT COALESCE(d.apartment_code,u.apartment_code) apartment_code,
       COALESCE(d.apartment_name,u.apartment_name) apartment_name, d.built_year_est est
FROM `dse-marketing.sales.pbi_dim_apartment` d
FULL JOIN (SELECT apartment_code, ANY_VALUE(apartment_name) apartment_name
           FROM `dse-marketing.sales.pbi_ref_apt_unit_area` GROUP BY 1) u USING(apartment_code)"""


# 육안 검토로 오매칭 판정한 단지 (당사코드) — 필요 시 추가
MANUAL_REJECT = {"042002"}  # 성서주공2단지 → K-apt '대구성서3'(3단지)로 잘못 붙음


def nm(s):
    s = "" if pd.isna(s) else str(s)
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"아파트|APT|단지|\s|-|·", "", s.upper())

def sim(a, b): return SequenceMatcher(None, nm(a), nm(b)).ratio()

def roadkey(s):
    m = re.search(r"(\S+(?:로|길)(?:\d+\S*?길)?)\s*(\d+(?:-\d+)?)", str(s or ""))
    return f"{m.group(1)} {m.group(2)}" if m else None

def lotkey(s):
    m = re.search(r"(\S+[동리가])\s+(\d+(?:-\d+)?)", str(s or ""))
    return f"{m.group(1)} {m.group(2)}" if m else None

def same_sgg(series, sgg): return series.str.contains(str(sgg)[:2], na=False)


def match(ours, k):
    for c in ["lat", "lon"]: ours[c] = pd.to_numeric(ours[c])
    ours["built_year_est"] = pd.to_numeric(ours["built_year_est"])
    k = k.copy()
    k["lat"] = pd.to_numeric(k["위도"]); k["lon"] = pd.to_numeric(k["경도"])
    k["code_prev"] = k["최종_시스템코드"].str.replace(r"\.0$", "", regex=True).str.zfill(6).where(k["최종_시스템코드"].notna())
    k["rk"] = k["도로명주소_정제"].fillna(k["1번_도로명주소"]).map(roadkey)
    k["lk"] = k["1번_법정동주소"].map(lotkey)
    ours["rk"] = ours.address.map(roadkey)
    ours["lk"] = ours.address.str.extract(r"\((.*?)\)")[0].map(lotkey)
    res = {}
    # A
    for c, g in k[k.code_prev.notna()].groupby("code_prev"):
        res[c] = (g.iloc[0]["단지코드"], "기존매칭(아파트코드)")
    # B
    used = {v[0] for v in res.values()}; kk = k[~k["단지코드"].isin(used)]
    for _, r in ours[~ours.apartment_code.isin(res)].iterrows():
        if r.rk:
            c = kk[(kk.rk == r.rk) & same_sgg(kk["시군구"], r.sigungu)]
            if len(c): res[r.apartment_code] = (c.iloc[0]["단지코드"], "도로명주소")
    # C
    used = {v[0] for v in res.values()}
    cand = k[~k["단지코드"].isin(used) & k.lat.notna()]
    R = 6371000
    for _, r in ours[~ours.apartment_code.isin(res) & ours.lat.notna() & ours.apt_name.notna()].iterrows():
        dl = np.radians(cand.lat - r.lat); dn = np.radians(cand.lon - r.lon)
        dist = 2 * R * np.arcsin(np.sqrt(np.sin(dl / 2) ** 2 + np.cos(np.radians(r.lat)) * np.cos(np.radians(cand.lat)) * np.sin(dn / 2) ** 2))
        j = dist.idxmin(); d = dist[j]; s = sim(r.apt_name, cand.loc[j, "단지명"])
        if (d < 200 and s >= 0.6) or (d < 50 and s >= 0.4):
            res[r.apartment_code] = (cand.loc[j, "단지코드"], "좌표+단지명")
    # D, E
    for _, r in ours[~ours.apartment_code.isin(res)].iterrows():
        if r.lk:
            c = k[(k.lk == r.lk) & same_sgg(k["시군구"], r.sigungu)]
            if len(c): res[r.apartment_code] = (c.iloc[0]["단지코드"], "지번주소"); continue
        if isinstance(r.apt_name, str):
            c = k[same_sgg(k["시군구"], r.sigungu)].copy()
            c["s"] = c["단지명"].map(lambda x: sim(r.apt_name, x))
            c = c[c.s >= 0.9]
            if len(c) == 1: res[r.apartment_code] = (c.iloc[0]["단지코드"], "단지명(시군구내)")
    m = pd.DataFrame([(c, kc, meth) for c, (kc, meth) in res.items()], columns=["code", "kapt_code", "match_method"])
    kd = k.drop_duplicates("단지코드").set_index("단지코드")
    m["kapt_name"] = m.kapt_code.map(kd["단지명"]); m["approve"] = m.kapt_code.map(kd["사용승인일"])
    est = ours.drop_duplicates("apartment_code").set_index("apartment_code")["built_year_est"]
    m["est"] = m.code.map(est); m["ay"] = m.approve.str[:4].astype(int)
    bad = (m.match_method != "기존매칭(아파트코드)") & (m.est > 1983) & (m.est + 2 < m.ay)
    bad |= m.code.isin(MANUAL_REJECT)
    print("오매칭 제거", int(bad.sum())); print(m[bad][["code", "kapt_name", "match_method", "approve", "est"]])
    return m[~bad]


def build(base, m):
    base["est"] = pd.to_numeric(base.est).astype("Int64")
    x = base.merge(m[["code", "kapt_code", "kapt_name", "match_method", "approve"]], left_on="apartment_code", right_on="code", how="left")
    dt = pd.to_datetime(x.approve, format="%Y%m%d", errors="coerce")
    x["built_date"] = dt.dt.date; x["built_year"] = dt.dt.year.astype("Int64")
    x["built_source"] = np.where(x.match_method.notna(), "K-apt 사용승인일", None)
    fill = x.built_year.isna() & x.est.notna()
    x.loc[fill, "built_year"] = x.loc[fill, "est"]; x.loc[fill, "built_source"] = "최초공급연도 추정"
    x.loc[(x.built_source == "최초공급연도 추정") & (x.est == 1983), "built_source"] = "최초공급연도 추정(1983 이전 가능)"
    x.loc[x.built_year.isna(), "built_source"] = "없음"
    x["built_decade"] = x.built_year.map(lambda y: f"{(int(y)//10)*10}년대" if pd.notna(y) else "미상")
    return x[["apartment_code", "apartment_name", "built_year", "built_date", "built_decade", "built_source",
              "kapt_code", "kapt_name", "match_method", "est"]].rename(columns={"est": "first_supply_year_est"})


if __name__ == "__main__":
    kapt = pd.read_csv(sys.argv[1], dtype=str)
    tag = sys.argv[2] if len(sys.argv) > 2 else f"{datetime.date.today():%Y%m%d}"
    ours, base = query_df(SQL_OURS), query_df(SQL_BASE)
    m = match(ours, kapt)
    print(m.match_method.value_counts())
    out = build(base, m)
    print(out.built_source.value_counts())
    path = DATA / f"apt_built_year_{tag}.csv"; out.to_csv(path, index=False, encoding="utf-8"); print("saved", path)
