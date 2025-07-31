from dotenv import load_dotenv
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from transformers import pipeline
from langchain.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing import Annotated, TypedDict, List
import datetime
from dataclasses import dataclass
import firebase_admin
from firebase_admin import credentials, firestore
import re
from google import genai
from serpapi import GoogleSearch
import os
import requests
from flask import Flask, request, send_from_directory
from pydub import AudioSegment
from elevenlabs.client import ElevenLabs
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import time
import threading
import uuid
import json

load_dotenv()
elevenlabs_client = ElevenLabs()

firebase_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
cred_dict = json.loads(firebase_json_str)
cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
TO_NUMBER = os.getenv("TO_NUMBER")
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

@dataclass
class Bookmark:
    place: str
    note: str
    timestamp: str
    category: str = ""
    location: str = ""


@dataclass
class UserInterest:
    likes: List[str]
    dislikes: List[str]
    visited_places: List[str]
    preferred_time: str = "morning"
    budget_range: str = "moderate"
    current_location: str = ""


class FirebaseUserManager:
    def __init__(self,db_instance):
        self.db = db_instance
        self.current_user_id = None
        self.current_user_data = None

    def validate_phone_number(self, phone):
        """Validate phone number format"""
        phone = re.sub(r'\D', '', phone)
        if len(phone) < 10 or len(phone) > 15:
            return None
        return phone

    def get_or_create_user(self, phone_number):
        """Get existing user or create new one"""
        phone_number = self.validate_phone_number(phone_number)
        if not phone_number:
            raise ValueError("Invalid phone number format")

        user_ref = db.collection('users').document(phone_number)
        user_doc = user_ref.get()

        if user_doc.exists:
            self.current_user_id = phone_number
            self.current_user_data = user_doc.to_dict()
            return False, self.current_user_data
        else:
            default_data = {
                'phone_number': phone_number,
                'name': '',
                'bookmarks': [],
                'interests': {
                    'likes': [],
                    'dislikes': [],
                    'visited_places': [],
                    'preferred_time': "morning",
                    'budget_range': "moderate",
                    'current_location': ""
                },
                'current_plan': {},
                'story_history': [],
                'detected_language': "Unknown",
                'created_at': firestore.SERVER_TIMESTAMP,
                'last_active': firestore.SERVER_TIMESTAMP
            }

            user_ref.set(default_data)
            self.current_user_id = phone_number
            self.current_user_data = default_data
            return True, default_data

    def update_user_name(self, name):
        """Update user's name"""
        if self.current_user_id:
            db.collection('users').document(self.current_user_id).update({
                'name': name,
                'last_active': firestore.SERVER_TIMESTAMP
            })
            self.current_user_data['name'] = name

    def load_chat_history(self):
        """Load chat history for the current user from Firestore."""
        if not self.current_user_id:
            return []  # No user selected, return empty history

        user_doc_ref = self.db.collection('users').document(self.current_user_id)
        user_doc = user_doc_ref.get()

        if user_doc.exists:
            chat_history_data = user_doc.to_dict().get('chat_history', [])
            # Convert stored dicts back to Langchain Message objects
            loaded_messages = []
            for msg_data in chat_history_data:
                if msg_data.get("type") == "human":
                    loaded_messages.append(HumanMessage(content=msg_data.get("content")))
                elif msg_data.get("type") == "ai":
                    loaded_messages.append(AIMessage(content=msg_data.get("content")))
                elif msg_data.get("type") == "system":
                    loaded_messages.append(SystemMessage(content=msg_data.get("content")))
            return loaded_messages
        return []

    def save_chat_history(self, messages: List[str]):
        """Save chat history for the current user to Firestore."""
        if self.current_user_id:
            # Convert Langchain Message objects to dictionaries for storage
            chat_history_data = []
            for msg in messages:
                chat_history_data.append({"type": msg.type, "content": msg.content})

            self.update_user_data('chat_history', chat_history_data)

    def update_detected_language(self, language):
        """Update user's detected language"""
        if self.current_user_id:
            self.update_user_data('detected_language', language)
            self.current_user_data['detected_language'] = language

    def get_user_data(self):
        """Get current user's data"""
        return self.current_user_data

    def ensure_user_exists(self, phone_number):
        """Ensures the user exists and sets current_user_id and current_user_data."""
        self.get_or_create_user(phone_number)

    def update_user_data(self, field, value):
        """Update specific field in user data"""
        if self.current_user_id:
            db.collection('users').document(self.current_user_id).update({
                field: value,
                'last_active': firestore.SERVER_TIMESTAMP
            })
            self.current_user_data[field] = value

    def add_bookmark(self, bookmark_data):
        """Add bookmark to user's data"""
        if self.current_user_id:
            current_bookmarks = self.current_user_data.get('bookmarks', [])
            current_bookmarks.append(bookmark_data)
            self.update_user_data('bookmarks', current_bookmarks)
            self.current_user_data['bookmarks'] = current_bookmarks

    def add_story(self, story_data):
        """Add story to user's history"""
        if self.current_user_id:
            current_stories = self.current_user_data.get('story_history', [])
            current_stories.append(story_data)
            self.update_user_data('story_history', current_stories)
            self.current_user_data['story_history'] = current_stories

    def update_interests(self, interests_data):
        """Update user's interests"""
        if self.current_user_id:
            self.update_user_data('interests', interests_data)
            self.current_user_data['interests'] = interests_data

user_manager = FirebaseUserManager(db)
google_client = genai.Client()

