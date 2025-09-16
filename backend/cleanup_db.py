from database import db
from bson import ObjectId

def cleanup_invalid_videos():
    """Remove videos with null or missing file_path"""
    
    # Find videos with null or missing file_path
    invalid_videos = list(db.videos.find({
        '$or': [
            {'file_path': None},
            {'file_path': {'$exists': False}},
            {'file_path': ''}
        ]
    }))
    
    print(f"Found {len(invalid_videos)} invalid videos:")
    
    for video in invalid_videos:
        print(f"  - {video['_id']}: {video.get('filename', 'No filename')} (file_path: {video.get('file_path', 'Missing')})")
    
    if len(invalid_videos) > 0:
        response = input("Do you want to delete these invalid videos? (y/N): ")
        if response.lower() == 'y':
            # Delete invalid videos and their violations
            for video in invalid_videos:
                video_id = video['_id']
                
                # Delete associated violations
                violations_deleted = db.violations.delete_many({'video_id': video_id})
                
                # Delete the video
                db.videos.delete_one({'_id': video_id})
                
                print(f"  ✅ Deleted video {video_id} and {violations_deleted.deleted_count} violations")
            
            print(f"Cleanup complete! Deleted {len(invalid_videos)} invalid videos.")
        else:
            print("Cleanup cancelled.")
    else:
        print("No invalid videos found!")

if __name__ == "__main__":
    cleanup_invalid_videos()