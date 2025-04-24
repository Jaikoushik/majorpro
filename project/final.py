import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import logging
import sys
import os
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Gemini API Setup
GEMINI_API_KEY = ""  # Replace with your actual API key
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secret key for session management

# Store job results
jobs = {}

def setup_chrome_driver():
    """Set up and return Chrome WebDriver with appropriate options"""
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--headless")  # Run in headless mode for web server
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
    
    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def analyze_with_gemini(data, platform, search_query):
    """Generic function to analyze data with Gemini API"""
    try:
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        
        if platform == "ajio" or platform == "amazon":
            # E-commerce prompt
            prompt = (
                f"You are an AI that detects dark patterns—deceptive UI/UX strategies used in e-commerce to manipulate users.\n\n"
                f"Analyze these {platform.capitalize()} search results for '{search_query}' and focus ONLY on detecting dark patterns.\n"
                f"Dark patterns include: fake discounts, artificial urgency, misleading pricing, and deceptive labeling.\n\n"
                f"For each product, provide ONLY these things:\n"
                f"1. Product title\n"
                f"2. Product URL (if available)\n"
                f"3. Dark pattern detected? (Yes/No) with a one-sentence explanation\n\n"
                f"Keep your analysis very brief and direct. No need for introductions or conclusions.\n\n"
                f"Here are the product listings:\n"
                + "\n\n".join([f"---PRODUCT {i+1}---\n{item}" for i, item in enumerate(data)])
            )
        elif platform == "twitter":
            # Twitter/social media prompt
            prompt = (
                f"You are an AI that detects deceptive online practices called 'dark patterns.'\n"
                f"Analyze the following tweets and identify if they contain dark patterns.\n"
                f"Also analyze the political related content to find dark patterns whether it is manipulating or not.\n"
                f"Provide a brief explanation in the following format:\n"
                f"Tweet: [Tweet Content]\n"
                f"Analysis: [Dark Pattern or Not, Explanation]\n\n"
                f"Tweets:\n{data}"
            )
        
        # Generation config for faster response
        generation_config = {
            "temperature": 0.1,
            "max_output_tokens": 10000,
        }
        
        logger.info(f"Sending request to Gemini for {platform} analysis...")
        response = model.generate_content(prompt, generation_config=generation_config)
        return response.text
        
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return f"Error analyzing {platform} data: {e}"

def scrape_ajio(search_query, job_id):
    """Scrape product data from Ajio"""
    logger.info(f"Starting Ajio search for '{search_query}'")
    driver = setup_chrome_driver()
    ajio_data = []
    
    try:
        jobs[job_id]['status'] = 'Connecting to Ajio...'
        # Go to Ajio
        driver.get("https://www.ajio.com/")
        
        # Set up wait
        wait = WebDriverWait(driver, 15)
        
        jobs[job_id]['status'] = 'Searching for products...'
        # Perform search
        search_box = wait.until(EC.presence_of_element_located((By.NAME, "searchVal")))
        search_box.clear()
        search_box.send_keys(search_query)
        search_box.submit()
        
        # Wait for products to load
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "item")))
        time.sleep(5)
        
        jobs[job_id]['status'] = 'Extracting product information...'
        # Extract product data
        product_cards = driver.find_elements(By.CLASS_NAME, "item")
        logger.info(f"Found {len(product_cards)} products on Ajio")
        
        product_count = min(20, len(product_cards))
        jobs[job_id]['status'] = f'Processing {product_count} products...'
        
        for i, card in enumerate(product_cards[:20]):  # Limit to first 20 products
            try:
                title = card.find_element(By.CLASS_NAME, "nameCls").text.strip()
                current_price = card.find_element(By.CLASS_NAME, "price").text.strip()
                original_price = ""
                discount = ""
                product_url = ""
                
                try:
                    original_price = card.find_element(By.CLASS_NAME, "orginal-price").text.strip()
                except:
                    pass
                
                try:
                    discount = card.find_element(By.CLASS_NAME, "discount").text.strip()
                except:
                    pass
                
                # Extract product URL
                try:
                    url_element = card.find_element(By.CSS_SELECTOR, "a")
                    if url_element:
                        product_url = url_element.get_attribute("href")
                        # Make sure we have absolute URLs
                        if product_url and not product_url.startswith("http"):
                            product_url = "https://www.ajio.com" + product_url
                except Exception as e:
                    logger.error(f"Error extracting Ajio product URL: {e}")
                    pass
                
                product_info = f"""
                Title: {title}
                Current Price: {current_price}
                Original Price: {original_price}
                Discount Info: {discount}
                Product URL: {product_url}
                """.strip()
                
                ajio_data.append(product_info)
                logger.info(f"Scraped Ajio product: {title[:50]}...")
                
                # Update status with progress
                jobs[job_id]['status'] = f'Processing products... ({i+1}/{product_count})'
                
            except Exception as e:
                logger.error(f"Error scraping Ajio product: {e}")
                continue
        
        if ajio_data:
            jobs[job_id]['status'] = 'Analyzing with Gemini AI...'
            result = analyze_with_gemini(ajio_data, "ajio", search_query)
            
            # Save results to file
            filename = f"ajio_{search_query}_analysis.txt"
            with open(os.path.join("static", "results", filename), "w", encoding="utf-8") as f:
                f.write(result)
            
            jobs[job_id]['status'] = 'Complete'
            jobs[job_id]['result'] = result
            jobs[job_id]['filename'] = filename
        else:
            jobs[job_id]['status'] = 'Failed - No products found'
            jobs[job_id]['result'] = 'No product data found to analyze'
        
    except Exception as e:
        logger.error(f"Error during Ajio scraping: {e}")
        jobs[job_id]['status'] = 'Failed'
        jobs[job_id]['result'] = f"Error during scraping: {str(e)}"
    
    finally:
        driver.quit()
        logger.info("Ajio browser closed")

