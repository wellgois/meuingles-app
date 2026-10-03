with cohort as (
    select user_key, {{ week_start('signup_date') }} as cohort_week
    from {{ source('silver', 'users') }}
    where coalesce(is_owner, false) = false
),
activity as (
    select distinct user_key, {{ week_start('attempt_date') }} as activity_week
    from {{ source('silver', 'attempts') }}
),
joined as (
    select
        c.cohort_week,
        c.user_key,
        cast({{ days_between('c.cohort_week', 'a.activity_week') }} / 7 as int) as week_offset
    from cohort c
    join activity a on a.user_key = c.user_key and a.activity_week >= c.cohort_week
),
sizes as (
    select cohort_week, count(*) as cohort_size from cohort group by cohort_week
)
select
    j.cohort_week,
    j.week_offset,
    s.cohort_size,
    count(distinct j.user_key)                                              as active_users,
    round(100.0 * count(distinct j.user_key) / s.cohort_size, 1)            as retention_pct
from joined j
join sizes s on s.cohort_week = j.cohort_week
group by j.cohort_week, j.week_offset, s.cohort_size
