#!/usr/bin/env bash
# The whole approved T4 pass, unattended, stopping at the first failure. [Shrestha]
#
#   scripts/aws/auto.sh labelled
#
# 1. wait (every 10 min, up to 24 h) until EC2 and S3 answer on this account
#    AND the G/VT vCPU quota is at least 4 -- a new account starts at 0, and
#    that is what actually blocks a g4dn.xlarge once the services are on
# 2. preflight + an EC2 dry-run launch -- both free; a refusal ends it here,
#    before a byte is uploaded
# 3. stage the chosen data to S3, then launch, setup, run (which fetches the
#    results and STOPS the instance)
# Every spending guardrail lives in t4.sh; this only sequences it.
set -euo pipefail
which="${1:?labelled or all}"
HERE="$(cd "$(dirname "$0")" && pwd)"
AWS="${AWS:-$HOME/.local/bin/aws}"
log() { echo "[$(date -u +%FT%TZ)] $*"; }

# The G and VT on-demand vCPU quota, or 0 if the call itself fails.
quota() {
    "$AWS" --region ap-south-1 service-quotas get-service-quota --service-code ec2 \
        --quota-code L-DB2E81BA --query 'Quota.Value' --output text 2>/dev/null || echo 0
}

for i in $(seq 1 144); do
    if "$AWS" --region ap-south-1 ec2 describe-availability-zones > /dev/null 2>&1 \
       && "$AWS" --region ap-south-1 s3api list-buckets > /dev/null 2>&1; then
        q=$(quota)
        if awk "BEGIN{exit !($q >= 4)}"; then
            log "EC2 and S3 active, G/VT vCPU quota $q"; break
        fi
        log "EC2 and S3 active, but G/VT vCPU quota is $q -- waiting for the increase to 4"
    fi
    [[ $i == 144 ]] && { log "not ready after 24 h -- check the quota request and contact AWS support"; exit 2; }
    sleep 600
done

log "preflight";  "$HERE/t4.sh" preflight
log "dry run";    "$HERE/t4.sh" dryrun
log "stage $which"; "$HERE/t4.sh" stage "$which"
log "launch";     "$HERE/t4.sh" launch
log "setup";      "$HERE/t4.sh" setup
log "run";        "$HERE/t4.sh" run
log "done -- results in docs/gpu-lane/t4, instance stopped"
"$HERE/t4.sh" status
