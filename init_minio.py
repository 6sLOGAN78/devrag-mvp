import os
from minio import Minio
from minio.error import S3Error

def init_buckets():
    client = Minio(
        "127.0.0.1:9000",
        access_key="rag_flow",
        secret_key="infini_rag_flow",
        secure=False
    )
    
    bucket_name = "ragflow-raw-documents"
    
    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            print(f"Bucket '{bucket_name}' created successfully.")
        else:
            print(f"Bucket '{bucket_name}' already exists.")
    except S3Error as exc:
        print("error occurred.", exc)

if __name__ == "__main__":
    init_buckets()
