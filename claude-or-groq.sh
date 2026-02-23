#!/usr/bin/env bash
set -euo pipefail

# Claude-mode switchable wrapper for Anthropic / Groq / OpenRouter
#
# Examples:
#   ./claude-or-groq.sh --set-source groq
#   ./claude-or-groq.sh --show-config
#   ./claude-or-groq.sh "What is the capital of France?"
#
# Claude mode source can be switched between:
#   anthropic (real Claude), groq, openrouter
# The script tries the selected source first, then falls back to the others.

APP_NAME="claude-or-groq"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/sanaa"
CONFIG_FILE="${CLAUDE_OR_GROQ_CONFIG:-$CONFIG_DIR/claude-or-groq.env}"
TIMEOUT="${TIMEOUT:-45}"
SANAA_ENGINE_URL="${SANAA_ENGINE_URL:-http://127.0.0.1:8101/api}"
SANAA_ENGINE_KEY="${SANAA_ENGINE_KEY:-}"
SANAA_ADMIN_SYNC="${SANAA_ADMIN_SYNC:-1}"

# Runtime-configurable defaults
CLAUDE_SOURCE_DEFAULT="anthropic"
CLAUDE_SOURCE="${CLAUDE_SOURCE:-$CLAUDE_SOURCE_DEFAULT}"

ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-${CLAUDE_API_KEY:-}}"
GROQ_API_KEY="${GROQ_API_KEY:-}"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"

ANTHROPIC_ENDPOINT="${ANTHROPIC_ENDPOINT:-https://api.anthropic.com/v1/messages}"
GROQ_ENDPOINT="${GROQ_ENDPOINT:-https://api.groq.com/openai/v1/chat/completions}"
OPENROUTER_ENDPOINT="${OPENROUTER_ENDPOINT:-https://openrouter.ai/api/v1/chat/completions}"

ANTHROPIC_MODEL_FAST="${ANTHROPIC_MODEL_FAST:-claude-3-haiku-20240307}"
ANTHROPIC_MODEL_PREMIUM="${ANTHROPIC_MODEL_PREMIUM:-claude-3-5-sonnet-20240620}"
GROQ_MODEL="${GROQ_MODEL:-llama-3.3-70b-versatile}"
OPENROUTER_MODEL="${OPENROUTER_MODEL:-openrouter/auto}"

HTTP_STATUS=""
HTTP_BODY=""
HTTP_ERR=""
ADMIN_PROVIDER=""
ADMIN_CLAUDE_SOURCE=""
ADMIN_AUTO_ORDER=""
ADMIN_SYNC_ACTIVE="no"
ADMIN_SYNC_LAST_ERROR=""

usage() {
  cat <<'EOF'
Usage:
  ./claude-or-groq.sh [options] "Your prompt"

Options:
  --set-source <anthropic|groq|openrouter>   Persist Claude-mode source
  --source <anthropic|groq|openrouter>       Use source for this run only
  --show-config                              Show effective config (no secrets)
  --self-test                                Validate dependencies and key presence
  --no-admin-sync                            Ignore Sanaa admin brain setting for this run
  -h, --help                                 Show help

Environment (keys):
  ANTHROPIC_API_KEY or CLAUDE_API_KEY
  GROQ_API_KEY
  OPENROUTER_API_KEY

Environment (Sanaa admin sync):
  SANAA_ENGINE_URL   (default: http://127.0.0.1:8101/api)
  SANAA_ENGINE_KEY   (Bearer token for Sanaa backend API)
  SANAA_ADMIN_SYNC   (1 default, set 0 to disable)
EOF
}

require_bin() {
  local bin="$1"
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "Missing dependency: $bin" >&2
    exit 1
  fi
}

load_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
  fi
}

persist_source() {
  local source="$1"
  mkdir -p "$CONFIG_DIR"
  cat > "$CONFIG_FILE" <<EOF
# $APP_NAME config
CLAUDE_SOURCE=$source
EOF
  echo "Saved Claude mode source: $source"
}

normalize_source() {
  local source="${1:-}"
  case "${source,,}" in
    anthropic|groq|openrouter) printf '%s\n' "${source,,}" ;;
    *) return 1 ;;
  esac
}

