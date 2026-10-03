select * from {{ ref('gold_level_progression') }}
where days_to_advance < 0 or to_level <> from_level + 1
