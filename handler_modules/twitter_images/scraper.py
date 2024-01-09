from functools import lru_cache
from pprint import pprint
from typing import Optional

from playwright.sync_api import sync_playwright
from nested_lookup import nested_lookup

import config
from handler_modules.twitter_images.parser import parse_tweet


@lru_cache()
def scrape_tweet(url: str) -> Optional[dict]:
    """
    Scrape a single tweet page for Tweet thread e.g.:
    https://twitter.com/Scrapfly_dev/status/1667013143904567296
    Return parent tweet, reply tweets and recommended tweets
    """
    _xhr_calls = []
    _calls = []

    def intercept_response(response):
        """capture all background requests and save them"""
        # we can extract details from background requests
        _calls.append(response)
        if response.request.resource_type == "xhr":
            _xhr_calls.append(response)
        return response

    with sync_playwright() as pw:
        browser = pw.firefox.launch(
            args=['--ignore-certificate-errors'],
            proxy={
                'server': config.proxy_url,
                'username': config.proxy_username,
                'password': config.proxy_password,
            },
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )
        page = context.new_page()

        # enable background request intercepting:
        page.on("response", intercept_response)
        # go to url and wait for the page to load
        page.goto(url)
        page.wait_for_selector("[data-testid='tweet'], [data-testid='error-detail'], span:has-text('Retry')")
        # page.wait_for_load_state("networkidle", timeout=5000)

        # find all tweet background requests:
        tweet_calls = [f for f in _xhr_calls if "TweetResultByRestId" in f.url]
        tweets = []
        for xhr in tweet_calls:
            data = xhr.json()
            xhr_tweets = nested_lookup("tweetResult", data)
            tweets.extend([tweet["result"] for tweet in xhr_tweets if "result" in tweet])

        # Now that we have all tweets we can parse them into a thread
        # The first tweet is the parent, the rest are replies or suggested tweets
        if tweets and not tweets[0].get('__typename') == 'TweetUnavailable':
            parent = tweets.pop(0)
        else:
            return None
        # replies = []
        # other = []
        # for tweet in tweets:
        #     if tweet["conversation_id"] == parent["conversation_id"]:
        #         replies.append(tweet)
        #     else:
        #         other.append(tweet)
        return parent


if __name__ == "__main__":
    scraped_data = scrape_tweet("https://twitter.com/Djelsamina/status/1719747468861075806")
    pprint(scraped_data)
    parsed_data = parse_tweet(scraped_data)
    pprint(parsed_data)
