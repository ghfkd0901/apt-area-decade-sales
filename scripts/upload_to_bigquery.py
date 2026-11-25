"""CSV → GCS 버킷 → 빅쿼리 테이블 (빅쿼리용스트림릿 02_데이터업로드와 같은 방식).
테이블은 sql/ 의 DDL로 미리 만들어 두고(스키마 고정), 여기서는 WRITE_TRUNCATE로 덮어씀.

사용: python upload_to_bigquery.py <csv경로> <테이블명>
예)  python upload_to_bigquery.py ../data/apt_unit_area_20261120.csv pbi_ref_apt_unit_area
"""
import sys, uuid, datetime
from google.cloud import bigquery
from common import clients, PROJECT, DATASET, BUCKET

def upload(csv_path, table):
    bq, gcs = clients()
    name = f"bq_uploads/{datetime.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}_{table}.csv"
    blob = gcs.bucket(BUCKET).blob(name)
    blob.upload_from_filename(csv_path, content_type="text/csv")
    try:
        cfg = bigquery.LoadJobConfig(source_format="CSV", skip_leading_rows=1, autodetect=False,
                                     write_disposition="WRITE_TRUNCATE", encoding="UTF-8",
                                     allow_quoted_newlines=True)
        ref = f"{PROJECT}.{DATASET}.{table}"
        bq.load_table_from_uri(f"gs://{BUCKET}/{name}", ref, job_config=cfg).result()
        print("loaded rows", bq.get_table(ref).num_rows, "→", ref)
    finally:
        blob.delete()

if __name__ == "__main__":
    upload(sys.argv[1], sys.argv[2])
