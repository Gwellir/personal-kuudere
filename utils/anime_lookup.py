from datetime import datetime, timedelta

from logger.logger import ANIMEBASE_LOG


class AnimeLookup:
    def __init__(self, jikan, data_interface):
        self._jikan = jikan
        self._di = data_interface

    # todo add synonyms
    def store_anime(self, a_entry):
        session = self._di.br.get_session()
        self._di.upsert_anime_entry(a_entry, session)
        session.commit()
        session.close()

    def get_anime_by_aid(self, mal_aid, forced=False):
        local_result = self._di.select_anime_by_id(mal_aid).first()
        answer = (
            {
                "mal_id": local_result.mal_aid,
                "title": local_result.title,
                "airing": local_result.status == "Currently Airing",
                "type": local_result.show_type,
                "members": local_result.members,
            }
            if local_result
            else None
        )
        if not local_result or not local_result.popularity or forced:
            # or datetime.now() - local_result.synced > timedelta(days=14):
            output = self._jikan.anime(mal_aid)
            if not output:
                return answer
            self.store_anime(output)
        else:
            output = answer
        return output

    # todo add streamlined search in cached base
    def lookup_anime_info_by_title(self, a_title: str, ongoing=False):
        """Searches the DB for titles matching query,
        order: exact match > substring > split words in the same order > MAL api search"""

        mal_info = self._di.select_anime_info_by_exact_synonym(a_title)
        if not mal_info:
            mal_info = self._di.select_anime_info_by_synonym_part(a_title)
        if not mal_info:
            mal_info = self._di.select_anime_info_by_split_words(a_title)
        if not mal_info:
            print(f'Looking up "{a_title}" on MAL...')
            search_results = self.mal_search_by_name(a_title, ongoing=ongoing)

            mal_info = [
                (
                    result["mal_id"],
                    result["title"],
                    result["airing"],
                    result["type"],
                    result["members"],
                )
                for result in search_results
            ]
            if mal_info:
                self.get_anime_by_aid(mal_info[0][0])
            else:
                return None
        # updates entries older than two weeks upon user`s request
        elif mal_info and datetime.now() - mal_info[0][5] > timedelta(days=14):
            result = self.get_anime_by_aid(mal_info[0][0])
            mal_info[0] = (
                result["mal_id"],
                result["title"],
                result["airing"],
                result["type"],
                result["members"],
            )
        else:
            # mal_info = sorted(mal_info, key=lambda item: len(item[1]), reverse=False)
            mal_info = sorted(mal_info, key=lambda item: len(item[1]))
        if ongoing:
            mal_info = [entry for entry in mal_info if entry[2] is True]
        return mal_info

    def mal_search_by_name(self, name: str, ongoing=False) -> list:
        params = dict()
        if ongoing:
            params["status"] = "airing"
        response = self._jikan.search(
            "anime",
            name,
            parameters=params,
        )
        results = response if response else []
        ANIMEBASE_LOG.debug(
            f"Searching MAL for '{name}'({ongoing}): {[(res['title'], res['mal_id']) for res in results]}"
        )
        if ongoing:
            return self._filter_ongoing(results)
        return results

    def _filter_ongoing(self, results: list) -> list:
        ong_types = ["TV", "ONA", "OVA"]
        ratings = ["G - All Ages", "PG-13 - Teens 13 or older", "R - 17+ (violence & profanity)", "R+ - Mild Nudity"]
        filtered = [
            res
            for res in results
            if res.get("type") in ong_types
            and res.get("rating") in ratings
            and res.get("airing") is True
        ]
        ANIMEBASE_LOG.debug(f"Filtered airing MAL results: {filtered}")
        return filtered
