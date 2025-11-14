#!/usr/bin/env python3

"""
Anime Subtitle Linguistic Difficulty Analyzer (v12 -> merged with debug v19 subtitle logic)

This script analyzes a library of anime subtitles to calculate and compare
linguistic difficulty.

Merged changes from your debug script:
- Improved, more flexible SRT regex to detect blocks with varied whitespace/line endings.
- ASS parsing: only lines starting with "Dialogue:" are processed; use split(',', 9) to extract text.
- Better cleaning: nested furigana removal, parentheses cleaning, tag/style removal, spacing normalization.
- Non-recursive subtitle discovery: only analyze .srt/.ass files directly inside each anime folder.
- Katakana loanword filter: ignore rare katakana-only lemmas (using zipf_frequency threshold).
- Keep existing v12 noise filters and other heuristics intact.
"""

import os
import re
import json
from pathlib import Path
import pandas as pd
from multiprocessing import Pool, cpu_count, Manager
from collections import defaultdict
import time

# --- Third-party libraries ---
try:
    from sudachipy import Dictionary, SplitMode
    from jamdict import Jamdict
    from wordfreq import zipf_frequency, top_n_list
    from tqdm import tqdm
except ImportError:
    print("Error: Required libraries not found.")
    print("Please run: pip install pandas sudachi-py sudachidict_core wordfreq jamdict jamdict-data tqdm")
    exit(1)

# --- Configuration ---
ROOT_DIR = "C:/Users/user/Desktop/kitsunekko-mirror/subtitles"
NUM_PROCESSES = cpu_count()
MIN_AVG_WORDS_PER_EP = 200
MIN_UNIQUE_WORDS = 300
DIFFICULTY_THRESHOLD = 5.0
# V12 ADD: Zipf threshold for filtering "noise" words.
NOISE_ZIPF_THRESHOLD = 3.5

# --- Regex (merged from debug v19 + main v12) ---
# Improved flexible SRT regex (from debug script) -- captures index, start, end, text block
RE_SRT = re.compile(
    r"(\d+)\s*[\r\n]+(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*[\r\n]+((?:.*(?:\r\n|\r|\n))*?)(?=\d+\s*[\r\n]+\d{2}:\d{2}:\d{2}|$)",
    re.MULTILINE
)

# ASS pattern is not used to parse the text field here anymore; we use the more robust split method below.
RE_ASS = re.compile(r"^Dialogue:\s*([^,]*?,){9}(.*)", re.IGNORECASE)

RE_TAGS = re.compile(r"<[^>]+>")
RE_ASS_STYLE = re.compile(r"\{[^}]+\}")
# nested furigana: (かな) inside full-width parentheses like （中野(なかの)）
RE_NESTED_FURIGANA = re.compile(r'\([ぁ-んァ-ヶー]+\)')
RE_BRACKETS_WESTERN = re.compile(r"\([^)]*\)")
RE_BRACKETS_JP = re.compile(r"（[^）]*）")
RE_SPACING = re.compile(r"[ \t\u3000]+")
RE_HAS_HIRAGANA = re.compile(r"[\u3040-\u309F]")
RE_KANJI = re.compile(r"[\u4E00-\u9FFF]")
RE_FOREIGN_WORD_CHECK = re.compile(r"[a-zA-Z\u0400-\u04FF]")

# V12 FIX: Added 'ッ' and 'っ' (small tsu)
RE_IS_JAPANESE = re.compile(r'^[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFーッっ]+$')

# Sound/noise filters
RE_REPETITIVE_SOUND = re.compile(r'^(.{1,3})\1+$')
RE_PURE_KANA_NOISE = re.compile(r'^[\u3040-\u309F\u30A0-\u30FFーッっ]{2,4}$')
RE_IS_KANA_ONLY = re.compile(r'^[\u3040-\u309F\u30A0-\u30FFーッっ]+$')

# --- Scoring Mappings ---
KANJI_SCORE_MAP = {
    1: 1,  # Grade 1
    2: 2,  # Grade 2
    3: 3,  # Grade 3
    4: 4,  # Grade 4
    5: 5,  # Grade 5
    6: 6,  # Grade 6
    8: 7,  # Other Jōyō (Secondary School)
    9: 8,  # Jinmeiyō (Names)
    None: 10  # Non-Jōyō / Unknown
}

# --- Cleaning function (from debug) ---
def clean_line(line: str) -> str:
    """Clean subtitle line with proper handling of nested parentheses/furigana."""
    # First, handle nested furigana: （中野(なかの)） -> （中野）
    line = RE_NESTED_FURIGANA.sub("", line)

    # Now remove remaining parentheses content
    line = RE_BRACKETS_JP.sub("", line)
    line = RE_BRACKETS_WESTERN.sub("", line)

    # Continue with other cleaning
    line = RE_ASS_STYLE.sub("", line)
    line = RE_TAGS.sub("", line)
    line = RE_SPACING.sub("", line)
    line = line.replace(r"\N", "|").replace(r"\r\n", "|").replace(r"\n", "|").replace(r"\r", "|")
    line = line.strip()

    return line

