# shared/state.py
import threading
import queue

# Shared queues
frame_queue = queue.Queue(maxsize=10)
save_queue = queue.Queue(maxsize=10)
process_queue = queue.Queue(maxsize=10)
display_queue = queue.Queue(maxsize=10)

cap = None

# Shared flags and locks
running = True
detected_food_drinks_lock = threading.Lock()
pose_points_lock = threading.Lock()
flagged_foodbev_lock = threading.Lock()

flagged_foodbev = [] # Format: [track ids]
pose_points = []
detected_food_drinks = {} # Format: { track_id, [coords(List Of 4 Values), center(Tuple Of 2 Values), confidence(Float), classId(Integer)] }
# Track wrist proximity times per person
wrist_proximity_history = {}  # Format: {track_id: [timestamps]}
