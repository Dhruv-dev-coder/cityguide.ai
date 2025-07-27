# CityGuide.AI 🏙️

A multilingual AI-powered city guide that provides personalized travel recommendations through WhatsApp. Built with LangChain, Google Gemini, Firebase, and Twilio, CityGuide.AI acts as your personal travel companion for any city in the world.

---

## 👥 Credits

**Developed by**: Teaam Syntax Squad [@Dhruv-dev-coder, @Achill3s01 and @Ghosty-Gigabytes] 
**Version**: 1.0.0  
**License**: MIT License  

> **Note**: This project requires paid API keys from third-party services. Users are responsible for their own API costs and terms of service compliance.

**Built with ❤️ using:**
- 🤖 Google Gemini 2.5 Flash for AI capabilities
- 🔗 LangChain for conversation orchestration  
- 🔥 Firebase for data persistence
- 📱 Twilio for WhatsApp integration
- 🎙️ ElevenLabs for voice synthesis
- 🔍 SerpAPI for real-time data

---

## 🌟 Features

### Core Capabilities
- **Multilingual Support**: Automatically detects and responds in user's preferred language
- **Voice & Text Integration**: Processes both text and voice messages via WhatsApp
- **Personalized Recommendations**: Learns from user preferences and conversation history
- **Real-time Information**: Weather, news, events, and place finder tools
- **Memory Persistence**: Remembers user interactions across sessions using Firebase

### AI-Powered Tools
1. **Day Planner**: Creates customized itineraries based on mood, time, and interests
2. **Bookmark System**: Save and retrieve favorite places with personal notes
3. **Points of Interest (POI)**: Discover attractions, restaurants, and hidden gems
4. **Interest Management**: Track user likes/dislikes for better recommendations
5. **Story Mode**: Generate engaging narratives about city locations
6. **Live Events**: Find current events and activities in any city
7. **Weather Updates**: Real-time weather information
8. **News Feed**: Local news and current affairs
9. **Places Finder**: Locate specific services (hospitals, ATMs, restaurants, etc.)
10. **User Profile**: Comprehensive travel history and preferences

## 🏗️ Architecture

### Tech Stack
- **AI/LLM**: Google Gemini 2.5 Flash via LangChain
- **Database**: Firebase Firestore
- **Communication**: Twilio WhatsApp API
- **Voice Processing**: ElevenLabs Text-to-Speech, Google Gemini for transcription
- **Web Search**: SerpAPI for real-time data
- **Framework**: Flask for webhook handling
- **Orchestration**: LangGraph for conversation flow

### System Components
```
WhatsApp User → Twilio → Flask Webhook → LangGraph Agent → Tools → Firebase → Response
```

## 📋 Prerequisites

- Python 3.8+
- WhatsApp Business Account (via Twilio)
- Firebase Project
- Google Gemini API access
- ElevenLabs API key
- SerpAPI key
- Public server/hosting platform (AWS, GCP, Heroku, DigitalOcean, etc.)

## 🚀 Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd cityguide-ai
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Setup
Create a `.env` file with the following variables:

```env
# Google Gemini
GOOGLE_API_KEY=your_google_gemini_api_key

# Firebase
FIREBASE_CREDENTIALS_JSON={"type": "service_account", "project_id": "...", ...}

# Twilio WhatsApp
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_NUMBER=+1234567890
TO_NUMBER=+1234567890

# ElevenLabs
ELEVENLABS_API_KEY=your_elevenlabs_api_key

# SerpAPI
SERP_API_KEY=your_serpapi_key

# Media URL (your public server URL)
MEDIA_URL_AUDIO=https://your-domain.com
```

### 4. Firebase Setup
1. Create a Firebase project
2. Enable Firestore Database
3. Create a service account and download credentials
4. Add the credentials JSON to your `.env` file

### 5. Twilio WhatsApp Setup
1. Create a Twilio account
2. Set up WhatsApp Business API
3. Configure webhook URL: `https://your-domain.com/incoming`
4. Set media URL base: `https://your-domain.com`

## 🚀 Deployment Guide

### Hosting Platform Options

#### 1. **Heroku** (Recommended for beginners)
```bash
# Install Heroku CLI and login
heroku login

# Create new app
heroku create your-app-name

# Set environment variables
heroku config:set GOOGLE_API_KEY=your_key
heroku config:set TWILIO_ACCOUNT_SID=your_sid
# ... (set all other env vars)

# Deploy
git push heroku main
```

#### 2. **AWS EC2**
- Launch an EC2 instance with Python support
- Install dependencies and upload your code
- Configure security groups for HTTP/HTTPS traffic
- Use PM2 or systemd for process management

#### 3. **Google Cloud Run**
```bash
# Build and deploy
gcloud run deploy cityguide-ai \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

#### 4. **DigitalOcean App Platform**
- Connect your GitHub repository
- Configure environment variables in the control panel
- Deploy directly from the dashboard

### Domain & SSL Setup
- Configure your domain to point to your server
- Enable HTTPS/SSL (required for Twilio webhooks)
- Update Twilio webhook URLs to use your domain

### Production Deployment
1. Deploy to your preferred hosting platform:
   - **AWS**: EC2, Elastic Beanstalk, or Lambda
   - **Google Cloud**: App Engine, Compute Engine, or Cloud Run
   - **Heroku**: Direct deployment with buildpacks
   - **DigitalOcean**: Droplets or App Platform
   - **Other**: Any VPS or cloud platform supporting Python

2. Ensure all environment variables are properly configured
3. Set up webhook URLs in Twilio:
   - Webhook URL: `https://your-domain.com/incoming`
   - Media URL: `https://your-domain.com/audio/`

