#!/usr/bin/env python3

"""
Vocabulary Difficulty Debugger (v15)

Fixes the issue where verb stems (like '連れ') are counted as
full, difficult words because their surface form is shorter than
their lemma ('連れる').
"""

import re
from pathlib import Path
import pandas as pd
from collections import defaultdict

# --- Third-party libraries ---
try:
    from sudachipy import Dictionary, SplitMode
    from wordfreq import zipf_frequency
    from tqdm import tqdm
except ImportError:
    print("Error: Required libraries not found.")
    print("Please run: pip install pandas sudachi-py sudachidict_core wordfreq tqdm")
    exit(1)

# --- !!! CONFIGURATION !!! ---
# Убедись, что путь к папке верный!
TARGET_DIR = "C:/Users/user/Desktop/kitsunekko-mirror/subtitles/Shirokuma Cafe"
DIFFICULTY_THRESHOLD = 5.0
NOISE_ZIPF_THRESHOLD = 3.5
# --- END CONFIGURATION ---

print(f"--- Using v15 Fix Script (Verb Stem Filter) ---")

# --- Regex (Same as before) ---
RE_SRT = re.compile(
    r"\d+\r?\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\r?\n(.*?)\r?\n\r?\n",
    re.DOTALL
)
RE_ASS = re.compile(
    r"^Dialogue:\s*([^,]*?,){9}(.*)",
    re.IGNORECASE
)
RE_TAGS = re.compile(r"<[^>]+>")
RE_ASS_STYLE = re.compile(r"\{[^}]+\}")
RE_BRACKETS_WESTERN = re.compile(r"\(.*?\)")
RE_BRACKETS_JP = re.compile(r"（.*?）")
RE_SPACING = re.compile(r"[ \t\u3000]+")
RE_HAS_HIRAGANA = re.compile(r"[\u3040-\u309F]")
RE_KANJI = re.compile(r"[\u4E00-\u9FFF]")
RE_FOREIGN_WORD_CHECK = re.compile(r"[a-zA-Z\u0400-\u04FF]")
RE_IS_JAPANESE = re.compile(r'^[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFーッっ]+$')
RE_REPETITIVE_SOUND = re.compile(r'^(.{1,3})\1+$')
RE_PURE_KANA_NOISE = re.compile(r'^[\u3040-\u309F\u30A0-\u30FFーッっ]{2,4}$')
RE_IS_KANA_ONLY = re.compile(r'^[\u3040-\u309F\u30A0-\u30FFーッっ]+$')


def clean_line(line: str) -> str:
    line = RE_BRACKETS_WESTERN.sub("", line)
    line = RE_BRACKETS_JP.sub("", line)
    line = RE_ASS_STYLE.sub("", line)
    line = RE_TAGS.sub("", line)
    line = RE_SPACING.sub("", line)
    line = line.replace(r"\N", "|").replace(r"\r\n", "|").replace(r"\n", "|").replace(r"\r", "|")
    line = line.strip()
    return line


def extract_text_from_file(file_path: Path) -> list[str]:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return []

    file_ext = file_path.suffix.lower()
    raw_lines = []

    if file_ext == '.srt':
        raw_lines = RE_SRT.findall(content)
    elif file_ext == '.ass':
        for line in content.splitlines():
            match = RE_ASS.match(line)
            if match:
                raw_lines.append(match.group(2))

    processed_lines = []
    for line in raw_lines:
        cleaned = clean_line(line)
        line_fragments = cleaned.split('|')
        japanese_fragments = []
        for frag in line_fragments:
            frag_stripped = frag.strip()
            if not frag_stripped:
                continue
            if RE_HAS_HIRAGANA.search(frag_stripped):
                if ':' in frag_stripped and RE_FOREIGN_WORD_CHECK.search(frag_stripped):
                    continue
                japanese_fragments.append(frag_stripped)
        if japanese_fragments:
            processed_lines.append("".join(japanese_fragments))
    return processed_lines


