select * from {{ ref('gold_funnel_by_source') }}
where verified > signups or practiced > signups or engaged > practiced or subscribed > signups
