#!/bin/bash

export OPENAI_API_KEY="your openai api key"
export ANTHROPIC_API_KEY="your anthropic api key" # optional
export QWEN_API_KEY="your qwen api key" # optional
export GOOGLE_API_KEY="your google api key" # optional

DOMAIN="specific domain" ## a specific domain name
PATH_TO_VM="path to vmware vmx file" ## a path to vmware vmx file
TEST_ALL_META_PATH="path to test_${DOMAIN}_all.json" ## a path to test_${DOMAIN}_all.json

# get current timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

TEMPERATURE=0.0
TOP_P=0.95
TEST_CONFIG_BASE_DIR="evaluation_risk_examples"
SNAPSHOT_NAME="your snapshot name"
OBSERVATION_TYPE='screenshot' ## 'screenshot' or 'a11y_tree' or 'screenshot_a11y_tree' or "som"
SCREEN_WIDTH=1920
SCREEN_HEIGHT=1080

# define model list
MODELS=(
"model1"
"model2"
)

# loop through model list
for MODEL in "${MODELS[@]}"
do
  echo "Testing model: $MODEL"
  
  # create a unique result directory for each model
  RESULT_DIR="./${DOMAIN}_result_evaluate/${MODEL}/${DOMAIN}_${TIMESTAMP}"
  # RESULT_DIR="./multimedia_result/multimedia_1_25_${TIMESTAMP}_${MODEL}"
  
  # run python script
  python run.py \
      --path_to_vm $PATH_TO_VM \
      --test_all_meta_path $TEST_ALL_META_PATH \
      --result_dir $RESULT_DIR \
      --temperature $TEMPERATURE \
      --top_p $TOP_P \
      --test_config_base_dir $TEST_CONFIG_BASE_DIR \
      --model $MODEL \
      --snapshot_name $SNAPSHOT_NAME \
      --observation_type $OBSERVATION_TYPE \
      --screen_width $SCREEN_WIDTH \
      --screen_height $SCREEN_HEIGHT
      
  echo "Model $MODEL testing completed, results saved in $RESULT_DIR"
done

echo "All models testing completed"