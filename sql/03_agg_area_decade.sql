-- ③ 연도 × 시군구 × 면적대 × 준공연대 아파트 개별난방 판매량 집계 (보고서 원자료)
-- 규칙
--   · 상품: 취사난방용 → 개별난방용으로 바꿔 하나로 집계 (사실상 동일 상품), 취사용·중앙난방용 등 제외
--   · 아파트만: sale.industry_name = '아파트' (연립·다세대·다가구 등 제외)
--   · 세대: 공동주택코드 + 동 + 호 (지번주소 끝 "○○동 ○○호" 정규식 추출)
--   · 온전한 연간 세대: 그 해 판매기록 10개월 이상 & 연 판매량 > 0
--   · 이상치: ㎡당 연 판매량 2.5㎥ 미만 세대 (빈집·거의 미사용) → *_n 컬럼은 이상치 제외 값
-- 연도 범위는 WHERE 절 날짜를 바꿔서 사용
WITH s AS (
  SELECT EXTRACT(YEAR FROM sales_ym) y, apartment_code,
    IFNULL(REGEXP_EXTRACT(lot_address, r'\s(\S+)동\s+\S+호\s*$'),'') dong,
    REGEXP_EXTRACT(lot_address, r'\s(\S+)호\s*$') ho,
    CASE WHEN product_name='취사난방용' THEN '개별난방용' ELSE product_name END product,
    industry_name, sales_ym, usage_m3
  FROM `dse-marketing.sales.sale`
  WHERE sales_ym BETWEEN '2021-01-01' AND '2025-12-01' AND IFNULL(apartment_code,'')!=''
), uy AS (
  SELECT y, apartment_code, dong, ho, SUM(usage_m3) m3, COUNT(DISTINCT sales_ym) months
  FROM s WHERE product='개별난방용' AND ho IS NOT NULL
  GROUP BY 1,2,3,4
  HAVING months>=10 AND m3>0 AND LOGICAL_AND(industry_name='아파트')
), j AS (
  SELECT uy.y, uy.m3, a.area_m2, a.area_band, a.area_band_order,
    IFNULL(d.sigungu,'미상') sigungu, IFNULL(b.built_decade,'미상') decade, b.built_source,
    uy.m3 / a.area_m2 >= 2.5 AS normal
  FROM uy
  JOIN `dse-marketing.sales.pbi_ref_apt_unit_area` a
    ON a.apartment_code=uy.apartment_code AND IFNULL(a.dong,'')=uy.dong AND a.ho=uy.ho
  LEFT JOIN `dse-marketing.sales.pbi_ref_apt_built_year` b ON b.apartment_code=uy.apartment_code
  LEFT JOIN `dse-marketing.sales.pbi_dim_apartment` d ON d.apartment_code=uy.apartment_code
  WHERE a.area_m2 IS NOT NULL
)
SELECT y, sigungu, area_band, area_band_order, decade,
  COUNT(*) units, ROUND(SUM(m3),1) m3_sum, ROUND(SUM(area_m2),2) area_sum,
  COUNTIF(normal) units_n, ROUND(SUM(IF(normal,m3,0)),1) m3_n, ROUND(SUM(IF(normal,area_m2,0)),2) area_n,
  COUNTIF(built_source='K-apt 사용승인일') units_kapt
FROM j
GROUP BY 1,2,3,4,5 ORDER BY 1,2,4,5
