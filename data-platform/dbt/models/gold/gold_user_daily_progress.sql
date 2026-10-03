select
    a.user_key,
    a.attempt_date,
    count(*)                                              as attempts,
    round(avg(a.main_score), 1)                           as avg_main_score,
    round(sum(coalesce(a.audio_ms, 0)) / 60000.0, 2)      as practice_minutes,
    max(a.level)                                          as max_level,
    sum(case when a.engine = 'azure' then 1 else 0 end)   as azure_attempts,
    sum(case when a.used_llm then 1 else 0 end)           as llm_attempts,
    max(case when u.is_owner then 1 else 0 end) = 1       as is_owner
from {{ source('silver', 'attempts') }} a
left join {{ source('silver', 'users') }} u on u.user_key = a.user_key
group by a.user_key, a.attempt_date
