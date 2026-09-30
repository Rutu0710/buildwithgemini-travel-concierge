# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import re
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo
import google.auth
from google import genai
from google.cloud import firestore, storage

from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .a2ui_utils import a2ui_callback

# Hardcode project ID as a string to prevent Agent Platform environment resolution issues
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-c3139008356e"

# Hardcode public Cloud Storage bucket name
PUBLIC_GCS_BUCKET_NAME = "travel-concierge-media-qwiklabs-gcp-01-c3139008356e"

# Read Agent Engine resource name from deployment_metadata.json if available
_agent_engine_resource_name = None
_metadata_path = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
if os.path.exists(_metadata_path):
    try:
        with open(_metadata_path, "r") as f:
            _meta = json.load(f)
            _agent_engine_resource_name = _meta.get("remote_agent_runtime_id")
    except Exception as e:
        print(f"Warning reading deployment_metadata.json: {e}")

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=_agent_engine_resource_name
)

# Extract Memory Bank ID from deployed Agent Engine resource name
MEMORY_BANK_ID = _agent_engine_resource_name.split("/")[-1] if _agent_engine_resource_name else "6185392822007365632"


def get_memory_service() -> VertexAiMemoryBankService:
    """Helper to instantiate the Vertex AI Memory Bank service using the deployed Agent Engine ID."""
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """Write session turn memories to Memory Bank after each agent turn if memory service is available."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError:
        pass
    return None


def _get_firestore_client() -> firestore.Client:
    """Helper to initialize the Firestore client with hardcoded project ID."""
    try:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=creds)
    except Exception:
        return firestore.Client(project=FIRESTORE_PROJECT_ID)


def _get_maps_api_key() -> str:
    """Helper to read GOOGLE_MAPS_API_KEY from environment or local .env file without hardcoding."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key and os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("GOOGLE_MAPS_API_KEY="):
                    key = line.strip().split("=", 1)[1].strip()
                    break
    return key


