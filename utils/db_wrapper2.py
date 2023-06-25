import re
from datetime import datetime, timedelta
from pprint import pprint

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import aliased

from orm.ORMWrapper import *

TYPE_LIST = ["TV", "ONA"]


class DataInterface:
    def __init__(self, br: BaseRelations):
        self.br = br

    # @staticmethod
    def select_group_list_for_user(self, mal_aid, user_id):
        session = self.br.get_session()
        result = (
            session.query(AniFeeds)
            .join(Users, AniFeeds.resolution == Users.preferred_res)
            .filter(AniFeeds.mal_aid == mal_aid, Users.id == user_id)
            .with_entities(AniFeeds.a_group, Users.preferred_res)
            .distinct()
        )
        session.close()
        return result

    # @staticmethod
    def select_anime_by_id(self, mal_aid, sess=None):
        if not sess:
            session = self.br.get_session()
        else:
            session = sess
        result = session.query(Anime).filter(Anime.mal_aid == mal_aid)
        if not sess:
            session.close()

        return result

    # @staticmethod
    def select_info_post_from_quotes(self):
        session = self.br.get_session()
        result = (
            session.query(Quotes)
            .filter(Quotes.keyword == "info")
            .order_by(Quotes.id)
            .with_entities(Quotes.content, Quotes.markdown)
        )
        session.close()

        return result

    # @staticmethod
    def select_user_tg_ids(self):
        session = self.br.get_session()
        result = session.query(Users.tg_id).filter(Users.tg_id != None)
        session.close()

        return result

    # @staticmethod
    def select_ptw_list_by_user_tg_id(self, user_tg_id):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .join(Users, Users.mal_uid == ListStatus.user_id)
            .filter(
                Users.tg_id == user_tg_id,
                ListStatus.status == 6,
                ListStatus.airing != 3,
            )
            .with_entities(ListStatus.title, ListStatus.mal_aid)
        )
        session.close()

        return result

    # @staticmethod
    def select_ptw_lists_by_usernames(self, nick_list):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .join(Users, Users.mal_uid == ListStatus.user_id)
            .filter(Users.mal_nick.in_(nick_list))
            .filter(ListStatus.status == 6, ListStatus.airing != 3)
            .with_entities(
                ListStatus.title,
                ListStatus.mal_aid,
                Users.mal_nick,
                ListStatus.show_type,
            )
        )
        session.close()

        return result

    # @staticmethod
    def select_registered_user_nicks(self):
        session = self.br.get_session()
        result = (
            session.query(Users)
            .filter(Users.mal_nick != None)
            .with_entities(Users.mal_nick)
        )
        session.close()

        return result

    # @staticmethod
    def select_watched_titles_in_score_interval(
        self, score_low, score_high, ignored_users
    ):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .join(Users, ListStatus.user_id == Users.mal_uid)
            .filter(ListStatus.status == 2)
            .filter(ListStatus.score >= score_low)
            .filter(ListStatus.score <= score_high)
            .filter(Users.mal_uid.notin_(ignored_users))
            .with_entities(
                ListStatus.title,
                ListStatus.mal_aid,
                Users.mal_nick,
                ListStatus.show_type,
            )
            .distinct()
        )
        session.close()

        return result

    # @staticmethod
    def select_watched_list_by_user_tg_id(self, user_tg_id):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .join(Users, ListStatus.user_id == Users.mal_uid)
            .filter(Users.tg_id == user_tg_id)
            .filter(ListStatus.status != 6)
            .with_entities(ListStatus.mal_aid)
        )
        session.close()

        return result

    # @staticmethod
    def select_quotes_by_keyword(self, keyword):
        session = self.br.get_session()
        result = (
            session.query(Quotes)
            .filter(Quotes.keyword == keyword)
            .with_entities(Quotes.content, Quotes.markdown)
        )
        session.close()

        return result

    # @staticmethod
    def select_quotes_like_keyword(self, keyword):
        session = self.br.get_session()
        result = (
            session.query(Quotes)
            .filter(Quotes.keyword.like(f"%{keyword}%"))
            .with_entities(Quotes.keyword)
        )
        session.close()

        return result

    # @staticmethod
    def select_all_quote_keywords(self):
        session = self.br.get_session()
        result = session.query(Quotes).order_by(Quotes.id).with_entities(Quotes.keyword)
        session.close()

        return result

    # @staticmethod
    def select_quote_author_by_keyword(self, keyword):
        session = self.br.get_session()
        result = (
            session.query(Quotes)
            .filter(Quotes.keyword == keyword)
            .with_entities(Quotes.keyword, Quotes.author_id)
        )
        session.close()

        return result

    # @staticmethod
    def select_titles_tracked_by_bot(self):
        session = self.br.get_session()
        result = (
            session.query(UsersXTracked)
            .join(Users, UsersXTracked.user_id == Users.id)
            .with_entities(
                UsersXTracked.mal_aid.label("mal_aid"), Users.tg_nick.label("tg_nick")
            )
        )
        session.close()

        return result

    # @staticmethod
    def select_titles_tracked_in_lists(self):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .join(Users, ListStatus.user_id == Users.mal_uid)
            .filter(ListStatus.status == 1, ListStatus.airing == 1)
            .with_entities(
                ListStatus.mal_aid.label("mal_aid"), Users.tg_nick.label("tg_nick")
            )
        )
        session.close()

        return result

    def select_all_tracked_titles(self):
        list_union = (
            self.select_titles_tracked_by_bot()
            .union(self.select_titles_tracked_in_lists())
            .subquery()
        )
        session = self.br.get_session()
        result = (
            session.query(list_union)
            .join(Anime, Anime.mal_aid == list_union.c.mal_aid)
            .filter(Anime.status == "Currently Airing")
            .group_by(Anime.mal_aid)
            .order_by(desc(func.count(list_union.c.mal_aid)))
            .with_entities(
                Anime.title, list_union.c.mal_aid, func.count(list_union.c.mal_aid)
            )
        )
        session.close()

        return result

    # @staticmethod
    def select_ongoing_ids(self):
        session = self.br.get_session()
        result = session.query(Ongoings).with_entities(Ongoings.mal_aid)
        session.close()

        return result

    # @staticmethod
    def select_fresh_movie_ids(self):
        session = self.br.get_session()
        result = (
            session.query(Anime)
            .filter(
                Anime.show_type == "Movie",
                Anime.started_at >= datetime.now() - timedelta(days=720),
            )
            .with_entities(Anime.mal_aid)
        )
        session.close()

        return result

    # # @staticmethod
    # def select_registered_tg_users_count(self):
    #     return self.select_user_tg_ids().count()
    # session.query(Users).with_entities(func.count(Users.tg_id))

    # @staticmethod
    def select_users_with_ongoing_titles_in_list(self):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .join(Users, Users.mal_uid == ListStatus.user_id)
            .filter(ListStatus.status == 1, ListStatus.airing == 1)
            .filter(ListStatus.show_type.in_(TYPE_LIST))
            .with_entities(Users.mal_nick)
            .distinct()
        )
        session.close()

        return result

    # @staticmethod
    def select_users_with_any_titles_in_list(self):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .join(Users, Users.mal_uid == ListStatus.user_id)
            .with_entities(Users.mal_nick, Users.tg_nick)
            .distinct()
        )
        session.close()

        return result

    # @staticmethod
    def select_all_recognized_titles_stats(self):
        session = self.br.get_session()
        result = (
            session.query(Ongoings)
            .join(Anime, Anime.mal_aid == Ongoings.mal_aid)
            .filter(or_(Ongoings.last_ep < Anime.episodes, Anime.episodes == None))
            .order_by(Anime.title)
            .with_entities(
                Anime.title, Ongoings.last_ep, Ongoings.last_release, Ongoings.mal_aid
            )
            .distinct()
        )
        session.close()

        return result

    # @staticmethod
    def select_locked_out_ongoings(self):
        threshold = datetime.now() - timedelta(hours=24)
        session = self.br.get_session()
        result = (
            session.query(Ongoings)
            .join(Anime, Anime.mal_aid == Ongoings.mal_aid)
            .filter(Ongoings.last_release >= threshold, Ongoings.last_ep > 1)
            .with_entities(
                Anime.title, Ongoings.last_ep, Ongoings.last_release, Ongoings.mal_aid
            )
        )
        session.close()

        return result

    # @staticmethod
    def select_future_anime(self):
        session = self.br.get_session()
        result = (
            session.query(Anime)
            .join(t_anime_x_producers, t_anime_x_producers.c.mal_aid == Anime.mal_aid)
            .join(Producers, Producers.mal_pid == t_anime_x_producers.c.mal_pid)
            .filter(or_(Anime.started_at == None, Anime.started_at > datetime.now()))
            .order_by(Anime.started_at)
            .with_entities(
                Anime.mal_aid,
                Anime.title,
                Anime.show_type,
                Anime.started_at,
                Producers.name,
            )
        )
        session.close()

        return result

    def select_future_anime_by_producer(self, producer_name):
        session = self.br.get_session()
        result = self.select_future_anime().filter(
            Producers.name.like(f"%{producer_name}%")
        )
        session.close()

        return result

    def select_future_anime_by_title(self, anime_title):
        session = self.br.get_session()
        result = self.select_future_anime().filter(Anime.title.like(f"%{anime_title}%"))
        session.close()

        return result

    # @staticmethod
    def select_user_list_address_by_tg_id(self, tg_id):
        session = self.br.get_session()
        result = (
            session.query(Users)
            .filter(Users.tg_id == tg_id, Users.mal_uid != None)
            .with_entities(Users.mal_nick, Users.service)
        )
        session.close()

        return result

    # @staticmethod
    def select_anime_seen_by_title(self, title):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .filter(ListStatus.title.like(f"%{title}%"))
            .with_entities(ListStatus.title, ListStatus.mal_aid)
            .distinct()
        )
        session.close()

        return result

    # @staticmethod
    def select_user_info_for_seen_title(self, mal_aid):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .join(Users, Users.mal_uid == ListStatus.user_id)
            .filter(ListStatus.mal_aid == mal_aid)
            .order_by(desc(ListStatus.score))
            .with_entities(
                Users.tg_nick, ListStatus.score, ListStatus.status, ListStatus.watched
            )
        )
        session.close()

        return result

    # @staticmethod
    def select_user_entry_by_tg_id(self, tg_id):
        session = self.br.get_session()
        result = session.query(Users).filter(Users.tg_id == tg_id)
        session.close()

        return result

    # @staticmethod
    def select_tracked_titles_by_user_tg_id(self, tg_id):
        session = self.br.get_session()
        result = (
            session.query(UsersXTracked)
            .join(Anime, UsersXTracked.mal_aid == Anime.mal_aid)
            .join(Users, Users.id == UsersXTracked.user_id)
            .filter(Users.tg_id == tg_id)
            .filter(Anime.status != "Finished Airing")
            .filter(UsersXTracked.dropped == False)
            .with_entities(UsersXTracked.mal_aid, Anime.title, UsersXTracked.a_group)
        )
        session.close()

        return result

    # @staticmethod
    def select_anime_to_track_from_ongoings_by_title(self, title):
        session = self.br.get_session()
        result = (
            session.query(Ongoings)
            .join(Anime, Anime.mal_aid == Ongoings.mal_aid)
            .filter(Anime.title.like(f"%{title}%"))
            .filter(Anime.show_type.in_(TYPE_LIST))
            .filter(Anime.status != "Finished Airing")
            .with_entities(Ongoings.mal_aid, Anime.title)
        )
        session.close()

        return result

    # @staticmethod
    def select_anime_tracked_by_user_id_and_anime_id(self, user_id, mal_aid):
        session = self.br.get_session()
        result = (
            session.query(UsersXTracked)
            .filter(UsersXTracked.user_id == user_id)
            .filter(UsersXTracked.mal_aid == mal_aid)
            .filter(UsersXTracked.dropped == False)
            .with_entities(UsersXTracked.mal_aid)
        )
        session.close()

        return result

    # @staticmethod
    def select_anime_tracked_by_user_id_and_title(self, user_id, title):
        session = self.br.get_session()
        result = (
            session.query(UsersXTracked)
            .join(Anime, Anime.mal_aid == UsersXTracked.mal_aid)
            .filter(Anime.title.like(f"%{title}%"))
            .filter(Anime.show_type.in_(TYPE_LIST))
            .filter(UsersXTracked.user_id == user_id)
            .filter(UsersXTracked.dropped == False)
            .with_entities(UsersXTracked.mal_aid, Anime.title)
        )
        session.close()

        return result

    # @staticmethod
    def select_gif_tags_by_media_id(self, file_id):
        session = self.br.get_session()
        result = (
            session.query(GifTags)
            .filter(GifTags.media_id == file_id)
            .with_entities(GifTags.media_id, GifTags.tag)
        )
        session.close()

        return result

    # @staticmethod
    def select_user_data_by_nick(self, nick):
        session = self.br.get_session()
        result = session.query(Users).filter(Users.tg_nick == nick)
        session.close()

        return result

    def select_gifs_by_tags(self):
        pass

    # @staticmethod
    def select_last_episodes(self, tg_id):
        session = self.br.get_session()
        result = session.query(v_last_episodes).filter(v_last_episodes.c.tg_id == tg_id)
        session.close()

        return result

    # @staticmethod
    def select_anime_info_by_exact_synonym(self, query):
        # mal_info = self.ani_db.select('distinct axs.mal_aid, a.title, a.status, a.show_type, a.eps, a.popularity',
        #                               'anime_x_synonyms axs join anime a on a.mal_aid = axs.mal_aid',
        #                               'axs.synonym = %s and a.popularity is not NULL', [query])
        session = self.br.get_session()
        mal_info = (
            session.query(AnimeXSynonyms)
            .join(Anime, Anime.mal_aid == AnimeXSynonyms.mal_aid)
            .filter(AnimeXSynonyms.synonym == query, Anime.popularity != None)
            .with_entities(
                AnimeXSynonyms.mal_aid,
                Anime.title,
                Anime.show_type,
                Anime.episodes,
                Anime.popularity,
                Anime.synced,
            )
            .distinct()
            .all()
        )
        session.close()

        return mal_info

    # @staticmethod
    def select_anime_info_by_synonym_part(self, query):
        # mal_info = self.ani_db.select('distinct axs.mal_aid, a.title, a.status, a.show_type, a.eps, a.popularity',
        #                               'anime_x_synonyms axs join anime a on a.mal_aid = axs.mal_aid',
        #                               'axs.synonym like %s and a.popularity is not NULL', [f'%{query}%'])
        session = self.br.get_session()
        mal_info = (
            session.query(AnimeXSynonyms)
            .join(Anime, Anime.mal_aid == AnimeXSynonyms.mal_aid)
            .filter(AnimeXSynonyms.synonym.like(f"%{query}%"), Anime.popularity != None)
            .with_entities(
                AnimeXSynonyms.mal_aid,
                Anime.title,
                Anime.show_type,
                Anime.episodes,
                Anime.popularity,
                Anime.synced,
            )
            .distinct()
            .all()
        )
        session.close()

        return mal_info

    # @staticmethod
    # todo tbh this requires a specific instrument like elastic
    def select_anime_info_by_split_words(self, query):
        q_string = "%" + "%".join(re.sub(r"\W+", " ", query).split(" ")) + "%"
        # mal_info = self.ani_db.select('distinct axs.mal_aid, a.title, a.status, a.show_type, a.eps, a.popularity',
        #                               'anime_x_synonyms axs join anime a on a.mal_aid = axs.mal_aid',
        #                               'axs.synonym rlike %s and a.popularity is not NULL',
        #                               [r_string])
        session = self.br.get_session()
        mal_info = (
            session.query(AnimeXSynonyms)
            .join(Anime, Anime.mal_aid == AnimeXSynonyms.mal_aid)
            .filter(AnimeXSynonyms.synonym.like(q_string), Anime.popularity != None)
            .with_entities(
                AnimeXSynonyms.mal_aid,
                Anime.title,
                Anime.show_type,
                Anime.episodes,
                Anime.popularity,
                Anime.synced,
            )
            .distinct()
            .all()
        )
        session.close()

        return mal_info

    # @staticmethod
    def select_relations_data(self):
        session = self.br.get_session()
        result = session.query(Anime).with_entities(
            Anime.mal_aid,
            Anime.related,
            Anime.title,
        )
        session.close()

        return result

    # handler_modules SELECT methods end
    # list_parser SELECT methods

    # @staticmethod
    def select_service_users_ids(self, service_name):
        session = self.br.get_session()
        result = (
            session.query(Users)
            .filter(Users.service == service_name)
            .with_entities(Users.mal_nick, Users.mal_uid)
        )
        session.close()

        return result

    # @staticmethod
    def select_user_is_in_list_status(self, service_user_id):
        session = self.br.get_session()
        result = (
            session.query(ListStatus)
            .filter(ListStatus.user_id == service_user_id)
            .with_entities(ListStatus.user_id)
        )
        session.close()

        return result

    # @staticmethod
    def select_genres(self):
        session = self.br.get_session()
        result = session.query(Genres.mal_gid)
        session.close()

        return result

    # @staticmethod
    def select_licensors(self):
        session = self.br.get_session()
        result = session.query(Licensors.name)
        session.close()

        return result

    # @staticmethod
    def select_producers(self):
        session = self.br.get_session()
        result = session.query(Producers.mal_pid)
        session.close()

        return result

    # feed_parser SELECT methods

    # @staticmethod
    def select_feed_entry_by_title_and_date(self, a_title, a_date, session):
        result = session.query(AniFeeds).filter(
            AniFeeds.title == a_title, AniFeeds.date == a_date
        )

        return result

    # @staticmethod
    def select_last_feed_entry(self):
        session = self.br.get_session()
        result = (
            session.query(AniFeeds)
            .order_by(desc(AniFeeds.date))
            .limit(1)
            .with_entities(AniFeeds.date, AniFeeds.title)
        )
        session.close()

        return result

    # @staticmethod
    def select_unchecked_feed_entries(self, session):
        result = (
            session.query(AniFeeds)
            .filter(AniFeeds.checked == 0)
            .order_by(AniFeeds.date)
        )

        return result

    # @staticmethod
    def select_ongoing_anime_id_by_synonym(self, synonym, session):
        query = session.query(AnimeXSynonyms).join(Anime)
        result = (
            query.filter(
                AnimeXSynonyms.synonym == synonym,
                Anime.status != "Finished Airing",
            )
            .with_entities(AnimeXSynonyms.mal_aid)
            .first()
        )
        if result:
            return result[0], 0
        else:
            AnimeSequels = aliased(Anime)
            result = (
                query.join(
                    AnimeXContinuations, AnimeXContinuations.anime_id == Anime.mal_aid
                )
                .join(
                    AnimeSequels, AnimeSequels.mal_aid == AnimeXContinuations.sequel_id
                )
                .filter(
                    AnimeXSynonyms.synonym == synonym,
                    AnimeSequels.status != "Finished Airing",
                )
                .with_entities(AnimeSequels.mal_aid, AnimeXContinuations.episode_shift)
                .first()
            )

            if not result:
                return None, 0

            return result

    # @staticmethod
    def select_mal_anime_ids_by_title_part(self, title, session):
        result = (
            session.query(Ongoings)
            .join(Anime)
            .filter(
                Anime.show_type.in_(TYPE_LIST),
                Anime.status != "Finished Airing",
                Anime.started_at < datetime.now() + timedelta(hours=24),
            )
            .filter(Anime.title.like(f"%{title}%"))
            .with_entities(Ongoings.mal_aid)
            .distinct()
        )

        return [e[0] for e in result.all()]

    def select_all_anime_ids(self):
        session = self.br.get_session()
        result = session.query(Anime).with_entities(Anime.mal_aid)
        session.close()
        return result

    # @staticmethod
    def select_torrent_is_saved_in_database(
        self, mal_aid, group, episode, res, size, session
    ):
        result = session.query(TorrentFiles).filter(
            TorrentFiles.mal_aid == mal_aid,
            TorrentFiles.a_group == group,
            TorrentFiles.episode == episode,
            TorrentFiles.res == res,
            TorrentFiles.file_size == size,
        )

        return result

    # @staticmethod
    def select_last_ongoing_ep_by_id(self, mal_aid, session):
        result = (
            session.query(Ongoings)
            .filter(Ongoings.mal_aid == mal_aid)
            .with_entities(Ongoings.last_ep)
        )

        return result

    # jobs SELECT methods

    # @staticmethod
    def select_today_titles(self, user_id=None):
        session = self.br.get_session()
        result = session.query(v_today_titles)
        if user_id:
            result = result.join(
                UsersXTracked, UsersXTracked.mal_aid == v_today_titles.c.mal_aid
            ).filter_by(
                user_id=user_id,
                dropped=False,
            )
        session.close()

        return result

    # @staticmethod
    def select_titles_pending_for_delivery(self):
        session = self.br.get_session()
        result = session.query(v_pending_delivery)
        session.close()

        return result

    def select_extended_user_stats(self, season):
        session = self.br.get_session()
        result = (
            session.query(
                v_extended_user_stats.c.mal_aid,
                v_extended_user_stats.c.season,
                v_extended_user_stats.c.title,
                v_extended_user_stats.c.tg_nick,
                func.min(v_extended_user_stats.c.status),
                func.min(v_extended_user_stats.c.watched),
            )
            .group_by(v_extended_user_stats.c.mal_aid, v_extended_user_stats.c.tg_nick)
            .filter(v_extended_user_stats.c.season == season)
        )
        session.close()

        return result

    # @staticmethod
    def select_waifu_blocker_shows(self):
        session = self.br.get_session()
        result = (
            session.query(Anime)
            .filter(
                or_(
                    and_(Anime.show_type == "ONA", Anime.episodes > 3),
                    Anime.show_type == "TV",
                )
            )
            .with_entities(Anime.mal_aid)
        )
        session.close()

        return result

    # synonyms SELECT methods
    # @staticmethod
    def select_by_synonym_id_pair(self, mal_aid, synonym):
        session = self.br.get_session()
        result = session.query(AnimeXSynonyms).filter(
            AnimeXSynonyms.mal_aid == mal_aid, AnimeXSynonyms.synonym == synonym
        )
        session.close()

        return result

    # @staticmethod
    def select_existing_synonyms(self):
        session = self.br.get_session()
        result = session.query(AnimeXSynonyms).with_entities(
            AnimeXSynonyms.mal_aid, AnimeXSynonyms.synonym
        )
        session.close()

        return result

    # @staticmethod
    def select_all_possible_synonyms(self):
        session = self.br.get_session()
        result = session.query(Anime).with_entities(
            Anime.mal_aid,
            Anime.title,
            Anime.title_english,
            Anime.title_japanese,
            Anime.title_synonyms,
        )
        session.close()

        return result

    # handler_modules INSERT methods
    # @staticmethod
    def insert_new_tracked_title(self, user_id, mal_aid, last_ep, a_group):
        new_tracked = UsersXTracked(
            user_id=user_id, mal_aid=mal_aid, last_ep=last_ep, a_group=a_group
        )
        session = self.br.get_session()
        check_dropped = (
            session.query(UsersXTracked)
            .filter(UsersXTracked.user_id == user_id)
            .filter(UsersXTracked.mal_aid == mal_aid)
            .filter(UsersXTracked.dropped == True)
        ).first()
        if check_dropped:
            check_dropped.dropped = False
        else:
            session.add(new_tracked)
        session.commit()
        session.close()

    def update_seasonal_data(self, cross_data, season_name, session):
        session.query(AnimeXSeasons).filter(
            AnimeXSeasons.season == season_name
        ).delete()
        for item in cross_data:
            anime_season_entry = AnimeXSeasons(**item)
            session.add(anime_season_entry)

    # todo this is some serious fuckery right here
    def upsert_anime_entry(self, a_entry, session):
        local_entry = self.select_anime_by_id(a_entry["mal_aid"], sess=session)
        if not local_entry.first():
            local_entry = Anime(**a_entry)
            session.add(local_entry)
        else:
            local_entry.update(a_entry)
        session.commit()

    # @staticmethod
    def insert_tags_into_gif_tags(self, values):
        session = self.br.get_session()
        for entry in values:
            new_tag = GifTags(media_id=entry[0], tag=entry[1])
            session.add(new_tag)
        session.commit()
        session.close()

    # @staticmethod
    def insert_new_user(self, tg_nick, tg_id):
        session = self.br.get_session()
        new_user = Users(tg_nick=tg_nick, tg_id=tg_id)
        session.add(new_user)
        session.commit()
        session.close()

    # from former db_wrapper
    # @staticmethod
    def insert_new_quote(self, keyword, content, markdown, author_id):
        session = self.br.get_session()
        new_quote = Quotes(
            keyword=keyword, content=content, markdown=markdown, author_id=author_id
        )
        session.add(new_quote)
        session.commit()
        session.close()

    # @staticmethod
    def insert_new_genres(self, genre_list, session):
        for genre in genre_list:
            new_genre = Genres(mal_gid=genre["mal_id"], name=genre["name"])
            session.add(new_genre)

    # @staticmethod
    def insert_new_producers(self, producer_list, session):
        for producer in producer_list:
            new_producer = Producers(mal_pid=producer["mal_id"], name=producer["name"])
            session.add(new_producer)

    # @staticmethod
    def insert_new_licensors(self, licensor_list, session):
        for licensor in licensor_list:
            new_licensor = Licensors(name=licensor["name"])
            session.add(new_licensor)

    # @staticmethod
    def insert_new_axg(self, anime, session):
        anime_ = session.query(Anime).filter(Anime.mal_aid == anime["mal_id"]).first()
        new_axg = [
            genre for genre in anime["genres"] if genre["mal_id"] not in anime_.genres
        ]
        for genre in new_axg:
            genre_ = (
                session.query(Genres).filter(Genres.mal_gid == genre["mal_id"]).first()
            )
            anime_.genres.append(genre_)

    # @staticmethod
    def insert_new_axp(self, anime, session):
        anime_ = session.query(Anime).filter(Anime.mal_aid == anime["mal_id"]).first()
        new_axp = [
            producer
            for producer in anime["producers"]
            if producer["mal_id"] not in anime_.producers
        ]
        for producer in new_axp:
            producer_ = (
                session.query(Producers)
                .filter(Producers.mal_pid == producer["mal_id"])
                .first()
            )
            anime_.producers.append(producer_)

    # @staticmethod
    def insert_new_axl(self, anime, session):
        anime_ = session.query(Anime).filter(Anime.mal_aid == anime["mal_id"]).first()
        new_axl = [
            licensor
            for licensor in anime["licensors"]
            if licensor not in anime_.licensors
        ]
        for licensor in new_axl:
            licensor_ = (
                session.query(Licensors).filter(Licensors.name == licensor["name"]).first()
            )
            anime_.licensors.append(licensor_)

    # @staticmethod
    def insert_new_animelist(self, mal_uid, anime_list):
        session = self.br.get_session()
        for anime in anime_list:
            list_entry = ListStatus(
                user_id=mal_uid,
                **anime,
            )
            session.add(list_entry)
        session.commit()
        session.close()

    def insert_new_sequel_data(self, entries):
        session = self.br.get_session()
        session.query(AnimeXContinuations).delete()
        for data in entries:
            continuation = AnimeXContinuations(
                anime_id=data[0],
                sequel_id=data[1],
                episode_shift=data[2],
            )
            session.add(continuation)
        session.commit()
        session.close()

    # feed_parser INSERT methods
    # @staticmethod
    def insert_new_feed_entry(self, a_title, a_date, a_link, a_description, session):
        feed_entry = AniFeeds(
            title=a_title, date=a_date, link=a_link, description=a_description
        )
        session.add(feed_entry)
        session.commit()

    # @staticmethod
    def insert_new_torrent_file(
        self, mal_aid, group, episode, filename, res, size, session
    ):
        torrent_file = TorrentFiles(
            mal_aid=mal_aid,
            a_group=group,
            episode=episode,
            torrent=filename,
            res=res,
            file_size=size,
        )
        session.add(torrent_file)
        session.commit()

    # synonyms INSERT methods
    # @staticmethod
    def insert_new_synonym(self, mal_aid, synonym):
        new_synonym = AnimeXSynonyms(mal_aid=mal_aid, synonym=synonym)
        session = self.br.get_session()
        try:
            session.add(new_synonym)
            session.commit()
        except Exception:
            print("INTEGRITY FAILURE")
            session.rollback()
        finally:
            session.close()

    # INSERT methods end
    # handler_modules DELETE methods
    # @staticmethod
    def delete_tracked_anime(self, user_id, mal_aid):
        session = self.br.get_session()
        result = (
            session.query(UsersXTracked)
            .filter(UsersXTracked.user_id == user_id)
            .filter(UsersXTracked.mal_aid == mal_aid)
            .first()
        )
        result.dropped = True
        session.commit()
        session.close()

    # @staticmethod
    def delete_quotes_by_keyword(self, keyword):
        session = self.br.get_session()
        session.query(Quotes).filter(Quotes.keyword == keyword).delete()
        session.close()

    # ListStatus DELETE handler_modules
    # @staticmethod
    def delete_list_by_user_id(self, user_id):
        session = self.br.get_session()
        session.query(ListStatus).filter(ListStatus.user_id == user_id).delete()
        session.commit()
        session.close()

    # handler_modules UPDATE methods
    # @staticmethod
    def update_quote_by_keyword(self, keyword, content):
        session = self.br.get_session()
        quote = session.query(Quotes).filter(Quotes.keyword == keyword).first()
        quote.content = content
        session.commit()
        session.close()

    # @staticmethod
    def update_users_id_for_manually_added_lists(self, user_id, user_name):
        session = self.br.get_session()
        user = session.query(Users).filter(Users.tg_nick == user_name).first()
        user.tg_id = user_id
        session.commit()
        session.close()

    # @staticmethod
    def update_group_for_users_release_tracking(self, a_group, user_id, mal_aid):
        session = self.br.get_session()
        release = (
            session.query(UsersXTracked)
            .filter(UsersXTracked.user_id == user_id, UsersXTracked.mal_aid == mal_aid)
            .first()
        )
        release.a_group = a_group
        release.last_ep = 0
        session.commit()
        session.close()

    # @staticmethod
    def update_users_preferred_resolution(self, res, tg_id):
        session = self.br.get_session()
        user = session.query(Users).filter(Users.tg_id == tg_id).first()
        user.preferred_res = res
        session.commit()
        session.close()

    # todo think about additional checking for correct episode numbers
    # @staticmethod
    def update_release_status_for_user_after_delivery(
        self, episode, user_id, mal_aid, a_group
    ):
        session = self.br.get_session()
        status = (
            session.query(UsersXTracked)
            .filter(
                UsersXTracked.user_id == user_id,
                UsersXTracked.mal_aid == mal_aid,
                UsersXTracked.a_group == a_group,
                UsersXTracked.last_ep < episode,
            )
            .first()
        )
        if status:
            status.last_ep = episode
            session.commit()
        session.close()

    # Feed parser update methods
    # todo not sure if it's actually needed
    # @staticmethod
    def update_anifeeds_entry(self, a_link, a_description, a_title, a_date, session):
        feed_entry = (
            session.query(AniFeeds)
            .filter(AniFeeds.title == a_title, AniFeeds.date == a_date)
            .first()
        )
        feed_entry.link = a_link
        feed_entry.description = a_description
        session.commit()

    # @staticmethod
    def update_anifeeds_with_parsed_information(
        self, mal_aid, a_group, resolution, episode, size, title, date, session
    ):
        feed_entry = (
            session.query(AniFeeds)
            .filter(AniFeeds.title == title, AniFeeds.date == date)
            .first()
        )
        feed_entry.mal_aid = mal_aid
        feed_entry.a_group = a_group
        feed_entry.resolution = resolution
        feed_entry.ep = episode
        feed_entry.size = size
        feed_entry.checked = 1
        session.commit()

    # @staticmethod
    def update_anifeeds_unrecognized_entry(self, size, title, date, session):
        feed_entry = (
            session.query(AniFeeds)
            .filter(AniFeeds.title == title, AniFeeds.date == date)
            .first()
        )
        feed_entry.size = size
        feed_entry.checked = 1
        session.commit()

    # List parser update methods
    # @staticmethod
    def update_users_service_id_for_service_nick(self, service_uid, service_nick):
        session = self.br.get_session()
        user = session.query(Users).filter(Users.mal_nick == service_nick).first()
        user.mal_uid = service_uid
        session.commit()
        session.close()

    def switch_torrent_delivery(self, tg_id):
        session = self.br.get_session()
        user = session.query(Users).filter(Users.tg_id == tg_id).first()
        result = not bool(user.send_torrents)
        user.send_torrents = result
        session.commit()
        session.close()
        return result


