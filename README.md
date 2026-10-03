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
