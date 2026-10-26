import cv2
import numpy as np
import os

class FaceRecognizer:
    """
    A lightweight face recognition module compatible with Python 3.14.
    Uses OpenCV's built-in LBPH (Local Binary Patterns Histograms) Face Recognizer.
    This avoids the heavy C++ build tools required by dlib/face_recognition on newer Python environments.
    """
    def __init__(self, cascade_path=None):
        # We use OpenCV's Haar Cascades for detecting faces.
        # Check project-local models directory first using absolute path based on __file__.
        if cascade_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            local_cascade = os.path.join(base_dir, "models", "haarcascade_frontalface_default.xml")
            cv2_cascade = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            
            if os.path.exists(local_cascade):
                cascade_path = local_cascade
            elif os.path.exists(cv2_cascade):
                cascade_path = cv2_cascade
            else:
                cascade_path = local_cascade

        if not os.path.exists(cascade_path):
            raise FileNotFoundError(
                f"Haar Cascade file not found at: '{cascade_path}'. "
                "Please ensure 'haarcascade_frontalface_default.xml' is located in 'ai-services/face-recognition/models/'."
            )

        self.face_detector = cv2.CascadeClassifier(cascade_path)
        if self.face_detector.empty():
            raise RuntimeError(f"Failed to load Haar Cascade classifier from '{cascade_path}'. File may be corrupt.")
        
        # LBPH Face Recognizer requires opencv-contrib-python
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        
        # OpenCV's recognizer requires integer labels for training. 
        # We create dictionaries to map incrementing integers to our UUIDs.
        self.current_int_label = 0
        self.label_to_uuid = {}
        self.uuid_to_details = {}
        
        # Training data arrays
        self.faces_data = []
        self.labels_data = []
        
        self.is_trained = False
        # LBPH distance threshold — webcam vs enrolled photo needs a looser match
        # (lower distance = better). Typical good matches are < 80-90.
        self.tolerance = 95.0
        self.face_size = (120, 120) 

    def _extract_face_roi(self, image_path=None, frame=None):
        """Helper function to load an image, convert to grayscale, and crop out the face region."""
        if frame is not None:
            img = frame
        else:
            if not image_path or not os.path.exists(image_path):
                print(f"Error: Image {image_path} not found.")
                return None
                
            img = cv2.imread(image_path)
            if img is None:
                print(f"Error: OpenCV could not read {image_path}.")
                return None
            
        # LBPH requires grayscale images
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Detect face coordinates — slightly more permissive for live webcam
        faces = self.face_detector.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40)
        )
        
        if len(faces) == 0:
            return None
            
        # For the MVP, we assume a single face is in the image, so we pick the largest one
        (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
        # Return the cropped grayscale facial region, normalized for LBPH
        roi = gray[y:y+h, x:x+w]
        try:
            roi = cv2.resize(roi, self.face_size)
        except Exception:
            return None
        return roi

    def register_student(self, student_id, name, roll_number, image_path):
        """
        Extracts the face from the provided image and prepares it for training.
        """
        face_roi = self._extract_face_roi(image_path)
        
        if face_roi is None:
            print(f"Error: No face detected in {image_path}. Cannot register.")
            return False
            
        self.faces_data.append(face_roi)
        self.labels_data.append(self.current_int_label)
        
        self.label_to_uuid[self.current_int_label] = student_id
        self.uuid_to_details[student_id] = {
            "name": name,
            "roll_number": roll_number
        }
        
        self.current_int_label += 1
        print(f"Successfully loaded facial data for {name} ({roll_number}).")
        return True

    def train_model(self):
        """
        Trains the OpenCV LBPH model. 
        Must be called ONCE after all students have been registered.
        """
        if len(self.faces_data) == 0:
            print("No training data available.")
            return False
            
        # Train requires a numpy array of numpy arrays, and a numpy array of integer labels
        self.recognizer.train(self.faces_data, np.array(self.labels_data))
        self.is_trained = True
        print("AI Model successfully trained on registered students.")
        return True

    def recognize_test_face(self, test_image_path=None, test_frame=None):
        """
        Compares a test face against the trained localized Model.
        Returns the match details and confidence level, or 'Unknown'.
        """
        if not self.is_trained:
            print("Error: Model has not been trained yet. Call train_model() first.")
            return None, 0.0
            
        face_roi = self._extract_face_roi(image_path=test_image_path, frame=test_frame)
        if face_roi is None:
            # Removed print statement to avoid spamming the console 30 times a second
            return None, 0.0
            
        # Predict returns the predicted integer label and a confidence/distance score
        predicted_label, distance = self.recognizer.predict(face_roi)
        
        # Convert OpenCV's LBPH distance to a mock "percentage" confidence 
        # (0 distance = perfect match. Usually cuts off around 100)
        confidence = max(0.0, 100.0 - distance)

        if distance <= self.tolerance:
            matched_uuid = self.label_to_uuid[predicted_label]
            student_info = self.uuid_to_details[matched_uuid]
            
            match_data = {
                "student_id": matched_uuid,
                "name": student_info["name"],
                "roll_number": student_info["roll_number"]
            }
            return match_data, confidence
        else:
            return "Unknown", confidence