show_config() {
  cat <<EOF
Config file: $CONFIG_FILE
Claude mode source: ${CLAUDE_SOURCE}
Timeout: ${TIMEOUT}s
Sanaa admin sync: ${ADMIN_SYNC_ACTIVE}
Sanaa engine URL: ${SANAA_ENGINE_URL}
Sanaa engine key configured: $( [[ -n "$SANAA_ENGINE_KEY" ]] && echo yes || echo no )
Sanaa admin provider: ${ADMIN_PROVIDER:-unknown}
Sanaa admin claude_source: ${ADMIN_CLAUDE_SOURCE:-unknown}
Sanaa admin auto order: ${ADMIN_AUTO_ORDER:-unknown}

Providers:
  anthropic endpoint: $ANTHROPIC_ENDPOINT
  anthropic fast model: $ANTHROPIC_MODEL_FAST
  anthropic premium model: $ANTHROPIC_MODEL_PREMIUM
  anthropic key configured: $( [[ -n "$ANTHROPIC_API_KEY" ]] && echo yes || echo no )

  groq endpoint: $GROQ_ENDPOINT
  groq model: $GROQ_MODEL
  groq key configured: $( [[ -n "$GROQ_API_KEY" ]] && echo yes || echo no )

  openrouter endpoint: $OPENROUTER_ENDPOINT
  openrouter model: $OPENROUTER_MODEL
  openrouter key configured: $( [[ -n "$OPENROUTER_API_KEY" ]] && echo yes || echo no )
EOF
}

self_test() {
  require_bin curl
  require_bin jq
  fetch_admin_brain_config >/dev/null 2>&1 || true
  show_config
  echo
  echo "Dependency check: OK"
  echo "Ready for live query if at least one provider key is configured."
}

http_get() {
  local url="$1"
  shift

  local body_file err_file curl_rc
  body_file="$(mktemp)"
  err_file="$(mktemp)"

  set +e
  HTTP_STATUS="$(curl -sS -m "$TIMEOUT" -o "$body_file" -w '%{http_code}' "$url" "$@" 2>"$err_file")"
  curl_rc=$?
  set -e

  HTTP_BODY="$(cat "$body_file")"
  HTTP_ERR="$(cat "$err_file")"
  rm -f "$body_file" "$err_file"

  if [[ $curl_rc -ne 0 ]]; then
    return $curl_rc
  fi
  return 0
}

http_post_json() {
  local url="$1"
  shift
  local payload="$1"
  shift

  local body_file err_file curl_rc
  body_file="$(mktemp)"
  err_file="$(mktemp)"

  set +e
  HTTP_STATUS="$(curl -sS -m "$TIMEOUT" -o "$body_file" -w '%{http_code}' "$url" "$@" \
    -H "Content-Type: application/json" \
    -d "$payload" 2>"$err_file")"
  curl_rc=$?
  set -e

  HTTP_BODY="$(cat "$body_file")"
  HTTP_ERR="$(cat "$err_file")"
  rm -f "$body_file" "$err_file"

  if [[ $curl_rc -ne 0 ]]; then
    return $curl_rc
  fi
  return 0
}

fetch_admin_brain_config() {
  ADMIN_SYNC_ACTIVE="no"
  ADMIN_SYNC_LAST_ERROR=""
  ADMIN_PROVIDER=""
  ADMIN_CLAUDE_SOURCE=""
  ADMIN_AUTO_ORDER=""

  [[ "$SANAA_ADMIN_SYNC" == "1" ]] || { ADMIN_SYNC_LAST_ERROR="disabled"; return 1; }
  [[ -n "$SANAA_ENGINE_KEY" ]] || { ADMIN_SYNC_LAST_ERROR="missing SANAA_ENGINE_KEY"; return 1; }

  if ! http_get "${SANAA_ENGINE_URL%/}/system/brain/config" \
    -H "Authorization: Bearer $SANAA_ENGINE_KEY"; then
    ADMIN_SYNC_LAST_ERROR="curl error: ${HTTP_ERR:-unknown}"
    return 1
  fi

  if [[ ! "$HTTP_STATUS" =~ ^2[0-9]{2}$ ]]; then
    ADMIN_SYNC_LAST_ERROR="HTTP $HTTP_STATUS"
    return 1
  fi

  ADMIN_PROVIDER="$(printf '%s\n' "$HTTP_BODY" | jq -r '.provider // .current_provider // empty' 2>/dev/null || true)"
  ADMIN_CLAUDE_SOURCE="$(printf '%s\n' "$HTTP_BODY" | jq -r '.claude_source // empty' 2>/dev/null || true)"
  ADMIN_AUTO_ORDER="$(printf '%s\n' "$HTTP_BODY" | jq -r '.auto_provider_order // empty' 2>/dev/null || true)"
  ADMIN_SYNC_ACTIVE="yes"
  return 0
}

