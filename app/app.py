"""아파트 면적·준공연대별 개별난방 판매량 탐색 앱
- 데이터: ../data/unit_year.parquet (scripts/00_extract_unit_data.py 로 1회 추출, 빅쿼리 재조회 없음)
- 실행:  streamlit run app.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# 스트림릿 버전 호환: 1.50 미만은 width="stretch" 미지원 → use_container_width 사용
_v = tuple(int(x) for x in st.__version__.split(".")[:2])
W = {"width": "stretch"} if _v >= (1, 50) else {"use_container_width": True}

st.set_page_config(page_title="아파트 면적·준공연대별 판매량", layout="wide")
DATA = Path(__file__).resolve().parents[1] / "data" / "unit_year.parquet"


@st.cache_data(show_spinner="데이터 불러오는 중…")
def load():
    df = pd.read_parquet(DATA)
    df["per_m2"] = df["m3"] / df["area_m2"]
    return df


if not DATA.exists():
    st.error(f"데이터 파일이 없습니다: {DATA}\n\nscripts/00_extract_unit_data.py 를 먼저 실행하세요.")
    st.stop()
df_all = load()
YEARS = sorted(df_all["y"].unique().tolist())

# ───────────────────────── 구간 정의 ─────────────────────────
INF = 10_000
AREA_PRESETS = {
    "기본 6구간": [0, 40, 60, 85, 102, 135, INF],
    "주택형 기준 (59·74·84형 등)": [0, 40, 55, 65, 78, 85, 102, 135, INF],
    "10㎡ 단위": list(range(0, 161, 10)) + [INF],
}
DECADE_PRESETS = {"10년 단위": 10, "5년 단위": 5}


def parse_edges(text, lo, hi):
    try:
        v = sorted({float(x) for x in text.replace(" ", "").split(",") if x})
        return [lo] + [x for x in v if lo < x < hi] + [hi]
    except ValueError:
        return None


def area_labels(edges):
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if a == 0: out.append(f"{b:g}㎡ 이하")
        elif b >= INF: out.append(f"{a:g}㎡ 초과")
        else: out.append(f"{a:g}~{b:g}㎡")
    return out


def year_bins(step=None, edges=None):
    if edges is None:
        edges = list(range(1970, 2031, step))
    labels = []
    for a, b in zip(edges[:-1], edges[1:]):
        labels.append(f"{int(a)}~{int(b) - 1}" if b - a > 1 else f"{int(a)}")
    return edges, labels


# ───────────────────────── 사이드바 ─────────────────────────
sb = st.sidebar
sb.header("필터")
pmode = sb.radio("판매 기간", ["단일 연도", "여러 해 평균"], horizontal=True,
                 help="여러 해 평균: 고른 기간의 세대×연도 기록을 모두 모아 '판매량 합계 ÷ 면적 합계'로 계산 → 연평균 값. "
                      "세대수는 연평균 세대수로 표시. 이상치는 해마다 따로 판정.")
if pmode == "단일 연도":
    year = sb.selectbox("판매연도", YEARS, index=len(YEARS) - 1,
                        help="이 연도 1~12월 판매량 합계(세대별 연간 판매량)로 계산합니다. 준공연도가 아닙니다.")
    PY = (year, year)
else:
    PY = sb.select_slider("판매연도 범위", options=YEARS, value=(YEARS[-3], YEARS[-1]),
                          help="예: 2023~2025 → 3년 연평균. 준공연도가 아닙니다.")
    year = PY[1]
NY = PY[1] - PY[0] + 1
PL = f"{PY[0]}년" if NY == 1 else f"{PY[0]}~{PY[1]}년 평균"
apt_only = sb.checkbox("아파트만 (연립·다세대 제외)", True)
sgg_all = sorted(df_all["sigungu"].astype(str).unique())
sgg = sb.multiselect("시군구", sgg_all, default=sgg_all)
kapt_only = sb.checkbox("준공연도 K-apt 사용승인일인 단지만", False,
                        help="체크 해제 시 최초공급연도 추정 단지도 포함 (세대 기준 약 11%)")

sb.header("구간")
dmode = sb.radio("준공연도 구간", ["10년 단위", "5년 단위", "직접 입력"], horizontal=True)
if dmode == "직접 입력":
    txt = sb.text_input("경계 연도 (쉼표)", "1990,2000,2005,2010,2015,2020")
    e = parse_edges(txt, 1970, 2031)
    if e is None: sb.error("숫자와 쉼표만 입력하세요"); st.stop()
    YE, YL = year_bins(edges=[int(x) for x in e])
else:
    YE, YL = year_bins(step=DECADE_PRESETS[dmode])

amode = sb.radio("면적 구간", list(AREA_PRESETS) + ["직접 입력"])
if amode == "직접 입력":
    txt = sb.text_input("경계 면적㎡ (쉼표)", "40,60,75,85,102,135")
    AE = parse_edges(txt, 0, INF)
    if AE is None: sb.error("숫자와 쉼표만 입력하세요"); st.stop()
else:
    AE = AREA_PRESETS[amode]
AL = area_labels(AE)

sb.header("이상치")
thr = sb.slider("㎡당 연 판매량 이 값 미만 = 이상치(빈집·거의 미사용)", 0.0, 5.0, 2.5, 0.1)
show_all = sb.checkbox("이상치 포함 값도 같이 보기", True)
min_n = sb.number_input("표본 경고 기준 (세대수 미만은 흐리게)", 0, 5000, 300, 50)


# ───────────────────────── 필터 & 파생 ─────────────────────────
@st.cache_data(show_spinner=False)
def prep(apt_only, sgg, kapt_only, YE, YL, AE, AL, thr):
    d = df_all
    if apt_only: d = d[d["is_apt"]]
    d = d[d["sigungu"].astype(str).isin(sgg)]
    if kapt_only: d = d[d["built_source"] == "K-apt 사용승인일"]
    d = d.copy()
    d["준공구간"] = pd.cut(d["built_year"].astype("float"), YE, labels=YL, right=False)
    d["면적구간"] = pd.cut(d["area_m2"], AE, labels=AL, right=True)
    d["정상"] = d["per_m2"] >= thr
    return d


d = prep(apt_only, tuple(sgg), kapt_only, tuple(YE), tuple(YL), tuple(AE), tuple(AL), thr)
dy = d[d["y"].between(PY[0], PY[1])]


def agg(frame, keys):
    g = frame.assign(m3_n=frame["m3"].where(frame["정상"], 0), a_n=frame["area_m2"].where(frame["정상"], 0),
                     u_n=frame["정상"].astype(int))
    r = g.groupby(keys, observed=True).agg(세대수_전체=("m3", "size"), 판매량_전체=("m3", "sum"), 면적_전체=("area_m2", "sum"),
                                           세대수=("u_n", "sum"), 판매량=("m3_n", "sum"), 면적=("a_n", "sum")).reset_index()
    if "y" not in keys:  # 여러 해가 섞여 있으면 연평균으로 (비율 지표는 그대로, 세대수·합계만 ÷ 연수)
        ny = max(frame["y"].nunique(), 1)
        for c in ["세대수_전체", "판매량_전체", "면적_전체", "세대수", "판매량", "면적"]:
            r[c] = r[c] / ny
    r["㎡당"] = r["판매량"] / r["면적"]
    r["㎡당(이상치포함)"] = r["판매량_전체"] / r["면적_전체"]
    r["세대당"] = r["판매량"] / r["세대수"]
    r["평균면적"] = r["면적"] / r["세대수"]
    r["이상치비중"] = 1 - r["세대수"] / r["세대수_전체"]
    return r


METRICS = {"㎡당 판매량 (㎥/㎡)": "㎡당", "㎡당 (이상치 포함)": "㎡당(이상치포함)", "세대당 판매량 (㎥)": "세대당",
           "평균 전용면적 (㎡)": "평균면적", "세대수": "세대수", "이상치 비중": "이상치비중"}
FMT = {"㎡당": ".2f", "㎡당(이상치포함)": ".2f", "세대당": ",.0f", "평균면적": ".1f", "세대수": ",.0f", "이상치비중": ".1%"}

st.title("아파트 면적·준공연대별 개별난방 판매량")
st.caption(f"{PL} 판매량 · {'아파트' if apt_only else '공동주택 전체'} · 개별난방용(취사난방용 포함) · 연 10개월 이상 판매 세대 · "
           f"이상치: ㎡당 {thr:.1f}㎥ 미만 · 데이터: {DATA.name} (빅쿼리 재조회 없음)")

tabs = st.tabs(["개요", "계산 따라가기", "면적 × 준공 히트맵", "시군구별", "연도별 추이", "단지별 산점도", "탐색적 분석(EDA)", "데이터"])

# ───────────────────────── 1. 개요 ─────────────────────────
with tabs[0]:
    tot = agg(dy.assign(_k=1), ["_k"]).iloc[0]
    c = st.columns(4)
    c[0].metric("분석 세대수 (이상치 제외)", f"{int(tot['세대수']):,}", f"전체 {int(tot['세대수_전체']):,}", delta_color="off")
    c[1].metric("세대당 연간 판매량", f"{tot['세대당']:,.0f} ㎥")
    c[2].metric("㎡당 연간 판매량", f"{tot['㎡당']:.2f} ㎥/㎡", f"이상치 포함 {tot['㎡당(이상치포함)']:.2f}", delta_color="off")
    c[3].metric("이상치 비중", f"{tot['이상치비중']:.1%}")

    st.markdown("**세대당 판매량 = 평균 전용면적 × ㎡당 판매량** — 세대당만 보면 '집 크기'와 '연식' 효과가 섞입니다.")
    a = agg(dy, ["준공구간"])
    cols = st.columns(3)
    for col, (m, ttl) in zip(cols, [("세대당", "① 세대당 판매량 (㎥)"), ("평균면적", "② 평균 전용면적 (㎡)"), ("㎡당", "③ ㎡당 판매량 (㎥/㎡) = ① ÷ ②")]):
        fig = go.Figure()
        fig.add_bar(x=a["준공구간"].astype(str), y=a[m], name="이상치 제외", text=a[m].map(lambda v: format(v, FMT[m])),
                    marker_opacity=np.where(a["세대수"] < min_n, 0.35, 1))
        if m == "㎡당" and show_all:
            fig.add_scatter(x=a["준공구간"].astype(str), y=a["㎡당(이상치포함)"], name="이상치 포함", mode="lines+markers",
                            line=dict(dash="dash", color="gray"))
        fig.update_layout(title=ttl, height=330, margin=dict(t=40, b=10), showlegend=(m == "㎡당" and show_all),
                          legend=dict(orientation="h", y=-0.2))
        col.plotly_chart(fig, **W)
    st.caption(f"흐린 막대 = 세대수 {min_n:,} 미만")

# ───────────────────────── 2. 계산 따라가기 ─────────────────────────
with tabs[1]:
    st.markdown("히트맵의 **칸 하나**가 어떻게 계산되는지 실제 숫자로 단계별로 따라갑니다.")
    c1, c2 = st.columns(2)
    sel_a = c1.selectbox("면적구간", AL, index=min(2, len(AL) - 1), key="tc_a")
    yl_avail = [y for y in YL if (dy["준공구간"] == y).any()]
    sel_d = c2.selectbox("준공구간", yl_avail, index=len(yl_avail) // 2, key="tc_d")
    cell = dy[(dy["면적구간"] == sel_a) & (dy["준공구간"] == sel_d)]
    if cell.empty:
        st.warning("해당 칸에 세대가 없습니다.")
    else:
        nrm, out = cell[cell["정상"]], cell[~cell["정상"]]
        N, Nn, No = len(cell), len(nrm), len(out)
        M, A = float(nrm["m3"].sum()), float(nrm["area_m2"].sum())
        Ma, Aa = float(cell["m3"].sum()), float(cell["area_m2"].sum())

        st.markdown("#### ① 대상 세대 고르기")
        st.markdown(f"{PL} · **{sel_a}** 이고 준공이 **{sel_d}** 인 세대 → **{N:,}건**"
                    + ("" if NY == 1 else f" (세대×연도 기록 {NY}년치, 연평균 {N / NY:,.0f}세대)") + "  \n"
                    f"(조건: {'아파트만, ' if apt_only else ''}개별난방용+취사난방용, 그해 판매기록 10개월 이상, 사이드바 시군구 필터 적용)")

        st.markdown("#### ② 세대마다 연간 판매량과 ㎡당 판매량 계산")
        st.markdown("세대별 **연간 판매량** = 1~12월 판매량 합계, **㎡당** = 연간 판매량 ÷ 그 세대 전용면적")
        if st.button("다른 세대 보기", key="tc_btn"):
            st.session_state["tc_seed"] = st.session_state.get("tc_seed", 0) + 1
        smp = cell.sample(min(10, N), random_state=st.session_state.get("tc_seed", 0)).copy()
        smp["이상치?"] = np.where(smp["정상"], "", f"예 (< {thr:.1f})")
        show = smp[["apartment_name", "sigungu", "built_year", "area_m2", "m3", "per_m2", "이상치?"]].rename(columns={
            "apartment_name": "단지", "sigungu": "시군구", "built_year": "준공연도", "area_m2": "전용면적(㎡)",
            "m3": "연간 판매량(㎥)", "per_m2": "㎡당(㎥/㎡)"})
        st.dataframe(show.style.format({"전용면적(㎡)": "{:.2f}", "연간 판매량(㎥)": "{:,.0f}", "㎡당(㎥/㎡)": "{:.2f}", "준공연도": "{:.0f}"}),
                     hide_index=True, **W)
        st.caption("무작위 10세대 예시 (동·호는 저장하지 않아 표시되지 않음)")

        st.markdown("#### ③ 이상치 빼기")
        st.markdown(f"㎡당 **{thr:.1f}㎥ 미만** = 빈집·거의 미사용으로 보고 제외 → "
                    f"**{No:,}세대 제외** ({No / N:.1%}), **{Nn:,}세대**로 계산")
        fig = px.histogram(cell[cell["per_m2"] <= cell["per_m2"].quantile(0.995)], x="per_m2", nbins=60,
                           title="이 칸 세대들의 ㎡당 판매량 분포 — 빨간 선 왼쪽이 이상치")
        fig.add_vline(x=thr, line_dash="dash", line_color="red")
        fig.update_layout(height=280, bargap=0.02, margin=dict(t=40, b=10), xaxis_title="㎡당 연간 판매량")
        st.plotly_chart(fig, **W)

        st.markdown("#### ④ 합계를 내서 나누기")
        c = st.columns(3)
        c[0].metric("판매량 합계", f"{M:,.0f} ㎥")
        c[1].metric("전용면적 합계", f"{A:,.0f} ㎡")
        c[2].metric("세대수", f"{Nn:,}")
        st.markdown(
            f"- **㎡당 판매량** = 판매량 합계 ÷ 면적 합계 = {M:,.0f} ÷ {A:,.0f} = **{M / A:.2f} ㎥/㎡**  ← 히트맵 칸 값\n"
            f"- **세대당 판매량** = 판매량 합계 ÷ 세대수 = {M:,.0f} ÷ {Nn:,} = **{M / Nn:,.0f} ㎥**\n"
            f"- **평균 전용면적** = 면적 합계 ÷ 세대수 = {A:,.0f} ÷ {Nn:,} = **{A / Nn:.1f} ㎡**\n"
            f"- 확인: 세대당 = 평균면적 × ㎡당 = {A / Nn:.1f} × {M / A:.2f} = **{(A / Nn) * (M / A):,.0f} ㎥** ✔")

        st.markdown("#### ⑤ 비교해 보기")
        simple = float(nrm["per_m2"].mean())
        st.markdown(
            f"- 이상치를 **포함**하면: {Ma:,.0f} ÷ {Aa:,.0f} = **{Ma / Aa:.2f} ㎥/㎡** "
            f"(제외했을 때보다 {Ma / Aa - M / A:+.2f}) — 빈집이 섞여 평균이 내려감\n"
            f"- 세대별 ㎡당을 그냥 평균내면: **{simple:.2f} ㎥/㎡** — 이 방식은 작은 집과 큰 집을 같은 무게로 쳐서 "
            f"작은 집 비중만큼 값이 달라짐. 그래서 **합계 ÷ 합계**(면적이 큰 집이 더 큰 무게)로 계산")
        tot = agg(dy.assign(_k=1), ["_k"]).iloc[0]
        st.markdown(f"- 같은 기간({PL}) 전체 평균 ㎡당은 **{tot['㎡당']:.2f}** → 이 칸은 전체보다 "
                    f"**{M / A / tot['㎡당'] - 1:+.0%}**")

# ───────────────────────── 2. 히트맵 ─────────────────────────
def heat(frame, row, colkey, metric, title, by_row=False):
    a = agg(frame, [row, colkey])
    z = a.pivot(index=row, columns=colkey, values=metric)
    n = a.pivot(index=row, columns=colkey, values="세대수")
    xs, ys = [str(c) for c in z.columns], [str(i) for i in z.index]
    ok = z.where(n >= min_n)
    diverging = metric != "세대수"
    if by_row and diverging:  # 행(면적구간·시군구)마다 자기 평균 대비 % → 가로 비교가 잘 보임
        rowmean = agg(frame, [row]).set_index(row)[metric]
        ok = ok.div(rowmean.reindex(z.index).values, axis=0) - 1
        span = float(np.nanmax(np.abs(ok.values))) if np.isfinite(ok.values).any() else 0.1
        zmin, zmax, cs = -span, span, "RdBu_r"
    elif diverging:  # 전체 평균 기준: 빨강 = 평균보다 높음, 파랑 = 낮음
        mid = float(agg(frame.assign(_k=1), ["_k"]).iloc[0][metric])
        span = float(np.nanmax(np.abs(ok.values - mid))) if np.isfinite(ok.values).any() else 1.0
        zmin, zmax, cs = mid - span, mid + span, "RdBu_r"
    else:
        zmin, zmax, cs = float(np.nanmin(ok.values)), float(np.nanmax(ok.values)), "Viridis"
    fig = go.Figure(go.Heatmap(z=ok.values, x=xs, y=ys, colorscale=cs, zmin=zmin, zmax=zmax, hoverongaps=False,
                               customdata=n.values, xgap=2, ygap=2,
                               hovertemplate="%{y} · %{x}<br>값 %{z:" + FMT[metric] + "}<br>세대수 %{customdata:,}<extra></extra>",
                               colorbar=dict(title=("행 평균 대비" if by_row else "평균 대비") if diverging else metric,
                                             tickformat="+.0%" if (by_row and diverging) else None)))
    low = z.where(n < min_n)
    fig.add_trace(go.Heatmap(z=np.where(low.notna(), 1, np.nan), x=xs, y=ys, colorscale=[[0, "#d9d9d9"], [1, "#d9d9d9"]],
                             showscale=False, hoverinfo="skip", xgap=2, ygap=2))
    for i, yv in enumerate(z.index):
        for j, xv in enumerate(z.columns):
            v, k = z.iloc[i, j], n.iloc[i, j]
            if pd.isna(v): continue
            if k < min_n:
                color = "#666666"
            else:
                cv = ok.iloc[i, j]
                t = (cv - zmin) / (zmax - zmin) if zmax > zmin else 0.5
                strong = abs(t - 0.5) > 0.28 if diverging else t < 0.45
                color = "white" if strong else "#111111"
            fig.add_annotation(x=xs[j], y=ys[i], showarrow=False, font=dict(color=color, size=14),
                               text=f"<b>{format(v, FMT[metric])}</b><br><span style='font-size:11px'>{int(k):,}세대</span>")
    fig.update_layout(title=title, height=120 + 52 * len(ys), margin=dict(t=40), yaxis=dict(autorange="reversed"),
                      plot_bgcolor="rgba(0,0,0,0)")
    return fig, a


with tabs[2]:
    c1, c2 = st.columns([2, 1])
    mlabel = c1.selectbox("지표", list(METRICS), key="hm_m")
    cmode = c2.radio("색 기준", ["면적구간(행)별 평균 대비", "전체 평균 대비"], key="hm_c")
    fig, a = heat(dy, "면적구간", "준공구간", METRICS[mlabel], f"{PL} 면적구간 × 준공구간 — {mlabel}", by_row=cmode.startswith("면적"))
    st.plotly_chart(fig, **W)
    st.caption(f"빨강 = 기준 평균보다 높음, 파랑 = 낮음, 흰색 = 평균 수준 · 칸 숫자는 실제 값 · 회색 칸 = 세대수 {min_n:,} 미만(참고용)")
    st.info("읽는 법: **가로(같은 면적구간 안에서 준공구간 비교)**로 읽으세요. ㎡당 값은 작은 집일수록 높게 나오는 게 정상입니다 — "
            "온수·취사처럼 집 크기와 무관한 고정 사용량이 있고, 소형일수록 외벽·창 비율이 커서입니다. 세대당으로는 큰 집이 더 많이 씁니다.")

# ───────────────────────── 3. 시군구 ─────────────────────────
with tabs[3]:
    mlabel = st.selectbox("지표", list(METRICS), key="sg_m")
    band_opt = ["전체"] + AL
    band = st.selectbox("면적구간 한정", band_opt)
    f = dy if band == "전체" else dy[dy["면적구간"] == band]
    cmode = st.radio("색 기준", ["시군구(행)별 평균 대비", "전체 평균 대비"], key="sg_c", horizontal=True)
    fig, a = heat(f, "sigungu", "준공구간", METRICS[mlabel], f"{PL} 시군구 × 준공구간 — {mlabel} ({band})", by_row=cmode.startswith("시군구"))
    st.plotly_chart(fig, **W)
    a2 = a[a["세대수"] >= min_n]
    fig = px.line(a2, x="준공구간", y=METRICS[mlabel], color="sigungu", markers=True, title="시군구별 비교 (표본 기준 이상만)")
    fig.update_layout(height=420)
    st.plotly_chart(fig, **W)

# ───────────────────────── 4. 연도별 추이 ─────────────────────────
with tabs[4]:
    mlabel = st.selectbox("지표", list(METRICS), key="tr_m")
    band = st.selectbox("면적구간 한정", ["전체"] + AL, key="tr_b")
    f = d if band == "전체" else d[d["면적구간"] == band]
    a = agg(f, ["y", "준공구간"])
    a = a[a["세대수"] >= min_n]
    fig = px.line(a, x="y", y=METRICS[mlabel], color="준공구간", markers=True, title=f"연도별 {mlabel} ({band})")
    fig.update_xaxes(dtick=1, title="판매연도"); fig.update_layout(height=450)
    st.plotly_chart(fig, **W)
    st.caption("모든 구간이 같은 방향으로 움직이면 기온·요금 같은 공통 요인 영향입니다. 기온 보정 전 실적치.")

# ───────────────────────── 5. 단지별 산점도 ─────────────────────────
with tabs[5]:
    c1, c2, c3 = st.columns(3)
    min_u = c1.number_input("단지 최소 세대수", 1, 3000, 50, 10)
    color_by = c2.selectbox("색 구분", ["sigungu", "built_source", "없음"])
    band = c3.selectbox("면적구간 한정", ["전체"] + AL, key="sc_b")
    f = dy if band == "전체" else dy[dy["면적구간"] == band]
    g = f[f["정상"]].groupby(["apartment_code", "apartment_name", "sigungu", "built_year", "built_source"], observed=True).agg(
        세대수=("m3", "size"), 판매량=("m3", "sum"), 면적=("area_m2", "sum")).reset_index()
    g[["세대수", "판매량", "면적"]] = g[["세대수", "판매량", "면적"]] / NY  # 연평균
    g = g[g["세대수"] >= min_u]
    g["㎡당"] = g["판매량"] / g["면적"]; g["세대당"] = g["판매량"] / g["세대수"]; g["평균면적"] = g["면적"] / g["세대수"]
    g["built_year"] = g["built_year"].astype(float)
    if len(g) > 2:
        k = np.polyfit(g["built_year"], g["㎡당"], 2, w=np.sqrt(g["세대수"]))
        xs = np.linspace(g["built_year"].min(), g["built_year"].max(), 100)
        g["추세값"] = np.polyval(k, g["built_year"]); g["추세대비"] = g["㎡당"] / g["추세값"] - 1
    fig = px.scatter(g, x="built_year", y="㎡당", size="세대수", color=None if color_by == "없음" else color_by,
                     hover_data={"apartment_name": True, "세대수": ":,", "세대당": ":,.0f", "평균면적": ":.1f", "㎡당": ":.2f",
                                 "built_source": True}, size_max=25, opacity=0.6,
                     title=f"{PL} 단지별 ㎡당 판매량 vs 준공연도 ({len(g):,}개 단지, 이상치 세대 제외)")
    if len(g) > 2:
        fig.add_scatter(x=xs, y=np.polyval(k, xs), mode="lines", name="추세(세대수 가중 2차)", line=dict(color="black", width=2))
    fig.update_layout(height=520, xaxis_title="준공연도")
    st.plotly_chart(fig, **W)
    if "추세대비" in g:
        st.markdown("**추세선 대비 많이/적게 쓰는 단지** — 영업·현장 확인 대상 후보")
        cols = ["apartment_name", "sigungu", "built_year", "세대수", "평균면적", "세대당", "㎡당", "추세대비"]
        fmt = {"세대수": "{:,.0f}", "평균면적": "{:.1f}", "세대당": "{:,.0f}", "㎡당": "{:.2f}", "추세대비": "{:+.0%}", "built_year": "{:.0f}"}
        l, r = st.columns(2)
        l.dataframe(g.nlargest(15, "추세대비")[cols].style.format(fmt), hide_index=True, **W)
        r.dataframe(g.nsmallest(15, "추세대비")[cols].style.format(fmt), hide_index=True, **W)

# ───────────────────────── 6. EDA ─────────────────────────
with tabs[6]:
    st.subheader("1. 데이터 개요")
    c = st.columns(4)
    c[0].metric("세대×연도 행", f"{len(d):,}")
    c[1].metric(f"{PL} 세대수" + ("" if NY == 1 else " (연평균)"), f"{len(dy) / NY:,.0f}")
    c[2].metric(f"{PL} 단지수", f"{dy['apartment_code'].nunique():,}")
    c[3].metric("연도 범위", f"{min(YEARS)}~{max(YEARS)}")
    src = dy["built_source"].astype(str).value_counts(normalize=True).rename("세대 비중").to_frame()
    l, r = st.columns(2)
    l.markdown("준공연도 출처"); l.dataframe(src.style.format("{:.1%}"), **W)
    yc = d.groupby("y").size().rename("세대수").to_frame()
    r.markdown("연도별 세대수 (신규 입주로 증가)"); r.dataframe(yc.style.format("{:,}"), **W)

    st.subheader("2. 분포")
    l, r = st.columns(2)
    q = dy["m3"].quantile(0.995)
    fig = px.histogram(dy[dy["m3"] <= q], x="m3", nbins=80, title="세대별 연간 판매량 (㎥, 상위 0.5% 잘라냄)")
    fig.update_layout(height=330, bargap=0.02); l.plotly_chart(fig, **W)
    q = dy["per_m2"].quantile(0.995)
    fig = px.histogram(dy[dy["per_m2"] <= q], x="per_m2", nbins=80, title="세대별 ㎡당 연간 판매량 (㎥/㎡)")
    fig.add_vline(x=thr, line_dash="dash", line_color="red", annotation_text=f"이상치 기준 {thr:.1f}")
    fig.update_layout(height=330, bargap=0.02); r.plotly_chart(fig, **W)
    l, r = st.columns(2)
    fig = px.histogram(dy[dy["area_m2"] <= 200], x="area_m2", nbins=100, title="전용면적 분포 (㎡) — 59·84형에 몰림")
    for e in AE[1:-1]: fig.add_vline(x=e, line_dash="dot", line_color="gray")
    fig.update_layout(height=330, bargap=0.02); l.plotly_chart(fig, **W)
    fig = px.histogram(dy, x=dy["built_year"].astype(float), nbins=60, color=dy["built_source"].astype(str),
                       title="준공연도 분포 (세대 기준)")
    fig.update_layout(height=330, bargap=0.02, legend=dict(orientation="h", y=-0.25), xaxis_title="준공연도")
    r.plotly_chart(fig, **W)

    st.subheader("3. 준공구간별 ㎡당 판매량 분포 (박스플롯)")
    smp = dy.sample(min(len(dy), 80_000), random_state=0)
    smp = smp[smp["per_m2"] <= smp["per_m2"].quantile(0.995)]
    fig = px.box(smp, x="준공구간", y="per_m2", points=False, category_orders={"준공구간": YL},
                 title="상자 = 중간 50% 세대, 가운데 선 = 중앙값 (표본 8만 세대)")
    fig.add_hline(y=thr, line_dash="dash", line_color="red", annotation_text="이상치 기준")
    fig.update_layout(height=420, yaxis_title="㎡당 연간 판매량"); st.plotly_chart(fig, **W)

    st.subheader("4. 면적과 판매량의 관계")
    fig = px.density_heatmap(smp[smp["area_m2"] <= 200], x="area_m2", y="m3", nbinsx=60, nbinsy=60,
                             title="전용면적 vs 연간 판매량 (밀도) — 면적이 커져도 판매량은 비례해서 늘지 않음")
    fig.update_layout(height=420); st.plotly_chart(fig, **W)

    st.subheader("5. 이상치 비중")
    a = agg(dy, ["면적구간", "준공구간"])
    fig = px.density_heatmap(a, x="준공구간", y="면적구간", z="이상치비중", histfunc="sum", text_auto=".1%",
                             color_continuous_scale="Reds", category_orders={"준공구간": YL, "면적구간": AL})
    fig.update_layout(height=360, title="면적구간 × 준공구간 이상치 비중"); st.plotly_chart(fig, **W)

    st.subheader("6. 기술통계 (준공구간별, 이상치 제외)")
    desc = dy[dy["정상"]].groupby("준공구간", observed=True)["per_m2"].describe(percentiles=[.1, .25, .5, .75, .9])
    st.dataframe(desc.style.format("{:,.2f}").format({"count": "{:,.0f}"}), **W)

# ───────────────────────── 7. 데이터 ─────────────────────────
with tabs[7]:
    keys = st.multiselect("집계 기준", ["y", "sigungu", "면적구간", "준공구간"], default=["y", "면적구간", "준공구간"])
    if keys:
        a = agg(d, keys)
        st.dataframe(a, **W, hide_index=True)
        st.download_button("CSV 다운로드", a.to_csv(index=False).encode("utf-8-sig"), "집계결과.csv", "text/csv")
