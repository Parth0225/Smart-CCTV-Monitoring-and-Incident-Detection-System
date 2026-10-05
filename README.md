# Smart CCTV UI

Web application for the Smart CCTV Monitoring and Incident Detection System.

## Run

Create a virtual environment, install the dependencies, and run Flask:

```powershell
cd smart-cctv-ui
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py run.py
```

Then visit `http://127.0.0.1:5000`.

Do not open `index.html` through Live Server or by double-clicking it: registration and login require the Flask server above.

## Included screens

Login, registration, dashboard, live feed, detection mode, incident alert, incident detail, incidents, history, settings, and logout.

## Authentication

Registration creates a user in `instance/cctv.db`. Passwords are never stored as plain text; Flask/Werkzeug stores password hashes. Login is only accepted when the submitted username and password match a registered user.

Camera, detection, incident, history, and settings values remain frontend demonstrations until their backend phase is added.

## Live dashboard

The dashboard reads its counts and recent-incidents list from SQLite and refreshes every three seconds. It starts with one online laptop camera and zero incidents. The `POST /api/incidents` endpoint is ready for the future OpenCV/YOLO detector to record `Motion Detected` or `Person Detected` events; the dashboard will reflect them on its next refresh.

## Live camera and detection

The Live Feed page starts a shared OpenCV webcam stream from `cv2.VideoCapture(0)`. Motion is detected through consecutive-frame comparison. YOLOv8 detects the `person` class only; its weights (`yolov8n.pt`) download automatically on the first successful run. Each detected event is rate-limited, annotated, saved as a screenshot in `static/uploads/`, and stored in SQLite. The dashboard, incidents list, history, and incident detail page use the same stored live data.

If the camera is unavailable, close other apps using it and grant camera permission to Python when Windows asks.