# --- Extraction function (merged behavior) ---
def extract_text_from_file(file_path: Path) -> list[str]:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return []

    file_ext = file_path.suffix.lower()
    raw_lines = []

    if file_ext == '.srt':
        # Use improved SRT regex to find text blocks
        matches = RE_SRT.findall(content)
        # matches[i][3] contains the text content
        raw_lines = [match[3] for match in matches]

    elif file_ext == '.ass':
        for line in content.splitlines():
            # Only process lines starting with "Dialogue:" (case-insensitive)
            if not line.lower().startswith('dialogue:'):
                continue

            # Split into max 10 parts (9 commas + text)
            parts = line.split(',', 9)
            if len(parts) < 10:
                continue

            raw_lines.append(parts[9].strip())

    processed_lines = []
    for line in raw_lines:
        cleaned = clean_line(line)
        line_fragments = cleaned.split('|')
        japanese_fragments = []
        for frag in line_fragments:
            frag_stripped = frag.strip()
            if not frag_stripped:
                continue
            # Keep fragments that include hiragana (likely Japanese)
            if RE_HAS_HIRAGANA.search(frag_stripped):
                # Skip foreign-labeled lines like "Character: English text"
                if ':' in frag_stripped and RE_FOREIGN_WORD_CHECK.search(frag_stripped):
                    continue
                japanese_fragments.append(frag_stripped)
        if japanese_fragments:
            processed_lines.append("".join(japanese_fragments))

    return processed_lines

