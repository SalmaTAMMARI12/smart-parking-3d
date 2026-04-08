-- ============================================================
--  INIT DATABASE — Parking Intelligent
--  Exécuté automatiquement au démarrage du container PostgreSQL
-- ============================================================

CREATE TABLE IF NOT EXISTS places (
    id          VARCHAR(10) PRIMARY KEY,
    ligne       INTEGER,
    colonne     INTEGER,
    etat        VARCHAR(10) DEFAULT 'libre',
    capteur_id  VARCHAR(15),
    timestamp   TIMESTAMP,
    type_place  VARCHAR(15) DEFAULT 'standard'
);

CREATE TABLE IF NOT EXISTS capteurs (
    capteur_id       VARCHAR(15) PRIMARY KEY,
    place_id         VARCHAR(10),
    actif            BOOLEAN DEFAULT TRUE,
    derniere_lecture TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historique (
    id        SERIAL PRIMARY KEY,
    place_id  VARCHAR(10),
    etat      VARCHAR(10),
    timestamp TIMESTAMP
);