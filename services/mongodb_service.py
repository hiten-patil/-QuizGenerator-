"""
MongoDB Service - Database operations with MongoDB Atlas
"""
import os
import secrets
import string
import ssl
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from bson.objectid import ObjectId
import bcrypt
import jwt


def _safe_print(message: str):
    """Print with safe encoding handling"""
    try:
        print(message, flush=True)
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback: encode to ASCII if Unicode fails (Windows console)
        safe = message.encode('ascii', errors='replace').decode('ascii')
        print(safe, flush=True)


class MongoDBService:
    """
    Service for MongoDB operations with MongoDB Atlas.
    
    MongoDB Atlas Setup Instructions:
    1. Go to: https://cloud.mongodb.com/
    2. Login and navigate to Cluster0
    3. Click "Browse Collections" to view your data
    4. Database name: Quizgenerator
    5. Collections: users, quizzes, documents, questions, attempts
    
    If you get SSL timeout:
    - Check IP whitelist in MongoDB Atlas Security → Network Access
    - Add your IP address or use 0.0.0.0/0
    - Check firewall/antivirus blocking port 27017
    """
    
    def __init__(self):
        self._client = None
        self._db = None
        self._initialized = False
        self._initialize_mongodb()
    
    def _initialize_mongodb(self):
        """Initialize MongoDB Atlas connection with SSL/TLS handling and local fallback"""
        try:
            from pymongo import MongoClient
            
            mongodb_uri = os.getenv('MONGODB_URI')
            if not mongodb_uri:
                _safe_print("[MongoDB] WARNING: No URI configured. Running in demo mode.")
                self._initialized = False
                return
            
            _safe_print("[MongoDB] Connecting to MongoDB Atlas...")
            
            # Check if it's Atlas or Local
            is_atlas = 'mongodb+srv://' in mongodb_uri
            if is_atlas:
                _safe_print("[MongoDB] MongoDB Atlas detected")
            
            # Try connection with SSL verification first (recommended)
            _safe_print("[MongoDB] Testing connection with SSL verification...")
            try:
                self._client = MongoClient(
                    mongodb_uri,
                    connectTimeoutMS=45000,
                    socketTimeoutMS=45000,
                    serverSelectionTimeoutMS=45000,
                    retryWrites=True,
                    w='majority',
                    authSource='admin',
                    minPoolSize=1,
                    maxPoolSize=50,
                    maxIdleTimeMS=45000,
                    # SSL/TLS settings
                    ssl=True,
                    tlsInsecure=False,
                    ssl_cert_reqs=ssl.CERT_REQUIRED
                )
                
                # Test connection
                self._client.admin.command('ping')
                self._db = self._client['Quizgenerator']
                self._initialized = True
                
                # Extract connection info for display
                uri_parts = mongodb_uri.replace('mongodb://', '').replace('mongodb+srv://', '')
                host_info = uri_parts.split('/')[0]
                
                _safe_print(f"[MongoDB] SUCCESS: Connected to MongoDB (SSL verified)")
                _safe_print(f"[MongoDB] Host: {host_info}")
                _safe_print(f"[MongoDB] Database: Quizgenerator")
                
                # Create indexes for better performance
                self._create_indexes()
                return
                
            except Exception as ssl_error:
                # If SSL verification fails, try without strict verification
                _safe_print("[MongoDB] WARNING: SSL verification failed, retrying without strict verification...")
                
                self._client = MongoClient(
                    mongodb_uri,
                    connectTimeoutMS=45000,
                    socketTimeoutMS=45000,
                    serverSelectionTimeoutMS=45000,
                    retryWrites=True,
                    w='majority',
                    authSource='admin',
                    minPoolSize=1,
                    maxPoolSize=50,
                    maxIdleTimeMS=45000,
                    # SSL/TLS settings - less strict
                    ssl=True,
                    tlsInsecure=True  # Disable certificate verification (for firewall issues)
                )
                
                # Test connection
                self._client.admin.command('ping')
                self._db = self._client['Quizgenerator']
                self._initialized = True
                
                # Extract connection info for display
                uri_parts = mongodb_uri.replace('mongodb://', '').replace('mongodb+srv://', '')
                host_info = uri_parts.split('/')[0]
                
                _safe_print(f"[MongoDB] SUCCESS: Connected to MongoDB (SSL unverified)")
                _safe_print(f"[MongoDB] Host: {host_info}")
                _safe_print(f"[MongoDB] Database: Quizgenerator")
                
                # Create indexes for better performance
                self._create_indexes()
                return
            
        except Exception as e:
            error_msg = str(e)
            _safe_print(f"\n[MongoDB] ERROR: Connection failed")
            _safe_print(f"[MongoDB] Details: {error_msg}\n")
            
            if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower() or 'ssl' in error_msg.lower():
                _safe_print("[MongoDB] TROUBLESHOOTING - SSL/Firewall Issue:")
                _safe_print("")
                _safe_print("[1] WHITELIST YOUR IP (most common fix):")
                _safe_print("    - Go to: https://cloud.mongodb.com/")
                _safe_print("    - Click 'Cluster0'")
                _safe_print("    - Go to 'Security' > 'Network Access'")
                _safe_print("    - Click 'Add IP Address'")
                _safe_print("    - Select 'Allow Access from Anywhere' (0.0.0.0/0)")
                _safe_print("    - Click 'Confirm' and wait 2-3 minutes")
                _safe_print("")
                _safe_print("[2] CHECK FIREWALL SETTINGS:")
                _safe_print("    - Windows Firewall may be blocking port 27017")
                _safe_print("    - Antivirus software may block SSL connections")
                _safe_print("    - Try temporarily disabling firewall to test")
                _safe_print("")
                _safe_print("[3] CHECK INTERNET CONNECTION:")
                _safe_print("    - Run: ping google.com")
                _safe_print("    - Run: ping cluster0.qsenboa.mongodb.net")
                _safe_print("")
                _safe_print("[4] DISABLE VPN:")
                _safe_print("    - If using VPN, try disabling it")
                _safe_print("    - Some VPNs block MongoDB Atlas")
                _safe_print("")
                _safe_print("[5] AFTER FIXING:")
                _safe_print("    - Run: python test_atlas_connection.py")
                _safe_print("    - Then: python app.py")
                _safe_print("")
            elif 'authentication' in error_msg.lower() or 'auth' in error_msg.lower():
                _safe_print("[MongoDB] ERROR: Authentication failed!")
                _safe_print("[MongoDB] Check credentials in .env:")
                _safe_print("    - Username: krishalmodi2345_db_user")
                _safe_print("    - Password: c35p04qQXnVk9VaU")
                _safe_print("    - Verify they are correct in MongoDB Atlas")
            
            # Try automatic fallback to local MongoDB so the app can still fully work
            try:
                from pymongo import MongoClient as _MongoClientFallback
                fallback_uri = os.getenv(
                    'MONGODB_FALLBACK_URI',
                    'mongodb://localhost:27017/Quizgenerator'
                )
                if fallback_uri:
                    _safe_print("[MongoDB] Attempting fallback to local MongoDB...")
                    self._client = _MongoClientFallback(
                        fallback_uri,
                        connectTimeoutMS=10000,
                        socketTimeoutMS=10000,
                        serverSelectionTimeoutMS=10000,
                        minPoolSize=1,
                        maxPoolSize=20,
                    )
                    # Test local connection
                    self._client.admin.command('ping')
                    self._db = self._client['Quizgenerator']
                    self._initialized = True

                    # Extract connection info for display
                    uri_parts = fallback_uri.replace('mongodb://', '').replace('mongodb+srv://', '')
                    host_info = uri_parts.split('/')[0]

                    _safe_print("[MongoDB] SUCCESS: Connected to local MongoDB (fallback)")
                    _safe_print(f"[MongoDB] Host: {host_info}")
                    _safe_print("[MongoDB] Database: Quizgenerator")

                    # Create indexes for the local database as well
                    self._create_indexes()
                    return
            except Exception as local_err:
                _safe_print(f"[MongoDB] WARNING: Local fallback also failed: {local_err}")

            self._initialized = False
            _safe_print("[MongoDB] RUNNING IN DEMO MODE (data not persisted - will not save to database)\n")
    
    def _create_indexes(self):
        """Create database indexes for performance"""
        try:
            # Users index
            self._db['users'].create_index('email', unique=True)
            self._db['users'].create_index('role')
            
            # Documents index
            self._db['documents'].create_index('instructor_id')
            self._db['documents'].create_index('created_at')
            
            # Quizzes index
            self._db['quizzes'].create_index('instructor_id')
            self._db['quizzes'].create_index('quiz_code', unique=True)
            self._db['quizzes'].create_index('created_at')
            
            # Questions index
            self._db['questions'].create_index('quiz_id')
            
            # Attempts index
            self._db['attempts'].create_index([('user_id', 1), ('quiz_id', 1)])
            self._db['attempts'].create_index('created_at')
            
        except Exception as e:
            _safe_print(f"[MongoDB] WARNING: Could not create indexes: {e}")
    
    def get_timestamp(self) -> str:
        """Get current timestamp as ISO string"""
        return datetime.utcnow().isoformat()
    
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    def _verify_password(self, password: str, hash_: str) -> bool:
        """Verify password against hash"""
        try:
            return bcrypt.checkpw(password.encode(), hash_.encode())
        except:
            return False
    
    # ===================== AUTHENTICATION =====================
    
    def sign_in(self, email: str, password: str) -> Optional[Dict]:
        """Sign in user with email and password"""
        if not self._initialized:
            # Demo mode
            return {
                'user_id': 'demo_user_1',
                'email': email,
                'id_token': 'demo_token'
            }
        
        try:
            if not email or not password:
                raise Exception("Email and password are required.")
            
            user = self._db['users'].find_one({'email': email.lower()})
            if not user:
                raise Exception("Email not found. Please sign up first.")
            
            if not self._verify_password(password, user.get('password_hash', '')):
                raise Exception("Incorrect password. Please try again.")
            
            # Generate JWT token
            token = jwt.encode(
                {
                    'user_id': str(user['_id']),
                    'email': user['email'],
                    'exp': datetime.utcnow().timestamp() + 86400 * 7  # 7 days
                },
                os.getenv('SECRET_KEY', 'your-secret-key-change-in-production'),
                algorithm='HS256'
            )
            
            return {
                'user_id': str(user['_id']),
                'email': user['email'],
                'id_token': token
            }
        except Exception as e:
            raise Exception(str(e))
    
    def create_user(self, email: str, password: str, name: str = '', role: str = 'student') -> Optional[Dict]:
        """Create new user account"""
        if not self._initialized:
            return {'user_id': 'demo_user_1', 'email': email}
        
        try:
            email = email.lower()
            
            # Check if user already exists
            if self._db['users'].find_one({'email': email}):
                raise Exception("Email already registered. Please login or use a different email.")
            
            user_data = {
                'email': email,
                'name': name or email.split('@')[0],
                'password_hash': self._hash_password(password),
                'role': role,
                'created_at': self.get_timestamp(),
                'updated_at': self.get_timestamp(),
                'is_active': True,
                'concept_mastery': {},
                'quiz_history': []
            }
            
            result = self._db['users'].insert_one(user_data)
            return {
                'user_id': str(result.inserted_id),
                'email': email
            }
        except Exception as e:
            raise Exception(str(e))
    
    def send_password_reset(self, email: str):
        """Send password reset email (placeholder)"""
        if not self._initialized:
            return True
        
        try:
            user = self._db['users'].find_one({'email': email.lower()})
            if not user:
                raise Exception("Email not found.")
            
            # Generate reset token (use secrets for secure random generation)
            reset_token = secrets.token_urlsafe(32)
            expiry = datetime.utcnow().timestamp() + 3600  # 1 hour
            
            self._db['users'].update_one(
                {'_id': user['_id']},
                {
                    '$set': {
                        'reset_token': reset_token,
                        'reset_token_expiry': expiry
                    }
                }
            )
            
            # TODO: Send email with reset token
            _safe_print(f"[Auth] Password reset token generated for {email}")
            return True
        except Exception as e:
            raise Exception(str(e))
    
    # ===================== USER DATA =====================
    
    def get_user_data(self, user_id: str) -> Dict:
        """Get user profile and data"""
        if not self._initialized:
            return self._get_demo_user_data()
        
        try:
            if not ObjectId.is_valid(user_id):
                return {}
            
            user = self._db['users'].find_one({'_id': ObjectId(user_id)})
            if user:
                user['id'] = str(user['_id'])
                del user['_id']
                del user['password_hash']  # Don't return password hash
            return user or {}
        except Exception as e:
            _safe_print(f"[MongoDB] Error getting user data: {e}")
            return {}
    
    def save_user_data(self, user_id: str, data: Dict):
        """Save user profile data"""
        if not self._initialized:
            return True
        
        try:
            if not ObjectId.is_valid(user_id):
                raise Exception("Invalid user ID")
            
            # Don't allow changing password here
            if 'password_hash' in data:
                del data['password_hash']
            
            data['updated_at'] = self.get_timestamp()
            
            self._db['users'].update_one(
                {'_id': ObjectId(user_id)},
                {'$set': data}
            )
            return True
        except Exception as e:
            raise Exception(str(e))
    
    def update_user_data(self, user_id: str, data: Dict):
        """Update specific user data fields"""
        return self.save_user_data(user_id, data)
    
    # ===================== DOCUMENTS =====================
    
    def save_document(self, user_id: str, doc_data: Dict) -> str:
        """Save uploaded document and return document ID"""
        if not self._initialized:
            return 'demo_doc_1'
        
        try:
            doc_data['instructor_id'] = user_id
            doc_data['created_at'] = self.get_timestamp()
            doc_data['updated_at'] = self.get_timestamp()
            
            result = self._db['documents'].insert_one(doc_data)
            return str(result.inserted_id)
        except Exception as e:
            raise Exception(f"Failed to save document: {str(e)}")
    
    def get_document(self, doc_id: str) -> Optional[Dict]:
        """Get document by ID"""
        if not self._initialized:
            return self._get_demo_document()
        
        try:
            if not ObjectId.is_valid(doc_id):
                return None
            
            doc = self._db['documents'].find_one({'_id': ObjectId(doc_id)})
            if doc:
                doc['id'] = str(doc['_id'])
                del doc['_id']
            return doc
        except Exception as e:
            _safe_print(f"[MongoDB] Error getting document: {e}")
            return None
    
    def get_instructor_documents(self, user_id: str) -> List[Dict]:
        """Get all documents uploaded by instructor"""
        if not self._initialized:
            return [self._get_demo_document()]
        
        try:
            docs = list(self._db['documents'].find({'instructor_id': user_id}))
            
            for doc in docs:
                doc['id'] = str(doc['_id'])
                del doc['_id']
            return docs
        except Exception as e:
            _safe_print(f"[MongoDB] Error getting documents: {e}")
            return []
    
    # ===================== QUIZZES =====================
    
    def generate_unique_quiz_code(self, max_attempts: int = 10) -> str:
        """Generate 16-digit unique quiz code (alphanumeric)"""
        if not self._initialized:
            return secrets.token_hex(8).upper()
        
        try:
            chars = string.ascii_uppercase + string.digits
            for _ in range(max_attempts):
                code = ''.join(secrets.choice(chars) for _ in range(16))
                
                # Check if code already exists
                if not self._db['quizzes'].find_one({'quiz_code': code}):
                    return code
            
            # Fallback: use UUID-based code
            return secrets.token_hex(8).upper()
        except Exception as e:
            _safe_print(f"[MongoDB] Error generating quiz code: {e}")
            return secrets.token_hex(8).upper()
    
    def create_quiz(self, quiz_data: Dict, questions: List[Dict]) -> str:
        """Create new quiz with questions and generate unique quiz code"""
        if not self._initialized:
            return 'demo_quiz_1'
        
        try:
            # Generate unique quiz code
            quiz_code = self.generate_unique_quiz_code()
            quiz_data['quiz_code'] = quiz_code
            quiz_data['created_at'] = self.get_timestamp()
            quiz_data['updated_at'] = self.get_timestamp()
            
            # Create quiz
            quiz_result = self._db['quizzes'].insert_one(quiz_data)
            quiz_id = str(quiz_result.inserted_id)
            
            # Save questions
            for question in questions:
                question['quiz_id'] = quiz_id
                question['created_at'] = self.get_timestamp()
                self._db['questions'].insert_one(question)
            
            return quiz_id
        except Exception as e:
            raise Exception(f"Failed to create quiz: {str(e)}")
    
    def get_quiz(self, quiz_id: str) -> Optional[Dict]:
        """Get quiz by ID"""
        if not self._initialized:
            return self._get_demo_quiz()
        
        try:
            if not ObjectId.is_valid(quiz_id):
                return None
            
            quiz = self._db['quizzes'].find_one({'_id': ObjectId(quiz_id)})
            if quiz:
                quiz['id'] = str(quiz['_id'])
                del quiz['_id']
            return quiz
        except Exception as e:
            print(f"Error getting quiz: {e}")
            return None
    
    def get_quiz_questions(self, quiz_id: str) -> List[Dict]:
        """Get all questions for a quiz"""
        if not self._initialized:
            return self._get_demo_questions()
        
        try:
            questions = list(self._db['questions'].find({'quiz_id': quiz_id}))
            
            for q in questions:
                q['id'] = str(q['_id'])
                del q['_id']
            return questions
        except Exception as e:
            _safe_print(f"[MongoDB] Error getting questions: {e}")
            return []
    
    def get_question(self, quiz_id: str, question_id: str) -> Optional[Dict]:
        """Get specific question"""
        questions = self.get_quiz_questions(quiz_id)
        for q in questions:
            if q['id'] == question_id:
                return q
        return None
    
    def update_quiz_questions(self, quiz_id: str, questions: List[Dict]):
        """Update quiz questions"""
        if not self._initialized:
            return True
        
        try:
            for q in questions:
                q_id = q.get('id')
                if q_id and ObjectId.is_valid(q_id):
                    q_copy = q.copy()
                    del q_copy['id']
                    q_copy['updated_at'] = self.get_timestamp()
                    
                    self._db['questions'].update_one(
                        {'_id': ObjectId(q_id)},
                        {'$set': q_copy}
                    )
            return True
        except Exception as e:
            raise Exception(f"Failed to update questions: {str(e)}")
    
    def get_instructor_quizzes(self, user_id: str) -> List[Dict]:
        """Get quizzes created by instructor"""
        if not self._initialized:
            return [self._get_demo_quiz()]
        
        try:
            quizzes = list(self._db['quizzes'].find({'instructor_id': user_id}))
            
            for quiz in quizzes:
                quiz['id'] = str(quiz['_id'])
                del quiz['_id']
            return quizzes
        except Exception as e:
            print(f"Error getting instructor quizzes: {e}")
            return []
    
    def get_available_quizzes(self, user_id: str) -> List[Dict]:
        """Get quizzes available to a user (public + own)"""
        if not self._initialized:
            return [self._get_demo_quiz()]
        
        try:
            # Get public quizzes and user's own quizzes
            quizzes = list(self._db['quizzes'].find({
                '$or': [
                    {'is_password_protected': False},
                    {'instructor_id': user_id}
                ]
            }))
            
            for quiz in quizzes:
                quiz['id'] = str(quiz['_id'])
                del quiz['_id']
            return quizzes
        except Exception as e:
            print(f"Error getting quizzes: {e}")
            return []
    
    def get_quiz_by_code(self, quiz_code: str) -> Optional[str]:
        """Get quiz ID from quiz code"""
        if not self._initialized:
            return 'demo_quiz_1'
        
        try:
            quiz = self._db['quizzes'].find_one({'quiz_code': quiz_code})
            if quiz:
                return str(quiz['_id'])
            return None
        except Exception as e:
            _safe_print(f"[MongoDB] Error getting quiz by code: {e}")
            return None
    
    def delete_quiz(self, quiz_id: str) -> bool:
        """Delete a quiz and all associated data"""
        if not self._initialized:
            return True
        
        try:
            if not ObjectId.is_valid(quiz_id):
                raise Exception("Invalid quiz ID")
            
            # Delete quiz
            self._db['quizzes'].delete_one({'_id': ObjectId(quiz_id)})
            
            # Delete questions
            self._db['questions'].delete_many({'quiz_id': quiz_id})
            
            # Note: We don't delete attempts as they contain student history
            _safe_print(f"[Quiz] Successfully deleted quiz {quiz_id}")
            return True
        except Exception as e:
            _safe_print(f"[MongoDB] Error deleting quiz: {e}")
            raise Exception(f"Failed to delete quiz: {str(e)}")
    
    # ===================== QUIZ ATTEMPTS =====================
    
    def create_quiz_attempt(self, user_id: str, quiz_id: str, questions: List[Dict]) -> str:
        """Create new quiz attempt"""
        if not self._initialized:
            return 'demo_attempt_1'
        
        try:
            attempt_data = {
                'user_id': user_id,
                'quiz_id': quiz_id,
                'question_ids': [q.get('id', '') for q in questions],
                'status': 'in_progress',
                'created_at': self.get_timestamp(),
                'updated_at': self.get_timestamp()
            }
            
            result = self._db['attempts'].insert_one(attempt_data)
            return str(result.inserted_id)
        except Exception as e:
            raise Exception(f"Failed to create attempt: {str(e)}")
    
    def save_quiz_result(self, user_id: str, quiz_id: str, attempt_id: str, result: Dict):
        """Save quiz attempt result"""
        if not self._initialized:
            return True
        
        try:
            import math
            
            def sanitize_value(value):
                if isinstance(value, (int, bool, str, type(None))):
                    return value
                if isinstance(value, float):
                    if math.isnan(value) or math.isinf(value):
                        return 0.0
                    return float(value)
                if isinstance(value, dict):
                    return {str(k): sanitize_value(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [sanitize_value(item) for item in value]
                return str(value)
            
            def sanitize_key(key):
                if not key:
                    return 'unknown'
                # Remove invalid characters
                safe_key = str(key).strip()
                if len(safe_key) > 100:
                    safe_key = safe_key[:100]
                return safe_key
            
            # Create sanitized result
            sanitized_result = {
                'score': sanitize_value(result.get('score', 0)),
                'score_percentage': sanitize_value(result.get('score_percentage', result.get('score', 0))),
                'correct': int(result.get('correct', 0)),
                'total_questions': int(result.get('total_questions', 0)),
                'marks_obtained': sanitize_value(result.get('marks_obtained', 0)),
                'total_marks': sanitize_value(result.get('total_marks', 100)),
                'timestamp': str(result.get('timestamp', self.get_timestamp())),
                'quiz_name': sanitize_value(result.get('quiz_name', 'Quiz'))
            }
            
            # Sanitize concept performance
            if 'concept_performance' in result and result['concept_performance']:
                sanitized_concepts = {}
                for concept, performance in result['concept_performance'].items():
                    safe_key = sanitize_key(concept)
                    safe_value = sanitize_value(performance)
                    sanitized_concepts[safe_key] = safe_value
                sanitized_result['concept_performance'] = sanitized_concepts
            
            # Sanitize detailed results
            sanitized_details = []
            for item in result.get('results', []):
                if isinstance(item, dict):
                    sanitized_details.append({
                        'question_id': str(item.get('question_id', '')),
                        'question_text': str(item.get('question_text', 'N/A'))[:500],
                        'question_type': str(item.get('question_type', 'mcq')),
                        'is_correct': bool(item.get('is_correct', False)),
                        'user_answer': str(item.get('user_answer', ''))[:300],
                        'correct_answer': str(item.get('correct_answer', ''))[:300],
                        'concept': sanitize_key(str(item.get('concept', 'General'))),
                        'explanation': str(item.get('explanation', ''))[:500],
                        'marks_obtained': int(item.get('marks_obtained', 0)),
                        'marks_total': int(item.get('marks_total', 1)),
                    })
            sanitized_result['details'] = sanitized_details
            
            if 'time_taken' in result:
                sanitized_result['time_taken'] = int(result.get('time_taken', 0))
            if 'time_taken_display' in result:
                sanitized_result['time_taken_display'] = str(result.get('time_taken_display', 'N/A'))
            
            # Update attempt with results
            if not ObjectId.is_valid(attempt_id):
                raise Exception("Invalid attempt ID")
            
            self._db['attempts'].update_one(
                {'_id': ObjectId(attempt_id)},
                {
                    '$set': {
                        'status': 'completed',
                        'completed_at': self.get_timestamp(),
                        'result': sanitized_result,
                        'updated_at': self.get_timestamp()
                    }
                }
            )
            
            # Update user concept mastery
            if 'concept_performance' in result and result['concept_performance']:
                user = self._db['users'].find_one({'_id': ObjectId(user_id)})
                if user:
                    concept_mastery = user.get('concept_mastery', {})
                    
                    for concept, performance in result['concept_performance'].items():
                        safe_key = sanitize_key(concept)
                        safe_performance = sanitize_value(performance)
                        
                        old_score = concept_mastery.get(safe_key, 0.5)
                        # Exponential moving average
                        new_score = 0.7 * float(old_score) + 0.3 * float(safe_performance)
                        concept_mastery[safe_key] = sanitize_value(new_score)
                    
                    self._db['users'].update_one(
                        {'_id': ObjectId(user_id)},
                        {'$set': {'concept_mastery': concept_mastery}}
                    )
            
            return True
        except Exception as e:
            _safe_print(f"[MongoDB] Error saving quiz result: {str(e)}")
            raise Exception(f"Failed to save result: {str(e)}")
    
    def get_quiz_result(self, user_id: str, quiz_id: str, attempt_id: str) -> Optional[Dict]:
        """Get quiz attempt result with detailed breakdown"""
        if not self._initialized:
            return self._get_demo_result()
        
        try:
            if not ObjectId.is_valid(attempt_id):
                return None
            
            attempt = self._db['attempts'].find_one({'_id': ObjectId(attempt_id)})
            if attempt and 'result' in attempt:
                result = attempt['result']
                # Restore 'results' from 'details' if available
                if 'details' in result and 'results' not in result:
                    result['results'] = result['details']
                return result
            return attempt
        except Exception as e:
            print(f"Error getting result: {e}")
            return None
    
    def get_quiz_history(self, user_id: str) -> List[Dict]:
        """Get user's quiz history"""
        if not self._initialized:
            return []
        
        try:
            history = list(self._db['attempts'].find({'user_id': user_id}))
            
            for h in history:
                h['id'] = str(h['_id'])
                del h['_id']
            
            return history
        except Exception as e:
            _safe_print(f"[MongoDB] Error getting history: {e}")
            return []
    
    def get_recent_quizzes(self, user_id: str, limit: int = 5) -> List[Dict]:
        """Get user's recent quiz attempts"""
        history = self.get_quiz_history(user_id)
        history.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return history[:limit]
    
    def add_to_quiz_history(self, user_id: str, history_entry: Dict) -> bool:
        """Add a quiz attempt to user's quiz history"""
        if not self._initialized:
            return True
        
        try:
            # Add timestamp if not present
            if 'timestamp' not in history_entry:
                history_entry['timestamp'] = self.get_timestamp()
            
            # Update user document with quiz history entry
            if not ObjectId.is_valid(user_id):
                raise Exception("Invalid user ID")
            
            result = self._db['users'].update_one(
                {'_id': ObjectId(user_id)},
                {
                    '$push': {
                        'quiz_history': history_entry
                    }
                }
            )
            
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            _safe_print(f"[MongoDB] Error adding to quiz history: {e}")
            return False
    
    # ===================== ANALYTICS =====================
    
    def get_quiz_statistics(self, quiz_id: str) -> Dict:
        """Get statistics for a quiz"""
        if not self._initialized:
            return {
                'total_attempts': 5,
                'average_score': 75.5,
                'completion_rate': 0.85
            }
        
        try:
            attempts = list(self._db['attempts'].find({
                'quiz_id': quiz_id,
                'status': 'completed'
            }))
            
            if not attempts:
                return {'total_attempts': 0, 'average_score': 0}
            
            scores = [a.get('result', {}).get('score', 0) for a in attempts]
            
            return {
                'total_attempts': len(attempts),
                'average_score': sum(scores) / len(scores) if scores else 0,
                'highest_score': max(scores) if scores else 0,
                'lowest_score': min(scores) if scores else 0
            }
        except Exception as e:
            _safe_print(f"[MongoDB] Error getting statistics: {e}")
            return {}
    
    def get_instructor_analytics(self, user_id: str) -> Dict:
        """Get aggregated analytics for instructor"""
        quizzes = self.get_instructor_quizzes(user_id)
        
        total_attempts = 0
        total_score = 0
        quiz_stats = []
        
        for quiz in quizzes:
            stats = self.get_quiz_statistics(quiz['id'])
            quiz_stats.append({**quiz, **stats})
            total_attempts += stats.get('total_attempts', 0)
            total_score += stats.get('average_score', 0) * stats.get('total_attempts', 0)
        
        return {
            'total_quizzes': len(quizzes),
            'total_attempts': total_attempts,
            'overall_average': total_score / total_attempts if total_attempts > 0 else 0,
            'quiz_stats': quiz_stats
        }
    
    def get_learning_curve(self, user_id: str) -> List[Dict]:
        """Get learning progress over time"""
        history = self.get_quiz_history(user_id)
        history.sort(key=lambda x: x.get('created_at', ''))
        
        return [
            {'date': h.get('created_at', ''), 'score': h.get('result', {}).get('score', 0)}
            for h in history
        ]
    
    def get_user_knowledge_graph(self, user_id: str) -> Dict:
        """Get knowledge graph for user's studied concepts"""
        if not self._initialized:
            return self._get_demo_knowledge_graph()
        
        try:
            user = self._db['users'].find_one({'_id': ObjectId(user_id)})
            if not user:
                return {'nodes': [], 'edges': []}
            
            concept_mastery = user.get('concept_mastery', {})
            nodes = [{'id': c, 'label': c, 'mastery': m} 
                    for c, m in concept_mastery.items()]
            
            return {'nodes': nodes, 'edges': []}
        except Exception as e:
            _safe_print(f"[MongoDB] Error getting knowledge graph: {e}")
            return {'nodes': [], 'edges': []}
    
    # ===================== DEMO DATA =====================
    
    def _get_demo_user_data(self) -> Dict:
        """Get demo user data for testing without MongoDB"""
        return {
            'id': 'demo_user_1',
            'name': 'Demo User',
            'email': 'demo@example.com',
            'role': 'student',
            'concept_mastery': {
                'Search Algorithms': 0.8,
                'BFS': 0.75,
                'DFS': 0.65,
                'A* Search': 0.45,
                'Heuristics': 0.5,
                'Knowledge Graphs': 0.3,
                'Machine Learning': 0.6
            },
            'quiz_history': []
        }
    
    def _get_demo_document(self) -> Dict:
        """Get demo document for testing"""
        return {
            'id': 'demo_doc_1',
            'filename': 'Introduction_to_AI.pdf',
            'concepts': ['Search Algorithms', 'BFS', 'DFS', 'A* Search', 
                        'Heuristics', 'Knowledge Graphs', 'Machine Learning'],
            'knowledge_graph': self._get_demo_knowledge_graph()
        }
    
    def _get_demo_quiz(self) -> Dict:
        """Get demo quiz for testing"""
        return {
            'id': 'demo_quiz_1',
            'name': 'Introduction to AI - Chapter 3',
            'num_questions': 10,
            'is_adaptive': True,
            'is_password_protected': False,
            'difficulty': 'mixed'
        }
    
    def _get_demo_questions(self) -> List[Dict]:
        """Get demo questions for testing"""
        return [
            {
                'id': 'q1',
                'text': 'Which search algorithm guarantees the shortest path in an unweighted graph?',
                'type': 'mcq',
                'options': ['BFS', 'DFS', 'A*', 'Hill Climbing'],
                'correct_answer': 'BFS',
                'concept': 'Search Algorithms',
                'difficulty': 'medium'
            },
            {
                'id': 'q2',
                'text': 'DFS uses a stack data structure for traversal.',
                'type': 'true_false',
                'correct_answer': 'True',
                'concept': 'DFS',
                'difficulty': 'easy'
            },
            {
                'id': 'q3',
                'text': 'What is a heuristic in the context of search algorithms?',
                'type': 'short_answer',
                'correct_answer': 'A function that estimates the cost to reach the goal',
                'concept': 'Heuristics',
                'difficulty': 'medium'
            }
        ]
    
    def _get_demo_result(self) -> Dict:
        """Get demo result for testing"""
        return {
            'score': 80,
            'total_questions': 5,
            'correct': 4,
            'time_taken': 300,
            'concept_performance': {
                'Search Algorithms': 1.0,
                'BFS': 0.5,
                'DFS': 1.0,
                'Heuristics': 0.75
            }
        }
    
    def _get_demo_knowledge_graph(self) -> Dict:
        """Get demo knowledge graph for testing"""
        return {
            'nodes': [
                {'id': 'AI', 'label': 'Artificial Intelligence'},
                {'id': 'Search', 'label': 'Search Algorithms'},
                {'id': 'BFS', 'label': 'Breadth-First Search'},
                {'id': 'DFS', 'label': 'Depth-First Search'},
                {'id': 'A*', 'label': 'A* Search'},
                {'id': 'Heuristics', 'label': 'Heuristics'},
                {'id': 'KG', 'label': 'Knowledge Graphs'}
            ],
            'edges': [
                {'from': 'AI', 'to': 'Search'},
                {'from': 'Search', 'to': 'BFS'},
                {'from': 'Search', 'to': 'DFS'},
                {'from': 'Search', 'to': 'A*'},
                {'from': 'A*', 'to': 'Heuristics'},
                {'from': 'AI', 'to': 'KG'}
            ]
        }
