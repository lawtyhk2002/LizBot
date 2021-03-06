import StringIO
import json
import random
import urllib
import urllib2
import logging
import ConfigParser
import os

# standard app engine imports
from google.appengine.api import urlfetch
import webapp2

TOKEN = ""
HOOK_TOKEN = ""
OWM_KEY = ""
PROJECT_ID = ""

# Lambda functions to parse updates from Telegram
def getText(update):            return update["message"]["text"]
def getLocation(update):        return update["message"]["location"]
def getChatId(update):          return update["message"]["chat"]["id"]
def getName(update):            return update["message"]["from"]["first_name"]
def getResult(update):          return update["result"]

# # Lambda functions to parse weather responses
def getDesc(w):                 return w["weather"][0]["description"]
def getTemp(w):                 return w["main"]["temp"]
def getCity(w):                 return w["name"]

logger = logging.getLogger("LizBot")
logger.setLevel(logging.DEBUG)

# Cities for weather requests
cities = ["London", "Brasov"]

# Accepted commands
commands = ["/weather", "/fact", "/mirror", "/fortune", "/trivia"]

# Keep track of conversation states: 'weatherReq', 'verifying', 'verified'
chats = {}

# Expected answers for pending trivia question
expected = {}

# --------------- Helper functions ---------------
# Read settings from configuration file
def parseConfig():
    global BASE_URL, URL_OWM, HOOK_TOKEN, PROJECT_ID
    
    c = ConfigParser.ConfigParser()
    c.read("config.ini")
    TOKEN = c.get("Settings", "TOKEN")
    BASE_URL = "https://api.telegram.org/bot" + TOKEN + "/"
    
    OWM_KEY = c.get("Settings", "OWM_KEY")
    URL_OWM = "http://api.openweathermap.org/data/2.5/weather?appid={}&units=metric".format(OWM_KEY)

    HOOK_TOKEN = c.get("Settings", "HOOK_TOKEN")
    PROJECT_ID = c.get("Settings", "PROJECT_ID")

# Set requests timeout (default is 15)
def setTimeout(numSec = 60):
    urlfetch.set_default_fetch_deadline(numSec)

# Deserialise object and serialise it to JSON formatted string
def formatResp(obj):
    parsed = json.load(obj)
    return json.dumps(parsed, indent=4, sort_keys=True)

# Make a request and get JSON response
def makeRequest(url):
    logger.debug("URL: %s" % url)
    r = urllib2.urlopen(url)
    resp = json.load(r)
    return resp

# Build a one-time keyboard for on-screen options
def buildKeyboard(items):
    keyboard = [[{"text":item}] for item in items]
    replyKeyboard = {"keyboard":keyboard, "one_time_keyboard": True}
    logger.debug(replyKeyboard)
    return json.dumps(replyKeyboard)

# Send URL-encoded message to chat id
def sendMessage(text, chatId, interface=None):
    params = {
        "chat_id": str(chatId),
        "text": text.encode("utf-8"),
        "parse_mode": "Markdown",
    }
    if interface:
        params["reply_markup"] = interface
    
    resp = urllib2.urlopen(BASE_URL + "sendMessage", urllib.urlencode(params)).read()

# --------------- Weather related stuff ---------------
# Query OWM for the weather for place or coords
def getWeather(place):
    if isinstance(place, dict):     # coordinates provided
        lat, lon = place["latitude"], place["longitude"]
        url = URL_OWM + "&lat=%f&lon=%f&cnt=1" % (lat, lon)
        logger.info("Requesting weather: " + url)
        js = makeRequest(url)
        logger.debug(js)
        return u"%s \N{DEGREE SIGN}C, %s in %s" % (getTemp(js), getDesc(js), getCity(js))
    else:                           # place name provided 
        # make req
        url = URL_OWM + "&q={}".format(place)
        logger.info("Requesting weather: " + url)
        js = makeRequest(url)
        logger.debug(js)
    return u"%s \N{DEGREE SIGN}C, %s in %s" % (getTemp(js), getDesc(js), getCity(js))

def buildCitiesKeyboard():
    keyboard = [[{"text": c}] for c in cities]
    keyboard.append([{"text": "Share location", "request_location": True}])
    replyKeyboard = {"keyboard": keyboard, "one_time_keyboard": True}
    logger.debug(replyKeyboard)
    return json.dumps(replyKeyboard)

# --------------- Random facts/fortune/compliments/challenges functions ---------------
# Read random line from big text file
def getRandom(fName): 
    f = open(fName, "r")

    fSize = os.stat(fName)[6]
    # Seek to a random place in the file
    f.seek(random.randint(0, fSize-1))

    # The first readline since it may fall in the middle of a line
    f.readline()
    # Read the next complete line
    line = f.readline()
    # If last line, wrap and read the first
    if not line:
        f.seek(0)
        f.readline()

    f.close()

    return line.strip()                                                                                           

def getFact():
    fName = "facts.txt"
    return getRandom(fName)    

def getCompliment():
    fName = "compliments.txt"
    return getRandom(fName)

def getCookie():
    fName = "fortunes.dat"
    return getRandom(fName)

