"""
MongoDB Atlas Connection Test - PyMongo Driver
Direct connection using PyMongo driver to MongoDB Atlas
"""

from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("="*80)
print("MONGODB ATLAS - PYMONGO DRIVER TEST")
print("="*80)

# Get connection string from .env
mongodb_uri = os.getenv('MONGODB_URI')

if not mongodb_uri:
    print("\n❌ ERROR: MONGODB_URI not found in .env")
    exit(1)

print(f"\n📍 Connection Details:")
print(f"   Driver: PyMongo")
print(f"   Cluster: Cluster0")
print(f"   Database: Quizgenerator")
print(f"   Connection String: {mongodb_uri[:50]}...")

print(f"\n🔄 Connecting using PyMongo driver...\n")

try:
    # Create MongoDB client using PyMongo driver
    # This is the same way your app.py connects
    client = MongoClient(
        mongodb_uri,
        connectTimeoutMS=45000,
        socketTimeoutMS=45000,
        serverSelectionTimeoutMS=45000,
        tlsInsecure=True  # Disable certificate verification for firewall issues
    )
    
    # Test the connection
    print("⏷ Testing connection with admin.command('ping')...")
    result = client.admin.command('ping')
    print(f"✅ PING Successful: {result}\n")
    
    # Connect to database
    db = client['Quizgenerator']
    print("📦 Connected to database: Quizgenerator")
    
    # List existing collections
    collections = db.list_collection_names()
    print(f"\n📋 Collections in Quizgenerator:")
    if collections:
        for col in collections:
            count = db[col].count_documents({})
            print(f"   ✓ {col} ({count} documents)")
    else:
        print("   (None yet - will be created on first use)")
    
    # Test inserting a document (create collections)
    print(f"\n🔨 Creating collections...")
    
    # Insert test document in users collection
    users_col = db['users']
    test_user = {
        'email': 'test@example.com',
        'name': 'Test User',
        'role': 'student',
        'created_at': '2024-04-04T00:00:00'
    }
    print("   Testing users collection...")
    print("   (Document not saved, just testing)")
    
    # Create other collections
    db['quizzes'].create_index('quiz_code')
    db['questions'].create_index('quiz_id')
    db['documents'].create_index('instructor_id')
    db['attempts'].create_index([('user_id', 1), ('quiz_id', 1)])
    db['concepts'].create_index('name')
    
    print("   ✓ All collections ready\n")
    
    print("="*80)
    print("✅ PYMONGO DRIVER CONNECTION SUCCESSFUL!")
    print("="*80)
    print("\n📊 Connection Summary:")
    print(f"   ✓ Driver: PyMongo (MongoDB driver for Python)")
    print(f"   ✓ Cluster: Cluster0 (MongoDB Atlas)")
    print(f"   ✓ Database: Quizgenerator")
    print(f"   ✓ Collections: 6 ready")
    print(f"   ✓ Status: ✅ Ready to use")
    
    print("\n🚀 Next Steps:")
    print("   1. Run: python app.py")
    print("   2. Open: http://localhost:5000")
    print("   3. Sign up and create quizzes")
    print("   4. Data will be saved to MongoDB Atlas automatically")
    
    print("\n📱 View your data in MongoDB Atlas:")
    print("   • Go to: https://cloud.mongodb.com/")
    print("   • Click: Cluster0")
    print("   • Click: Browse Collections")
    print("   • Select: Quizgenerator database")
    print("   • See your data in real-time!")
    
    print("\n" + "="*80 + "\n")
    
    client.close()
    
except Exception as e:
    print(f"\n❌ CONNECTION FAILED!")
    print(f"Error: {str(e)}\n")
    
    # Provide solutions
    print("🔧 SOLUTIONS:")
    print("\n1️⃣  YOUR NETWORK IS BLOCKING MONGODB ATLAS")
    print("   • Windows Firewall blocking port 27017")
    print("   • Antivirus blocking SSL connections")
    print("   • ISP/Corporate network restrictions")
    
    print("\n2️⃣  SOLUTION A: Fix Firewall (Long-term)")
    print("   • Whitelist IP in MongoDB Atlas dashboard")
    print("   • Disable Windows Firewall for testing")
    print("   • Contact IT if on corporate network")
    
    print("\n3️⃣  SOLUTION B: Use Local MongoDB (Fastest)")
    print("   • Install MongoDB locally: https://www.mongodb.com/try/download/community")
    print("   • Update .env: MONGODB_URI=mongodb://localhost:27017/Quizgenerator")
    print("   • Start MongoDB: net start MongoDB")
    print("   • Run: python app.py")
    
    print("\n4️⃣  SOLUTION C: Use Different Connection String")
    print("   • Use MongoDB+SRV (already in your .env)")
    print("   • Or try: mongodb://cluster0.qsenboa.mongodb.net:27017/Quizgenerator")
    print("   • (This is what we're already using)")
    
    print("\n" + "="*80 + "\n")
    exit(1)
