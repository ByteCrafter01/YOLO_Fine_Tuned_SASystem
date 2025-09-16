import torch_patch
import cv2
import os
import threading
from datetime import datetime
import base64
import numpy as np
from PIL import Image
import io
import math
from collections import defaultdict, deque
from ultralytics import YOLO
from database import db


class VideoProcessor:
    # Update this path to match your actual model location
    def __init__(self, ppe_model_path="./models/best.pt"):        # Load your fine-tuned PPE model
        self.ppe_model = None
        
        # Load YOLOv8 person detection model for better person detection
        self.person_model = None
        
        self.load_models(ppe_model_path)
        
        # Enhanced tracking parameters
        self.person_tracks = {}
        self.next_person_id = 1
        self.max_track_age = 30  # frames
        self.track_distance_threshold = 100  # pixels
        
        # Temporal consistency parameters for smoother detection
        self.temporal_window = 10  # frames for smoothing
        self.confidence_buffer = defaultdict(lambda: deque(maxlen=self.temporal_window))
        self.violation_history = defaultdict(lambda: deque(maxlen=self.temporal_window))
        
        # Enhanced detection thresholds
        self.person_conf_threshold = 0.5
        self.ppe_conf_threshold = 0.3
        self.min_detection_confidence = 0.4
        
    def load_models(self, ppe_model_path):
        try:
            if os.path.exists(ppe_model_path):
                self.ppe_model = YOLO(ppe_model_path)
                print(f"PPE model loaded: {len(self.ppe_model.names)} classes")
                print(f"PPE Classes: {list(self.ppe_model.names.values())}")
            else:
                print(f"PPE model not found: {ppe_model_path}")
            
            # Load person detection model
            self.person_model = YOLO('yolov8n.pt')  # Pre-trained COCO model
            print("Person detection model loaded")
            
        except Exception as e:
            print(f"Error loading models: {e}")
    
    def calculate_iou(self, box1, box2):
        """Calculate Intersection over Union (IoU) between two boxes"""
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2
        
        intersection_x1 = max(x1_min, x2_min)
        intersection_y1 = max(y1_min, y2_min)
        intersection_x2 = min(x1_max, x2_max)
        intersection_y2 = min(y1_max, y2_max)
        
        if intersection_x1 >= intersection_x2 or intersection_y1 >= intersection_y2:
            return 0
        
        intersection_area = (intersection_x2 - intersection_x1) * (intersection_y2 - intersection_y1)
        box1_area = (x1_max - x1_min) * (y1_max - y1_min)
        box2_area = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = box1_area + box2_area - intersection_area
        
        return intersection_area / union_area if union_area > 0 else 0
    
    def calculate_distance(self, center1, center2):
        """Calculate Euclidean distance between two points"""
        return math.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
    
    def get_bbox_center(self, bbox):
        """Get center point of bounding box"""
        if isinstance(bbox, dict):
            return ((bbox['x1'] + bbox['x2']) / 2, (bbox['y1'] + bbox['y2']) / 2)
        else:
            return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    
    def update_person_tracking(self, people_detections):
        """Update person tracking with improved accuracy"""
        current_tracks = {}
        
        # Update existing tracks
        for person in people_detections:
            person_center = self.get_bbox_center(person['bbox'])
            best_match_id = None
            best_distance = float('inf')
            
            # Find best matching existing track
            for track_id, track_info in self.person_tracks.items():
                track_center = self.get_bbox_center(track_info['bbox'])
                distance = self.calculate_distance(person_center, track_center)
                
                if distance < self.track_distance_threshold and distance < best_distance:
                    best_distance = distance
                    best_match_id = track_id
            
            # Assign track ID
            if best_match_id is not None:
                person['track_id'] = best_match_id
                current_tracks[best_match_id] = person
            else:
                # Create new track
                person['track_id'] = self.next_person_id
                current_tracks[self.next_person_id] = person
                self.next_person_id += 1
        
        # Update tracking data
        self.person_tracks = current_tracks
        
        return people_detections
    
    def is_ppe_near_person(self, person_bbox, ppe_bbox, iou_threshold=0.08):
        """Enhanced PPE-person association with better logic"""
        
        # Convert bbox format if needed
        if isinstance(person_bbox, dict):
            person_box = [person_bbox['x1'], person_bbox['y1'], person_bbox['x2'], person_bbox['y2']]
        else:
            person_box = person_bbox
            
        if isinstance(ppe_bbox, dict):
            ppe_box = [ppe_bbox['x1'], ppe_bbox['y1'], ppe_bbox['x2'], ppe_bbox['y2']]
        else:
            ppe_box = ppe_bbox
        
        # Check IoU overlap first
        iou = self.calculate_iou(person_box, ppe_box)
        if iou > iou_threshold:
            return True, iou * 2  # Higher weight for direct overlap
        
        # Enhanced proximity check
        person_center = self.get_bbox_center(person_box)
        ppe_center = self.get_bbox_center(ppe_box)
        person_width = person_box[2] - person_box[0]
        person_height = person_box[3] - person_box[1]
        
        distance = self.calculate_distance(person_center, ppe_center)
        
        # Dynamic threshold based on person size
        proximity_threshold = max(person_width, person_height) * 0.6
        
        if distance < proximity_threshold:
            # Calculate match score based on distance
            match_score = 1.0 - (distance / proximity_threshold)
            return True, match_score
        
        return False, 0
    
    def apply_temporal_smoothing(self, people_detections):
        """Apply temporal smoothing to reduce flickering violations"""
        
        for person in people_detections:
            track_id = person['track_id']
            
            # Update confidence buffers
            self.confidence_buffer[f"{track_id}_helmet"].append(1.0 if person['has_helmet'] else 0.0)
            self.confidence_buffer[f"{track_id}_vest"].append(1.0 if person['has_vest'] else 0.0)
            
            # Calculate smoothed confidence
            helmet_confidence = np.mean(list(self.confidence_buffer[f"{track_id}_helmet"]))
            vest_confidence = np.mean(list(self.confidence_buffer[f"{track_id}_vest"]))
            
            # Apply smoothed results with hysteresis
            helmet_threshold = 0.4
            vest_threshold = 0.4
            
            person['has_helmet_smoothed'] = bool(helmet_confidence > helmet_threshold)
            person['has_vest_smoothed'] = bool(vest_confidence > vest_threshold)
            person['violation_smoothed'] = bool(not (person['has_helmet_smoothed'] and person['has_vest_smoothed']))
                        # Store violation history for statistics
            self.violation_history[track_id].append(person['violation_smoothed'])
        
        return people_detections
    
    def process_video_async(self, video_id, video_path):
        """Process video in background thread"""
        thread = threading.Thread(target=self.process_video, args=(video_id, video_path))
        thread.daemon = True
        thread.start()
    
    def process_video(self, video_id, video_path):
        """Main video processing function with enhanced detection"""
        if not self.ppe_model or not self.person_model or not os.path.exists(video_path):
            return
        
        try:
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            violations = []
            violation_count = 0
            frame_count = 0
            
            frame_interval = max(1, int(fps))
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                if frame_count % frame_interval == 0:
                    timestamp = frame_count / fps if fps > 0 else 0
                    violations_found = self.detect_violations(frame, timestamp)
                    
                    for violation in violations_found:
                        violation_count += 1
                        screenshot_path = self.save_violation_screenshot_with_bbox(
                            frame, video_id, timestamp, violation
                        )
                        
                        db.save_violation(
                            video_id=video_id,
                            timestamp=timestamp,
                            violation_type=violation['type'],
                            screenshot_path=screenshot_path,
                            bbox_data=violation.get('bbox_data', {})
                        )
                        violations.append(violation)
                
                frame_count += 1
            
            cap.release()
            
            summary = self.generate_summary(violations, duration, total_frames)
            
            db.update_video_processing(
                video_id=video_id,
                summary=summary,
                total_violations=violation_count,
                duration=duration,
                frame_count=total_frames
            )
            
            print(f"Video processing complete: {violation_count} violations found")
            
        except Exception as e:
            print(f"Error processing video {video_id}: {e}")
    
    def detect_violations(self, frame, timestamp):
        """Enhanced violation detection using both models"""
        violations = []
        
        try:
            # Detect people using dedicated person model
            people = []
            if self.person_model:
                person_results = self.person_model(frame, verbose=False, conf=self.person_conf_threshold)
                
                if person_results[0].boxes is not None:
                    for box in person_results[0].boxes:
                        if int(box.cls[0]) == 0:  # Person class
                            coords = box.xyxy[0].tolist()
                            confidence = float(box.conf[0])
                            
                            if confidence >= self.min_detection_confidence:
                                people.append({
                                    'bbox': {'x1': int(coords[0]), 'y1': int(coords[1]), 
                                           'x2': int(coords[2]), 'y2': int(coords[3])},
                                    'confidence': confidence,
                                    'has_helmet': False,
                                    'has_vest': False,
                                    'violation': True,
                                    'associated_helmets': [],
                                    'associated_vests': [],
                                    'track_id': None
                                })
            
            # Update tracking
            people = self.update_person_tracking(people)
            
            # Detect PPE items using fine-tuned model
            helmets = []
            vests = []
            
            if self.ppe_model:
                ppe_results = self.ppe_model(frame, verbose=False, conf=self.ppe_conf_threshold)
                
                if ppe_results[0].boxes is not None:
                    for box in ppe_results[0].boxes:
                        class_name = self.ppe_model.names[int(box.cls[0])]
                        coords = box.xyxy[0].tolist()
                        confidence = float(box.conf[0])
                        
                        # Filter out very small detections
                        bbox_area = (coords[2] - coords[0]) * (coords[3] - coords[1])
                        if bbox_area < 1000:  # Minimum area threshold
                            continue
                        
                        ppe_item = {
                            'bbox': {'x1': int(coords[0]), 'y1': int(coords[1]), 
                                   'x2': int(coords[2]), 'y2': int(coords[3])},
                            'confidence': confidence,
                            'used': False,
                            'area': bbox_area
                        }
                        
                        # Updated class names for your fine-tuned model
                        if class_name == "Safety-Helmet" and confidence >= self.ppe_conf_threshold:
                            helmets.append(ppe_item)
                        elif class_name == "Reflective-Jacket" and confidence >= self.ppe_conf_threshold:
                            vests.append(ppe_item)
            
            print(f"TIMESTAMP {timestamp}s:")
            print(f"  People detected: {len(people)}")
            print(f"  Helmets detected: {len(helmets)}")
            print(f"  Vests detected: {len(vests)}")
            
            # Enhanced association algorithm
            helmets.sort(key=lambda x: x['confidence'], reverse=True)
            vests.sort(key=lambda x: x['confidence'], reverse=True)
            
            # Associate helmets with people
            for helmet in helmets:
                best_person_idx = -1
                best_match_score = 0
                
                for i, person in enumerate(people):
                    is_near, match_score = self.is_ppe_near_person(person['bbox'], helmet['bbox'])
                    
                    if is_near:
                        # Enhanced scoring for helmets (prefer upper body)
                        person_bbox = person['bbox']
                        person_upper_bbox = [
                            person_bbox['x1'], 
                            person_bbox['y1'], 
                            person_bbox['x2'], 
                            person_bbox['y1'] + (person_bbox['y2'] - person_bbox['y1']) * 0.45
                        ]
                        
                        upper_iou = self.calculate_iou(person_upper_bbox, 
                            [helmet['bbox']['x1'], helmet['bbox']['y1'], helmet['bbox']['x2'], helmet['bbox']['y2']])
                        
                        # Combine multiple factors for better matching
                        total_score = (match_score * 0.4 + 
                                     upper_iou * 0.4 + 
                                     (helmet['confidence'] * 0.2))
                        
                        if total_score > best_match_score:
                            best_match_score = total_score
                            best_person_idx = i
                
                if best_person_idx >= 0 and best_match_score > 0.1:
                    people[best_person_idx]['has_helmet'] = bool(True)
                    people[best_person_idx]['associated_helmets'].append(helmet)
                    helmet['used'] = True
            
            # Associate vests with people
            for vest in vests:
                best_person_idx = -1
                best_match_score = 0
                
                for i, person in enumerate(people):
                    is_near, match_score = self.is_ppe_near_person(person['bbox'], vest['bbox'])
                    
                    if is_near:
                        # Enhanced scoring for vests (prefer middle body)
                        person_bbox = person['bbox']
                        person_middle_bbox = [
                            person_bbox['x1'], 
                            person_bbox['y1'] + (person_bbox['y2'] - person_bbox['y1']) * 0.15,
                            person_bbox['x2'], 
                            person_bbox['y1'] + (person_bbox['y2'] - person_bbox['y1']) * 0.85
                        ]
                        
                        middle_iou = self.calculate_iou(person_middle_bbox, 
                            [vest['bbox']['x1'], vest['bbox']['y1'], vest['bbox']['x2'], vest['bbox']['y2']])
                        
                        # Combine multiple factors
                        total_score = (match_score * 0.4 + 
                                     middle_iou * 0.4 + 
                                     (vest['confidence'] * 0.2))
                        
                        if total_score > best_match_score:
                            best_match_score = total_score
                            best_person_idx = i
                
                if best_person_idx >= 0 and best_match_score > 0.1:
                    people[best_person_idx]['has_vest'] = bool(True)
                    people[best_person_idx]['associated_vests'].append(vest)
                    vest['used'] = True
            
            # Apply temporal smoothing
            people = self.apply_temporal_smoothing(people)
            
            # Generate violations using smoothed results
            violations = self.check_ppe_compliance_enhanced(people, timestamp)
            
            print(f"  Violations found: {len(violations)}")
            print("---")
                
        except Exception as e:
            print(f"Detection error at {timestamp}s: {e}")
        
        return violations
    
    def check_ppe_compliance_enhanced(self, people, timestamp):
        """Enhanced PPE compliance check with improved violation detection"""
        violations = []
        people_count = len(people)
        
        if people_count == 0:
            return violations
        
        people_without_helmets = []
        people_without_vests = []
        
        for person in people:
            # Use smoothed results for final determination
            if not person.get('has_helmet_smoothed', person['has_helmet']):
                people_without_helmets.append(person)
            
            if not person.get('has_vest_smoothed', person['has_vest']):
                people_without_vests.append(person)
        
        # Create violations for missing helmets
        if len(people_without_helmets) > 0:
            if len(people_without_helmets) / people_count >= 0.3:  # 30% threshold
                violations.append({
                    'type': 'Missing Safety Helmet',
                    'severity': 'high',
                    'people_affected': len(people_without_helmets),
                    'timestamp': timestamp,
                    'bbox_data': {
                        'violation_people': people_without_helmets,
                        'missing_ppe_type': 'safety helmet'
                    }
                })
        
        # Create violations for missing vests
        if len(people_without_vests) > 0:
            if len(people_without_vests) / people_count >= 0.3:  # 30% threshold
                violations.append({
                    'type': 'Missing Reflective Jacket',
                    'severity': 'high',
                    'people_affected': len(people_without_vests),
                    'timestamp': timestamp,
                    'bbox_data': {
                        'violation_people': people_without_vests,
                        'missing_ppe_type': 'reflective jacket'
                    }
                })
        
        return violations
    
    def analyze_raw_frame(self, frame):
        """Analyze raw OpenCV frame for live streaming with enhanced detection"""
        try:
            # Similar to detect_violations but simplified for live streaming
            people = []
            
            # Detect people
            if self.person_model:
                person_results = self.person_model(frame, verbose=False, conf=self.person_conf_threshold)
                
                if person_results[0].boxes is not None:
                    for box in person_results[0].boxes:
                        if int(box.cls[0]) == 0:  # Person class
                            coords = box.xyxy[0].tolist()
                            confidence = float(box.conf[0])
                            
                            if confidence >= self.min_detection_confidence:
                                people.append({
                                    'bbox': {'x1': int(coords[0]), 'y1': int(coords[1]), 
                                           'x2': int(coords[2]), 'y2': int(coords[3])},
                                    'confidence': confidence,
                                    'has_helmet': False,
                                    'has_vest': False
                                })
            
            # Detect PPE
            helmets = []
            vests = []
            
            if self.ppe_model:
                ppe_results = self.ppe_model(frame, verbose=False, conf=self.ppe_conf_threshold)
                
                if ppe_results[0].boxes is not None:
                    for box in ppe_results[0].boxes:
                        class_name = self.ppe_model.names[int(box.cls[0])]
                        coords = box.xyxy[0].tolist()
                        confidence = float(box.conf[0])
                        
                        bbox_area = (coords[2] - coords[0]) * (coords[3] - coords[1])
                        if bbox_area < 1000:
                            continue
                        
                        ppe_item = {
                            'bbox': {'x1': int(coords[0]), 'y1': int(coords[1]), 
                                   'x2': int(coords[2]), 'y2': int(coords[3])},
                            'confidence': confidence
                        }
                        
                        if class_name == "Safety-Helmet":
                            helmets.append(ppe_item)
                        elif class_name == "Reflective-Jacket":
                            vests.append(ppe_item)
            
            # Simple association for live streaming
            for person in people:
                # Check for helmets
                for helmet in helmets:
                    is_near, _ = self.is_ppe_near_person(person['bbox'], helmet['bbox'])
                    if is_near:
                        person['has_helmet'] = True
                        break
                
                # Check for vests
                for vest in vests:
                    is_near, _ = self.is_ppe_near_person(person['bbox'], vest['bbox'])
                    if is_near:
                        person['has_vest'] = True
                        break
            
            # Simple violation check
            violations = []
            people_without_helmets = [p for p in people if not p['has_helmet']]
            people_without_vests = [p for p in people if not p['has_vest']]
            
            if len(people_without_helmets) > 0:
                violations.append({'type': 'Missing Safety Helmet', 'people_affected': len(people_without_helmets)})
            
            if len(people_without_vests) > 0:
                violations.append({'type': 'Missing Reflective Jacket', 'people_affected': len(people_without_vests)})
            
            return {
                'people_count': len(people),
                'ppe_detected': len(helmets) + len(vests),
                'violations': violations,
                'compliance_status': 'compliant' if not violations else 'non-compliant'
            }
            
        except Exception as e:
            print(f"Raw frame analysis error: {e}")
            return {
                'people_count': 0,
                'ppe_detected': 0,
                'violations': [],
                'compliance_status': 'unknown'
            }
    
    def save_violation_screenshot_with_bbox(self, frame, video_id, timestamp, violation):
        """Save screenshot with enhanced bounding box annotations"""
        try:
            annotated_frame = frame.copy()
            
            bbox_data = violation.get('bbox_data', {})
            violation_people = bbox_data.get('violation_people', [])
            missing_ppe_type = bbox_data.get('missing_ppe_type', '')
            
            for person in violation_people:
                bbox = person['bbox']
                confidence = person['confidence']
                track_id = person.get('track_id', 'Unknown')
                
                # Draw person bounding box in red
                cv2.rectangle(
                    annotated_frame,
                    (bbox['x1'], bbox['y1']),
                    (bbox['x2'], bbox['y2']),
                    (0, 0, 255),
                    3
                )
                
                # Enhanced label with track ID
                label = f"ID:{track_id} - Missing {missing_ppe_type.title()}"
                confidence_text = f"Conf: {confidence:.2f}"
                
                # Calculate label positioning
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                conf_size = cv2.getTextSize(confidence_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
                
                label_y = bbox['y1'] - 45 if bbox['y1'] > 45 else bbox['y2'] + 45
                
                # Draw background for text
                cv2.rectangle(
                    annotated_frame,
                    (bbox['x1'], label_y - 25),
                    (bbox['x1'] + max(label_size[0], conf_size[0]) + 10, label_y + 20),
                    (0, 0, 255),
                    -1
                )
                
                # Draw text
                cv2.putText(
                    annotated_frame,
                    label,
                    (bbox['x1'] + 5, label_y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA
                )
                
                cv2.putText(
                    annotated_frame,
                    confidence_text,
                    (bbox['x1'] + 5, label_y + 15),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA
                )
                
                # Draw specific violation indicators
                if 'helmet' in missing_ppe_type.lower():
                    # Highlight head area
                    head_height = int((bbox['y2'] - bbox['y1']) * 0.3)
                    head_y2 = bbox['y1'] + head_height
                    cv2.rectangle(annotated_frame, (bbox['x1'], bbox['y1']), 
                                (bbox['x2'], head_y2), (0, 255, 255), 2)
                
                if 'jacket' in missing_ppe_type.lower() or 'vest' in missing_ppe_type.lower():
                    # Highlight torso area
                    torso_start = bbox['y1'] + int((bbox['y2'] - bbox['y1']) * 0.25)
                    torso_end = bbox['y1'] + int((bbox['y2'] - bbox['y1']) * 0.75)
                    cv2.rectangle(annotated_frame, (bbox['x1'], torso_start), 
                                (bbox['x2'], torso_end), (0, 255, 255), 2)
            
            # Save annotated frame
            violation_dir = f"uploads/violations/{video_id}"
            os.makedirs(violation_dir, exist_ok=True)
            
            filename = f"violation_{int(timestamp)}_{violation['type'].replace(' ', '_')}.jpg"
            filepath = os.path.join(violation_dir, filename)
            
            cv2.imwrite(filepath, annotated_frame)
            return filepath
            
        except Exception as e:
            print(f"Error saving annotated screenshot: {e}")
            return self.save_violation_screenshot(frame, video_id, timestamp, violation['type'])
    
    def save_violation_screenshot(self, frame, video_id, timestamp, violation_type):
        """Original save screenshot method (fallback)"""
        try:
            violation_dir = f"uploads/violations/{video_id}"
            os.makedirs(violation_dir, exist_ok=True)
            
            filename = f"violation_{int(timestamp)}_{violation_type.replace(' ', '_')}.jpg"
            filepath = os.path.join(violation_dir, filename)
            
            cv2.imwrite(filepath, frame)
            return filepath
            
        except Exception as e:
            print(f"Error saving screenshot: {e}")
            return ""
    
    def generate_summary(self, violations, duration, total_frames):
        """Generate enhanced video analysis summary"""
        violation_types = {}
        for v in violations:
            v_type = v['type']
            violation_types[v_type] = violation_types.get(v_type, 0) + 1
        
        summary_parts = [
            f"Enhanced PPE Video Analysis Complete",
            f"Duration: {duration:.1f} seconds ({total_frames} frames)",
            f"Total Violations: {len(violations)}"
        ]
        
        if violation_types:
            summary_parts.append("Violation Breakdown:")
            for v_type, count in violation_types.items():
                summary_parts.append(f"  • {v_type}: {count} instances")
                
            # Calculate violation rate
            if len(violations) > 0:
                avg_violations_per_minute = (len(violations) / duration) * 60
                summary_parts.append(f"Average violations per minute: {avg_violations_per_minute:.1f}")
        else:
            summary_parts.append("No PPE violations detected - Full compliance achieved!")
        
        return "\n".join(summary_parts)
    
    # Keep existing methods for backward compatibility
    def get_frame_for_streaming(self, video_path, frame_number=0):
        try:
            # Open video capture
            print(f"🐛 DEBUG: Original video_path: '{video_path}'")
            print(f"🐛 DEBUG: Type: {type(video_path)}")

            normalized_path = os.path.normpath(video_path)
            if not os.path.exists(normalized_path):
                print(f"Error: Video file not found: {normalized_path}")

                print(f"🐛 DEBUG: Normalized path: '{normalized_path}'")

                print(f"Current working directory: {os.getcwd()}")
                print(f"Looking for file: {os.path.abspath(normalized_path)}")
                return None
        
            cap = cv2.VideoCapture(normalized_path)
            
            # Check if video opened successfully
            if not cap.isOpened():
                print(f"Error: Cannot open video file: {video_path}")
                return None
            
            # Get video properties for validation
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Validate frame number
            if frame_number < 0:
                frame_number = 0
            elif frame_number >= total_frames:
                frame_number = total_frames - 1
                print(f"Warning: Requested frame {frame_number} exceeds video length. Using last frame.")
            
            # Set frame position
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            
            # Read the specific frame
            ret, frame = cap.read()
            
            # Release the video capture object
            cap.release()
            
            if ret and frame is not None:
                # Encode frame to base64 JPEG for streaming
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]  # 80% quality
                _, buffer = cv2.imencode('.jpg', frame, encode_param)
                
                # Convert to base64 string
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                return frame_base64
            else:
                print(f"Error: Could not read frame {frame_number} from video")
                return None
            
        except Exception as e:
            print(f"Error getting frame: {e}")
            return None
    
    def encode_frame(self, frame):
        try:
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            return frame_base64
        except Exception as e:
            print(f"Error encoding frame: {e}")
            return None
    
# Create processor instance with enhanced capabilities
processor = VideoProcessor()