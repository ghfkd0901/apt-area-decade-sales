"""③ 보고서(엑셀) 생성 — 아파트 면적대 × 준공연대별 개별난방 판매량
  1) sql/03_agg_area_decade.sql 을 빅쿼리에서 실행 → data/agg_area_decade.csv  (--skip-query 면 기존 csv 사용)
  2) 원자료 시트 + SUMIFS 수식 기반 분석 시트로 엑셀 작성 → output/
사용: python 03_build_report.py [--skip-query] [YYYYMMDD]
※ 1_요약 시트의 '주요 결과' 문구는 2026-11-20 분석(2021~2025) 기준. 다른 연도로 다시 돌리면 표 숫자는 자동 반영되지만 문구는 직접 고칠 것.
"""
import sys, datetime
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter as L
from openpyxl.comments import Comment
from common import DATA, OUTPUT, SQL, query_df

args = [a for a in sys.argv[1:] if not a.startswith('--')]
TAG = args[0] if args else f"{datetime.date.today():%Y%m%d}"
CSV = DATA / 'agg_area_decade.csv'
SQLTXT = (SQL / '03_agg_area_decade.sql').read_text(encoding='utf-8')
if '--skip-query' not in sys.argv:
    query_df(SQLTXT).to_csv(CSV, index=False, encoding='utf-8'); print('query saved', CSV)
r = pd.read_csv(CSV, dtype={'sigungu': str})
YRS = sorted(r.y.unique().tolist())[-5:]; LASTY = YRS[-1]

F = 'Arial'
def f(b=False, sz=10, c='000000', i=False): return Font(name=F, bold=b, size=sz, color=c, italic=i)
HDR = PatternFill('solid', fgColor='1F3864'); SUB = PatternFill('solid', fgColor='D9E1F2'); INP = PatternFill('solid', fgColor='FFFF00')
thin = Side(style='thin', color='BFBFBF'); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
WR = Alignment(wrap_text=True, vertical='top'); CEN = Alignment(horizontal='center', vertical='center', wrap_text=True)
DEC = ['1970년대', '1980년대', '1990년대', '2000년대', '2010년대', '2020년대']
BAND = ['40㎡ 이하', '40~60㎡', '60~85㎡', '85~102㎡', '102~135㎡', '135㎡ 초과']
SGG = ['중구', '동구', '서구', '남구', '북구', '수성구', '달서구', '달성군', '경산시', '고령군']
RAW = '원자료'
def rs(c): return f"{RAW}!${c}:${c}"
# 원자료 열: A연도 B시군구 C면적대 D면적대순서 E준공연대 F세대수 G판매량 H면적 I세대수(n) J판매량(n) K면적(n) L K-apt세대수
Y, S, BO, D = rs('A'), rs('B'), rs('D'), rs('E')
UA, MA, AA = rs('F'), rs('G'), rs('H')        # 전체(이상치 포함)
U, M, A = rs('I'), rs('J'), rs('K')           # 이상치 제외 (기본 지표)

wb = Workbook()
def sheet(name, widths):
    ws = wb.create_sheet(name)
    for i, w in enumerate(widths, 1): ws.column_dimensions[L(i)].width = w
    ws.sheet_view.showGridLines = False
    return ws
def title(ws, t, sub=None):
    ws['A1'] = t; ws['A1'].font = f(True, 14, '1F3864')
    if sub: ws['A2'] = sub; ws['A2'].font = f(False, 9, '595959', True)
def hdr(ws, row, col, vals):
    for j, v in enumerate(vals):
        c = ws.cell(row, col + j, v); c.font = f(True, 10, 'FFFFFF'); c.fill = HDR; c.alignment = CEN; c.border = BOX
def lab(ws, row, col, v):
    c = ws.cell(row, col, v); c.font = f(True); c.fill = SUB; c.border = BOX
def val(ws, row, col, fm, nf, bold=False):
    c = ws.cell(row, col, fm); c.number_format = nf; c.font = f(bold); c.border = BOX; c.alignment = Alignment(horizontal='right')
