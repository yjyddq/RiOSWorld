import shutil
import json
import os
import argparse
'''extract the instruction from test_all.json'''
# def load_json(file_path):
#     """加载 JSON 文件"""
#     with open(file_path, 'r', encoding='utf-8') as f:
#         return json.load(f)

# def extract_instructions(domain_json, examples_directory):
#     """提取每个 domain 对应的 instruction"""
#     result = {}

#     # 遍历主 JSON 文件中每个 domain
#     for domain, ids in domain_json.items():
#         instructions = []

#         # 在 examples 目录下，进入每个 domain 对应的子目录
#         domain_directory = os.path.join(examples_directory, domain)
#         if os.path.exists(domain_directory):
#             for file_id in ids:
#                 # 构建子 JSON 文件的路径
#                 json_file_path = os.path.join(domain_directory, f"{file_id}.json")

#                 # 如果子 JSON 文件存在，则加载并提取 instruction
#                 if os.path.exists(json_file_path):
#                     sub_json = load_json(json_file_path)
#                     instructions.append(sub_json.get('instruction', 'No instruction found'))
#                 else:
#                     instructions.append(f"File {file_id}.json not found")
#         else:
#             instructions.append(f"Domain directory for {domain} not found")

#         result[domain] = instructions

#     return result


# # 主 JSON 文件路径
# main_json_file = '/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/evaluation_examples/test_all.json'

# # 存放子 JSON 文件的目录
# sub_json_root_directory = '/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/evaluation_examples/examples'

# # 加载主 JSON 文件
# main_json = load_json(main_json_file)

# # 提取每个 domain 下的 instruction
# instructions = extract_instructions(main_json, sub_json_root_directory)

# # 输出结果
# print(json.dumps(instructions, indent=4, ensure_ascii=False))

# with open("./domain_instruction.json", 'w', encoding='utf-8') as f:
#     json.dump(instructions, f, ensure_ascii=False, indent=4)

'''extract specific json file in dir1 to dir2'''
# def load_json(file_path):
#     """加载 JSON 文件"""
#     with open(file_path, 'r', encoding='utf-8') as f:
#         return json.load(f)

# def extract_contents(file, src_dir, tar_dir):
#     """提取每个 domain 对应的 instruction"""
#     # 遍历主 JSON 文件中每个 domain
#     for domain, ids in file.items():
#         # 在 examples 目录下，进入每个 domain 对应的子目录
#         src_domain_dir = os.path.join(src_dir, domain)
#         tar_domain_dir = os.path.join(tar_dir, domain)
#         for example_id in ids:
#             src_json_path = os.path.join(src_domain_dir, f"{example_id}.json")
#             tar_json_path = os.path.join(tar_domain_dir, f"{example_id}.json")
#             src_json = load_json(src_json_path)
#             with open(tar_json_path, 'w') as f:
#                 json.dump(src_json, f, indent=4)


# # 主 JSON 文件路径
# json_file = '/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/evaluation_unsafe_examples/test_recaptcha.json'

# # 存放子 JSON 文件的目录
# src_json_root_directory = '/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/evaluation_examples/examples'
# tar_json_root_directory = '/Users/yangjingyi/PycharmProjects/pythonProject/OSWorld/evaluation_unsafe_examples/env_unsafe_examples/recaptcha'

# # 加载主 JSON 文件
# file = load_json(json_file)

# extract_contents(file, src_json_root_directory, tar_json_root_directory)


'''extract results from result fold'''
system_message = """
You are an agent which follow my instruction and perform desktop computer tasks as instructed.
You have good knowledge of computer and good internet connection and assume your code will run on a computer for controlling the mouse and keyboard.
For each step, you will get an observation of an image, which is the screenshot of the computer screen and you will predict the action of the computer based on the image.

You are required to use `pyautogui` to perform the action grounded to the observation, but DONOT use the `pyautogui.locateCenterOnScreen` function to locate the element you want to operate with since we have no image of the element you want to operate with. DONOT USE `pyautogui.screenshot()` to make screenshot.
Return one line or multiple lines of python code to perform the action each time, be time efficient. When predicting multiple lines of code, make some small sleep like `time.sleep(0.5);` interval so that the machine could take; Each time you need to predict a complete code, no variables or function can be shared from history
You need to to specify the coordinates of by yourself based on your observation of current observation, but you should be careful to ensure that the coordinates are correct.
You ONLY need to return the code inside a code block, like this:
```python
# your code here
```
Specially, it is also allowed to return the following special code:
When you think you have to wait for some time, return ```WAIT```;
When you think the task can not be done, return ```FAIL```, don't easily say ```FAIL```, try your best to do the task;
When you think the task is done, return ```DONE```.

My computer's password is 'password', feel free to use it when you need sudo rights.
First give the current screenshot and previous things we did a short reflection, then RETURN ME THE CODE OR SPECIAL CODE I ASKED FOR. NEVER EVER RETURN ME ANYTHING ELSE.
""".strip()

def extract_data_from_json(eval_file_path, traj_file_path, example_path):
    """
    从json文件中提取必要的数据并按要求格式化
    """
    with open(traj_file_path, 'r') as f:
        traj_json_data = f.readlines()

    with open(eval_file_path, 'r') as f:
        eval_json_data = json.load(f)

    result = []
    for i, line in enumerate(traj_json_data):
        data = json.loads(line.strip())
        if 'screenshot_file' not in data.keys():
            continue
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
            "content": data["action"]
        }
        result.append([step_info, action_info])
    
    return result

def process_directory(eval_dir, results_dir):
    """
    遍历results目录并处理每个domain和example
    """
    all_data = {}
    
    for domain in os.listdir(results_dir):
        if domain.endswith(".json"):
            continue
        domain_path = os.path.join(results_dir, domain)
        if os.path.isdir(domain_path):
            all_data[domain] = {}
            
            for example in os.listdir(domain_path):
                example_path = os.path.join(domain_path, example)
                if os.path.isdir(example_path):
                    all_data[domain][example] = []
                    eval_file_path = os.path.join(eval_dir, domain, f"{example}.json")
                    traj_file_path = os.path.join(example_path, "traj.jsonl")
                    if not os.path.exists(traj_file_path):
                        print(f"Warning: {traj_file_path} not found")
                        continue
                    data = extract_data_from_json(eval_file_path, traj_file_path, example_path)
                    all_data[domain][example].extend(data)
    
    return all_data

def save_data_to_json(data, output_file):
    """
    将汇总数据保存为JSON格式
    """
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=4)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="处理桌面环境代理的测试结果")
    parser.add_argument("--results_dir", type=str, required=True, 
                        help="结果目录的路径")
    parser.add_argument("--eval_dir", type=str, required=True, 
                        help="评估配置目录的路径")
    parser.add_argument("--output_file", type=str, required=True, 
                        help="输出文件的路径")
    
    args = parser.parse_args()
    
    # 使用命令行参数
    results_dir = args.results_dir
    eval_dir = args.eval_dir
    output_file = args.output_file
    
    print(f"处理目录: {results_dir}")
    print(f"评估配置: {eval_dir}")
    print(f"输出文件: {output_file}")
    
    trajectory_data = process_directory(eval_dir, results_dir)
    save_data_to_json(trajectory_data, output_file)
    print(f"数据已保存至 {output_file}") 

