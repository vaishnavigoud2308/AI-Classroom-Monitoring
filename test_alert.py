import os, sys, time
sys.path.insert(0, os.path.abspath('ai-services'))
sys.path.insert(0, os.path.abspath('ai-services/alert-engine'))
from api.dependencies import GLOBAL_CONFIG
from alert_engine import AlertEngine
alert_engine = AlertEngine(config=GLOBAL_CONFIG)
alert_engine.process_activity_event('fef737a5-b89f-4d74-9ffa-774092169692', {
    'student_id': 'UNKNOWN_STUDENT',
    'activity': 'phone_usage',
    'confidence': 99.0
})
