# 🍽️ Gemini Gastro-Agent

A cutting-edge Multimodal Live Agent with Human-in-the-Loop (HITL) capabilities, designed to revolutionize restaurant customer service. Built with the **Google Agent Development Kit (ADK)** and the **Gemini Multimodal Live API**.

## 🚀 Overview

Gemini Gastro-Agent acts as an intelligent, real-time voice assistant for restaurant customers while keeping the business owner perfectly in sync. It replaces traditional static menus with dynamic, conversational, and highly visual interactions.

### ✨ Architecture & Key Components

1. **Frontend (Client Interface):** - Built with **React/Vite** and deployed on **Firebase Hosting**.
   - Captures real-time audio via the user's microphone and streams it to the backend using WebSockets.
   - Dynamically renders visual UI elements (Menu Cards with dish images, prices, and allergen info) based on the conversation.

2. **Backend (Core Engine):** - A high-performance **Python/FastAPI** server, containerized and deployed on **Google Cloud Run**.
   - Maintains WebSocket connections with the frontend and handles seamless communication with the Gemini Multimodal Live API.

3. **The Brain (Google ADK & MCP):** - Powered by a Python-configured intelligent agent utilizing a Model Context Protocol (**MCP**) Toolset. Instead of rigid programming, the agent autonomously uses tools:
     - `FirestoreTool`: Reads real-time menu data and dish availability.
     - `TelegramTool`: Triggers a tripartite chat, escalating complex issues directly to the restaurant owner.

4. **Backoffice (Telegram HITL):** - Owners interact with their restaurant system simply by texting a Telegram Bot (e.g., *"Paella is sold out"*).
   - A webhook in the backend catches this message and instantly updates **GCP Firestore**, syncing the Agent's knowledge base in real-time.

## 📂 Project Structure

This monorepo is organized to clearly separate the Python backend engine from the React frontend interface.

```text
gemini-gastro-agent/
│
├── backend/                        # 🧠 Python Engine (FastAPI + ADK)
│   ├── Dockerfile                  # Deployment configuration for Google Cloud Run
│   ├── requirements.txt            # Python dependencies (fastapi, websockets, google-genai...)
│   ├── main.py                     # FastAPI server & WebSockets entry point
│   ├── agent/
│   │   ├── gastro_agent.py         # ADK Agent configuration & System Prompt
│   │   └── tools.py                # MCP tools implementation (Telegram, Firestore)
│   ├── core/
│   │   ├── config.py               # Environment variables setup (.env)
│   │   └── database.py             # GCP Firestore connection handler
│   └── webhooks/
│       └── telegram_webhook.py     # Listens to owner's messages & updates the DB
│
├── frontend/                       # 📱 Client Interface (React/Vite)
│   ├── firebase.json               # Firebase deployment configuration
│   ├── package.json                # Node dependencies & scripts
│   ├── src/
│   │   ├── components/
│   │   │   ├── LiveAudioVisualizer.jsx # Visual feedback for agent listening state
│   │   │   └── MenuCard.jsx        # UI component for dishes, prices, and allergens
│   │   ├── hooks/
│   │   │   └── useGeminiLive.js    # WebSocket logic to connect with the backend
│   │   └── App.jsx                 # Main application view
│
├── architecture.png                # 🖼️ High-level architecture diagram
└── README.md                       # 📝 Project documentation
```

## 🛠️ Tech Stack

* **AI & Agent:** Google GenAI SDK, Google Agent Development Kit (ADK), Model Context Protocol (MCP)
* **Backend:** Python, FastAPI, WebSockets, Docker
* **Frontend:** React, Vite, TailwindCSS (or your CSS framework)
* **Cloud & DB:** Google Cloud Run, GCP Firestore, Firebase Hosting
* **Integrations:** Telegram Bot API

## 🏁 Getting Started

continue...
