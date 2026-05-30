"""
MongoDB Atlas Connection Test with SSL Handling
Tests connection to Quizgenerator database on Cluster0
"""

import os
import ssl
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

mongodb_uri = os.getenv('MONGODB_URI')

print("="*80)
print("MONGODB ATLAS CONNECTION TEST - QuizGenerator")
print("="*80)
print(f"\n📍 Connection String loaded from .env")
print(f"Database: Quizgenerator")
print(f"Cluster: Cluster0")

if not mongodb_uri:
    print("\n❌ ERROR: MONGODB_URI not found in .env")
    exit(1)

print("\n🔄 Attempting to connect to MongoDB Atlas...\n")

try:
    # Try with SSL verification first
    print("🔐 Attempting with SSL certificate verification...")
    client = MongoClient(
        mongodb_uri,
        connectTimeoutMS=45000,
        socketTimeoutMS=45000,
        serverSelectionTimeoutMS=45000,
        retryWrites=True,
        w='majority',
        ssl=True,
        tlsInsecure=False,
        ssl_cert_reqs=ssl.CERT_REQUIRED
    )
    
    print("⏷ Testing connection with ping command...")
    result = client.admin.command('ping')
    print(f"✅ PING Successful (SSL Verified): {result}\n")
    ssl_mode = "✓ VERIFIED"
    
except Exception as ssl_error:
    print(f"⚠️  SSL verification failed: {str(ssl_error)[:100]}...\n")
    print("🔄 Retrying without strict SSL verification...\n")
    
    try:
        # Try without strict SSL verification
        client = MongoClient(
            mongodb_uri,
            connectTimeoutMS=45000,
            socketTimeoutMS=45000,
            serverSelectionTimeoutMS=45000,
            retryWrites=True,
            w='majority',
            ssl=True,
            tlsInsecure=True
        )
        
        print("⏷ Testing connection with ping command...")
        result = client.admin.command('ping')
        print(f"✅ PING Successful (SSL Unverified): {result}\n")
        ssl_mode = "⚠️  UNVERIFIED (Firewall/Proxy Issue)"
        
    except Exception as final_error:
        print(f"❌ CONNECTION FAILED!")
        print(f"Error: {str(final_error)}\n")
        
        print("🔧 TROUBLESHOOTING STEPS:\n")
        print("1️⃣  WHITELIST YOUR IP IN MONGODB ATLAS (Most Important):")
        print("    • Go to: https://cloud.mongodb.com/")
        print("    • Click 'Cluster0'")
        print("    • Click 'Security' → 'Network Access'")
        print("    • Click 'Add IP Address'")
        print("    • Select 'Allow Access from Anywhere' (0.0.0.0/0)")
        print("    • Click 'Confirm'")
        print("    • WAIT 2-3 MINUTES for changes to take effect\n")
        
        print("2️⃣  CHECK YOUR FIREWALL:")
        print("    • Windows Defender Firewall may block MongoDB (port 27017)")
        print("    • Antivirus software may block SSL connections")
        print("    • Try disabling firewall temporarily to test\n")
        
        print("3️⃣  CHECK INTERNET CONNECTION:")
        print("    • Run: ping google.com")
        print("    • Run: ping cluster0.qsenboa.mongodb.net")
        print("    • Check if you can access https://cloud.mongodb.com/\n")
        
        print("4️⃣  DISABLE VPN IF ENABLED:")
        print("    • Some VPNs block MongoDB Atlas connections")
        print("    • Test with VPN disabled\n")
        
        print("5️⃣  CHECK MONGODB ATLAS STATUS:")
        print("    • Go to: https://status.mongodb.com/")
        print("    • Verify Cluster0 is running (green status)\n")
        
        print("6️⃣  CHECK CLUSTER STATUS IN DASHBOARD:")
        print("    • Go to: https://cloud.mongodb.com/")
        print("    • Click 'Cluster0'")
        print("    • Verify cluster status is 'Running' (green indicator)\n")
        
        print("="*80)
        exit(1)

try:
    # Connect to database
    db = client['Quizgenerator']
    print("📦 Connected to database: Quizgenerator")
    
    # Get existing collections
    collections = db.list_collection_names()
    print(f"\n📋 Existing Collections:")
    if collections:
        for col in collections:
            count = db[col].count_documents({})
            print(f"   • {col} ({count} documents)")
    else:
        print("   (None yet - will be created on first use)")
    
    # Create collections with indexes if they don't exist
    print("\n🔨 Creating collections and indexes...")
    
    # Users collection
    db['users'].create_index('email', unique=True)
    db['users'].create_index('role')
    print("   ✓ Users collection ready")
    
    # Quizzes collection
    db['quizzes'].create_index('instructor_id')
    db['quizzes'].create_index('quiz_code', unique=True)
    db['quizzes'].create_index('created_at')
    print("   ✓ Quizzes collection ready")
    
    # Questions collection
    db['questions'].create_index('quiz_id')
    print("   ✓ Questions collection ready")
    
    # Documents collection
    db['documents'].create_index('instructor_id')
    db['documents'].create_index('created_at')
    print("   ✓ Documents collection ready")
    
    # Attempts collection
    db['attempts'].create_index([('user_id', 1), ('quiz_id', 1)])
    db['attempts'].create_index('created_at')
    print("   ✓ Attempts collection ready")
    
    # Concepts collection
    db['concepts'].create_index('name')
    print("   ✓ Concepts collection ready")
    
    print("\n" + "="*80)
    print("✅ MONGODB ATLAS CONNECTION SUCCESSFUL!")
    print("="*80)
    print("\n📊 Database Details:")
    print(f"   • Database Name: Quizgenerator")
    print(f"   • Host: Cluster0 (MongoDB Atlas)")
    print(f"   • Collections: 6 ready (users, quizzes, questions, documents, attempts, concepts)")
    print(f"   • SSL Mode: {ssl_mode}")
    print(f"   • Status: ✅ Ready for use")
    
    print("\n🔗 View your data in MongoDB Atlas:")
    print("   1. Go to: https://cloud.mongodb.com/")
    print("   2. Login with your MongoDB Atlas account")
    print("   3. Click on 'Cluster0'")
    print("   4. Click 'Browse Collections'")
    print("   5. Select database 'Quizgenerator'")
    print("   6. View your collections and data")
    
    print("\n📝 Next Steps:")
    print("   • Run: python app.py")
    print("   • Go to: http://localhost:5000")
    print("   • Sign up and create quizzes")
    print("   • Data will be saved automatically to MongoDB Atlas")
    
    print("\n" + "="*80 + "\n")
    
    client.close()
    
except Exception as e:
    print(f"\n❌ ERROR: Failed to set up collections")
    print(f"Error: {str(e)}\n")
    exit(1)