def getChall():
    questions = json.loads(open("trivia.json").read())
    numQ = len(questions)
    
    return questions[random.randint(0, numQ-1)]
  
# --------------- Request handler functions ---------------
# Return basic information about the bot
class MeHandler(webapp2.RequestHandler):
    def get(self):
        setTimeout()
        parseConfig()

        url = BASE_URL + "getMe"
        respBuf = urllib2.urlopen(url)

        self.response.headers["Content-Type"] = "text/plain"
        self.response.write(formatResp(respBuf))

# Get information about webhook status
class GetWebhookHandler(webapp2.RequestHandler):
    def get(self):
        setTimeout()
        parseConfig()

        url = BASE_URL + "getWebhookInfo"
        respBuf = urllib2.urlopen(url)

        self.response.headers["Content-Type"] = "text/plain"
        self.response.write(formatResp(respBuf))

# Set a webhook url for Telegram to POST to
class SetWebhookHandler(webapp2.RequestHandler):
    def get(self):
        setTimeout()
        parseConfig()

        hookUrl = "https://%s.appspot.com/TG%s" % (PROJECT_ID, HOOK_TOKEN)
        logger.info("Setting new webhook to: %s" % hookUrl)
        respBuf = urllib2.urlopen(BASE_URL + "setWebhook", urllib.urlencode({
            "url": hookUrl
        })) 
        self.response.headers["Content-Type"] = "text/plain"
        self.response.write(formatResp(respBuf))

# Remove webhook integration
class DeleteWebhookHandler(webapp2.RequestHandler):
    def get(self):
        setTimeout()
        parseConfig()

        url = BASE_URL + "deleteWebhook"
        respBuf = urllib2.urlopen(url)

        self.response.headers["Content-Type"] = "text/plain"
        self.response.write(formatResp(respBuf))


# Handler for the webhook, called by Telegram
class WebhookHandler(webapp2.RequestHandler):
    def post(self):
        setTimeout()
        parseConfig()
        logger.info("Received request: %s from %s" % (self.request.url, self.request.remote_addr))

        if HOOK_TOKEN not in self.request.url:
            # Not coming from Telegram
            logger.error("Post request without token from IP: %s" % self.request.remote_addr)
            return
 
        body = json.loads(self.request.body)
        
        chatId = getChatId(body)
        logger.info("Response body: " + str(body))

        try:
            text = getText(body)
        except Exception as e:
            logger.info("No text field in update. Try to get location")
            loc = getLocation(body)
            # Was weather previously requested?
            if (chatId in chats) and (chats[chatId] == "weatherReq"):
                logger.info("Weather requested for %s in chat id %d" % (str(loc), chatId))
                # Send weather to chat id and clear state
                sendMessage(getWeather(loc), chatId)
                del chats[chatId]
            return
      

        if text == "/start":
            keyboard = buildKeyboard(commands)
            sendMessage("Hello %s! Why not try the commands below:"  % getName(body), chatId, keyboard)

        elif text == "/weather":
            keyboard = buildCitiesKeyboard()
            chats[chatId] = "weatherReq"
            sendMessage("Select a city", chatId, keyboard)

        elif (text in cities) and (chatId in chats) and (chats[chatId] == "weatherReq"):
            logger.info("Weather requested for %s" % text)
            # Send weather to chat id and clear state
            sendMessage(getWeather(text), chatId)
            del chats[chatId]

        elif text == "/fact":
            sendMessage(getFact(), chatId)

        elif text == "/mirror":
            sendMessage(getCompliment(), chatId)

        elif text == "/fortune":
            sendMessage(getCookie(), chatId)

        elif text == "/trivia": 
            # Has user answered the challenge?
            if (chatId not in chats) or (chats[chatId] != "waitingAnswer"):
                logger.info("Sendia trivia question")
                chal = getChall() 
                question = chal["Question"]
                answers = chal["Answers"]
                keyboard = buildKeyboard(answers)
                sendMessage("New chat! Please verify by answering a simple question!", chatId)
                sendMessage(question, chatId, keyboard)

                # Change status
                chats[chatId] = "waitingAnswer"

                expected[chatId] = answers[chal["Correct"]]
    
        elif (chatId in chats) and (chats[chatId] == "waitingAnswer"):
            logger.info("Verify user answer")

            if text == expected[chatId]:
                logger.info("Correct trivia answer!")
                sendMessage("Wow! That is correct!", chatId)
            else:
                logger.info("Incorrect answer")
                sendMessage("Wrong answer :(", chatId)

            del chats[chatId]
   
        elif text.startswith("/"):
            sendMessage("Cahn's Axiom: When all else fails, read the instructions", chatId) 

        else:
            keyboard = buildKeyboard(commands)
            sendMessage("I learn new things every day but for now you can ask me about the following:", chatId, keyboard)


app = webapp2.WSGIApplication([
    ('/me', MeHandler),
    ('/set_webhook', SetWebhookHandler),
    ('/get_webhook', GetWebhookHandler),
    ('/del_webhook', DeleteWebhookHandler),
    (r'/TG.*' , WebhookHandler),
], debug=True)
