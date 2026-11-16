# 🦺 PPE Compliance Monitor (YOLOv8)

A web app that watches construction-site video and flags workers who are **missing a hard hat or safety vest**, using a custom fine-tuned YOLOv8 model.

> This is version 3 of my PPE-safety project series:
> [v1 – GPT-4o Vision](https://github.com/ByteCrafter01/PPE_Detection_OpenAI) →
> [v2 – YOLO + AI Q&A](https://github.com/ByteCrafter01/Safety_Administration_system) →
> **v3 – Fine-tuned YOLO + user accounts (this repo)**

---

## ✨ Features

- **Upload a video or use a live webcam stream**
- **Two-stage detection**: find each person first, then match helmets and vests to that person
- **Fewer false alarms**: a short "memory" of recent frames smooths out flickering detections before a violation is raised
- **Violation snapshots** saved with timestamps, browsable per video
- **Login / register** with JWT (JSON Web Token) authentication
- **Real-time updates** to the browser over WebSockets (Socket.IO)

## 🔄 How it works

```
Video / webcam
      │
      ▼
YOLOv8 (person detector) ──► who is in the frame?
      │
      ▼
Fine-tuned YOLOv8 (PPE model) ──► helmets & vests
      │
      ▼
Match PPE to each person  ──►  smooth over recent frames
      │
      ▼
Violation? ──► save snapshot to MongoDB ──► push alert to dashboard
```

## 🛠️ Tech stack

| Layer | Tools |
|---|---|
| Detection | Ultralytics YOLOv8, OpenCV |
| Backend | Python, Flask, Flask-SocketIO |
| Database | MongoDB (local or Atlas) |
| Auth | JWT (PyJWT) |
| Frontend | HTML, CSS, vanilla JavaScript |

## 🚀 Run it locally

```bash
git clone https://github.com/ByteCrafter01/YOLO_Fine_Tuned_SASystem.git
cd YOLO_Fine_Tuned_SASystem
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
MONGODB_URI=mongodb://localhost:27017/
DB_NAME=ppe_detection
JWT_SECRET_KEY=change-me-to-a-long-random-string
```

Then start the app:

```bash
python run.py
```

Open http://localhost:5000, register an account and upload a site video.

## 📁 Project structure

```
backend/
├── app.py              # Flask routes + Socket.IO events
├── video_processor.py  # Detection pipeline (person → PPE → smoothing)
├── database.py         # MongoDB access + user accounts
└── models/best.pt      # Fine-tuned PPE weights
frontend/
├── templates/          # Dashboard, live stream, video grid, login pages
└── static/             # CSS + JS
run.py                  # Entry point
```

## 💡 What I learned

- Fine-tuning YOLOv8 on a custom PPE dataset
- Why per-frame detections flicker, and how a short temporal window fixes it
- Streaming results to a browser in real time with WebSockets
