# Complaint Management System

A Django + PostgreSQL web app for managing complaints, with three roles: Complainant, Staff, and Admin.

## Demo

### Admin side
<!-- Replace this line with your video/GIF, e.g.: -->
<!-- ![Admin demo](docs/admin-demo.gif) -->
<!-- or, if uploading a video file: -->
<!-- https://github.com/your-username/your-repo/assets/your-video-link -->


### User side
<!-- Replace this line with your video/GIF, e.g.: -->
<!-- ![User demo](docs/user-demo.gif) -->
<!-- or, if uploading a video file: -->
<!-- https://github.com/your-username/your-repo/assets/your-video-link -->

## Features
- Complainants file and track complaints
- Staff claim and resolve complaints
- Admins get a dashboard with charts and CSV export
- Comments, attachments, status history, email notifications

## Setup

```bash
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your PostgreSQL password.

```bash
python manage.py makemigrations accounts complaints
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`. Demo login (password `Demo@12345`):

| Username | Role |
|---|---|
| `admin_demo` | Admin |
| `staff_ravi` | Staff |
| `user_asha` | Complainant |

## Tech stack
Python, Django, PostgreSQL, Bootstrap 5, Chart.js