def transcribe_and_identify_language(audio_file_path: str):
    """
    Uploads an audio file, sends it to Gemini for transcription and language identification,
    and returns the detected language and the transcribed text.
    """
    try:
        myfile = google_client.files.upload(file=audio_file_path)
        response = google_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                "First, identify the language of this audio clip. Then, provide a perfect word-for-word transcription. Format your response as: 'Language: [Detected Language]\nTranscription: [Perfect Transcription]'",
                myfile
            ]
        )
        full_response_text = response.text
        detected_language = "Unknown"
        transcribed_text = full_response_text
        if "Language:" in full_response_text and "Transcription:" in full_response_text:
            lines = full_response_text.split('\n')
            for line in lines:
                if line.startswith("Language:"):
                    detected_language = line.replace("Language:", "").strip()
                elif line.startswith("Transcription:"):
                    transcribed_text = line.replace("Transcription:", "").strip()
                    transcription_start_index = full_response_text.find("Transcription:") + len("Transcription:")
                    transcribed_text = full_response_text[transcription_start_index:].strip()
                    break

        return detected_language, transcribed_text

    except Exception as e:
        print(f"An error occurred: {e}")
        return "Error", f"Could not process audio: {e}"

def detect_mood(text):
    emotion_classifier = pipeline("text-classification", model="j-hartmann/emotion-english-distilroberta-base")
    mood_result = emotion_classifier(text)
    label = mood_result[0]['label'].lower()
    label_map = {
        "joy": "Happy",
        "sadness": "Sad",
        "anger": "Angry",
        "fear": "Fearful",
        "disgust": "Disgusted",
        "surprise": "Surprised",
        "neutral": "Neutral"
    }
    return label_map.get(label, "Neutral")


def get_current_time(*args, **kwargs):
    """Returns the current time in H:MM AM/PM format."""
    import datetime
    now = datetime.datetime.now()
    return now.strftime("%I:%M %p")

def day_planner_tool(mood: str, time_slot: str, specific_interests: str, location: str) -> str:
    """Generate a customized day itinerary for any city based on user preferences."""

    user_data = user_manager.get_user_data()
    user_interests = user_data.get('interests', {})
    user_interests['current_location'] = location
    user_likes = user_interests.get('likes', [])
    user_dislikes = user_interests.get('dislikes', [])
    user_visited_places = user_interests.get('visited_places', [])
    user_preferred_time = user_interests.get('preferred_time',
                                             'not specified')
    user_budget_range = user_interests.get('budget_range', 'not specified')

    prompt = f"""Create a detailed day itinerary for {location} with the following specifications:

    Location: {location}
    Mood: {mood}
    Time Slot: {time_slot}
    Specific Interests: {specific_interests}

    User Profile:
    - Likes: {', '.join(user_likes)}
    - Dislikes: {', '.join(user_dislikes)}
    - Previously visited in {location}: {', '.join([p for p in user_visited_places if location.lower() in p.lower()])}
    - Preferred time: {user_preferred_time}
    - Budget range: {user_budget_range}

    Generate a structured itinerary with time slots and activities.
    Include specific {location} locations, brief descriptions, and practical tips.
    Focus on authentic local experiences and hidden gems when possible.
    Consider local culture, weather, and transportation.

    Format as a clear, readable itinerary with time slots and detailed descriptions.
    """

    messages = [
        SystemMessage(
            content=f"You are a local travel expert for {location} who creates personalized itineraries. Provide practical, location-specific advice with local insights."),
        HumanMessage(content=prompt)
    ]

    response = llm.invoke(messages)

    user_manager.update_user_data('current_plan', {
        "itinerary": response.content,
        "mood": mood,
        "location": location,
        "date": datetime.datetime.now().isoformat(),
        "preferences": {
            "time_slot": time_slot,
            "interests": specific_interests
        }
    })
    return f" **Here’s your day plan for {location}** (from {time_slot}):\n\n{response.content}"


def bookmark_tool(place: str, note: str, category: str, location: str) -> str:
    """Save a place to user's bookmarks with personal notes."""

    user_data = user_manager.get_user_data()
    bookmarks = user_data.get('bookmarks', [])
    existing = [b for b in bookmarks if
                b.get('place', '').lower() == place.lower() and b.get('location', '').lower() == location.lower()]

    if existing:
        return f"'{place}' in {location} is already bookmarked with note: '{existing[0].note}'"

    bookmark_data = {
        'place': place,
        'note': note,
        'category': category,
        'location': location,
        'timestamp': datetime.datetime.now().isoformat()
    }
    user_manager.add_bookmark(bookmark_data)
    prompt = f"""Enhance this bookmark with useful local context for {location}:

    Place: {place}
    Location: {location}
    User Note: {note}
    Category: {category}

    Provide brief, practical information about:
    1. Best time to visit
    2. What makes it special locally
    3. Nearby attractions in {location}
    4. Local tips or insider knowledge

    Keep it concise and {location}-specific.
    """

    messages = [
        SystemMessage(
            content=f"You are a {location} local expert providing practical travel advice with insider knowledge."),
        HumanMessage(content=prompt)
    ]

    enhancement = llm.invoke(messages).content

    return f" '{place}' bookmarked successfully in {location}!\n\n Your note: {note}\n\n Local insights:\n{enhancement}\n\n Total bookmarks: {len(user_data['bookmarks'])}"