pick_source_from_auto_order() {
  local raw="${1:-}"
  local item
  local -a items=()
  IFS=',' read -r -a items <<< "$raw"
  for item in "${items[@]}"; do
    item="$(printf '%s' "$item" | tr '[:upper:]' '[:lower:]')"
    item="${item#"${item%%[![:space:]]*}"}"
    item="${item%"${item##*[![:space:]]}"}"
    case "$item" in
      anthropic|groq|openrouter)
        printf '%s\n' "$item"
        return 0
        ;;
    esac
  done
  return 1
}

sync_source_from_admin_if_available() {
  if ! fetch_admin_brain_config; then
    return 1
  fi

  case "${ADMIN_PROVIDER:-}" in
    claude)
      if normalized="$(normalize_source "${ADMIN_CLAUDE_SOURCE:-}")"; then
        CLAUDE_SOURCE="$normalized"
      fi
      ;;
    groq|openrouter)
      CLAUDE_SOURCE="${ADMIN_PROVIDER}"
      ;;
    auto)
      if picked="$(pick_source_from_auto_order "${ADMIN_AUTO_ORDER:-}")"; then
        CLAUDE_SOURCE="$picked"
      fi
      ;;
    *)
      # local/unknown: keep local persisted source
      ;;
  esac

  return 0
}

push_source_to_admin() {
  local source="$1"

  [[ "$SANAA_ADMIN_SYNC" == "1" ]] || return 1
  [[ -n "$SANAA_ENGINE_KEY" ]] || return 1

  local payload
  payload="$(jq -n --arg source "$source" '{provider:"claude", claude_source:$source}')"

  if ! http_post_json "${SANAA_ENGINE_URL%/}/system/brain/config" "$payload" \
    -X POST \
    -H "Authorization: Bearer $SANAA_ENGINE_KEY"; then
    ADMIN_SYNC_LAST_ERROR="curl error: ${HTTP_ERR:-unknown}"
    return 1
  fi

  if [[ ! "$HTTP_STATUS" =~ ^2[0-9]{2}$ ]]; then
    ADMIN_SYNC_LAST_ERROR="HTTP $HTTP_STATUS"
    return 1
  fi

  ADMIN_SYNC_ACTIVE="yes"
  ADMIN_PROVIDER="claude"
  ADMIN_CLAUDE_SOURCE="$source"
  return 0
}

call_anthropic() {
  local prompt="$1"
  [[ -n "$ANTHROPIC_API_KEY" ]] || return 10

  local payload
  payload="$(jq -n \
    --arg model "$ANTHROPIC_MODEL_PREMIUM" \
    --arg prompt "$prompt" \
    '{
      model: $model,
      max_tokens: 1024,
      temperature: 0.3,
      messages: [{role:"user", content:$prompt}]
    }')"

  http_post_json "$ANTHROPIC_ENDPOINT" "$payload" \
    -X POST \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01"
}

call_groq() {
  local prompt="$1"
  [[ -n "$GROQ_API_KEY" ]] || return 10

  local payload
  payload="$(jq -n \
    --arg model "$GROQ_MODEL" \
    --arg prompt "$prompt" \
    '{
      model: $model,
      temperature: 0.3,
      max_tokens: 1024,
      messages: [{role:"user", content:$prompt}]
    }')"

  http_post_json "$GROQ_ENDPOINT" "$payload" \
    -X POST \
    -H "Authorization: Bearer $GROQ_API_KEY"
}

call_openrouter() {
  local prompt="$1"
  [[ -n "$OPENROUTER_API_KEY" ]] || return 10

  local payload
  payload="$(jq -n \
    --arg model "$OPENROUTER_MODEL" \
    --arg prompt "$prompt" \
    '{
      model: $model,
      temperature: 0.3,
      max_tokens: 1024,
      messages: [{role:"user", content:$prompt}]
    }')"

  http_post_json "$OPENROUTER_ENDPOINT" "$payload" \
    -X POST \
    -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    -H "HTTP-Referer: https://ai.sanaa.co" \
    -H "X-Title: Sanaa Claude Mode Wrapper"
}

extract_reply() {
  local provider="$1"
  local body="$2"
  case "$provider" in
    anthropic)
      printf '%s\n' "$body" | jq -r '.content[]? | select(.type=="text") | .text' ;;
    groq|openrouter)
      printf '%s\n' "$body" | jq -r '.choices[0].message.content // .choices[].message.content' ;;
    *)
      return 1 ;;
  esac
}

provider_order_for_source() {
  case "$1" in
    anthropic) printf '%s\n' "anthropic groq openrouter" ;;
    groq) printf '%s\n' "groq anthropic openrouter" ;;
    openrouter) printf '%s\n' "openrouter anthropic groq" ;;
    *) return 1 ;;
  esac
}

