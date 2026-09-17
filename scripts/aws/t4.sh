#!/usr/bin/env bash
# The T4 column: one g4dn.xlarge, scripted end to end. [Shrestha]
#
#   scripts/aws/t4.sh preflight      credentials, region, quota, price -- spends nothing
#   scripts/aws/t4.sh budget         $50 monthly budget + email alert (runbook: FIRST)
#   scripts/aws/t4.sh stage          S3 bucket; upload seq 08 + poses + FRNet checkpoint
#   scripts/aws/t4.sh launch         key pair, SG (SSH from this IP only), instance, EIP
#   scripts/aws/t4.sh setup          clone, venv, Patchwork++, cupy, torch, data sync, tests
#   scripts/aws/t4.sh run            T4 measurements -> results/t4/ on the instance
#   scripts/aws/t4.sh fetch          copy results/t4 back (json/md/log only)
#   scripts/aws/t4.sh ssh            open a shell (tmux)
#   scripts/aws/t4.sh status | stop | start
#
# Follows docs/gpu-lane/02-AWS-RUNBOOK.md: ap-south-1, g4dn.xlarge, Deep Learning
# Base OSS Nvidia Driver AMI (Ubuntu 22.04), 150 GB gp3, tagged Project=vrgrid,
# Owner=shrestha. There is deliberately NO terminate command: stop keeps the
# volume for ~$0.40/day, terminate destroys it, and that should be a decision
# made in the console, not a typo here.
#
# State (instance id, key path, bucket) lives in ~/.vrgrid-aws so the commands
# chain across shells.

set -euo pipefail

AWS="${AWS:-$HOME/.local/bin/aws}"
REGION="${VRGRID_AWS_REGION:-ap-south-1}"
TYPE="g4dn.xlarge"
DISK_GB=150
STATE="$HOME/.vrgrid-aws"
KEY_NAME="vrgrid-t4"
KEY_PATH="$HOME/.ssh/${KEY_NAME}.pem"
SG_NAME="vrgrid-t4-ssh"
TAGS="Key=Project,Value=vrgrid},{Key=Owner,Value=shrestha"
REPO="https://github.com/Stxtics03/vrgrid-26.git"
HERE="$(cd "$(dirname "$0")/../.." && pwd)"

mkdir -p "$STATE"
aws_() { "$AWS" --region "$REGION" "$@"; }
save() { echo "$2" > "$STATE/$1"; }
load() { cat "$STATE/$1" 2>/dev/null || true; }
die() { echo "t4.sh: $*" >&2; exit 1; }
ip() { aws_ ec2 describe-instances --instance-ids "$(load instance)" \
         --query 'Reservations[0].Instances[0].PublicIpAddress' --output text; }
ssh_() { ssh -i "$KEY_PATH" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 "ubuntu@$(ip)" "$@"; }

preflight() {
    "$AWS" sts get-caller-identity --output table || die "no AWS credentials -- run: $AWS configure"
    echo "region $REGION"
    aws_ ec2 describe-instance-type-offerings --location-type region \
        --filters "Name=instance-type,Values=$TYPE" --query 'InstanceTypeOfferings[].InstanceType' --output text \
        | grep -q "$TYPE" || die "$TYPE not offered in $REGION"
    # G and VT on-demand vCPU quota; a new account is often 0, and launch then fails
    local q
    q=$("$AWS" --region "$REGION" service-quotas get-service-quota --service-code ec2 \
        --quota-code L-DB2E81BA --query 'Quota.Value' --output text 2>/dev/null || echo "unknown")
    echo "G/VT on-demand vCPU quota: $q (g4dn.xlarge needs 4)"
    [[ "$q" == "unknown" ]] || awk "BEGIN{exit !($q >= 4)}" || \
        echo "!! quota below 4 -- request an increase in Service Quotas before launch"
    echo "AMI: $(ami)"
    echo "public IP of this machine: $(curl -s https://checkip.amazonaws.com)"
}

ami() {
    aws_ ec2 describe-images --owners amazon \
        --filters "Name=name,Values=Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*" \
                  "Name=state,Values=available" \
        --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text
}

