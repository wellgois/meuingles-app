with att as (
    select user_key, count(*) as attempts
    from {{ source('silver', 'attempts') }}
    group by user_key
),
base as (
    select
        coalesce(u.signup_source, 'sem origem')   as signup_source,
        coalesce(u.signup_campaign, '')           as signup_campaign,
        u.email_verified                          as email_verified,
        coalesce(att.attempts, 0)                 as attempts,
        case when u.plan in ('active', 'canceled') or u.paid_until is not null then 1 else 0 end as subscribed
    from {{ source('silver', 'users') }} u
    left join att on att.user_key = u.user_key
    where coalesce(u.is_owner, false) = false
)
select
    signup_source,
    signup_campaign,
    count(*)                                                                   as signups,
    sum(case when email_verified then 1 else 0 end)                            as verified,
    sum(case when attempts >= 1 then 1 else 0 end)                             as practiced,
    sum(case when attempts >= {{ var('engaged_attempts') }} then 1 else 0 end) as engaged,
    sum(subscribed)                                                            as subscribed
from base
group by signup_source, signup_campaign