def search_destinations(query: str = "", max_price: float = 0.0) -> str:
    """Search for travel destinations in the Firestore database.

    Args:
        query: Optional search keyword to match destination name, country, description, or tags.
        max_price: Optional maximum budget per night. If > 0, filters for destinations <= max_price.

    Returns:
        A list of matching travel destinations with details like name, country, description, price per night, rating, and tags.
    """
    try:
        db = _get_firestore_client()
        docs = db.collection("destinations").stream()
        results = []
        q_lower = query.lower().strip()

        for doc in docs:
            item = doc.to_dict()
            item["id"] = doc.id
            price = float(item.get("price_per_night", 0.0))

            if max_price > 0 and price > max_price:
                continue

            if q_lower:
                name = item.get("name", "").lower()
                country = item.get("country", "").lower()
                desc = item.get("description", "").lower()
                tags = [t.lower() for t in item.get("tags", [])]
                if not (q_lower in name or q_lower in country or q_lower in desc or any(q_lower in t for t in tags)):
                    continue

            results.append(item)

        if not results:
            return f"No travel destinations found matching query='{query}'" + (f" and max_price=${max_price}" if max_price > 0 else "") + "."

        lines = [f"Found {len(results)} destination(s):"]
        for dest in results:
            tags_str = ", ".join(dest.get("tags", []))
            lines.append(
                f"- {dest.get('name')} ({dest.get('country')}): {dest.get('description')} "
                f"| ${dest.get('price_per_night')}/night | Rating: {dest.get('rating')}/5 | Tags: [{tags_str}]"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error querying Firestore database: {str(e)}"


def add_destination(
    name: str,
    country: str,
    description: str,
    price_per_night: float,
    rating: float = 4.5,
    tags: str = "",
) -> str:
    """Add a new travel destination to the Firestore database.

    Args:
        name: Name of the city or destination (e.g. 'Barcelona').
        country: Country where the destination is located (e.g. 'Spain').
        description: Brief overview of what makes the destination appealing.
        price_per_night: Estimated accommodation cost per night in USD.
        rating: Rating out of 5.0 (default 4.5).
        tags: Comma-separated list of tags (e.g. 'beach, culture, food').

    Returns:
        A confirmation string stating whether the destination was successfully saved.
    """
    try:
        db = _get_firestore_client()
        doc_id = re.sub(r"[^a-z0-9]+", "-", f"{name}-{country}".lower()).strip("-")
        doc_ref = db.collection("destinations").document(doc_id)

        parsed_tags = [t.strip().lower() for t in tags.split(",") if t.strip()] if isinstance(tags, str) else tags

        data = {
            "name": name,
            "country": country,
            "description": description,
            "price_per_night": float(price_per_night),
            "rating": float(rating),
            "tags": parsed_tags,
        }
        doc_ref.set(data)
        return f"Successfully added destination '{name}' ({country}) to Firestore with ID '{doc_id}'."
    except Exception as e:
        return f"Error adding destination to Firestore: {str(e)}"


def book_travel_package(
    destination_name: str,
    traveler_name: str,
    start_date: str,
    num_nights: int = 3,
    num_guests: int = 1,
) -> str:
    """Book a travel package reservation for a destination and save it to Firestore.

    Args:
        destination_name: Name of the target destination (e.g. 'Tokyo', 'Paris').
        traveler_name: Full name of the primary traveler.
        start_date: Desired trip start date in YYYY-MM-DD format.
        num_nights: Number of nights for the stay (default 3).
        num_guests: Number of travelers (default 1).

    Returns:
        A confirmation summary string with booking code and total price calculation.
    """
    try:
        db = _get_firestore_client()
        booking_code = f"TC-{uuid.uuid4().hex[:6].upper()}"
        doc_ref = db.collection("bookings").document(booking_code)

        # Lookup destination for price calculation if available
        docs = db.collection("destinations").stream()
        price_per_night = 200.0
        for doc in docs:
            item = doc.to_dict()
            if destination_name.lower() in item.get("name", "").lower():
                price_per_night = float(item.get("price_per_night", 200.0))
                destination_name = item.get("name", destination_name)
                break

        total_price = price_per_night * num_nights * num_guests

        booking_data = {
            "booking_code": booking_code,
            "destination_name": destination_name,
            "traveler_name": traveler_name,
            "start_date": start_date,
            "num_nights": int(num_nights),
            "num_guests": int(num_guests),
            "total_price": total_price,
            "status": "CONFIRMED",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        doc_ref.set(booking_data)

        return (
            f"🎉 Booking Confirmed! Code: {booking_code} | Traveler: {traveler_name} | "
            f"Destination: {destination_name} | Dates: {start_date} ({num_nights} nights, {num_guests} guest(s)) | "
            f"Total Price: ${total_price:.2f}"
        )
    except Exception as e:
        return f"Error creating booking in Firestore: {str(e)}"


def get_real_time_weather(city: str) -> str:
    """Fetch live real-time weather report for a destination city using Open-Meteo public API.

    Args:
        city: Name of the destination city (e.g. 'Tokyo', 'Paris', 'Zurich', 'Maui').

    Returns:
        A string summarizing the current live temperature in Celsius and wind speed.
    """
    try:
        encoded_city = urllib.parse.quote(city.strip())
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "TravelConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            geo_data = json.loads(response.read().decode("utf-8"))

        results = geo_data.get("results")
        if not results:
            return f"Could not find geographic coordinates for city: '{city}'."

        location = results[0]
        lat = location["latitude"]
        lon = location["longitude"]
        city_name = location.get("name", city)
        country = location.get("country", "")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        req_w = urllib.request.Request(weather_url, headers={"User-Agent": "TravelConcierge/1.0"})
        with urllib.request.urlopen(req_w, timeout=5) as response_w:
            w_data = json.loads(response_w.read().decode("utf-8"))

        current = w_data.get("current_weather", {})
        temp_c = current.get("temperature", "N/A")
        wind = current.get("windspeed", "N/A")

        return (
            f"🌤️ Live Weather for {city_name} ({country}): "
            f"Temperature: {temp_c}°C | Wind Speed: {wind} km/h"
        )
    except Exception as e:
        return f"Error fetching live weather for '{city}': {str(e)}"


def geocode_address(address: str) -> str:
    """Geocode an address or landmark into geographic coordinates (latitude and longitude) using Google Maps Geocoding API.

    Args:
        address: Street address, landmark, or city name (e.g. 'Tokyo Station' or 'Eiffel Tower, Paris').

    Returns:
        A string containing formatted address, latitude, longitude, and place_id.
    """
    api_key = _get_maps_api_key()
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    try:
        encoded_addr = urllib.parse.quote(address.strip())
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_addr}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "TravelConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        if data.get("status") != "OK" or not data.get("results"):
            return f"Geocoding failed for '{address}': {data.get('status', 'No results found')}"

        res = data["results"][0]
        formatted_address = res.get("formatted_address", address)
        location = res.get("geometry", {}).get("location", {})
        lat = location.get("lat")
        lng = location.get("lng")
        place_id = res.get("place_id", "")

        return (
            f"📍 Geocoded '{address}':\n"
            f"- Address: {formatted_address}\n"
            f"- Location: ({lat}, {lng})\n"
            f"- Place ID: {place_id}"
        )
    except Exception as e:
        return f"Error geocoding address '{address}': {str(e)}"


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "restaurant",
    radius_meters: float = 1000.0,
) -> str:
    """Search for nearby places of a given type around coordinates using Google Places API (New).

    Args:
        latitude: Latitude coordinate of the central location (e.g. 35.6812).
        longitude: Longitude coordinate of the central location (e.g. 139.7671).
        place_type: Type of place to search for (e.g. 'restaurant', 'tourist_attraction', 'lodging', 'cafe').
        radius_meters: Radius in meters around the center location (default 1000.0).

    Returns:
        A string listing nearby places with key fields (name, formatted address, location coordinates, and rating).
    """
    api_key = _get_maps_api_key()
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating",
            "User-Agent": "TravelConcierge/1.0",
        }
        body = {
            "includedTypes": [place_type],
            "maxResultCount": 5,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": float(latitude),
                        "longitude": float(longitude),
                    },
                    "radius": float(radius_meters),
                }
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        places = data.get("places", [])
        if not places:
            return f"No nearby '{place_type}' places found within {radius_meters}m of ({latitude}, {longitude})."

        lines = [f"Found {len(places)} nearby '{place_type}' place(s):"]
        for place in places:
            display_name = place.get("displayName", {}).get("text", "Unknown Name")
            address = place.get("formattedAddress", "N/A")
            loc = place.get("location", {})
            rating = place.get("rating", "N/A")
            lines.append(
                f"- {display_name} | Address: {address} | Location: ({loc.get('latitude')}, {loc.get('longitude')}) | Rating: {rating}"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"Error searching nearby places: {str(e)}"


async def generate_destination_image(
    destination_name: str,
    prompt: str = "",
    tool_context: ToolContext | None = None,
) -> str:
    """Generate a scenic travel photo for a destination using gemini-3.1-flash-lite-image in the global region,
    save it as an ADK artifact for Playground, upload it to Cloud Storage, and return its public HTTPS URL.

    Args:
        destination_name: Name of the travel destination or city (e.g. 'Tokyo', 'Paris', 'Maui').
        prompt: Optional specific description for the image.
        tool_context: Injected ADK ToolContext used to save the image as an artifact in Playground.

    Returns:
        The public HTTPS URL of the uploaded image on Cloud Storage (https://storage.googleapis.com/<bucket>/<object>).
    """
    try:
        final_prompt = prompt.strip() or f"A realistic, vibrant scenic travel photo of {destination_name}"

        # 1. Call gemini-3.1-flash-lite-image model in global location
        client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=final_prompt,
        )

        part = response.candidates[0].content.parts[0]
        image_bytes = part.inline_data.data
        mime_type = part.inline_data.mime_type or "image/jpeg"

        clean_slug = re.sub(r"[^a-z0-9]+", "-", destination_name.lower()).strip("-") or "destination"
        filename = f"{clean_slug}-{uuid.uuid4().hex[:6]}.jpg"

        # 2. Save artifact using tool_context if available (so it shows up in Playground's Artifacts panel)
        if tool_context is not None:
            try:
                artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                await tool_context.save_artifact(filename=filename, artifact=artifact_part)
            except Exception as e:
                print(f"Warning saving artifact: {e}")

        # 3. Upload same image bytes directly to public GCS bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(PUBLIC_GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{PUBLIC_GCS_BUCKET_NAME}/{filename}"
        return public_url
    except Exception as e:
        return f"Error generating destination image: {str(e)}"


