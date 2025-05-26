import base64
import json
import logging
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from http import HTTPStatus
from io import BytesIO
from typing import Dict, List

import backoff
import dashscope
import google.generativeai as genai
import openai
import requests
import tiktoken
from PIL import Image
from google.api_core.exceptions import InvalidArgument, ResourceExhausted, InternalServerError, BadRequest
from groq import Groq
from requests.exceptions import SSLError

from mm_agents.accessibility_tree_wrap.heuristic_retrieve import filter_nodes, draw_bounding_boxes
from mm_agents.prompts import SYS_PROMPT_IN_SCREENSHOT_OUT_CODE, SYS_PROMPT_IN_SCREENSHOT_OUT_ACTION, \
    SYS_PROMPT_IN_A11Y_OUT_CODE, SYS_PROMPT_IN_A11Y_OUT_ACTION, \
    SYS_PROMPT_IN_BOTH_OUT_CODE, SYS_PROMPT_IN_BOTH_OUT_ACTION, \
    SYS_PROMPT_IN_SOM_OUT_TAG, PLANNER_SYS_PROMPT_IN_A11Y_OUT_CODE, CONTROLLER_SYS_PROMPT_IN_SCREENSHOT_OUT_CODE

logger = logging.getLogger("desktopenv.agent")

pure_text_settings = ['a11y_tree']

attributes_ns_ubuntu = "https://accessibility.windows.example.org/ns/attributes"
attributes_ns_windows = "https://accessibility.windows.example.org/ns/attributes"
state_ns_ubuntu = "https://accessibility.ubuntu.example.org/ns/state"
state_ns_windows = "https://accessibility.windows.example.org/ns/state"
component_ns_ubuntu = "https://accessibility.ubuntu.example.org/ns/component"
component_ns_windows = "https://accessibility.windows.example.org/ns/component"
value_ns_ubuntu = "https://accessibility.ubuntu.example.org/ns/value"
value_ns_windows = "https://accessibility.windows.example.org/ns/value"
class_ns_windows = "https://accessibility.windows.example.org/ns/class"
# More namespaces defined in OSWorld, please check desktop_env/server/main.py

def extract_coordinate_list(code_string):
    # Update patterns to match either numbers or variable names
    coordinate_pattern = r'(\d+|[a-zA-Z_][a-zA-Z_0-9]*)'
    
    # Pattern to match coordinates in pyautogui.click(980, 160) or pyautogui.click(variable_x, variable_y)
    click_pattern = re.compile(rf'pyautogui\.click\(\s*{coordinate_pattern}\s*,\s*{coordinate_pattern}\s*')
    
    # Pattern to match coordinates in pyautogui.click(x=250, y=750) or pyautogui.click(x=var_x, y=var_y)
    click_keyword_pattern = re.compile(rf'pyautogui\.click\(\s*x\s*=\s*{coordinate_pattern}\s*,\s*y\s*=\s*{coordinate_pattern}\s*')
    
    # Pattern to match coordinates in pyautogui.moveTo(500, 300) or pyautogui.moveTo(variable_x, variable_y)
    move_pattern = re.compile(rf'pyautogui\.moveTo\(\s*{coordinate_pattern}\s*,\s*{coordinate_pattern}\s*')
    
    # Pattern to match coordinates in pyautogui.moveTo(x=250, y=750) or pyautogui.moveTo(x=var_x, y=var_y)
    move_keyword_pattern = re.compile(rf'pyautogui\.moveTo\(\s*x\s*=\s*{coordinate_pattern}\s*,\s*y\s*=\s*{coordinate_pattern}\s*')
    
    # Pattern to match assignments like tag_1 = (1006, 571)
    assignment_pattern = re.compile(rf'([a-zA-Z_][a-zA-Z_0-9]*)\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)')
    
    # Find all variable assignments
    assignment_matches = assignment_pattern.findall(code_string)
    
    # Store the variable assignments in a dictionary
    variable_map = {var: (int(x), int(y)) for var, x, y in assignment_matches}
    
    # Replace pyautogui.click(tag_X) with pyautogui.click(X, Y)
    for var, (x, y) in variable_map.items():
        click_var_pattern = re.compile(rf'pyautogui\.click\(\s*{var}\s*\)')
        code_string = click_var_pattern.sub(f'pyautogui.click({x}, {y})', code_string)
        # Replace pyautogui.moveTo(tag_X) with pyautogui.moveTo(X, Y)
        move_var_pattern = re.compile(rf'pyautogui\.moveTo\(\s*{var}\s*\)')
        code_string = move_var_pattern.sub(f'pyautogui.moveTo({x}, {y})', code_string)
    # Now that the code_string is updated, run the original pattern matching logic
    
    # Find all matches
    click_matches = click_pattern.findall(code_string)
    click_keyword_matches = click_keyword_pattern.findall(code_string)
    move_matches = move_pattern.findall(code_string)
    move_keyword_matches = move_keyword_pattern.findall(code_string)
    
    # Combine all matches into one list
    all_matches = click_matches + click_keyword_matches + move_matches + move_keyword_matches
    
    if len(all_matches) == 0 and "click" in code_string:
        # In case of direct assignment like x, y = 100, 200 or x, y = var_x, var_y
        preassignment_pattern = re.compile(rf'x\s*,\s*y\s*=\s*{coordinate_pattern}\s*,\s*{coordinate_pattern}')
        preassignment_matches = preassignment_pattern.findall(code_string)
        all_matches += preassignment_matches
    
    # Process results: numbers as integers, variables as strings
    coordinates = [(int(x) if x.isdigit() else x, int(y) if y.isdigit() else y) for x, y in all_matches]
    
    return coordinates

def is_within_bounding_box(x, y, bounding_box):
    # Extract the bounding box coordinates
    xmin = bounding_box['xmin']
    ymin = bounding_box['ymin']
    xmax = bounding_box['xmax']
    ymax = bounding_box['ymax']
    
    # Check if the point [x, y] is within or on the edge of the bounding box
    if xmin <= x <= xmax and ymin <= y <= ymax:
        return True
    else:
        return False
    
# Function to encode the image
def encode_image(image_content):
    return base64.b64encode(image_content).decode('utf-8')


def encoded_img_to_pil_img(data_str):
    base64_str = data_str.replace("data:image/png;base64,", "")
    image_data = base64.b64decode(base64_str)
    image = Image.open(BytesIO(image_data))

    return image


def save_to_tmp_img_file(data_str):
    base64_str = data_str.replace("data:image/png;base64,", "")
    image_data = base64.b64decode(base64_str)
    image = Image.open(BytesIO(image_data))

    tmp_img_path = os.path.join(tempfile.mkdtemp(), "tmp_img.png")
    image.save(tmp_img_path)

    return tmp_img_path


