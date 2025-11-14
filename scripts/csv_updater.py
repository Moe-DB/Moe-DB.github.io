import pandas as pd

old_file = "anilist_data_with_img_status.csv"
new_file = "new_data.csv"
output_file = "anilist_data_with_img_status_updated.csv"

old_df = pd.read_csv(old_file)
new_df = pd.read_csv(new_file)

old_df["Anime Title"] = old_df["Anime Title"].astype(str).str.strip()
new_df["Anime Title"] = new_df["Anime Title"].astype(str).str.strip()

update_cols = [
    "Avg. Words/Episode",
    "Unique Words",
    "Kanji Difficulty (1-100)",
    "Vocab Difficulty (1-100)",
    "Overall Difficulty (1-100)",
    "Vocab Density (%)"
]

updated_df = old_df.copy()

for _, row in new_df.iterrows():
    title = row["Anime Title"]

    if title in updated_df["Anime Title"].values:
        for col in update_cols:
            updated_df.loc[updated_df["Anime Title"] == title, col] = row[col]

    else:
        # Create a row with the exact same columns/dtypes
        new_row = {col: None for col in updated_df.columns}

        # Copy values from new CSV wherever possible
        for col in new_df.columns:
            if col in new_row:
                new_row[col] = row[col]

        # Make df with correct dtypes to avoid warnings
        new_row_df = pd.DataFrame([new_row]).astype(updated_df.dtypes.to_dict())

        updated_df = pd.concat([updated_df, new_row_df], ignore_index=True)

updated_df.to_csv(output_file, index=False)

print("Update complete! Saved as:", output_file)