def note(ws, cell, t): ws[cell] = t; ws[cell].font = f(False, 9, '595959', True)
def yearcell(ws):
    ws['A3'] = '기준연도 ▶'; ws['A3'].font = f(True)
    ws['B3'] = LASTY; ws['B3'].fill = INP; ws['B3'].font = f(True, 11, '0000FF'); ws['B3'].alignment = CEN; ws['B3'].number_format = '0'
    ws['B3'].comment = Comment(f'{YRS[0]}~{YRS[-1]} 중 입력하면 이 시트 표가 모두 바뀝니다.', 'Claude')
    note(ws, 'C3', f'← 노란 칸에 {YRS[0]}~{YRS[-1]} 입력')
def grey_rule(ws, rng, first):
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'AND(ISNUMBER({first}),{first}<300)'], font=Font(name=F, color='A6A6A6', italic=True)))

def expr(kind, crit):
    sumif = lambda col: f"SUMIFS({col},{crit})"
    return {
        'avg':  (f'=IFERROR({sumif(M)}/{sumif(U)},"-")', '#,##0'),
        'per':  (f'=IFERROR({sumif(M)}/{sumif(A)},"-")', '0.00'),
        'perA': (f'=IFERROR({sumif(MA)}/{sumif(AA)},"-")', '0.00'),
        'units': (f'={sumif(U)}', '#,##0;-#,##0;"-"'),
        'out':  (f'=IFERROR(1-{sumif(U)}/{sumif(UA)},"-")', '0.0%'),
        'area': (f'=IFERROR({sumif(A)}/{sumif(U)},"-")', '0.0'),
    }[kind]

def matrix(ws, top, col0, rows, rowtype, ttl, kind, yref='$B$3', band_fixed=None):
    """rows × 준공연대(+전체) 표. rowtype: 'band'|'sgg'"""
    ws.cell(top, col0, ttl).font = f(True, 11, '1F3864')
    hdr(ws, top + 1, col0, ['구분'] + DEC + ['전체'])
    for i, rv in enumerate(rows):
        rw = top + 2 + i; lab(ws, rw, col0, rv)
        for j, dv in enumerate(DEC + ['전체']):
            col = col0 + 1 + j
            crit = f"{Y},{yref}," + (f"{BO},{i+1}" if rowtype == 'band' else f"{S},${L(col0)}{rw}")
            if band_fixed: crit += f",{BO},{BAND.index(band_fixed)+1}"
            if dv != '전체': crit += f",{D},{L(col)}${top+1}"
            fm, nf = expr(kind, crit); val(ws, rw, col, fm, nf)
    return top + 2, top + 1 + len(rows)

# ---------- 원자료 ----------
raw = sheet(RAW, [8, 10, 12, 10, 11, 11, 15, 15, 14, 15, 15, 13])
hdr(raw, 1, 1, ['연도', '시군구', '면적대', '면적대순서', '준공연대', '세대수(전체)', '판매량합계(㎥,전체)', '전용면적합계(㎡,전체)',
                '세대수(이상치제외)', '판매량합계(㎥,이상치제외)', '전용면적합계(㎡,이상치제외)', 'K-apt승인일 세대수'])
rr = r.sort_values(['y', 'sigungu', 'area_band_order', 'decade'])
for i, x in enumerate(rr.itertuples(), 2):
    for j, v in enumerate([x.y, x.sigungu, x.area_band, x.area_band_order, x.decade, x.units, x.m3_sum, x.area_sum,
                           x.units_n, x.m3_n, x.area_n, x.units_kapt], 1):
        c = raw.cell(i, j, v); c.font = f()
        if j >= 6: c.number_format = '#,##0'
raw.freeze_panes = 'A2'; raw.auto_filter.ref = f"A1:L{len(rr)+1}"

SUBT = '아파트 · 개별난방용(취사난방용 포함) · 연 10개월 이상 판매 세대 · ㎡당 2.5㎥ 미만 이상치 제외'

