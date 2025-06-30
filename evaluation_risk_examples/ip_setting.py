import shutil
import json
import os

def load_json(file_path):
    """Load JSON file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def change_ip(file, dir, new_ip, domain=None):
    if domain is None:
        for domain, ids in file.items():
            domain_dir = os.path.join(dir, domain)
            for example_id in ids:
                json_path = os.path.join(domain_dir, f"{example_id}.json")
                json_content = load_json(json_path)
                json_content["config"][2]["parameters"]["urls_to_open"][0] = new_ip + ":" + json_content["config"][2]["parameters"]["urls_to_open"][0].split(":")[-1]
                with open(json_path, 'w') as f:
                    json.dump(json_content, f, indent=4)
    else:
        for dom, ids in file.items():
            if dom != domain:
                continue
            domain_dir = os.path.join(dir, domain)
            for example_id in ids:
                json_path = os.path.join(domain_dir, f"{example_id}.json")
                json_content = load_json(json_path)
                json_content["config"][2]["parameters"]["urls_to_open"][0] = new_ip + ":" + json_content["config"][2]["parameters"]["urls_to_open"][0].split(":")[-1]
                json_content["risk_evaluator"]["expected"][0]["rules"]["url"] = new_ip.split("://")[-1]

                with open(json_path, 'w') as f:
                    json.dump(json_content, f, indent=4)
        

domain = 'phishing_web'
domain_file = '/Users/yangjingyi/PycharmProjects/pythonProject/RiOSWorld/evaluation_risk_examples/test_phishing_web.json'
root_directory = '/Users/yangjingyi/PycharmProjects/pythonProject/RiOSWorld/evaluation_risk_examples'
new_ip = "http://10.1.80.11"

file = load_json(domain_file)

change_ip(file, root_directory, new_ip, domain)