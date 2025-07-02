import os
import time
import signal
import sys
import xml.etree.ElementTree as ET
import requests
import logging
from dotenv import load_dotenv
from caldera.py_caldera import run_operation, check_operation_run

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

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
        logger.error(f"Error reading or parsing XML file: {e}")
        return None


def retry_run_operation(operation_name, adversary, group, retries=3, delay=5):
    """
    Retry mechanism for running a Caldera operation.
    :param operation_name: Name of the operation to run.
    :param adversary: Adversary ID.
    :param group: Group ID.
    :param retries: Number of retry attempts.
    :param delay: Delay between retry attempts in seconds.
    :return: Response from the Caldera operation or None if all retries fail.
    """
    for attempt in range(retries):
        try:
            response = run_operation(operation_name, adversary, group)
            if response:
                return response
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
        time.sleep(delay)
    return None


def post_caldera_status(api_server_url, api_token, session_id, operation_name, operation_id, status):
    """
    Posts the operation status to the /caldera endpoint.
    :param api_server_url: API server URL.
    :param api_token: Bearer token for authentication.
    :param session_id: Session ID associated with the operation.
    :param operation_name: Name of the operation.
    :param operation_id: ID of the operation.
    :param status: Current status of the operation.
    """
    headers = {"Authorization": f'Bearer {api_token}'}
    payload = {
        "session_id": session_id,
        "operation_name": operation_name,
        "operation_id": operation_id,
        "status": status
    }
    try:
        logger.info(f"Posting status update to {api_server_url}/caldera with payload: {payload}")
        response = requests.post(f"{api_server_url}/caldera", json=payload, headers=headers)
        if response.status_code == 200:
            logger.info(f"Successfully updated operation '{operation_name}' with status '{status}'.")
        else:
            logger.error(f"Failed to update operation '{operation_name}' with status '{status}'. Response: {response.text}")
    except Exception as e:
        logger.error(f"Error posting operation status for '{operation_name}': {e}")


def signal_handler(sig, frame):
    """
    Graceful shutdown on SIGINT.
    """
    logger.info("Graceful shutdown initiated.")
    sys.exit(0)


def main():
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Load environment variables
    access_target_url = os.getenv("ACCESS_TARGET_URL")
    api_server_url = os.getenv("API_SERVER_URL")
    api_token = os.getenv("API_TOKEN")

    # Validate environment variables
    if not all([access_target_url, api_server_url, api_token]):
        logger.error("ACCESS_TARGET_URL, API_SERVER_URL, and API_TOKEN environment variables must be set.")
        return

    # Read session.xml and convert to JSON
    session_data = read_session_xml_as_json(SESSION_XML_PATH)
    if not session_data:
        logger.error("Failed to read session.xml or parse it into JSON.")
        return

    session_id = session_data.get("id")
    logger.info(f"Loaded session data: {session_data}")

    while True:
        try:
            # Step 1: Perform a GET request to the ACCESS_TARGET_URL
            logger.info(f"Checking URL: {access_target_url}")
            response = requests.get(access_target_url, timeout=10)
            if response.status_code == 200:
                logger.info(f"Successfully accessed {access_target_url}")

                # Step 2: Send a POST request to the API_SERVER_URL with the session payload
                payload = {"session": session_id}
                headers = {"Authorization": f'Bearer {api_token}'}

                logger.info(f"Sending POST request to {api_server_url}/coin with payload: {payload}")
                post_response = requests.post(f"{api_server_url}/coin", json=payload, headers=headers)

                if post_response.status_code == 200:
                    response_data = post_response.json()
                    logger.info("POST request successful!")

                    # Step 3: Handle actions in the response
                    if 'actions' in response_data.keys() and isinstance(response_data['actions'], list):
                        for a in response_data['actions']:
                            if 'service' not in a.keys():
                                continue
                            if a['service'] == 'caldera' and a['task'] == 'run_operation':
                                adversary = a.get('adversary')
                                group = a.get('group', '')
                                operation_name = a.get('operation_name')

                                if not all([adversary, operation_name]):
                                    logger.warning(f"Invalid parameters in action: {a}")
                                    continue

                                try:
                                    response = retry_run_operation(operation_name, adversary, group)
                                    if response:
                                        operation_id = response.get('id')
                                        logger.info(f"Operation '{operation_name}' started with ID: {operation_id}")
                                        post_caldera_status(api_server_url, api_token, session_id, operation_name, operation_id, "started")
                                    else:
                                        logger.error(f"Failed to start operation '{operation_name}'.")
                                except Exception as e:
                                    logger.error(f"Error running operation '{operation_name}': {e}")
                            elif a['service'] == 'caldera' and a['task'] == 'check_operation':
                                operation_id = a.get('operation_id')

                                if not all([operation_id]):
                                    logger.warning(f"Invalid parameters in action: {a}")
                                    continue

                                try:
                                    response = check_operation_run(operation_id)
                                    if response:
                                        status = response.get('status')
                                        logger.info(f"Operation '{operation_id}' checked with current status: {status}")
                                        post_caldera_status(api_server_url, api_token, session_id, a.get('operation_name'), operation_id, status)
                                    else:
                                        logger.error(f"Failed to check operation '{operation_id}'.")
                                except Exception as e:
                                    logger.error(f"Error checking operation '{operation_id}': {e}")

                else:
                    logger.error(f"POST request failed with status code {post_response.status_code}: {post_response.text}")
            else:
                logger.error(f"GET request failed with status code {response.status_code}: {response.text}")

        except Exception as e:
            logger.error(f"Error during processing: {e}")

        # Wait for the next interval
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()