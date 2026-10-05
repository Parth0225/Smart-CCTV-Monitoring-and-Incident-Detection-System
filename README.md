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

## Included screens

Login, registration, dashboard, live feed, detection mode, incident alert, incident detail, incidents, history, settings, and logout.

## Authentication

Registration creates a user in `instance/cctv.db`. Passwords are never stored as plain text; Flask/Werkzeug stores password hashes. Login is only accepted when the submitted username and password match a registered user.

Camera, detection, incident, history, and settings values remain frontend demonstrations until their backend phase is added.
