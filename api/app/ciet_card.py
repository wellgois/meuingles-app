"""Card "Simular entrevista CI&T": roteiro de estudo pessoal (perguntas reais da entrevista de 02/11/2026 e
respostas-modelo em inglês). Só o dono da conta recebe estes dados; os outros usuários recebem 404.
As respostas são um roteiro para ler em voz alta e adaptar: confira cada fato antes de usar em outra entrevista."""

TITLE = "Simular entrevista CI&T"
SUBTITLE = ("Vaga Senior Data Engineer - Databricks (02/11/2026). Perguntas reais, respostas-modelo em inglês e treino em voz. "
            "Ajuste o texto ao que você consegue explicar e comprovar.")

ITEMS = [
    {
        "id": "scope",
        "tag": "Escopo e inglês",
        "question": (
            "Could you clarify the scope and duration of your hands-on data engineering work, including the scale of the "
            "Databricks pipelines and your use of PySpark, Python, SQL, and cloud services? Also, what production experience "
            "do you have troubleshooting pipeline performance or reliability, and using Git, CI/CD, automated testing, and "
            "infrastructure as code? Finally, how would you characterize your English proficiency in professional discussions?"
        ),
        "answer": (
            "Let me be direct about scope and duration. My hands-on data engineering experience comes from my own projects, "
            "since 2026, not from a formal data engineer role. In June and July 2026, I designed and ran a medallion lakehouse "
            "on Azure with Databricks and Data Factory, using PySpark and Delta Lake, with incremental ingestion by time windows. "
            "The volume was small to medium, from my educational platforms, not terabytes. Today I maintain a daily pipeline that "
            "merges four sources in PostgreSQL, about 9,800 records, with HMAC-SHA256 pseudonymization. I also maintain the data "
            "platform of MeuInglês, with Spark and Delta in bronze and silver, dbt in gold, and a daily cron job with email alerts. "
            "For troubleshooting, I handled three real Azure incidents and documented them on GitHub. I use Git every day, and my "
            "CI on GitHub Actions runs 8 Spark tests and 17 dbt data tests. I have not practiced infrastructure as code with "
            "Terraform yet. My English is basic: I read technical documentation well, but speaking is still developing."
        ),
        "notes": [
            "Azure sempre no passado (jun–jul/2026); não diga \"em produção\" nem \"ADLS Gen2\" até confirmar o armazenamento.",
            "Admitir o volume pequeno é melhor do que inflar a escala numa vaga Sênior.",
        ],
    },
    {
        "id": "pipeline",
        "tag": "Pipeline Databricks",
        "question": (
            "Tell me about a Databricks pipeline you designed or substantially improved using PySpark, Delta Lake, or SQL: "
            "what did it ingest, how did you structure the transformations, and what was your contribution?"
        ),
        "answer": (
            "The best example is the medallion lakehouse I designed and ran on Azure Databricks with Data Factory, in June and "
            "July 2026. It ingested usage data from my educational platforms, coming from a daily pipeline that merges four "
            "sources in PostgreSQL and exports pseudonymized CSV files. The ingestion was incremental, by time windows. Data "
            "Factory orchestrated the runs and passed the RunId to Databricks, so I could trace every run, and failed windows "
            "were rerun automatically. I used the medallion architecture: bronze with raw data in Delta Lake, silver with "
            "cleaning and standardization in PySpark, and gold with aggregated tables in SQL for the dashboards. My contribution "
            "was end to end: I designed the architecture, wrote the notebooks, configured Data Factory, and operated the pipeline "
            "alone. It is a personal project with small to medium volume. Later I applied the same structure in MeuInglês, with "
            "Delta and Spark in bronze and silver, and dbt in gold with automated tests in CI."
        ),
        "notes": [
            "Os notebooks do Azure foram perdidos: só diga o que consegue explicar se pedirem detalhes (silver com deduplicação e gold em SQL são a descrição típica de medallion, confirme o que você de fato fez).",
            "Se o tempo apertar, corte o trecho do MeuInglês.",
        ],
    },
    {
        "id": "diagnosis",
        "tag": "Diagnóstico",
        "question": (
            "Walk me through a time when you diagnosed a Databricks pipeline performance, scalability, or reliability issue: "
            "what evidence helped you find the cause, and how did the pipeline perform afterward?"
        ),
        "answer": (
            "The best case is a reliability problem in my Azure Databricks and Data Factory pipeline in June 2026. The pipeline "
            "failed silently for about eight days: around 24 failed runs, and the dashboards had no data since June 6th. To find "
            "the cause, I used the Azure CLI and the logs of each run. The Data Factory RunId, which I already passed to "
            "Databricks, let me link each ADF run to its cluster. I found three causes in sequence. First, a capacity stockout: "
            "the region had no Standard_DS3_v2 machines, so I changed to the Standard_D4ds_v5 family. Second, an ADF error 3202, "
            "because base_parameters was empty, and I fixed it by passing the pipeline RunId. Third, a QuotaExceeded error from "
            "the four vCPU limit, and I ran a single-node cluster while the quota was raised. After the fixes, the pipeline ran "
            "again and the data came back to the dashboards. The main lesson was observability: the failure was silent because I "
            "had no alert. So in MeuInglês I added an email alert for any failure of the daily pipeline."
        ),
        "notes": [
            "Não há medida de desempenho \"depois\" (tempo, custo). Se perguntarem, diga que o foco foi confiabilidade e não invente números.",
            "Se sobrar tempo: painel do MeuInglês parado de 04 a 20/10 (imagem Docker removida); o script agora reconstrói a imagem sozinho.",
        ],
    },
    {
        "id": "git-ci",
        "tag": "Git, testes e CI/CD",
        "question": (
            "How did it go when you delivered a data engineering change using Git, automated tests, and CI/CD or infrastructure "
            "as code and needed to get another person on board, and how did their response change?"
        ),
        "answer": (
            "I will be transparent: my data projects are individual, so I do not have a case with a code review from a teammate. "
            "But I have a real example of delivering a change with Git, tests, and CI, and having to earn trust in it. In "
            "MeuInglês, the public dashboard was stopped from October 4th to 20th, because the Docker image had been removed and "
            "the daily job was failing. I fixed the script to rebuild the image when it does not exist, and I added an email alert "
            "when the dashboard fails. I did it with a versioned Git commit, a backup before the change, and a check that the "
            "text I was replacing existed exactly once. I tested it by rebuilding the image, regenerating the dashboard, and "
            "receiving the test email. The CI on GitHub Actions runs 8 Spark tests on bronze and silver and 17 dbt data tests on "
            "gold, so every change is validated before it goes in. In a team, I would handle the convincing with evidence: a small "
            "pull request, green tests, a description of the risk, and a rollback plan. Infrastructure as code, like Terraform, "
            "is something I am still developing."
        ),
        "notes": [
            "Não existe colega nem revisor nos registros: não diga que convenceu alguém. Se tiver um caso real de revisão (escola, trabalho anterior, curso), troque o trecho \"In a team...\" por ele.",
            "O alerta só foi testado com e-mail de teste; o ramo \"painel falhou\" ainda não rodou numa falha real.",
        ],
    },
    {
        "id": "quality",
        "tag": "Qualidade e governança",
        "question": (
            "What happened in a specific instance when you aligned data quality, schema, or access requirements with analysts, "
            "data scientists, or business stakeholders: how did you resolve differing needs and ensure the delivered data was "
            "reliable and governed?"
        ),
        "answer": (
            "My projects are individual, so my stakeholders were the users and my own use of the data. But I have a concrete case "
            "about quality and governance. In JogandoLógica, the student ranking was losing points. The cause was a LIMIT applied "
            "before the aggregation, on a UNION of four sources, which cut rows before the sum. In MeuInglês, the session time was "
            "inflated: 433 sessions and about 1,005 fake hours, because I used NOW() instead of the last ping. In both cases, I "
            "fixed the query, made a backup first, and checked the numbers afterward. From those experiences, I treat quality as "
            "part of the pipeline: in MeuInglês, the gold layer in dbt has 6 models and 17 data tests that block broken data before "
            "it reaches the dashboard. For governance, the feed that leaves the daily pipeline is pseudonymized with HMAC-SHA256 at "
            "the source, to protect student data, in line with the Brazilian privacy law, LGPD. Access to the destination uses a "
            "write token with an expiry date, not open credentials. In a team, I would use data contracts: agree on schema, "
            "quality rules, and who can access what with the analysts before publishing."
        ),
        "notes": [
            "Os números do ranking e das 1.005 horas vêm das suas publicações e não foram reverificados: só detalhe o que consegue explicar.",
            "Se não se sentir seguro, tire a frase do token com validade (o SAS de escrita vale até 31/07/2027, segundo o relatório).",
            "Não afirme que alinhou requisitos com analistas reais.",
        ],
    },
]


def card():
    return {"title": TITLE, "subtitle": SUBTITLE, "items": ITEMS}