### Local Development (Optional)
For local testing, you can still use tools like ngrok:
```bash
# Install ngrok
npm install -g ngrok

# Expose local port
ngrok http 5000

# Run the Flask application
python app.py
```

## 📱 Usage

### WhatsApp Commands
Users can interact with CityGuide.AI through natural language. Here are some example interactions:

#### Planning & Itineraries
- "Plan my day in Paris"
- "I'm feeling adventurous, what should I do in Tokyo this afternoon?"
- "Create a romantic evening itinerary for London"

#### Discovering Places
- "Show me hidden gems in Barcelona"
- "Find the best street food in Bangkok"
- "Recommend museums in New York"

#### Bookmarking
- "Save Central Park as my favorite jogging spot"
- "Bookmark this restaurant - amazing pasta!"
- "Show me all my saved places in Rome"

#### Real-time Information
- "What's the weather like in Mumbai?"
- "Any events happening in Berlin this weekend?"
- "Find hospitals near Times Square"

#### Personal Preferences
- "I love art galleries"
- "I don't like crowded places"
- "Remove hiking from my interests"

#### Story Mode
- "Tell me a story about visiting the Eiffel Tower and Louvre"
- "Create an adventure tale about exploring Old Delhi"

### Voice Messages
- Send voice messages in any language
- Automatic transcription and language detection
- Receive audio responses back

## 🛠️ Configuration

### User Data Structure
```python
{
    'phone_number': str,
    'name': str,
    'bookmarks': List[dict],
    'interests': {
        'likes': List[str],
        'dislikes': List[str],
        'visited_places': List[str],
        'preferred_time': str,
        'budget_range': str,
        'current_location': str
    },
    'current_plan': dict,
    'story_history': List[dict],
    'chat_history': List[dict],
    'detected_language': str,
    'created_at': timestamp,
    'last_active': timestamp
}
```

### Tool Configuration
Each tool can be customized through the `city_explorer_tools` list. Tools include:
- Input format specifications
- Description for LLM understanding
- Function mappings

## 🔧 Customization

### Adding New Tools
1. Create a new function in the tools section
2. Add it to the `city_explorer_tools` list with proper formatting
3. Update the prompt template if needed

### Modifying AI Behavior
- Edit the `prompt_string` to change AI personality
- Adjust system messages for different conversation styles
- Modify tool descriptions for better LLM understanding

### Language Support
- The system automatically detects languages via Google Gemini
- Add language-specific prompts if needed
- ElevenLabs supports multiple languages for voice responses

## 📊 Monitoring & Analytics

### Logging
- User interactions are logged to console
- Error handling for API failures
- File cleanup tracking

### Data Storage
- All user data stored in Firebase Firestore
- Chat history persistence
- User preferences and bookmarks

### Performance
- Asynchronous audio processing
- Automatic file cleanup (300 seconds)
- Memory-efficient conversation handling

## 🚨 Error Handling

### Common Issues
1. **Audio Processing Failures**: Falls back to text processing
2. **API Rate Limits**: Graceful degradation with error messages
3. **Firebase Connection**: Retry logic for database operations
4. **Twilio Webhooks**: Proper HTTP response codes

### Debugging
- Enable detailed logging in development
- Monitor Firebase console for data issues
- Check Twilio logs for webhook failures

## 🔐 Security Considerations

- Environment variables for all sensitive data
- Firebase security rules for user data protection
- Twilio webhook validation
- Automatic cleanup of temporary audio files

## 📈 Scaling

### Performance Optimization
- Implement caching for frequently accessed data
- Use connection pooling for database operations
- Optimize LLM prompts for faster responses

### Infrastructure
- Use cloud functions for serverless scaling
- Implement load balancing for high traffic
- Consider Redis for session management

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

MIT License

Copyright (c) 2024 [Your Name/Organization]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### Third-Party Services Disclaimer

This project integrates with several third-party APIs and services:
- Google Gemini API
- Twilio WhatsApp Business API  
- ElevenLabs Text-to-Speech API
- SerpAPI
- Firebase/Firestore

Users are responsible for:
- Obtaining their own API keys and accounts
- Complying with each service's terms of use
- Managing their own usage costs and billing
- Ensuring compliance with data privacy regulations

The MIT license applies only to this codebase and does not grant any rights to third-party services.

## 🆘 Support

For issues and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review Twilio and Firebase documentation

## 🔮 Future Enhancements

- Group chat support
- Integration with booking platforms
- Offline mode capabilities
- Advanced analytics dashboard
- Multi-city trip planning
- Social features (sharing itineraries)
- Integration with transport APIs
- Photo recognition for location identification

---

**Made with ❤️ for travelers worldwide**
