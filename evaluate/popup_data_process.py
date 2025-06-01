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

def count_actions_and_attacks(log_lines, random_tgt=False):
    action_count = 0
    attack_count = 0
    successful_attack_count = 0
    pass_count = 0
    fail_count = 0

    # Define patterns for actions, attacks, and results
    action_pattern = r"[0mRESPONSE:"
    attack_pattern = r"Attack result: (True|False)"
    result_pattern = r"\[Result\] \((PASS|FAIL)\)"

    for line in log_lines:
        if "[0mRESPONSE:" in line:
            print(line.split("RESPONSE:  ")[-1]+'\n')
    return {
        "action_count": action_count,
        "attack_count": attack_count,
        "successful_attack_count": successful_attack_count,
        "pass": pass_count
    }

# def analyze_log_file(file_path):
#     # Define regex patterns for time formats and group markers
#     time_format_1 = r"(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})"
#     time_format_2 = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})"
#     # config_marker = r"\[Example ID\]:\s([0-9a-fA-F\-]+)"
#     config_marker = r"\[Example ID\]:\s+(\S+)"
#     result_marker = r"Result: "
    
#     log_lines = []

#     # Open the file and read each line
#     with open(file_path, 'r') as file:
#         for line in file:
#             # Strip the line of extra spaces
#             line = line.strip()
#             # if "6766f2b8-8a72-417f-a9e5-56fcaa735837" in line:
#             #     print(True)
#             # Extract and normalize time for sorting
#             time_match = re.search(time_format_1, line) or re.search(time_format_2, line)
#             if time_match:
#                 time_str = time_match.group(1)
#                 try:
#                     if '-' in time_str and ':' in time_str:
#                         timestamp = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S,%f")
#                     else:
#                         timestamp = datetime.strptime(time_str, "%Y-%m-%d-%H-%M-%S")
#                     log_lines.append((timestamp, line))
#                 except ValueError:
#                     continue  # Skip lines that don't match any time format

#     # Sort lines by timestamp
#     log_lines.sort(key=lambda x: x[0])

#     groups = defaultdict(list)  # Dictionary to store the groups of lines
#     current_group_id = None     # Track the current group
#     is_in_group = False         # Track if we're inside a group

#     current_group = []
#     # Process each line after sorting
#     for _, line in log_lines:
#         # Check if the line starts a new group
#         config_match = re.search(config_marker, line)
#         if config_match:
#             current_group_id = config_match.group(1)
#             is_in_group = True
#             current_group = []

#         # If inside a group, add the line to the appropriate group
#         if is_in_group and current_group_id is not None:
#             current_group.append(line)

#         # Check if the line ends the current group
#         result_match = re.search(result_marker, line)
#         if result_match:
#             is_in_group = False  # End the group immediately after this line
#             groups[current_group_id] = current_group
#             current_group = []

#     return dict(groups)

def analyze_log_file(file_path):
    # 定义任务ID的正则表达式
    config_marker = r"\[Example ID\]:\s+(\S+)"
    result_marker = r"Result: "
    
    groups = defaultdict(list)  # 存储分组的字典
    current_group_id = None     # 当前分组ID
    is_in_group = False         # 是否在分组中

    # 打开文件并读取每一行
    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            
            # 检查是否是新任务的开始
            config_match = re.search(config_marker, line)
            if config_match:
                current_group_id = config_match.group(1)
                is_in_group = True
            
            # 如果在分组中，添加行到对应分组
            if is_in_group and current_group_id is not None:
                groups[current_group_id].append(line)
            
            # 检查是否是当前任务的结束
            result_match = re.search(result_marker, line)
            if result_match and is_in_group:
                is_in_group = False  # 结束当前分组
    
    return dict(groups)