budget() {
    local acct email
    acct=$("$AWS" sts get-caller-identity --query Account --output text)
    email="${VRGRID_ALERT_EMAIL:?set VRGRID_ALERT_EMAIL to the address that gets the alert}"
    "$AWS" budgets create-budget --account-id "$acct" \
        --budget '{"BudgetName":"vrgrid-t4","BudgetLimit":{"Amount":"50","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}' \
        --notifications-with-subscribers "[{\"Notification\":{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":80,\"ThresholdType\":\"PERCENTAGE\"},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$email\"}]}]" \
        && echo "budget vrgrid-t4: \$50/month, alert at 80% to $email"
}

stage() {
    # shellcheck disable=SC1091
    source "$HERE/scripts/env.sh"
    local bucket
    bucket=$(load bucket)
    if [[ -z "$bucket" ]]; then
        bucket="vrgrid-data-$("$AWS" sts get-caller-identity --query Account --output text)"
        aws_ s3 mb "s3://$bucket" || true
        aws_ s3api put-bucket-tagging --bucket "$bucket" --tagging "TagSet=[{$TAGS}]"
        save bucket "$bucket"
    fi
    # Runbook §4: sequence 08 is what every T4 measurement reads.
    aws_ s3 sync "$VRGRID_DATA_ROOT/sequences/08" "s3://$bucket/dataset/sequences/08"
    aws_ s3 cp "$VRGRID_DATA_ROOT/poses/08.txt" "s3://$bucket/dataset/poses/08.txt"
    aws_ s3 cp "$VRGRID_FRNET_CHECKPOINT" "s3://$bucket/checkpoints/$(basename "$VRGRID_FRNET_CHECKPOINT")"
    echo "staged to s3://$bucket"
}

