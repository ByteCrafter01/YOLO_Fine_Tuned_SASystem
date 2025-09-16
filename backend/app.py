import torch_patch 
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, disconnect
from flask_cors import CORS
import os
import threading
import time
import cv2
from werkzeug.utils import secure_filename
import uuid
from database import db
from video_processor import processor
from datetime import datetime
from functools import wraps
import jwt
from flask import redirect

app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/static')
app.config['UPLOAD_FOLDER'] = os.path.join('uploads', 'videos')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

if app.debug:
    app.config['EXPLAIN_TEMPLATE_LOADING'] = True

@app.after_request
def add_cache_control(response):
    """Add cache control headers for development"""
    if app.debug:
        if request.endpoint == 'static':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
    return response

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

os.makedirs(os.path.join('uploads', 'videos'), exist_ok=True)
os.makedirs(os.path.join('uploads', 'violations'), exist_ok=True)
live_sessions = {}

# ============ AUTHENTICATION DECORATORS ============

def token_required(f):
    """Decorator to require JWT token for API routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # Bearer <token>
            except IndexError:
                return jsonify({'error': 'Invalid authorization header format'}), 401
        
        if not token:
            return jsonify({'error': 'Authentication token is missing'}), 401
        
        try:
            current_user = db.verify_jwt_token(token)
            if not current_user:
                return jsonify({'error': 'Invalid or expired token'}), 401
        except Exception as e:
            return jsonify({'error': 'Token verification failed'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated

def auth_required_page(f):
    """Decorator to require authentication for page routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check for token in various places
        token = None
        
        # First check Authorization header (for API-style requests)
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # Bearer <token>
            except IndexError:
                pass
        
        # Check for token in cookies as backup
        if not token:
            token = request.cookies.get('ppe_token')
        
        # Check for token in query parameter (for development/testing)
        if not token:
            token = request.args.get('token')
        
        if not token:
            # No token found, redirect to login
            return redirect('/login')
        
        try:
            current_user = db.verify_jwt_token(token)
            if not current_user:
                # Invalid token, redirect to login
                return redirect('/login')
            
            # Token is valid, proceed to the route
            # Optionally, you can make current_user available in the template
            return f(*args, **kwargs)
            
        except Exception as e:
            # Token verification failed, redirect to login
            return redirect('/login')
    
    return decorated

# ============ AUTHENTICATION ROUTES ============

@app.route('/login')
def login_page():
    """Serve login page"""
    return render_template('login.html')

@app.route('/register')
def register_page():
    """Serve registration page"""
    return render_template('register.html')

@app.route('/logout')
def logout():
    """Logout route to clear tokens and redirect to login"""
    response = redirect('/login')
    response.set_cookie('ppe_token', '', expires=0) 
    return response

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register new user with @payoda.com email"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    
    result = db.create_user(email, password, full_name)
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': result['message'],
            'user_id': result['user_id']
        }), 201
    else:
        return jsonify({'error': result['error']}), 400

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Authenticate user and return JWT token"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    
    auth_result = db.authenticate_user(email, password)
    
    if auth_result['success']:
        user_data = auth_result['user']
        token = db.generate_jwt_token(user_data)
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'token': token,
            'user': {
                'user_id': user_data['user_id'],
                'email': user_data['email'],
                'full_name': user_data['full_name']
            }
        }), 200
    else:
        return jsonify({'error': auth_result['error']}), 401

@app.route('/api/auth/verify', methods=['GET'])
@token_required
def verify_token(current_user):
    """Verify if token is still valid"""
    return jsonify({
        'valid': True,
        'user': {
            'user_id': current_user['user_id'],
            'email': current_user['email'],
            'full_name': current_user['full_name']
        }
    }), 200

@app.route('/api/auth/users', methods=['GET'])
@token_required
def get_all_users(current_user):
    """Get all registered users (admin endpoint)"""
    users = db.get_all_users()
    return jsonify({'users': users}), 200

# ============ PROTECTED PAGE ROUTES ============

@app.route('/')
@auth_required_page
def dashboard():
    return render_template('dashboard.html')

@app.route('/live-stream')
@auth_required_page
def live_stream():
    return render_template('live-stream.html')

