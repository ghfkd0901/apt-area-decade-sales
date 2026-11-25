-- ⑤ 스트림릿 앱용 세대×연도 단위 원자료 (1회 추출 → data/unit_year.parquet)
-- 규칙: 취사난방용→개별난방용 통합, 연 10개월 이상 & 판매량>0, 면적 매칭된 세대만
--       아파트 여부·이상치는 앱에서 필터 (is_apt 컬럼, ㎡당 기준 슬라이더)
-- 동·호 등 세대 식별정보는 저장하지 않음 (세대 키는 해시값으로만 보관)
WITH s AS (
  SELECT EXTRACT(YEAR FROM sales_ym) y, apartment_code,
    IFNULL(REGEXP_EXTRACT(lot_address, r'\s(\S+)동\s+\S+호\s*$'),'') dong,
    REGEXP_EXTRACT(lot_address, r'\s(\S+)호\s*$') ho,
    CASE WHEN product_name='취사난방용' THEN '개별난방용' ELSE product_name END product,
    industry_name, sales_ym, usage_m3
  FROM `dse-marketing.sales.sale`
  WHERE sales_ym BETWEEN '2021-01-01' AND '2025-12-01' AND IFNULL(apartment_code,'')!=''
), uy AS (
  SELECT y, apartment_code, dong, ho, SUM(usage_m3) m3, COUNT(DISTINCT sales_ym) months,
    LOGICAL_AND(industry_name='아파트') is_apt
  FROM s WHERE product='개별난방용' AND ho IS NOT NULL
  GROUP BY 1,2,3,4 HAVING months>=10 AND m3>0
)
SELECT uy.y, uy.apartment_code, a.apartment_name, IFNULL(d.sigungu,'미상') sigungu,
  FARM_FINGERPRINT(CONCAT(uy.apartment_code,'|',uy.dong,'|',uy.ho)) unit_key,
  uy.is_apt, a.area_m2, b.built_year, b.built_source, uy.m3
FROM uy
JOIN `dse-marketing.sales.pbi_ref_apt_unit_area` a
  ON a.apartment_code=uy.apartment_code AND IFNULL(a.dong,'')=uy.dong AND a.ho=uy.ho
LEFT JOIN `dse-marketing.sales.pbi_ref_apt_built_year` b ON b.apartment_code=uy.apartment_code
LEFT JOIN `dse-marketing.sales.pbi_dim_apartment` d ON d.apartment_code=uy.apartment_code
WHERE a.area_m2 IS NOT NULL
