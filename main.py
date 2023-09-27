import time
import json
import csv
from random import randint
import requests
import datetime

import schedule
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from seleniumwire import webdriver as wiredriver

def dismiss_alert(driver):
    try:
        WebDriverWait(driver, 5).until(EC.alert_is_present())
        alert = Alert(driver)
        alert.dismiss()
    except:
        pass

def init_chromedriver():
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument("start-maximized")

    driver = wiredriver.Chrome(options=chrome_options, seleniumwire_options={'enable_har': True})
    return driver

def get_har_file(driver, page_id, cookies):
    driver.get("https://www.facebook.com")
    time.sleep(5)
    for cookie in cookies:
        driver.add_cookie(cookie)

    driver.execute_script("window.alert = function() {};")
    url = f"https://www.facebook.com/profile.php?id={page_id}&sk=followers"
    driver.get(url)
    try:
        alert = driver.switch_to.alert
        alert.accept()
    except:
        print("No Alert")

    WebDriverWait(driver, 10).until(lambda driver: driver.execute_script("return document.readyState") == "complete")

    driver.execute_script("window.alert = function() {};")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight + 1000);")
    time.sleep(5)

    har = driver.har

    with open('network_traffic.har', 'w') as har_file:
        har_file.write(str(har))

    return har

def get_continuation_token(har):
    try:
        if isinstance(har, str):
            har = json.loads(har)

        for entry in har['log']['entries']:
            request = entry.get('request')
            if not request:
                continue

            post_data = request.get('postData')
            if not post_data:
                continue

            params = post_data.get('params')
            if not params:
                continue

            cursor = None
            for param in params:
                if param['name'] == 'variables':
                    variables = param['value']
                    variables = json.loads(variables)
                    if 'cursor' in variables and 'count' in variables and variables['count'] == 8:
                        return variables['cursor'], '&'.join([f"{param['name']}={param['value']}" for param in params])
    except Exception as e:
        print(e)
        return None

def scrape_list(har, cookies_json, page_id):
    cursor, param_string = get_continuation_token(har)
    first_cursor = cursor

    if not cursor:
        print("No continuation token found")
        return

    cookie_string = '; '.join([f"{cookie['name']}={cookie['value']}" for cookie in cookies_json])

    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    yesterday = yesterday.strftime("%Y-%m-%d")
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    followers = set()  # Use a set to store followers for faster membership check

    try:
        with open("followers.csv", "r", encoding='utf-8') as f:
            csv_reader = csv.reader(f)
            next(csv_reader)  # Skip the header row
            for row in csv_reader:
                followers.add(row[2])  # Assuming 'id' is in the third column
    except FileNotFoundError:
        pass

    cursor = cursor
    with open("followers.csv", "a", newline='', encoding='utf-8') as csv_file:
        csv_writer = csv.writer(csv_file)
        caught_up = False
        while True:
            time.sleep(randint(1, 5))
            if caught_up:
                break

            url = "https://www.facebook.com/api/graphql"
            payload = param_string.replace(first_cursor, cursor)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Content-Type": "application/x-www-form-urlencoded",
                "X-FB-Friendly-Name": "ProfileCometAppCollectionListRendererPaginationQuery",
                "X-ASBD-ID": "129477",
                "Origin": "https://www.facebook.com",
                "Alt-Used": "www.facebook.com",
                "Connection": "keep-alive",
                "Referer": f"https://www.facebook.com/profile.php?id={page_id}&sk=followers",
                "Cookie": cookie_string,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "TE": "trailers",
            }

            response = requests.post(url, data=payload, headers=headers)
            response = response.json()
            if response.get('error'):
                print(f"Error encountered: {response['error']}")
                break

            if response['data']['node']['pageItems']['page_info']['has_next_page']:
                continuation_token = response['data']['node']['pageItems']['page_info']['end_cursor']
            else:
                continuation_token = None

            profiles = response['data']['node']['pageItems']['edges']

            existing_data = []

            new_data = []
            if 'data' in response and 'node' in response['data'] and 'pageItems' in response['data']['node']:
                profiles = response['data']['node']['pageItems']['edges']
                for profile in profiles:
                    profile = profile['node']
                    image = profile['image']['uri']
                    title = profile['title']['text']
                    id = profile['actions_renderer']['profile_actions'][0]['client_handler']['profile_action'][
                        'profile_owner']['id']
                    subtitle_text = profile['subtitle_text'].get('text', 'n/a')
                    url = profile['url']

                    if id in followers:
                        print(f"Caught all new followers for today. Total followers: {len(existing_data) - 1}")
                        caught_up = True
                        break

                    if id not in followers:  # Check if the follower is not already in the CSV
                        followers.add(id)  # Add the new follower to the set
                        data = [image, title, id, subtitle_text, url, today]
                        new_data.append(data)
                        print(f"Added Profile - {title}")

            if len(new_data) == 0:
                print("No new followers found")
                break

            existing_data.extend(new_data)

            with open("followers.csv", "a+", newline='', encoding='utf-8') as csv_file:
                csv_writer = csv.writer(csv_file)
                csv_writer.writerows(existing_data)

            print(continuation_token)
            cursor = continuation_token



def job():
    driver = init_chromedriver()
    cookies = [
        {
            "name": "datr",
            "value": "X_cPZaBYqXNFYY5JnuGYYnl2",
            "domain": ".facebook.com",
            "path": "/",
            "expires": 1730105190,
            "httpOnly": True,
            "secure": True
        },
        {
            "name": "sb",
            "value": "o2kBZecPI7AgppvB2y-BFsQm",
            "domain": ".facebook.com",
            "path": "/",
            "expires": 1730105190,
            "httpOnly": True,
            "secure": True
        },
        {
            "name": "i_user",
            "value": "61550964032031",
            "domain": ".facebook.com",
            "path": "/",
            "expires": 1727081198,
            "httpOnly": False,
            "secure": True
        },
        {
            "name": "dpr",
            "value": "0.8955223880597015",
            "domain": ".facebook.com",
            "path": "/",
            "expires": 1696152756,
            "httpOnly": False,
            "secure": True
        },
        {
            "name": "c_user",
            "value": "100094654806004",
            "domain": ".facebook.com",
            "path": "/",
            "expires": 1727084752,
            "httpOnly": False,
            "secure": True
        },
        {
            "name": "xs",
            "value": "16%3A1ugeF4uVYC8fkQ%3A2%3A1695545190%3A-1%3A-1%3A%3AAcVUVUryS4Nvi0CFaMCCoHKBh4H9e59mFd0rqpkZJw",
            "domain": ".facebook.com",
            "path": "/",
            "expires": 1727084752,
            "httpOnly": True,
            "secure": True
        },
        {
            "name": "fr",
            "value": "09CRjiF1zhgL2lfnx.AWU0HT_b1HKz8sMq07mUnQ2xPq0.BlEAVR.8n.AAA.0.0.BlEAVR.AWVQDHtpfhY",
            "domain": ".facebook.com",
            "path": "/",
            "expires": 1703324752,
            "httpOnly": True,
            "secure": True
        },
        {
            "name": "wd",
            "value": "1525x729",
            "domain": ".facebook.com",
            "path": "/",
            "expires": 1696158096,
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax"
        }
    ]
    page_id = "61550964032031"
    har = get_har_file(driver, page_id, cookies)
    driver.quit()
    scrape_list(har, cookies, page_id)

schedule.every().day.at("00:00").do(job)

while True:
    schedule.run_pending()
    time.sleep(1)