@app.route('/video-grid')
@auth_required_page
def video_grid():
    return render_template('video-grid.html')

@app.route('/video-detail/<video_id>')
@auth_required_page
def video_detail(video_id):
    return render_template('video-detail.html', video_id=video_id)

# ============ PROTECTED API ROUTES ============

@app.route('/api/videos', methods=['GET'])
@token_required
def get_videos(current_user):
    videos = db.get_all_videos()
    return jsonify(videos)

@app.route('/api/video/<video_id>', methods=['GET'])
@token_required
def get_video(current_user, video_id):
    video = db.get_video(video_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    violations = db.get_video_violations(video_id)
    return jsonify({
        'video': video,
        'violations': violations
    })

@app.route('/api/upload', methods=['POST'])
@token_required
def upload_video(current_user):
    if 'video' not in request.files:
        return jsonify({'error': 'No video file'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file:
        filename = secure_filename(file.filename)
        # Use os.path.join for proper path construction
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        # Normalize the path
        file_path = os.path.normpath(file_path)
        
        file.save(file_path)
        
        # Verify file was saved
        if not os.path.exists(file_path):
            return jsonify({'error': 'Failed to save video file'}), 500
        
        # Save video with user tracking
        video_id = db.save_video(filename, file_path, current_user['user_id'])
        
        processor.process_video_async(video_id, file_path)
        
        return jsonify({
            'success': True,
            'video_id': video_id,
            'message': 'Video uploaded and processing started',
            'uploaded_by': current_user['full_name']
        })
        
@app.route('/api/download/<video_id>', methods=['GET'])
@token_required
def download_video(current_user, video_id):
    try:
        video = db.get_video(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        file_path = video['file_path']
        if not os.path.exists(file_path):
            return jsonify({'error': 'Video file not found on server'}), 404
        
        filename = video['filename']
        directory = os.path.dirname(file_path)
        
        return send_from_directory(
            directory, 
            os.path.basename(file_path), 
            as_attachment=True, 
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/api/videos/<video_id>', methods=['DELETE'])
@token_required
def delete_video(current_user, video_id):
    try:
        video = db.get_video(video_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404
        
        file_path = video['file_path']
        if os.path.exists(file_path):
            os.remove(file_path)
        
        success = db.delete_video(video_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Video deleted successfully'})
        else:
            return jsonify({'error': 'Failed to delete video from database'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500

@app.route('/api/violations/<path:filepath>')
@token_required
def serve_violation_screenshot(current_user, filepath):
    return send_from_directory('uploads/violations', filepath)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Public health check endpoint"""
    db_status = db.test_connection()
    
    return jsonify({
        'status': 'healthy' if db_status['status'] == 'connected' else 'unhealthy',
        'database': db_status,
        'timestamp': datetime.now().isoformat(),
        'auth_enabled': True
    })

# ============ SOCKET.IO AUTHENTICATION ============

def authenticate_socket(auth_data):
    """Authenticate Socket.IO connection using JWT token"""
    if not auth_data or 'token' not in auth_data:
        return None
    
    token = auth_data['token']
    user_data = db.verify_jwt_token(token)
    return user_data

@socketio.on('connect')
def handle_connect(auth):
    print(f'Client attempting connection: {request.sid}')
    
    # Authenticate the connection
    current_user = authenticate_socket(auth)
    if not current_user:
        print(f'❌ Unauthorized connection attempt: {request.sid}')
        disconnect()
        return False
    
    print(f'✅ Client authenticated: {current_user["email"]} ({request.sid})')
    emit('connected', {
        'status': 'Connected to PPE Detection System',
        'user': current_user['full_name']
    })

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}')
    if request.sid in live_sessions:
        del live_sessions[request.sid]

@socketio.on('start_live_stream')
def handle_start_live_stream(data):
    # Get user from token in the session (this is a simplified approach)
    auth_data = data.get('auth', {})
    current_user = authenticate_socket(auth_data)
    
    if not current_user:
        emit('error', {'message': 'Authentication required for live streaming'})
        return
    
    session_id = str(uuid.uuid4())
    video_source = data.get('video_source', 'webcam')
    
    # Create live session with user tracking
    db.create_live_session(session_id, current_user['user_id'])
    
    live_sessions[request.sid] = {
        'session_id': session_id,
        'video_source': video_source,
        'active': True,
        'frame_count': 0,
        'user_id': current_user['user_id']
    }
    
    emit('live_session_started', {
        'session_id': session_id,
        'started_by': current_user['full_name']
    })
    
    if video_source == 'webcam':
        threading.Thread(
            target=webcam_live_stream,
            args=(request.sid, session_id),
            daemon=True
        ).start()
    else:
        threading.Thread(
            target=simulate_live_stream,
            args=(request.sid, session_id, video_source),
            daemon=True
        ).start()

@socketio.on('query_live_stream')
def handle_query(data):
    session_id = data.get('session_id')
    query = data.get('query', '').lower()
    
    if request.sid not in live_sessions:
        emit('query_response', {'error': 'No active live session'})
        return
    
    session = live_sessions[request.sid]
    
    db_session = db.get_live_session(session_id)
    if not db_session:
        emit('query_response', {'error': 'Session not found'})
        return
    
    frame_data = db_session.get('current_frame_data', {})
    response = process_query(query, frame_data)
    
    db.add_query_to_session(session_id, query, response)
    
    emit('query_response', {
        'query': query,
        'response': response,
        'timestamp': time.time()
    })

@socketio.on('stop_live_stream')
def handle_stop_live_stream(data):
    session_id = data.get('session_id')
    
    if request.sid in live_sessions:
        live_sessions[request.sid]['active'] = False
        del live_sessions[request.sid]
    
    if session_id:
        db.close_live_session(session_id)
    
    emit('live_session_stopped', {'message': 'Live stream stopped'})

# ============ LIVE STREAMING FUNCTIONS (UNCHANGED) ============

def simulate_live_stream(client_id, session_id, video_path):
    """Simulate live streaming from uploaded video"""
    if not os.path.exists(video_path):
        print(f"Video file not found: {video_path}")
        return
    
    cap = cv2.VideoCapture(video_path)
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
    frame_delay = 1.0 / fps
    
    frame_count = 0
    
    while client_id in live_sessions and live_sessions[client_id]['active']:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        
        try:
            # Use the correct method name
            analysis = processor.analyze_raw_frame(frame)
            
            db.update_live_session(session_id, analysis)
            
            # Encode frame for streaming
            frame_base64 = processor.encode_frame(frame)
            
            socketio.emit('live_frame', {
                'frame': frame_base64,
                'analysis': analysis,
                'frame_count': frame_count
            }, room=client_id)
            
            if analysis['violations']:
                socketio.emit('violation_alert', {
                    'violations': analysis['violations'],
                    'timestamp': time.time()
                }, room=client_id)
            
            frame_count += 1
            time.sleep(frame_delay)
            
        except Exception as e:
            print(f"Streaming error: {e}")
            break
    
    cap.release()

def webcam_live_stream(client_id, session_id):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Cannot access webcam")
        return
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 20)

    filename = f"webcam_{session_id}.mp4"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    fps = 20.0
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Recording webcam: {frame_width}x{frame_height} at {fps}fps")
    out = cv2.VideoWriter(file_path, fourcc, fps, (frame_width, frame_height))
    
    if not out.isOpened():
        print("Error: VideoWriter could not be opened")
        cap.release()
        return

    frame_count = 0
    start_time = time.time()
    
    print(f"Starting webcam stream for session {session_id}")
    
    while client_id in live_sessions and live_sessions[client_id]['active']:
        ret, frame = cap.read()
        if not ret:
            print("Webcam frame not captured")
            break

        try:
            out.write(frame)
            
            analysis_frame = frame.copy()

            analysis = processor.analyze_raw_frame(analysis_frame)
            frame_base64 = processor.encode_frame(frame)

            db.update_live_session(session_id, analysis)

            socketio.emit('live_frame', {
                'frame': frame_base64,
                'analysis': analysis,
                'frame_count': frame_count
            }, room=client_id)

            if analysis.get('violations'):
                socketio.emit('violation_alert', {
                    'violations': analysis['violations'],
                    'timestamp': time.time()
                }, room=client_id)

            frame_count += 1
            time.sleep(0.05)
            if frame_count % 100 == 0:
                elapsed = time.time() - start_time
                print(f"Recorded {frame_count} frames in {elapsed:.1f}s")
        except Exception as e:
            print(f"Webcam streaming error: {e}")
            break
        
    print(f"Stopping webcam stream. Total frames recorded: {frame_count}")

    cap.release()
    out.release()
    
    time.sleep(0.5)
    
    # Get user_id from live session for video tracking
    user_id = live_sessions.get(client_id, {}).get('user_id')
    
    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        print(f"Video file created: {file_path} ({file_size} bytes)")
        
        if file_size > 1000:
            video_id = db.save_video(filename, file_path, user_id)
            
            def delayed_processing():
                time.sleep(2)
                processor.process_video_async(video_id, file_path)
            
            threading.Thread(target=delayed_processing, daemon=True).start()
            print(f"Webcam session saved as {file_path}, video_id={video_id}")
        else:
            print(f"Warning: Video file too small ({file_size} bytes), might be corrupted")
    else:
        print("Error: Video file was not created")  

def process_query(query, frame_data):
    """Process natural language queries about current frame"""
    query = query.lower().strip()
    
    if not frame_data:
        return "No active video stream data available."
    
    people_count = frame_data.get('people_count', 0)
    violations = frame_data.get('violations', [])
    compliance_status = frame_data.get('compliance_status', 'unknown')
    
    if 'how many people' in query or 'person count' in query:
        return f"Currently detecting {people_count} person(s) in the video stream."
    
    if 'compliance' in query or 'ppe status' in query:
        if compliance_status == 'compliant':
            return f"Current PPE compliance status: COMPLIANT. All {people_count} person(s) have required PPE."
        elif compliance_status == 'non-compliant':
            violation_types = [v['type'] for v in violations]
            return f"PPE VIOLATIONS DETECTED: {', '.join(violation_types)}. {people_count} person(s) visible."
        else:
            return "Unable to determine current PPE compliance status."
    
    if 'violation' in query or 'missing' in query:
        if violations:
            violation_details = []
            for v in violations:
                violation_details.append(f"{v['type']} (affects {v.get('people_affected', 1)} person(s))")
            return f"Current violations: {', '.join(violation_details)}"
        else:
            return "No PPE violations currently detected."
    
    if 'safe' in query or 'safety' in query:
        if not violations:
            return f"Work area appears SAFE. {people_count} person(s) detected with proper PPE compliance."
        else:
            return f"SAFETY CONCERN: {len(violations)} violation(s) detected. Immediate attention required."
    
    if 'hard hat' in query or 'helmet' in query:
        hardhat_violations = [v for v in violations if 'hard hat' in v['type'].lower()]
        if hardhat_violations:
            return f"Hard hat violation detected - {hardhat_violations[0].get('people_affected', 1)} person(s) missing hard hats."
        else:
            return "All visible persons appear to be wearing hard hats."
    
    if 'vest' in query or 'high vis' in query:
        vest_violations = [v for v in violations if 'vest' in v['type'].lower()]
        if vest_violations:
            return f"Safety vest violation detected - {vest_violations[0].get('people_affected', 1)} person(s) missing safety vests."
        else:
            return "All visible persons appear to be wearing safety vests."
    
    if 'status' in query or 'what do you see' in query:
        status_parts = [
            f"People detected: {people_count}",
            f"Compliance status: {compliance_status.upper()}",
            f"Active violations: {len(violations)}"
        ]
        if violations:
            status_parts.append(f"Violation types: {', '.join([v['type'] for v in violations])}")
        
        return " | ".join(status_parts)
    
    return f"Current status: {people_count} person(s) detected, compliance status: {compliance_status}. Try asking about 'PPE status', 'violations', 'person count', or 'safety status'."

if __name__ == '__main__':
    print("🔐 Starting PPE Detection System with JWT Authentication")
    print("📋 Dashboard: http://localhost:5000")
    print("🔑 Login: http://localhost:5000/login")
    print("📝 Register: http://localhost:5000/register")
    print("🗄️ Make sure MongoDB is running on localhost:27017")
    print("✉️ Only @payoda.com emails can register")
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)