# --- Worker that processes a single anime directory (non-recursive subtitle search) ---
def process_anime_directory(args: tuple) -> dict:
    """
    Analyzes all subtitle files for a single anime title, using a shared kanji_cache.
    Args is a tuple: (dir_path, kanji_cache)
    """
    dir_path, kanji_cache = args

    try:
        tokenizer = Dictionary().create(mode=SplitMode.C)
        jam = Jamdict()
    except Exception as e:
        print(f"\nError: Failed to initialize SudachiPy or Jamdict in worker for {dir_path.name}.")
        print(f"Details: {e}")
        return {}

    # NON-RECURSIVE: only search current directory (no subfolders)
    subtitle_files = []
    for ext in ('*.srt', '*.ass'):
        subtitle_files.extend(dir_path.glob(ext))

    if not subtitle_files:
        return {}

    total_files = len(subtitle_files)
    total_words = 0
    total_kanji_count = 0
    total_dialogue_lines = 0

    all_word_rarity_scores = []
    all_unique_lemmas = set()
    all_unique_kanji = set()

    VALID_POS_MAIN = {'名詞', '動詞', '形容詞', '副詞'}
    INVALID_POS_SUB = {'数詞', '非自立可能'}

    for file_path in subtitle_files:
        lines = extract_text_from_file(file_path)
        for line in lines:
            total_dialogue_lines += 1
            try:
                tokens = tokenizer.tokenize(line)
                for token in tokens:
                    lemma = token.dictionary_form()

                    # --- POS INFO ---
                    pos_tuple = token.part_of_speech()
                    pos_main = pos_tuple[0]
                    pos_sub = pos_tuple[1]

                    # --- DROP FILTERS (v12 logic) ---
                    if pos_main == '感動詞':
                        continue
                    if pos_main == '外国語' or '外国' in pos_tuple:
                        continue
                    if '固有名詞' in pos_tuple:
                        continue
                    if '擬声語' in pos_tuple or '擬態語' in pos_tuple:
                        continue
                    if pos_sub in INVALID_POS_SUB:
                        continue

                    if lemma.isdigit():
                        continue
                    if not RE_IS_JAPANESE.match(lemma):
                        continue

                    # Verb stem filter as in debug: skip if surface shorter than lemma for verbs
                    surface = token.surface()
                    if len(surface) < len(lemma) and pos_main == '動詞':
                        continue

                    # Lemmatization fix from debug: when surface is kana-only but lemma contains kanji,
                    # prefer surface (e.g., cases where Sudachi gives kanji lemma but text is kana)
                    if surface != lemma and RE_IS_KANA_ONLY.match(surface) and RE_KANJI.search(lemma):
                        lemma = surface

                    # --- Katakana loanword filter (from debug) ---
                    # If lemma is kana-only and fully katakana (plus ー、ッ、っ) then treat rare ones as loanword/noise
                    if RE_IS_KANA_ONLY.match(lemma):
                        # check for katakana-only characters range
                        if all('\u30A0' <= c <= '\u30FF' or c in 'ーッっ' for c in lemma):
                            zipf_k = zipf_frequency(lemma, 'ja')
                            # Rare katakana -> likely not useful; threshold set per debug (4.5)
                            if zipf_k < 4.5:
                                continue

                    # --- V12 NOISE FILTERS (keep these) ---
                    # Repetitive sounds
                    if RE_REPETITIVE_SOUND.match(lemma):
                        continue

                    # Short kana-only noise (2-4 chars) if zipf below NOISE_ZIPF_THRESHOLD
                    if RE_PURE_KANA_NOISE.match(lemma):
                        if not RE_KANJI.search(lemma):
                            zipf_n = zipf_frequency(lemma, 'ja')
                            if zipf_n < NOISE_ZIPF_THRESHOLD:
                                continue

                    # --- KEEP filter ---
                    if pos_main not in VALID_POS_MAIN:
                        continue

                    # Single-kana noun junk filter
                    if len(lemma) == 1 and pos_main == '名詞':
                        continue

                    # --- Scoring ---
                    zipf = zipf_frequency(lemma, 'ja')
                    if zipf == 0.0:
                        continue

                    score = max(0, 8.0 - zipf)

                    all_word_rarity_scores.append(score)
                    all_unique_lemmas.add(lemma)
                    total_words += 1

                    kanji_in_lemma = RE_KANJI.findall(lemma)
                    if kanji_in_lemma:
                        total_kanji_count += len(kanji_in_lemma)
                        all_unique_kanji.update(kanji_in_lemma)

            except Exception:
                # keep going on any tokenization/processing errors
                continue

    if total_files == 0 or total_words == 0:
        return {}

    # 1. Volume
    avg_words_per_ep = total_words / total_files
    unique_word_count = len(all_unique_lemmas)

    if avg_words_per_ep < MIN_AVG_WORDS_PER_EP or unique_word_count < MIN_UNIQUE_WORDS:
        return {}

    # 2. Kanji Difficulty
    kanji_density = total_kanji_count / total_dialogue_lines if total_dialogue_lines > 0 else 0

    if all_unique_kanji:
        kanji_complexity_scores = []
        for k in all_unique_kanji:
            if k in kanji_cache:
                grade = kanji_cache[k]
            else:
                result = jam.lookup(f"kanji:{k}")
                grade = None
                if result.chars:
                    grade = result.chars[0].grade
                kanji_cache[k] = grade
            score = KANJI_SCORE_MAP.get(grade, 10)
            kanji_complexity_scores.append(score)

        if kanji_complexity_scores:
            avg_kanji_complexity = sum(kanji_complexity_scores) / len(kanji_complexity_scores)
        else:
            avg_kanji_complexity = 0
    else:
        avg_kanji_complexity = 0

    raw_kanji_score = kanji_density * avg_kanji_complexity

    # 3. Vocabulary Difficulty (Density)
    if total_words > 0:
        difficult_word_instances = sum(1 for s in all_word_rarity_scores if s >= DIFFICULTY_THRESHOLD)
        raw_vocab_score = (difficult_word_instances / total_words) * 100
    else:
        raw_vocab_score = 0

    # Load optional .kitsuinfo.json (safe)
    kitsu_data = {
        'entry_id': None, 'entry_type': None, 'english_name': None,
        'japanese_name': None, 'tmdb_id': None, 'anilist_id': None
    }
    kitsu_info_path = dir_path / ".kitsuinfo.json"

    if kitsu_info_path.exists():
        try:
            with open(kitsu_info_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            kitsu_data['entry_id'] = data.get('entry_id')
            kitsu_data['entry_type'] = data.get('entry_type')
            kitsu_data['english_name'] = data.get('english_name')
            kitsu_data['japanese_name'] = data.get('japanese_name')
            kitsu_data['tmdb_id'] = data.get('tmdb_id')
            kitsu_data['anilist_id'] = data.get('anilist_id')

        except (json.JSONDecodeError, Exception):
            pass

    # Return results dictionary (preserving your original fields)
    return {
        'Anime Title': dir_path.name,
        'entry_id': kitsu_data['entry_id'],
        'entry_type': kitsu_data['entry_type'],
        'english_name': kitsu_data['english_name'],
        'japanese_name': kitsu_data['japanese_name'],
        'tmdb_id': kitsu_data['tmdb_id'],
        'anilist_id': kitsu_data['anilist_id'],
        'Avg. Words/Episode': avg_words_per_ep,
        'Unique Words': unique_word_count,
        'RawKanjiScore': raw_kanji_score,
        'RawVocabScore': raw_vocab_score,
    }

# --- Utility scaler (unchanged) ---
def min_max_scaler(series: pd.Series, min_val=1, max_val=100) -> pd.Series:
    """Scales a pandas Series to a 1-100 range."""
    if series.max() == series.min():
        return pd.Series([min_val] * len(series), index=series.index)
    scaled = min_val + (max_val - min_val) * \
             (series - series.min()) / (series.max() - series.min())
    return scaled

# --- Main entrypoint (unchanged high-level logic, only underlying parsing/filters changed) ---
def main():
    start_time = time.time()

    root = Path(ROOT_DIR)
    if not root.is_dir():
        print(f"Error: Root directory not found: {ROOT_DIR}")
        print("Please set the 'ROOT_DIR' variable at the top of the script.")
        return

    anime_dirs = [d for d in root.iterdir() if d.is_dir()]
    if not anime_dirs:
        print(f"Error: No subdirectories found in {ROOT_DIR}.")
        return

    num_titles = len(anime_dirs)
    print(f"Found {num_titles} anime titles. Starting analysis using {NUM_PROCESSES} processes...")
    print(f"Vocab Difficulty based on 'Density' (Words >= {DIFFICULTY_THRESHOLD} score).")
    print(
        f"Applying content thresholds: Min {MIN_AVG_WORDS_PER_EP} avg. words/ep, Min {MIN_UNIQUE_WORDS} unique words.")
    print(f"Applying noise filters (Zipf < {NOISE_ZIPF_THRESHOLD}) and katakana loanword filtering...")

    with Manager() as manager:
        kanji_cache = manager.dict()

        task_args = [(d, kanji_cache) for d in anime_dirs]

        valid_results = []
        with Pool(processes=NUM_PROCESSES) as pool:
            results_iterator = pool.imap_unordered(process_anime_directory, task_args)
            for result in tqdm(results_iterator, total=num_titles, desc="Analyzing Titles", unit="title"):
                if result:
                    valid_results.append(result)

    if not valid_results:
        print("\nAnalysis complete, but no valid subtitle data was found.")
        print("This could be due to no titles meeting the minimum content thresholds.")
        return

    # --- Create and Normalize DataFrame ---
    df = pd.DataFrame(valid_results)

    df.rename(columns={'RawVocabScore': 'Vocab Density (%)'}, inplace=True)

    df['Kanji Difficulty (1-100)'] = min_max_scaler(df['RawKanjiScore'])
    df['Vocab Difficulty (1-100)'] = min_max_scaler(df['Vocab Density (%)'])
    df['Overall Difficulty (1-100)'] = \
        (df['Kanji Difficulty (1-100)'] + df['Vocab Difficulty (1-100)']) / 2

    final_columns = [
        'Anime Title',
        'entry_id',
        'entry_type',
        'english_name',
        'japanese_name',
        'tmdb_id',
        'anilist_id',
        'Avg. Words/Episode',
        'Unique Words',
        'Kanji Difficulty (1-100)',
        'Vocab Difficulty (1-100)',
        'Overall Difficulty (1-100)',
        'Vocab Density (%)'
    ]
    df_final = df[final_columns].copy()

    df_final['Avg. Words/Episode'] = df_final['Avg. Words/Episode'].round(0).astype(int)
    df_final['Kanji Difficulty (1-100)'] = df_final['Kanji Difficulty (1-100)'].round(1)
    df_final['Vocab Difficulty (1-100)'] = df_final['Vocab Difficulty (1-100)'].round(1)
    df_final['Overall Difficulty (1-100)'] = df_final['Overall Difficulty (1-100)'].round(1)
    df_final['Vocab Density (%)'] = df_final['Vocab Density (%)'].round(2)

    df_sorted_difficulty = df_final.sort_values(by='Overall Difficulty (1-100)')

    end_time = time.time()
    print("\n" + "=" * 80)
    print(f"Analysis Complete! Processed {num_titles} titles in {end_time - start_time:.2f} seconds.")
    print(f"Found and included {len(valid_results)} titles that meet the content thresholds.")
    print("=" * 80)

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_rows', 200)
    pd.set_option('display.width', 1000)

    print("\n### ANIME TITLES SORTED BY DIFFICULTY (Easiest to Hardest) ###")
    print(df_sorted_difficulty.to_string(index=False))

    try:
        csv_path_difficulty = "anime_difficulty_report.csv"
        df_sorted_difficulty.to_csv(csv_path_difficulty, index=False, encoding='utf-8-sig')

        print("\n" + "=" * 80)
        print(f"Successfully saved report to:")
        print(f"1. {os.path.abspath(csv_path_difficulty)}")
        print("=" * 80)
    except Exception as e:
        print(f"\nWarning: Could not save CSV report. Error: {e}")

if __name__ == "__main__":
    main()
