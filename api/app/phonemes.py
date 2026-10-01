"""Fonemas: conversão do alfabeto SAPI (padrão do Azure) para IPA e dicas para quem fala português."""

SAPI_TO_IPA = {
    "aa": "ɑ", "ae": "æ", "ah": "ʌ", "ao": "ɔ", "aw": "aʊ", "ax": "ə", "ay": "aɪ", "b": "b",
    "ch": "tʃ", "d": "d", "dh": "ð", "eh": "ɛ", "er": "ɝ", "ey": "eɪ", "f": "f", "g": "ɡ",
    "h": "h", "hh": "h", "ih": "ɪ", "iy": "i", "jh": "dʒ", "k": "k", "l": "l", "m": "m",
    "n": "n", "ng": "ŋ", "ow": "oʊ", "oy": "ɔɪ", "p": "p", "r": "ɹ", "s": "s", "sh": "ʃ",
    "t": "t", "th": "θ", "uh": "ʊ", "uw": "u", "v": "v", "w": "w", "y": "j", "z": "z", "zh": "ʒ",
}

TIPS = {
    "θ": "Ponha a ponta da língua entre os dentes e sopre o ar, sem voz. Não troque por 'f', 't' ou 's'.",
    "ð": "Língua entre os dentes, com voz (a garganta vibra). Não troque por 'd' ou 'z'.",
    "ɹ": "Enrole a ponta da língua para trás sem encostar no céu da boca. Não é o 'r' de 'rato' nem o de 'caro'.",
    "h": "É só um sopro, como o 'rr' bem leve de 'carro' no Rio. Não engula.",
    "æ": "Abra bem a boca, entre 'é' e 'á', como em 'cat'.",
    "ɪ": "'i' curto e relaxado, quase um 'ê' fechado. Não estique como o 'i' de 'vida'.",
    "i": "'i' longo e esticado, sorrindo um pouco.",
    "ʊ": "'u' curto e relaxado, como em 'book'.",
    "u": "'u' longo, com os lábios bem arredondados.",
    "ʌ": "Som de 'â' curto e solto, como em 'but'.",
    "ə": "Vogal fraca e neutra, quase um 'â' rápido. Não pronuncie a letra como está escrita.",
    "ɝ": "'ur' de 'work': língua enrolada para trás, sem vogal aberta antes.",
    "ŋ": "Termine no fundo da garganta, sem soltar um 'g' nem um 'i' depois.",
    "l": "No fim da palavra, o 'l' é escuro: encoste a língua atrás dos dentes, sem virar 'u'.",
    "t": "No fim da palavra, pare no 't' sem soltar vogal ('requiremen-t', não 'requiremen-tchi').",
    "d": "No fim da palavra, pare no 'd' sem acrescentar vogal ('build', não 'buildi').",
    "k": "Solte o 'k' com um pequeno sopro e sem vogal depois.",
    "s": "'s' sem vogal antes nem depois: 'schema' começa direto em 'sk', sem 'is'.",
    "z": "O 's' de plural depois de som com voz vira 'z': 'jobs', 'tables'.",
    "v": "Lábio de baixo encostado nos dentes de cima, com voz.",
    "eɪ": "Ditongo 'ei' completo, como em 'data' (DEI-ta).",
    "oʊ": "Ditongo 'ou' completo, terminando com os lábios arredondados.",
    "aɪ": "Ditongo 'ai' completo, como em 'pipeline'.",
    "tʃ": "Como o 'tch' de 'tchau'.",
    "dʒ": "Como o 'dj' de 'Djavan'.",
    "w": "Comece com os lábios arredondados, como um 'u' rápido.",
    "j": "Como o 'i' rápido de 'iate'.",
}


def to_ipa(p: str) -> str:
    p = (p or "").strip().replace("ˈ", "").replace("ˌ", "")
    return SAPI_TO_IPA.get(p.lower(), p)


MULTI = ["tʃ", "dʒ", "aɪ", "eɪ", "ɔɪ", "aʊ", "oʊ"]
NORMALIZE = {"r": "ɹ", "ɚ": "ɝ", "g": "ɡ"}


def tokens(ipa: str) -> list[str]:
    """Quebra uma transcrição IPA ('/ˈwer.haʊs/') em fonemas: ['w', 'e', 'ɹ', 'h', 'aʊ', 's']."""
    s = (ipa or "").strip("/")
    for ch in "ˈˌ.ː ":
        s = s.replace(ch, "")
    out, i = [], 0
    while i < len(s):
        for m in MULTI:
            if s.startswith(m, i):
                out.append(m); i += len(m); break
        else:
            out.append(NORMALIZE.get(s[i], s[i])); i += 1
    return out


# Frases de engenharia de dados escritas para treinar cada som.
DRILLS = {
    "ɹ": ["We read raw records from the source.", "The report runs every morning.",
          "Retry the request after the error.", "Our warehouse stores three years of history."],
    "t": ["The test failed at the last step.", "Wait, that output is not right.",
          "Start the import at eight.", "We cut the latency by half."],
    "d": ["We added a field to the old table.", "The job failed and I fixed it.",
          "I deployed the code last Friday.", "The dashboard updated around noon."],
    "i": ["We need clean data each week.", "Each team reads the same schema.",
          "Please keep the key fields.", "The feed is free to read."],
    "ɪ": ["This is a big win for the business.", "It will fix six tables.",
          "The pipeline is still in testing.", "We listed the missing fields."],
    "θ": ["I think the throughput is three times higher.", "Both threads finished on Thursday.",
          "Thanks for the thorough review.", "The growth was over thirty percent."],
    "ð": ["The data is there in the other table.", "This is the same as that one.",
          "They loaded those files together.", "Then we merge them with the others."],
    "æ": ["The batch ran after the backup.", "We cannot cancel that task.",
          "Check the cache and the backlog.", "Add a tag to the dataset."],
    "l": ["We pull all the logs into one table.", "Schedule the model as a daily job.",
          "The pool is full, so the call failed.", "Tell the tool to fill the null values."],
    "ʊ": ["I took a look at the notebook.", "Could you push it to the good branch?",
          "The full workload should run tonight."],
    "ɔ": ["We bought more storage for the logs.", "All the data was lost after the fault.",
          "The call was caught by the audit."],
    "aɪ": ["I like the new pipeline design.", "The file size is quite high.",
           "Write the files on time.", "Why did the price rise?"],
    "h": ["How many hours does the job take?", "The history table has a hash key.",
          "Help me handle the high load.", "Who has the host name?"],
    "ŋ": ["We are running and testing the job.", "The string is missing in the log.",
          "Nothing is pending in the queue."],
    "ʌ": ["We run one update every month.", "The budget comes up on Monday.",
          "Cut the bulk of the duplicates."],
    "eɪ": ["The data came late again today.", "Make the table name the same.",
           "We save the state in a cache layer."],
    "ɝ": ["The worker searched the first record.", "Our server works with third party data.",
          "Return the current version first."],
}


def tip_for(p: str) -> str:
    return TIPS.get(p, "")
