-- ④ 점검용: 판매 세대(동·호 파싱)와 면적 테이블 매칭률 확인 — 면적 테이블 갱신 후 실행
WITH t AS (
  SELECT DISTINCT apartment_code,
    IFNULL(REGEXP_EXTRACT(lot_address, r'\s(\S+)동\s+\S+호\s*$'),'') dong,
    REGEXP_EXTRACT(lot_address, r'\s(\S+)호\s*$') ho
  FROM `dse-marketing.sales.sale`
  WHERE sales_ym = (SELECT MAX(sales_ym) FROM `dse-marketing.sales.sale`)
    AND IFNULL(apartment_code,'')!='' AND product_name IN ('개별난방용','취사난방용')
)
SELECT COUNT(*) sale_units,
  COUNTIF(a.apartment_code IS NOT NULL) matched,
  ROUND(COUNTIF(a.apartment_code IS NOT NULL)/COUNT(*),4) match_rate,
  ROUND(COUNTIF(a.area_m2 IS NOT NULL)/COUNT(*),4) area_rate
FROM t LEFT JOIN `dse-marketing.sales.pbi_ref_apt_unit_area` a
  ON a.apartment_code=t.apartment_code AND IFNULL(a.dong,'')=t.dong AND a.ho=t.ho
WHERE t.ho IS NOT NULL;