def linearize_accessibility_tree(accessibility_tree, platform="ubuntu"):

    if platform == "ubuntu":
        _attributes_ns = attributes_ns_ubuntu
        _state_ns = state_ns_ubuntu
        _component_ns = component_ns_ubuntu
        _value_ns = value_ns_ubuntu
    elif platform == "windows":
        _attributes_ns = attributes_ns_windows
        _state_ns = state_ns_windows
        _component_ns = component_ns_windows
        _value_ns = value_ns_windows
    else:
        raise ValueError("Invalid platform, must be 'ubuntu' or 'windows'")

    filtered_nodes = filter_nodes(ET.fromstring(accessibility_tree), platform)
    linearized_accessibility_tree = ["tag\tname\ttext\tclass\tdescription\tposition (top-left x&y)\tsize (w&h)"]

    # Linearize the accessibility tree nodes into a table format
    for node in filtered_nodes:
        if node.text:
            text = (
                node.text if '"' not in node.text \
                    else '"{:}"'.format(node.text.replace('"', '""'))
            )

        elif node.get("{{{:}}}class".format(class_ns_windows), "").endswith("EditWrapper") \
                and node.get("{{{:}}}value".format(_value_ns)):
            node_text = node.get("{{{:}}}value".format(_value_ns), "")
            text = (node_text if '"' not in node_text \
                        else '"{:}"'.format(node_text.replace('"', '""'))
                    )
        else:
            text = '""'

        linearized_accessibility_tree.append(
            "{:}\t{:}\t{:}\t{:}\t{:}\t{:}\t{:}".format(
                node.tag, node.get("name", ""),
                text,
                node.get("{{{:}}}class".format(_attributes_ns), "") if platform == "ubuntu" else node.get("{{{:}}}class".format(class_ns_windows), ""),
                node.get("{{{:}}}description".format(_attributes_ns), ""),
                node.get('{{{:}}}screencoord'.format(_component_ns), ""),
                node.get('{{{:}}}size'.format(_component_ns), "")
            )
        )

    return "\n".join(linearized_accessibility_tree)


def tag_screenshot(screenshot, accessibility_tree, platform="ubuntu"):
    nodes = filter_nodes(ET.fromstring(accessibility_tree), platform=platform, check_image=True)
    # Make tag screenshot
    marks, drew_nodes, element_list, tagged_screenshot = draw_bounding_boxes(nodes, screenshot)

    return marks, drew_nodes, tagged_screenshot, element_list


def parse_actions_from_string(input_string):
    if input_string.strip() in ['WAIT', 'DONE', 'FAIL']:
        return [input_string.strip()]
    # Search for a JSON string within the input string
    actions = []
    matches = re.findall(r'```json\s+(.*?)\s+```', input_string, re.DOTALL)
    if matches:
        # Assuming there's only one match, parse the JSON string into a dictionary
        try:
            for match in matches:
                action_dict = json.loads(match)
                actions.append(action_dict)
            return actions
        except json.JSONDecodeError as e:
            return f"Failed to parse JSON: {e}"
    else:
        matches = re.findall(r'```\s+(.*?)\s+```', input_string, re.DOTALL)
        if matches:
            # Assuming there's only one match, parse the JSON string into a dictionary
            try:
                for match in matches:
                    action_dict = json.loads(match)
                    actions.append(action_dict)
                return actions
            except json.JSONDecodeError as e:
                return f"Failed to parse JSON: {e}"
        else:
            try:
                action_dict = json.loads(input_string)
                return [action_dict]
            except json.JSONDecodeError:
                raise ValueError("Invalid response format: " + input_string)


def parse_code_from_string(input_string):
    input_string = "\n".join([line.strip() for line in input_string.split(';') if line.strip()])
    if input_string.strip() in ['WAIT', 'DONE', 'FAIL']:
        return [input_string.strip()]

    # This regular expression will match both ```code``` and ```python code```
    # and capture the `code` part. It uses a non-greedy match for the content inside.
    pattern = r"```(?:\w+\s+)?(.*?)```"
    # Find all non-overlapping matches in the string
    matches = re.findall(pattern, input_string, re.DOTALL)

    # The regex above captures the content inside the triple backticks.
    # The `re.DOTALL` flag allows the dot `.` to match newline characters as well,
    # so the code inside backticks can span multiple lines.

    # matches now contains all the captured code snippets

    codes = []

    for match in matches:
        match = match.strip()
        commands = ['WAIT', 'DONE', 'FAIL']  # fixme: updates this part when we have more commands

        if match in commands:
            codes.append(match.strip())
        elif match.split('\n')[-1] in commands:
            if len(match.split('\n')) > 1:
                codes.append("\n".join(match.split('\n')[:-1]))
            codes.append(match.split('\n')[-1])
        else:
            codes.append(match)

    return codes


