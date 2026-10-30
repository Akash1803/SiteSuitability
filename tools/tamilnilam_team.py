"""Copy of the team script D:\\code\\Sipcot_code\\Tamilnilam_code.py - same columns, same output layout - with three changes only:
  1. input / output paths from the command line:  python tools/tamilnilam_team.py <clip_output.xlsx> <output.xlsx>
  2. survey / subdivision numbers keep their text: int(float("2E4")) made subdivision 2E4 into 20000 (invalid on Tamilnilam);
     now only a trailing ".0" is dropped
  3. one kept-alive connection for all rows (same answers, much faster); the CLIP output's own response_status column is
     renamed clip_status so it does not clash with this script's response_status"""
import re  # For text cleaning
import sys

import pandas as pd
import requests
from tqdm import tqdm  # Progress bar

# Input and output file paths
input_file, output_file = sys.argv[1], sys.argv[2]
# New columns to add
columns_to_add = [
    "Patta_Number",
    "Government_Priority",
    "Extent_Hectares",
    "Extent_Ares",
    "Land_Type_English",
    "Poramboke",
    "Cultivable",
    "Owner_Details",  # Combine multiple owners into this column
    "Owner_Update_Dates",  # Add a column for updated dates
    "Owner_Number",
    "remarks",
    "remarks1",  # Total number of owners
    "Response_Status"  # Track API response status
]

# Load input data from Excel file
input_data = pd.read_excel(input_file, dtype={"survey_no": str, "sub_division": str})
input_data = input_data.rename(columns={"response_status": "clip_status"})

session = requests.Session()

# Initialize a list to store processed rows
output_data = []


# Function to clean and format owner details while preserving Tamil text
def clean_owner_name(name):
    # Remove unwanted spaces and any non-printable control characters
    name = re.sub(r"[^\w\s\u0B80-\u0BFF]", "", name)  # Keep Tamil and normal word characters
    name = " ".join(name.split())  # Remove extra spaces
    return name.strip()


# Helper function: keep survey / subdivision text as it is (only a trailing ".0" from Excel is dropped)
def safe_int_str(value):
    if pd.isna(value):
        return ""
    v = str(value).strip()
    return v[:-2] if v.endswith(".0") and v[:-2].isdigit() else v


# Use tqdm to show a progress bar as we iterate over each row
with tqdm(total=input_data.shape[0], desc="Processing Rows") as pbar:
    for index, row in input_data.iterrows():
        district_id = row['district_id']
        taluk_id = row['taluk_id']
        village_id = row['village_id']

        # Safely handle survey_no and sub_division
        survey_no = safe_int_str(row['survey_no'])
        sub_division = safe_int_str(row['sub_division'])

        # Construct the API URL
        api_url = f"https://www.tnagrisnet.tn.gov.in/RES/landdetail/index/{district_id}/{taluk_id}/{village_id}/{survey_no}/{sub_division}"

        # Initialize the new columns with default values
        new_data = {col: None for col in columns_to_add}

        # Add original row data to ensure no rows are skipped
        combined_row = row.to_dict()

        try:
            # Make the API request
            response = session.get(api_url, timeout=60)
            response.raise_for_status()  # Raise an error for bad status codes

            # Parse the response as JSON
            response_json = response.json()

            # Check for specific invalid input message
            if response_json == {"0": "Enter valid Survey No and Subdivision"}:
                new_data["Response_Status"] = "Invalid Survey No or Subdivision"
            else:
                try:
                    # Extract aregData
                    areg_data = response_json.get("aregData", {}).get("areg", {})
                    new_data["Patta_Number"] = areg_data.get("pattaNo", "").strip()
                    new_data["Government_Priority"] = areg_data.get("GovtPri", "").strip()
                    new_data["Extent_Hectares"] = areg_data.get("extHect", "").strip()
                    new_data["Extent_Ares"] = areg_data.get("extAres", "").strip()
                    new_data["Land_Type_English"] = areg_data.get("landTypeEng", "").strip()
                    new_data["Poramboke"] = areg_data.get("Poramboke", "").strip()
                    new_data["Cultivable"] = areg_data.get("cultivable", "").strip()
                    new_data["remarks"] = areg_data.get("remarks", "").strip()
                    new_data["remarks1"] = areg_data.get("remarks1", "").strip()

                    # Extract chittaData
                    chitta_data = response_json.get("chittaData", {}).get("chitta")
                    owner_details = []
                    owner_update_dates = []
                    owner_numbers = []

                    if isinstance(chitta_data, list):
                        # Process multiple owners
                        for owner in chitta_data:
                            owner_name = owner.get("owner", "").strip()
                            cleaned_name = clean_owner_name(owner_name)
                            if cleaned_name:
                                owner_details.append(cleaned_name)
                            owner_update_date = owner.get("updationdt", "").strip()
                            if owner_update_date:
                                owner_update_dates.append(owner_update_date)
                            owner_num = owner.get("ownernum", "").strip()
                            if owner_num:
                                owner_numbers.append(owner_num)
                    elif isinstance(chitta_data, dict):
                        # Process single owner
                        owner_name = chitta_data.get("owner", "").strip()
                        cleaned_name = clean_owner_name(owner_name)
                        if cleaned_name:
                            owner_details.append(cleaned_name)
                        owner_update_date = chitta_data.get("updationdt", "").strip()
                        if owner_update_date:
                            owner_update_dates.append(owner_update_date)
                        owner_num = chitta_data.get("ownernum", "").strip()
                        if owner_num:
                            owner_numbers.append(owner_num)

                    new_data["Owner_Details"] = ", ".join(owner_details) if owner_details else "-"
                    new_data["Owner_Update_Dates"] = ", ".join(owner_update_dates) if owner_update_dates else "-"
                    new_data["Owner_Number"] = len(owner_details) if owner_details else 0
                    new_data["Response_Status"] = "Success"

                except Exception as json_error:
                    print(f"Error parsing JSON for row {index}: {json_error}")
                    new_data["Response_Status"] = "JSON format is not valid"

        except Exception as e:
            print(f"Error processing row {index}: {e}")
            new_data["Response_Status"] = f"Error: {e}"

        # Combine the original row with the new data
        combined_row.update(new_data)
        output_data.append(combined_row)

        # Update the progress bar
        pbar.update(1)

# Convert the list of combined rows to a DataFrame
output_df = pd.DataFrame(output_data)

# Convert all column names to lowercase
output_df.columns = output_df.columns.str.lower()

# Write the enriched data to a new Excel file
output_df.to_excel(output_file, index=False)

print(f"Processed data has been saved to {output_file}")
