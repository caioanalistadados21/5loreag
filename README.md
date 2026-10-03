# Agenda Mobile + Google Calendar

Aplicativo Streamlit de agenda com duração fixa de **1h30**, banco SQLite local e sincronização opcional com Google Calendar.

O projeto foi preparado para funcionar em:

- Windows local;
- Linux/macOS;
- Docker;
- Render/Railway/VPS usando variáveis de ambiente.

## Regras da agenda

- Início do dia: **07:00**.
- Horários de início a cada **30 minutos**.
- Cada atendimento ocupa **1h30**.
- Último início: **19:00**.
- Encerramento máximo: **20:30**.
- Conflitos são validados antes de salvar.
- Eventos já existentes no Google Calendar também bloqueiam horários.

## O que foi ajustado na integração Google

- leitura das credenciais por `.streamlit/secrets.toml` **ou `secrets.toml` na raiz**;
- leitura por `GOOGLE_SERVICE_ACCOUNT_JSON`;
- leitura por variáveis separadas (`GOOGLE_PROJECT_ID`, `GOOGLE_CLIENT_EMAIL`, `GOOGLE_PRIVATE_KEY`);
- leitura por `service_account.json`;
- mensagens específicas para erros 400/401/403/404;
- teste de leitura do calendário;
- **teste real de gravação**, criando um evento temporário e apagando logo em seguida;
- criação do atendimento no Google antes de gravar a cópia local;
- rollback do evento Google se a gravação local falhar;
- link para abrir o evento criado no Google Calendar;
- diagnóstico de configuração quando faltam credenciais.

## 1. Criar a Service Account

No Google Cloud:

1. Crie ou selecione um projeto.
2. Ative **Google Calendar API**.
3. Vá em **IAM e administrador > Contas de serviço**.
4. Crie uma Service Account.
5. Na Service Account, crie uma chave do tipo **JSON**.
6. Baixe o arquivo JSON.

O JSON terá um campo parecido com:

```json
"client_email": "agenda-mobile@meu-projeto.iam.gserviceaccount.com"
```

Esse endereço é importante.

## 2. Compartilhar o calendário correto

Entre no Google Calendar da conta:

```text
caioanalistadados@gmail.com
```

Abra as configurações desse calendário e compartilhe com o `client_email` da Service Account.

A permissão precisa permitir **fazer alterações nos eventos**.

O projeto está configurado para usar:

```text
calendar_id = caioanalistadados@gmail.com
```

## 3. Configuração local recomendada

Você pode usar qualquer uma destas duas formas:

```text
.streamlit/secrets.toml
```

ou, nesta versão do projeto:

```text
secrets.toml
```

na raiz, no mesmo diretório de `app.py`.

Há modelos em `.streamlit/secrets.example.toml` e `secrets.example.toml`. Copie um deles para o nome final e substitua os campos pelos valores do JSON da Service Account.

Exemplo:

```toml
[google_calendar]
calendar_id = "caioanalistadados@gmail.com"

[google_service_account]
type = "service_account"
project_id = "meu-projeto"
private_key_id = "..."
private_key = """-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
"""
client_email = "agenda-mobile@meu-projeto.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
```

> Não envie `secrets.toml`, `.streamlit/secrets.toml`, `service_account.json` ou a chave privada para o Git. Todos estão protegidos no `.gitignore`.

## 4. Alternativa local com service_account.json

Você também pode deixar o JSON original na raiz do projeto com o nome:

```text
service_account.json
```

E definir somente:

### Windows CMD

```bat
set GOOGLE_CALENDAR_ID=caioanalistadados@gmail.com
streamlit run app.py
```

### PowerShell

```powershell
$env:GOOGLE_CALENDAR_ID="caioanalistadados@gmail.com"
streamlit run app.py
```

O arquivo `service_account.json` já está no `.gitignore`.

## 5. Instalar e executar no Windows

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Na primeira instalação você também pode executar:

```text
setup_windows.bat
```

Depois, para abrir o sistema, execute:

```text
run.bat
```

Depois abra:

```text
http://localhost:8501
```

## 6. Testar a integração antes de agendar

Abra a barra lateral do aplicativo.

Quando as credenciais estiverem carregadas, aparecerá:

```text
Google Calendar configurado
```

Execute na ordem:

### 1. Testar leitura do Google

Deve retornar algo como:

