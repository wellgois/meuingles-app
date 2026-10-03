with firsts as (
    select user_key, level, min(attempt_date) as first_date
    from {{ source('silver', 'attempts') }}
    group by user_key, level
)
select
    cur.user_key,
    cur.level      as from_level,
    nxt.level      as to_level,
    cur.first_date as from_first_date,
    nxt.first_date as to_first_date,
    {{ days_between('cur.first_date', 'nxt.first_date') }} as days_to_advance
from firsts cur
join firsts nxt on nxt.user_key = cur.user_key and nxt.level = cur.level + 1