def get_bookmarks_tool(location: str = "") -> str:
    """Retrieve user bookmarks, optionally filtered by location."""

    user_data = user_manager.get_user_data()
    bookmarks = user_data.get('bookmarks', [])

    filtered_bookmarks = []
    if location:
        for b in bookmarks:
            bookmark_location = b.get('location')
            if bookmark_location and location.lower() in bookmark_location.lower():
                filtered_bookmarks.append(b)
        header = f"Your bookmarks in {location}:"
    else:
        filtered_bookmarks = bookmarks
        header = "All your bookmarks:"

    if not filtered_bookmarks:
        return f"No bookmarks found{' in ' + location if location else ''}. Start exploring and bookmark your favorite places!"

    result = [header]
    for b in filtered_bookmarks:
        place = b.get("place", "N/A")
        note = b.get("note", "N/A")
        category = b.get("category", "N/A")
        added_date = b.get("timestamp", "N/A")
        if added_date != "N/A":
            added_date = added_date[:10]
        location_str = b.get("location", "N/A")

        result.append(f"\n {place} ({location_str})")
        result.append(f"    {note}")
        result.append(f"    Category: {category}")
        result.append(f"    Added: {added_date}")

    return "\n".join(result)


def poi_tool(interest_type: str, location: str, hidden_gems_only: bool = False) -> str:
    """Recommend points of interest and hidden gems in any city."""

    user_data = user_manager.get_user_data()
    user_interests = user_data.get('interests', {})
    user_likes = user_interests.get('likes', [])
    user_dislikes = user_interests.get('dislikes', [])
    user_visited_places = user_interests.get('visited_places', [])
    user_budget_range = user_interests.get('budget_range', 'not specified')

    gem_instruction = "Focus ONLY on hidden gems, local secrets, and off-the-beaten-path places" if hidden_gems_only else "Include both popular attractions and hidden gems"

    prompt = f"""Recommend places in {location} for someone interested in {interest_type}:

    Location: {location}
    Interest Type: {interest_type}
    Hidden Gems Focus: {hidden_gems_only}

   User Profile:
    - Likes: {', '.join(user_likes)}
    - Dislikes: {', '.join(user_dislikes)}
    - Already visited in {location}: {', '.join([p for p in user_visited_places if location.lower() in p.lower()])}
    - Budget preference: {user_budget_range}

    Instructions: {gem_instruction}

    Provide 3-4 recommendations with:
    1. Place name and location within {location}
    2. Brief description and why it's special
    3. Best time to visit
    4. Approximate cost/budget level
    5. Local tips or insider knowledge

    Focus on authentic, local experiences that match the user's interests.
    Avoid places they've already visited.
    """

    messages = [
        SystemMessage(
            content=f"You are a {location} local who knows the city's best-kept secrets, authentic experiences, and local hotspots."),
        HumanMessage(content=prompt)
    ]

    response = llm.invoke(messages)

    return f" {interest_type.title()} recommendations in {location}:\n\n{response.content}"


def interest_tool(interest: str, action: str, location: str) -> str:
    """Manage user interests and preferences."""

    user_data = user_manager.get_user_data()
    user_interests = user_data.get('interests', {})

    if 'likes' not in user_interests:
        user_interests['likes'] = []
    if 'dislikes' not in user_interests:
        user_interests['dislikes'] = []

    if action == "add_like":
        if interest not in user_interests['likes']:
            user_interests['likes'].append(interest)
            user_manager.update_interests(user_interests)
            message = f" Added '{interest}' to your likes"
        else:
            message = f"'{interest}' is already in your likes"

    elif action == "add_dislike":
        if interest not in user_interests['dislikes']:
            user_interests['dislikes'].append(interest)
            user_manager.update_interests(user_interests)
            message = f" Added '{interest}' to your dislikes"
        else:
            message = f"'{interest}' is already in your dislikes"

    elif action == "remove":
        if interest in user_interests['likes']:
            user_interests['likes'].remove(interest)
            user_manager.update_interests(user_interests)
            message = f" Removed '{interest}' from your likes"
        elif interest in user_interests['dislikes']:
            user_interests['dislikes'].remove(interest)
            user_manager.update_interests(user_interests)
            message = f" Removed '{interest}' from your dislikes"
        else:
            message = f"'{interest}' not found in your preferences"

    else:
        return " Invalid action. Use 'add_like', 'add_dislike', or 'remove'"

    prompt = f"""Based on the user's interest in '{interest}', suggest 3-5 related interests they might enjoy in {location}.

    Current likes: {', '.join(user_interests['likes'])}
    Current dislikes: {', '.join(user_interests['dislikes'])}
    Location: {location}

    Provide brief explanations for each suggestion, focusing on what's available in {location}.
    """

    messages = [
        SystemMessage(
            content=f"You are a {location} travel expert who understands how different interests connect and what's available locally."),
        HumanMessage(content=prompt)
    ]

    suggestions = llm.invoke(messages).content

    return f"{message}\n\n Related interests you might enjoy in {location}:\n{suggestions}"


def story_mode_tool(locations: List[str], theme: str, perspective: str, location: str) -> str:
    """Generate an engaging narrative story about visiting locations in any city."""

    user_data = user_manager.get_user_data()
    user_interests = user_data.get('interests', {})
    locations_str = ', '.join(locations)

    prompt = f"""Create an engaging {theme} story about visiting these locations in {location}:

    City: {location}
    Locations: {locations_str}
    Theme: {theme}
    Perspective: {perspective}

    User Profile (for personalization):
     - Likes: {', '.join(user_interests.get('likes', []))}
    - Dislikes: {', '.join(user_interests.get('dislikes', []))}

    Story Requirements:
    1. Connect all locations in a logical sequence within {location}
    2. Include local culture, history, and authentic details about {location}
    3. Create vivid descriptions of each place
    4. Make it engaging and immersive
    5. Include practical details naturally (transportation, timing, local tips)
    6. Use {perspective} perspective throughout
    7. Incorporate local customs, food, and cultural elements

    Length: 600-800 words
    Style: Engaging, descriptive, with local insights and cultural authenticity
    """

    messages = [
        SystemMessage(
            content=f"You are a master storyteller who knows {location}'s history, culture, hidden stories, and local life intimately. Create immersive narratives that educate and entertain."),
        HumanMessage(content=prompt)
    ]

    story = llm.invoke(messages).content

    story_entry = {
        "story": story,
        "locations": locations,
        "theme": theme,
        "perspective": perspective,
        "location": location,
        "timestamp": datetime.datetime.now().isoformat()
    }

    user_manager.add_story(story_entry)

    return f" Your {theme} story in {location}:\n\n{story}"