launch() {
    [[ -z "$(load instance)" ]] || die "instance $(load instance) already recorded; use start/status"
    if [[ ! -f "$KEY_PATH" ]]; then
        aws_ ec2 create-key-pair --key-name "$KEY_NAME" --query KeyMaterial --output text > "$KEY_PATH"
        chmod 400 "$KEY_PATH"
    fi
    local myip vpc sg id alloc
    myip=$(curl -s https://checkip.amazonaws.com)
    vpc=$(aws_ ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
    sg=$(aws_ ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" \
         --query 'SecurityGroups[0].GroupId' --output text)
    if [[ "$sg" == "None" ]]; then
        sg=$(aws_ ec2 create-security-group --group-name "$SG_NAME" --vpc-id "$vpc" \
             --description "vrgrid T4: SSH from one IP" --query GroupId --output text)
    fi
    aws_ ec2 authorize-security-group-ingress --group-id "$sg" --protocol tcp --port 22 \
        --cidr "$myip/32" 2>/dev/null || true
    # No IAM role on the instance: `setup` hands it one-hour session credentials
    # for the S3 pull over SSH, so no long-lived key ever sits on the box.
    id=$(aws_ ec2 run-instances --image-id "$(ami)" --instance-type "$TYPE" \
         --key-name "$KEY_NAME" --security-group-ids "$sg" \
         --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$DISK_GB,VolumeType=gp3,DeleteOnTermination=true}" \
         --tag-specifications "ResourceType=instance,Tags=[{$TAGS}]" "ResourceType=volume,Tags=[{$TAGS}]" \
         --query 'Instances[0].InstanceId' --output text)
    save instance "$id"
    echo "launched $id; waiting for running"
    aws_ ec2 wait instance-running --instance-ids "$id"
    alloc=$(aws_ ec2 allocate-address --domain vpc --tag-specifications "ResourceType=elastic-ip,Tags=[{$TAGS}]" \
            --query AllocationId --output text)
    aws_ ec2 associate-address --instance-id "$id" --allocation-id "$alloc" > /dev/null
    save eip "$alloc"
    aws_ ec2 wait instance-status-ok --instance-ids "$id"
    echo "ready: ssh -i $KEY_PATH ubuntu@$(ip)"
}

setup() {
    local bucket
    bucket=$(load bucket)
    [[ -n "$bucket" ]] || die "nothing staged; run stage first"
    # Short-lived credentials for the S3 pull, from this machine's session, so
    # the instance never holds long-lived keys.
    local creds
    creds=$("$AWS" sts get-session-token --duration-seconds 3600 \
            --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text)
    read -r AK SK ST <<< "$creds"
    ssh_ "bash -s" <<EOF
set -euo pipefail
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
sudo apt-get -qq update && sudo apt-get -qq install -y python3-venv python3-dev cmake build-essential tmux unzip > /dev/null
if ! command -v aws > /dev/null; then
    curl -sS -o /tmp/awscli.zip https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip
    unzip -q -o /tmp/awscli.zip -d /tmp && sudo /tmp/aws/install > /dev/null
fi
AWS_ACCESS_KEY_ID=$AK AWS_SECRET_ACCESS_KEY=$SK AWS_SESSION_TOKEN=$ST \
    aws --region $REGION s3 sync s3://$bucket ~/assets --only-show-errors
[[ -d vrgrid-26 ]] || git clone -q $REPO
cd vrgrid-26 && git pull -q
python3 -m venv .venv && source .venv/bin/activate
pip -q install --upgrade pip
pip -q install -e ".[dev]"
[[ -d ~/patchwork-plusplus ]] || git clone -q --depth 1 https://github.com/url-kaist/patchwork-plusplus.git ~/patchwork-plusplus
pip -q install ~/patchwork-plusplus/python
pip -q install cupy-cuda12x torch
python -c "import cupy, torch; print('cupy', cupy.__version__, cupy.cuda.runtime.getDeviceProperties(0)['name']); print('torch', torch.__version__, torch.cuda.get_device_name(0))"
VRGRID_ASSETS=~/assets source scripts/env.sh
python scripts/data_status.py || true
python -m pytest -q -p no:cacheprovider 2>&1 | tail -3
EOF
}

run() {
    ssh_ "bash -s" <<'EOF'
set -euo pipefail
cd vrgrid-26 && source .venv/bin/activate && VRGRID_ASSETS=~/assets source scripts/env.sh
mkdir -p results/t4
{ nvidia-smi; nvcc --version 2>/dev/null || true; lscpu | head -20; } > results/t4/host.log
python scripts/timing_table.py --seq 08 --frames 200 --device cpu  > results/t4/timing_cpu.log  2>&1
python scripts/timing_table.py --seq 08 --frames 200 --device cuda > results/t4/timing_cuda.log 2>&1
python scripts/gpu_parity.py   --seq 08 --frames 200               > results/t4/parity.log       2>&1
python scripts/vram_contention.py --seq 08 --frames 200 --pair-seconds 40 \
       --out results/t4/vram-contention.json                       > results/t4/vram_contention.log 2>&1
python scripts/frnet_eval.py --seq 08 --frames 200 --fast-scatter  > results/t4/frnet_eval.log   2>&1
echo done
EOF
}

fetch() {
    mkdir -p "$HERE/docs/gpu-lane/t4"
    scp -i "$KEY_PATH" "ubuntu@$(ip):vrgrid-26/results/t4/*.{log,json}" "$HERE/docs/gpu-lane/t4/"
    ls -la "$HERE/docs/gpu-lane/t4"
}

status() {
    local id
    id=$(load instance)
    [[ -n "$id" ]] || { echo "no instance recorded"; return; }
    aws_ ec2 describe-instances --instance-ids "$id" \
        --query 'Reservations[0].Instances[0].[InstanceId,State.Name,InstanceType,PublicIpAddress]' --output text
}

case "${1:-}" in
    preflight) preflight ;;
    budget) budget ;;
    stage) stage ;;
    launch) launch ;;
    setup) setup ;;
    run) run ;;
    fetch) fetch ;;
    ssh) ssh_ -t "tmux new -A -s vrgrid" ;;
    status) status ;;
    stop) aws_ ec2 stop-instances --instance-ids "$(load instance)" --output text ;;
    start) aws_ ec2 start-instances --instance-ids "$(load instance)" --output text
           aws_ ec2 wait instance-running --instance-ids "$(load instance)"; status ;;
    *) sed -n '2,17p' "$0"; exit 1 ;;
esac
