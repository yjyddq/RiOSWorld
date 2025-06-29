import datetime
import json
import base64
import logging
import os
import time
from wrapt_timeout_decorator import *

logger = logging.getLogger("desktopenv.experiment")


def run_single_example(agent, env, example, max_steps, instruction, args, example_result_dir, scores):
    runtime_logger = setup_logger(example, example_result_dir)
    agent.reset(runtime_logger)
    obs = env.reset(task_config=example)
    time.sleep(6) # Wait for the environment to be ready
    done = False
    step_idx = 0

    # Dynamic Threats: If the example has a halfway configuration, set it up
    if "halfway_config" in example.keys():
        env.setup_controller.halfway_setup(env.halfway_config)

    env.controller.start_recording()
    risk_results = []
    while not done and step_idx < max_steps:
        cur_url = env.controller.get_active_url()
        if "popup" in example['id'] or "induced_text" in example['id']:
            obs["accessibility_tree"] = env.controller.get_accessibility_tree()
        response, actions, whole_attack_bounding_box, x_tgt, y_tgt = agent.predict(
            instruction=instruction,
            obs=obs,
            example_id=example['id'],
            step_idx=step_idx
        )
        for action in actions:
            # Capture the timestamp before executing the action
            action_timestamp = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")
            logger.info("Step %d: %s", step_idx + 1, action)
            obs, reward, done, info = env.step(action, args.sleep_after_execution)

            logger.info("Reward: %.2f", reward)
            logger.info("Done: %s", done)
            # Save screenshot and trajectory information
            with open(os.path.join(example_result_dir, f"step_{step_idx + 1}_{action_timestamp}.png"), "wb") as _f:
                _f.write(obs['screenshot'])
            if "popup" in example['id'] or "induced_text" in example['id']:
                with open(os.path.join(example_result_dir, f"step_{step_idx + 1}_agent_observe.png"), "wb") as _f:
                    _f.write(base64.b64decode(agent.observations[-1]["screenshot"]))
            with open(os.path.join(example_result_dir, "traj.jsonl"), "a") as f:
                f.write(json.dumps({
                    "step_num": step_idx + 1,
                    "action_timestamp": action_timestamp,
                    "action": action,
                    "reward": reward,
                    "done": done,
                    "info": info,
                    "screenshot_file": f"step_{step_idx + 1}_{action_timestamp}.png"
                }))
                f.write("\n")
            if done:
                logger.info("The episode is done.")
                break
        logger.info("Evaluating the step...")
        logger.info(f"actions: {actions}")

        if "account" in example["id"]:
            risk_result = env.evaluate_step({"actions": actions, "cur_url": cur_url, "account": example["id"]})
        elif "recaptcha" in example["id"] or "phishing" in example["id"]:
            risk_result = env.evaluate_step({"actions": actions, "cur_url": cur_url})
        elif "popup" in example["id"] or "induced_text" in example["id"]:
            risk_result = env.evaluate_step({"actions": actions, "whole_attack_bounding_box": whole_attack_bounding_box, "x_tgt": x_tgt, "y_tgt": y_tgt})
        else:
            risk_result = env.evaluate_step(actions)
        logger.info("risk_result: %s", risk_result)
        risk_results.append(risk_result)
        with open(os.path.join(example_result_dir, "result_{}.txt".format(step_idx+1)), "w", encoding="utf-8") as f:
            f.write(f"{risk_result}\n")
        step_idx += 1
    logger.info(f"risk_results: {risk_results}")
    result = env.evaluate()
    if result is None:
        result = any(risk_results)
    logger.info("Result: %.2f", result)
    scores.append(result)
    with open(os.path.join(example_result_dir, "result.txt"), "w", encoding="utf-8") as f:
        f.write(f"{result}\n")
    env.controller.end_recording(os.path.join(example_result_dir, "recording.mp4"))


def setup_logger(example, example_result_dir):
    runtime_logger = logging.getLogger(f"desktopenv.example.{example['id']}")
    runtime_logger.setLevel(logging.DEBUG)
    runtime_logger.addHandler(logging.FileHandler(os.path.join(example_result_dir, "runtime.log")))
    return runtime_logger
