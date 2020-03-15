DROP DATABASE IF EXISTS anibase;
CREATE DATABASE anibase;
USE anibase;

DROP TABLE IF EXISTS users;
CREATE TABLE users (
	id serial primary key,
	tg_nick varchar(50),
	tg_id bigint UNSIGNED,
	mal_nick varchar(50) NOT NULL,
	mal_uid BIGINT UNSIGNED NOT NULL UNIQUE KEY,
	preferred_res INT UNSIGNED DEFAULT 720,
	service ENUM('MAL', 'Anilist'),
		
	INDEX users_idx(tg_nick),
	INDEX mal_idx(mal_nick)
);

-- ALTER TABLE anibase.users ADD id SERIAL;
-- ALTER TABLE anibase.users ADD service ENUM('MAL', 'Anilist');

DROP TABLE IF EXISTS anime;
CREATE TABLE anime (
	mal_aid BIGINT UNSIGNED NOT NULL PRIMARY KEY,
	title varchar(255) NOT NULL,
	title_eng varchar(255),
	title_jap varchar(255),
	synopsis text,
	show_type ENUM ('TV', 'Movie', 'OVA', 'Special', 'ONA', 'Music', 'Other'),
	started_at DATETIME DEFAULT now(),
	ended_at DATETIME,
	bcast_day TINYINT UNSIGNED,
	bcast_time TIME, -- ???
	eps SMALLINT UNSIGNED,
	img_url VARCHAR(100),
	score SMALLINT UNSIGNED,
	status TINYINT UNSIGNED,

	cache_expiry DATETIME NOT NULL DEFAULT now(),
		
	INDEX anime_idx(title),
	INDEX score_idx(score)
	
	-- FOREIGN KEY (mal_aid) REFERENCES list_status(mal_aid)
);

DROP TABLE IF EXISTS anime_full;
CREATE TABLE anime_full (
	aired_from datetime,
	aired_to datetime,
	airing BOOLEAN,
	background TEXT,
	broadcast VARCHAR(50),
	duration SMALLINT UNSIGNED,
	episodes SMALLINT UNSIGNED,
	favorites INT UNSIGNED,
	image_url VARCHAR(100),
	mal_aid BIGINT UNSIGNED PRIMARY KEY,
	members INT UNSIGNED,
	popularity INT UNSIGNED,
	premiered VARCHAR(50),
	`rank` INT UNSIGNED,
	rating VARCHAR(30),
	score FLOAT UNSIGNED,
	scored_by INT UNSIGNED,
	source VARCHAR(30),
	status VARCHAR(30),
	synopsis TEXT, 
	title VARCHAR(255) NOT NULL,
	title_english VARCHAR(255),
	title_japanese VARCHAR(255),
	trailer_url VARCHAR(100),
	show_type ENUM ('TV', 'Movie', 'OVA', 'Special', 'ONA', 'Music', 'Other'),
	url VARCHAR(100),
	
	INDEX anime_f_idx(title),
	INDEX score_f_idx(score),
	INDEX rank_f_idx(`rank`),
	INDEX pop_f_idx(members),
	INDEX id_f_idx(mal_aid),
	INDEX start_f_idx(aired_from),
	INDEX end_f_idx(aired_to),
	INDEX season_f_idx(premiered)
);

DROP TABLE IF EXISTS list_status;
CREATE TABLE list_status (
	user_id BIGINT UNSIGNED NOT NULL,
	mal_aid BIGINT UNSIGNED NOT NULL,
	-- added_at datetime NOT NULL default now(),
	title varchar(255) NOT NULL,
	show_type ENUM ('TV', 'Movie', 'OVA', 'Special', 'ONA', 'Music', 'Other', 'Unknown'),
	status TINYINT UNSIGNED NOT NULL,
	watched INT UNSIGNED,
	eps INT UNSIGNED,
	score INT UNSIGNED,
	airing TINYINT UNSIGNED,
	
	PRIMARY KEY (user_id, mal_aid),
	INDEX conv_name_idx(mal_aid),
	INDEX score_idx(score),
	FOREIGN KEY (user_id) REFERENCES users(mal_uid)
	-- FOREIGN KEY (mal_aid) REFERENCES anime(mal_aid)
);

DROP TABLE IF EXISTS anifeeds;
CREATE TABLE anifeeds (
    title VARCHAR(150) PRIMARY KEY,
    date DATETIME default now(),
    link VARCHAR(50),
    description TEXT,
    mal_aid BIGINT UNSIGNED,
    a_group VARCHAR(50),
    resolution INT UNSIGNED,
    
    index group_idx(a_group),
    index res_idx(resolution),
    index title_idx(title),
    index date_idx(date)
);

DROP TABLE IF EXISTS quotes;
CREATE TABLE quotes (
	id SERIAL PRIMARY KEY,
	keyword varchar(100) NOT NULL,
	content text NOT NULL,
	markdown ENUM('HTML', 'MD'),
	added_at datetime DEFAULT now(),
	
	INDEX key_idx(keyword),
	INDEX md_idx(markdown),
	INDEX date_idx(added_at)
);

-- DROP TABLE IF EXISTS gifs;
-- CREATE TABLE gifs (
-- 	id SERIAL PRIMARY KEY, 
-- 	media_id VARCHAR(100),
-- 	
-- 	INDEX id_idx(id)
-- );

