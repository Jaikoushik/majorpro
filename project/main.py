import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Set up Gemini API key
GEMINI_API_KEY = "AIzaSyBJoPu7ohUAtX7TTSliUtsGDG-U7dNWXag"  # Replace with your actual API key
genai.configure(api_key=GEMINI_API_KEY)

# Setup Chrome with Selenium
chrome_options = Options()
chrome_options.add_argument("--window-size=1920x1080")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--disable-infobars")
chrome_options.add_argument("--disable-notifications")

service = Service()
driver = webdriver.Chrome(service=service, options=chrome_options)

# Open Twitter Explore
driver.get("https://twitter.com/explore")

# Wait for page load
wait = WebDriverWait(driver, 15)
wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

# Allow manual login
input("Log in to Twitter and press Enter to continue...")

# Locate Search Box
try:
    search_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Search query"]')))
except:
    print("Search box not found!")
    driver.quit()
    exit()

# Perform search
search_query = "politics"
search_box.send_keys(search_query)
search_box.send_keys(Keys.RETURN)

# Wait for results to load
wait.until(EC.presence_of_element_located((By.XPATH, '//div[@data-testid="tweetText"]')))

# Scroll to load more tweets
tweets_text = set()
scroll_attempts = 0
max_scrolls = 5
previous_tweet_count = 0
while len(tweets_text) < 100 and scroll_attempts < max_scrolls:
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)  # Wait for new tweets to load

    # Extract new tweets
    new_tweets = driver.find_elements(By.XPATH, '//div[@data-testid="tweetText"]')

    # Add only new tweets to the set
    for tweet in new_tweets:
        text = tweet.text.strip()
        if text and text not in tweets_text:  # Avoid empty & duplicate tweets
            tweets_text.add(text)

    scroll_attempts += 1

    # If no new tweets are found, break early
    if len(tweets_text) == previous_tweet_count:
        break

    previous_tweet_count = len(tweets_text)  # Update count for next iteration

# Print only once after collection is complete
print(f"Total tweets collected: {len(tweets_text)}")


# Convert tweets to list (Limit to 100)
tweets_text = list(tweets_text)[:100]

driver.quit()

# Analyze tweets with Gemini
def analyze_dark_patterns(tweets):
    try:
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")  # Correct model name
        prompt = f"""
        You are an AI that detects deceptive online practices called 'dark patterns.'
        Analyze the following tweets and identify if they contain dark patterns. 
        Provide a brief explanation in the following format:
        Also analyze the political related content as well to find the dark patterns whether it is manipulating or not.
        Tweet: [Tweet Content]
        Analysis: [Dark Pattern or Not, Explanation]

        Tweets:
        {tweets}
        """

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error analyzing tweets: {e}"

# Send tweets for analysis
if tweets_text:
    print("\nAnalyzing tweets for dark patterns...\n")
    result = analyze_dark_patterns(tweets_text)
    print(result)
else:
    print("No tweets found!")