"""Shared OpenCV camera, motion detection, and YOLO person detection service."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable

import cv2

try:
    from ultralytics import YOLO
except ImportError:  # Allows motion-only mode when YOLO has not been installed yet.
    YOLO = None


class CameraDetector:
    def __init__(self, on_incident: Callable[[str, object], None], camera_index: int = 0):
        self.on_incident = on_incident
        self.camera_index = camera_index
        self._lock = threading.Lock()
        self._capture = None
        self._thread = None
        self._running = False
        self._latest_jpeg: bytes | None = None
        self._previous_gray = None
        self._model = None
        self._last_event: dict[str, float] = {}
        self._status = {
            "camera_online": False,
            "motion_active": False,
            "person_active": False,
            "last_detection": None,
            "error": None,
        }

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cctv-camera")
        self._thread.start()

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def latest_frame(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def _open_camera(self) -> bool:
        self._capture = cv2.VideoCapture(self.camera_index)
        if not self._capture.isOpened():
            with self._lock:
                self._status["error"] = "Laptop webcam could not be opened. Check camera permission and close other camera apps."
                self._status["camera_online"] = False
            self._capture.release()
            self._capture = None
            return False
        with self._lock:
            self._status["camera_online"] = True
            self._status["error"] = None
        return True

    def _load_model(self) -> None:
        if self._model is not None or YOLO is None:
            return
        try:
            self._model = YOLO("yolov8n.pt")
        except Exception as exc:
            with self._lock:
                self._status["error"] = f"YOLO is unavailable: {exc}"

    def _can_create_event(self, incident_type: str, seconds: int = 15) -> bool:
        now = time.monotonic()
        previous = self._last_event.get(incident_type, 0)
        if now - previous < seconds:
            return False
        self._last_event[incident_type] = now
        return True

    def _notify(self, incident_type: str, frame) -> None:
        if not self._can_create_event(incident_type):
            return
        try:
            self.on_incident(incident_type, frame)
        except Exception as exc:
            with self._lock:
                self._status["error"] = f"Could not save incident: {exc}"

    def _loop(self) -> None:
        while self._running:
            if self._capture is None and not self._open_camera():
                time.sleep(3)
                continue
            ok, frame = self._capture.read()
            if not ok:
                with self._lock:
                    self._status["camera_online"] = False
                    self._status["error"] = "Camera frame could not be read. Retrying…"
                self._capture.release()
                self._capture = None
                time.sleep(1)
                continue

            frame = cv2.resize(frame, (640, 480))
            annotated = frame.copy()
            gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
            motion = False
            if self._previous_gray is not None:
                difference = cv2.absdiff(self._previous_gray, gray)
                _, threshold = cv2.threshold(difference, 25, 255, cv2.THRESH_BINARY)
                motion = cv2.countNonZero(cv2.dilate(threshold, None, iterations=2)) > 4500
            self._previous_gray = gray

            person_confidence = None
            self._load_model()
            if self._model is not None:
                try:
                    result = self._model(frame, classes=[0], conf=0.55, verbose=False)[0]
                    if len(result.boxes):
                        box = result.boxes[0]
                        person_confidence = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                        cv2.putText(annotated, f"person {person_confidence:.2f}", (x1, max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 255), 2)
                except Exception as exc:
                    with self._lock:
                        self._status["error"] = f"YOLO detection error: {exc}"

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if motion:
                self._notify("Motion Detected", annotated)
            if person_confidence is not None:
                self._notify("Person Detected", annotated)

            cv2.putText(annotated, f"{now}  LIVE", (14, 32), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 255), 2)
            ok, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                with self._lock:
                    self._latest_jpeg = buffer.tobytes()
                    self._status.update(
                        motion_active=motion,
                        person_active=person_confidence is not None,
                        last_detection={
                            "type": "Person Detected" if person_confidence is not None else "Motion Detected" if motion else None,
                            "confidence": round(person_confidence * 100) if person_confidence is not None else None,
                            "time": now,
                            "camera": "Laptop Webcam",
                        } if (motion or person_confidence is not None) else None,
                    )
            time.sleep(.03)

    def frames(self):
        self.start()
        while True:
            frame = self.latest_frame()
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(.08)
