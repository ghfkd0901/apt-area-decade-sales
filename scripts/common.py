"""공통 설정 — 빅쿼리/GCS 클라이언트.
서비스계정 키는 D:\\Project\\빅쿼리용스트림릿 의 키를 그대로 사용 (이 폴더에 복사하지 않음).
"""
import os
from pathlib import Path
from google.cloud import bigquery, storage
from google.oauth2 import service_account

PROJECT = "dse-marketing"
DATASET = "sales"
BUCKET = "daesung_marketing"
KEY_PATH = os.environ.get(
    "DSE_GCP_KEY",
    r"D:\Project\빅쿼리용스트림릿\dse-marketing-9992ea6d6a24.json",
)
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
SQL = ROOT / "sql"


def clients():
    cred = service_account.Credentials.from_service_account_file(
        KEY_PATH, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return (bigquery.Client(credentials=cred, project=PROJECT),
            storage.Client(credentials=cred, project=PROJECT))


def query_df(sql: str):
    bq, _ = clients()
    return bq.query(sql).to_dataframe()