def get_live_events_tool(city: str) -> str:
    """Get live events happening in a specific city this weekend."""
    try:
        search = GoogleSearch({
            "engine": "google_events",
            "q": f"events in {city} this weekend",
            "api_key": os.getenv("SERP_API_KEY")  # Add your SerpAPI key to .env file
        })
        results = search.get_dict()
        events = results.get("events_results", [])

        if not events:
            return f" No live events found for {city} this weekend. Try checking local event websites or social media for updated listings."

        event_list = [f" Live Events in {city} this weekend:\n"]
        for event in events[:5]:
            title = event.get('title', 'Unnamed Event')
            venue = event.get('venue', {}).get('name', 'Venue TBA')
            date = event.get('date', {}).get('start_date', 'Date TBA')
            event_list.append(f"• {title}")
            event_list.append(f"   {venue}")
            event_list.append(f"   {date}\n")

        return "\n".join(event_list)
    except Exception as e:
        return f"Sorry, I couldn't fetch live events for {city} right now. Please try again later or check local event listings."


def get_weather_tool(city: str) -> str:
    """Get current weather information for a specific city."""
    try:
        search = GoogleSearch({
            "engine": "google",
            "q": f"weather in {city}",
            "api_key": os.getenv("SERP_API_KEY")
        })
        results = search.get_dict()
        weather_box = results.get("answer_box", {})

        if not weather_box:
            return f"🌦 Weather information for {city} is not available right now. Please check a weather app or website."

        temperature = weather_box.get('temperature', 'N/A')
        description = weather_box.get('weather', 'N/A')
        humidity = weather_box.get('humidity', 'N/A')
        wind = weather_box.get('wind', 'N/A')

        weather_info = f"""🌦 Current Weather in {city}:

 Temperature: {temperature}
 Conditions: {description}
 Humidity: {humidity}
 Wind: {wind}

Perfect for planning your day out! Let me know if you need activity recommendations based on this weather."""

        return weather_info
    except Exception as e:
        return f"Sorry, I couldn't fetch weather information for {city} right now. Please try again later."


def get_news_tool(location: str, topic: str = "") -> str:
    """Get top current news for a specific location, optionally filtered by topic."""
    try:
        # If no topic specified, get general local news
        if not topic or topic.lower() in ['news', 'latest', 'top news', 'current']:
            query = f"top news {location} today"
        else:
            query = f"{topic} {location} news"

        search = GoogleSearch({
            "engine": "google_news",
            "q": query,
            "api_key": os.getenv("SERP_API_KEY")
        })
        results = search.get_dict()
        news = results.get("news_results", [])

        if not news:
            return f" No recent news found for {location}. The city might be having a quiet news day!"

        header = f" Top News in {location}:\n" if not topic or topic.lower() in ['news', 'latest', 'top news',
                                                                                  'current'] else f" Latest on '{topic}' in {location}:\n"
        news_list = [header]

        for i, article in enumerate(news[:5], 1):  # Limit to top 5 articles
            title = article.get('title', 'No title')
            source = article.get('source', 'Unknown source')
            date = article.get('date', 'Recent')
            snippet = article.get('snippet', '')

            news_list.append(f"{i}. {title}")
            news_list.append(f"{source} • {date}")
            if snippet:
                news_list.append(f"{snippet}")
            news_list.append("")

        return "\n".join(news_list)
    except Exception as e:
        return f"Sorry, I couldn't fetch news for {location} right now. Please try again later."


def get_places_tool(query: str, location: str) -> str:
    """Find specific types of places (restaurants, hospitals, shops, etc.) in a given location."""
    try:
        search = GoogleSearch({
            "engine": "google",
            "q": f"{query} in {location}",
            "api_key": os.getenv("SERP_API_KEY")
        })
        results = search.get_dict()
        places = results.get("local_results", {}).get("places", [])

        if not places:
            # Try alternative search structure
            places = results.get("places_results", [])

        if not places:
            return f" No places found for '{query}' in {location}. Try a different search term or broader location."

        places_list = [f" Places for '{query}' in {location}:\n"]
        for place in places[:5]:
            title = place.get('title', place.get('name', 'Unnamed Place'))
            address = place.get('address', 'Address not available')
            rating = place.get('rating', 'No rating')
            phone = place.get('phone', '')

            places_list.append(f"• {title}")
            places_list.append(f"   {address}")
            if rating != 'No rating':
                places_list.append(f" Rating: {rating}")
            if phone:
                places_list.append(f"{phone}")
            places_list.append("")

        return "\n".join(places_list)
    except Exception as e:
        return f"Sorry, I couldn't find places for '{query}' in {location} right now. Please try again later."

def get_user_profile_tool(location: str) -> str:
    """Get user profile with location-specific data."""

    user_data = user_manager.get_user_data()
    user_interests = user_data.get('interests', {})
    bookmarks = user_data.get('bookmarks', [])
    story_history = user_data.get('story_history', [])
    current_plan = user_data.get('current_plan', {})
    location_bookmarks = [b for b in bookmarks if location.lower() in b.get('location', '').lower()]
    location_stories = [s for s in story_history if location.lower() in s.get("location", "").lower()]

    profile = f"""👤 Your Travel Profile:

    Interests:
        Likes: {', '.join(user_interests.get('likes', []))}
        Dislikes: {', '.join(user_interests.get('dislikes', []))}
        Preferred time: {user_interests.get('preferred_time', 'morning')}
        Budget range:  {user_interests.get('budget_range', 'moderate')}
        Language: {user_data.get('detected_language', 'Unknown')}

    In {location}:
        Bookmarks: {len(location_bookmarks)}
        Stories created: {len(location_stories)}
        Current plan: {'Yes' if current_plan.get('location', '') == location.lower() else 'No'}

    Overall:
        Total bookmarks: {len(user_data['bookmarks'])}
        Total stories: {len(user_data['story_history'])}
        Cities explored: {len(set(b.get('location', '') for b in bookmarks))}
"""

    return profile