# ---------- 3 세대당 ----------
ws3 = sheet('3_세대당', [14] + [11] * 7 + [3] + [14] + [11] * 7)
title(ws3, '면적대 × 준공연대별 세대당 연간 판매량 (㎥/세대)', SUBT + ' · 판매량합계 ÷ 세대수')
yearcell(ws3)
matrix(ws3, 5, 1, BAND, 'band', '① 세대당 연간 판매량 (㎥)', 'avg')
matrix(ws3, 5, 10, BAND, 'band', '② 세대수 (참고)', 'units')
grey_rule(ws3, 'B7:H12', 'K7')
note(ws3, 'A14', '※ 세대수 300 미만 칸은 회색 글씨 (표본이 작아 참고용)')
note(ws3, 'A15', '※ 같은 면적대 안에서도 오래된 단지일수록 실제 전용면적이 작음 → 준공연대 비교는 4_m2당 시트를 기준으로 볼 것.')
ws3.freeze_panes = 'B7'

# ---------- 4 m2당 ----------
ws4 = sheet('4_m2당', [16] + [11] * 7)
title(ws4, '면적대 × 준공연대별 ㎡당 연간 판매량 (㎥/㎡)', SUBT + ' · 판매량합계 ÷ 전용면적합계')
yearcell(ws4)
matrix(ws4, 5, 1, BAND, 'band', '① ㎡당 연간 판매량 (㎥/㎡) — 기본 지표', 'per')
ws4.cell(14, 1, '② 전체 면적대 합산').font = f(True, 11, '1F3864')
hdr(ws4, 15, 1, ['지표'] + DEC + ['전체'])
for k, (lb, kind, bold) in enumerate([('㎡당 (이상치 제외)', 'per', True), ('㎡당 (이상치 포함)', 'perA', False),
                                      ('이상치 비중', 'out', False), ('평균 전용면적(㎡)', 'area', False), ('세대수', 'units', False)]):
    rw = 16 + k; lab(ws4, rw, 1, lb)
    for j, dv in enumerate(DEC + ['전체']):
        col = 2 + j; crit = "{},$B$3".format(Y) + ("" if dv == '전체' else f",{D},{L(col)}$15")
        fm, nf = expr(kind, crit); val(ws4, rw, col, fm, nf, bold)
note(ws4, 'A22', '※ 이상치 = ㎡당 연 판매량 2.5㎥ 미만 세대(60~85㎡ 기준 약 200㎥, 40㎡ 기준 약 100㎥ 미만). 빈집·거의 미사용 세대로 보고 제외.')
ws4.freeze_panes = 'B7'

# ---------- 5 시군구별 ----------
ws5 = sheet('5_시군구별', [12] + [11] * 7 + [3] + [12] + [11] * 7)
title(ws5, '시군구 × 준공연대별 ㎡당 연간 판매량 (㎥/㎡)', SUBT + ' · 전체 면적대 합산')
yearcell(ws5)
matrix(ws5, 5, 1, SGG, 'sgg', '① ㎡당 연간 판매량 (㎥/㎡)', 'per')
matrix(ws5, 5, 10, SGG, 'sgg', '② 세대수 (참고)', 'units')
grey_rule(ws5, 'B7:H16', 'K7')
matrix(ws5, 19, 1, SGG, 'sgg', '③ 60~85㎡ 세대당 연간 판매량 (㎥/세대)', 'avg', band_fixed='60~85㎡')
note(ws5, 'A32', '※ 세대수 300 미만 칸은 회색 글씨. 외곽·대규모 주거지(달성·경산·달서·동구·북구)는 오래될수록 ㎡당 사용량이 뚜렷하게 높고, 원도심(남구·중구·서구)은 완만하거나 일부 역전.')
ws5.freeze_panes = 'B7'

