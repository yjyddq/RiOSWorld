# Evaluation examples

Here we put the data examples to benchmark the ability of agents when interacting with GUI.
The examples are stored in `./examples` where each data item formatted as:

```
{
    "id": "uid", # unique id
    "snapshot": "snapshot_id", # the snapshot id of the environment, with some data already there and apps already opened, or just desktop
    "instruction": "natural_language_instruction", # the natural language instruction of the task, what we want the agent to do
    "source": "website_url", # where we know this example, some forum, or some website, or some paper
    "config": {xxx}, # the scripts to setup the donwload and open files actions, as the initial state of a task
    "related_apps": ["app1", "app2", ...], # the related apps, which are opened during the task
    "evaluator": "evaluation_dir", # the directory of the evaluator, which contains the evaluation script for this example
…
}
```

The risk examples are stored in `evaluation_risk_examples/examples` where each data item formatted as:

```
{
    "id": "uid", # unique id
    "snapshot": "snapshot_id", # the snapshot id of the environment, with some data already there and apps already opened, or just desktop
    "instruction": "natural_language_instruction", # the natural language instruction of the task, what we want the agent to do
    "source": "website_url", # where we know this example, some forum, or some website, or some paper
    "config": {xxx}, # the scripts to setup the donwload and open files actions, as the initial state of a task
    "halfway_config": {xxx}, # the scripts to setup the donwload and open files actions, as the halfway state of a task
    "related_apps": ["app1", "app2", ...], # the related apps, which are opened during the task
    "evaluator": "evaluation_dir", # the directory of the evaluator, which contains the evaluation script for this example
    "risk_evaluator": "evaluation_dir", # the directory of the evaluator, which contains the risk evaluation script for this example
…
}
```
