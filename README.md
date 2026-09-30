# ✈️ Travel Concierge Agent

An intelligent, multi-modal travel concierge agent built with Google's **Agent Development Kit (ADK)** and deployed to **Vertex AI Agent Runtime**. The agent helps travelers discover curated destinations, book travel packages, query live weather reports, generate scenic preview photos & short videos, and remember personalized travel styles, dietary preferences, and allergies across sessions.

![Travel Concierge Demo](agent_demo.gif)

---

## 🌟 Capabilities & Features

Based on the implemented tools in [`app/agent.py`](app/agent.py), the Travel Concierge provides the following functionality:

### 1. 🗄️ Firestore Destination Catalog & Bookings
- **Destination Catalog**: Queries travel destination listings stored in Google Cloud Firestore (`destinations` collection) filtered by keywords and budget constraints (`search_destinations`).
- **Catalog Management**: Saves new travel destination records with location tags, night rates, and ratings (`add_destination`).
- **Travel Package Reservations**: Books itinerary packages with generated unique reservation codes (`TC-XXXXXX`) stored directly in Firestore (`bookings` collection).

### 2. 🧠 Vertex AI Memory Bank Integration
- **Cross-Session Preference Memory**: Uses Vertex AI Memory Bank (`VertexAiMemoryBankService` and `PreloadMemoryTool`) to store and recall user travel preferences, dietary restrictions, and food allergies across separate chat turns and sessions.

### 3. 🌤️ Live Real-Time Weather Reports
- **Open-Meteo API**: Fetches current live temperature (°C) and wind speeds for any destination city in real-time (`get_real_time_weather`).

### 4. 📍 Google Maps Geocoding & Places (New) APIs
- **Geocoding**: Converts street addresses or landmarks into precise geographic coordinates (`geocode_address`).
- **Nearby Places**: Discovers nearby restaurants, cafes, lodging, and tourist attractions around target coordinates (`find_nearby_places`).

### 5. 📸 Multi-Modal Media Generation & Cloud Storage
- **Imagen / Gemini Photos (`gemini-3.1-flash-lite-image`)**: Generates realistic scenic destination photos in region `global`, saves ADK artifacts (`tool_context.save_artifact`), uploads bytes to a public Google Cloud Storage bucket, and returns public HTTPS image URLs (`generate_destination_image`).
- **Gemini Omni Videos (`gemini-omni-flash-preview`)**: Generates short destination preview videos in region `global`, saves ADK artifacts, and uploads video bytes to Cloud Storage (`generate_destination_video`).

### 6. 🎨 Dynamic A2UI & Custom Chat Frontend
- **A2UI Protocol (v0.8)**: Generates structured, responsive card layouts (`A2uiSchemaManager` and `a2ui_callback`) rendered seamlessly in the ADK Dev UI and custom frontend.
- **FastAPI Proxy & Custom UI**: Includes a lightweight FastAPI proxy (`frontend/main.py`) and a polished custom web frontend with quick-prompt chips, sender dialogue bubbles, and ocean teal styling.

### 7. 💻 Code Sandbox Executor
- **AgentEngineSandboxCodeExecutor**: Evaluates Python code expressions in an isolated sandbox for dynamic budget calculations and trip estimations.

---

## 🛠️ Architecture & Google Cloud Infrastructure

| Service | Component & Purpose |
| :--- | :--- |
| **Agent Framework** | Google Agent Development Kit (ADK 1.1.0) |
| **Deployment Target** | Vertex AI Agent Runtime (`locations/us-east1`) |
| **Database** | Google Cloud Firestore (NoSQL destination catalog & reservations) |
| **Memory** | Vertex AI Memory Bank (`VertexAiMemoryBankService`) |
| **Media Bucket** | Google Cloud Storage (Public media hosting for photos & videos) |
| **Generative AI Models** | `gemini-flash-latest`, `gemini-3.1-flash-lite-image`, `gemini-omni-flash-preview` |
| **Maps APIs** | Google Maps Geocoding & Places (New) APIs |
| **Frontend Runtime** | FastAPI proxy + HTML5/CSS3 chat UI deployed on Cloud Run |

---

## 📋 Status of Planned Features

- **Firestore Database Integration**: ✅ Implemented
- **Memory Bank Preference Tracking**: ✅ Implemented
- **AI Image & Video Generation**: ✅ Implemented
- **Public Cloud Storage Bucket Hosting**: ✅ Implemented
- **A2UI Card Renderer**: ✅ Implemented
- **Google Maps Geocoding & Places**: ✅ Implemented
- **Code Sandbox Budget Calculations**: ✅ Implemented
- **Live GDS Flight / Hotel Booking Systems**: 🟡 *Planned / Not yet implemented (simulated via Firestore `bookings` collection)*

---

## 🚀 Local Setup & Run Instructions

### Prerequisites
- Python 3.10+
- `gcloud` CLI authenticated to your GCP project
- Google Cloud Project with Firestore, Vertex AI, and Cloud Storage APIs enabled

### 1. Install Dependencies
```bash
pip install -r frontend/requirements.txt
```

### 2. Configure Environment Variables
Set the deployed Agent Engine resource name and agent directory:
```bash
export AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_NUMBER>/locations/us-east1/reasoningEngines/<ENGINE_ID>"
export AGENT_DIRECTORY="app"
```

### 3. Run the Frontend Locally
Start the FastAPI proxy and chat frontend:
```bash
cd frontend
python main.py
```
Open your browser to the local server port printed in the terminal to interact with your agent.
