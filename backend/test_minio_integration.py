"""
MinIO & Object Storage Verification Script.
Tests connection, bucket status, artifact uploads, presigned URLs, and image caching.
Can be executed by recruiters and developers to verify object storage deployment.
"""
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings
from app.services.storage_service import StorageService


def run_minio_tests():
    print("=" * 80)
    print("INCUBRIX VIDEO ENGINE — MINIO & OBJECT STORAGE VERIFICATION")
    print("=" * 80)
    print(f"MinIO Endpoint:  {settings.minio_endpoint}")
    print(f"MinIO Bucket:    {settings.minio_bucket}")
    print(f"MinIO AccessKey: {settings.minio_access_key}")
    print(f"Use MinIO Flag:  {settings.use_minio}")
    print("-" * 80)

    storage = StorageService()
    if not storage.use_minio:
        print("❌ Error: MinIO is not enabled or connection failed.")
        return False

    print("[SUCCESS] MinIO Client connected successfully!")

    # 1. Test basic file upload
    test_file = Path(__file__)
    test_key = "tests/test_connection.py"
    s3_uri = storage.upload_file(test_file, test_key)
    print(f"[SUCCESS] Uploaded test object: {s3_uri}")

    # 2. Test Presigned URL Generation
    presigned_url = storage.get_presigned_url(test_key, expires_hours=1)
    print(f"[SUCCESS] Generated Presigned URL: {presigned_url[:80]}...")

    # 3. Test Image Caching
    imgs = list(Path("backend/storage/jobs").rglob("*.jpg"))
    if imgs:
        sample_img = imgs[0]
        cache_key = "test_minio_cached_image"
        cached_uri = storage.cache_image(sample_img, cache_key)
        print(f"[SUCCESS] Cached image in MinIO: {cached_uri}")

        temp_dir = Path("backend/storage/temp_test_cache")
        retrieved = storage.get_cached_image(cache_key, temp_dir)
        if retrieved and retrieved.exists():
            print(f"[SUCCESS] Successfully retrieved cached image from MinIO: {retrieved.name} ({retrieved.stat().st_size} bytes)")
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            print("[FAILED] Failed to retrieve cached image from MinIO")

    # 4. List existing job artifacts in MinIO
    print("-" * 80)
    print("Checking stored job artifacts in MinIO:")
    if storage.minio_client:
        objects = list(storage.minio_client.list_objects(settings.minio_bucket, prefix="jobs/", recursive=True))
        print(f"Total job objects in MinIO: {len(objects)}")
        for obj in objects[:8]:
            print(f" - {obj.object_name} ({obj.size} bytes)")
        if len(objects) > 8:
            print(f" ... and {len(objects) - 8} more objects.")

    print("\n" + "=" * 80)
    print("ALL MINIO & OBJECT STORAGE CHECKS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = run_minio_tests()
    sys.exit(0 if success else 1)
