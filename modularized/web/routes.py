from flask import Flask, Response, request, jsonify, render_template
import cv2
from shared.state import running, queue, display_queue


app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    print("[STREAM] Client connected to /video_feed")
    def generate_stream():
        # global display_queue
        while running:
            try:
                frame = display_queue.get(timeout=1)
            except queue.Empty:
                continue

            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')