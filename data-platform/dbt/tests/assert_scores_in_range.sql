select 'progress' as model, avg_main_score as value from {{ ref('gold_user_daily_progress') }}
where avg_main_score < 0 or avg_main_score > 100
union all
select 'phoneme_avg', avg_score from {{ ref('gold_phoneme_difficulty') }}
where avg_score < 0 or avg_score > 100
union all
select 'phoneme_pct', pct_below_80 from {{ ref('gold_phoneme_difficulty') }}
where pct_below_80 < 0 or pct_below_80 > 100
union all
select 'retention', retention_pct from {{ ref('gold_weekly_retention') }}
where retention_pct < 0 or retention_pct > 100
