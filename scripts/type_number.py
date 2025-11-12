import pandas as pd
import os

# --- Настройки ---
CSV_FILENAME = "anime_difficulty_report.csv"


# --- Конец Настроек ---

def analyze_entry_types(filepath: str):
    """
    Анализирует CSV-файл и подсчитывает количество
    каждого 'entry_type', включая пустые значения.
    """

    # 1. Проверяем, существует ли файл
    if not os.path.exists(filepath):
        print(f"Ошибка: Файл не найден по пути: {filepath}")
        print("Пожалуйста, убедитесь, что скрипт находится в той же папке, что и ваш CSV,")
        print(f"или измените переменную CSV_FILENAME в скрипте.")
        return

    try:
        # 2. Читаем CSV-файл
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Ошибка при чтении CSV-файла: {e}")
        return

    # 3. Проверяем, есть ли нужный столбец
    if 'entry_type' not in df.columns:
        print(f"Ошибка: Столбец 'entry_type' не найден в файле {filepath}.")
        print("Доступные столбцы:", df.columns.tolist())
        return

    # 4. Считаем уникальные значения в столбце 'entry_type'
    #    dropna=False очень важен — он гарантирует,
    #    что мы также подсчитаем строки, где entry_type пустой (NaN/None).
    print(f"Анализируем '{filepath}'...")
    print("---" * 10)
    print("Количество наименований по 'entry_type':\n")

    type_counts = df['entry_type'].value_counts(dropna=False)

    # 5. Выводим результат
    print(type_counts)
    print("---" * 10)

    # 'NaN' в выводе представляет собой строки,
    # где 'entry_type' был пуст (None).
    if type_counts.index.isna().any():
        print("(NaN обозначает записи, у которых не было .kitsuinfo.json или поле было пустым)")
    else:
        print("(Пустых 'entry_type' не найдено)")


if __name__ == "__main__":
    analyze_entry_types(CSV_FILENAME)