from typing import Dict

import jmespath


def parse_tweet(data: Dict) -> Dict:
    """Parse Twitter tweet JSON dataset for the most important fields"""
    result = jmespath.search(
        """{
        created_at: date,
        attached_media: media_extended[],
        favorite_count: likes,
        reply_count: replies,
        retweet_count: retweets,
        text: text,
        id: conversationID,
        name: user_name,
        screen_name: user_screen_name,
        sensitive: possibly_sensitive
    }""",
        data,
    )

    return result