city_explorer_tools = [
    Tool(
        name="DayPlannerTool",
        func=lambda query: day_planner_tool(
            mood=query.split('|')[0] if '|' in query else "neutral",
            time_slot=query.split('|')[1] if '|' in query and len(query.split('|')) > 1 else "full day",
            specific_interests=query.split('|')[2] if '|' in query and len(
                query.split('|')) > 2 else "local attractions",
            location=query.split('|')[3] if '|' in query and len(query.split('|')) > 3 else "current location"
        ),
        description=(
            "Generate a customized day itinerary for any city based on user preferences. "
            "This tool provides a structured plan with activities, time slots, and practical tips. "
            "Use it when the user explicitly asks for a 'day plan', 'itinerary', or 'what to do in X city'.\n"
            "Format: 'mood|time_slot|specific_interests|location'\n"
            "Example: 'energetic|morning to evening|history and art museums|London'\n"
            "mood: (e.g., 'relaxing', 'adventurous', 'neutral')\n"
            "time_slot: (e.g., 'morning', 'afternoon', 'full day', '9am-6pm')\n"
            "specific_interests: (e.g., 'food', 'shopping', 'nature', 'historical sites')\n"
            "location: (e.g., 'Paris', 'Tokyo', '{current_location}') - **ALWAYS provide a specific city**"
        )
    ),
    Tool(
        name="BookmarkTool",
        func=lambda query: bookmark_tool(
            place=query.split('|')[0],
            note=query.split('|')[1] if '|' in query and len(query.split('|')) > 1 else "No note provided.",
            category=query.split('|')[2] if '|' in query and len(query.split('|')) > 2 else "general",
            location=query.split('|')[3] if '|' in query and len(query.split('|')) > 3 else "current location"
        ),
        description=(
            "Save a specific place to the user's personal bookmarks with a note, category, and location. "
            "Use this when the user expresses a desire to 'save', 'bookmark', 'remember', or 'add to favorites' a place.\n"
            "Format: 'place|note|category|location'\n"
            "Example: 'Eiffel Tower|Great for sunset views|landmark|Paris'\n"
            "place: (e.g., 'Central Park', 'British Museum')\n"
            "note: (a short personal note about the place)\n"
            "category: (e.g., 'attraction', 'restaurant', 'park', 'museum', 'shop')\n"
            "location: (e.g., 'New York', 'London', '{current_location}') - **ALWAYS provide a specific city**"
        )
    ),
    Tool(
        name="GetBookmarksTool",
        func=lambda query: get_bookmarks_tool(location=query if query else ""),
        description=(
            "Retrieve and list all of the user's saved bookmarks. "
            "Optionally filter bookmarks by a specific location. "
            "Use this when the user asks to 'see my bookmarks', 'what have I saved', or 'show my saved places in X city'.\n"
            "Format: 'location' (optional, e.g., 'Paris') or leave empty for all bookmarks.\n"
            "Example: 'London' (to get bookmarks only in London)\n"
            "Example: '' (empty string to get all bookmarks from all locations)"
        )
    ),
    Tool(
        name="POITool",
        func=lambda query: poi_tool(
            interest_type=query.split('|')[0],
            location=query.split('|')[1] if '|' in query and len(query.split('|')) > 1 else "current location",
            hidden_gems_only=query.split('|')[2].lower() == 'true' if '|' in query and len(
                query.split('|')) > 2 else False
        ),
        description=(
            "Recommend interesting points of interest (POIs), attractions, or activities in a given city, "
            "optionally focusing only on 'hidden gems' or local secrets. "
            "Use this when the user asks for 'recommendations', 'places to visit', 'things to do', 'hidden gems', "
            "'best restaurants', or similar discovery queries.\n"
            "Format: 'interest_type|location|hidden_gems_only'\n"
            "Example: 'local food|Tokyo|true' (for hidden food gems in Tokyo)\n"
            "interest_type: (e.g., 'food', 'museums', 'nature', 'nightlife', 'shopping', 'historical sites')\n"
            "location: (e.g., 'Kyoto', 'Rome', '{current_location}') - **ALWAYS provide a specific city**\n"
            "hidden_gems_only: (boolean, 'true' or 'false'. Use 'true' if user explicitly asks for 'hidden' or 'local' spots)"
        )
    ),
    Tool(
        name="InterestTool",
        func=lambda query: interest_tool(
            interest=query.split('|')[0],
            action=query.split('|')[1] if '|' in query and len(query.split('|')) > 1 else "add_like",
            location=query.split('|')[2] if '|' in query and len(query.split('|')) > 2 else "current location"
        ),
        description=(
            "Manage the user's personal likes, dislikes, and travel preferences. "
            "This tool updates the user's profile to personalize future recommendations. "
            "Use this when the user explicitly states they 'like', 'dislike', 'want to add', 'want to remove', or 'are interested in' something specific.\n"
            "Format: 'interest|action|location'\n"
            "Example: 'art galleries|add_like|Paris'\n"
            "interest: (e.g., 'museums', 'street food', 'hiking', 'nightlife')\n"
            "action: (string, required) Must be one of: 'add_like', 'add_dislike', or 'remove'\n"
            "location: (e.g., 'Barcelona', 'Singapore', '{current_location}') - **ALWAYS provide a specific city if relevant to the interest**"
        )
    ),
    Tool(
        name="StoryModeTool",
        func=lambda query: story_mode_tool(
            locations=query.split('|')[0].split(','),
            theme=query.split('|')[1] if '|' in query and len(query.split('|')) > 1 else "adventure",  # Default theme
            perspective=query.split('|')[2] if '|' in query and len(query.split('|')) > 2 else "third person",
            location=query.split('|')[3] if '|' in query and len(query.split('|')) > 3 else "current location"
        ),
        description=(
            "Generate an engaging narrative story about visiting specific locations in a given city. "
            "This tool creates creative travel narratives based on user-defined locations, theme, and perspective. "
            "Use this when the user explicitly asks for a 'story', 'narrative', 'tale', or 'fiction' about places.\n"
            "Format: 'location1,location2,location3|theme|perspective|city'\n"
            "Example: 'Eiffel Tower,Louvre Museum|romantic|first person|Paris'\n"
            "locations: (comma-separated list of specific places, e.g., 'Red Fort,India Gate')\n"
            "theme: (e.g., 'adventure', 'historical', 'romantic', 'mystery', 'quirky', 'whimsical')\n"
            "perspective: (e.g., 'first person', 'third person', 'tour guide', 'adventurer's log')\n"
            "city: (e.g., 'London', 'Delhi', '{current_location}') - **ALWAYS provide a specific city where the story takes place**"
        )
    ),
    Tool(
        name="GetUserProfileTool",
        func=lambda query: get_user_profile_tool(location=query if query else ""),
        description=(
            "Retrieve and display the user's comprehensive travel profile, "
            "including their interests, saved bookmarks, story history, and current plan details. "
            "Optionally filter profile data to be specific to a given location. "
            "Use this when the user asks to 'see my profile', 'my preferences', 'my saved data', or 'what do you know about me'.\n"
            "Format: 'location' (optional, e.g., 'London') or leave empty for a general profile.\n"
            "Example: 'Delhi' (to get profile data specific to Delhi)\n"
            "Example: '' (empty string to get overall profile data)"
        )
    ),
    Tool(
        name="LiveEventsTool",
        func=lambda query: get_live_events_tool(city=query),
        description=(
            "Get live events happening in a specific city this weekend. "
            "Use this when the user asks about 'events', 'concerts', 'shows', 'what's happening', "
            "or 'things to do this weekend' in a city.\n"
            "Format: Just provide the city name\n"
            "Example: 'Delhi' or 'New York' or 'London'\n"
            "city: (e.g., 'Mumbai', 'Paris', 'Tokyo') - **ALWAYS provide a specific city name**"
        )
    ),
    Tool(
        name="WeatherTool",
        func=lambda query: get_weather_tool(city=query),
        description=(
            "Get current weather information for a specific city. "
            "Use this when the user asks about 'weather', 'temperature', 'climate', "
            "'how's the weather', or 'should I bring an umbrella' for a location.\n"
            "Format: Just provide the city name\n"
            "Example: 'Mumbai' or 'London' or 'Tokyo'\n"
            "city: (e.g., 'Delhi', 'Paris', 'Singapore') - **ALWAYS provide a specific city name**"
        )
    ),
    Tool(
        name="NewsTool",
        func=lambda query: get_news_tool(
            location=query.split('|')[0],
            topic=query.split('|')[1] if '|' in query and len(query.split('|')) > 1 else ""
        ),
        description=(
            "Get top current news for a specific location, optionally filtered by topic. "
            "Use this when the user asks about 'news', 'latest updates', 'what's happening in', "
            "or wants current information about a city or region.\n"
            "Format: 'location|topic' (topic is optional)\n"
            "Example: 'Delhi' (for top news in Delhi) or 'Mumbai|transportation' (for transport news in Mumbai)\n"
            "location: (e.g., 'Delhi', 'Mumbai', 'Chennai') - **ALWAYS provide a specific city/location**\n"
            "topic: (optional, e.g., 'politics', 'weather', 'transportation', 'festivals') - provide if user wants specific type of news"
        )
    ),
    Tool(
        name="PlacesFinderTool",
        func=lambda query: get_places_tool(
            query=query.split('|')[0],
            location=query.split('|')[1] if '|' in query and len(query.split('|')) > 1 else "current location"
        ),
        description=(
            "Find specific types of places like hospitals, restaurants, ATMs, pharmacies, etc. in a given location. "
            "Use this when the user asks to 'find', 'locate', 'where is the nearest', "
            "or needs practical services and facilities.\n"
            "Format: 'search_query|location'\n"
            "Example: 'hospitals near me|Connaught Place Delhi' or 'ATMs|Mumbai Central'\n"
            "search_query: (e.g., 'hospitals', 'restaurants', 'ATMs', 'pharmacies', 'gas stations')\n" 
            "location: (e.g., 'Connaught Place Delhi', 'Times Square New York') - **ALWAYS provide specific location**"
        )
    )
]