def extract_data_from_json(eval_file_path, traj_file_path, example_path, lines):
    """
    从json文件中提取必要的数据并按要求格式化
    """
    # print(f"len(lines): {len(lines)}")
    with open(traj_file_path, 'r') as f:
        traj_json_data = f.readlines()

    with open(eval_file_path, 'r') as f:
        eval_json_data = json.load(f)

    # print(group_id, lines)
    # for group_id, lines in popup_result.items():
    #     if "ee9a" in group_id:
    #         continue
    #     for line in lines:
    #         if "[0mRESPONSE:" in line:
    #             print(line.split("RESPONSE:  ")[-1]+'\n')
    line_iter = iter(lines)
    # print(f"line_iter: {line_iter}")

    result = []
    for i, line in enumerate(traj_json_data):
        data = json.loads(line.strip())
        # print(f"data: {data}")
        if 'screenshot_file' not in data.keys():
            continue
        # print(f"num_iters: {i}")
        
        # 尝试获取下一行，添加错误处理
        try:
            description = next(line_iter)
        except StopIteration:
            print(f"Warning: No more lines in log for step {i}")
            description = ""
            
        # 更灵活的匹配方式
        if "RESPONSE:" in description:  # 移除了[0m部分
            description = description.split("RESPONSE:")[-1].strip()
        else:
            description_found = False
            # 尝试查找包含RESPONSE的行
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
        
            # print(i)
            # print(description+" "+data['action'])
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
    """
    遍历results目录并处理每个domain和example
    """
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
                # print(f"popup_result: {popup_result.keys()}")
                example_path = os.path.join(domain_path, example)
                # print(f"example_path: {example_path}")
                if os.path.isdir(example_path):
                    all_data[domain][example] = []
                    eval_file_path = os.path.join(eval_dir, domain, f"{example}.json")
                    traj_file_path = os.path.join(example_path, "traj.jsonl")
                    if not os.path.exists(traj_file_path):
                        print(f"Warning: {traj_file_path} not found")
                        continue
                    print(example)
                    # if example == "6766f2b8-8a72-417f-a9e5-56fcaa735837":
                    #     continue
                    lines = popup_result[example]
                    data = extract_data_from_json(eval_file_path, traj_file_path, example_path, lines)
                    all_data[domain][example].extend(data)
    
    return all_data

def save_data_to_json(data, output_file):
    """
    将汇总数据保存为JSON格式
    """
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=4)



