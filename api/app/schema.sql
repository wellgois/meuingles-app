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

-- Visitas ao site (medição própria, sem cookies e sem IP).
CREATE TABLE IF NOT EXISTS visits (
    pv           uuid PRIMARY KEY,
    vid          text NOT NULL,
    sid          text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    path         text NOT NULL,
    ref_host     text,
    utm_source   text,
    utm_medium   text,
    utm_campaign text,
    utm_content  text,
    device       text,
    inapp        text NOT NULL DEFAULT '',
    is_new       boolean NOT NULL DEFAULT false,
    dur_s        int NOT NULL DEFAULT 0,
    max_scroll   int NOT NULL DEFAULT 0,
    clicked_cta  boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS visits_created ON visits (created_at DESC);
CREATE INDEX IF NOT EXISTS visits_vid ON visits (vid);

-- Origem do cadastro (de onde a pessoa veio quando criou a conta).
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_source text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_campaign text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_content text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_vid text;

-- LGPD: ao excluir a conta, apaga as visitas anônimas ligadas a ela.
-- Lista de supressão: o pipeline de dados apaga do lake quem excluiu a conta.
CREATE TABLE IF NOT EXISTS deleted_users (
    user_id     uuid PRIMARY KEY,
    signup_vid  text,
    deleted_at  timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION delete_user_visits() RETURNS trigger AS $$
BEGIN
    IF OLD.signup_vid IS NOT NULL THEN
        DELETE FROM visits WHERE vid = OLD.signup_vid;
    END IF;
    INSERT INTO deleted_users (user_id, signup_vid) VALUES (OLD.id, OLD.signup_vid)
        ON CONFLICT (user_id) DO NOTHING;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS users_delete_visits ON users;
CREATE TRIGGER users_delete_visits BEFORE DELETE ON users FOR EACH ROW EXECUTE FUNCTION delete_user_visits();

-- Fase 5: simulador de entrevista (nível 5). Transcrições só aqui; apagadas em cascata com a conta.
CREATE TABLE IF NOT EXISTS interview_sessions (
    id             uuid PRIMARY KEY,
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz,
    track          text,
    status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'finished', 'abandoned')),
    questions      jsonb NOT NULL,
    overall        numeric(5,1),
    report         jsonb,
    llm_in_tokens  int NOT NULL DEFAULT 0,
    llm_out_tokens int NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS interview_sessions_user ON interview_sessions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS interview_turns (
    session_id  uuid NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    seq         int NOT NULL,
    q_index     int NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('question', 'followup')),
    prompt      text NOT NULL,
    answer      text,
    duration_ms int,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, seq)
);

-- Fase A: currículo do candidato (criptografado no aplicativo) e consentimentos.
CREATE TABLE IF NOT EXISTS user_consents (
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('cv_storage', 'cv_ai')),
    version     text NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, kind)
);

CREATE TABLE IF NOT EXISTS cv_documents (
    user_id        uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    file_kind      text NOT NULL CHECK (file_kind IN ('pdf', 'docx', 'text')),
    file_size      int NOT NULL,
    file_name_enc  bytea,
    file_enc       bytea,
    profile_enc    bytea NOT NULL,
    llm_in_tokens  int NOT NULL DEFAULT 0,
    llm_out_tokens int NOT NULL DEFAULT 0
);

ALTER TABLE interview_turns ADD COLUMN IF NOT EXISTS suggestion text;
ALTER TABLE interview_turns ADD COLUMN IF NOT EXISTS assisted boolean NOT NULL DEFAULT false;

ALTER TABLE users ADD COLUMN IF NOT EXISTS tier text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_tier text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS promo_code text;
CREATE TABLE IF NOT EXISTS promo_codes (
    code        text PRIMARY KEY,
    trial_days  int NOT NULL CHECK (trial_days BETWEEN 1 AND 90),
    max_uses    int,
    used_count  int NOT NULL DEFAULT 0,
    expires_at  timestamptz,
    active      boolean NOT NULL DEFAULT true,
    label       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS audio_min int;
ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS max_sims int;
ALTER TABLE users ADD COLUMN IF NOT EXISTS promo_audio_min int;
ALTER TABLE users ADD COLUMN IF NOT EXISTS promo_max_sims int;
ALTER TABLE cv_documents ADD COLUMN IF NOT EXISTS terms_enc bytea;
