"""Fixed limits for the NanoEvo V1 control plane."""

EVOLUTION_SCHEMA_VERSION = 1

REVIEW_EVERY_N_TRAJECTORIES = 10
REVIEW_INTERVAL_OPTIONS = (5, 10, 20, 100)
REVIEW_TRAJECTORY_WINDOW = 10
REVIEW_MAX_ITERATIONS = 8
# Large marketplace Skills can take longer to review because the isolated
# reviewer must inspect their exact text before proposing a safe replacement.
REVIEW_TIMEOUT_SECONDS = 180
MAX_PROPOSALS_PER_REVIEW = 1

MAX_TOOL_RESULT_CHARS = 4_000
MAX_FINAL_RESPONSE_CHARS = 4_000
MAX_PATCH_CHARS = 8_000
# A reviewer must see the exact Skill text to build an old_text/new_text patch.
# Marketplace Skills commonly exceed 16K characters, so the review-only runner
# needs a larger result budget than ordinary agent tools.
REVIEW_MAX_TOOL_RESULT_CHARS = 64_000
REVIEW_FINAL_EXCERPT_BUDGET = 8_000

# Redaction is deliberately bounded independently from review input sizes so a
# pathological nested tool payload cannot become a persistence or logging risk.
MAX_REDACTION_DEPTH = 8
MAX_REDACTION_ITEMS = 100
PROJECT_SCOPE_HASH_LENGTH = 16

REDACTED_VALUE = "[REDACTED]"
TRUNCATED_SUFFIX = "\n... (truncated)"
