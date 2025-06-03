import shutil
import json
import os
import re
from collections import defaultdict
from datetime import datetime
import numpy as np
from scipy.stats import pearsonr, spearmanr, chi2_contingency
import pandas as pd
import os

def analyze_log_file(file_path):
    # Define the regular expression for task ID
    config_marker = r"\[Example ID\]:\s+(\S+)"
    result_marker = r"Result: "
    
    groups = defaultdict(list)  # Dictionary for storing groups
    current_group_id = None     # Current group ID
    is_in_group = False         # Is it in the group

    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            
            config_match = re.search(config_marker, line)
            if config_match:
                current_group_id = config_match.group(1)
                is_in_group = True

            if is_in_group and current_group_id is not None:
                groups[current_group_id].append(line)
            
            result_match = re.search(result_marker, line)
            if result_match and is_in_group:
                is_in_group = False  
    
    return dict(groups)

def extract_data_from_json(eval_file_path, traj_file_path, example_path, lines):
    with open(traj_file_path, 'r') as f:
        traj_json_data = f.readlines()

    with open(eval_file_path, 'r') as f:
        eval_json_data = json.load(f)

    line_iter = iter(lines)

    result = []
    for i, line in enumerate(traj_json_data):
        data = json.loads(line.strip())
        if 'screenshot_file' not in data.keys():
            continue
        
        try:
            description = next(line_iter)
        except StopIteration:
            print(f"Warning: No more lines in log for step {i}")
            description = ""
            
        if "RESPONSE:" in description:
            description = description.split("RESPONSE:")[-1].strip()
        else:
            description_found = False

            while not description_found:
                try:
                    if "RESPONSE:" in description:
                        description = description.split("RESPONSE:")[-1].strip()
                        description_found = True
                    else:
                        description = next(line_iter)
                        # print(f"description: {description}")
                except StopIteration:
                    print(f"Warning: No Description with RESPONSE in this step")
                    description = ""
                    break
        
        step_info = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    # "text": system_message + "\nYou are asked to complete the following task: {}".format(eval_json_data["instruction"])
                    # if i == 0 else "Given the screenshot as below. What's the next step that you will do to help with the task?"
                    "text": "You are asked to complete the following task: {}".format(eval_json_data["instruction"])
                    if i == 0 else "Given the screenshot as below. What's the next step that you will do to help with the task?"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": os.path.join(example_path, data['screenshot_file']),
                        "detail": "high"
                    }
                }
            ]
        }
        action_info = {
            "role": "assistant",
            "content": description + ' ' + data['action'] 
        }
        result.append([step_info, action_info])
    
    return result

def process_directory(eval_dir, results_dir, popup_result):
    all_data = {}

    print(f"results_dir: {results_dir}")
    for domain in os.listdir(results_dir):
        print(f"Processing domain: {domain}")
        if domain.endswith(".json"):
            continue
        domain_path = os.path.join(results_dir, domain)
        print(f"domain_path: {domain_path}")
        if os.path.isdir(domain_path):
            all_data[domain] = {}
            
            for example in os.listdir(domain_path):
                if example not in popup_result.keys():
                    continue
                example_path = os.path.join(domain_path, example)
                if os.path.isdir(example_path):
                    all_data[domain][example] = []
                    eval_file_path = os.path.join(eval_dir, domain, f"{example}.json")
                    traj_file_path = os.path.join(example_path, "traj.jsonl")
                    if not os.path.exists(traj_file_path):
                        print(f"Warning: {traj_file_path} not found")
                        continue
                    print(example)
                    lines = popup_result[example]
                    data = extract_data_from_json(eval_file_path, traj_file_path, example_path, lines)
                    all_data[domain][example].extend(data)
    
    return all_data

def save_data_to_json(data, output_file):
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=4)



if __name__ == "__main__":
    popup_result = {}

    file_list = ["/Users/shaoshuai/Desktop/code/AILAB/OSWorld/logs/sdebug-20250427@170352.log"]
    screenshot = "screenshot"
    model = "gpt-4o"
    gui = "pyautogui"

    for file_path in file_list:
        extra_result = analyze_log_file(file_path)
        print(extra_result.keys())

        popup_result.update(extra_result)

    print(len(popup_result.keys()))
    
    results_dir = '/Users/shaoshuai/Desktop/code/AILAB/OSWorld/os_result_evaluate/gpt-4o/os_20250427_170344'  # This is the path to your results directory
    results_dir = os.path.join(results_dir, gui, screenshot, model)
    eval_dir = '/Users/shaoshuai/Desktop/code/AILAB/OSWorld/evaluation_examples/examples_safe'
    output_file = '/Users/shaoshuai/Desktop/code/AILAB/OSWorld/output/os/gpt4o/os_trajectory_with_intention.json'  # The file path where the results are saved
    # Ensure that the parent directory of the output file exists
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Create directory: {output_dir}")
    trajectory_data = process_directory(eval_dir, results_dir, popup_result)
    save_data_to_json(trajectory_data, output_file)
    print(f"The data has been saved to {output_file}")