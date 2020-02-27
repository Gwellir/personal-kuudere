USE anibase;
DROP TRIGGER IF EXISTS check_new_max_ep;

delimiter //
CREATE TRIGGER check_new_max_ep
BEFORE UPDATE
ON anifeeds FOR EACH ROW
BEGIN
	IF NEW.mal_aid IS NOT NULL AND (NEW.ep > (SELECT max(ep) FROM anifeeds WHERE mal_aid = NEW.mal_aid) OR (SELECT last_ep FROM ongoings WHERE mal_aid = NEW.mal_aid) IS NULL) THEN
		IF NEW.mal_aid NOT IN (SELECT mal_aid FROM ongoings) THEN
			INSERT INTO ongoings(mal_aid, last_ep, last_release) VALUES(NEW.mal_aid, NEW.ep, NEW.`date`);
		ELSE
			UPDATE ongoings SET last_ep = NEW.ep, last_release = NEW.date WHERE mal_aid = NEW.mal_aid;
		END IF;
	END IF;
END//
DELIMITER ;

-- DROP TRIGGER IF EXISTS fix_nyaa_time;
-- 
-- delimiter //
-- CREATE TRIGGER fix_nyaa_time
-- BEFORE INSERT
-- ON anifeeds FOR EACH ROW
-- BEGIN
-- 	SET	NEW.`date` = CONVERT_TZ(NEW.`date`, '+00:00', '+03:00');
-- END//
-- DELIMITER ;