def parse_code_from_som_string(input_string, masks):
    # parse the output string by masks
    tag_vars = ""
    for i, mask in enumerate(masks):
        x, y, w, h = mask
        tag_vars += "tag_" + str(i + 1) + "=" + "({}, {})".format(int(x + w // 2), int(y + h // 2))
        tag_vars += "\n"

    actions = parse_code_from_string(input_string)

    for i, action in enumerate(actions):
        if action.strip() in ['WAIT', 'DONE', 'FAIL']:
            pass
        else:
            action = tag_vars + action
            actions[i] = action

    return actions


def trim_accessibility_tree(linearized_accessibility_tree, max_tokens):
    enc = tiktoken.encoding_for_model("gpt-4")
    tokens = enc.encode(linearized_accessibility_tree)
    if len(tokens) > max_tokens:
        linearized_accessibility_tree = enc.decode(tokens[:max_tokens])
        linearized_accessibility_tree += "[...]\n"
    return linearized_accessibility_tree



class PromptAgent:
    def __init__(
            self,
            platform="ubuntu",
            model="gpt-4-vision-preview",
            max_tokens=1500,
            top_p=0.9,
            temperature=0.5,
            action_space="computer_13",
            observation_type="screenshot_a11y_tree",
            # observation_type can be in ["screenshot", "a11y_tree", "screenshot_a11y_tree", "som"]
            max_trajectory_length=3,
            a11y_tree_max_tokens=10000
    ):
        self.platform = platform
        self.model = model
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.temperature = temperature
        self.action_space = action_space
        self.observation_type = observation_type
        self.max_trajectory_length = 0 # max_trajectory_length
        self.a11y_tree_max_tokens = a11y_tree_max_tokens

        self.thoughts = []
        self.actions = []
        self.observations = []

        if observation_type == "screenshot":
            if action_space == "computer_13":
                self.system_message = SYS_PROMPT_IN_SCREENSHOT_OUT_ACTION
            elif action_space == "pyautogui":
                self.system_message = SYS_PROMPT_IN_SCREENSHOT_OUT_CODE
            else:
                raise ValueError("Invalid action space: " + action_space)
        elif observation_type == "a11y_tree":
            if action_space == "computer_13":
                self.system_message = SYS_PROMPT_IN_A11Y_OUT_ACTION
            elif action_space == "pyautogui":
                self.system_message = SYS_PROMPT_IN_A11Y_OUT_CODE
            else:
                raise ValueError("Invalid action space: " + action_space)
        elif observation_type == "screenshot_a11y_tree":
            if action_space == "computer_13":
                self.system_message = SYS_PROMPT_IN_BOTH_OUT_ACTION
            elif action_space == "pyautogui":
                self.system_message = SYS_PROMPT_IN_BOTH_OUT_CODE
            else:
                raise ValueError("Invalid action space: " + action_space)
        elif observation_type == "som":
            if action_space == "computer_13":
                raise ValueError("Invalid action space: " + action_space)
            elif action_space == "pyautogui":
                self.system_message = SYS_PROMPT_IN_SOM_OUT_TAG
            else:
                raise ValueError("Invalid action space: " + action_space)
        else:
            raise ValueError("Invalid experiment type: " + observation_type)

    def predict(self, instruction: str, obs: Dict, step_idx: int) -> List:
        """
        Predict the next action(s) based on the current observation.
        """
        system_message = self.system_message + "\nYou are asked to complete the following task: {}".format(instruction)

        # Prepare the payload for the API call
        messages = []
        masks = None

        messages.append({
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": system_message
                },
            ]
        })

        # Append trajectory
        assert len(self.observations) == len(self.actions) and len(self.actions) == len(self.thoughts) \
            , "The number of observations and actions should be the same."

        if len(self.observations) > self.max_trajectory_length:
            if self.max_trajectory_length == 0:
                _observations = []
                _actions = []
                _thoughts = []
            else:
                _observations = self.observations[-self.max_trajectory_length:]
                _actions = self.actions[-self.max_trajectory_length:]
                _thoughts = self.thoughts[-self.max_trajectory_length:]
        else:
            _observations = self.observations
            _actions = self.actions
            _thoughts = self.thoughts

        for previous_obs, previous_action, previous_thought in zip(_observations, _actions, _thoughts):

            # {{{1
            if self.observation_type == "screenshot_a11y_tree":
                _screenshot = previous_obs["screenshot"]
                _linearized_accessibility_tree = previous_obs["accessibility_tree"]

                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Given the screenshot and info from accessibility tree as below:\n{}\nWhat's the next step that you will do to help with the task?".format(
                                _linearized_accessibility_tree)
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{_screenshot}",
                                "detail": "high"
                            }
                        }
                    ]
                })
            elif self.observation_type in ["som"]:
                _screenshot = previous_obs["screenshot"]

                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Given the tagged screenshot as below. What's the next step that you will do to help with the task?"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{_screenshot}",
                                "detail": "high"
                            }
                        }
                    ]
                })
            elif self.observation_type == "screenshot":
                _screenshot = previous_obs["screenshot"]

                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Given the screenshot as below. What's the next step that you will do to help with the task?"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{_screenshot}",
                                "detail": "high"
                            }
                        }
                    ]
                })
            elif self.observation_type == "a11y_tree":
                _linearized_accessibility_tree = previous_obs["accessibility_tree"]

                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Given the info from accessibility tree as below:\n{}\nWhat's the next step that you will do to help with the task?".format(
                                _linearized_accessibility_tree)
                        }
                    ]
                })
            else:
                raise ValueError("Invalid observation_type type: " + self.observation_type)  # 1}}}

            messages.append({
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": previous_thought.strip() if len(previous_thought) > 0 else "No valid action"
                    },
                ]
            })

        # {{{1
        if self.observation_type in ["screenshot", "screenshot_a11y_tree"]:
            base64_image = encode_image(obs["screenshot"])
            linearized_accessibility_tree = linearize_accessibility_tree(accessibility_tree=obs["accessibility_tree"],
                                                                         platform=self.platform) if self.observation_type == "screenshot_a11y_tree" else None
            logger.debug("LINEAR AT: %s", linearized_accessibility_tree)

            if linearized_accessibility_tree:
                linearized_accessibility_tree = trim_accessibility_tree(linearized_accessibility_tree,
                                                                        self.a11y_tree_max_tokens)

            if self.observation_type == "screenshot_a11y_tree":
                self.observations.append({
                    "screenshot": base64_image,
                    "accessibility_tree": linearized_accessibility_tree
                })
            else:
                self.observations.append({
                    "screenshot": base64_image,
                    "accessibility_tree": None
                })

            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Given the screenshot as below. What's the next step that you will do to help with the task?"
                        if self.observation_type == "screenshot"
                        else "Given the screenshot and info from accessibility tree as below:\n{}\nWhat's the next step that you will do to help with the task?".format(
                            linearized_accessibility_tree)
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}",
                            "detail": "high"
                        }
                    }
                ]
            })
        elif self.observation_type == "a11y_tree":
            linearized_accessibility_tree = linearize_accessibility_tree(accessibility_tree=obs["accessibility_tree"],
                                                                         platform=self.platform)
            logger.debug("LINEAR AT: %s", linearized_accessibility_tree)

            if linearized_accessibility_tree:
                linearized_accessibility_tree = trim_accessibility_tree(linearized_accessibility_tree,
                                                                        self.a11y_tree_max_tokens)

            self.observations.append({
                "screenshot": None,
                "accessibility_tree": linearized_accessibility_tree
            })

            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Given the info from accessibility tree as below:\n{}\nWhat's the next step that you will do to help with the task?".format(
                            linearized_accessibility_tree)
                    }
                ]
            })
        elif self.observation_type == "som":
            # Add som to the screenshot
            masks, drew_nodes, tagged_screenshot, linearized_accessibility_tree = tag_screenshot(obs["screenshot"], obs[
                "accessibility_tree"], self.platform)
            base64_image = encode_image(tagged_screenshot)
            logger.debug("LINEAR AT: %s", linearized_accessibility_tree)

            if linearized_accessibility_tree:
                linearized_accessibility_tree = trim_accessibility_tree(linearized_accessibility_tree,
                                                                        self.a11y_tree_max_tokens)

            self.observations.append({
                "screenshot": base64_image,
                "accessibility_tree": linearized_accessibility_tree
            })

            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Given the tagged screenshot and info from accessibility tree as below:\n{}\nWhat's the next step that you will do to help with the task?".format(
                            linearized_accessibility_tree)
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}",
                            "detail": "high"
                        }
                    }
                ]
            })
        else:
            raise ValueError("Invalid observation_type type: " + self.observation_type)  # 1}}}

        # with open("messages.json", "w") as f:
        #     f.write(json.dumps(messages, indent=4))

        # logger.info("PROMPT: %s", messages)

        try:
            response = self.call_llm({
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "top_p": self.top_p,
                "temperature": self.temperature
            })
        except Exception as e:
            logger.error("Failed to call " + self.model + ", Error: " + str(e))
            response = ""
        
        logger.info("RESPONSE: %s", response)
        # print(response)

        try:
            actions = self.parse_actions(response, masks)
            self.thoughts.append(response)
        except ValueError as e:
            print("Failed to parse action from response", e)
            actions = None
            self.thoughts.append("")

        return response, actions

    @backoff.on_exception(
        backoff.constant,
        # here you should add more model exceptions as you want,
        # but you are forbidden to add "Exception", that is, a common type of exception
        # because we want to catch this kind of Exception in the outside to ensure each example won't exceed the time limit
        (
                # General exceptions
                SSLError,

                # OpenAI exceptions
                openai.RateLimitError,
                openai.BadRequestError,
                openai.InternalServerError,

                # Google exceptions
                InvalidArgument,
                ResourceExhausted,
                InternalServerError,
                BadRequest,

                # Groq exceptions
                # todo: check
        ),
        interval=30,
        max_tries=10
    )
    def call_llm(self, payload):
        if self.model.startswith("lmdeploy") or self.model.startswith("sglang") or self.model.startswith("vllm"):
            # import warnings
            # warnings.filterwarnings("ignore", category=FutureWarning)
            # from lmdeploy.serve.openai.api_client import APIClient
            from openai import OpenAI
            
            messages = payload["messages"]
            max_tokens = payload["max_tokens"]
            top_p = payload["top_p"]
            temperature = payload["temperature"]
            lmdeploy_messages = messages
            # lmdeploy_messages = []
            # for i, message in enumerate(messages):
            #     lmdeploy_message = {
            #         "role": message["role"],
            #         "content": []
            #     }

            #     for part in message["content"]:
            #         if part['type'] == "image_url":
            #             lmdeploy_message['content'].append(
            #                 {"type": "image_url", "image_url": {"url": part['image_url']['url']}})

            #         if part['type'] == "text":
            #             lmdeploy_message['content'].append({"type": "text", "text": part['text']})

            #     lmdeploy_messages.append(lmdeploy_message)

            if lmdeploy_messages[0]['role'] == "system":
                lmdeploy_system_message_item = lmdeploy_messages[0]['content'][0]
                lmdeploy_messages[1]['content'].insert(0, lmdeploy_system_message_item)
                lmdeploy_messages.pop(0)
            # The implementation based on LMDeploy
            # client = APIClient('http://10.140.1.25:23333')  # you need to modify the IP address when you use another compute node
            # model_name = client.available_models[0]

            # The implementation based on OpenAI
            client = OpenAI( 
                base_url="http://10.140.1.115:23333/v1", api_key="EMPTY") # you need to modify the IP address when you use another compute node
            model_name = client.models.list().data[0].id
      
            flag = 0
            while True:
                try:
                    if flag > 20:
                        break
                    logger.info("Generating content with model: %s", self.model)
                    # The implementation based on LMDeploy
                    # for item in client.chat_completions_v1(model=model_name, 
                    #                       messages=lmdeploy_messages,
                    #                       max_length=max_tokens,
                    #                       top_p=top_p,
                    #                       temperature=temperature):
                    #     response = item

                    # The implementation based on OpenAI
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=lmdeploy_messages,
                        max_tokens=max_tokens,
                        top_p=top_p,
                        temperature=temperature)
                    break
                except:
                    if flag == 0:
                        lmdeploy_messages = [lmdeploy_messages[0]] + lmdeploy_messages[-1:]
                    else:
                        lmdeploy_messages[-1]["content"] = ' '.join(lmdeploy_messages[-1]["content"].split()[:-500])
                    flag = flag + 1
            try:
                # The implementation based on LMDeploy
                # return response['choices'][0]['message']['content']
                # The implementation based on OpenAI
                return response.choices[0].message.content
            except Exception as e:
                print("Failed to call LLM: " + str(e))
                return ""

        elif self.model.startswith("gpt"):
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"
            }
            Baseurl = "https://api.claudeshop.top"
            url = Baseurl + "/v1/chat/completions"
            logger.info("Generating content with GPT model: %s", self.model)
            response = requests.post(
                # "https://api.openai.com/v1/chat/completions", # original
                url,
                headers=headers,
                json=payload
            )
           
            if response.status_code != 200:
                if response.json()['error']['code'] == "context_length_exceeded":
                    logger.error("Context length exceeded. Retrying with a smaller context.")
                    payload["messages"] = [payload["messages"][0]] + payload["messages"][-1:]
                    retry_response = requests.post(
                        # "https://api.openai.com/v1/chat/completions",
                        url,
                        headers=headers,
                        json=payload
                    )
                    if retry_response.status_code != 200:
                        logger.error(
                            "Failed to call LLM even after attempt on shortening the history: " + retry_response.text)
                        return ""

                logger.error("Failed to call LLM: " + response.text)
                time.sleep(5)
                return ""
            else:
                return response.json()['choices'][0]['message']['content']
        
        elif self.model.startswith("claude"):
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer sk-ulzQlvtlEfIFXBvoKpFmqerUUiJGSP5vovgT8oPv2s11BmBe"
            }
            Baseurl = "https://boyuerichdata.chatgptten.com"
            url = Baseurl + "/v1/chat/completions"
            logger.info("Generating content with Claude model: %s", self.model)
            response = requests.post(
                url,
                headers=headers,
                json=payload
            )
           
            if response.status_code != 200:
                if response.json()['error']['code'] == "context_length_exceeded":
                    logger.error("Context length exceeded. Retrying with a smaller context.")
                    payload["messages"] = [payload["messages"][0]] + payload["messages"][-1:]
                    retry_response = requests.post(
                        url,
                        headers=headers,
                        json=payload
                    )
                    if retry_response.status_code != 200:
                        logger.error(
                            "Failed to call LLM even after attempt on shortening the history: " + retry_response.text)
                        return ""

                logger.error("Failed to call LLM: " + response.text)
                time.sleep(5)
                return ""
            else:
                return response.json()['choices'][0]['message']['content']

        # elif self.model.startswith("claude"):
        #     messages = payload["messages"]
        #     max_tokens = payload["max_tokens"]
        #     top_p = payload["top_p"]
        #     temperature = payload["temperature"]

        #     claude_messages = []

        #     for i, message in enumerate(messages):
        #         claude_message = {
        #             "role": message["role"],
        #             "content": []
        #         }
        #         assert len(message["content"]) in [1, 2], "One text, or one text with one image"
        #         for part in message["content"]:

        #             if part['type'] == "image_url":
        #                 image_source = {}
        #                 image_source["type"] = "base64"
        #                 image_source["media_type"] = "image/png"
        #                 image_source["data"] = part['image_url']['url'].replace("data:image/png;base64,", "")
        #                 claude_message['content'].append({"type": "image", "source": image_source})

        #             if part['type'] == "text":
        #                 claude_message['content'].append({"type": "text", "text": part['text']})

        #         claude_messages.append(claude_message)

        #     # the claude not support system message in our endpoint, so we concatenate it at the first user message
        #     if claude_messages[0]['role'] == "system":
        #         claude_system_message_item = claude_messages[0]['content'][0]
        #         claude_messages[1]['content'].insert(0, claude_system_message_item)
        #         claude_messages.pop(0)

        #     logger.debug("CLAUDE MESSAGE: %s", repr(claude_messages))

        #     headers = {
        #         "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        #         "anthropic-version": "2023-06-01",
        #         "content-type": "application/json"
        #     }

        #     payload = {
        #         "model": self.model,
        #         "max_tokens": max_tokens,
        #         "messages": claude_messages,
        #         "temperature": temperature,
        #         "top_p": top_p
        #     }

        #     response = requests.post(
        #         "https://api.anthropic.com/v1/messages",
        #         headers=headers,
        #         json=payload
        #     )

        #     if response.status_code != 200:

        #         logger.error("Failed to call LLM: " + response.text)
        #         time.sleep(5)
        #         return ""
        #     else:
        #         return response.json()['content'][0]['text']

        elif self.model.startswith("gemini"):
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer sk-5blVTIfg5GPUdpdcpAZNTJ0Bqxh4ozDPcCDH6nZPG68AMjzl"
            }
            Baseurl = "https://api.claudeshop.top"
            url = Baseurl + "/v1/chat/completions"
            logger.info("Generating content with Gemini model: %s", self.model)
            response = requests.post(
                url,
                headers=headers,
                json=payload
            )

            if response.status_code != 200:
                if response.json()['error']['code'] == "context_length_exceeded":
                    logger.error("Context length exceeded. Retrying with a smaller context.")
                    payload["messages"] = [payload["messages"][0]] + payload["messages"][-1:]
                    retry_response = requests.post(
                        url,
                        headers=headers,
                        json=payload
                    )
                    if retry_response.status_code != 200:
                        logger.error(
                            "Failed to call LLM even after attempt on shortening the history: " + retry_response.text)
                        return ""

                logger.error("Failed to call LLM: " + response.text)
                time.sleep(5)
                return ""
            else:
                return response.json()['choices'][0]['message']['content']

        elif self.model.startswith("mistral"):
            messages = payload["messages"]
            max_tokens = payload["max_tokens"]
            top_p = payload["top_p"]
            temperature = payload["temperature"]

            assert self.observation_type in pure_text_settings, f"The model {self.model} can only support text-based input, please consider change based model or settings"

            mistral_messages = []

            for i, message in enumerate(messages):
                mistral_message = {
                    "role": message["role"],
                    "content": ""
                }

                for part in message["content"]:
                    mistral_message['content'] = part['text'] if part['type'] == "text" else ""

                mistral_messages.append(mistral_message)

            from openai import OpenAI

            client = OpenAI(api_key=os.environ["TOGETHER_API_KEY"],
                            base_url='https://api.together.xyz',
                            )

            flag = 0
            while True:
                try:
                    if flag > 20:
                        break
                    logger.info("Generating content with model: %s", self.model)
                    response = client.chat.completions.create(
                        messages=mistral_messages,
                        model=self.model,
                        max_tokens=max_tokens,
                        top_p=top_p,
                        temperature=temperature
                    )
                    break
                except:
                    if flag == 0:
                        mistral_messages = [mistral_messages[0]] + mistral_messages[-1:]
                    else:
                        mistral_messages[-1]["content"] = ' '.join(mistral_messages[-1]["content"].split()[:-500])
                    flag = flag + 1

            try:
                return response.choices[0].message.content
            except Exception as e:
                print("Failed to call LLM: " + str(e))
                return ""

        elif self.model.startswith("THUDM"):
            # THUDM/cogagent-chat-hf
            messages = payload["messages"]
            max_tokens = payload["max_tokens"]
            top_p = payload["top_p"]
            temperature = payload["temperature"]

            cog_messages = []

            for i, message in enumerate(messages):
                cog_message = {
                    "role": message["role"],
                    "content": []
                }

                for part in message["content"]:
                    if part['type'] == "image_url":
                        cog_message['content'].append(
                            {"type": "image_url", "image_url": {"url": part['image_url']['url']}})

                    if part['type'] == "text":
                        cog_message['content'].append({"type": "text", "text": part['text']})

                cog_messages.append(cog_message)

            # the cogagent not support system message in our endpoint, so we concatenate it at the first user message
            if cog_messages[0]['role'] == "system":
                cog_system_message_item = cog_messages[0]['content'][0]
                cog_messages[1]['content'].insert(0, cog_system_message_item)
                cog_messages.pop(0)

            payload = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": cog_messages,
                "temperature": temperature,
                "top_p": top_p
            }

            base_url = "http://127.0.0.1:8000"

            response = requests.post(f"{base_url}/v1/chat/completions", json=payload, stream=False)
            if response.status_code == 200:
                decoded_line = response.json()
                content = decoded_line.get("choices", [{}])[0].get("message", "").get("content", "")
                return content
            else:
                print("Failed to call LLM: ", response.status_code)
                return ""

        elif self.model in ["gemini-pro", "gemini-pro-vision"]:
            messages = payload["messages"]
            max_tokens = payload["max_tokens"]
            top_p = payload["top_p"]
            temperature = payload["temperature"]

            content = payload['messages'][0]['content']
            print(content)

            if self.model == "gemini-pro":
                assert self.observation_type in pure_text_settings, f"The model {self.model} can only support text-based input, please consider change based model or settings"

            gemini_messages = []
            for i, message in enumerate(messages):
                role_mapping = {
                    "assistant": "model",
                    "user": "user",
                    "system": "system"
                }
                gemini_message = {
                    "role": role_mapping[message["role"]],
                    "parts": []
                }
                assert len(message["content"]) in [1, 2], "One text, or one text with one image"

                # The gemini only support the last image as single image input
                if i == len(messages) - 1:
                    for part in message["content"]:
                        gemini_message['parts'].append(part['text']) if part['type'] == "text" \
                            else gemini_message['parts'].append(encoded_img_to_pil_img(part['image_url']['url']))
                else:
                    for part in message["content"]:
                        gemini_message['parts'].append(part['text']) if part['type'] == "text" else None

                gemini_messages.append(gemini_message)

            # the gemini not support system message in our endpoint, so we concatenate it at the first user message
            if gemini_messages[0]['role'] == "system":
                gemini_messages[1]['parts'][0] = gemini_messages[0]['parts'][0] + "\n" + gemini_messages[1]['parts'][0]
                gemini_messages.pop(0)

            # since the gemini-pro-vision donnot support multi-turn message
            if self.model == "gemini-pro-vision":
                message_history_str = ""
                for message in gemini_messages:
                    message_history_str += "<|" + message['role'] + "|>\n" + message['parts'][0] + "\n"
                gemini_messages = [{"role": "user", "parts": [message_history_str, gemini_messages[-1]['parts'][1]]}]
                # gemini_messages[-1]['parts'][1].save("output.png", "PNG")

            # print(gemini_messages)
            api_key = os.environ.get("GENAI_API_KEY")
            assert api_key is not None, "Please set the GENAI_API_KEY environment variable"
            genai.configure(api_key=api_key)
            logger.info("Generating content with Gemini model: %s", self.model)
            # request_options = {"timeout": 120}
            request_options = {"timeout": 10} ## for debug
            gemini_model = genai.GenerativeModel(self.model)

            response = gemini_model.generate_content(
                gemini_messages,
                generation_config={
                    "candidate_count": 1,
                    # "max_output_tokens": max_tokens,
                    "top_p": top_p,
                    "temperature": temperature
                },
                safety_settings={
                    "harassment": "block_none",
                    "hate": "block_none",
                    "sex": "block_none",
                    "danger": "block_none"
                },
                request_options=request_options
            )
            return response.text

        elif self.model == "gemini-1.5-pro-latest":
            messages = payload["messages"]
            max_tokens = payload["max_tokens"]
            top_p = payload["top_p"]
            temperature = payload["temperature"]

            gemini_messages = []
            for i, message in enumerate(messages):
                role_mapping = {
                    "assistant": "model",
                    "user": "user",
                    "system": "system"
                }
                assert len(message["content"]) in [1, 2], "One text, or one text with one image"
                gemini_message = {
                    "role": role_mapping[message["role"]],
                    "parts": []
                }

                # The gemini only support the last image as single image input
                for part in message["content"]:

                    if part['type'] == "image_url":
                        # Put the image at the beginning of the message
                        gemini_message['parts'].insert(0, encoded_img_to_pil_img(part['image_url']['url']))
                    elif part['type'] == "text":
                        gemini_message['parts'].append(part['text'])
                    else:
                        raise ValueError("Invalid content type: " + part['type'])

                gemini_messages.append(gemini_message)

            # the system message of gemini-1.5-pro-latest need to be inputted through model initialization parameter
            system_instruction = None
            if gemini_messages[0]['role'] == "system":
                system_instruction = gemini_messages[0]['parts'][0]
                gemini_messages.pop(0)

            api_key = os.environ.get("GENAI_API_KEY")
            assert api_key is not None, "Please set the GENAI_API_KEY environment variable"
            genai.configure(api_key=api_key)
            logger.info("Generating content with Gemini model: %s", self.model)
            # request_options = {"timeout": 120}    
            request_options = {"timeout": 10} ## for debug
            gemini_model = genai.GenerativeModel(
                self.model,
                system_instruction=system_instruction
            )

            with open("response.json", "w") as f:
                messages_to_save = []
                for message in gemini_messages:
                    messages_to_save.append({
                        "role": message["role"],
                        "content": [part if isinstance(part, str) else "image" for part in message["parts"]]
                    })
                json.dump(messages_to_save, f, indent=4)

            response = gemini_model.generate_content(
                gemini_messages,
                generation_config={
                    "candidate_count": 1,
                    # "max_output_tokens": max_tokens,
                    "top_p": top_p,
                    "temperature": temperature
                },
                safety_settings={
                    "harassment": "block_none",
                    "hate": "block_none",
                    "sex": "block_none",
                    "danger": "block_none"
                },
                request_options=request_options
            )

            return response.text

        elif self.model.startswith("llama"):
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"
            }
            Baseurl = "https://api.claudeshop.top"
            url = Baseurl + "/v1/chat/completions"
            logger.info("Generating content with LLAMA model: %s", self.model)
            response = requests.post(
                # "https://api.openai.com/v1/chat/completions", # original
                url,
                headers=headers,
                json=payload
            )
           
            if response.status_code != 200:
                if response.json()['error']['code'] == "context_length_exceeded":
                    logger.error("Context length exceeded. Retrying with a smaller context.")
                    payload["messages"] = [payload["messages"][0]] + payload["messages"][-1:]
                    retry_response = requests.post(
                        # "https://api.openai.com/v1/chat/completions",
                        url,
                        headers=headers,
                        json=payload
                    )
                    if retry_response.status_code != 200:
                        logger.error(
                            "Failed to call LLM even after attempt on shortening the history: " + retry_response.text)
                        return ""

                logger.error("Failed to call LLM: " + response.text)
                time.sleep(5)
                return ""
            else:
                return response.json()['choices'][0]['message']['content']
        


        elif self.model.startswith("qwen"):
            messages = payload["messages"]
            max_tokens = payload["max_tokens"]
            top_p = payload["top_p"]
            temperature = payload["temperature"]

            qwen_messages = []

            for i, message in enumerate(messages):
                qwen_message = {
                    "role": message["role"],
                    "content": []
                }
                assert len(message["content"]) in [1, 2], "One text, or one text with one image"
                for part in message["content"]:
                    qwen_message['content'].append(
                        {"image": "file://" + save_to_tmp_img_file(part['image_url']['url'])}) if part[
                                                                                                      'type'] == "image_url" else None
                    qwen_message['content'].append({"text": part['text']}) if part['type'] == "text" else None

                qwen_messages.append(qwen_message)

            # The implementation based on Groq API
            dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY")

            flag = 0
            while True:
                try:
                    if flag > 20:
                        break
                    logger.info("Generating content with model: %s", self.model)

                    if self.model in ["qwen-vl-plus", "qwen-vl-max"]:
                        response = dashscope.MultiModalConversation.call(
                            model=self.model,
                            messages=qwen_messages,
                            result_format="message",
                            max_length=max_tokens,
                            top_p=top_p,
                            temperature=temperature
                        )

                    elif self.model in ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-max-0428", "qwen-max-0403",
                                        "qwen-max-0107", "qwen-max-longcontext"]:
                        response = dashscope.Generation.call(
                            model=self.model,
                            messages=qwen_messages,
                            result_format="message",
                            max_length=max_tokens,
                            top_p=top_p,
                            temperature=temperature
                        )

                    else:
                        raise ValueError("Invalid model: " + self.model)

                    if response.status_code == HTTPStatus.OK:
                        break
                    else:
                        logger.error('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                            response.request_id, response.status_code,
                            response.code, response.message
                        ))
                        raise Exception("Failed to call LLM: " + response.message)
                except:
                    if flag == 0:
                        qwen_messages = [qwen_messages[0]] + qwen_messages[-1:]
                    else:
                        for i in range(len(qwen_messages[-1]["content"])):
                            if "text" in qwen_messages[-1]["content"][i]:
                                qwen_messages[-1]["content"][i]["text"] = ' '.join(
                                    qwen_messages[-1]["content"][i]["text"].split()[:-500])
                    flag = flag + 1

            try:
                if self.model in ["qwen-vl-plus", "qwen-vl-max"]:
                    return response['output']['choices'][0]['message']['content'][0]['text']
                else:
                    return response['output']['choices'][0]['message']['content']

            except Exception as e:
                print("Failed to call LLM: " + str(e))
                return ""

        else:
            raise ValueError("Invalid model: " + self.model)

    def parse_actions(self, response: str, masks=None):

        if self.observation_type in ["screenshot", "a11y_tree", "screenshot_a11y_tree"]:
            # parse from the response
            if self.action_space == "computer_13":
                actions = parse_actions_from_string(response)
            elif self.action_space == "pyautogui":
                actions = parse_code_from_string(response)
            else:
                raise ValueError("Invalid action space: " + self.action_space)

            self.actions.append(actions)

            return actions
        elif self.observation_type in ["som"]:
            # parse from the response
            if self.action_space == "computer_13":
                raise ValueError("Invalid action space: " + self.action_space)
            elif self.action_space == "pyautogui":
                actions = parse_code_from_som_string(response, masks)
            else:
                raise ValueError("Invalid action space: " + self.action_space)

            self.actions.append(actions)

            return actions

    def reset(self, _logger=None):
        global logger
        logger = _logger if _logger is not None else logging.getLogger("desktopenv.agent")

        self.thoughts = []
        self.actions = []
        self.observations = []


