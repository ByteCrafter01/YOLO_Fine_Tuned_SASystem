from pymongo import MongoClient
from datetime import datetime, timedelta
import os
from bson import ObjectId
from dotenv import load_dotenv
import bcrypt
import jwt
import re

load_dotenv()

class Database:
    def __init__(self):
        self.connection_string = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        self.db_name = os.getenv('DB_NAME', 'ppe_detection')
        self.jwt_secret = os.getenv('JWT_SECRET_KEY', 'your-super-secret-jwt-key-change-this')
        
        try:
            self.client = MongoClient(self.connection_string)
            
            self.client.admin.command('ping')
            print(f"✅ Successfully connected to MongoDB Atlas!")
            print(f"Database: {self.db_name}")
            
        except Exception as e:
            print(f"❌ Failed to connect to MongoDB Atlas: {e}")
            print("🔄 Falling back to local MongoDB...")
            
            local_uri = os.getenv('LOCAL_MONGODB_URI', 'mongodb://localhost:27017/')
            try:
                self.client = MongoClient(local_uri)
                self.client.admin.command('ping')
                print(f"✅ Connected to local MongoDB")
            except Exception as local_e:
                print(f"❌ Failed to connect to local MongoDB: {local_e}")
                raise Exception("Could not connect to any MongoDB instance")
        
        self.db = self.client[self.db_name]
        self.videos = self.db.videos
        self.violations = self.db.violations
        self.live_sessions = self.db.live_sessions
        self.users = self.db.users  # New users collection
        
        self._create_indexes()
    
    def _create_indexes(self):
        """Create database indexes for better performance"""
        try:
            self.videos.create_index([("upload_time", -1)])
            self.videos.create_index([("processed", 1)])
            
            self.violations.create_index([("video_id", 1), ("timestamp", 1)])
            self.violations.create_index([("detected_at", -1)])
            
            self.live_sessions.create_index([("session_id", 1), ("active", 1)])
            self.live_sessions.create_index([("started_at", -1)])
            
            # User indexes
            self.users.create_index([("email", 1)], unique=True)
            self.users.create_index([("created_at", -1)])
            
            print("✅ Database indexes created successfully")
        except Exception as e:
            print(f"⚠️ Warning: Could not create indexes: {e}")
    
    def test_connection(self):
        """Test database connection and return status"""
        try:
            collections = self.db.list_collection_names()
            server_info = self.client.server_info()
            
            return {
                'status': 'connected',
                'server_version': server_info.get('version', 'Unknown'),
                'collections': collections,
                'database': self.db_name
            }
        except Exception as e:
            return {
                'status': 'disconnected',
                'error': str(e)
            }
    
    # ============ USER AUTHENTICATION METHODS ============
    
    def validate_payoda_email(self, email):
        """Validate that email belongs to @payoda.com domain"""
        email = email.lower().strip()
        email_pattern = r'^[a-zA-Z0-9._%+-]+@payoda\.com$'
        return re.match(email_pattern, email) is not None
    
    def hash_password(self, password):
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt)
    
    def verify_password(self, password, hashed_password):
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password)
    
    def create_user(self, email, password, full_name=None):
        """Register a new user with @payoda.com email validation"""
        email = email.lower().strip()
        
        # Validate email domain
        if not self.validate_payoda_email(email):
            return {
                'success': False,
                'error': 'Only @payoda.com email addresses are allowed to register'
            }
        
        # Check if user already exists
        if self.users.find_one({'email': email}):
            return {
                'success': False,
                'error': 'User with this email already exists'
            }
        
        # Validate password strength
        if len(password) < 6:
            return {
                'success': False,
                'error': 'Password must be at least 6 characters long'
            }
        
        # Hash password and create user
        hashed_password = self.hash_password(password)
        
        user_doc = {
            'email': email,
            'password': hashed_password,
            'full_name': full_name or email.split('@')[0].title(),
            'created_at': datetime.now(),
            'last_login': None,
            'is_active': True
        }
        
        try:
            result = self.users.insert_one(user_doc)
            return {
                'success': True,
                'user_id': str(result.inserted_id),
                'message': 'User registered successfully'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Registration failed: {str(e)}'
            }
    
    def authenticate_user(self, email, password):
        """Authenticate user and return user data if valid"""
        email = email.lower().strip()
        
        user = self.users.find_one({'email': email, 'is_active': True})
        
        if not user:
            return {
                'success': False,
                'error': 'Invalid email or password'
            }
        
        if self.verify_password(password, user['password']):
            # Update last login
            self.users.update_one(
                {'_id': user['_id']},
                {'$set': {'last_login': datetime.now()}}
            )
            
            return {
                'success': True,
                'user': {
                    'user_id': str(user['_id']),
                    'email': user['email'],
                    'full_name': user['full_name'],
                    'created_at': user['created_at']
                }
            }
        else:
            return {
                'success': False,
                'error': 'Invalid email or password'
            }
    
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        try:
            user = self.users.find_one({'_id': ObjectId(user_id), 'is_active': True})
            if user:
                return {
                    'user_id': str(user['_id']),
                    'email': user['email'],
                    'full_name': user['full_name'],
                    'created_at': user['created_at'],
                    'last_login': user.get('last_login')
                }
            return None
        except:
            return None
    
    def generate_jwt_token(self, user_data):
        """Generate JWT token for authenticated user"""
        payload = {
            'user_id': user_data['user_id'],
            'email': user_data['email'],
            'full_name': user_data['full_name'],
            'exp': datetime.utcnow() + timedelta(hours=24),  # Token expires in 24 hours
            'iat': datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')
        return token
    
    def verify_jwt_token(self, token):
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            
            # Verify user still exists and is active
            user = self.get_user_by_id(payload['user_id'])
            if not user:
                return None
                
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def get_all_users(self):
        """Get all registered users (admin function)"""
        users = list(self.users.find({'is_active': True}, {'password': 0}).sort('created_at', -1))
        for user in users:
            user['_id'] = str(user['_id'])
        return users
    
    # ============ EXISTING VIDEO METHODS ============
    
    def save_video(self, filename, file_path, user_id=None):
        """Save video with optional user tracking"""
        # Always normalize and convert to forward slashes for storage
        normalized_path = os.path.normpath(file_path)
        # Convert to forward slashes for consistent storage
        storage_path = normalized_path.replace(os.sep, '/')
        
        print(f"🐛 DEBUG: Original file_path: '{file_path}'")
        print(f"🐛 DEBUG: Normalized: '{normalized_path}'")
        print(f"🐛 DEBUG: Storage path: '{storage_path}'")
        
        video_doc = {
            'filename': filename,
            'file_path': storage_path,  # Store with forward slashes
            'upload_time': datetime.now(),
            'processed': False,
            'total_violations': 0,
            'summary': '',
            'duration': 0,
            'frame_count': 0,
            'uploaded_by': ObjectId(user_id) if user_id else None
        }
        result = self.videos.insert_one(video_doc)
        return str(result.inserted_id)
    
    def update_video_processing(self, video_id, summary, total_violations, duration=0, frame_count=0):
        self.videos.update_one(
            {'_id': ObjectId(video_id)},
            {
                '$set': {
                    'processed': True,
                    'summary': summary,
                    'total_violations': total_violations,
                    'duration': duration,
                    'frame_count': frame_count,
                    'processed_at': datetime.now()
                }
            }
        )
    
    def get_all_videos(self):
        videos = list(self.videos.find().sort('upload_time', -1))
        for video in videos:
            video['_id'] = str(video['_id'])
            if video.get('uploaded_by'):
                video['uploaded_by'] = str(video['uploaded_by'])
            
            # Convert stored path to proper OS path separators
            if 'file_path' in video and video['file_path'] is not None:
                stored_path = video['file_path']
                video['file_path'] = os.path.normpath(stored_path)
            else:
                # Handle missing or None file_path
                video['file_path'] = ""
                print(f"⚠️ Warning: Video {video['_id']} has no file_path")
        
        return videos
    
    def get_video(self, video_id):
        video = self.videos.find_one({'_id': ObjectId(video_id)})
        if video:
            video['_id'] = str(video['_id'])
            if video.get('uploaded_by'):
                video['uploaded_by'] = str(video['uploaded_by'])
            
            # Convert stored path to proper OS path separators
            if 'file_path' in video and video['file_path'] is not None:
                stored_path = video['file_path']
                video['file_path'] = os.path.normpath(stored_path)
                print(f"DEBUG get_video: stored='{stored_path}', normalized='{video['file_path']}'")
            else:
                # Handle missing or None file_path
                video['file_path'] = ""
                print(f"⚠️ Warning: Video {video_id} has no file_path")
        
        return video
        
    def delete_video(self, video_id):
        """Delete video and all associated violations"""
        try:
            self.violations.delete_many({'video_id': ObjectId(video_id)})
        
            result = self.videos.delete_one({'_id': ObjectId(video_id)})
        
            return result.deleted_count > 0
        
        except Exception as e:
            print(f"Error deleting video {video_id}: {e}")
            return False
    
    def save_violation(self, video_id, timestamp, violation_type, screenshot_path, bbox_data=None):
        violation_doc = {
            'video_id': ObjectId(video_id),
            'timestamp': timestamp,
            'violation_type': violation_type,
            'screenshot_path': screenshot_path,
            'bbox_data': bbox_data or {},
            'detected_at': datetime.now()
        }
        result = self.violations.insert_one(violation_doc)
        return str(result.inserted_id)
    
    def get_video_violations(self, video_id):
        violations = list(self.violations.find({'video_id': ObjectId(video_id)}).sort('timestamp', 1))
        for violation in violations:
            violation['_id'] = str(violation['_id'])
            violation['video_id'] = str(violation['video_id'])
        return violations
    
    def create_live_session(self, session_id, user_id=None):
        """Create live session with optional user tracking"""
        session_doc = {
            'session_id': session_id,
            'started_at': datetime.now(),
            'active': True,
            'current_frame_data': {},
            'query_history': [],
            'violation_count': 0,
            'started_by': ObjectId(user_id) if user_id else None
        }
        result = self.live_sessions.insert_one(session_doc)
        return str(result.inserted_id)
    
    def update_live_session(self, session_id, frame_data):
        self.live_sessions.update_one(
            {'session_id': session_id, 'active': True},
            {
                '$set': {
                    'current_frame_data': frame_data,
                    'last_updated': datetime.now()
                }
            }
        )
    
    def add_query_to_session(self, session_id, query, response):
        self.live_sessions.update_one(
            {'session_id': session_id, 'active': True},
            {
                '$push': {
                    'query_history': {
                        'query': query,
                        'response': response,
                        'timestamp': datetime.now()
                    }
                }
            }
        )
    
    def close_live_session(self, session_id):
        self.live_sessions.update_one(
            {'session_id': session_id},
            {
                '$set': {
                    'active': False,
                    'ended_at': datetime.now()
                }
            }
        )
    
    def get_live_session(self, session_id):
        session = self.live_sessions.find_one({'session_id': session_id, 'active': True})
        if session:
            session['_id'] = str(session['_id'])
            if session.get('started_by'):
                session['started_by'] = str(session['started_by'])
        return session

db = Database()