import pandas as pd
import asyncio
import time
from jikanpy.aiojikan import AioJikan
from fuzzywuzzy import fuzz
import sys

# --- SETTINGS ---
# The name of the file to process
INPUT_FILE = "v3_list.csv"
# The name of the file where results will be saved
OUTPUT_FILE = "v3_list_analyzed.csv"

# 🎯 SIMILARITY THRESHOLD (0-100). If accuracy is lower, we consider it incorrect.
SIMILARITY_THRESHOLD = 90
# ⏱️ API LIMIT: No more than 1 request per second (to comply with 60/min limit)
REQUEST_INTERVAL = 1.0


# --- END OF SETTINGS ---


# 🌟 Asynchronous function to search for ONE title
async def find_anime_details(aio_jikan, title, request_semaphore, index, total_titles, start_time):
    clean_title = title.split('(')[0].strip()
    best_match_score = 0
    # ❗️ Default Classification: 'Not Anime'
    result_type = 'Not Anime'
    best_match_result = None

    # ❗️ 1. WAIT FOR SEMAPHORE TO ENSURE 1 REQUEST/SEC
    await request_semaphore.acquire()

    try:
        # ASYNCHRONOUS CALL
        jikan_results = await aio_jikan.search('anime', clean_title, parameters={'limit': 5})

        # Start a timer to release the semaphore after 1 second
        asyncio.get_running_loop().call_later(REQUEST_INTERVAL, request_semaphore.release)

        # 2. Iterate through results and find the best match
        if jikan_results and jikan_results.get('data'):
            best_match_score = 0

            for result in jikan_results['data']:
                found_name = result['title']
                current_score = fuzz.ratio(clean_title.lower(), found_name.lower())

                if current_score > best_match_score:
                    best_match_score = current_score
                    best_match_result = result

            # 3. Analyze the best result
            if best_match_result and best_match_score >= SIMILARITY_THRESHOLD:
                # ❗️ UPDATED LOGIC: Use the exact 'type' from Jikan (e.g., 'TV', 'Movie', 'OVA')
                anime_type = best_match_result.get('type')
                if anime_type:
                    result_type = anime_type # Set classification to the specific type
                else:
                    result_type = 'Anime (Unknown Type)'

    except Exception as e:
        # If the API returns an error, ensure the semaphore is released
        if request_semaphore.locked():
            request_semaphore.release()

        # Output the Jikan error immediately for debugging
        print(f"\n[⚠️ JIKAN ERROR] \tWhen searching for '{title}': {e}")
        # Return "API Error" instead of classification
        return title, 'API Error', 0, index, total_titles

    # ❗️ Output Progress
    elapsed_time = time.time() - start_time
    remaining_titles = total_titles - (index + 1)

    # Calculate Approximate Time Remaining
    eta = remaining_titles * REQUEST_INTERVAL

    progress_message = (
        f"[{index + 1}/{total_titles}] "
        f"Processed: **{title}** -> {result_type}. "
        f"Remaining: {remaining_titles}. ETA: ~{eta:.0f} sec."
    )

    # Write the message to the console, overwriting the line
    sys.stdout.write(f"\r{progress_message}")
    sys.stdout.flush()

    return title, result_type, best_match_score, index, total_titles


# 🏁 Main asynchronous function
async def main():
    start_time = time.time()

    # 1. Load CSV
    try:
        df = pd.read_csv(INPUT_FILE)
        # Check if the title column exists
        if 'Anime Title' not in df.columns:
            print(f"❌ Error: Column 'Anime Title' not found in '{INPUT_FILE}'. Please check the name.")
            return

    except FileNotFoundError:
        print(f"❌ Error: File '{INPUT_FILE}' not found. Ensure it is in the same folder.")
        return

    titles_to_process = df['Anime Title'].dropna().tolist()
    total_titles = len(titles_to_process)

    print(f"--- 🔍 Found {total_titles} titles. Starting asynchronous search (1 request/sec limit)... ---")

    # 2. Rate Limiter Setup (Asynchronous Semaphore)
    request_semaphore = asyncio.Semaphore(1)

    async with AioJikan() as aio_jikan:
        # Create the list of tasks, passing extra parameters for progress tracking
        tasks = [find_anime_details(aio_jikan, title, request_semaphore, index, total_titles, start_time)
                 for index, title in enumerate(titles_to_process)]

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks)

    # Add a newline after the progress bar finishes
    sys.stdout.write('\n')

    # 3. Process Results and Update DataFrame

    # Create dictionaries for fast DataFrame update
    classification_map = {}
    score_map = {}

    # Unpack results, ignoring index and total_titles
    for title, result_type, score, _, _ in results:
        classification_map[title] = result_type
        score_map[title] = score

    # Create new columns and populate them
    df['Classification'] = df['Anime Title'].map(classification_map)
    df['Match_Score'] = df['Anime Title'].map(score_map)

    # 4. Save the Updated CSV
    df.to_csv(OUTPUT_FILE, index=False)

    end_time = time.time()
    total_run_time = end_time - start_time

    print(f"--- ✨ Search Complete! ---")
    print(f"✅ Results saved to file: **{OUTPUT_FILE}**")
    print(f"⏳ Total runtime: **{total_run_time:.2f} seconds**.")
    print(f"⏱️ Estimated time based on limit (1 sec/request): {total_titles * REQUEST_INTERVAL:.0f} seconds.")


if __name__ == "__main__":
    asyncio.run(main())