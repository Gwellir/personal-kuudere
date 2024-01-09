from typing import Dict

import jmespath


def parse_user(user_data):
    return user_data


def parse_tweet(data: Dict) -> Dict:
    """Parse Twitter tweet JSON dataset for the most important fields"""
    result = jmespath.search(
        """{
        created_at: legacy.created_at,
        attached_urls: legacy.entities.urls[].expanded_url,
        attached_urls2: legacy.entities.url.urls[].expanded_url,
        attached_media: legacy.entities.media[],
        tagged_users: legacy.entities.user_mentions[].screen_name,
        tagged_hashtags: legacy.entities.hashtags[].text,
        favorite_count: legacy.favorite_count,
        bookmark_count: legacy.bookmark_count,
        quote_count: legacy.quote_count,
        reply_count: legacy.reply_count,
        retweet_count: legacy.retweet_count,
        quote_count: legacy.quote_count,
        text: legacy.full_text,
        is_quote: legacy.is_quote_status,
        is_retweet: legacy.retweeted,
        language: legacy.lang,
        user_id: legacy.user_id_str,
        id: legacy.id_str,
        name: core.user_results.result.legacy.name,
        screen_name: core.user_results.result.legacy.screen_name,
        conversation_id: legacy.conversation_id_str,
        source: source,
        views: views.count
    }""",
        data,
    )
    result["poll"] = {}
    poll_data = jmespath.search("card.legacy.binding_values", data) or []
    for poll_entry in poll_data:
        key, value = poll_entry["key"], poll_entry["value"]
        if "choice" in key:
            result["poll"][key] = value["string_value"]
        elif "end_datetime" in key:
            result["poll"]["end"] = value["string_value"]
        elif "last_updated_datetime" in key:
            result["poll"]["updated"] = value["string_value"]
        elif "counts_are_final" in key:
            result["poll"]["ended"] = value["boolean_value"]
        elif "duration_minutes" in key:
            result["poll"]["duration"] = value["string_value"]
    user_data = jmespath.search("core.user_results.result", data)
    if user_data:
        result["user"] = parse_user(user_data)
    return result