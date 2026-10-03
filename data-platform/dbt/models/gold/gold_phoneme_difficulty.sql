select
    p.phoneme,
    count(*)                                                                   as attempts,
    count(distinct a.user_key)                                                 as users_count,
    round(avg(p.score), 1)                                                     as avg_score,
    round(100.0 * sum(case when p.score < 80 then 1 else 0 end) / count(*), 1) as pct_below_80
from {{ source('silver', 'attempt_phonemes') }} p
join {{ source('silver', 'attempts') }} a on a.attempt_id = p.attempt_id
where p.score is not null
group by p.phoneme
