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
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- Index for fuzzy search
CREATE INDEX idx_search_objects_text_trgm ON search_objects USING GIN (text_content gin_trgm_ops);

-- Customer-generated events table
CREATE TABLE admin_events
(
    id          SERIAL PRIMARY KEY,
    object_id   INT  REFERENCES search_objects (id) ON DELETE SET NULL,
    message     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_resolved BOOLEAN   DEFAULT FALSE
);

-- Images table for storing image data
CREATE TABLE images
(
    id              SERIAL PRIMARY KEY,
    image_path      TEXT  NOT NULL,
    image_key       TEXT  NOT NULL,
    image_source_id INT   REFERENCES image_sources (id) ON DELETE SET NULL,
    image_data      BYTEA NOT NULL,
    thumbnail_data  BYTEA,
    sha512_hash     TEXT  NOT NULL UNIQUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