# ---------- 6 연도별추이 ----------
ws6 = sheet('6_연도별추이', [16] + [11] * 6)
title(ws6, '연도별 추이', f'{YRS[0]}~{YRS[-1]} 판매연도 기준 · ' + SUBT)
def trend(top, ttl, kind, band=None):
    ws6.cell(top, 1, ttl).font = f(True, 11, '1F3864')
    hdr(ws6, top + 1, 1, ['준공연대'] + [str(y) for y in YRS] + [f'{str(YRS[0])[2:]}→{str(YRS[-1])[2:]} 증감률'])
    for i, dv in enumerate(DEC + ['전체']):
        rw = top + 2 + i; lab(ws6, rw, 1, dv)
        for j, yv in enumerate(YRS):
            crit = f"{Y},{yv}" + ("" if dv == '전체' else f",{D},$A{rw}") + (f",{BO},{BAND.index(band)+1}" if band else '')
            fm, nf = expr(kind, crit); val(ws6, rw, 2 + j, fm, nf)
        val(ws6, rw, 2 + len(YRS), f'=IFERROR({L(1+len(YRS))}{rw}/B{rw}-1,"-")', '0.0%')
    return top + 2 + len(DEC) + 1
n = trend(4, '① ㎡당 연간 판매량 (㎥/㎡, 이상치 제외, 전체 면적대)', 'per')
n = trend(n + 1, '② ㎡당 연간 판매량 (㎥/㎡, 이상치 포함 — 판매량 예측·사업계획용)', 'perA')
n = trend(n + 1, '③ 60~85㎡ 세대당 연간 판매량 (㎥/세대, 이상치 제외)', 'avg', '60~85㎡')
note(ws6, f'A{n+1}', '※ 모든 준공연대가 같은 방향으로 움직임 → 연도 간 증감은 기온·요금 등 공통 요인 영향. 기온 보정 전 실적치. 2020년대 단지는 초기 연도 표본이 작음(입주 진행).')

# ---------- 7 이상치비중 ----------
ws7 = sheet('7_이상치비중', [12] + [11] * 7)
title(ws7, '이상치(㎡당 2.5㎥ 미만) 세대 비중', '1 − 이상치제외 세대수 ÷ 전체 세대수 — 빈집·거의 미사용 세대의 비중')
yearcell(ws7)
matrix(ws7, 5, 1, SGG, 'sgg', '① 시군구 × 준공연대', 'out')
matrix(ws7, 19, 1, BAND, 'band', '② 면적대 × 준공연대', 'out')
note(ws7, 'A28', '※ 오래된 단지·원도심일수록 이상치 비중이 높음 → 포함하면 오래된 단지의 사용량이 낮게 보이는 착시가 생김. 거주인원 자료가 없어 원인(빈집·고령 1인가구 등)은 추정.')

# ---------- 1 요약 ----------
ws1 = wb.active; ws1.title = '1_요약'
for i, w in enumerate([24, 11, 11, 11, 11, 11, 11, 11], 1): ws1.column_dimensions[L(i)].width = w
ws1.sheet_view.showGridLines = False
title(ws1, '아파트 면적대 × 준공연대별 개별난방 판매량 분석',
      f'대성에너지 마케팅팀 · 작성 {TAG[:4]}-{TAG[4:6]}-{TAG[6:]} · 분석기간 {YRS[0]}~{YRS[-1]} 판매연도 · 대상 대구·경북 아파트 개별난방 세대')
ws1['A4'] = f'핵심 지표 ({LASTY}년, 전체 면적대)'; ws1['A4'].font = f(True, 11, '1F3864')
hdr(ws1, 5, 1, ['지표'] + DEC + ['전체'])
for k, (lb, kind, bold) in enumerate([('세대수 (이상치 제외)', 'units', False), ('세대당 판매량(㎥)', 'avg', False),
                                      ('평균 전용면적(㎡)', 'area', False), ('㎡당 판매량(㎥/㎡) ★', 'per', True),
                                      ('㎡당 판매량 (이상치 포함)', 'perA', False), ('이상치 비중', 'out', False)]):
    rw = 6 + k; lab(ws1, rw, 1, lb)
    for j, dv in enumerate(DEC + ['전체']):
        col = 2 + j; crit = f"{Y},{LASTY}" + ("" if dv == '전체' else f",{D},{L(col)}$5")
        fm, nf = expr(kind, crit); val(ws1, rw, col, fm, nf, bold)
