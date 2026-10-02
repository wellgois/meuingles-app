"""Banco de conteúdo da trilha. IPA em inglês americano (General American).

Nível 1: palavras técnicas com dica de pronúncia para falantes de português.
Nível 2: frases curtas do dia a dia de engenharia de dados.
Nível 3: explicar um conceito (fala livre; feedback de IA entra com a chave do LLM).
Nível 4: perguntas comportamentais no formato STAR.
"""

WORDS = [
    # id, palavra, IPA, dica
    ("data", "data", "/ˈdeɪ.tə/", "Fale DEI-ta, com 'ei'. Evite 'dáta'."),
    ("schema", "schema", "/ˈskiː.mə/", "SKII-ma: 'sk' como em 'skate' e 'i' longo. Nunca 'xema'."),
    ("pipeline", "pipeline", "/ˈpaɪp.laɪn/", "PAIP-lain. As duas sílabas têm 'ai'."),
    ("query", "query", "/ˈkwɪr.i/", "KUÍ-ri, com o 'r' enrolado para trás, sem bater a língua."),
    ("throughput", "throughput", "/ˈθruː.pʊt/", "O 'th' é a língua entre os dentes soprando ar. Nada de 'f' ou 't'."),
    ("idempotent", "idempotent", "/ˌaɪ.dəmˈpoʊ.tənt/", "ai-dem-POU-tent. A sílaba forte é POU."),
    ("warehouse", "warehouse", "/ˈwer.haʊs/", "UÉR-raus. O 'h' de house é aspirado, como 'r' de 'rato'."),
    ("lakehouse", "lakehouse", "/ˈleɪk.haʊs/", "LEIK-raus. Não engula o 'k'."),
    ("partition", "partition", "/pɑːrˈtɪʃ.ən/", "par-TÍ-shan. A força fica no TÍ."),
    ("latency", "latency", "/ˈleɪ.tən.si/", "LEI-ten-si. A força fica no começo."),
    ("cache", "cache", "/kæʃ/", "Igual a 'cash'. Uma sílaba só, sem 'ê' no final."),
    ("database", "database", "/ˈdeɪ.tə.beɪs/", "DEI-ta-beis. Termina em 's', não em 'z'."),
    ("analytics", "analytics", "/ˌæn.əˈlɪt.ɪks/", "a-na-LÍ-tiks. A força fica no LÍ."),
    ("architecture", "architecture", "/ˈɑːr.kə.tek.tʃɚ/", "AR-ki-tek-tcher. O 'ch' soa 'k'."),
    ("orchestration", "orchestration", "/ˌɔːr.kəˈstreɪ.ʃən/", "or-kes-TREI-shan. O 'ch' soa 'k'."),
    ("ingestion", "ingestion", "/ɪnˈdʒes.tʃən/", "in-DJÉS-tchan."),
    ("deduplicate", "deduplicate", "/diːˈduː.plɪ.keɪt/", "di-DU-pli-keit."),
    ("aggregate", "aggregate", "/ˈæɡ.rə.ɡeɪt/", "Á-gre-gueit. A força fica no começo."),
    ("schedule", "schedule", "/ˈskedʒ.uːl/", "SKÉ-djul no inglês americano."),
    ("scalable", "scalable", "/ˈskeɪ.lə.bəl/", "SKEI-la-bol. O 'l' final é escuro, quase 'u'."),
    ("metadata", "metadata", "/ˈmet.əˌdeɪ.tə/", "MÉ-ta-dei-ta."),
    ("column", "column", "/ˈkɑː.ləm/", "KÁ-lam. O 'n' final é mudo."),
    ("source", "source", "/sɔːrs/", "Uma sílaba só: sórs."),
    ("workflow", "workflow", "/ˈwɝːk.floʊ/", "UÂRK-flou. O 'or' soa como 'âr'."),
    ("deploy", "deploy", "/dɪˈplɔɪ/", "di-PLÓI. A força fica no final."),
    ("environment", "environment", "/ɪnˈvaɪ.rən.mənt/", "in-VAI-ron-ment. O 'n' antes do 'm' quase some."),
    ("requirement", "requirement", "/rɪˈkwaɪr.mənt/", "ri-KUAIR-ment."),
    ("azure", "Azure", "/ˈæʒ.ɚ/", "Á-jer, com 'j' de 'já'. Não 'azúre'."),
    ("python", "Python", "/ˈpaɪ.θɑːn/", "PAI-thon, com 'th' de língua entre os dentes."),
    ("sql", "SQL", "/ˈsiː.kwəl/", "SII-kwel, ou letra por letra: es-kiu-él."),
]