```text
Leitura OK · Agenda: ...
Service Account: ...@...iam.gserviceaccount.com
```

### 2. Testar gravação no Google

O aplicativo cria um evento temporário e o remove logo em seguida.

O resultado esperado é:

```text
Gravação OK. Evento temporário criado e removido com sucesso.
```

Se esse teste funcionar, a Service Account realmente possui permissão para criar eventos.

## 7. Erros mais comuns

### Erro 403

Normalmente significa que a Service Account consegue autenticar, mas **não tem permissão de gravação** no calendário.

Confira se o calendário `caioanalistadados@gmail.com` foi compartilhado com o `client_email` exato da Service Account e se a permissão permite alterar eventos.

### Erro 404

Normalmente significa:

- `GOOGLE_CALENDAR_ID` incorreto; ou
- o calendário não foi compartilhado com a Service Account.

Use:

```text
caioanalistadados@gmail.com
```

### Erro 401

A credencial é inválida, foi revogada, está incompleta ou a chave privada foi copiada incorretamente.

Gere uma nova chave JSON na Service Account e atualize a configuração.

### Google Calendar não configurado

A barra lateral informa quais itens estão faltando.

No mínimo, o projeto precisa de:

```text
GOOGLE_CALENDAR_ID
```

mais uma forma de credencial da Service Account.

## 8. Se aparecer "Google Calendar ainda não está configurado"

Confira primeiro a localização do arquivo. O Streamlit tradicionalmente procura `.streamlit/secrets.toml`; esta versão também aceita `secrets.toml` na raiz, no mesmo diretório de `app.py`.

Exemplo correto usando arquivo na raiz:

```text
agenda_google_calendar_completo/
├── app.py
├── google_calendar.py
├── secrets.toml
└── ...
```

Depois de criar ou mover o arquivo, **pare e inicie novamente o Streamlit**.

Se o arquivo existir mas estiver com TOML inválido, o aplicativo agora mostra a linha e a coluna do erro. Em TOML, não coloque vírgula no fim de uma atribuição, por exemplo `private_key = "..."` deve terminar sem vírgula.

Se estiver usando Docker, não coloque a chave dentro da imagem. Prefira as variáveis `GOOGLE_CALENDAR_ID` e `GOOGLE_SERVICE_ACCOUNT_JSON`, ou monte `secrets.toml` como volume somente leitura.

## 9. Deploy no Render/Railway/VPS

Para ambiente hospedado, prefira variáveis de ambiente.

Defina:

```text
GOOGLE_CALENDAR_ID=caioanalistadados@gmail.com
```

E:

```text
GOOGLE_SERVICE_ACCOUNT_JSON=<JSON COMPLETO DA SERVICE ACCOUNT>
```

Há um modelo em:

```text
.env.example
```

O código também corrige automaticamente chaves privadas recebidas com `\n` no lugar de quebra de linha real.

## 9. Docker

Crie `.env` baseado em `.env.example` e execute:

```bash
docker compose up -d --build
```

Abra:

```text
http://localhost:8501
```

O `docker-compose.yml` mantém o banco SQLite em um volume Docker.

## 10. Como o salvamento funciona

Quando **Sincronizar com Google Calendar** está ativado:

1. o app consulta os compromissos existentes no Google;
2. valida conflito de horário;
3. cria o evento no Google Calendar;
4. recebe o ID do evento;
5. salva a cópia no SQLite com esse ID;
6. mostra uma confirmação e um botão para abrir o evento no Google Calendar.

Se o Google recusar o evento, o registro local não é criado.

Se o Google criar o evento, mas o SQLite falhar, o aplicativo tenta excluir o evento do Google para evitar inconsistência.

## Estrutura

```text
agenda_google_calendar_completo/
├── app.py
├── config.py
├── database.py
├── google_calendar.py
├── scheduling.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── setup_windows.bat
├── run.bat
├── run.sh
├── README.md
├── .env.example
├── .gitignore
├── .dockerignore
├── .streamlit/
│   ├── config.toml
│   └── secrets.example.toml
├── data/
│   └── .gitkeep
└── tests/
    ├── test_google_config.py
    └── test_slots.py
```

## Segurança

Nunca publique:

```text
.streamlit/secrets.toml
service_account.json
.env
```

O projeto já ignora esses arquivos no Git e no contexto do Docker.
