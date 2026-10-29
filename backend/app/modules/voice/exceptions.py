class VoiceError(Exception):
    """Carries the contract error code; detail never includes internal causes."""

    status_code = 400
    code = "invalid_request"
    detail = "요청 형식이 올바르지 않습니다."


class VoiceSessionNotFound(VoiceError):
    status_code = 404
    code = "session_not_found"
    detail = "세션을 찾을 수 없습니다."


class VoiceSessionCompleted(VoiceError):
    status_code = 410
    code = "session_expired"
    detail = "새 이용 세션을 시작해 주세요."


class VoiceRequestNotFound(VoiceError):
    status_code = 404
    code = "voice_request_not_found"
    detail = "음성 요청을 찾을 수 없습니다."


class RequestInProgress(VoiceError):
    status_code = 409
    code = "request_in_progress"
    detail = "이전 음성 요청을 처리하고 있습니다."


class IdempotencyKeyReused(VoiceError):
    status_code = 409
    code = "idempotency_key_reused"
    detail = "같은 키로 다른 요청을 보냈습니다."
