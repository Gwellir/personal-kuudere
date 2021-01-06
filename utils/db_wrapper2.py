import re

from orm.ORMWrapper import *
from pprint import pprint
from sqlalchemy import func, desc, or_, and_
from datetime import datetime, timedelta


TYPE_LIST = ['TV', 'ONA']

br = BaseRelations()


class DataInterface:
    @staticmethod
    def select_group_list_for_user(mal_aid, user_id):
        session = br.get_session()
        result = session.query(AniFeeds).\
                 join(Users, AniFeeds.resolution == Users.preferred_res).\
                 filter(AniFeeds.mal_aid == mal_aid, Users.id == user_id).\
                 with_entities(AniFeeds.a_group, Users.preferred_res).distinct()
        session.close()
        return result


    @staticmethod
    def select_anime_by_id(mal_aid):
        session = br.get_session()
        result = session.query(Anime).filter(Anime.mal_aid == mal_aid)
        session.close()

        return result

    @staticmethod
    def select_info_post_from_quotes():
        session = br.get_session()
        result = session.query(Quotes).filter(Quotes.keyword == 'info').order_by(Quotes.id).\
            with_entities(Quotes.content, Quotes.markdown)
        session.close()

        return result

    @staticmethod
    def select_user_tg_ids():
        session = br.get_session()
        result = session.query(Users).filter(Users.tg_id != None).with_entities(Users.tg_id)
        session.close()

        return result

    @staticmethod
    def select_ptw_list_by_user_tg_id(user_tg_id):
        session = br.get_session()
        result = session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id).\
            filter(Users.tg_id == user_tg_id, ListStatus.status == 6, ListStatus.airing != 3).\
            with_entities(ListStatus.title, ListStatus.mal_aid)
        session.close()

        return result

    @staticmethod
    def select_ptw_lists_by_usernames(nick_list):
        session = br.get_session()
        result = session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id). \
            filter(Users.mal_nick.in_(nick_list)).filter(ListStatus.status == 6, ListStatus.airing != 3). \
            with_entities(ListStatus.title, ListStatus.mal_aid, Users.mal_nick, ListStatus.show_type)
        session.close()

        return result

    @staticmethod
    def select_registered_user_nicks():
        session = br.get_session()
        result = session.query(Users).filter(Users.mal_nick != None).with_entities(Users.mal_nick)
        session.close()

        return result

    @staticmethod
    def select_watched_titles_in_score_interval(score_low, score_high, ignored_users):
        session = br.get_session()
        result = session.query(ListStatus).join(Users, ListStatus.user_id == Users.mal_uid).\
            filter(ListStatus.status == 2).\
            filter(ListStatus.score >= score_low).filter(ListStatus.score <= score_high).\
            filter(Users.mal_uid.notin_(ignored_users)).\
            with_entities(ListStatus.title, ListStatus.mal_aid, Users.mal_nick, ListStatus.show_type).\
            distinct()
        session.close()

        return result

    @staticmethod
    def select_watched_list_by_user_tg_id(user_tg_id):
        session = br.get_session()
        result = session.query(ListStatus).join(Users, ListStatus.user_id == Users.mal_uid).\
            filter(Users.tg_id == user_tg_id).filter(ListStatus.status != 6).\
            with_entities(ListStatus.mal_aid)
        session.close()

        return result

    @staticmethod
    def select_quotes_by_keyword(keyword):
        session = br.get_session()
        result = session.query(Quotes).filter(Quotes.keyword == keyword).\
            with_entities(Quotes.content, Quotes.markdown)
        session.close()

        return result

    @staticmethod
    def select_quotes_like_keyword(keyword):
        session = br.get_session()
        result = session.query(Quotes).filter(Quotes.keyword.like(f'%{keyword}%')).\
            with_entities(Quotes.keyword)
        session.close()

        return result

    @staticmethod
    def select_all_quote_keywords():
        session = br.get_session()
        result = session.query(Quotes).order_by(Quotes.id).\
            with_entities(Quotes.keyword)
        session.close()

        return result

    @staticmethod
    def select_quote_author_by_keyword(keyword):
        session = br.get_session()
        result = session.query(Quotes).filter(Quotes.keyword == keyword).\
            with_entities(Quotes.keyword, Quotes.author_id)
        session.close()

        return result

    @staticmethod
    def select_titles_tracked_by_bot():
        session = br.get_session()
        result = session.query(UsersXTracked).join(Users, UsersXTracked.user_id == Users.id).\
            with_entities(UsersXTracked.mal_aid.label('mal_aid'), Users.tg_nick.label('tg_nick'))
        session.close()

        return result

    @staticmethod
    def select_titles_tracked_in_lists():
        session = br.get_session()
        result = session.query(ListStatus).join(Users, ListStatus.user_id == Users.mal_uid).\
            filter(ListStatus.status == 1, ListStatus.airing == 1).\
            with_entities(ListStatus.mal_aid.label('mal_aid'), Users.tg_nick.label('tg_nick'))
        session.close()

        return result

    def select_all_tracked_titles(self):
        list_union = self.select_titles_tracked_by_bot().union(self.select_titles_tracked_in_lists()).subquery()
        session = br.get_session()
        result = session.query(list_union).\
            join(Anime, Anime.mal_aid == list_union.c.mal_aid).\
            filter(Anime.status == 'Currently Airing').\
            group_by(Anime.mal_aid).\
            order_by(desc(func.count(list_union.c.mal_aid))).\
            with_entities(Anime.title, list_union.c.mal_aid, func.count(list_union.c.mal_aid))
        session.close()

        return result

    @staticmethod
    def select_ongoing_ids():
        session = br.get_session()
        result = session.query(Ongoings).with_entities(Ongoings.mal_aid)
        session.close()

        return result

    @staticmethod
    def select_fresh_movie_ids():
        session = br.get_session()
        result = session.query(Anime).\
            filter(Anime.show_type == 'Movie',
                   Anime.started_at >= datetime.now() - timedelta(days=720)).\
            with_entities(Anime.mal_aid)
        session.close()

        return result

    # @staticmethod
    # def select_registered_tg_users_count(self):
    #     return self.select_user_tg_ids().count()
            # session.query(Users).with_entities(func.count(Users.tg_id))

    @staticmethod
    def select_users_with_ongoing_titles_in_list():
        session = br.get_session()
        result = session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id)\
            .filter(ListStatus.status == 1, ListStatus.airing == 1)\
            .filter(ListStatus.show_type.in_(TYPE_LIST))\
            .with_entities(Users.mal_nick).distinct()
        session.close()

        return result

    @staticmethod
    def select_users_with_any_titles_in_list():
        session = br.get_session()
        result = session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id)\
            .with_entities(Users.mal_nick, Users.tg_nick).distinct()
        session.close()

        return result

    @staticmethod
    def select_all_recognized_titles_stats():
        session = br.get_session()
        result = session.query(Ongoings).join(Anime, Anime.mal_aid == Ongoings.mal_aid)\
            .filter(or_(Ongoings.last_ep < Anime.eps, Anime.eps == None))\
            .order_by(Anime.title)\
            .with_entities(Anime.title, Ongoings.last_ep, Ongoings.last_release, Ongoings.mal_aid).distinct()
        session.close()

        return result

    @staticmethod
    def select_locked_out_ongoings():
        threshold = datetime.now() - timedelta(hours=24)
        session = br.get_session()
        result = session.query(Ongoings).join(Anime, Anime.mal_aid == Ongoings.mal_aid).\
            filter(Ongoings.last_release >= threshold, Ongoings.last_ep > 1).\
            with_entities(Anime.title, Ongoings.last_ep, Ongoings.last_release, Ongoings.mal_aid)
        session.close()

        return result

    @staticmethod
    def select_future_anime():
        session = br.get_session()
        result = session.query(Anime).\
            join(t_anime_x_producers, t_anime_x_producers.c.mal_aid == Anime.mal_aid).\
            join(Producers, Producers.mal_pid == t_anime_x_producers.c.mal_pid).\
            filter(or_(Anime.started_at == None, Anime.started_at > datetime.now())).\
            order_by(Anime.started_at).\
            with_entities(Anime.mal_aid, Anime.title, Anime.show_type, Anime.started_at, Producers.name)
        session.close()

        return result

    def select_future_anime_by_producer(self, producer_name):
        session = br.get_session()
        result = self.select_future_anime().filter(Producers.name.like(f'%{producer_name}%'))
        session.close()

        return result

    def select_future_anime_by_title(self, anime_title):
        session = br.get_session()
        result = self.select_future_anime().filter(Anime.title.like(f'%{anime_title}%'))
        session.close()

        return result

    @staticmethod
    def select_user_list_address_by_tg_id(tg_id):
        session = br.get_session()
        result = session.query(Users).\
            filter(Users.tg_id == tg_id).\
            with_entities(Users.mal_nick, Users.service)
        session.close()

        return result

    @staticmethod
    def select_anime_seen_by_title(title):
        session = br.get_session()
        result = session.query(ListStatus).\
            filter(ListStatus.title.like(f'%{title}%')).\
            with_entities(ListStatus.title, ListStatus.mal_aid).\
            distinct()
        session.close()

        return result

    @staticmethod
    def select_user_info_for_seen_title(mal_aid):
        session = br.get_session()
        result = session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id).\
            filter(ListStatus.mal_aid == mal_aid).\
            order_by(desc(ListStatus.score)).\
            with_entities(Users.tg_nick, ListStatus.score, ListStatus.status, ListStatus.watched)
        session.close()

        return result

    @staticmethod
    def select_user_id_by_tg_id(tg_id):
        session = br.get_session()
        result = session.query(Users).\
            filter(Users.tg_id == tg_id).\
            with_entities(Users.id)
        session.close()

        return result

    @staticmethod
    def select_tracked_titles_by_user_tg_id(tg_id):
        session = br.get_session()
        result = session.query(UsersXTracked).\
            join(Anime, UsersXTracked.mal_aid == Anime.mal_aid).\
            join(Users, Users.id == UsersXTracked.user_id).\
            filter(Users.tg_id == tg_id).\
            with_entities(UsersXTracked.mal_aid, Anime.title, UsersXTracked.a_group)
        session.close()

        return result

    @staticmethod
    def select_anime_to_track_from_ongoings_by_title(title):
        session = br.get_session()
        result = session.query(Ongoings).join(Anime, Anime.mal_aid == Ongoings.mal_aid).\
            filter(Anime.title.like(f'%{title}%')).\
            filter(Anime.show_type.in_(TYPE_LIST)).\
            with_entities(Ongoings.mal_aid, Anime.title)
        session.close()

        return result

    @staticmethod
    def select_anime_tracked_by_user_id_and_anime_id(user_id, mal_aid):
        session = br.get_session()
        result = session.query(UsersXTracked).\
            filter(UsersXTracked.user_id == user_id).\
            filter(UsersXTracked.mal_aid == mal_aid).\
            with_entities(UsersXTracked.mal_aid)
        session.close()

        return result

    @staticmethod
    def select_anime_tracked_by_user_id_and_title(user_id, title):
        session = br.get_session()
        result = session.query(UsersXTracked).join(Anime, Anime.mal_aid == UsersXTracked.mal_aid).\
            filter(Anime.title.like(f'%{title}%')).\
            filter(Anime.show_type.in_(TYPE_LIST)).\
            filter(UsersXTracked.user_id == user_id).\
            with_entities(UsersXTracked.mal_aid, Anime.title)
        session.close()

        return result

    @staticmethod
    def select_gif_tags_by_media_id(file_id):
        session = br.get_session()
        result = session.query(GifTags).\
            filter(GifTags.media_id == file_id).\
            with_entities(GifTags.media_id, GifTags.tag)
        session.close()

        return result

    @staticmethod
    def select_user_data_by_nick(nick):
        session = br.get_session()
        result = session.query(Users).filter(Users.tg_nick == nick)
        session.close()

        return result

    def select_gifs_by_tags(self):
        pass

    @staticmethod
    def select_last_episodes(tg_id):
        session = br.get_session()
        result = session.query(v_last_episodes).filter(v_last_episodes.c.tg_id == tg_id)
        session.close()

        return result

    @staticmethod
    def select_anime_info_by_exact_synonym(query):
        # mal_info = self.ani_db.select('distinct axs.mal_aid, a.title, a.status, a.show_type, a.eps, a.popularity',
        #                               'anime_x_synonyms axs join anime a on a.mal_aid = axs.mal_aid',
        #                               'axs.synonym = %s and a.popularity is not NULL', [query])
        session = br.get_session()
        mal_info = session.query(AnimeXSynonyms).join(Anime, Anime.mal_aid == AnimeXSynonyms.mal_aid).\
            filter(AnimeXSynonyms.synonym == query, Anime.popularity != None).\
            with_entities(AnimeXSynonyms.mal_aid, Anime.title, Anime.show_type, Anime.eps, Anime.popularity).\
            distinct().all()
        session.close()

        return mal_info

    @staticmethod
    def select_anime_info_by_synonym_part(query):
        # mal_info = self.ani_db.select('distinct axs.mal_aid, a.title, a.status, a.show_type, a.eps, a.popularity',
        #                               'anime_x_synonyms axs join anime a on a.mal_aid = axs.mal_aid',
        #                               'axs.synonym like %s and a.popularity is not NULL', [f'%{query}%'])
        session = br.get_session()
        mal_info = session.query(AnimeXSynonyms).join(Anime, Anime.mal_aid == AnimeXSynonyms.mal_aid).\
            filter(AnimeXSynonyms.synonym.like(f'%{query}%'), Anime.popularity != None).\
            with_entities(AnimeXSynonyms.mal_aid, Anime.title, Anime.show_type, Anime.eps, Anime.popularity).\
            distinct().all()
        session.close()

        return mal_info

    @staticmethod
    # todo tbh this requires a specific instrument like elastic
    def select_anime_info_by_split_words(query):
        q_string = '%' + '%'.join(re.sub(r'\W+', ' ', query).split(' ')) + '%'
        # mal_info = self.ani_db.select('distinct axs.mal_aid, a.title, a.status, a.show_type, a.eps, a.popularity',
        #                               'anime_x_synonyms axs join anime a on a.mal_aid = axs.mal_aid',
        #                               'axs.synonym rlike %s and a.popularity is not NULL',
        #                               [r_string])
        session = br.get_session()
        mal_info = session.query(AnimeXSynonyms).join(Anime, Anime.mal_aid == AnimeXSynonyms.mal_aid).\
            filter(AnimeXSynonyms.synonym.like(q_string), Anime.popularity != None).\
            with_entities(AnimeXSynonyms.mal_aid, Anime.title, Anime.show_type, Anime.eps, Anime.popularity).\
            distinct().all()
        session.close()

        return mal_info

    @staticmethod
    def select_relations_data():
        session = br.get_session()
        result = session.query(Anime) \
            .with_entities(Anime.mal_aid, Anime.related, Anime.title, )
        session.close()

        return result

    # handler_modules SELECT methods end
    # list_parser SELECT methods

    @staticmethod
    def select_service_users_ids(service_name):
        session = br.get_session()
        result = session.query(Users).\
            filter(Users.service == service_name).\
            with_entities(Users.mal_nick, Users.mal_uid)
        session.close()

        return result

    @staticmethod
    def select_user_is_in_list_status(service_user_id):
        session = br.get_session()
        result = session.query(ListStatus).\
            filter(ListStatus.user_id == service_user_id).\
            with_entities(ListStatus.user_id)
        session.close()

        return result

    @staticmethod
    def select_genres():
        session = br.get_session()
        result = session.query(Genres.mal_gid)
        session.close()

        return result

    @staticmethod
    def select_licensors():
        session = br.get_session()
        result = session.query(Licensors.name)
        session.close()

        return result

    @staticmethod
    def select_producers():
        session = br.get_session()
        result = session.query(Producers.mal_pid)
        session.close()

        return result

    # feed_parser SELECT methods

    @staticmethod
    def select_feed_entry_by_title_and_date(a_title, a_date):
        session = br.get_session()
        result = session.query(AniFeeds).filter(AniFeeds.title == a_title, AniFeeds.date == a_date)
        session.close()

        return result

    @staticmethod
    def select_last_feed_entry():
        session = br.get_session()
        result = session.query(AniFeeds).\
            order_by(desc(AniFeeds.date)).\
            limit(1).\
            with_entities(AniFeeds.date, AniFeeds.title)
        session.close()

        return result

    @staticmethod
    def select_unchecked_feed_entries():
        session = br.get_session()
        result = session.query(AniFeeds).filter(AniFeeds.checked == 0).order_by(AniFeeds.date)
        session.close()

        return result

    @staticmethod
    def select_ongoing_anime_id_by_synonym(synonym):
        session = br.get_session()
        result = session.query(AnimeXSynonyms).join(Anime).\
            filter(AnimeXSynonyms.synonym == synonym, Anime.status != 'Finished Airing').\
            with_entities(AnimeXSynonyms.mal_aid)
        session.close()

        return result

    @staticmethod
    def select_mal_anime_ids_by_title_part(title):
        session = br.get_session()
        result = session.query(Ongoings).join(Anime).\
            filter(
                Anime.show_type.in_(TYPE_LIST),
                Anime.status != 'Finished Airing',
                Anime.started_at < datetime.now() + timedelta(hours=24),
            ).\
            filter(Anime.title.like(f'%{title}%')).\
            with_entities(Ongoings.mal_aid).\
            distinct()
        session.close()

        return result

    @staticmethod
    def select_anime_id_is_in_database(mal_aid):
        session = br.get_session()
        result = session.query(Anime).\
            filter(Anime.mal_aid == mal_aid).\
            with_entities(Anime.mal_aid)
        session.close()

        return result

    @staticmethod
    def select_torrent_is_saved_in_database(mal_aid, group, episode, res, size):
        session = br.get_session()
        result = session.query(TorrentFiles).\
            filter(TorrentFiles.mal_aid == mal_aid, TorrentFiles.a_group == group, TorrentFiles.episode == episode,
                   TorrentFiles.res == res, TorrentFiles.file_size == size)
        session.close()

        return result

    @staticmethod
    def select_last_ongoing_ep_by_id(mal_aid):
        session = br.get_session()
        result = session.query(Ongoings).filter(Ongoings.mal_aid == mal_aid).\
            with_entities(Ongoings.last_ep)
        session.close()

        return result

    # jobs SELECT methods

    @staticmethod
    def select_today_titles():
        session = br.get_session()
        result = session.query(v_today_titles)
        session.close()

        return result

    @staticmethod
    def select_titles_pending_for_delivery():
        session = br.get_session()
        result = session.query(v_pending_delivery)
        session.close()

        return result

    @staticmethod
    def select_waifu_blocker_shows():
        session = br.get_session()
        result = session.query(Anime).filter(or_(and_(Anime.show_type == 'ONA', Anime.eps > 3), Anime.show_type == 'TV'))\
            .with_entities(Anime.mal_aid)
        session.close()

        return result

    # synonyms SELECT methods
    @staticmethod
    def select_by_synonym_id_pair(mal_aid, synonym):
        session = br.get_session()
        result = session.query(AnimeXSynonyms)\
            .filter(AnimeXSynonyms.mal_aid == mal_aid, AnimeXSynonyms.synonym == synonym)
        session.close()

        return result

    @staticmethod
    def select_existing_synonyms():
        session = br.get_session()
        result = session.query(AnimeXSynonyms)
        session.close()

        return result

    @staticmethod
    def select_all_possible_synonyms():
        session = br.get_session()
        result = session.query(Anime). \
            with_entities(Anime.mal_aid, Anime.title, Anime.title_eng, Anime.title_jap, Anime.title_synonyms)
        session.close()

        return result

    # handler_modules INSERT methods
    @staticmethod
    def insert_new_tracked_title(user_id, mal_aid, last_ep, a_group):
        new_tracked = UsersXTracked(user_id=user_id, mal_aid=mal_aid, last_ep=last_ep, a_group=a_group)
        session = br.get_session()
        session.add(new_tracked)
        session.commit()
        session.close()

    def upsert_anime_entry(self, a_entry):
        local_entry = self.select_anime_by_id(a_entry.mal_id).first()
        session = br.get_session()
        if not local_entry:
            local_entry = Anime(mal_aid=a_entry.mal_id, title=a_entry.title, title_eng=a_entry.title_english,
                                title_jap=a_entry.title_japanese, synopsis=a_entry.synopsis, show_type=a_entry.type,
                                started_at=a_entry.aired['from'][:10] if a_entry.aired['from'] else None,
                                ended_at=a_entry.aired['to'][:10] if a_entry.aired['to'] else None,
                                eps=a_entry.episodes, img_url=a_entry.image_url, score=a_entry.score,
                                status=a_entry.status, background=a_entry.background, broadcast=a_entry.broadcast,
                                duration=a_entry.duration, favorites=a_entry.favorites, members=a_entry.members,
                                popularity=a_entry.popularity, premiered=a_entry.premiered, rank=a_entry.rank,
                                rating=a_entry.rating, scored_by=a_entry.scored_by, source=a_entry.source,
                                trailer_url=a_entry.trailer_url, ending_themes=a_entry.ending_themes,
                                related=a_entry.related, opening_themes=a_entry.opening_themes,
                                title_synonyms=a_entry.title_synonyms, )
            session.add(local_entry)
        else:
            local_entry.title = a_entry.title
            local_entry.title_eng = a_entry.title_english
            local_entry.title_jap = a_entry.title_japanese
            local_entry.synopsis = a_entry.synopsis
            local_entry.show_type = a_entry.type
            local_entry.started_at = a_entry.aired['from'][:10] if a_entry.aired['from'] else None
            local_entry.ended_at = a_entry.aired['to'][:10] if a_entry.aired['to'] else None
            local_entry.eps = a_entry.episodes
            local_entry.img_url = a_entry.image_url
            local_entry.score = a_entry.score
            local_entry.status = a_entry.status
            local_entry.background = a_entry.background
            local_entry.broadcast = a_entry.broadcast
            local_entry.duration = a_entry.duration
            local_entry.favorites = a_entry.favorites
            local_entry.members = a_entry.members
            local_entry.popularity = a_entry.popularity
            local_entry.premiered = a_entry.premiered
            local_entry.rank = a_entry.rank
            local_entry.rating = a_entry.rating
            local_entry.scored_by = a_entry.scored_by
            local_entry.source = a_entry.source
            local_entry.trailer_url = a_entry.trailer_url
            local_entry.ending_themes = a_entry.ending_themes
            local_entry.related = a_entry.related
            local_entry.opening_themes = a_entry.opening_themes
            local_entry.title_synonyms = a_entry.title_synonyms
        session.commit()
        session.close()

    @staticmethod
    def insert_tags_into_gif_tags(values):
        session = br.get_session()
        for entry in values:
            new_tag = GifTags(media_id=entry[0], tag=entry[1])
            session.add(new_tag)
        session.commit()
        session.close()

    @staticmethod
    def insert_new_user(tg_nick, tg_id):
        session = br.get_session()
        new_user = Users(tg_nick=tg_nick, tg_id=tg_id)
        session.add(new_user)
        session.commit()
        session.close()

    # from former db_wrapper
    @staticmethod
    def insert_new_quote(keyword, content, markdown, author_id):
        session = br.get_session()
        new_quote = Quotes(keyword=keyword, content=content, markdown=markdown, author_id=author_id)
        session.add(new_quote)
        session.commit()
        session.close()

    @staticmethod
    def insert_new_genres(genre_list):
        session = br.get_session()
        for genre in genre_list:
            new_genre = Genres(mal_gid=genre['mal_id'], name=genre['name'])
            session.add(new_genre)
        session.commit()
        session.close()

    @staticmethod
    def insert_new_producers(producer_list):
        session = br.get_session()
        for producer in producer_list:
            new_producer = Producers(mal_pid=producer['mal_id'], name=producer['name'])
            session.add(new_producer)
        session.commit()
        session.close()

    @staticmethod
    def insert_new_licensors(licensor_list):
        session = br.get_session()
        for licensor in licensor_list:
            new_licensor = Licensors(name=licensor)
            session.add(new_licensor)
        session.commit()
        session.close()

    @staticmethod
    def insert_new_axg(anime):
        session = br.get_session()
        anime_ = session.query(Anime).filter(Anime.mal_aid == anime['mal_id']).first()
        new_axg = [genre for genre in anime['genres'] if genre['mal_id'] not in anime_.genres]
        for genre in new_axg:
            genre_ = session.query(Genres).filter(Genres.mal_gid == genre['mal_id']).first()
            anime_.genres.append(genre_)
        session.commit()
        session.close()

    @staticmethod
    def insert_new_axp(anime):
        session = br.get_session()
        anime_ = session.query(Anime).filter(Anime.mal_aid == anime['mal_id']).first()
        new_axp = [producer for producer in anime['producers'] if producer['mal_id'] not in anime_.producers]
        for producer in new_axp:
            producer_ = session.query(Producers).filter(Producers.mal_pid == producer['mal_id']).first()
            anime_.producers.append(producer_)
        session.commit()
        session.close()

    @staticmethod
    def insert_new_axl(anime):
        session = br.get_session()
        anime_ = session.query(Anime).filter(Anime.mal_aid == anime['mal_id']).first()
        new_axl = [licensor for licensor in anime['licensors'] if licensor not in anime_.licensors]
        for licensor in new_axl:
            licensor_ = session.query(Licensors).filter(Licensors.name == licensor).first()
            anime_.licensors.append(licensor_)
        session.commit()
        session.close()

    @staticmethod
    def insert_new_animelist(mal_uid, anime_list):
        session = br.get_session()
        for anime in anime_list:
            list_entry = ListStatus(user_id=mal_uid, mal_aid=anime['mal_id'], title=anime['title'],
                                    show_type=anime['type'], status=anime['watching_status'],
                                    watched=anime['watched_episodes'], eps=anime['total_episodes'],
                                    score=anime['score'], airing=anime['airing_status'])
            session.add(list_entry)
        session.commit()
        session.close()

    # feed_parser INSERT methods
    @staticmethod
    def insert_new_feed_entry(a_title, a_date, a_link, a_description):
        feed_entry = AniFeeds(title=a_title, date=a_date, link=a_link, description=a_description)
        session = br.get_session()
        session.add(feed_entry)
        session.commit()
        session.close()

    @staticmethod
    def insert_new_torrent_file(mal_aid, group, episode, filename, res, size):
        torrent_file = TorrentFiles(mal_aid=mal_aid, a_group=group, episode=episode, torrent=filename, res=res,
                                        file_size=size)
        session = br.get_session()
        session.add(torrent_file)
        session.commit()
        session.close()

    # synonyms INSERT methods
    @staticmethod
    def insert_new_synonym(mal_aid, synonym):
        new_synonym = AnimeXSynonyms(mal_aid=mal_aid, synonym=synonym)
        session = br.get_session()
        try:
            session.add(new_synonym)
            session.commit()
        except Exception:
            print('INTEGRITY FAILURE')
            session.rollback()
        session.close()

    # INSERT methods end
    # handler_modules DELETE methods
    @staticmethod
    def delete_tracked_anime(user_id, mal_aid):
        session = br.get_session()
        session.query(UsersXTracked).\
            filter(UsersXTracked.user_id == user_id, UsersXTracked.mal_aid == mal_aid).\
            delete()
        session.commit()
        session.close()

    @staticmethod
    def delete_quotes_by_keyword(keyword):
        session = br.get_session()
        session.query(Quotes).\
            filter(Quotes.keyword == keyword).\
            delete()
        session.close()

    # ListStatus DELETE handler_modules
    @staticmethod
    def delete_list_by_user_id(user_id):
        session = br.get_session()
        session.query(ListStatus).\
            filter(ListStatus.user_id == user_id).\
            delete()
        session.commit()
        session.close()

    # handler_modules UPDATE methods
    @staticmethod
    def update_quote_by_keyword(keyword, content):
        session = br.get_session()
        quote = session.query(Quotes).filter(Quotes.keyword == keyword).first()
        quote.content = content
        session.commit()
        session.close()

    @staticmethod
    def update_users_id_for_manually_added_lists(user_id, user_name):
        session = br.get_session()
        user = session.query(Users).filter(Users.tg_nick == user_name).first()
        user.tg_id = user_id
        session.commit()
        session.close()

    @staticmethod
    def update_group_for_users_release_tracking(a_group, user_id, mal_aid):
        session = br.get_session()
        release = session.query(UsersXTracked).filter(UsersXTracked.user_id == user_id,
                                                      UsersXTracked.mal_aid == mal_aid).first()
        release.a_group = a_group
        release.last_ep = 0
        session.commit()
        session.close()

    @staticmethod
    def update_users_preferred_resolution(res, tg_id):
        session = br.get_session()
        user = session.query(Users).filter(Users.tg_id == tg_id).first()
        user.preferred_res = res
        session.commit()
        session.close()

    # todo think about additional checking for correct episode numbers
    @staticmethod
    def update_release_status_for_user_after_delivery(episode, user_id, mal_aid, a_group):
        session = br.get_session()
        status = session.query(UsersXTracked).\
            filter(UsersXTracked.user_id == user_id, UsersXTracked.mal_aid == mal_aid,
                  UsersXTracked.a_group == a_group, UsersXTracked.last_ep < episode).first()
        if status:
            status.last_ep = episode
            session.commit()
        session.close()

    # Feed parser update methods
    # todo not sure it's actually needed
    @staticmethod
    def update_anifeeds_entry(a_link, a_description, a_title, a_date):
        session = br.get_session()
        feed_entry = session.query(AniFeeds).filter(AniFeeds.title == a_title,
                                                    AniFeeds.date == a_date).first()
        feed_entry.link = a_link
        feed_entry.description = a_description
        session.commit()
        session.close()

    @staticmethod
    def update_anifeeds_with_parsed_information(mal_aid, a_group, resolution, episode, size, title, date):
        session = br.get_session()
        feed_entry = session.query(AniFeeds).filter(AniFeeds.title == title, AniFeeds.date == date).first()
        feed_entry.mal_aid = mal_aid
        feed_entry.a_group = a_group
        feed_entry.resolution = resolution
        feed_entry.ep = episode
        feed_entry.size = size
        feed_entry.checked = 1
        session.commit()
        session.close()

    @staticmethod
    def update_anifeeds_unrecognized_entry(size, title, date):
        session = br.get_session()
        feed_entry = session.query(AniFeeds).filter(AniFeeds.title == title, AniFeeds.date == date).first()
        feed_entry.size = size
        feed_entry.checked = 1
        session.commit()
        session.close()

    # List parser update methods
    @staticmethod
    def update_users_service_id_for_service_nick(service_uid, service_nick):
        session = br.get_session()
        user = session.query(Users).filter(Users.mal_nick == service_nick).first()
        user.mal_uid = service_uid
        session.commit()
        session.close()


if __name__ == '__main__':
    di = DataInterface()
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
