import pandas as pd
import os

# --- Configuration ---
# 1. Set the path to your big CSV file.
INPUT_CSV_PATH = 'anilist_data_with_img_status.csv'

# 2. Set the path to your local image folder.
IMAGE_FOLDER_PATH = 'img/tmdbimg'

# 3. Set the name for the new, updated CSV file.
OUTPUT_CSV_PATH = 'your_media_list_updated.csv'


# --- End Configuration ---


def find_local_tmdb_image(poster_url):
    """
    Checks a 'poster_url' to see if it's a TMDB link.
    If it is, it checks if the corresponding image file exists locally.
    Returns the filename if found, otherwise returns an empty string.
    """
    # Ensure the URL is a string (handles empty/NaN values)
    url = str(poster_url)

    # 1. Check if it's a TMDB URL
    if 'image.tmdb.org' not in url:
        return ''  # Not a TMDB link, skip

    try:
        # 2. Extract the filename from the URL
        image_filename = os.path.basename(url)

        # Handle cases where basename might be empty (e.g., URL ends with '/')
        if not image_filename:
            return ''

        # 3. Create the full path to the local image
        full_image_path = os.path.join(IMAGE_FOLDER_PATH, image_filename)

        # 4. Check if the file exists
        if os.path.exists(full_image_path):
            # 5. If it exists, return the filename
            return image_filename
        else:
            # File not found in the local folder
            return ''

    except Exception as e:
        # Catch any errors during path processing
        print(f"Error processing URL '{url}': {e}")
        return ''


# --- Main Script ---

print("Starting script...")

# Check if the image folder exists
if not os.path.isdir(IMAGE_FOLDER_PATH):
    print(f"Error: The image folder '{IMAGE_FOLDER_PATH}' was not found.")
    print("Please check the 'IMAGE_FOLDER_PATH' variable in the script.")
else:
    try:
        # Read the main CSV file
        print(f"Loading {INPUT_CSV_PATH}...")
        df = pd.read_csv(INPUT_CSV_PATH)

        # Check if 'poster_url' column exists
        if 'poster_url' not in df.columns:
            print(f"Error: The CSV file does not have a 'poster_url' column.")
        else:
            # Create the new 'tmdb_img_filename' column
            # The .apply() method runs our function for every row in the 'poster_url' column
            print("Processing rows and checking for local images...")
            df['tmdb_img_filename'] = df['poster_url'].apply(find_local_tmdb_image)

            # Save the modified DataFrame to a new CSV file
            df.to_csv(OUTPUT_CSV_PATH, index=False)

            print(f"\nProcessing complete!")
            print(f"Updated data saved to {OUTPUT_CSV_PATH}")

    except FileNotFoundError:
        print(f"Error: Input file not found at '{INPUT_CSV_PATH}'")
        print("Please check the 'INPUT_CSV_PATH' variable in the script.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")