BEGIN; -- file executed as single transaction
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE id_type_enum AS enum ('user', 'authority', 'project', 'action');

CREATE TABLE ID (
    id          numeric         PRIMARY KEY,
    id_type     id_type_enum    NOT NULL
);

CREATE TABLE users (
    user_id         numeric     PRIMARY KEY REFERENCES ID(id),
    pwd_hash        text        NOT NULL,
    is_leader       boolean     NOT NULL DEFAULT FALSE,
    last_activity   TIMESTAMP   NOT NULL,
    upvotes         INT         NOT NULL DEFAULT 0,
    downvotes       INT         NOT NULL DEFAULT 0
);

CREATE INDEX trolls_index ON users ((users.upvotes - users.downvotes));

CREATE TABLE votes (
    user_id     numeric NOT NULL REFERENCES ID(id),
    action_id   numeric NOT NULL REFERENCES ID(id),
    is_upvote   boolean NOT NULL,
    PRIMARY KEY (user_id, action_id)
);

CREATE TABLE actions (
    action_id       numeric PRIMARY KEY REFERENCES ID(id),
    project_id      numeric NOT NULL REFERENCES ID(id),
    user_id         numeric NOT NULL REFERENCES ID(id), 
    authority_id    numeric NOT NULL REFERENCES ID(id),
    is_support      boolean NOT NULL,
    upvotes         INT     NOT NULL DEFAULT 0,
    downvotes       INT     NOT NULL DEFAULT 0
);

CREATE VIEW trolls AS
    SELECT user_id, upvotes, downvotes FROM users
    WHERE downvotes > upvotes;

---
CREATE OR REPLACE FUNCTION new_user() RETURNS TRIGGER AS  $BODY$
BEGIN
    INSERT INTO ID VALUES(NEW.user_id, 'user'::id_type_enum);
    RETURN NEW;
END;
$BODY$ LANGUAGE plpgsql;

CREATE TRIGGER on_new_user_trig 
    BEFORE INSERT
    ON users
    FOR EACH ROW EXECUTE PROCEDURE new_user();

---
CREATE OR REPLACE FUNCTION update_votes() RETURNS TRIGGER AS $BODY$
BEGIN
    IF NEW.is_upvote THEN
        UPDATE actions SET upvotes = upvotes + 1 WHERE NEW.action_id = action_id;
        UPDATE users u SET upvotes = u.upvotes + 1 
        FROM actions a WHERE a.action_id = NEW.action_id AND a.user_id = u.user_id;
    ELSE
        UPDATE actions SET downvotes = downvotes + 1 WHERE NEW.action_id = action_id;
        UPDATE users u SET downvotes = u.downvotes + 1 
        FROM actions a WHERE a.action_id = NEW.action_id AND a.user_id = u.user_id;
    END IF;
    RETURN NEW;
END;
$BODY$ LANGUAGE plpgsql;

CREATE TRIGGER on_vote_trig
    AFTER INSERT
    ON votes
    FOR EACH ROW EXECUTE PROCEDURE update_votes();

---
CREATE OR REPLACE FUNCTION on_new_action () RETURNS TRIGGER AS $BODY$
BEGIN
    INSERT INTO ID VALUES(NEW.action_id, 'action'::id_type_enum);
    -- project exists => authority exists -> fill it
    IF NEW.project_id IN (SELECT id AS project_id FROM ID WHERE id_type = 'project'::id_type_enum) THEN
        NEW.authority_id := (SELECT authority_id FROM actions 
                                WHERE project_id = NEW.project_id LIMIT 1);
    -- new project => possibly new authority
    ELSE
        INSERT INTO ID VALUES (NEW.project_id, 'project'::id_type_enum);
        -- authority doesn't exist -> add new
        IF NEW.authority_id NOT IN (SELECT id AS authority_id FROM ID WHERE id_type = 'authority'::id_type_enum) THEN
            INSERT INTO ID VALUES (NEW.authority_id, 'authority'::id_type_enum);
        END IF;
    END IF;
    RETURN NEW;
END;
$BODY$ LANGUAGE plpgsql;

CREATE TRIGGER on_new_action_trig
    BEFORE INSERT
    ON actions
    FOR EACH ROW EXECUTE PROCEDURE on_new_action();

---
CREATE USER app WITH ENCRYPTED PASSWORD 'md596d1b2d8ca22e9afe63b1fc7bb10b9de';
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app;
GRANT SELECT, UPDATE, INSERT ON ALL TABLES IN SCHEMA public TO app;
GRANT SELECT ON trolls TO app;
COMMIT;