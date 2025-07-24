#!/bin/bash

# Ensure logging directory exists
mkdir -p /coin-forge

# Log function for better readability
log() { echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" >> /coin-forge/health-script.log; }

log "---- Script started ----"

set -euo pipefail

# Log file configuration
LOG_FILE="/coin-forge/health-script.log"
MAX_LOG_SIZE=$((5 * 1024 * 1024))  # 5 MB

# Check if the log file exceeds the maximum size and handle it
if [[ -f "$LOG_FILE" && $(stat -c%s "$LOG_FILE") -gt $MAX_LOG_SIZE ]]; then
    log "Log file size exceeded $MAX_LOG_SIZE bytes. Deleting and recreating the log file."
    rm -f "$LOG_FILE"
    touch "$LOG_FILE"
fi

# Check if cfg.json exists
if [[ ! -f "/coin-forge/cfg.json" ]]; then
    log "Error: cfg.json file not found."
    exit 1
fi

# Parse cfg.json without jq (safe assignments)
CONTROLLER_IP=""
TARGET_URL=""
DEVICE_HOSTNAME=""

CONTROLLER_IP=$(grep '"CONTROLLER_IP"' /coin-forge/cfg.json | awk -F'"' '{print $4}') || CONTROLLER_IP=""
TARGET_URL=$(grep '"TARGET_URL"' /coin-forge/cfg.json | awk -F'"' '{print $4}') || TARGET_URL=""
DEVICE_HOSTNAME=$(grep '"COIN_FORGE_HOST"' /coin-forge/cfg.json | awk -F'"' '{print $4}') || DEVICE_HOSTNAME=""

log "CONTROLLER_IP: ${CONTROLLER_IP:-}"
log "TARGET_URL: ${TARGET_URL:-}"
log "DEVICE_HOSTNAME: ${DEVICE_HOSTNAME:-}"

if [[ -z "${CONTROLLER_IP:-}" || -z "${TARGET_URL:-}" ]]; then
    log "Error: CONTROLLER_IP or TARGET_URL is missing in cfg.json."
    exit 1
fi

if [[ -z "${DEVICE_HOSTNAME:-}" ]]; then
    DEVICE_HOSTNAME=$(hostname)
    log "DEVICE_HOSTNAME not found in cfg.json, using system hostname: $DEVICE_HOSTNAME"
fi

# Get primary IP address (IPv4, non-loopback)
DEVICE_IP=""
DEVICE_IP=$(/sbin/ifconfig | awk '/inet addr:/{if ($2 != "127.0.0.1") print $2}' | head -n1 | cut -d: -f2)
log "DEVICE_IP: ${DEVICE_IP:-}"
if [[ -z "${DEVICE_IP:-}" ]]; then
    log "Error: Unable to determine DEVICE_IP."
    exit 1
fi

# Get primary interface name
PRIMARY_IF=""
PRIMARY_IF=$(ip route | awk '/default/ {print $5; exit}') || PRIMARY_IF=""
log "PRIMARY_IF: ${PRIMARY_IF:-}"
if [[ -z "${PRIMARY_IF:-}" ]]; then
    log "Error: Unable to determine PRIMARY_IF."
    exit 1
fi

# Get current CPU utilization (percentage, last 1 min)
CPU_LINE=""
CPU_IDLE=""
CPU_UTIL=""
CPU_LINE=$(top -bn2 | grep "Cpu(s)" | tail -n 1) || CPU_LINE=""
CPU_IDLE=$(echo "$CPU_LINE" | awk '{for(i=1;i<=NF;i++) if ($i ~ /id,/) print $(i-1)}' | sed 's/,//') || CPU_IDLE=""
if [[ -z "${CPU_IDLE:-}" ]]; then
    CPU_IDLE=$(echo "$CPU_LINE" | awk '{print $8}') || CPU_IDLE="0.0"
fi
CPU_UTIL=$(awk -v idle="${CPU_IDLE:-0.0}" 'BEGIN {printf "%.1f", 100 - idle}') || CPU_UTIL="0.0"
log "CPU_UTIL: $CPU_UTIL (Idle: $CPU_IDLE)"

# Get current memory usage (used/total in MB)
MEM_TOTAL=""
MEM_USED=""
MEM_TOTAL=$(free -m | awk '/Mem:/ {print $2}') || MEM_TOTAL="0"
MEM_USED=$(free -m | awk '/Mem:/ {print $3}') || MEM_USED="0"
log "MEM_TOTAL: $MEM_TOTAL"
log "MEM_USED: $MEM_USED"

# Get total bytes in and out on primary interface
BYTES_IN=""
BYTES_OUT=""
BYTES_IN=$(cat /proc/net/dev | awk -v iface="$PRIMARY_IF" '$1 ~ iface":" {gsub(/:/,"",$1); print $2}') || BYTES_IN="0"
BYTES_OUT=$(cat /proc/net/dev | awk -v iface="$PRIMARY_IF" '$1 ~ iface":" {gsub(/:/,"",$1); print $10}') || BYTES_OUT="0"
log "BYTES_IN: $BYTES_IN"
log "BYTES_OUT: $BYTES_OUT"

if [[ -z "${BYTES_IN:-}" || -z "${BYTES_OUT:-}" ]]; then
    log "Error: Unable to fetch network byte counts."
    exit 1
fi

# Check reachability
log "Testing reachability of $TARGET_URL..."
REACHABLE=false
if curl --silent --head "$TARGET_URL" > /dev/null; then
    log "Successfully reached $TARGET_URL. Preparing to send health-check to $CONTROLLER_IP..."
    REACHABLE=true
else
    log "Error: Failed to reach $TARGET_URL."
fi

# Prepare JSON payload
PAYLOAD=$(cat <<EOF
{
  "ip": "$DEVICE_IP",
  "hostname": "$DEVICE_HOSTNAME",
  "cpu_utilization": "$CPU_UTIL",
  "memory_used_mb": "$MEM_USED",
  "memory_total_mb": "$MEM_TOTAL",
  "network_bytes_in": "$BYTES_IN",
  "network_bytes_out": "$BYTES_OUT",
  "remote_connection": $REACHABLE
}
EOF
)
log "Payload prepared: $PAYLOAD"

# POST data to health-check endpoint and capture response
HEALTH_CHECK_URL="http://$CONTROLLER_IP:5000/health-check"
log "Sending POST request to $HEALTH_CHECK_URL"

HTTP_RESPONSE_BODY=""
HTTP_STATUS_CODE=""
HTTP_RESPONSE_TMP=$(mktemp)

# Send POST and capture the HTTP status and body
HTTP_STATUS_CODE=$(curl --silent --show-error --fail -X POST \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    -w "%{http_code}" \
    -o "$HTTP_RESPONSE_TMP" \
    "$HEALTH_CHECK_URL" 2>>"$LOG_FILE")

HTTP_RESPONSE_BODY=$(cat "$HTTP_RESPONSE_TMP")
rm -f "$HTTP_RESPONSE_TMP"

log "HTTP response code: $HTTP_STATUS_CODE"
log "HTTP response body: $HTTP_RESPONSE_BODY"

if [[ "$HTTP_STATUS_CODE" -ne 200 ]]; then
    log "Error: Health-check POST failed with HTTP status $HTTP_STATUS_CODE."
    exit 1
fi

# Extract 'initiate_incident' value from JSON (true/false)
INITIATE_INCIDENT=$(echo "$HTTP_RESPONSE_BODY" | grep -o '"initiate_incident":[ ]*\(true\|false\)' | head -n1 | awk -F: '{gsub(/[ \t]/,"",$2); print $2}')
log "initiate_incident in response: $INITIATE_INCIDENT"

if [[ "$INITIATE_INCIDENT" == "true" ]]; then
    log "initiate_incident is true! Updating cfg.json and notifying controller..."

    # Update /coin-forge/cfg.json: set INITIATE_ATTACK to true
    CFG_FILE="/coin-forge/cfg.json"
    TMP_CFG=$(mktemp)

    # Replace the value for INITIATE_ATTACK (whether true or false) with true
    # Handles both "INITIATE_ATTACK":false and "INITIATE_ATTACK": false
    sed -E 's/("INITIATE_ATTACK"[ ]*:[ ]*)false/\1true/' "$CFG_FILE" > "$TMP_CFG"
    mv "$TMP_CFG" "$CFG_FILE"
    log "Updated /coin-forge/cfg.json: INITIATE_ATTACK set to true."

    # Notify controller via attack-initiated endpoint
    ATTACK_INITIATED_URL="http://$CONTROLLER_IP:5000/attack-initiated"
    ATTACK_RESP=$(curl --silent --show-error --fail -X POST "$ATTACK_INITIATED_URL" -H "Content-Type: application/json" -d '{}' 2>>"$LOG_FILE" || echo "error")
    log "Sent POST to $ATTACK_INITIATED_URL. Response: $ATTACK_RESP"
else
    log "initiate_incident is not true; nothing to do."
fi

log "Health-check script completed successfully."