tools = [
            Tool(
                name="Time",
                func=get_current_time,
                description="Useful for when you need to know the current time.",
            ),
        ] + city_explorer_tools

prompt_string = """You are CityGuide.AI – a cheerful, multilingual, and super helpful AI city guide.
Your job is to be the travel buddy every explorer wishes they had: informative, inspiring, occasionally funny, and always ready to uncover the hidden gems of any city.

The user you're speaking with is currently in {location}. They are feeling {mood}, and based on your previous conversations and stored preferences (see chat memory below), you must guide them like a local would—with warmth, wit, and wonderful recommendations.

Chat Memory:
{chat_history}

Available Tools:
{tools}

 TOOL USAGE RULES:
When the user asks for:
- Day plans, itineraries, schedules → Use DayPlannerTool
- Saving/bookmarking places → Use BookmarkTool  
- Viewing saved places → Use GetBookmarksTool
- Finding places/recommendations → Use POITool
- Managing likes/dislikes → Use InterestTool
- Creating stories → Use StoryModeTool
- Profile info → Use GetUserProfileTool
- Current events/shows → Use LiveEventsTool
- Weather information → Use WeatherTool  
- News and updates → Use NewsTool
- Finding specific places → Use PlacesFinderTool

TOOL FORMAT (use EXACTLY this format):
Action: [exact_tool_name]
Action Input: [properly_formatted_input]

 City Explorer Tools Usage:
-  DayPlannerTool: Format 'mood|time_slot|interests|location' (e.g., 'relaxing|10am-6pm|museums and cafes|{location}')
-  BookmarkTool: Format 'place|note|category|location' (e.g., 'Central Park|Perfect for jogging|park|{location}')
-  GetBookmarksTool: Just provide location name or leave empty for all bookmarks
-  POITool: Format 'interest_type|location|hidden_gems_only' (e.g., 'food|{location}|true')
-  InterestTool: Format 'interest|action|location' (actions: add_like, add_dislike, remove)
-  StoryModeTool: Format 'location1,location2|theme|perspective|city' (themes: adventure, historical, romantic, mystery)
-  GetUserProfileTool: Provide location for location-specific profile data
-  LiveEventsTool: Just provide city name (e.g., '{location}')
-  WeatherTool: Just provide city name (e.g., '{location}')
-  NewsTool: Format 'location|topic' (e.g., '{location}' or '{location}|transportation')
-  PlacesFinderTool: Format 'search_query|location' (e.g., 'hospitals|{location}')


IMPORTANT INSTRUCTIONS:
- ALWAYS use tools when the user's request matches tool capabilities
- Use the user's current location ({location}) in tool calls
- Format tool inputs EXACTLY as specified
- Be proactive with tool usage - don't just answer generically when tools can help
- Under no circumstances should you include emojis. Express tone using only words.

Now the user says:
"{input}"

Analyze the request and determine if you need to use a tool. If yes, use the Action/Action Input format. If no, respond directly.
"""

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    location: str
    mood: str
    chat_history: str
    detected_language: str