SENTENCES = [
    ("s01", "The job failed because of a schema mismatch."),
    ("s02", "We load the raw data into the bronze layer."),
    ("s03", "The silver layer cleans and deduplicates the data."),
    ("s04", "Gold tables are ready for business users."),
    ("s05", "This query is too slow, so I added a partition."),
    ("s06", "The pipeline runs every day at six in the morning."),
    ("s07", "I use Delta Lake to keep the history of each table."),
    ("s08", "Our orchestration tool retries failed tasks."),
    ("s09", "We need to reduce the latency of this dashboard."),
    ("s10", "I wrote a merge statement to avoid duplicates."),
    ("s11", "The source system changed its file format."),
    ("s12", "Let me check the logs before we restart the job."),
    ("s13", "Data quality tests run before each deployment."),
    ("s14", "I think the bottleneck is in the join."),
    ("s15", "Could you share the requirements for this report?"),
    ("s16", "The throughput dropped after the last release."),
    ("s17", "We store the files in Parquet format."),
    ("s18", "I built this pipeline from scratch."),
    ("s19", "My main stack is Databricks, PySpark and SQL."),
    ("s20", "I have been working with data for two years."),
]

EXPLAIN = [
    ("e01", "Explain the medallion architecture.",
     ["bronze", "silver", "gold", "raw", "clean", "business"]),
    ("e02", "What does idempotent mean in a data pipeline?",
     ["same", "result", "twice", "duplicate", "rerun"]),
    ("e03", "What is the difference between batch and streaming?",
     ["batch", "streaming", "real", "time", "latency", "schedule"]),
    ("e04", "Why do we partition a table?",
     ["partition", "filter", "query", "faster", "date", "files"]),
    ("e05", "What is change data capture?",
     ["change", "capture", "insert", "update", "delete", "source"]),
    ("e06", "How do you check data quality?",
     ["null", "duplicate", "test", "schema", "range", "alert"]),
    ("e07", "What is a slowly changing dimension type two?",
     ["history", "version", "start", "end", "current", "dimension"]),
    ("e08", "What is the difference between a data lake and a data warehouse?",
     ["lake", "warehouse", "raw", "structured", "schema", "cost"]),
]

STAR = [
    ("p01", "Tell me about a pipeline you built from scratch."),
    ("p02", "Tell me about a time a pipeline failed in production."),
    ("p03", "How did you make a slow job run faster?"),
    ("p04", "Tell me about a time you disagreed with a teammate."),
    ("p05", "Why do you want to work as a data engineer?"),
    ("p06", "How does your experience as a teacher help you in data?"),
]

STAR_WORDS = {
    "situation": ["when", "last", "year", "month", "company", "project", "school", "had", "was"],
    "task": ["needed", "goal", "task", "responsible", "asked", "had to"],
    "action": ["i built", "i wrote", "i decided", "i created", "i added", "i changed", "i used", "i fixed"],
    "result": ["result", "reduced", "improved", "saved", "percent", "faster", "now", "records", "hours"],
}

