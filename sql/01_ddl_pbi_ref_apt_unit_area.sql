-- ① 세대별 전용면적 테이블 (전산팀 공동주택정보등록 w_ea5010_m 추출본)
-- 자동감지로 만들면 공동주택코드 앞자리 0이 사라지므로 반드시 이 DDL로 먼저 생성 후 업로드
CREATE TABLE IF NOT EXISTS `dse-marketing.sales.pbi_ref_apt_unit_area` (
  apartment_code STRING OPTIONS(description='공동주택코드'),
  apartment_name STRING OPTIONS(description='공동주택명'),
  dong STRING OPTIONS(description='동'),
  ho STRING OPTIONS(description='호'),
  pyeong INT64 OPTIONS(description='평형(공급평형, 참고용)'),
  area_m2 FLOAT64 OPTIONS(description='전용면적(㎡)'),
  area_band STRING OPTIONS(description='면적대 (면적 없으면 면적 미등록)'),
  area_band_order INT64 OPTIONS(description='면적대 정렬순서, 미등록=99')
);
