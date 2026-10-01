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
    p = (p or "").strip()
    return SAPI_TO_IPA.get(p.lower(), p)


def tip_for(p: str) -> str:
    return TIPS.get(p, "")
