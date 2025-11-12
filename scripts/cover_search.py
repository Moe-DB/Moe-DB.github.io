import csv
import requests
import time
import os

# --- Configuration ---
INPUT_FILENAME = 'list.csv'
OUTPUT_FILENAME = 'list_with_all_data.csv'  # Changed to a new output file
ANILIST_ID_COLUMN_NAME = 'anilist_id'

# --- NEW: Define all column names ---
POSTER_COLUMN_NAME = 'poster_url'
EPISODES_COLUMN_NAME = 'episodes'
STATUS_COLUMN_NAME = 'status'
GENRES_COLUMN_NAME = 'genres'
YEAR_COLUMN_NAME = 'start_year'
SCORE_COLUMN_NAME = 'average_score'
# --- End of new column names ---

# --- End of Configuration ---


# This is the GraphQL query we will send to AniList.
ANILIST_API_URL = 'https://graphql.anilist.co'

# --- UPDATED: New GraphQL Query ---
# We are now asking for all the new fields you wanted
QUERY = '''
query ($id: Int) {
  Media (id: $id, type: ANIME) {
    id
    coverImage {
      large
    }
    episodes
    status
    genres
    startDate {
      year
    }
    averageScore
  }
}
'''


# --- End of Updated Query ---


# --- UPDATED: Function renamed and logic expanded ---
def get_media_data(anilist_id):
    """
    Fetches all media data for a given AniList ID.
    Returns a TUPLE of (poster, episodes, status, genres, year, score)
    or None if not found or an error occurs.
    Includes retry logic for 429 Rate Limit errors.
    """
    try:
        # Convert to float first to handle IDs like "123.0", then to int
        variables = {
            'id': int(float(anilist_id))
        }
    except ValueError:
        # This catches bad IDs like 'abc' or '1.2.3' before we even make a request
        print(f"  -> Error parsing data for ID: {anilist_id}")
        return None

    # --- Retry Logic ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Make the POST request to the AniList API
            response = requests.post(
                ANILIST_API_URL,
                json={'query': QUERY, 'variables': variables},
                timeout=15  # Add a timeout for safety
            )

            # Raise an error if the request was unsuccessful (like 429, 404, 500)
            response.raise_for_status()

            # --- Success ---
            data = response.json()
            if 'data' in data and 'Media' in data['data'] and data['data']['Media']:

                # --- NEW: Extract all data points ---
                media = data['data']['Media']

                poster_url = media.get('coverImage', {}).get('large')
                episodes = media.get('episodes')
                status = media.get('status')

                # Genres is a list, so we join it into a single comma-separated string
                genres_list = media.get('genres', [])
                genres_str = ", ".join(genres_list)

                year = media.get('startDate', {}).get('year')
                score = media.get('averageScore')

                # Return all data as a single tuple
                return (poster_url, episodes, status, genres_str, year, score)
                # --- End of new extraction ---

            else:
                print(f"  -> No data found for ID: {anilist_id}")
                return None  # Request was successful, but no data for this ID

        except requests.exceptions.RequestException as e:
            # --- This is our Error Handler ---
            if e.response is not None and e.response.status_code == 429:
                try:
                    retry_after = int(e.response.headers.get('Retry-After', 10))
                    print(f"  -> Hit Rate Limit (429). Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                except Exception:
                    print(f"  -> Hit Rate Limit (429). Waiting 10 seconds...")
                    time.sleep(10)
            else:
                print(f"  -> HTTP Error for ID {anilist_id}: {e}")
                return None  # Don't retry, just fail this row

        except (KeyError, TypeError):
            print(f"  -> Error parsing JSON response for ID: {anilist_id}")
            return None  # Fail this row

    # If we exit the loop, it means we tried 3 times and failed
    print(f"  -> Failed to fetch ID {anilist_id} after {max_retries} attempts.")
    return None


# --- END of Updated Function ---


def process_csv():
    """
    Reads the input CSV, fetches all media data, and writes to a new output CSV.
    """
    print(f"Starting to process '{INPUT_FILENAME}'...")

    if not os.path.exists(INPUT_FILENAME):
        print(f"ERROR: Input file not found: '{INPUT_FILENAME}'")
        print("Please make sure the file is in the same directory as the script, or provide the full path.")
        return

    updated_rows = []
    id_column_index = -1

    try:
        with open(INPUT_FILENAME, mode='r', encoding='utf-8') as infile:
            reader = csv.reader(infile, delimiter=',')

            try:
                header = next(reader)
            except StopIteration:
                print("ERROR: The CSV file is empty.")
                return

            try:
                id_column_index = header.index(ANILIST_ID_COLUMN_NAME)
            except ValueError:
                print(f"ERROR: Column '{ANILIST_ID_COLUMN_NAME}' not found in your CSV.")
                print(f"Available columns are: {', '.join(header)}")
                return

            # --- UPDATED: Add all new columns to the header ---
            header.append(POSTER_COLUMN_NAME)
            header.append(EPISODES_COLUMN_NAME)
            header.append(STATUS_COLUMN_NAME)
            header.append(GENRES_COLUMN_NAME)
            header.append(YEAR_COLUMN_NAME)
            header.append(SCORE_COLUMN_NAME)
            updated_rows.append(header)
            # --- End of updated header ---

            # Process each row in the CSV
            for i, row in enumerate(reader):
                if len(row) <= id_column_index:
                    print(f"Skipping row {i + 2}: Malformed row...")
                    row.extend([''] * 6)  # Add 6 empty columns
                    updated_rows.append(row)
                    continue

                anilist_id = row[id_column_index].strip()
                print(f"Processing row {i + 2}: AniList ID = '{anilist_id}'")

                # --- UPDATED: Handle the tuple (or None) response ---
                media_data_tuple = None
                if anilist_id:
                    # Call our new function
                    media_data_tuple = get_media_data(anilist_id)
                    time.sleep(0.7)  # Proactive sleep to avoid 429
                else:
                    print("  -> No ID, skipping API call.")

                # media_data_tuple is either None (on failure) or a tuple of 6 items
                if media_data_tuple:
                    # We have data! Add each item to the row
                    # str(item) handles numbers, (item if item is not None else '') handles Nones
                    row.extend([str(item) if item is not None else '' for item in media_data_tuple])
                else:
                    # No data found or no ID, so add 6 empty columns
                    row.extend([''] * 6)

                updated_rows.append(row)
                # --- End of updated row processing ---


    except FileNotFoundError:
        print(f"ERROR: Could not find file '{INPUT_FILENAME}'")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading the file: {e}")
        return

    # Write the updated data to the new CSV file
    try:
        with open(OUTPUT_FILENAME, mode='w', encoding='utf-8', newline='') as outfile:
            writer = csv.writer(outfile, delimiter=',')
            writer.writerows(updated_rows)

        print("\n-------------------------------------------------")
        print("✅ Success!")
        print(f"All processing is complete. Your new file is saved as '{OUTPUT_FILENAME}'")
        print(f"Total rows processed (including header): {len(updated_rows)}")

    except IOError as e:
        print(f"\nERROR: Could not write to output file '{OUTPUT_FILENAME}'.")
        print(f"Details: {e}")


# --- Run the main function ---
if __name__ == "__main__":
    process_csv()