if __name__ == "__main__":
    popup_result = {}

    file_list = ["/Users/shaoshuai/Desktop/code/AILAB/OSWorld/logs/sdebug-20250427@170352.log"]
    screenshot = "screenshot_a11y_tree"
    model = "gpt-4o"
    gui = "pyautogui"
    # /Users/shaoshuai/Desktop/code/AILAB/OSWorld/os_result_evaluate/gpt-4.1/os_20250429_004249/pyautogui/screenshot_a11y_tree/gpt-4.1/os/os_05/result_1.txt

    for file_path in file_list:
        extra_result = analyze_log_file(file_path)
        print(extra_result.keys())

        popup_result.update(extra_result)

    print(len(popup_result.keys()))
    
    results_dir = '/Users/shaoshuai/Desktop/code/AILAB/OSWorld/os_result_evaluate/gpt-4o/os_20250427_170344'  # 这里是你的results目录的路径
    results_dir = os.path.join(results_dir, gui, screenshot, model)
    eval_dir = '/Users/shaoshuai/Desktop/code/AILAB/OSWorld/evaluation_examples/examples_safe'
    output_file = '/Users/shaoshuai/Desktop/code/AILAB/OSWorld/output/os/gpt4o/os_trajectory_with_intention.json'  # 结果保存的文件路径
    # 确保output_file的上级目录存在
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"创建目录: {output_dir}")
    trajectory_data = process_directory(eval_dir, results_dir, popup_result)
    save_data_to_json(trajectory_data, output_file)
    print(f"数据已保存至 {output_file}")

    # 定义输入文件路径和输出文件夹路径
    # test_all_file = '/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/evaluation_examples/test_all.json'
    # examples_folder = '/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/evaluation_examples/examples'
    # assessment_file = '/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/test/results/Qwen2.5-VL-72B-Instruct/step_wosp_gpt_4o_mini_assessment.json'

    # # 读取 test_all.json 文件
    # with open(test_all_file, 'r', encoding='utf-8') as f:
    #     test_all_data = json.load(f)
    
    # # 读取 assessment.json 文件
    # with open(assessment_file, 'r', encoding='utf-8') as f:
    #     assessment_data = json.load(f)

    # cnt = 0
    # # 遍历 test_all.json 中的每个 domain
    # for domain, example_ids in test_all_data.items():
    #     domain_folder = os.path.join(examples_folder, domain)
        
    #     for example_id in example_ids:
    #         # 查找 example_id 对应的 JSON 文件
    #         example_file_path = os.path.join(domain_folder, f"{example_id}.json")
    #         items = assessment_data[domain][example_id]

    #         for item in items:
    #             if item[2]["safe_flag"] == "unsafe":
    #                 with open(example_file_path, 'r', encoding='utf-8') as f:
    #                     example_data = json.load(f)
    #                 cnt += 1
    #                 break
            
    #         output_folder = domain_folder.replace("examples", "unsafe_examples")
    #         if not os.path.exists(output_folder):
    #             os.makedirs(output_folder)
    #         output_file_path = example_file_path.replace("examples", "unsafe_examples")
    #         with open(output_file_path, 'w') as f:
    #             json.dump(example_data, f, indent=4)

    # print(f"Unsafe Num: {cnt}")
    # print("Extract Completed! unsafe examples save to safety_examples folder")


    '''delete the examples that are not in test_user.json'''
    # # 扫描目标目录
    # target_dir = "/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/evaluation_unsafe_examples/user_unsafe_examples"

    # # 读取test_user.json文件
    # with open('/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/test/examples/test_user.json', 'r') as f:
    #     # 跳过第一行注释
    #     content = f.read()
    #     content = content[content.find('{'):]  # 从第一个{开始解析
    #     test_user_data = json.loads(content)

    # # 收集所有的example_id
    # valid_example_ids = []
    # for domain, examples in test_user_data.items():
    #     for example in examples:
    #         for example_id in example.keys():
    #             valid_example_ids.append(os.path.join(os.path.join(target_dir, domain), example_id+'.json'))

    # # print(len(valid_example_ids))
    # print(f"Found {len(valid_example_ids)} valid example IDs in test_user.json")
    

    # deleted_count = 0
    # num_count = 0
    # for dirname in os.listdir(target_dir):
    #     dir_path = os.path.join(target_dir, dirname)
    #     for filename in os.listdir(dir_path):
    #         file_path = os.path.join(dir_path, filename)
    #         num_count += 1
    #         # 如果文件名（作为example_id）不在有效列表中，删除该文件
    #         if file_path not in valid_example_ids:
    #             print(f"Deleting {file_path}")
    #             os.remove(file_path)
    #             deleted_count += 1
    # print(f"Total {num_count} files that were under target_dir")
    # print(f"Deleted {deleted_count} files that were not in test_user.json")

    # new_num_count = 0
    # for dirname in os.listdir(target_dir):
    #     dir_path = os.path.join(target_dir, dirname)
    #     for filename in os.listdir(dir_path):
    #         file_path = os.path.join(dir_path, filename)
    #         new_num_count += 1
    # print(f"Now Total {new_num_count} files that were under target_dir")

# /Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/evaluation_unsafe_examples/user_unsafe_examples/gimp/2a729ded-3296-423d-aec4-7dd55ed5fbb3.json

# results
# - domain1
#     - example1
#         - 1.png
#         - 2.png
#         ...
#         - traj.json
#     - example2
#         - 1.png
#         - 2.png
#         ...
#         - traj.json
#     - example3
#     ...
# - domain2
#     - example1
#     - example2
#     - example3
#     ...
# - domain3
#     ...
# ...


# {
#     "chrome": {
#         "7b6c7e24-c58a-49fc-a5bb-d57b80e5b4c3": [
#             [
#                 {
#                     "role": "user",
#                     "content": [
#                     {
#                         "type": "text",
#                         "text": "Given the screenshot as below. What's the next step that you will do to help with the task?"
#                     },
#                     {
#                         "type": "image_url",
#                         "image_url": {
#                             "url": "image_path",
#                             "detail": "high"
#                         }
#                     }
#                     ]
#                 },
#                 {
#                     "role": "assistant", 
#                     "content": "pyautogui.click(572, 650)\ntime.sleep(0.5)"
#                 },
#             ],
#         ],
#     },

#     "domain": {
#         "example_id": [
#             [
#                 {
#                     "role": "user",
#                     "content": [
#                     {
#                         "type": "text",
#                         "text": "instruction"
#                     },
#                     {
#                         "type": "image_url",
#                         "image_url": {
#                             "url": "image_path",
#                             "detail": "high"
#                         }
#                     }
#                     ]
#                 }
#             ]
#         ],
#     }
# }