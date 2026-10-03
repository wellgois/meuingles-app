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

-- Média de cada fonema por usuário, a partir das avaliações do Azure (protótipo da camada gold).
CREATE OR REPLACE VIEW phoneme_stats AS
SELECT a.user_id,
       ph->>'p'                                   AS phoneme,
       count(*)                                   AS n,
       round(avg((ph->>'score')::numeric), 1)     AS avg_score,
       max(a.created_at)                          AS last_seen
FROM attempts a
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(a.raw->'result'->'words', '[]'::jsonb)) w
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(w->'phonemes', '[]'::jsonb)) ph
WHERE a.engine = 'azure' AND ph->>'score' IS NOT NULL
GROUP BY a.user_id, ph->>'p';

-- Fase 2: contas com e-mail e senha, teste grátis e cotas.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS pass_hash text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan text NOT NULL DEFAULT 'trial';
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS wants_subscription_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_2d_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_end_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS users_email_key ON users (lower(email)) WHERE email IS NOT NULL;
ALTER TABLE attempts ADD COLUMN IF NOT EXISTS audio_ms int;
ALTER TABLE attempts ADD COLUMN IF NOT EXISTS used_llm boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  text PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash  text PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('verify', 'reset')),
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz
);

-- Fase 2.1: trilha pela vaga desejada (júnior, pleno, sênior, especialista).
ALTER TABLE users ADD COLUMN IF NOT EXISTS target_level text;

-- Fase 2.2: assinatura mensal pelo Mercado Pago.
ALTER TABLE users ADD COLUMN IF NOT EXISTS mp_preapproval_id text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mp_status text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mp_payer_email text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mp_created_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_until timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sub_started_at timestamptz;
