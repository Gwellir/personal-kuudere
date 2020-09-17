import re

from ORMWrapper import *
from pprint import pprint
from sqlalchemy import func, desc, or_, and_, insert, update
from sqlalchemy.orm import aliased
from datetime import datetime, timedelta


TYPE_LIST = ['TV', 'ONA']

br = BaseRelations()
session = br.session


class DataInterface:
    @staticmethod
    def select_group_list_for_user(mal_aid, user_id):
        return session.query(AniFeeds).\
                 join(Users, AniFeeds.resolution == Users.preferred_res).\
                 filter(AniFeeds.mal_aid == mal_aid, Users.id == user_id).\
                 with_entities(AniFeeds.a_group, Users.preferred_res).distinct()
        
    @staticmethod
    def select_anime_by_id(mal_aid):
        return session.query(Anime).filter(Anime.mal_aid == mal_aid)

    @staticmethod
    def select_info_post_from_quotes():
        return session.query(Quotes).filter(Quotes.keyword == 'info').order_by(Quotes.id).\
            with_entities(Quotes.content, Quotes.markdown)

    @staticmethod
    def select_user_tg_ids():
        return session.query(Users).filter(Users.tg_id != None).with_entities(Users.tg_id)
        
    @staticmethod
    def select_ptw_list_by_user_tg_id(user_tg_id):
        return session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id).\
            filter(Users.tg_id == user_tg_id, ListStatus.status == 6, ListStatus.airing != 3).\
            with_entities(ListStatus.title, ListStatus.mal_aid)
        
    @staticmethod
    def select_ptw_lists_by_usernames(nick_list):
        return session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id). \
            filter(Users.mal_nick.in_(nick_list)).filter(ListStatus.status == 6, ListStatus.airing != 3). \
            with_entities(ListStatus.title, ListStatus.mal_aid)
        
    @staticmethod
    def select_registered_user_nicks():
        return session.query(Users).filter(Users.mal_nick != None).with_entities(Users.mal_nick)
        
    @staticmethod
    def select_watched_titles_in_score_interval(score_low, score_high, ignored_users):
        return session.query(ListStatus).join(Users, ListStatus.user_id == Users.mal_uid).\
            filter(ListStatus.status == 2).\
            filter(ListStatus.score >= score_low).filter(ListStatus.score <= score_high).\
            filter(Users.mal_uid.notin_(ignored_users)).\
            with_entities(ListStatus.title, ListStatus.mal_aid, Users.mal_nick, ListStatus.show_type).\
            distinct()
        
    @staticmethod
    def select_watched_list_by_user_tg_id(user_tg_id):
        return session.query(ListStatus).join(Users, ListStatus.user_id == Users.mal_uid).\
            filter(Users.tg_id == user_tg_id).filter(ListStatus.status != 6).\
            with_entities(ListStatus.mal_aid)
        
    @staticmethod
    def select_quotes_by_keyword(keyword):
        return session.query(Quotes).filter(Quotes.keyword == keyword).\
            with_entities(Quotes.content, Quotes.markdown)
        
    @staticmethod
    def select_quotes_like_keyword(keyword):
        return session.query(Quotes).filter(Quotes.keyword.like(keyword)).\
            with_entities(Quotes.keyword)
        
    @staticmethod
    def select_all_quote_keywords():
        return session.query(Quotes).order_by(Quotes.id).\
            with_entities(Quotes.keyword)
        
    @staticmethod
    def select_quote_author_by_keyword(keyword):
        return session.query(Quotes).filter(Quotes.keyword == keyword).\
            with_entities(Quotes.keyword, Quotes.author_id)
        
    @staticmethod
    def select_titles_tracked_by_bot():
        return session.query(UsersXTracked).join(Users, UsersXTracked.user_id == Users.id).\
            with_entities(UsersXTracked.mal_aid.label('mal_aid'), Users.tg_nick.label('tg_nick'))
        
    @staticmethod
    def select_titles_tracked_in_lists():
        return session.query(ListStatus).join(Users, ListStatus.user_id == Users.mal_uid).\
            filter(ListStatus.status == 1, ListStatus.airing == 1).\
            with_entities(ListStatus.mal_aid.label('mal_aid'), Users.tg_nick.label('tg_nick'))
        
    def select_all_tracked_titles(self):
        list_union = self.select_titles_tracked_by_bot().union(self.select_titles_tracked_in_lists()).subquery()
        return session.query(list_union).\
            join(Anime, Anime.mal_aid == list_union.c.mal_aid).\
            group_by(Anime.mal_aid).\
            order_by(desc(func.count(list_union.c.mal_aid))).\
            with_entities(Anime.title, list_union.c.mal_aid, func.count(list_union.c.mal_aid))
        
    @staticmethod
    def select_ongoing_ids():
        return session.query(Ongoings).with_entities(Ongoings.mal_aid)
        
    # @staticmethod
    # def select_registered_tg_users_count(self):
    #     return self.select_user_tg_ids().count()
            # session.query(Users).with_entities(func.count(Users.tg_id))
        
    @staticmethod
    def select_users_with_ongoing_titles_in_list():
        return session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id)\
            .filter(ListStatus.status == 1, ListStatus.airing == 1)\
            .filter(ListStatus.show_type.in_(TYPE_LIST))\
            .with_entities(Users.mal_nick).distinct()
        
    @staticmethod
    def select_users_with_any_titles_in_list():
        return session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id)\
            .with_entities(Users.mal_nick, Users.tg_nick).distinct()
        
    @staticmethod
    def select_all_recognized_titles_stats():
        return session.query(Ongoings).join(Anime, Anime.mal_aid == Ongoings.mal_aid)\
            .filter(or_(Ongoings.last_ep < Anime.eps, Anime.eps == None))\
            .order_by(Anime.title)\
            .with_entities(Anime.title, Ongoings.last_ep, Ongoings.last_release, Ongoings.mal_aid).distinct()
        
    @staticmethod
    def select_locked_out_ongoings():
        threshold = datetime.now() - timedelta(hours=24)
        return session.query(Ongoings).join(Anime, Anime.mal_aid == Ongoings.mal_aid).\
            filter(Ongoings.last_release >= threshold, Ongoings.last_ep > 1).\
            with_entities(Anime.title, Ongoings.last_ep, Ongoings.last_release, Ongoings.mal_aid)
        
    @staticmethod
    def select_future_anime():
        return session.query(Anime).\
            join(t_anime_x_producers, t_anime_x_producers.c.mal_aid == Anime.mal_aid).\
            join(Producers, Producers.mal_pid == t_anime_x_producers.c.mal_pid).\
            filter(or_(Anime.started_at == None, Anime.started_at > datetime.now())).\
            order_by(Anime.started_at).\
            with_entities(Anime.mal_aid, Anime.title, Anime.show_type, Anime.started_at, Producers.name)
        
    def select_future_anime_by_producer(self, producer_name):
        return self.select_future_anime().filter(Producers.name.like(f'%{producer_name}%'))
        
    def select_future_anime_by_title(self, anime_title):
        return self.select_future_anime().filter(Anime.title.like(f'%{anime_title}%'))
        
    @staticmethod
    def select_user_list_address_by_tg_id(tg_id):
        return session.query(Users).\
            filter(Users.tg_id == tg_id).\
            with_entities(Users.mal_nick, Users.service)
        
    @staticmethod
    def select_anime_seen_by_title(title):
        return session.query(ListStatus).\
            filter(ListStatus.title.like(f'%{title}%')).\
            with_entities(ListStatus.title, ListStatus.mal_aid).\
            distinct()
        
    @staticmethod
    def select_user_info_for_seen_title(mal_aid):
        return session.query(ListStatus).join(Users, Users.mal_uid == ListStatus.user_id).\
            filter(ListStatus.mal_aid == mal_aid).\
            order_by(desc(ListStatus.score)).\
            with_entities(Users.mal_nick, ListStatus.score, ListStatus.status, ListStatus.watched)
        
    @staticmethod
    def select_user_id_by_tg_id(tg_id):
        return session.query(Users).\
            filter(Users.tg_id == tg_id).\
            with_entities(Users.id)
        
    @staticmethod
    def select_tracked_titles_by_user_tg_id(tg_id):
        return session.query(UsersXTracked).\
            join(Anime, UsersXTracked.mal_aid == Anime.mal_aid).\
            join(Users, Users.id == UsersXTracked.user_id).\
            filter(Users.tg_id == tg_id).\
            with_entities(UsersXTracked.mal_aid, Anime.title, UsersXTracked.a_group)
        
    @staticmethod
    def select_anime_to_track_from_ongoings_by_title(title):
        return session.query(Ongoings).join(Anime, Anime.mal_aid == Ongoings.mal_aid).\
            filter(Anime.title.like(f'%{title}%')).\
            filter(Anime.show_type.in_(TYPE_LIST)).\
            with_entities(Ongoings.mal_aid, Anime.title)
        
    @staticmethod
    def select_anime_tracked_by_user_id_and_anime_id(user_id, mal_aid):
        return session.query(UsersXTracked).\
            filter(UsersXTracked.user_id == user_id).\
            filter(UsersXTracked.mal_aid == mal_aid).\
            with_entities(UsersXTracked.mal_aid)
        
    @staticmethod
    def select_anime_tracked_by_user_id_and_title(user_id, title):
        return session.query(UsersXTracked).join(Anime, Anime.mal_aid == UsersXTracked.mal_aid).\
            filter(Anime.title.like(f'%{title}%')).\
            filter(Anime.show_type.in_(TYPE_LIST)).\
            filter(UsersXTracked.user_id == user_id).\
            with_entities(UsersXTracked.mal_aid, Anime.title)

    @staticmethod
    def select_gif_tags_by_media_id(file_id):
        return session.query(GifTags).\
            filter(GifTags.media_id == file_id).\
            with_entities(GifTags.media_id, GifTags.tag)

    @staticmethod
    def select_user_data_by_nick(nick):
        return session.query(Users).filter(Users.tg_nick == nick)

    def select_gifs_by_tags(self):
        pass

    @staticmethod
    def select_last_episodes(tg_id):
        return session.query(v_last_episodes).filter(v_last_episodes.c.tg_id == tg_id)

    @staticmethod
    def select_anime_info_by_exact_synonym(query):
        # mal_info = self.ani_db.select('distinct axs.mal_aid, a.title, a.status, a.show_type, a.eps, a.popularity',
        #                               'anime_x_synonyms axs join anime a on a.mal_aid = axs.mal_aid',
        #                               'axs.synonym = %s and a.popularity is not NULL', [query])
        mal_info = session.query(AnimeXSynonyms).join(Anime, Anime.mal_aid == AnimeXSynonyms.mal_aid).\
            filter(AnimeXSynonyms.synonym == query, Anime.popularity != None).\
            with_entities(AnimeXSynonyms.mal_aid, Anime.title, Anime.show_type, Anime.eps, Anime.popularity).\
            distinct().all()
        return mal_info

    @staticmethod
    def select_anime_info_by_synonym_part(query):
        # mal_info = self.ani_db.select('distinct axs.mal_aid, a.title, a.status, a.show_type, a.eps, a.popularity',
        #                               'anime_x_synonyms axs join anime a on a.mal_aid = axs.mal_aid',
        #                               'axs.synonym like %s and a.popularity is not NULL', [f'%{query}%'])
        mal_info = session.query(AnimeXSynonyms).join(Anime, Anime.mal_aid == AnimeXSynonyms.mal_aid).\
            filter(AnimeXSynonyms.synonym.like(f'%{query}%'), Anime.popularity != None).\
            with_entities(AnimeXSynonyms.mal_aid, Anime.title, Anime.show_type, Anime.eps, Anime.popularity).\
            distinct().all()

        return mal_info

    @staticmethod
    # todo tbh this requires a specific instrument like elastic
    def select_anime_info_by_ordered_token_regex(query):
        r_string = '.*' + '.*'.join(re.sub(r'\W+', ' ', query).split(' ')) + '.*'
        # mal_info = self.ani_db.select('distinct axs.mal_aid, a.title, a.status, a.show_type, a.eps, a.popularity',
        #                               'anime_x_synonyms axs join anime a on a.mal_aid = axs.mal_aid',
        #                               'axs.synonym rlike %s and a.popularity is not NULL',
        #                               [r_string])
        mal_info = session.query(AnimeXSynonyms).join(Anime, Anime.mal_aid == AnimeXSynonyms.mal_aid).\
            filter(AnimeXSynonyms.synonym.op('regexp')(r_string), Anime.popularity != None).\
            with_entities(AnimeXSynonyms.mal_aid, Anime.title, Anime.show_type, Anime.eps, Anime.popularity).\
            distinct().all()

        return mal_info

    # handlers SELECT methods end
    # list_parser SELECT methods

    @staticmethod
    def select_service_users_ids(service_name):
        return session.query(Users).\
            filter(Users.service == service_name).\
            with_entities(Users.mal_nick, Users.mal_uid)

    @staticmethod
    def select_user_is_in_list_status(service_user_id):
        return session.query(ListStatus).\
            filter(ListStatus.user_id == service_user_id).\
            with_entities(ListStatus.user_id)

    @staticmethod
    def select_genres():
        return session.query(Genres.mal_gid)

    @staticmethod
    def select_licensors():
        return session.query(Licensors.name)

    @staticmethod
    def select_producers():
        return session.query(Producers.mal_pid)

    # feed_parser SELECT methods

    @staticmethod
    def select_feed_entry_by_title_and_date(a_title, a_date):
        return session.query(AniFeeds).filter(AniFeeds.title == a_title, AniFeeds.date == a_date)

    @staticmethod
    def select_last_feed_entry():
        return session.query(AniFeeds).\
            order_by(desc(AniFeeds.date)).\
            limit(1).\
            with_entities(AniFeeds.date, AniFeeds.title)

    @staticmethod
    def select_unchecked_feed_entries():
        return session.query(AniFeeds).filter(AniFeeds.checked == 0).order_by(AniFeeds.date)

    @staticmethod
    def select_ongoing_anime_id_by_synonym(synonym):
        return session.query(AnimeXSynonyms).join(Anime).\
            filter(AnimeXSynonyms.synonym == synonym, Anime.status != 'Finished Airing').\
            with_entities(AnimeXSynonyms.mal_aid)

    # todo fix ListStatus dependancy
    @staticmethod
    def select_mal_anime_ids_by_title_part(title):
        return session.query(Ongoings).join(Anime).\
            filter(Anime.show_type.in_(TYPE_LIST), Anime.status != 'Finished Airing').\
            filter(Anime.title.like(f'%{title}%')).\
            with_entities(Ongoings.mal_aid).\
            distinct()

    @staticmethod
    def select_anime_id_is_in_database(mal_aid):
        return session.query(Anime).\
            filter(Anime.mal_aid == mal_aid).\
            with_entities(Anime.mal_aid)

    @staticmethod
    def select_torrent_is_saved_in_database(mal_aid, group, episode, res, size):
        return session.query(TorrentFiles).\
            filter(TorrentFiles.mal_aid == mal_aid, TorrentFiles.a_group == group, TorrentFiles.episode == episode,
                   TorrentFiles.res == res, TorrentFiles.file_size == size)

    # jobs SELECT methods

    @staticmethod
    def select_today_titles():
        return session.query(v_today_titles)

    @staticmethod
    def select_titles_pending_for_delivery():
        return session.query(v_pending_delivery)

    @staticmethod
    def select_waifu_blocker_shows():
        return session.query(Anime).filter(or_(and_(Anime.show_type == 'ONA', Anime.eps > 3), Anime.show_type == 'TV'))\
            .with_entities(Anime.mal_aid)

    # synonyms SELECT methods
    @staticmethod
    def select_by_synonym_id_pair(mal_aid, synonym):
        return session.query(AnimeXSynonyms)\
            .filter(AnimeXSynonyms.mal_aid == mal_aid, AnimeXSynonyms.synonym == synonym)

    @staticmethod
    def select_all_possible_synonyms():
        return session.query(Anime). \
            with_entities(Anime.mal_aid, Anime.title, Anime.title_eng, Anime.title_jap, Anime.title_synonyms)

    # handlers INSERT methods
    @staticmethod
    def insert_new_tracked_title(user_id, mal_aid, last_ep, a_group):
        new_tracked = UsersXTracked(user_id=user_id, mal_aid=mal_aid, last_ep=last_ep, a_group=a_group)
        session.add(new_tracked)
        session.commit()
        # br.edit_data(q)

    def upsert_anime_entry(self, a_entry):
        local_entry = self.select_anime_by_id(a_entry.mal_id).first()
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

    @staticmethod
    def insert_tags_into_gif_tags(values):
        for entry in values:
            new_tag = GifTags(media_id=entry[0], tag=entry[1])
            session.add(new_tag)
        session.commit()
        # q = insert(GifTags)
        # tag_list = [{'media_id': entry[0], 'tag': entry[1]} for entry in values]
        # br.edit_data(q, tag_list)

    @staticmethod
    def insert_new_user(tg_nick, tg_id):
        new_user = Users(tg_nick=tg_nick, tg_id=tg_id)
        session.add(new_user)
        session.commit()
        # q = insert(Users).values(tg_nick=tg_nick, tg_id=tg_id)
        # br.edit_data(q)

    # from former db_wrapper
    @staticmethod
    def insert_new_quote(keyword, content, markdown, author_id):
        new_quote = Quotes(keyword=keyword, content=content, markdown=markdown, author_id=author_id)
        session.add(new_quote)
        session.commit()

    @staticmethod
    def insert_new_genres(genre_list):
        for genre in genre_list:
            new_genre = Genres(mal_gid=genre['mal_id'], name=genre['name'])
            session.add(new_genre)
        session.commit()

    @staticmethod
    def insert_new_producers(producer_list):
        for producer in producer_list:
            new_producer = Producers(mal_pid=producer['mal_id'], name=producer['name'])
            session.add(new_producer)
        session.commit()

    @staticmethod
    def insert_new_licensors(licensor_list):
        for licensor in licensor_list:
            new_licensor = Licensors(name=licensor)
            session.add(new_licensor)
        session.commit()

    @staticmethod
    def insert_new_axg(anime):
        anime_ = session.query(Anime).filter(Anime.mal_aid == anime['mal_id']).first()
        new_axg = [genre for genre in anime['genres'] if genre['mal_id'] not in anime_.genres]
        for genre in new_axg:
            genre_ = session.query(Genres).filter(Genres.mal_gid == genre['mal_id']).first()
            anime_.genres.append(genre_)
        session.commit()

    @staticmethod
    def insert_new_axp(anime):
        anime_ = session.query(Anime).filter(Anime.mal_aid == anime['mal_id']).first()
        new_axp = [producer for producer in anime['producers'] if producer['mal_id'] not in anime_.producers]
        for producer in new_axp:
            producer_ = session.query(Producers).filter(Producers.mal_pid == producer['mal_id']).first()
            anime_.producers.append(producer_)
        session.commit()

    @staticmethod
    def insert_new_axl(anime):
        anime_ = session.query(Anime).filter(Anime.mal_aid == anime['mal_id']).first()
        new_axl = [licensor for licensor in anime['licensors'] if licensor not in anime_.licensors]
        for licensor in new_axl:
            licensor_ = session.query(Licensors).filter(Licensors.name == licensor).first()
            anime_.licensors.append(licensor_)
        session.commit()

    @staticmethod
    def insert_new_animelist(mal_uid, anime_list):
        for anime in anime_list:
            list_entry = ListStatus(user_id=mal_uid, mal_aid=anime['mal_id'], title=anime['title'],
                                    show_type=anime['type'], status=anime['watching_status'],
                                    watched=anime['watched_episodes'], eps=anime['total_episodes'],
                                    score=anime['score'], airing=anime['airing_status'])
            session.add(list_entry)
        session.commit()
        # q = insert(ListStatus)
        # status_list = [{
        #     'user_id': mal_uid,
        #     'mal_aid': anime['mal_id'],
        #     'title': anime['title'],
        #     'show_type': anime['type'],
        #     'status': anime['watching_status'],
        #     'watched': anime['watched_episodes'],
        #     'eps': anime['total_episodes'],
        #     'score': anime['score'],
        #     'airing': anime['airing_status'],
        #     } for anime in anime_list]
        # br.edit_data(q, status_list)

    # feed_parser INSERT methods
    @staticmethod
    def insert_new_feed_entry(a_title, a_date, a_link, a_description):
        feed_entry = AniFeeds(title=a_title, date=a_date, link=a_link, description=a_description)
        session.add(feed_entry)
        session.commit()

    @staticmethod
    def insert_new_synonyms(mal_aid, a_title):
        synonym = AnimeXSynonyms(synonym=a_title, mal_aid=mal_aid)
        session.add(synonym)
        session.commit()

    @staticmethod
    def insert_new_torrent_file(mal_aid, group, episode, filename, res, size):
        torrent_file = TorrentFiles(mal_aid=mal_aid, a_group=group, episode=episode, torrent=filename, res=res,
                                        file_size=size)
        session.add(torrent_file)
        session.commit()

    # synonyms INSERT methods
    @staticmethod
    def insert_new_synonym(mal_aid, synonym):
        new_synonym = AnimeXSynonyms(mal_aid=mal_aid, synonym=synonym)
        try:
            session.add(new_synonym)
        except Exception:
            print('INTEGRITY FAILURE')

    # INSERT methods end
    # handlers DELETE methods
    @staticmethod
    def delete_tracked_anime(user_id, mal_aid):
        session.query(UsersXTracked).\
            filter(UsersXTracked.user_id == user_id, UsersXTracked.mal_aid == mal_aid).\
            delete()
        session.commit()

    @staticmethod
    def delete_quotes_by_keyword(keyword):
        session.query(Quotes).\
            filter(Quotes.keyword == keyword).\
            delete()

    # ListStatus DELETE handlers
    @staticmethod
    def delete_list_by_user_id(user_id):
        session.query(ListStatus).\
            filter(ListStatus.user_id == user_id).\
            delete()

    # handlers UPDATE methods
    @staticmethod
    def update_quote_by_keyword(keyword, content):
        quote = session.query(Quotes).filter(keyword == keyword).first()
        quote.content = content
        session.commit()
        # q = update(Quotes).values(content=content, ). \
        #     where(Quotes.keyword == keyword)
        # br.edit_data(q)

    @staticmethod
    def update_users_id_for_manually_added_lists(user_id, user_name):
        user = session.query(Users).filter(Users.tg_nick == user_name).first()
        user.tg_id = user_id
        session.commit()
        # q = update(Users).values(tg_id=user_id).where(Users.tg_nick == user_name)
        # br.edit_data(q)

    @staticmethod
    def update_group_for_users_release_tracking(a_group, user_id, mal_aid):
        release = session.query(UsersXTracked).filter(UsersXTracked.user_id == user_id,
                                                      UsersXTracked.mal_aid == mal_aid).first()
        release.a_group = a_group
        release.last_ep = 0
        session.commit()
        # q = update(UsersXTracked).values(a_group=a_group, last_ep=0).\
        #     where(UsersXTracked.user_id == user_id, UsersXTracked.mal_aid == mal_aid)
        # br.edit_data(q)

    @staticmethod
    def update_users_preferred_resolution(res, tg_id):
        user = session.query(Users).filter(Users.tg_id == tg_id).first()
        user.preferred_res = res
        session.commit()
        # q = update(Users).values(preferred_res=res).where(Users.tg_id == tg_id)
        # br.edit_data(q)

    #todo think about additional checking for correct episode numbers
    @staticmethod
    def update_release_status_for_user_after_delivery(episode, user_id, mal_aid, a_group):
        status = session.query(UsersXTracked).\
            filter(UsersXTracked.user_id == user_id, UsersXTracked.mal_aid == mal_aid,
                  UsersXTracked.a_group == a_group, UsersXTracked.last_ep < episode).first()
        status.last_ep = episode
        session.commit()
        # br.edit_data(q)

    # Feed parser update methods
    # todo not sure it's actually needed
    @staticmethod
    def update_anifeeds_entry(a_link, a_description, a_title, a_date):
        feed_entry = session.query(AniFeeds).filter(AniFeeds.title == a_title,
                                                    AniFeeds.date == a_date).first()
        feed_entry.link = a_link
        feed_entry.description = a_description
        session.commit()
        # q = update(AniFeeds).values(link=a_link, description=a_description).\
        #     where(AniFeeds.title == a_title, AniFeeds.date == a_date)
        # br.edit_data(q)

    @staticmethod
    def update_anifeeds_with_parsed_information(mal_aid, a_group, resolution, episode, size, title, date):
        feed_entry = session.query(AniFeeds).filter(AniFeeds.title == title, AniFeeds.date == date).first()
        feed_entry.mal_aid = mal_aid
        feed_entry.a_group = a_group
        feed_entry.resolution = resolution
        feed_entry.ep = episode
        feed_entry.size = size
        feed_entry.checked = 1
        session.commit()
        # q = update(AniFeeds).values(mal_aid=mal_aid, a_group=a_group, resolution=resolution,
        #                             ep=episode, size=size, checked=1).\
        #     where(AniFeeds.title == title)
        # br.edit_data(q)

    @staticmethod
    def update_anifeeds_unrecognized_entry(size, title, date):
        feed_entry = session.query(AniFeeds).filter(AniFeeds.title == title, AniFeeds.date == date).first()
        feed_entry.size = size
        feed_entry.checked = 1
        session.commit()
        # q = update(AniFeeds).values(size=size, checked=1).where(AniFeeds.title == title)
        # br.edit_data(q)

    # List parser update methods
    @staticmethod
    def update_users_service_id_for_service_nick(service_uid, service_nick):
        user = session.query(Users).filter(Users.mal_nick == service_nick).first()
        user.mal_uid = service_uid
        session.commit()
        # q = update(Users).values(mal_uid=service_uid, mal_nick=service_nick).\
        #     where(Users.mal_nick == service_nick)
        # br.edit_data(q)


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
