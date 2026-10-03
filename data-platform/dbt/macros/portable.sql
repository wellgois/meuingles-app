{# Os dois únicos pontos em que o SQL muda entre DuckDB (local) e Spark/Databricks. #}

{% macro days_between(start_date, end_date) -%}
    {{ return(adapter.dispatch('days_between', 'meuingles')(start_date, end_date)) }}
{%- endmacro %}

{% macro default__days_between(start_date, end_date) -%}
    datediff({{ end_date }}, {{ start_date }})
{%- endmacro %}

{% macro duckdb__days_between(start_date, end_date) -%}
    date_diff('day', {{ start_date }}, {{ end_date }})
{%- endmacro %}

{% macro week_start(date_col) -%}
    {{ return(adapter.dispatch('week_start', 'meuingles')(date_col)) }}
{%- endmacro %}

{% macro default__week_start(date_col) -%}
    trunc({{ date_col }}, 'week')
{%- endmacro %}

{% macro duckdb__week_start(date_col) -%}
    cast(date_trunc('week', {{ date_col }}) as date)
{%- endmacro %}
