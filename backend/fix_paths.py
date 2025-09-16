from database import db
import os

def fix_existing_paths():
    """Fix existing video paths in database"""
    videos = list(db.videos.find())
    
    for video in videos:
        if 'file_path' in video:
            old_path = video['file_path']
            # Normalize and convert to forward slashes
            new_path = os.path.normpath(old_path).replace(os.sep, '/')
            
            if old_path != new_path:
                print(f"Fixing: '{old_path}' -> '{new_path}'")
                db.videos.update_one(
                    {'_id': video['_id']},
                    {'$set': {'file_path': new_path}}
                )

if __name__ == "__main__":
    fix_existing_paths()
    print("Path fixing complete!")