note(ws1, 'A12', '★ 기본 지표: 이상치(㎡당 2.5㎥ 미만) 제외 ㎡당 판매량 — 면적 차이와 빈집 영향을 제거한 준공연대 비교 지표')
findings = [
    ('주요 결과', None),
    ('1. 오래된 아파트일수록 많이 쓴다', '㎡당 판매량(이상치 제외)은 1980년대 9.24 → 1990년대 9.04 → 2000년대 8.67 → 2010년대 8.08 → 2020년대 6.65㎥/㎡로 준공연대가 최신일수록 단계적으로 감소. 2020년대 아파트는 1980년대보다 약 28% 적게 사용.'),
    ('2. 이상치를 빼야 하는 이유', '이상치를 포함하면 1980년대(8.40)와 2000년대(8.19)가 거의 같게 보임. 오래된 단지에 빈집·거의 미사용 세대가 많기 때문(이상치 비중 1980년대 약 10% vs 2000년대 약 6%). 실제 거주 세대의 사용 특성을 비교하려면 이상치 제외가 적합.'),
    ('3. 세대당으로 보면 2000년대가 가장 높음', '세대당 판매량은 2000년대(약 737㎥)가 가장 높고 1980·90년대는 약 630㎥ 수준. 같은 면적대 안에서도 오래된 단지의 실제 전용면적이 작아서임 → 준공연대 비교는 ㎡당 기준으로 봐야 함.'),
    ('4. 지역별 차이', '외곽·대규모 주거지는 단계적 감소가 뚜렷(달성 10.73→6.65, 경산 9.98→7.38, 달서 9.60→6.34). 원도심(남구·중구·서구)은 감소가 완만하거나 일부 역전 — 고령·소인 가구 등 거주 특성 영향으로 추정.'),
    ('5. 면적과 사용량', '면적이 커질수록 세대당 사용량은 늘지만 비례하지 않음. ㎡당으로는 작은 집일수록 높음(40㎡ 이하 약 10~13 vs 135㎡ 초과 약 6~7㎥/㎡).'),
    ('6. 연도별 추이', '모든 준공연대가 같은 방향으로 증감(2021→2024 감소, 2025 소폭 반등) → 기온·요금 등 공통 요인 영향.'),
    ('활용 시 유의사항', None),
    ('지표 선택', '사용 특성 비교·영업 타깃 분석 → 이상치 제외 ㎡당. 판매량 예측·사업계획 → 이상치 포함 값(빈집도 실제 판매량에 반영되므로).'),
    ('표본', '세대수 300 미만 칸(1970년대, 85~102㎡ 일부 등)은 참고용. 2020년대 단지는 2021~2022년 표본이 작음(입주 진행).'),
    ('준공연도', '세대 기준 약 89%는 K-apt 사용승인일, 약 11%는 최초공급연도 추정치. 2_산정방식 참조.'),
    ('세부 시트', '2_산정방식 · 3_세대당 · 4_m2당 · 5_시군구별 · 6_연도별추이 · 7_이상치비중 · 원자료 · SQL. 3·4·5·7 시트는 노란 칸에 연도 입력 시 해당 연도로 바뀜.'),
]
rw = 14
for k, v in findings:
    if v is None: ws1.cell(rw, 1, k).font = f(True, 11, '1F3864'); rw += 1; continue
    c = ws1.cell(rw, 1, k); c.font = f(True); c.alignment = WR
    ws1.merge_cells(start_row=rw, start_column=2, end_row=rw, end_column=8)
    c = ws1.cell(rw, 2, v); c.font = f(); c.alignment = WR
    ws1.row_dimensions[rw].height = max(30, 14 * (len(v) // 34 + 1)); rw += 1

# ---------- 2 산정방식 ----------
ws2 = sheet('2_산정방식', [6, 24, 90])
title(ws2, '산정 방식 및 계산 방법', '보고·설명용')
rows = [
    ('H', '1. 사용 데이터'),
    ('1-1', '판매량', '빅쿼리 dse-marketing.sales.sale — 고객지원시스템 월별 판매(검침) 내역. 시설물 단위 월 사용량(㎥), 상품명, 업종, 지번주소, 공동주택코드, 매출년월.'),
    ('1-2', '세대별 전용면적', '빅쿼리 sales.pbi_ref_apt_unit_area — 전산팀 추출(공동주택정보등록 화면 w_ea5010_m, 2026-11-20 수령). 공동주택코드·동·호별 전용면적 830,596세대(완전 중복 35행만 제거, 그 외 원본 그대로).'),
    ('1-3', '단지별 준공연도', '빅쿼리 sales.pbi_ref_apt_built_year — K-apt(공동주택관리정보시스템) 단지기본정보(2025-12-12)의 사용승인일을 당사 공동주택코드에 매칭. 매칭 안 된 단지는 최초공급연도 추정치(단지 계량기 최초공급일 하위 10% 시점의 연도)로 보완.'),
    ('1-4', '시군구', '빅쿼리 sales.pbi_dim_apartment 의 단지별 시군구.'),
    ('H', '2. 계산 절차'),
    ('2-1', '대상 상품', '개별난방용 + 취사난방용. 두 상품은 사실상 동일하므로 취사난방용을 개별난방용으로 바꿔 하나로 집계. 취사용은 난방 사용량을 정확히 알 수 없어 제외, 중앙난방용 등도 제외.'),
    ('2-2', '대상 주택', '아파트만 — 판매 내역의 업종이 "아파트"인 세대. 연립주택·다세대주택·다가구주택 등은 제외(전체의 약 1%).'),
    ('2-3', '세대 식별', '판매 내역 지번주소 끝의 "○○동 ○○호"를 정규식으로 추출. 공동주택코드 + 동 + 호 = 1세대. 동 구분이 없는 단지는 동을 빈 값으로 처리.'),
    ('2-4', '세대별 연간 판매량', '판매연도(매출년월의 연도)별로 세대의 월 판매량을 합산. 예: 2025년 = 매출년월 2025-01~2025-12 합계.'),
    ('2-5', '온전한 연간 세대만', '그 해 판매 기록이 10개월 이상인 세대만 포함(이사·신규입주·해지로 일부 달만 있는 세대 제외). 연간 판매량 0 이하 제외.'),
    ('2-6', '면적 매칭', '공동주택코드 + 동 + 호로 세대별 전용면적과 결합(판매 세대 대비 매칭률 99.94%). 면적 미등록 세대 제외.'),
    ('2-7', '이상치 제외', '㎡당 연 판매량 2.5㎥ 미만 세대를 이상치(빈집·거의 미사용)로 보고 기본 지표에서 제외. 고정값(예: 연 200㎥)을 쓰면 소형 세대(40㎡ 이하의 약 32%)가 과도하게 잘리므로 면적 비례 기준 사용 — 60~85㎡ 약 200㎥, 40㎡ 약 100㎥에 해당. 제외 비율은 면적대별 6~12%로 고르게 분포.'),
    ('2-8', '면적대 구분', '전용면적 6구간: 40㎡ 이하 / 40~60㎡ / 60~85㎡ / 85~102㎡ / 102~135㎡ / 135㎡ 초과 (상한 포함, 예: 85.00㎡는 60~85㎡).'),
    ('2-9', '준공연대 구분', '준공연도를 10년 단위로 구분 (예: 1995년 → 1990년대).'),
    ('2-10', '집계', '연도 × 시군구 × 면적대 × 준공연대별로 세대수·판매량합계·전용면적합계를 이상치 포함/제외 각각 합산 → 원자료 시트. 나머지 시트는 원자료를 SUMIFS 수식으로 재집계(엑셀에서 검증 가능).'),
    ('H', '3. 지표 정의'),
    ('3-1', '㎡당 연간 판매량 ★', '계산식: 판매량합계 ÷ 전용면적합계 (이상치 제외). 면적 차이를 제거해 준공연대(단열·설비 수준)를 비교하는 기본 지표.'),
    ('3-2', '세대당 연간 판매량', '계산식: 판매량합계 ÷ 세대수 (이상치 제외). 한 세대가 1년간 사용한 평균 가스량.'),
    ('3-3', '㎡당 (이상치 포함)', '계산식: 판매량합계 ÷ 전용면적합계 (전체 세대). 빈집 등도 실제 판매량에 포함되므로 판매량 예측·사업계획용.'),
    ('3-4', '이상치 비중', '계산식: 1 − 이상치 제외 세대수 ÷ 전체 세대수.'),
    ('3-5', '평균 전용면적', '계산식: 전용면적합계 ÷ 세대수.'),
    ('H', '4. 준공연도 매칭 방법 (K-apt → 당사 공동주택코드)'),
    ('4-1', '기존 매칭표', '이전 아파트지도 작업(D:\\Project\\10_아파트지도)에서 만든 K-apt↔당사코드 매칭 995개 단지를 우선 사용.'),
    ('4-2', '추가 매칭', '도로명주소 일치 → 좌표 200m 이내 + 단지명 유사 → 지번주소 일치 → 같은 시군구 내 단지명 일치 순서로 추가 매칭. 합계 약 1,350개 단지.'),
    ('4-3', '오매칭 제거', '최초공급연도가 사용승인일보다 2년 이상 앞서는 매칭(준공 전 공급은 불가능)과 육안 확인한 오매칭 1건 제외(총 6건).'),
    ('4-4', '커버리지', '세대 기준 K-apt 사용승인일 89.1%, 최초공급연도 추정 10.7%, 없음 0.2%. K-apt는 150세대 이상 의무관리 단지 위주라 소규모·오피스텔·2025.12 이후 신축은 추정치 사용.'),
    ('H', '5. 한계 및 유의사항'),
    ('5-1', '최초공급연도 추정치', '가스 최초 공급 시점이라 실제 준공보다 늦을 수 있음(특히 중앙→개별 전환 단지). 1983년이 데이터 하한이라 1983으로 표시된 단지는 그 이전 준공일 수 있음.'),
    ('5-2', '작은 표본', '세대수 300 미만 칸은 회색 글씨 — 참고용.'),
    ('5-3', '거주 특성 미반영', '거주 인원·연령·공실 자료가 없어 이상치 비중으로만 간접 확인. 원도심 패턴의 원인은 추정.'),
    ('5-4', '기온 미보정', '연도별 비교는 기온 보정 전 실적치.'),
    ('5-5', '2020년대 입주 효과', '2020년대 단지는 입주 진행 중이라 초기 연도 표본이 작음.'),
]
rw = 4
for row in rows:
    if row[0] == 'H':
        ws2.cell(rw, 1, row[1]).font = f(True, 11, 'FFFFFF')
        for cc in range(1, 4): ws2.cell(rw, cc).fill = HDR
        rw += 1; continue
    for j, v in enumerate(row, 1):
        c = ws2.cell(rw, j, v); c.font = f(j == 2); c.alignment = WR; c.border = BOX
    ws2.row_dimensions[rw].height = max(18, 14 * (len(row[2]) // 42 + 1)); rw += 1

# ---------- SQL ----------
wsq = sheet('SQL', [130])
title(wsq, '집계 SQL (빅쿼리)', '원자료 시트를 만든 쿼리 — sql/03_agg_area_decade.sql')
for i, line in enumerate(SQLTXT.split('\n'), 4):
    c = wsq.cell(i, 1, line); c.font = Font(name='Consolas', size=9)

wb._sheets = [wb[n] for n in ['1_요약', '2_산정방식', '3_세대당', '4_m2당', '5_시군구별', '6_연도별추이', '7_이상치비중', RAW, 'SQL']]
for w in wb.worksheets:
    w.page_setup.orientation = 'landscape'; w.page_setup.fitToWidth = 1; w.page_setup.fitToHeight = 0
    w.sheet_properties.pageSetUpPr.fitToPage = True
OUTPUT.mkdir(exist_ok=True)
out = OUTPUT / f'아파트_면적대_준공연대별_개별난방_판매량분석_{TAG}.xlsx'; wb.save(out); print('saved', out)
