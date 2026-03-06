CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

CREATE OR REPLACE FUNCTION best_word_levenshtein(content TEXT, query TEXT)
RETURNS INT AS $$
    SELECT COALESCE(MIN(levenshtein(lower(word), lower(query))), 999)
    FROM unnest(string_to_array(content, ' ')) AS word;
$$ LANGUAGE SQL IMMUTABLE;

CREATE TABLE image_sources
(
    id          SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL UNIQUE,
    description TEXT
);

INSERT INTO image_sources (source_name, description) VALUES
('LVIA',     'Lithuanian State Historical Archives'),
('НАРБ',     'Национальный архив Республики Беларусь'),
('ЦДАВО',    'Центральний державний архів вищих органів влади та управління України'),
('ЦДАГО',    'Центральний державний архів громадських об''єднань України'),
('ЦДАЗУ',    'Центральний державний архів зарубіжної україніки'),
('ЦДІАК',    'Центральний державний історичний архів України, м. Київ'),
('ЦДІАЛ',    'Центральний державний історичний архів України, м. Львів'),
('ГДА МВС',  'Галузевий державний архів Міністерства внутрішніх справ України'),
('ГДА МО',   'Галузевий державний архів Міністерства оборони України'),
('ГДА СБУ',  'Галузевий державний архів Служби безпеки України'),
('ГДА СЗРУ', 'Галузевий державний архів Служби зовнішньої розвідки України'),
('ДААРК',    'Державний архів в Автономній Республіці Крим'),
('ДАВіО',    'Державний архів Вінницької області'),
('ДАВоО',    'Державний архів Волинської області'),
('ДАДнО',    'Державний архів Дніпропетровської області'),
('ДАДоО',    'Державний архів Донецької області'),
('ДАЖО',     'Державний архів Житомирської області'),
('ДАЗкО',    'Державний архів Закарпатської області'),
('ДАЗпО',    'Державний архів Запорізької області'),
('ДАІФО',    'Державний архів Івано-Франківської області'),
('ДАК',      'Державний архів м. Києва'),
('ДАКО',     'Державний архів Київської області'),
('ДАКрО',    'Державний архів Кіровоградської області'),
('ДАЛО',     'Державний архів Львівської області'),
('ДАЛуО',    'Державний архів Луганської області'),
('ДАМО',     'Державний архів Миколаївської області'),
('ДАОО',     'Державний архів Одеської області'),
('ДАПО',     'Державний архів Полтавської області'),
('ДАРО',     'Державний архів Рівненської області'),
('ДАС',      'Державний архів м. Севастополя'),
('ДАСО',     'Державний архів Сумської області'),
('ДАТО',     'Державний архів Тернопільської області'),
('ДАХеО',    'Державний архів Херсонської області'),
('ДАХмО',    'Державний архів Хмельницької області'),
('ДАХО',     'Державний архів Харківської області'),
('ДАЧвО',    'Державний архів Чернівецької області'),
('ДАЧгО',    'Державний архів Чернігівської області'),
('ДАЧкО',    'Державний архів Черкаської області');

CREATE TABLE images
(
    id                  SERIAL PRIMARY KEY,
    image_path          TEXT  NOT NULL,
    image_key           TEXT  NOT NULL,
    image_source_id     INT   REFERENCES image_sources (id) ON DELETE SET NULL,
    telegram_file_id    TEXT,
    image_data          BYTEA NOT NULL,
    thumbnail_data      BYTEA,
    sha512_hash         TEXT  NOT NULL UNIQUE,
    image_file_path     TEXT,
    thumbnail_file_path TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE search_objects
(
    id           SERIAL PRIMARY KEY,
    text_content TEXT NOT NULL,
    image_id     INT  REFERENCES images (id) ON DELETE SET NULL,
    price        INT  NOT NULL DEFAULT 300,
    created_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users
(
    id                SERIAL PRIMARY KEY,
    username          VARCHAR(150) UNIQUE NOT NULL,
    email             VARCHAR(255) UNIQUE NOT NULL,
    hashed_password   VARCHAR(255)        NOT NULL,
    telegram_username VARCHAR(150),
    is_admin          BOOLEAN DEFAULT FALSE,
    is_verified       BOOLEAN DEFAULT FALSE,
    is_subscribed     BOOLEAN DEFAULT FALSE
);

CREATE TABLE image_purchases
(
    id           SERIAL PRIMARY KEY,
    user_id      INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    image_id     INT NOT NULL REFERENCES images (id) ON DELETE CASCADE,
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, image_id)
);

CREATE INDEX idx_search_objects_text_trgm ON search_objects USING GIN (text_content gin_trgm_ops);
CREATE INDEX idx_images_key_trgm ON images USING GIN (image_key gin_trgm_ops);
CREATE INDEX idx_images_path_trgm ON images USING GIN (image_path gin_trgm_ops);
CREATE UNIQUE INDEX idx_users_email ON users (email);
CREATE INDEX idx_image_purchases_user_id ON image_purchases (user_id);
CREATE INDEX idx_image_purchases_image_id ON image_purchases (image_id);