# Trilhas por vaga desejada: perguntas STAR extras no nível 4, antes das comuns.
TRACKS = {"junior": "Júnior", "pleno": "Pleno", "senior": "Sênior", "especialista": "Especialista"}
STAR_TRACKS = {
    "junior": [
        ("jr1", "Tell me about a project you built while learning data engineering."),
        ("jr2", "How do you learn a new tool quickly?"),
        ("jr3", "Tell me about a mistake you made and what you learned from it."),
    ],
    "pleno": [
        ("pl1", "Tell me about a time you improved data quality in a pipeline."),
        ("pl2", "Tell me about a time you delivered with unclear requirements."),
        ("pl3", "How did you handle a schema change in a source system?"),
    ],
    "senior": [
        ("sr1", "Tell me about an architecture decision you made and its trade-offs."),
        ("sr2", "Tell me about a time you mentored another engineer."),
        ("sr3", "How did you reduce the cost of a data platform?"),
    ],
    "especialista": [
        ("sp1", "Tell me about a time you set the technical direction for several teams."),
        ("sp2", "How do you decide between building and buying a data tool?"),
        ("sp3", "Tell me about a time you convinced leadership to invest in platform work."),
    ],
}
TRACK_HINTS = {
    "junior": " Mostre como você aprende e o que entregou.",
    "pleno": " Mostre o problema técnico e o impacto com um número.",
    "senior": " Mostre o trade-off que você escolheu e o impacto no negócio.",
    "especialista": " Mostre a decisão, quem você convenceu e o efeito em vários times.",
}

LEVEL_NAMES = {1: "Sounds & Words", 2: "Sentences", 3: "Explain it", 4: "Your projects", 5: "Interview"}

WORD_INDEX = {w[1].lower(): {"ipa": w[2], "tip": w[3]} for w in WORDS}


def items_for_level(level: int, track: str | None = None):
    if level == 1:
        return [{"id": "w:" + i, "text": t, "ipa": ipa, "hint": tip, "kind": "word"} for i, t, ipa, tip in WORDS]
    if level == 2:
        return [{"id": i, "text": t, "kind": "sentence", "hint": "Ouça primeiro e depois repita no mesmo ritmo."} for i, t in SENTENCES]
    if level == 3:
        return [{"id": i, "text": t, "kind": "explain", "keywords": k,
                 "hint": "Fale por 45 a 60 segundos. Tente usar: " + ", ".join(k) + "."} for i, t, k in EXPLAIN]
    if level == 4:
        hint = "Responda em 90 a 120 segundos: Situação, Tarefa, Ação e Resultado com um número."
        extra = [{"id": i, "text": t, "kind": "star", "track": track, "hint": hint + TRACK_HINTS[track]}
                 for i, t in STAR_TRACKS.get(track, [])]
        return extra + [{"id": i, "text": t, "kind": "star", "hint": hint} for i, t in STAR]
    return []


def find_item(item_id: str):
    for lv in (1, 2, 3, 4):
        for it in items_for_level(lv):
            if it["id"] == item_id:
                return lv, it
    for tr in STAR_TRACKS:
        for it in items_for_level(4, tr):
            if it["id"] == item_id:
                return 4, it
    if item_id.startswith("t:") and 3 <= len(item_id) <= 202:
        return 2, {"id": item_id, "text": item_id[2:], "kind": "sentence", "hint": "Frase sugerida pela IA a partir da sua última resposta."}
    if item_id.startswith("r:"):
        word = item_id[2:]
        info = WORD_INDEX.get(word.lower(), {})
        return 1, {"id": item_id, "text": word, "kind": "word", "ipa": info.get("ipa", ""), "hint": info.get("tip", "")}
    return None, None


def words_with_phoneme(ph: str) -> list[dict]:
    from .phonemes import tokens
    return [{"id": "w:" + i, "text": t, "ipa": ipa, "hint": tip, "kind": "word"}
            for i, t, ipa, tip in WORDS if ph in tokens(ipa)]