async def generate_destination_video(
    destination_name: str,
    prompt: str = "",
    tool_context: ToolContext | None = None,
) -> str:
    """Generate a short video for a travel destination using gemini-omni-flash-preview in the global region,
    save it as an ADK artifact for Playground, upload it to Cloud Storage, and return its public HTTPS URL.

    Args:
        destination_name: Name of the travel destination or item (e.g. 'Paris', 'Tokyo', 'Bali').
        prompt: Optional description for the video scene.
        tool_context: Injected ADK ToolContext used to save the video as an artifact in Playground.

    Returns:
        The public HTTPS URL of the uploaded video on Cloud Storage (https://storage.googleapis.com/<bucket>/<object>).
    """
    try:
        final_prompt = prompt.strip() or f"A vibrant scenic preview video of {destination_name} travel destination"

        client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=final_prompt,
        )

        import base64
        if hasattr(interaction, "output_video") and hasattr(interaction.output_video, "data"):
            video_bytes = base64.b64decode(interaction.output_video.data)
        elif hasattr(interaction, "output") and hasattr(interaction.output, "data"):
            video_bytes = base64.b64decode(interaction.output.data)
        else:
            raise ValueError(f"Unexpected response structure from gemini-omni-flash-preview: {interaction}")

        clean_slug = re.sub(r"[^a-z0-9]+", "-", destination_name.lower()).strip("-") or "destination"
        filename = f"{clean_slug}-{uuid.uuid4().hex[:6]}.mp4"
        mime_type = "video/mp4"

        if tool_context is not None:
            try:
                artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
                await tool_context.save_artifact(filename=filename, artifact=artifact_part)
            except Exception as e:
                print(f"Warning saving video artifact: {e}")

        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(PUBLIC_GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{PUBLIC_GCS_BUCKET_NAME}/{filename}"
        return public_url
    except Exception as e:
        return f"Error generating destination video: {str(e)}"


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


# Build system prompt using A2uiSchemaManager version 0.8 and BasicCatalog
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are the Travel Concierge assistant. You help users explore travel destinations, "
        "search the destination catalog stored in Firestore database, add new destinations, "
        "book travel package reservations, get live real-time weather reports for any city via Open-Meteo, "
        "geocode addresses using Google Geocoding API, find nearby places using Google Places API (New), "
        "generate realistic destination preview photos, generate short destination preview videos, execute Python code safely in a sandbox for calculations, "
        "and remember user preferences, dietary restrictions, and allergies across sessions using Memory Bank. "
        "Always pay close attention to any allergies or dietary constraints the user mentions, remember them for future conversations, "
        "and filter or customize all destination, restaurant, and itinerary recommendations to accommodate those allergies safely."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        get_weather,
        get_current_time,
        search_destinations,
        add_destination,
        book_travel_package,
        get_real_time_weather,
        geocode_address,
        find_nearby_places,
        generate_destination_image,
        generate_destination_video,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