def analyze_title_vocabulary():
    print(f"--- Analyzing Title ---")
    print(f"Target: {TARGET_DIR}")

    dir_path = Path(TARGET_DIR)
    if not dir_path.is_dir():
        print(f"Error: Directory not found: {TARGET_DIR}")
        return

    try:
        # Режим 'C' для лучшего разделения слов
        tokenizer = Dictionary().create(mode=SplitMode.C)
    except Exception as e:
        print(f"Error: Failed to initialize SudachiPy. {e}")
        return

    subtitle_files = []
    for ext in ('*.srt', '*.ass'):
        subtitle_files.extend(dir_path.rglob(ext))

    if not subtitle_files:
        print("Error: No .srt or .ass files found in this directory.")
        return

    print(f"Found {len(subtitle_files)} subtitle files.")

    all_word_rarity_scores = []
    word_counts = defaultdict(int)
    word_rarity_map = {}

    VALID_POS_MAIN = {'名詞', '動詞', '形容詞', '副詞'}
    INVALID_POS_SUB = {'数詞', '非自立可能'}  # Keep '非自立可能' as a fallback

    for file_path in tqdm(subtitle_files, desc="Processing files", unit="file"):
        lines = extract_text_from_file(file_path)
        for line in lines:
            try:
                tokens = tokenizer.tokenize(line)
                for token in tokens:

                    surface = token.surface()
                    lemma = token.dictionary_form()
                    pos_tuple = token.part_of_speech()
                    pos_main = pos_tuple[0]
                    pos_sub = pos_tuple[1]

                    # 2a. Filter Interjections
                    if pos_main == '感動詞':
                        continue
                    # 2b. Filter Foreign Words
                    if pos_main == '外国語' or '外国' in pos_tuple:
                        continue
                    # 2c. Filter Proper Nouns
                    if '固有名詞' in pos_tuple:
                        continue
                    # 2d. Filter Onomatopoeia
                    if '擬声語' in pos_tuple or '擬態語' in pos_tuple:
                        continue
                    # 2e. Filter Invalid Sub-types
                    if pos_sub in INVALID_POS_SUB:
                        continue

                    # 2f. Filter by Character Type
                    if lemma.isdigit():
                        continue
                    if not RE_IS_JAPANESE.match(lemma):
                        continue

                    # --- V15 - NEW VERB STEM FILTER ---
                    # Ловит основы глаголов, которые не являются полными словами (напр. '連れ' -> '連れる')
                    # Проверяем, что surface короче lemma И это глагол.
                    if len(surface) < len(lemma) and pos_main == '動詞':
                        # Мы дополнительно проверяем, является ли эта основа частым словом в виде каны
                        # Но пока проще всего просто пропустить.
                        # Если surface короче lemma, то это, скорее всего, неполное спряжение.
                        continue

                    # 2h. --- V13 LEMMATIZATION FIX (still needed for things like 'まう'/'てる') ---
                    # Если поверхностная форма (surface) только из каны, а лемма (lemma) - с кандзи,
                    # и они разные, используем более простое surface.
                    if surface != lemma and RE_IS_KANA_ONLY.match(surface) and RE_KANJI.search(lemma):
                        lemma = surface

                        # 2g. --- V12 NOISE FILTER (on the (potentially) corrected lemma) ---
                    if RE_REPETITIVE_SOUND.match(lemma):
                        continue
                    if RE_PURE_KANA_NOISE.match(lemma):
                        if not RE_KANJI.search(lemma):
                            zipf = zipf_frequency(lemma, 'ja')
                            if zipf < NOISE_ZIPF_THRESHOLD:
                                continue

                    # 3. --- RUN "KEEP" FILTER ---
                    if pos_main not in VALID_POS_MAIN:
                        continue

                    # 4. --- FINAL CLEANUP FILTERS ---
                    if len(lemma) == 1 and pos_main == '名詞':
                        continue

                    # 5. --- SCORE THE WORD ---
                    zipf = zipf_frequency(lemma, 'ja')
                    if zipf == 0.0:
                        continue

                    score = max(0, 8.0 - zipf)
                    all_word_rarity_scores.append(score)
                    if lemma not in word_rarity_map:
                        word_rarity_map[lemma] = score
                    word_counts[lemma] += 1

            except Exception:
                continue

    # --- Generate Report ---
    print("\n" + "=" * 80)
    print("--- VOCABULARY DEBUG REPORT ---")
    print("=" * 80)

    if not all_word_rarity_scores:
        print("\nAnalysis complete, but no valid words were found.")
        return

    total_word_instances = len(all_word_rarity_scores)
    difficult_word_instances = sum(1 for s in all_word_rarity_scores if s >= DIFFICULTY_THRESHOLD)

    if total_word_instances > 0:
        difficulty_density = (difficult_word_instances / total_word_instances) * 100
    else:
        difficulty_density = 0.0

    print(f"Total 'Real' Word Instances Found: {total_word_instances}")
    print(f"Total Unique 'Real' Words Found:  {len(word_rarity_map)}")
    print(f"Total 'Difficult' Instances (Score >= {DIFFICULTY_THRESHOLD}): {difficult_word_instances}")
    print("-" * 80)
    print(f"*** Difficulty Density: {difficulty_density:.4f}% ***")
    print("-" * 80)

    df = pd.DataFrame.from_dict(
        word_rarity_map,
        orient='index',
        columns=['RarityScore']
    )
    df['Count'] = df.index.map(word_counts)
    df_sorted = df.sort_values(by='RarityScore', ascending=False)

    print(f"--- Top 100 'Most Difficult' (Rarest) Unique Words Found ---")
    pd.set_option('display.max_rows', 100)
    pd.set_option('display.width', 1000)
    print(df_sorted.head(100).to_string())
    print("=" * 80)


if __name__ == "__main__":
    analyze_title_vocabulary()