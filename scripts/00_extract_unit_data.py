"""⓪ 스트림릿 앱용 세대×연도 데이터 1회 추출 (빅쿼리 비용 발생 — 데이터 갱신할 때만 실행)
sql/05_unit_year_extract.sql 을 1번 실행 → 임시테이블 → GCS에 parquet로 내보내기 → 다운로드 → data/unit_year.parquet
임시테이블·GCS 파일은 끝나면 삭제.
사용: python 00_extract_unit_data.py            (한 번에 실행)
      python 00_extract_unit_data.py --start    (쿼리만 제출)  →  --fetch (결과 받기)
"""
import sys, datetime, tempfile
from pathlib import Path
import pandas as pd
from google.cloud import bigquery
from common import DATA, SQL, clients, PROJECT, DATASET, BUCKET

TMP = f"{PROJECT}.{DATASET}._tmp_unit_year_extract"
PREFIX = "tmp/unit_year_extract/"


def start(bq):
    sql = (SQL / '05_unit_year_extract.sql').read_text(encoding='utf-8')
    cfg = bigquery.QueryJobConfig(destination=TMP, write_disposition="WRITE_TRUNCATE")
    job = bq.query(sql, job_config=cfg)
    print("submitted", job.job_id)
    return job


def fetch(bq, gcs):
    for j in bq.list_jobs(max_results=20):
        if getattr(j, "destination", None) and str(j.destination).endswith("_tmp_unit_year_extract") and j.state != "DONE":
            print("waiting job", j.job_id); j.result()
    t = bq.get_table(TMP)
    t.expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=6); bq.update_table(t, ["expires"])
    print("tmp rows", t.num_rows)
    cfg = bigquery.ExtractJobConfig(destination_format="PARQUET", compression="SNAPPY")
    bq.extract_table(TMP, f"gs://{BUCKET}/{PREFIX}part-*.parquet", job_config=cfg).result()
    blobs = list(gcs.bucket(BUCKET).list_blobs(prefix=PREFIX))
    parts = []
    with tempfile.TemporaryDirectory() as td:
        for b in blobs:
            p = Path(td) / Path(b.name).name; b.download_to_filename(p); parts.append(pd.read_parquet(p))
    df = pd.concat(parts, ignore_index=True)
    df['y'] = df['y'].astype('int16')
    for c in ['apartment_code', 'apartment_name', 'sigungu', 'built_source']:
        df[c] = df[c].astype('category')
    df['built_year'] = df['built_year'].astype('Int16')
    df['area_m2'] = df['area_m2'].astype('float32'); df['m3'] = df['m3'].astype('float32')
    df['is_apt'] = df['is_apt'].astype(bool)
    out = DATA / 'unit_year.parquet'
    df.to_parquet(out, index=False, compression='zstd')
    print(f'saved {out} rows={len(df):,}'); print(df.groupby('y').size())
    for b in blobs: b.delete()
    bq.delete_table(TMP, not_found_ok=True); print("cleaned tmp table & gcs files")


if __name__ == '__main__':
    bq, gcs = clients()
    if '--fetch' not in sys.argv: start(bq)
    if '--start' not in sys.argv: fetch(bq, gcs)
