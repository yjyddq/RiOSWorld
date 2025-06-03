#!/bin/bash

export OPENAI_API_KEY="your openai api key"
BASE_URL="your base url"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
EVALUATOR="gpt-4o"
DOMAINS=( 
"domain1"
"domain2"
)

GUI="pyautogui"
SCREENSHOT="screenshot" ## "screenshot" or "a11y_tree" or "screenshot_a11y_tree" or "som"
EVAL_DIR="path to evaluation_examples/examples_safe"
EVAL_MODE="step"
USE_IMAGE="True" ## whether you use screenshot in the evaluation

declare -a MODELS=(
    "model to be evaluated"
    )

declare -a LOG_FILES=(
    "path to log file"
)

declare -a RESULTS_DIRS=(
    "path to results directory"
)

if [ ${#MODELS[@]} -ne ${#LOG_FILES[@]} ] || [ ${#MODELS[@]} -ne ${#RESULTS_DIRS[@]} ]; then
    echo "Error: The lengths of the model, log file, and result directory arrays do not match"
    exit 1
fi

for ((i=0; i<${#MODELS[@]}; i++)); do
    MODEL_EVALUATED="${MODELS[$i]}"
    DOMAIN="${DOMAINS[$i]}"
    LOG_FILE="${LOG_FILES[$i]}"
    RESULTS_DIRS="${RESULTS_DIRS[$i]}"
    
    echo "====================================================================="
    echo "Processing model: $MODEL_EVALUATED"
    echo "Log file: $LOG_FILE"
    echo "Result directory: $RESULTS_DIRS"
    echo "====================================================================="
    
    # set output file path
    PROCESSED_OUTPUT="path to processed output file"
    EVAL_OUTPUT="path to evaluation output file"
    RESULT_FILE="path to result file"
    
    # create necessary directories
    mkdir -p $(dirname "$PROCESSED_OUTPUT")
    mkdir -p $(dirname "$EVAL_OUTPUT")
    mkdir -p $(dirname "$RESULT_FILE")
    
    echo "1. run data_process.py generate trajectory data"
    
    # Run data_process.py to process data
    python -c "
import sys
sys.path.append('evaluate')
from data_process import analyze_log_file, process_directory, save_data_to_json
import os

# process log file
print('Analyzing log file...')
try:
    popup_result = analyze_log_file('$LOG_FILE')
    print(f'Found {len(popup_result.keys())} tasks')
    
    if len(popup_result.keys()) == 0:
        print('Warning: No tasks found, but continue execution')
    
    # process result directory
    print('Processing result directory...')
    results_dir = '$RESULTS_DIRS'
    results_dir = os.path.join(results_dir, '$GUI', '$SCREENSHOT', '$MODEL_EVALUATED')
    eval_dir = '$EVAL_DIR'
    output_file = '$PROCESSED_OUTPUT'
    
    # ensure the parent directory of output_file exists
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f'Create directory: {output_dir}')
    
    # process data
    trajectory_data = process_directory(eval_dir, results_dir, popup_result)
    
    # check if trajectory_data is empty
    has_data = False
    for domain in trajectory_data:
        if trajectory_data[domain]:
            has_data = True
            break
    
    if not has_data:
        print('Warning: The processed result is empty')
        # create an empty structure to avoid JSON parsing errors
        trajectory_data = {'$DOMAIN': {'example': []}}
    
    save_data_to_json(trajectory_data, output_file)
    print(f'Data saved to {output_file}')
except Exception as e:
    print(f'Error processing data: {e}')
    # ensure at least one valid JSON file is created to avoid subsequent errors
    with open('$PROCESSED_OUTPUT', 'w') as f:
        f.write('{}')
    sys.exit(1)
"
    
    # check if the output file exists and is not empty
    if [ ! -s "$PROCESSED_OUTPUT" ]; then
        echo "Warning: The generated trajectory data file is empty, skipping this model's evaluation"
        continue
    fi
    
    echo "2. Run safety_evaluation.py for evaluation"
    
    # run safety_evaluation.py for evaluation
    python evaluate/safety_evaluation.py \
        --model_name "$EVALUATOR" \
        --api_key "$OPENAI_API_KEY" \
        --api_base "$BASE_URL" \
        --input_file "$PROCESSED_OUTPUT" \
        --output_file "$EVAL_OUTPUT" \
        --result_file "$RESULT_FILE" \
        --eval_mode "$EVAL_MODE" \
        --eval_prompt "${DOMAIN}_eval_prompt" \
        --use_image "$USE_IMAGE" \
        --ablation_mode "$ABLATION_MODE"
    
    echo "Trajectory data saved to: $PROCESSED_OUTPUT"
    echo "Evaluation result saved to: $EVAL_OUTPUT"
    echo "Statistic result saved to: $RESULT_FILE"
    
    echo "Evaluate each trajectory for safety risk"
    python evaluate/evaluate_traj_by_step.py \
        --path_result "$EVAL_OUTPUT" \
        --domain "$DOMAIN" \
        --result_file "$RESULT_FILE"
    
    echo "===== Model $MODEL_EVALUATED evaluation completed ====="
    echo ""
done

echo "===== All models evaluation completed ====="