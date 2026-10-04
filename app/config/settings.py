from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal


class Settings(BaseSettings):
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    deepgram_api_key: str = Field("", env="DEEPGRAM_API_KEY")
    elevenlabs_api_key: str = Field("", env="ELEVENLABS_API_KEY")

    primary_llm_model: str = Field("claude-haiku-4-5", env="PRIMARY_LLM_MODEL")
    fallback_llm_model: str = Field("claude-sonnet-4-5", env="FALLBACK_LLM_MODEL")

    stt_provider: Literal["deepgram", "local"] = Field("deepgram", env="STT_PROVIDER")
    tts_provider: Literal["elevenlabs", "local"] = Field("elevenlabs", env="TTS_PROVIDER")

    audio_sample_rate: int = Field(16000, env="AUDIO_SAMPLE_RATE")
    audio_channels: int = Field(1, env="AUDIO_CHANNELS")
    audio_frame_ms: int = Field(20, env="AUDIO_FRAME_MS")

    silence_timeout_ms: int = Field(800, env="SILENCE_TIMEOUT_MS")
    number_silence_timeout_ms: int = Field(2000, env="NUMBER_SILENCE_TIMEOUT_MS")
    barge_in_min_duration_ms: int = Field(300, env="BARGE_IN_MIN_DURATION_MS")
    end_of_turn_confidence_threshold: float = Field(0.6, env="END_OF_TURN_CONFIDENCE_THRESHOLD")
    stt_low_confidence_threshold: float = Field(0.5, env="STT_LOW_CONFIDENCE_THRESHOLD")

    max_verification_attempts: int = Field(3, env="MAX_VERIFICATION_ATTEMPTS")
    max_clarification_attempts: int = Field(2, env="MAX_CLARIFICATION_ATTEMPTS")
    max_tool_retries: int = Field(2, env="MAX_TOOL_RETRIES")
    max_call_duration_seconds: int = Field(600, env="MAX_CALL_DURATION_SECONDS")
    max_idle_seconds: int = Field(30, env="MAX_IDLE_SECONDS")
    max_concurrent_sessions: int = Field(20, env="MAX_CONCURRENT_SESSIONS")
    max_frame_bytes: int = Field(65536, env="MAX_FRAME_BYTES")

    promise_max_days_ahead: int = Field(30, env="PROMISE_MAX_DAYS_AHEAD")
    promise_min_amount: float = Field(100.0, env="PROMISE_MIN_AMOUNT")
    due_date_change_max_days: int = Field(10, env="DUE_DATE_CHANGE_MAX_DAYS")
    overdue_escalation_days: int = Field(90, env="OVERDUE_ESCALATION_DAYS")

    database_url: str = Field("sqlite:///./loan_agent.db", env="DATABASE_URL")

    agent_name: str = Field("Priya", env="AGENT_NAME")
    company_name: str = Field("Nova Finance", env="COMPANY_NAME")

    elevenlabs_voice_id: str = Field("EXAVITQu4vr4xnSDxMaL", env="ELEVENLABS_VOICE_ID")
    deepgram_language: str = Field("en-IN", env="DEEPGRAM_LANGUAGE")
    deepgram_model: str = Field("nova-2", env="DEEPGRAM_MODEL")

    log_level: str = Field("INFO", env="LOG_LEVEL")
    replay_store_path: str = Field("./replay_store", env="REPLAY_STORE_PATH")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
