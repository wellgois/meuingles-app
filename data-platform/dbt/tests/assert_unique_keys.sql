select 'progress' as model, count(*) as n from {{ ref('gold_user_daily_progress') }}
group by user_key, attempt_date having count(*) > 1
union all
select 'progression', count(*) from {{ ref('gold_level_progression') }}
group by user_key, from_level having count(*) > 1
union all
select 'funnel', count(*) from {{ ref('gold_funnel_by_source') }}
group by signup_source, signup_campaign having count(*) > 1
union all
select 'retention', count(*) from {{ ref('gold_weekly_retention') }}
group by cohort_week, week_offset having count(*) > 1
