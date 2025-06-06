import os
import time
import xml.etree.ElementTree as ET
import requests
from dotenv import load_dotenv

load_dotenv()


# Constants
SESSION_XML_PATH = "session.xml"
CHECK_INTERVAL = 10  # Interval to check the webpage in seconds


def read_session_xml_as_json(xml_path):
    """
    Reads the session.xml file and converts its data to JSON.
    :param xml_path: Path to the XML file.
    :return: JSON representation of the XML data.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        session_data = {child.tag: child.text for child in root}
        return session_data
    except Exception as e:
        print(f"Error reading or parsing XML file: {e}")
        return None


def main():
    # Load environment variables
    access_target_url = os.getenv("ACCESS_TARGET_URL")
    api_server_url = os.getenv("API_SERVER_URL")
    api_token = os.getenv("API_TOKEN")

    # Validate environment variables
    if not all([access_target_url, api_server_url, api_token]):
        print("Error: ACCESS_TARGET_URL, API_SERVER_URL, and API_TOKEN environment variables must be set.")
        return

    # Read session.xml and convert to JSON
    session_data = read_session_xml_as_json(SESSION_XML_PATH)
    if not session_data:
        print("Error: Failed to read session.xml or parse it into JSON.")
        return

    session_id = session_data.get("id")

    print(f"Loaded session data: {session_data}")

    while True:
        try:
            # Step 1: Perform a GET request to the ACCESS_TARGET_URL
            print(f"Checking URL: {access_target_url}")
            response = requests.get(access_target_url, timeout=10)
            if response.status_code == 200:
                print(f"Successfully accessed {access_target_url}")

                # Step 2: Send a POST request to the API_SERVER_URL with the session payload
                payload = {"session": session_id}
                headers = {"Authorization": f'Bearer {api_token}'}

                print(f"Sending POST request to {api_server_url}/coin with payload: {payload}")
                post_response = requests.post(f"{api_server_url}/coin", json=payload, headers=headers)

                if post_response.status_code == 200:
                    print("POST request successful!")
                else:
                    print(f"POST request failed with status code {post_response.status_code}: {post_response.text}")
            else:
                print(f"GET request failed with status code {response.status_code}: {response.text}")

        except Exception as e:
            print(f"Error during processing: {e}")

        # Wait for the next interval
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()