prompt_template = ChatPromptTemplate.from_template(prompt_string)
tool_node = ToolNode(tools)

def agent_node(state: AgentState):
    chat_history = "\n".join([f"{msg.type}: {msg.content}" for msg in state["messages"][:-1]])
    last_message = state["messages"][-1]
    detected_language = state.get("detected_language", "English")

    formatted_prompt = prompt_template.format(
        location=state["location"],
        mood=state["mood"],
        chat_history=chat_history,
        detected_language=detected_language,
        tools="\n".join([f"- {tool.name}: {tool.description}" for tool in tools]),
        input=last_message.content
    )

    response = llm.invoke([HumanMessage(content=formatted_prompt)])

    if "Action:" in response.content and "Action Input:" in response.content:
        lines = response.content.split('\n')
        action_line = next((line for line in lines if line.startswith("Action:")), None)
        action_input_line = next((line for line in lines if line.startswith("Action Input:")), None)

        if action_line and action_input_line:
            tool_name = action_line.split("Action:")[1].strip()
            tool_input = action_input_line.split("Action Input:")[1].strip()

            for tool in tools:
                if tool.name == tool_name:
                    try:
                        tool_result = tool.func(tool_input)
                        final_prompt = f"""
                        {formatted_prompt}

                        Action: {tool_name}
                        Action Input: {tool_input}
                        Observation: {tool_result}

                        Now provide your final response to the user.

                        IMPORTANT:
                        - DO NOT summarize or say "see the above result".
                        - DIRECTLY INCLUDE the full tool output in your reply, as if you wrote it yourself.
                        - You are CityGuide.AI – speak in your usual cheerful tone, but make sure the full itinerary is visible to the user.
                        """

                        final_response = llm.invoke([HumanMessage(content=final_prompt)])
                        return {"messages": [AIMessage(content=final_response.content)]}
                    except Exception as e:
                        return {"messages": [
                            AIMessage(content=f"I encountered an error using the {tool_name} tool: {str(e)}")]}

    return {"messages": [AIMessage(content=response.content)]}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    return END

workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue)

app_langgraph = workflow.compile()
app = Flask(__name__)

initial_message = """You are CityGuide.AI – a cheerful, multilingual, and highly knowledgeable AI city guide and travel companion.
Your mission is to make every traveler feel like a local, by understanding their location, mood, interests, and past conversations.
You always speak in a helpful, friendly, sometimes funny, and motivating tone.

Your strengths:
-  Hyperlocal expertise of ANY city the user visits
-  Support for multiple languages and cultures
-  Deep memory: you remember user interests, mood, bookmarks, and past chats
-  You can call external tools like DayPlanner, BookmarkTool, POITool, StoryMode, and InterestTool for any location
-  You are always enthusiastic, curious, and positive in tone

Start each conversation warmly, adapt to the user's mood and location, and always offer something helpful. You are their energetic digital city companion for ANY city in the world!
"""


def generate_unique_file_paths(user_phone, file_type="audio"):
    """Generate unique file paths for each user and request"""
    sanitized_phone = re.sub(r'\D', '', user_phone)  # Remove non-digits
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4())[:8]

    if file_type == "incoming":
        ogg_path = f"incoming_{sanitized_phone}_{timestamp}_{unique_id}.ogg"
        mp3_path = f"incoming_{sanitized_phone}_{timestamp}_{unique_id}.mp3"
        return ogg_path, mp3_path
    elif file_type == "outgoing":
        mp3_path = f"output_{sanitized_phone}_{timestamp}_{unique_id}.mp3"
        return mp3_path


