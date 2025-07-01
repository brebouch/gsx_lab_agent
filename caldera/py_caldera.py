###################
#
# Python Caldera Client
#
#
#
######################
import json
import os

import dotenv
import requests

dotenv.load_dotenv()

caldera_server = os.environ.get('CALDERA_SERVER')

base_url = f'{caldera_server}:8888/api/v2'

waiting_responses = []


STATUS_CODES = {
    0: 'Fail',
    1: 'Pass',
    124: 'Pass'
}


def get_header():
    return {
        'KEY': os.environ.get('CALDERA_API_TOKEN'),
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }


def rest_get(endpoint, **kwargs):
    # Construct the base URL with the endpoint
    url = f'{base_url}/{endpoint}'

    # Check if there are any keyword arguments to add as query parameters
    if kwargs:
        # Append query parameters to the URL
        query_params = '&'.join([f"{key}={value}" for key, value in kwargs.items()])
        url = f"{url}?{query_params}"

    # Make the GET request with the constructed URL
    return requests.get(url, headers=get_header(), verify=False)


def rest_delete(endpoint, **kwargs):
    # Construct the base URL with the endpoint
    url = f'{base_url}/{endpoint}'

    # Append query parameters if any
    if kwargs:
        query_params = '&'.join([f"{key}={value}" for key, value in kwargs.items()])
        url = f"{url}?{query_params}"

    # Make the DELETE request with the constructed URL
    return requests.delete(url, headers=get_header(), verify=False)


def rest_head(endpoint, **kwargs):
    # Construct the base URL with the endpoint
    url = f'{base_url}/{endpoint}'

    # Check if there are any keyword arguments to add as query parameters
    if kwargs:
        # Append query parameters to the URL
        query_params = '&'.join([f"{key}={value}" for key, value in kwargs.items()])
        url = f"{url}?{query_params}"

    # Make the GET request with the constructed URL
    return requests.head(url, headers=get_header(), verify=False)


def rest_post(endpoint, data, **kwargs):
    # Construct the base URL with the endpoint
    url = f'{base_url}/{endpoint}'

    # Append query parameters if any
    if kwargs:
        query_params = '&'.join([f"{key}={value}" for key, value in kwargs.items()])
        url = f"{url}?{query_params}"

    # Ensure data is a dictionary
    if not isinstance(data, dict):
        data = {}

    # Make the POST request with the constructed URL and data
    return requests.post(url, json=data, headers=get_header(), verify=False)


def rest_put(endpoint, data, **kwargs):
    # Construct the base URL with the endpoint
    url = f'{base_url}/{endpoint}'

    # Append query parameters if any
    if kwargs:
        query_params = '&'.join([f"{key}={value}" for key, value in kwargs.items()])
        url = f"{url}?{query_params}"

    # Ensure data is a dictionary
    if not isinstance(data, dict):
        data = {}

    # Make the PUT request with the constructed URL and data
    return requests.put(url, json=data, headers=get_header(), verify=False)


def rest_patch(endpoint, data, **kwargs):
    # Construct the base URL with the endpoint
    url = f'{base_url}/{endpoint}'

    # Append query parameters if any
    if kwargs:
        query_params = '&'.join([f"{key}={value}" for key, value in kwargs.items()])
        url = f"{url}?{query_params}"

    # Ensure data is a dictionary
    if not isinstance(data, dict):
        data = {}

    # Make the PUT request with the constructed URL and data
    return requests.patch(url, json=data, headers=get_header(), verify=False)


def run_operation(name, adversary_id, group='', auto_close='true'):
    operation = {
        'name': name,
        'adversary': {
            'adversary_id': adversary_id
        },
        'group': group,
        'auto_close': auto_close
    }
    op = rest_post('operations', operation)
    if op:
        waiting_responses.append(op)
        with open('new_operation.json', 'w') as json_writer:
            json_writer.write(json.dumps(op))
    for w in waiting_responses:
        report = get_operation_report(w['id'], True)
        print('hi')



def get_operation_report(operation_id, enable_agent_output=False):
    data = {
        'enable_agent_output': enable_agent_output
    }
    return rest_post(f'operations/{operation_id}/report', data=data)


def get_operation_list():
    return rest_get(f'operations')


def get_steps_key(report_json):
    if 'steps' in report_json.keys():
        if isinstance(report_json['steps'], dict):
            return report_json['steps'].keys()


def normalize_report_json(report_json):
    agents = get_steps_key(report_json)
    result = {}
    success = 0
    failed = 0
    for a in agents:
        for s in report_json['steps'][a]['steps']:
            if a not in result.keys():
                result.update({a: []})
            if s['status'] == 0:
                success += 1
            else:
                failed += 1

            result[a].append({
                'Status': STATUS_CODES[s['status']],
                'Task': s['name'],
                'Description': s['description']
            })
    if failed == 0:
        successful = 100
    else:
        successful = float(success / failed)
    return result, successful



def check_operation_run(operation_id, run_type):
    checkup = rest_get(f'operations/{operation_id}')
    if checkup:
        if checkup['state'] != 'running':
            response_index = 0
            for i in range(len(waiting_responses)):
                if waiting_responses[i]['id'] == operation_id:
                    response_index = i
                    break
            if response_index:
                del waiting_responses[response_index]
            if checkup['state'] == 'finished':
                # Add reference to completed operation but not in error state
                report = get_operation_report(operation_id, True)
                with open('complete_operation.json', 'w') as json_writer:
                    json_writer.write(json.dumps(report))
    return checkup



if __name__ == '__main__':
    check_operation_run('14860721-76f7-44d9-a86d-5be71f9c6071')
    run_operation('TestOp1', '89d971f4-fab8-4c15-bc8f-d64b26728c81')