def scrape_amazon(search_query, job_id):
    """Scrape product data from Amazon"""
    logger.info(f"Starting Amazon search for '{search_query}'")
    driver = setup_chrome_driver()
    amazon_data = []
    
    try:
        jobs[job_id]['status'] = 'Connecting to Amazon...'
        # Visit Amazon and search
        driver.get("https://www.amazon.in/")
        time.sleep(5)  # Wait for page to fully load
        
        wait = WebDriverWait(driver, 20)
        
        # Try to accept cookies if banner appears
        try:
            cookie_accept = wait.until(EC.element_to_be_clickable((By.ID, "sp-cc-accept")))
            cookie_accept.click()
        except:
            pass
        
        jobs[job_id]['status'] = 'Searching for products...'
        # Perform search
        search_box = wait.until(EC.element_to_be_clickable((By.ID, "twotabsearchtextbox")))
        search_box.clear()
        search_box.send_keys(search_query)
        search_button = wait.until(EC.element_to_be_clickable((By.ID, "nav-search-submit-button")))
        search_button.click()
        
        # Wait for product listings to load
        logger.info("Waiting for Amazon search results...")
        time.sleep(5)
        
        jobs[job_id]['status'] = 'Extracting product information...'
        # Get product cards
        product_cards = driver.find_elements(By.CSS_SELECTOR, 'div[data-component-type="s-search-result"]')
        logger.info(f"Found {len(product_cards)} product cards on Amazon")
        
        if len(product_cards) == 0:
            logger.warning("No product cards found. Amazon may have changed their HTML structure.")
            # Try an alternative selector
            product_cards = driver.find_elements(By.CSS_SELECTOR, '.s-result-item')
            logger.info(f"Second attempt found {len(product_cards)} cards")
        
        product_count = min(15, len(product_cards))
        jobs[job_id]['status'] = f'Processing {product_count} products...'
        
        for i, card in enumerate(product_cards[:15]):  # Limit to first 15 products
            try:
                # Extract title
                title = "Title not found"
                title_selectors = [
                    (By.CSS_SELECTOR, 'h2 a span'),
                    (By.CSS_SELECTOR, '.a-size-medium.a-color-base.a-text-normal'),
                    (By.CSS_SELECTOR, '.a-size-base-plus.a-color-base.a-text-normal'),
                    (By.XPATH, './/h2//a//span'),
                    (By.XPATH, './/a[@class="a-link-normal"]//span'),
                    (By.CSS_SELECTOR, 'h2 a')
                ]
                
                for selector_type, selector in title_selectors:
                    try:
                        elements = card.find_elements(selector_type, selector)
                        if elements:
                            title = elements[0].text.strip()
                            if title:
                                break
                    except:
                        continue
                
                # Extract current price
                current_price = "Not available"
                try:
                    price_whole = card.find_elements(By.CSS_SELECTOR, '.a-price-whole')
                    if price_whole:
                        current_price = price_whole[0].text.strip()
                except:
                    pass
                
                # Extract original price
                original_price = "Not available"
                try:
                    orig_price = card.find_elements(By.CSS_SELECTOR, '.a-price.a-text-price .a-offscreen')
                    if orig_price:
                        original_price = orig_price[0].get_attribute('innerHTML').replace('₹', '').strip()
                except:
                    pass
                
                # Calculate discount
                discount = "Not enough info"
                if current_price != "Not available" and original_price != "Not available":
                    try:
                        curr = float(current_price.replace(",", ""))
                        orig = float(original_price.replace(",", ""))
                        if orig > curr:
                            discount = f"Discount: ₹{orig - curr:.2f} off ({((orig-curr)/orig)*100:.1f}%)"
                        else:
                            discount = "No discount"
                    except:
                        discount = "Could not calculate"
                
                # Extract product URL
                product_url = "Not available"
                try:
                    # Look for the title link
                    link_elements = card.find_elements(By.CSS_SELECTOR, 'h2 a')
                    if link_elements:
                        product_url = link_elements[0].get_attribute('href')
                    # Alternative method if above fails
                    if product_url == "Not available" or not product_url:
                        any_link = card.find_elements(By.CSS_SELECTOR, 'a.a-link-normal')
                        if any_link:
                            for link in any_link:
                                href = link.get_attribute('href')
                                if href and '/dp/' in href:
                                    product_url = href
                                    break
                except Exception as e:
                    logger.error(f"Error extracting Amazon product URL: {e}")
                    pass
                
                # Create product info
                product_info = (
                    f"Title: {title}\n"
                    f"Current Price: ₹{current_price}\n"
                    f"Original Price: ₹{original_price}\n"
                    f"Discount Info: {discount}\n"
                    f"Product URL: {product_url}"
                )
                
                amazon_data.append(product_info)
                logger.info(f"Scraped Amazon product {i+1}: {title[:50]}...")
                
                # Update status with progress
                jobs[job_id]['status'] = f'Processing products... ({i+1}/{product_count})'
                
            except Exception as e:
                logger.error(f"Error processing Amazon product {i+1}: {e}")
                continue
        
        if amazon_data:
            jobs[job_id]['status'] = 'Analyzing with Gemini AI...'
            result = analyze_with_gemini(amazon_data, "amazon", search_query)
            
            # Save results to file
            filename = f"amazon_{search_query}_analysis.txt"
            with open(os.path.join("static", "results", filename), "w", encoding="utf-8") as f:
                f.write(result)
            
            jobs[job_id]['status'] = 'Complete'
            jobs[job_id]['result'] = result
            jobs[job_id]['filename'] = filename
        else:
            jobs[job_id]['status'] = 'Failed - No products found'
            jobs[job_id]['result'] = 'No product data found to analyze'
                
    except Exception as e:
        logger.error(f"Error during Amazon scraping: {e}")
        jobs[job_id]['status'] = 'Failed'
        jobs[job_id]['result'] = f"Error during scraping: {str(e)}"
    
    finally:
        driver.quit()
        logger.info("Amazon browser closed")

