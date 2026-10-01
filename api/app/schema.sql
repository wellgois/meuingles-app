-- MeuInglês: banco transacional (OLTP). O pipeline de dados lê daqui na Fase 3.
CREATE TABLE IF NOT EXISTS users (
    id          uuid PRIMARY KEY,
    name        text NOT NULL,
    level       int  NOT NULL DEFAULT 1 CHECK (level BETWEEN 1 AND 5),
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Uma linha por tentativa de fala. "raw" guarda o payload recebido (vira a camada bronze).
CREATE TABLE IF NOT EXISTS attempts (
    id           bigserial PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    level        int  NOT NULL,
    item_id      text NOT NULL,
    target_text  text NOT NULL,
    transcript   text NOT NULL,
    engine       text NOT NULL CHECK (engine IN ('browser', 'azure')),
    main_score   numeric(5,1) NOT NULL CHECK (main_score BETWEEN 0 AND 100),
    accuracy     numeric(5,1),
    completeness numeric(5,1),
    confidence   numeric(5,1),
    fluency      numeric(5,1),
    duration_ms  int,
    word_count   int,
    raw          jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS attempts_user_time ON attempts (user_id, created_at DESC);

-- Uma linha por palavra esperada ou ouvida (vira a camada silver).
CREATE TABLE IF NOT EXISTS attempt_words (
    attempt_id  bigint NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    seq         int    NOT NULL,
    position    int,
    expected    text,
    heard       text,
    status      text   NOT NULL CHECK (status IN ('ok', 'close', 'wrong', 'missing', 'extra')),
    score       numeric(5,1),
    PRIMARY KEY (attempt_id, seq)
);

-- Caderno de erros com revisão espaçada (1, 3, 7, 14, 30 dias).
CREATE TABLE IF NOT EXISTS review_items (
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word          text NOT NULL,
    interval_days int  NOT NULL DEFAULT 1,
    next_due      date NOT NULL,
    misses        int  NOT NULL DEFAULT 0,
    hits          int  NOT NULL DEFAULT 0,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, word)
);
