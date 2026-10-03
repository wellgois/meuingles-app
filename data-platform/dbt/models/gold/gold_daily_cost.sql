with daily as (
    select
        attempt_date,
        count(*)                                                                          as attempts,
        sum(case when engine = 'azure' then coalesce(audio_ms, 0) else 0 end) / 3600000.0 as azure_hours,
        sum(case when used_llm then 1 else 0 end)                                         as llm_calls,
        sum(case when used_llm and llm_in_tokens is not null then 1 else 0 end)           as llm_calls_measured,
        sum(case when used_llm then coalesce(llm_in_tokens, {{ var('llm_default_in_tokens') }}) else 0 end)   as llm_in_tokens,
        sum(case when used_llm then coalesce(llm_out_tokens, {{ var('llm_default_out_tokens') }}) else 0 end) as llm_out_tokens
    from {{ source('silver', 'attempts') }}
    group by attempt_date
)
select
    attempt_date,
    attempts,
    round(azure_hours, 4)                                                      as azure_hours,
    round(azure_hours * {{ var('azure_usd_per_hour') }}, 4)                    as azure_cost_usd,
    llm_calls,
    llm_calls_measured,
    llm_in_tokens,
    llm_out_tokens,
    round((llm_in_tokens * {{ var('llm_usd_in_per_m') }} + llm_out_tokens * {{ var('llm_usd_out_per_m') }}) / 1000000.0, 4) as llm_cost_usd,
    round(azure_hours * {{ var('azure_usd_per_hour') }}
          + (llm_in_tokens * {{ var('llm_usd_in_per_m') }} + llm_out_tokens * {{ var('llm_usd_out_per_m') }}) / 1000000.0, 4) as total_cost_usd
from daily
