import pandas as pd
import numpy as np
import sys

# --- НАСТРОЙКА ---
# Имя файла, который мы получили из Google Sheets
INPUT_FILE = 'v5 full data.csv'
# Имя файла, в который мы сохраним чистые данные
OUTPUT_FILE = 'list_final_cleaned.csv'


# --------------------


def clean_status(status_series):
    """
    Нормализует колонку 'status'.
    Сопоставляет разные значения (TMDb) с твоими значениями (Anilist).
    """
    print("Очистка колонки 'status'...")

    # Сначала убираем лишние пробелы (на всякий случай)
    # .str.strip() вернет NaN для пустых ячеек, что нормально
    try:
        status_series = status_series.str.strip()
    except AttributeError:
        print("  > Ошибка: Колонка 'status' не содержит строк. Пропускаем.")
        return status_series

    # Словарь для замены.
    # Ключ = то, что мы нашли (TMDb), Значение = то, во что мы это превращаем.
    status_map = {
        'Released': 'FINISHED',
        'Ended': 'FINISHED',
        'Returning Series': 'RELEASING',
        'Returning': 'RELEASING',
        'Canceled': 'CANCELED'
        # 'FINISHED' и 'RELEASING' (из Anilist) уже в правильном формате
    }

    # .replace() заменит только те значения, что найдет в карте.
    # Значения 'FINISHED' и 'RELEASING' останутся 'FINISHED' и 'RELEASING'.
    cleaned_series = status_series.replace(status_map)

    print("  > 'Released' -> 'FINISHED'")
    print("  > 'Returning Series' -> 'RELEASING'")
    print("  > Готово.")
    return cleaned_series


def normalize_score(score_series):
    """
    Нормализует 'average_score' к шкале 1-100.
    - Удаляет 0 и 10
    - Конвертирует 7.4 -> 74
    - Оставляет 63 (1-100) как есть
    """
    print("Нормализация колонки 'average_score'...")

    # 1. Сначала конвертируем все в числа.
    # errors='coerce' превратит любой текст (например, пустые строки) в 'NaN' (пусто).
    try:
        numeric_scores = pd.to_numeric(score_series, errors='coerce')
    except Exception as e:
        print(f"  > Ошибка: Не удалось конвертировать 'average_score' в числа. {e}")
        return score_series

    # 2. Создаем функцию-помощник для применения к КАЖДОЙ ячейке
    def process_score(score):
        # Если ячейка пустая (NaN), оставляем ее пустой (NaN)
        if pd.isna(score):
            return np.nan

        # Твое правило: если 0 или 10, сделать поле пустым (NaN)
        if score == 0 or score == 10:
            return np.nan

        # Твое правило: если это шкала 1-10 (например, 7.4, 8, 9.5)
        # Мы предполагаем, что все < 11 (кроме 0 и 10) - это шкала 1-10.
        if score > 0 and score < 11:
            return score * 10

        # Твое правило: если это шкала 1-100 (например, 63, 74)
        # Мы предполагаем, что все >= 11 - это уже 1-100.
        if score >= 11 and score <= 100:
            return score

        # Если что-то не попало под правила (например, -5), убираем
        return np.nan

    # 3. Применяем нашу функцию ко всей колонке
    cleaned_series = numeric_scores.apply(process_score)

    print("  > 7.4 -> 74.0")
    print("  > 10 -> (пусто)")
    print("  > 0 -> (пусто)")
    print("  > 63 -> 63.0")
    print("  > Готово.")
    return cleaned_series


def clean_genres(genres_series):
    """
    Очищает колонку 'genres', удаляя 'N/A'.
    """
    print("Очистка колонки 'genres'...")
    try:
        # .replace() найдет ячейки, которые ТОЧНО равны 'N/A', и заменит их на пустую строку
        cleaned_series = genres_series.replace('N/A', '')
    except Exception as e:
        print(f"  > Ошибка: Не удалось очистить 'genres'. {e}")
        return genres_series

    print("  > 'N/A' -> (пусто)")
    print("  > Готово.")
    return cleaned_series


# --- Основной скрипт ---
def main():
    print(f"Загрузка файла: {INPUT_FILE}...")
    try:
        # Загружаем CSV. Мы знаем, что разделитель - запятая.
        df = pd.read_csv(INPUT_FILE, sep=',')
        print(f"Загружено {len(df)} строк.")
    except FileNotFoundError:
        print(f"ОШИБКА: Файл '{INPUT_FILE}' не найден.")
        print("Убедись, что файл находится в той же папке, что и скрипт.")
        return
    except Exception as e:
        print(f"ОШИБКА при чтении CSV: {e}")
        return

    # 1. Очистка 'status'
    if 'status' in df.columns:
        df['status'] = clean_status(df['status'])
    else:
        print("ВНИМАНИЕ: Колонка 'status' не найдена. Пропускаем.")

    # 2. Очистка 'average_score'
    if 'average_score' in df.columns:
        df['average_score'] = normalize_score(df['average_score'])
    else:
        print("ВНИМАНИЕ: Колонка 'average_score' не найдена. Пропускаем.")

    # 3. Очистка 'genres'
    if 'genres' in df.columns:
        df['genres'] = clean_genres(df['genres'])
    else:
        print("ВНИМАНИЕ: Колонка 'genres' не найдена. Пропускаем.")

    # 4. Сохранение результата
    try:
        df.to_csv(OUTPUT_FILE, sep=',', index=False, encoding='utf-8')
        print(f"\nУспешно сохранено!")
        print(f"Все изменения в файле: {OUTPUT_FILE}")
    except Exception as e:
        print(f"ОШИБКА при сохранении файла: {e}")


# Запускаем главный скрипт
if __name__ == "__main__":
    main()