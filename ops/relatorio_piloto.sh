#!/bin/bash
CODE="${1:?uso: bash ops/relatorio_piloto.sh <codigo>}"
[[ "$CODE" =~ ^[a-z0-9-]+$ ]] || { echo "codigo invalido"; exit 1; }
cd /opt/meuingles && docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -x -v code='"$CODE" <<'SQL'
WITH u AS (SELECT id, email_verified FROM users WHERE promo_code = :'code'),
a AS (SELECT user_id, count(*) AS tentativas, coalesce(sum(audio_ms) FILTER (WHERE engine = 'azure'), 0) AS ms
      FROM attempts WHERE user_id IN (SELECT id FROM u) GROUP BY user_id),
s AS (SELECT user_id, count(*) AS sims, count(*) FILTER (WHERE status = 'finished') AS fin,
             count(*) FILTER (WHERE status = 'finished' AND overall >= 75) AS aprov
      FROM interview_sessions WHERE user_id IN (SELECT id FROM u) GROUP BY user_id)
SELECT
 (SELECT used_count || ' de ' || coalesce(max_uses::text, 'sem limite') FROM promo_codes WHERE code = :'code') AS vagas_usadas,
 count(*) AS cadastros,
 count(*) FILTER (WHERE u.email_verified) AS email_confirmado,
 count(a.user_id) AS fizeram_alguma_tentativa,
 count(s.user_id) AS iniciaram_simulacao,
 coalesce(sum(s.sims), 0) AS simulacoes_iniciadas,
 coalesce(sum(s.fin), 0) AS simulacoes_finalizadas,
 count(*) FILTER (WHERE s.aprov > 0) AS alunos_com_nota_75_ou_mais,
 round(coalesce(sum(a.ms), 0) / 60000.0, 1) AS min_audio_azure,
 count(*) FILTER (WHERE a.ms >= 36 * 60000) AS perto_do_limite_de_audio,
 count(*) FILTER (WHERE s.sims >= 8) AS perto_do_limite_de_simulacoes,
 round(coalesce(sum(a.ms), 0) / 3600000.0 * 6.79, 2) AS custo_audio_brl_estimado,
 round(coalesce(sum(s.sims), 0) * 0.12, 2) AS custo_ia_brl_estimado
FROM u LEFT JOIN a ON a.user_id = u.id LEFT JOIN s ON s.user_id = u.id;
SQL
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -x -v code='"$CODE" <<'SQL'
SELECT count(*) AS simulacoes_com_relatorio,
 count(DISTINCT s.user_id) AS alunos,
 CASE WHEN count(DISTINCT s.user_id) >= 5 THEN round(avg((s.report->'criteria'->>'star')::numeric), 1) END AS media_star,
 CASE WHEN count(DISTINCT s.user_id) >= 5 THEN round(avg((s.report->'criteria'->>'technical')::numeric), 1) END AS media_tecnica,
 CASE WHEN count(DISTINCT s.user_id) >= 5 THEN round(avg((s.report->'criteria'->>'vocabulary')::numeric), 1) END AS media_vocabulario,
 CASE WHEN count(DISTINCT s.user_id) >= 5 THEN round(avg((s.report->'criteria'->>'grammar')::numeric), 1) END AS media_gramatica,
 CASE WHEN count(DISTINCT s.user_id) >= 5 THEN round(avg((s.report->'criteria'->>'clarity')::numeric), 1) END AS media_clareza
FROM interview_sessions s JOIN users u ON u.id = s.user_id
WHERE u.promo_code = :'code' AND s.status = 'finished' AND s.report IS NOT NULL;
SQL
