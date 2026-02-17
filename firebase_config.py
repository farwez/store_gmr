import firebase_admin
from firebase_admin import credentials, firestore, storage
import sys
import os

try:
    if not firebase_admin._apps:
        # Check if service account key exists
        if not os.path.exists("serviceAccountKey.json"):
            print("❌ Error: serviceAccountKey.json not found!")
            print("Please add your Firebase service account key to the project directory.")
            sys.exit(1)
        
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred, {
            "storageBucket": "stores-8f223.appspot.com"
        })
        print("✅ Firebase initialized successfully")

    db = firestore.client()
    
    # Try to get storage bucket, but make it optional
    try:
        bucket = storage.bucket()
        storage_available = True
        print("✅ Firebase Storage available")
    except Exception as storage_error:
        bucket = None
        storage_available = False
        print(f"⚠️ Firebase Storage not available: {storage_error}")
        print("   Bills will be generated locally only (no cloud upload)")
        
except Exception as e:
    print(f"❌ Firebase initialization error: {e}")
    print("Please check your serviceAccountKey.json and Firebase configuration.")
    sys.exit(1)