def setup_chrome_driver_for_twitter():
    """Set up Chrome WebDriver with visible browser specifically configured for Twitter/X"""
    options = Options()
    options.add_argument("--start-maximized")  # Open browser in maximized mode
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--disable-notifications")
    
    # Add user agent to appear more like a normal browser
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    # Disable automation flags
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    driver = webdriver.Chrome(options=options)
    # Mask WebDriver to avoid detection
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def scrape_twitter(search_query, job_id):
    """Scrape tweets from X (Twitter) with manual login"""
    logger.info(f"Starting X/Twitter search for '{search_query}'")
    driver = setup_chrome_driver_for_twitter()
    tweets_text = set()

    try:
        jobs[job_id]['status'] = 'Waiting for manual login'
        
        # Go directly to X homepage first
        driver.get("https://twitter.com")
        time.sleep(3)
        
        # Then go to login page
        twitter_url = "https://twitter.com/i/flow/login"
        driver.get(twitter_url)

        logger.info("Please manually log into X/Twitter in the opened browser.")
        print("Please log in to X/Twitter manually...")
        print("The browser will wait up to 2 minutes for login to complete.")
        
        # Set up WebDriverWait for more reliable detection
        wait = WebDriverWait(driver, 120)  # Increased to 2 minutes
        
        # Wait for login to complete
        try:
            # Wait for either the home timeline or explore page to load
            wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, '//div[@data-testid="primaryColumn"]')),
                    EC.presence_of_element_located((By.XPATH, '//div[@aria-label="Home timeline"]')),
                    EC.presence_of_element_located((By.XPATH, '//input[@data-testid="SearchBox_Search_Input"]'))
                )
            )
            logger.info("Login appears successful, continuing to search...")
        except Exception as e:
            logger.warning(f"Login wait timed out: {e}")
            if "login" in driver.current_url.lower():
                raise Exception("Login not completed. Please try again and complete the login process.")

        jobs[job_id]['status'] = 'Searching for content...'
        
        # Navigate to X/Twitter search page with the query
        search_url = f"https://twitter.com/search?q={search_query}&src=typed_query&f=live"
        driver.get(search_url)
        time.sleep(8)  # Give more time for search results to load

        # Multiple selectors to try for tweets
        tweet_selectors = [
            '//div[@data-testid="tweetText"]',
            '//article//div[@lang]',
            '//div[@data-testid="tweet"]//div[@lang]'
        ]
        
        jobs[job_id]['status'] = 'Collecting tweets...'
        
        # Scroll and collect tweets
        scroll_attempts = 5  # Increase for more results
        tweets_found = 0
        
        for scroll in range(scroll_attempts):
            logger.info(f"Scroll attempt {scroll+1}/{scroll_attempts}")
            
            # Try different selectors
            for selector in tweet_selectors:
                try:
                    tweets = driver.find_elements(By.XPATH, selector)
                    if tweets:
                        for tweet in tweets:
                            tweet_content = tweet.text.strip()
                            if tweet_content and len(tweet_content) > 5:  # Ensure it's not empty or too short
                                tweets_text.add(tweet_content)
                                tweets_found += 1
                        break  # If we found tweets with this selector, no need to try others
                except Exception as e:
                    logger.warning(f"Error with selector {selector}: {e}")
                    continue
            
            # Update status
            jobs[job_id]['status'] = f'Collecting tweets... Found {len(tweets_text)} tweets'
            
            # Scroll down to load more tweets
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(5)  # Wait longer for content to load
        
        if tweets_text:
            tweets_list = list(tweets_text)
            jobs[job_id]['status'] = 'Analyzing with Gemini AI...'
            
            # Create better formatted tweet data for analysis
            formatted_tweets = "\n\n".join([f"Tweet {i+1}: {tweet}" for i, tweet in enumerate(tweets_list)])
            
            result = analyze_with_gemini(formatted_tweets, "twitter", search_query)
            
            # Save results to file
            filename = f"twitter_{search_query}_analysis.txt"
            with open(os.path.join("static", "results", filename), "w", encoding="utf-8") as f:
                f.write(result)
            
            jobs[job_id]['status'] = 'Complete'
            jobs[job_id]['result'] = result
            jobs[job_id]['filename'] = filename
        else:
            jobs[job_id]['status'] = 'Completed - No tweets found'
            jobs[job_id]['result'] = f"No tweets found for the search query '{search_query}'"

    except Exception as e:
        logger.error(f"Error during X/Twitter scraping: {e}")
        jobs[job_id]['status'] = 'Failed'
        jobs[job_id]['result'] = f"Error during X/Twitter scraping: {str(e)}"

    finally:
        driver.quit()
        logger.info("X/Twitter browser closed")
# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    platform = request.form.get('platform')
    search_query = request.form.get('search_query')
    
    if not platform or not search_query:
        return jsonify({'error': 'Platform and search query are required'}), 400
    
    # Create job ID based on timestamp and query
    job_id = f"{platform}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{search_query}"
    
    # Initialize job status
    jobs[job_id] = {
        'platform': platform,
        'query': search_query,
        'status': 'Initiated',
        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'result': None,
        'filename': None
    }
    
    # Start the appropriate scraper in a separate thread
    if platform == 'ajio':
        thread = threading.Thread(target=scrape_ajio, args=(search_query, job_id))
    elif platform == 'amazon':
        thread = threading.Thread(target=scrape_amazon, args=(search_query, job_id))
    elif platform == 'twitter':
        thread = threading.Thread(target=scrape_twitter, args=(search_query, job_id))
    else:
        return jsonify({'error': 'Invalid platform selected'}), 400
    
    thread.daemon = True
    thread.start()
    
    # Store job ID in session and redirect to job status page
    session['current_job'] = job_id
    return redirect(url_for('job_status', job_id=job_id))

@app.route('/job/<job_id>')
def job_status(job_id):
    if job_id not in jobs:
        return render_template('error.html', message="Job not found"), 404
    
    job = jobs[job_id]
    return render_template('job_status.html', job=job, job_id=job_id)

@app.route('/job/<job_id>/status')
def get_job_status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(jobs[job_id])

@app.route('/results')
def show_results():
    results_files = []
    results_dir = os.path.join("static", "results")
    
    if os.path.exists(results_dir):
        for file in os.listdir(results_dir):
            if file.endswith('.txt'):
                file_path = os.path.join(results_dir, file)
                file_size = os.path.getsize(file_path)
                modified_time = os.path.getmtime(file_path)
                modified_date = datetime.fromtimestamp(modified_time).strftime('%Y-%m-%d %H:%M:%S')
                
                results_files.append({
                    'name': file,
                    'size': f"{file_size / 1024:.1f} KB",
                    'date': modified_date
                })
    
    return render_template('results.html', results=results_files)

@app.route('/view_result/<filename>')
def view_result(filename):
    file_path = os.path.join("static", "results", filename)
    
    if not os.path.exists(file_path):
        return render_template('error.html', message="Result file not found"), 404
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Determine platform and query from filename
    parts = filename.split('_')
    platform = parts[0]
    
    return render_template('view_result.html', 
                          content=content, 
                          filename=filename,
                          platform=platform)

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