if __name__ == "__main__":
    di = DataInterface(BaseRelations())
    # group_list = [entry[0] for entry in di.select_group_list_for_user(38656, 3).all()]
    # pprint(group_list)
    # anime_by_id = di.select_anime_by_id(38656).one()
    # pprint(anime_by_id.title_eng)
    info_post = di.select_info_post_from_quotes().one()
    pprint(info_post)
    # user_tg_ids = di.select_user_tg_ids().all()
    # pprint(user_tg_ids)
    # user_ptw_list = di.select_ptw_list_by_user_tg_id(37718983).all()
    # pprint(user_ptw_list)
    # ptw_lists_by_username = di.select_ptw_lists_by_usernames(['Valion', 'Utena']).all()
    # pprint(ptw_lists_by_username)
    # pprint(di.select_titles_tracked_in_lists().all())
    # pprint(di.select_titles_tracked_by_bot().all())
    # pprint(di.select_all_tracked_titles().all())

    # print(di.select_registered_tg_users_count())
    # print(di.select_ongoing_ids().count())
    # print(di.select_ongoing_ids().all())
    # pprint(di.select_all_recognized_titles_stats().all())
    # pprint(di.select_future_anime_by_title('OVA').all())
    # pprint(di.select_last_episodes(37718983).all())
    # pprint(di.select_last_feed_entry().one())
    # pprint(di.select_unchecked_feed_entries().all())
    # di.insert_new_tracked_title(3, 39039, 100, 'HorribleSubs')
    # pprint(di.select_quote_author_by_keyword('info').first())
