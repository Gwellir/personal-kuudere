import mysql.connector
import config


class DBInterface(object):
    def __init__(self):
        self.__conn = mysql.connector.connect(
            host=config.DB.host,
            user=config.DB.user,
            passwd=config.DB.passwd,
            charset='utf8',
            use_unicode=True,
            database=config.DB.db_name
        )
        self.db_name = config.DB.db_name
        self._cursor = self.__conn.cursor()
        self._cursor.execute("SET NAMES utf8mb4;")
        self.anime_ids = set([entry[0] for entry in self.select('mal_aid', 'anime')])

    def create_if_not_exists(self, table_name, fields,
                             params="ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci"):
        print(f"SQL> Creating table {self.db_name}.{table_name}\nFields: {fields}\nParameters: {params}")
        self._cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
        {fields}
        ) {params};""")

    def add_quote(self, quote, table_name='quotes'):
        self._cursor.execute(f"""insert into {table_name} (keyword, content, markdown, author_id)
                            VALUES (%s, %s, %s, %s)""", quote)

    def add_users(self, user_list, table_name='users'):
        # self._cursor.execute("SHOW TABLES LIKE '{}'".format(table_name))
        # result = self._cursor.fetchone()
        # if not result:
        #     self.create(table_name)
        user_tuples = [(user['username'], user['user_id'], None, None) for user in user_list]
        self._cursor.executemany("""
            insert into {table} (mal_nick, mal_uid, tg_nick, tg_id)
            values (%s,%s,%s,%s)
            """.format(table=table_name), user_tuples)

    def add_genres(self, genre_list, table_name='genres'):
        genre_tuples = [(genre['mal_id'], genre['name']) for genre in genre_list]
        self._cursor.executemany("""
            insert into {table} (mal_gid, name)
            values (%s,%s)
            """.format(table=table_name), genre_tuples)

    def add_producers(self, producer_list, table_name='producers'):
        producer_tuples = [(producer['mal_id'], producer['name']) for producer in producer_list]
        self._cursor.executemany("""
            insert into {table} (mal_pid, name)
            values (%s,%s)
            """.format(table=table_name), producer_tuples)

    def add_licensors(self, licensor_list, table_name='licensors'):
        licensor_tuples = [(licensor,) for licensor in licensor_list]
        self._cursor.executemany("""
            insert into {table} (name)
            values (%s)
            """.format(table=table_name), licensor_tuples)

    def add_animelist(self, mal_uid, anime_list, table_name='list_status'):
        anime_tuples = [(mal_uid, anime['mal_id'], anime['title'], anime['type'], anime['watching_status'],
                         anime['watched_episodes'], anime['total_episodes'], anime['score'],
                         anime['airing_status']) for anime in anime_list]
        self._cursor.executemany("""
            insert into {table} (user_id, mal_aid, title, show_type, status, watched, eps, score, airing)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """.format(table=table_name), anime_tuples)

    def add_anime(self, anime_list, table_name='anime'):
        anime_tuples = [(anime['mal_id'], anime['title'], anime['synopsis'],
                         anime['type'] if (anime['type'] != '-') else 'Unknown',
                         anime['airing_start'][:10] + ' ' +
                         anime['airing_start'][11:19] if anime['airing_start'] else None,
                         anime['episodes'], anime['image_url'], float(anime['score']) if anime['score'] else None)
                        for anime in anime_list if anime['mal_id'] not in self.anime_ids]
        self.anime_ids |= set([anime[0] for anime in anime_tuples])
        self._cursor.executemany("""
            insert into {table} (mal_aid, title, synopsis, show_type, started_at, eps, img_url, score)
            values (%s,%s,%s,%s,%s,%s,%s,%s)
            """.format(table=table_name), anime_tuples)

    def add_axg(self, anime, table_name='anime_x_genres'):
        axg_tuples = [(anime['mal_id'], genre['mal_id']) for genre in anime['genres']]
        self._cursor.executemany("""
            insert into {table} (mal_aid, mal_gid)
            values (%s,%s)
            """.format(table=table_name), axg_tuples)

    def add_axp(self, anime, table_name='anime_x_producers'):
        axp_tuples = [(anime['mal_id'], producer['mal_id']) for producer in anime['producers']]
        self._cursor.executemany("""
            insert into {table} (mal_aid, mal_pid)
            values (%s,%s)
            """.format(table=table_name), axp_tuples)

    def add_axl(self, anime, table_name='anime_x_licensors'):
        axp_tuples = [(anime['mal_id'], licensor) for licensor in anime['licensors']]
        self._cursor.executemany("""
            insert into {table} (mal_aid, name)
            values (%s,%s)
            """.format(table=table_name), axp_tuples)

    def select(self, fields, table_name, pattern=None, p_values=None, quiet=False):
        query = f"SELECT {fields} FROM {table_name}"
        if pattern:
            query += f" WHERE {pattern}"
            if not quiet:
                print('SQL>', query % tuple(p_values))
            self._cursor.execute(query, tuple(p_values))
        else:
            if not quiet:
                print('SQL>', query)
            self._cursor.execute(query)
        answer = self._cursor.fetchall()
        if not quiet:
            print('SQL> Selected {} items.'.format(len(answer)))
        return answer

    def update(self, table_name, fields, f_values, pattern=None, p_values=None):
        query = f"UPDATE {table_name} SET {fields}"
        params = f_values
        if pattern:
            query += f" WHERE {pattern}"
            params.extend(p_values)
            print('SQL>', query % tuple(params))
            self._cursor.execute(query, tuple(params))
        else:
            print('SQL>', query % tuple(params))
            self._cursor.execute(query, tuple(params))

    def delete(self, table_name, pattern, p_values):
        query = f"DELETE FROM {table_name} where {pattern}"
        print('SQL>', query % tuple(p_values))
        self._cursor.execute(query, tuple(p_values))

    def commit(self):
        self.__conn.commit()

    def close(self):
        self._cursor.close()
        self.__conn.close()
