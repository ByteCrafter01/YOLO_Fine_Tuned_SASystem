#!/usr/bin/env python3

import os
import sys
from backend.app import app, socketio

def check_dependencies():
    """Check if required files and dependencies exist"""
    required_dirs = [
        'uploads/videos',
        'uploads/violations', 
        'backend/models'
    ]
    
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            print(f"✓ Created directory: {dir_path}")
    
    # Check for YOLO model
    model_path = 'backend/models/best.pt'
    if not os.path.exists(model_path):
        print(f"⚠️  YOLO model not found at {model_path}")
        print("   Please place your trained YOLO model (best.pt) in the backend/models/ directory")
        print("   The system will still work with OpenAI Vision API if configured")
    else:
        print(f"✓ YOLO model found: {model_path}")

def configure_app_for_development():
    """Configure Flask app for development with auto-reload for static files"""
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable static file caching
    app.config['TEMPLATES_AUTO_RELOAD'] = True   # Auto-reload templates
    app.jinja_env.auto_reload = True             # Auto-reload Jinja templates
    
    # Additional debug configuration
    if app.debug:
        app.config['EXPLAIN_TEMPLATE_LOADING'] = True

def main():
    print("🚀 PPE Detection System")
    print("=" * 50)
    
    # Check dependencies
    check_dependencies()
    
    # Configure app for development
    configure_app_for_development()
    
    print("\n🔧 System Configuration:")
    print("   Frontend: React-like vanilla JS with WebSocket")
    print("   Backend: Flask + SocketIO + MongoDB")
    print("   AI Models: YOLO + OpenAI Vision")
    print("   Database: MongoDB (localhost:27017)")
    print("   Debug Mode: ENABLED (auto-reload for CSS/JS)")
    
    print("\n🌐 Available Endpoints:")
    print("   Dashboard: http://localhost:5000")
    print("   Live Stream: http://localhost:5000/live-stream")
    print("   Video Grid: http://localhost:5000/video-grid")
    print("   API: http://localhost:5000/api/")
    
    print("\n📋 Features:")
    print("   ✓ WebSocket live streaming")
    print("   ✓ Real-time PPE detection")
    print("   ✓ Interactive query system")
    print("   ✓ Multi-video grid selection")
    print("   ✓ Automated video processing")
    print("   ✓ Violation timeline & screenshots")
    
    print("\n⚙️  Make sure MongoDB is running:")
    print("   mongod --dbpath /path/to/your/db")
    
    print("\n💡 Development Tips:")
    print("   - CSS/JS changes will auto-reload")
    print("   - Use Ctrl+C to stop the server")
    print("   - Check browser console for errors")
    
    print("\n" + "=" * 50)
    print("🚀 Starting server...")
    
    try:
        # Use socketio.run() instead of app.run() since you have WebSocket functionality
        socketio.run(
            app, 
            debug=False, 
            host='0.0.0.0', 
            port=5000,
            use_reloader=False,      # Auto-restart on Python file changes
            reloader_options={
                'extra_files': [    # Watch additional files for changes
                    'frontend/static/css/styles.css',
                    'frontend/static/js/live-stream.js',
                    'frontend/static/js/video-detail.js',
                    'frontend/static/js/video-grid.js',
                ]
            },
            log_output=True
        )
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down PPE Detection System...")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        print("Make sure MongoDB is running and all dependencies are installed.")
        sys.exit(1)

if __name__ == '__main__':
    main()