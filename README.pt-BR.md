# MeuInglês

[English](README.md)

[![CI](https://github.com/wellgois/meuingles-app/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/wellgois/meuingles-app/actions/workflows/ci.yml)

App de inglês falado para profissionais de dados que se preparam para entrevistas de emprego no Brasil. No ar em https://meuingles.wellgois.com (landing em `/`, app em `/app/`).

Produto em fase inicial, com base pequena de usuários.

## O que faz

| Nível | O que você pratica |
|---|---|
| 1 Sounds & Words | Palavras gravadas no navegador e avaliadas por fonema com Azure Speech |
| 2 Sentences | O mesmo, com frases completas |
| 3 Explain it | Explicações faladas; o Claude corrige a gramática e reescreve a resposta em inglês natural |
| 4 Your projects (STAR) | Perguntas comportamentais respondidas por voz, com feedback de IA |
| 5 Interview | Simulador de entrevista (abaixo) |

Os níveis 3 e 4 usam o reconhecimento de fala do navegador, então continuam disponíveis quando a cota mensal de áudio avaliado acaba.

## Simulador de entrevista (nível 5)

- 3 perguntas: comportamental (STAR), técnica e system design, cada uma com uma pergunta de acompanhamento da IA sobre o ponto mais fraco da resposta.
- Relatório com nota geral e 5 critérios: STAR, correção técnica, vocabulário, gramática e clareza. Aprovação com nota 75 ou mais; o nível pede 2 simulações aprovadas.
- O relatório é feito só a partir do texto transcrito. Não faz afirmações sobre pronúncia nem qualidade do áudio.
- Sem vaga, as perguntas vêm de um banco fixo, sorteado. Opcionalmente, o aluno cola a descrição de uma vaga e as 3 perguntas são geradas a partir dela (e do perfil do currículo, se houver consentimento). Se a geração falhar, a simulação não começa e nenhuma cota é gasta. O texto da vaga é apagado ao finalizar. As perguntas nunca são geradas só a partir do currículo.
- Sugestão da IA (opcional): rascunho de resposta escrito só com o perfil do currículo. Respostas muito parecidas com o rascunho são marcadas como assistidas, e as notas de vocabulário, gramática e clareza ficam limitadas a 70 nelas.
- As respostas são apagadas ao finalizar a simulação; fica só o relatório.

## Currículo

PDF, DOCX ou texto colado vira um perfil em inglês. O aluno revisa e edita antes de salvar. O perfil é guardado criptografado, só depois de consentimento explícito, e pode ser baixado, substituído, apagado ou ter o consentimento retirado.

## Como rodar

```bash
cp .env.example .env   # preencha os valores; nunca faça commit do .env
docker compose up -d --build
curl http://127.0.0.1:$APP_PORT/api/health
```

Arquitetura, CI/CD, deploy com rollback e pipeline de dados estão descritos no [README em inglês](README.md) e em [`data-platform/`](data-platform/README.md).

## Limitações conhecidas

- O Pix é um pagamento avulso de 30 dias e não renova sozinho.
- Sem vaga, o banco de perguntas é fixo e só muda conforme a trilha de carreira.
- O reconhecimento de fala do simulador depende do navegador (o Chrome funciona melhor); é possível digitar a resposta.
- Não há painel para professor ou instituição.
- As notas são geradas por um modelo de linguagem a partir da transcrição. São feedback de treino, não certificação nem previsão de contratação.