class PlannerController:
    def __init__(
            self,
            platform="ubuntu",
            model="o1-preview_gpt-4-vision-preview",
            max_tokens=1500,
            top_p=0.9,
            temperature=0.5,
            action_space="computer_13",
            observation_type="screenshot_a11y_tree",
            # observation_type can be in ["screenshot", "a11y_tree", "screenshot_a11y_tree", "som"]
            max_trajectory_length=3,
            a11y_tree_max_tokens=10000
    ):
        self.platform = platform
        self.model = model
        self.planner = model.split('_')[0]
        self.controller = model.split('_')[1]
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.temperature = temperature
        self.action_space = action_space
        self.observation_type = observation_type
        self.max_trajectory_length = max_trajectory_length
        self.a11y_tree_max_tokens = a11y_tree_max_tokens

        self.thoughts = []
        self.actions = []
        self.observations = []

        assert observation_type == "screenshot_a11y_tree", "The observation type must be screenshot_a11y_tree."

        if observation_type == "screenshot":
            if action_space == "computer_13":
                self.system_message = SYS_PROMPT_IN_SCREENSHOT_OUT_ACTION
            elif action_space == "pyautogui":
                self.system_message = SYS_PROMPT_IN_SCREENSHOT_OUT_CODE
            else:
                raise ValueError("Invalid action space: " + action_space)
        elif observation_type == "a11y_tree":
            if action_space == "computer_13":
                self.system_message = SYS_PROMPT_IN_A11Y_OUT_ACTION
            elif action_space == "pyautogui":
                self.system_message = SYS_PROMPT_IN_A11Y_OUT_CODE
            else:
                raise ValueError("Invalid action space: " + action_space)
        elif observation_type == "screenshot_a11y_tree":
            if action_space == "computer_13":
                self.system_message = SYS_PROMPT_IN_BOTH_OUT_ACTION
            elif action_space == "pyautogui":
                self.system_message = SYS_PROMPT_IN_BOTH_OUT_CODE
                self.planner_system_message = PLANNER_SYS_PROMPT_IN_A11Y_OUT_CODE
                self.controller_system_message = CONTROLLER_SYS_PROMPT_IN_SCREENSHOT_OUT_CODE
            else:
                raise ValueError("Invalid action space: " + action_space)
        elif observation_type == "som":
            if action_space == "computer_13":
                raise ValueError("Invalid action space: " + action_space)
            elif action_space == "pyautogui":
                self.system_message = SYS_PROMPT_IN_SOM_OUT_TAG
            else:
                raise ValueError("Invalid action space: " + action_space)
        else:
            raise ValueError("Invalid experiment type: " + observation_type)

    def predict(self, instruction: str, obs: Dict, step_idx: int) -> List:
        """
        Predict the next action(s) based on the current observation.
        """
        # planner_system_message = self.planner_system_message + "\nYou are asked to give a planning for the following task: {}".format(instruction)
        # controller_system_message = self.controller_system_message + "\nYou are asked to complete the following task: {}".format(instruction)
        planner_system_message = self.planner_system_message
        controller_system_message = self.controller_system_message

        # Prepare the payload for the API call
        planner_messages = []
        controller_messages = []
        masks = None

        planner_messages.append({
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": planner_system_message
                },
            ]
        })

        controller_messages.append({
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": controller_system_message
                },
            ]
        })

        # Append trajectory
        assert len(self.observations) == len(self.actions) and len(self.actions) == len(self.thoughts) \
            , "The number of observations and actions should be the same."

        if len(self.observations) > self.max_trajectory_length:
            if self.max_trajectory_length == 0:
                _observations = []
                _actions = []
                _thoughts = []
            else:
                _observations = self.observations[-self.max_trajectory_length:]
                _actions = self.actions[-self.max_trajectory_length:]
                _thoughts = self.thoughts[-self.max_trajectory_length:]
        else:
            _observations = self.observations
            _actions = self.actions
            _thoughts = self.thoughts

        for previous_obs, previous_action, previous_thought in zip(_observations, _actions, _thoughts):
            # {{{1
            _linearized_accessibility_tree = previous_obs["accessibility_tree"]
            planner_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Given the info from accessibility tree as below:\n{}\nYou are asked to give a planning for the following task: {}".format(
                        _linearized_accessibility_tree, instruction) if step_idx == 1 else
                        "Given the info from accessibility tree as below:\n{}\nPlease replan following steps based on previous results, and give the next step that you plan to do for the task: {}".format(
                        _linearized_accessibility_tree, instruction)
                    }
                ]
            })

            _screenshot = previous_obs["screenshot"]
            controller_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Given the screenshot as below. What should you do to complete the sub-task: {}?".format(previous_thought[0].strip() if len(previous_thought[0]) > 0 else "No valid low-level instruction")
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{_screenshot}",
                            "detail": "high"
                        }
                    }
                ]
            })
            
            planner_messages.append({
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": previous_thought[0].strip() if len(previous_thought[0]) > 0 else "No valid low-level instruction"
                    },
                ]
            })

            controller_messages.append({
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": previous_thought[1].strip() if len(previous_thought[1]) > 0 else "No valid action"
                    },
                ]
            })

        # {{{1
        base64_image = encode_image(obs["screenshot"])
        linearized_accessibility_tree = linearize_accessibility_tree(accessibility_tree=obs["accessibility_tree"],
                                            platform=self.platform) if self.observation_type == "screenshot_a11y_tree" else None
        logger.debug("LINEAR AT: %s", linearized_accessibility_tree)

        linearized_accessibility_tree = trim_accessibility_tree(linearized_accessibility_tree,
                                            self.a11y_tree_max_tokens)

        self.observations.append({
            "screenshot": base64_image,
            "accessibility_tree": linearized_accessibility_tree
        })

        planner_messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    # What's the next step that you plan to do for the task: {}?
                    "text": "Given the info from accessibility tree as below:\n{}\nYou are asked to give a planning for the following task: {}".format(
                    linearized_accessibility_tree, instruction) if step_idx == 0 else
                    "Given the info from accessibility tree as below:\n{}\nPlease replan following steps based on previous results, and give the next step that you plan to do for the task: {}".format(
                        linearized_accessibility_tree, instruction)
                }
            ]
        })

        controller_messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "\nYou are asked to complete the following task: {}".format(instruction)
                    if step_idx == 0 else
                    "Given the screenshot as below. What should you do to complete the task: ?" # will be replaced in call_llm
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}",
                        "detail": "high"
                    }
                }
            ]
        })

        # Call LLMs
        try:
            sub_instruction, response = self.call_llm({
                "model": self.model,
                "planner_messages": planner_messages,
                "controller_messages": controller_messages,
                "max_tokens": self.max_tokens,
                "top_p": self.top_p,
                "temperature": self.temperature
            })
        except Exception as e:
            logger.error("Failed to call " + self.model + ", Error: " + str(e))
            sub_instruction = instruction
            response = ""
        
        logger.info("RESPONSE: %s", response)
        # print(response)

        try:
            actions = self.parse_actions(response, masks)
            self.thoughts.append([sub_instruction, response])
            # self.actions.append(response)
        except ValueError as e:
            print("Failed to parse action from response", e)
            actions = None
            self.thoughts.append(["", ""])
            # self.actions.append("")

        return response, actions

    @backoff.on_exception(
        backoff.constant,
        # here you should add more model exceptions as you want,
        # but you are forbidden to add "Exception", that is, a common type of exception
        # because we want to catch this kind of Exception in the outside to ensure each example won't exceed the time limit
        (
                # General exceptions
                SSLError,

                # OpenAI exceptions
                openai.RateLimitError,
                openai.BadRequestError,
                openai.InternalServerError,

                # Google exceptions
                InvalidArgument,
                ResourceExhausted,
                InternalServerError,
                BadRequest,

                # Groq exceptions
                # todo: check
        ),
        interval=30,
        max_tries=10
    )
    def call_llm(self, payload):
        from openai import OpenAI
        import re

        planner_messages = payload["planner_messages"]
        controller_messages = payload["controller_messages"]
        max_tokens = payload["max_tokens"]
        top_p = payload["top_p"]
        temperature = payload["temperature"]
  

        # The implementation based on OpenAI
        planner = OpenAI( 
            base_url="http://10.140.1.29:23333/v1", api_key="YOUR_API_KEY") # you need to modify the IP address when you use another compute node
        planner_model_name = planner.models.list().data[0].id

        controller = OpenAI( 
            base_url="http://10.140.1.115:23333/v1", api_key="EMPTY") # you need to modify the IP address when you use another compute node
        controller_model_name = controller.models.list().data[0].id
      
        flag = 0
        while True:
            try:
                if flag > 20:
                    break
                logger.info("Generating content with model: %s", self.model)
                # The implementation based on OpenAI
                planner_response = planner.chat.completions.create(
                    model=planner_model_name,
                    messages=planner_messages,
                    max_tokens=2*max_tokens,
                    top_p=top_p,
                    temperature=temperature)
                pattern = r"<answer>\s*(.*?)\s*</answer>"
                planner_content = re.findall(pattern, planner_response.choices[0].message.content, re.DOTALL)[-1]

                controller_messages[-1]["content"][0]['text'] = "Given the screenshot as below. What should you do to complete the sub-task: {}?".format(planner_content)
                logger.info("SUB INSTRUCTION: %s", controller_messages[-1]["content"][0]['text'])
                controller_response = controller.chat.completions.create(
                    model=controller_model_name,
                    messages=controller_messages,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    temperature=temperature)
                break
            except:
                if flag == 0:
                    controller_messages = [controller_messages[0]] + controller_messages[-1:]
                else:
                    controller_messages[-1]["content"] = ' '.join(controller_messages[-1]["content"].split()[:-500])
                flag = flag + 1
        try:
            # The implementation based on OpenAI
            return planner_content, controller_response.choices[0].message.content
        except Exception as e:
            print("Failed to call LLM: " + str(e))
            return "", ""

    def parse_actions(self, response: str, masks=None):

        if self.observation_type in ["screenshot", "a11y_tree", "screenshot_a11y_tree"]:
            # parse from the response
            if self.action_space == "computer_13":
                actions = parse_actions_from_string(response)
            elif self.action_space == "pyautogui":
                actions = parse_code_from_string(response)
            else:
                raise ValueError("Invalid action space: " + self.action_space)

            self.actions.append(actions)

            return actions
        elif self.observation_type in ["som"]:
            # parse from the response
            if self.action_space == "computer_13":
                raise ValueError("Invalid action space: " + self.action_space)
            elif self.action_space == "pyautogui":
                actions = parse_code_from_som_string(response, masks)
            else:
                raise ValueError("Invalid action space: " + self.action_space)

            self.actions.append(actions)

            return actions

    def reset(self, _logger=None):
        global logger
        logger = _logger if _logger is not None else logging.getLogger("desktopenv.agent")

        self.thoughts = []
        self.actions = []
        self.observations = []

