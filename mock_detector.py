import random
import time

def mock_detect_accident():
    """
    Mock accident detection that alternates between 'accident' and 'no accident'
    with a slight bias toward 'no accident'.
    
    This is used for testing without consuming the Together API quota.
    """
    # Simulate processing delay
    time.sleep(0.1)
    
    # 80% chance of no accident, 20% chance of accident
    return "accident" if random.random() < 0.2 else "no accident" 