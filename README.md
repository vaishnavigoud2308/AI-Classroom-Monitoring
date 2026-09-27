# AI-Powered Classroom Monitoring System

## Overview
This is an AI-based classroom assistant designed to assist teachers with:
1. Automatic student attendance using face recognition.
2. Teacher-controlled attendance correction.
3. Mobile phone detection using YOLO/object detection.
4. Possible sleeping/attention indicators using facial landmarks, head position, and eye cues.
5. Classroom audio activity detection for possible talking or excessive noise.
6. Monitoring alerts and logs.
7. A comprehensive teacher dashboard for management.
8. Attendance records and classroom monitoring reports.

**Important Project Principle:** The AI is designed to assist the teacher, not replace them. All AI detections should be treated as alerts/indicators, and the teacher must be able to review, override, or correct them.

## Technology Stack
- **Frontend / Dashboard**: Lovable, React, TypeScript, Tailwind CSS
- **Backend & Data**: Supabase (PostgreSQL, Auth, Storage, Edge Functions)
- **AI Services**: Python, OpenCV, YOLO (Object Detection), Facial Landmarks, Audio Processing

## Architecture & Project Structure
- `ai-services/`: Contains independent Python scripts and modular AI processing logic.
  - `face-recognition/`: Scripts for processing student faces to perform automatic roll calls.
  - `phone-detection/`: YOLO-based object detection scripts to identify mobile phones in use.
  - `attention-monitoring/`: Analysis scripts for facial landmarks, head-pose estimation, and eye cues indicating sleepiness or lack of attention.
  - `audio-monitoring/`: Basic audio activity and noise level detection.
- `supabase/`: Backend configurations and definitions.
  - `migrations/`: PostgreSQL database schemas, SQL scripts, and migrations.
  - `functions/`: Serverless Supabase Edge Functions.
- `docs/`: Project documentation, guidelines, and API notes.
