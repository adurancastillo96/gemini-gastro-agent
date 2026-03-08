# 🍽️ Gemini Gastro-Agent

A cutting-edge Multimodal Live Agent with Human-in-the-Loop (HITL) capabilities, designed to revolutionize restaurant customer service. Built with the **Gemini Multimodal Live API** and optimized for ultra-low latency.

## 🚀 Overview

Gemini Gastro-Agent acts as an intelligent, real-time voice assistant for restaurant customers while keeping the business owner perfectly in sync. It replaces traditional static menus with dynamic, conversational, and highly visual interactions.

### ✨ Architecture & Key Components

1. **Frontend (Client Interface):**
   - Built with **React 19 / Vite** and deployed on **Firebase Hosting**.
   - Captures real-time audio via `AudioWorklet` and streams it to the backend using WebSockets.
   - Dynamically renders visual UI elements (Menu Cards with dish images, prices, and allergen info) inline based on the system's responses.
   - Includes optional Google Sign-In for advanced features like HITL escalation and automated video reviews.

2. **Backend (Core Engine):**
   - A high-performance **Python/FastAPI** server, deployed on **Google Cloud Run**.
   - Functions as an optimized WebSocket proxy between the client and the **Gemini Live API**.
   - Utilizes the native **`google-genai` SDK** with Function Calling (zero-abstraction for minimal latency).
   - Implements an **in-memory RAM cache** for sub-millisecond local tool executions.

3. **Data & Synchronization (Firestore):**
   - **GCP Firestore** acts as the persistent source of truth for the multi-tenant catalogs.
   - Venues, menus, owners, and employees are managed via isolated documents.

4. **Backoffice (Telegram HITL):**
   - Owners and employees interact with their restaurant system simply by texting a Telegram Bot (e.g., *"Paella is sold out"*).
   - A webhook in the backend securely catches this message, instantly updates Firestore, purges the RAM cache, and relays responses to active agent sessions if an escalation is in progress.

## 📂 Project Structure

This monorepo is organized to clearly separate the Python backend engine from the React frontend interface.

```text
gemini-gastro-agent/
│
├── backend/                        # 🧠 Python Engine (FastAPI)
│   ├── Dockerfile
│   ├── requirements.txt            # Minimal direct dependencies
│   ├── main.py                     # FastAPI app & WebSocket routes
│   ├── agent/                      # Gemini Live session manager & tools
│   ├── core/                       # Config, database (Firestore), and RAM cache
│   └── webhooks/                   # Telegram webhook endpoint
│
├── frontend/                       # 📱 Client Interface (React/Vite)
│   ├── src/
│   │   ├── components/             # UI: ChatBubble, ProductCarousel, TalkButton, etc.
│   │   ├── hooks/                  # AudioCapture & GeminiLive WebSocket logic
│   │   ├── pages/                  # Venue chat page
│   │   └── App.jsx
│   ├── package.json
│   └── firebase.json               # Firebase deployment configuration
│
├── software-requirements-document.md
├── architecture.png                # 🖼️ High-level architecture diagram
└── README.md                       # 📝 Project documentation
```

## 🛠️ Tech Stack

* **AI & Agent:** Gemini Live API (`gemini-live-2.5-flash-native-audio`), `google-genai` SDK (Native Function Calling)
* **Backend:** Python 3.11+, FastAPI, WebSockets, Uvicorn, Docker
* **Frontend:** React 19, Vite, Web Audio API (`AudioWorklet`), Firebase Auth
* **Cloud & DB:** Google Cloud Run, GCP Firestore, Firebase Hosting, Secret Manager
* **Integrations:** Telegram Bot API (via Webhooks)

## 🏁 Getting Started

*(Documentation to be continued based on deployment and setup instructions...)*
