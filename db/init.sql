-- Enable fuzzy search extension
CREATE
    EXTENSION IF NOT EXISTS pg_trgm;

-- Dictionary table for image sources
CREATE TABLE image_sources
(
    id          SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL UNIQUE,
    description TEXT
);

-- Main searchable objects table
CREATE TABLE search_objects
(
    id           SERIAL PRIMARY KEY,
    text_content TEXT NOT NULL,
    image_id     INT  REFERENCES images (id) ON DELETE SET NULL,
    price        INT  NOT NULL DEFAULT 300,
    created_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);


-- Indexes for fuzzy search
CREATE INDEX idx_search_objects_text_trgm ON search_objects USING GIN (text_content gin_trgm_ops);
CREATE INDEX idx_images_key_trgm ON images USING GIN (image_key gin_trgm_ops);
CREATE INDEX idx_images_path_trgm ON images USING GIN (image_path gin_trgm_ops);

-- Images table for storing image data
CREATE TABLE images
(
    id               SERIAL PRIMARY KEY,
    image_path       TEXT  NOT NULL,
    image_key        TEXT  NOT NULL,
    image_source_id  INT   REFERENCES image_sources (id) ON DELETE SET NULL,
    telegram_file_id TEXT,
    image_data       BYTEA NOT NULL,
    thumbnail_data   BYTEA,
    sha512_hash      TEXT  NOT NULL UNIQUE,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

CREATE UNIQUE INDEX idx_users_email ON users (email);

-- Table to track user purchases of specific search objects
CREATE TABLE image_purchases
(
    id           SERIAL PRIMARY KEY,
    user_id      INT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    image_id     INT NOT NULL REFERENCES images (id) ON DELETE CASCADE,
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, image_id)
);