run_provider() {
  local provider="$1"
  local prompt="$2"
  local rc=0

  case "$provider" in
    anthropic) call_anthropic "$prompt" || rc=$? ;;
    groq) call_groq "$prompt" || rc=$? ;;
    openrouter) call_openrouter "$prompt" || rc=$? ;;
    *) echo "Unknown provider: $provider" >&2; return 1 ;;
  esac

  if [[ $rc -eq 10 ]]; then
    echo "[$provider] skipped (missing API key)" >&2
    return 10
  fi
  if [[ $rc -ne 0 ]]; then
    echo "[$provider] curl error: ${HTTP_ERR:-unknown}" >&2
    return 1
  fi

  if [[ ! "$HTTP_STATUS" =~ ^2[0-9]{2}$ ]]; then
    echo "[$provider] HTTP $HTTP_STATUS" >&2
    if [[ -n "$HTTP_BODY" ]]; then
      printf '%s\n' "$HTTP_BODY" | jq . 2>/dev/null || printf '%s\n' "$HTTP_BODY" >&2
    fi
    return 1
  fi

  return 0
}

main() {
  require_bin curl
  require_bin jq

  load_config

  local one_off_source="" set_source="" do_show=0 do_self_test=0 no_admin_sync=0
  local -a prompt_parts=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --set-source)
        [[ $# -ge 2 ]] || { echo "--set-source requires a value" >&2; exit 1; }
        set_source="$(normalize_source "$2")" || { echo "Invalid source: $2" >&2; exit 1; }
        shift 2
        ;;
      --source)
        [[ $# -ge 2 ]] || { echo "--source requires a value" >&2; exit 1; }
        one_off_source="$(normalize_source "$2")" || { echo "Invalid source: $2" >&2; exit 1; }
        shift 2
        ;;
      --show-config)
        do_show=1; shift ;;
      --self-test)
        do_self_test=1; shift ;;
      --no-admin-sync)
        no_admin_sync=1; shift ;;
      -h|--help)
        usage; exit 0 ;;
      --)
        shift
        while [[ $# -gt 0 ]]; do prompt_parts+=("$1"); shift; done
        ;;
      *)
        prompt_parts+=("$1"); shift ;;
    esac
  done

  if [[ $no_admin_sync -eq 1 ]]; then
    SANAA_ADMIN_SYNC="0"
  fi

  if [[ -n "$set_source" ]]; then
    persist_source "$set_source"
    if push_source_to_admin "$set_source"; then
      echo "Updated Sanaa admin Claude source: $set_source" >&2
    elif [[ -n "$SANAA_ENGINE_KEY" && "$SANAA_ADMIN_SYNC" == "1" ]]; then
      echo "Warning: could not update Sanaa admin brain config (${ADMIN_SYNC_LAST_ERROR:-unknown})" >&2
    fi
    # Reflect immediately in current run
    CLAUDE_SOURCE="$set_source"
  fi

  if [[ -z "$one_off_source" ]]; then
    sync_source_from_admin_if_available || true
  fi

  if [[ $do_show -eq 1 ]]; then
    show_config
  fi

  if [[ $do_self_test -eq 1 ]]; then
    self_test
  fi

  if [[ ${#prompt_parts[@]} -eq 0 ]]; then
    if [[ $do_show -eq 1 || $do_self_test -eq 1 || -n "$set_source" ]]; then
      exit 0
    fi
    usage
    exit 1
  fi

  local prompt source order provider success=0
  prompt="${prompt_parts[*]}"
  source="${one_off_source:-${CLAUDE_SOURCE:-$CLAUDE_SOURCE_DEFAULT}}"
  source="$(normalize_source "$source")" || { echo "Invalid effective source: $source" >&2; exit 1; }

  echo "Claude mode source: $source" >&2
  if [[ "$ADMIN_SYNC_ACTIVE" == "yes" ]]; then
    echo "Sanaa admin brain provider: ${ADMIN_PROVIDER:-unknown}" >&2
  elif [[ "$SANAA_ADMIN_SYNC" == "1" && -n "$ADMIN_SYNC_LAST_ERROR" ]]; then
    echo "Sanaa admin sync unavailable: ${ADMIN_SYNC_LAST_ERROR}" >&2
  fi
  echo "Prompt: $prompt" >&2

  order="$(provider_order_for_source "$source")"
  for provider in $order; do
    if run_provider "$provider" "$prompt"; then
      echo "[$provider] success (HTTP $HTTP_STATUS)" >&2
      extract_reply "$provider" "$HTTP_BODY"
      success=1
      break
    else
      echo "[$provider] failed, trying next source..." >&2
    fi
  done

  if [[ $success -ne 1 ]]; then
    echo "All providers failed (anthropic/groq/openrouter)." >&2
    exit 1
  fi
}

main "$@"