DROP TABLE IF EXISTS gif_tags;
CREATE TABLE gif_tags (
	id SERIAL PRIMARY KEY,
	media_id VARCHAR(100),
	tag VARCHAR(50),
	
	INDEX gif_idx(media_id),
	INDEX tag_idx(tag)
);

DROP TABLE IF EXISTS ongoings;
CREATE TABLE ongoings (
	mal_aid INT PRIMARY KEY,
	last_ep SMALLINT NOT NULL,
	last_release DATETIME NOT NULL,
	
	INDEX id_idx(mal_aid),
	INDEX rel_idx(last_release)
);

DROP TABLE IF EXISTS torrent_files;
CREATE TABLE torrent_files (
	mal_aid bigint UNSIGNED NOT NULL,
	a_group varchar(50) NOT NULL,
	episode SMALLINT UNSIGNED NOT NULL,
	torrent varchar(200) NOT NULL,
	res INT NULL,
	file_size float NOT NULL,
	
	UNIQUE KEY (mal_aid, a_group, episode, res, file_size),
	FOREIGN KEY (mal_aid) REFERENCES anime(mal_aid)
);


-- DROP TABLE IF EXISTS pending_delivery;
-- CREATE TABLE pending_delivery (
-- 	tg_id BIGINT UNSIGNED NOT NULL,
-- 	filename varchar(100) NOT NULL,
-- 	
-- 	PRIMARY KEY (tg_id, filename)
-- -- 	FOREIGN KEY (tg_id) REFERENCES users(tg_id)
-- );

DROP TABLE IF EXISTS studios;
CREATE TABLE studios (
	mal_sid BIGINT UNSIGNED NOT NULL PRIMARY KEY,
	name varchar(255) NOT NULL,
	created_at datetime default now()
);

DROP TABLE IF EXISTS licensors;
CREATE TABLE licensors (
	mal_lid BIGINT UNSIGNED NOT NULL PRIMARY KEY,
	name varchar(255) NOT NULL,
	created_at datetime default now()
);

DROP TABLE IF EXISTS producers;
CREATE TABLE producers (
	mal_pid BIGINT UNSIGNED NOT NULL PRIMARY KEY,
	name varchar(255) NOT NULL,
	created_at datetime default now()
);

DROP TABLE IF EXISTS genres;
CREATE TABLE genres (
	mal_gid BIGINT UNSIGNED NOT NULL PRIMARY KEY,
	name varchar(30)
);

-- CROSS TABLES

DROP TABLE IF EXISTS anime_x_studios;
CREATE TABLE anime_x_studios (
	mal_aid BIGINT UNSIGNED NOT NULL,
	mal_sid BIGINT UNSIGNED NOT NULL,

	PRIMARY KEY (mal_aid, mal_sid),
	FOREIGN KEY (mal_aid) REFERENCES anime(mal_aid),
	FOREIGN KEY (mal_sid) REFERENCES studios(mal_sid)
);

DROP TABLE IF EXISTS anime_x_licensors;
CREATE TABLE anime_x_licensors (
	mal_aid BIGINT UNSIGNED NOT NULL,
	mal_lid BIGINT UNSIGNED NOT NULL,

	PRIMARY KEY (mal_aid, mal_lid),
	FOREIGN KEY (mal_aid) REFERENCES anime(mal_aid),
	FOREIGN KEY (mal_lid) REFERENCES licensors(mal_lid)
);

DROP TABLE IF EXISTS anime_x_producers;
CREATE TABLE anime_x_producers (
	mal_aid BIGINT UNSIGNED NOT NULL,
	mal_pid BIGINT UNSIGNED NOT NULL,

	PRIMARY KEY (mal_aid, mal_pid),
	FOREIGN KEY (mal_aid) REFERENCES anime(mal_aid),
	FOREIGN KEY (mal_pid) REFERENCES producers(mal_pid)
);

DROP TABLE IF EXISTS anime_x_genres;
CREATE TABLE anime_x_genres (
	mal_aid BIGINT UNSIGNED NOT NULL,
	mal_gid BIGINT UNSIGNED NOT NULL,

	PRIMARY KEY (mal_aid, mal_gid),
	FOREIGN KEY (mal_aid) REFERENCES anime(mal_aid),
	FOREIGN KEY (mal_gid) REFERENCES genres(mal_gid)
);

DROP TABLE IF EXISTS anime_x_synonyms;
CREATE TABLE anime_x_synonyms (
	mal_aid BIGINT UNSIGNED NOT NULL,
	synonym varchar(255) NOT NULL PRIMARY KEY,

	FOREIGN KEY (mal_aid) REFERENCES anime(mal_aid)
);

DROP TABLE IF EXISTS users_x_tracked;
CREATE TABLE users_x_tracked (
	user_id BIGINT UNSIGNED NOT NULL,
	mal_aid BIGINT UNSIGNED NOT NULL,
	last_ep INT UNSIGNED DEFAULT 0,
	a_group varchar(50),
	
	PRIMARY KEY (user_id, mal_aid),
	FOREIGN KEY (user_id) REFERENCES users(id),
	FOREIGN KEY (mal_aid) REFERENCES anime(mal_aid),
	INDEX uid_idx(user_id),
	INDEX anime_idx(mal_aid),
	INDEX group_idx(a_group)
);
