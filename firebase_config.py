import firebase_admin
import streamlit as st
from firebase_admin import credentials, firestore, storage
import sys
import os

try:
    if not firebase_admin._apps:
        # Check for secrets (Streamlit Cloud)
        # Wrap in try-except because accessing st.secrets might error if no file exists
        try:
            if hasattr(st, "secrets") and "firebase" in st.secrets:
                # Create a dictionary from the secrets
                key_dict = dict(st.secrets["firebase"])
                
                # Fix private_key formatting if needed
                if "private_key" in key_dict:
                    key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
                
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred, {
                    "storageBucket": "stores-8f223.appspot.com"
                })
                print("✅ Firebase initialized from Secrets")
                # Return early if successful
                # But we need to set st.session_state or something to indicate success? 
                # No, just set _apps is enough.
        except Exception:
            pass # proceed to local file check

        # Check for local file if not initialized yet
        if not firebase_admin._apps and os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred, {
                "storageBucket": "stores-8f223.appspot.com"
            })
            print("✅ Firebase initialized from local file")
            
        else:
            print("❌ Error: Firebase credentials not found!")
            print("Locally: Add 'serviceAccountKey.json' to root.")
            print("Cloud: Add '[firebase]' secrets in Streamlit Dashboard.")
            # Don't exit, let it fail gracefully or show error in UI
            # sys.exit(1) 
            # Better to let the app run and show error in UI
            pass

    db = firestore.client()
    firestore_module = firestore
    
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
