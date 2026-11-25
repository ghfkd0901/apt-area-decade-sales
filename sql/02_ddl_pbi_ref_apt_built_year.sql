-- ② 단지별 준공연도 테이블 (K-apt 사용승인일 매칭 + 최초공급연도 추정 보완)
CREATE TABLE IF NOT EXISTS `dse-marketing.sales.pbi_ref_apt_built_year` (
  apartment_code STRING OPTIONS(description='공동주택코드'),
  apartment_name STRING OPTIONS(description='공동주택명'),
  built_year INT64 OPTIONS(description='준공연도 (K-apt 사용승인일 연도, 없으면 최초공급연도 추정)'),
  built_date DATE OPTIONS(description='K-apt 사용승인일 (매칭된 단지만)'),
  built_decade STRING OPTIONS(description='준공연대 (예: 1990년대)'),
  built_source STRING OPTIONS(description='K-apt 사용승인일 / 최초공급연도 추정 / 최초공급연도 추정(1983 이전 가능) / 없음'),
  kapt_code STRING OPTIONS(description='K-apt 단지코드'),
  kapt_name STRING OPTIONS(description='K-apt 단지명'),
  match_method STRING OPTIONS(description='K-apt 매칭 방식'),
  first_supply_year_est INT64 OPTIONS(description='최초공급연도 추정 (pbi_dim_apartment.built_year_est)')
);