def cleanup_incoming_files(ogg_path, mp3_path):
    """Clean up incoming audio files after 300 seconds"""
    time.sleep(300)
    try:
        if ogg_path and os.path.exists(ogg_path):
            os.remove(ogg_path)
            print(f"Deleted incoming OGG file: {ogg_path}")
    except Exception as e:
        print(f"Error deleting incoming OGG file {ogg_path}: {e}")

    try:
        if mp3_path and os.path.exists(mp3_path):
            os.remove(mp3_path)
            print(f"Deleted incoming MP3 file: {mp3_path}")
    except Exception as e:
        print(f"Error deleting incoming MP3 file {mp3_path}: {e}")

@app.route("/incoming", methods=["POST"])
def incoming():
    from_number = request.form.get("From")
    message_body = request.form.get("Body", "")
    media_url = request.form.get("MediaUrl0")
    resp = MessagingResponse()

    # Ensure user exists and get their data
    user_manager.ensure_user_exists(from_number)
    user_data = user_manager.get_user_data()
    current_location = user_data.get('interests', {}).get('current_location', 'Delhi')
    stored_language = user_data.get('detected_language', 'English')

    # Create user-specific memory instance
    user_memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    # Load user's chat history into this memory instance
    loaded_chat_messages = user_manager.load_chat_history()
    user_memory.chat_memory.add_message(SystemMessage(content=initial_message))
    for msg in loaded_chat_messages:
        user_memory.chat_memory.add_message(msg)

    # Initialize variables for this request
    transcribed_text = message_body
    detected_language = stored_language
    detected_mood = "neutral"
    ogg_path = None
    mp3_path = None

    if media_url:
        print("Downloading from:", media_url)

        # Generate unique file paths for this user/request
        ogg_path, mp3_path = generate_unique_file_paths(from_number, "incoming")

        try:
            response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))

            with open(ogg_path, "wb") as f:
                f.write(response.content)

            audio = AudioSegment.from_ogg(ogg_path)
            audio.export(mp3_path, format="mp3")

            detected_language, transcribed_text = transcribe_and_identify_language(mp3_path)

            if detected_language != "Unknown" and detected_language != stored_language:
                user_manager.update_detected_language(detected_language)
                stored_language = detected_language

            detected_mood = detect_mood(transcribed_text)

        except Exception as e:
            print(f"Error processing audio for {from_number}: {e}")
            transcribed_text = "Sorry, I couldn't process your audio message."

    # Process the message (audio or text)
    user_message = HumanMessage(content=transcribed_text)
    user_memory.chat_memory.add_message(user_message)

    # Create state for this user's request
    state = AgentState(
        messages=[user_message],
        location=current_location,
        mood=detected_mood,
        chat_history="\n".join([f"{msg.type}: {msg.content}" for msg in user_memory.chat_memory.messages]),
        detected_language=stored_language
    )

    # Get AI response
    result = app_langgraph.invoke(state)
    ai_response = result["messages"][-1].content

    # Add AI response to user's memory
    ai_message = AIMessage(content=ai_response)
    user_memory.chat_memory.add_message(ai_message)

    # Save this user's updated chat history
    user_manager.save_chat_history(user_memory.chat_memory.messages)

    # Send text response immediately
    #resp.message(ai_response)

    # Start asynchronous audio response with user-specific data
    def delayed_audio():
        time.sleep(2)
        send_audio(from_number, ai_response)

    threading.Thread(target=delayed_audio).start()
    if ogg_path or mp3_path:
        threading.Thread(target=cleanup_incoming_files, args=(ogg_path, mp3_path)).start()

    return str(resp)


@app.route('/audio/<filename>')
def serve_audio(filename):
    return send_from_directory('.', filename)


@app.route("/send-audio", methods=["GET"])
def send_audio(to_number, text_to_speak):
    """Send audio message to specific user with specific text"""

    # Ensure proper WhatsApp format
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"

    # Generate unique output file path for this user/request
    mp3_path = generate_unique_file_paths(to_number, "outgoing")

    try:
        # Generate audio
        elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

        audio = elevenlabs.text_to_speech.convert(
            text=text_to_speak,
            voice_id="JBFqnCBsd6RMkjVDRZzb",
            model_id="eleven_turbo_v2_5",
            output_format="mp3_44100_128",
        )

        # Save to unique file
        with open(mp3_path, "wb") as f:
            f.write(b"".join(audio))

        print(f"Audio saved as: {mp3_path} for user: {to_number}")

        # Send via Twilio
        media_ngrok = os.getenv("MEDIA_URL_AUDIO")
        media_url = f'{media_ngrok}/audio/{mp3_path}'

        message = client.messages.create(
            from_=f"whatsapp:{TWILIO_NUMBER}",
            to=to_number,
            #body='🎵 Audio response:',
            media_url=[media_url]
        )

        print(f"Audio message sent! SID: {message.sid} to {to_number}")

        # Schedule cleanup of this specific file
        def cleanup_outgoing_file():
            time.sleep(300)
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
                    print(f"Deleted outgoing file: {mp3_path}")
            except Exception as e:
                print(f"Error deleting outgoing file {mp3_path}: {e}")

        threading.Thread(target=cleanup_outgoing_file).start()

        return "Audio sent", 200

    except Exception as e:
        print(f"Error sending audio to {to_number}: {e}")
        return str(e), 500

if __name__ == "__main__":
    def run_flask():
        app.run(port=5000)
    run_flask()
