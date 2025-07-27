# standup_ticket_bot/handlers/utils.py

from standup_ticket_bot.models.concert import SourceEnum

# короткие метки для источников
SRC_LABEL = {
    SourceEnum.YANDEX: "ЯН",
    SourceEnum.GOSTANDUP: "ГО",
    SourceEnum.TIMEPAD: "ТМ",
}


def format_concert_row(concert) -> str:
    """
    Формирует строку в виде:
    Название события DD/MM (МЕТКА) — X/Y билетов/регистраций
    """
    date_str = concert.date.strftime("%d/%m")
    label = SRC_LABEL.get(concert.source, "?")
    sold = concert.tickets_sold
    total = concert.tickets_total

    unit = "регистраций" if concert.source == SourceEnum.TIMEPAD else "билетов"

    return f"{concert.name} {date_str} ({label}) — {sold}/{total} {unit}"
