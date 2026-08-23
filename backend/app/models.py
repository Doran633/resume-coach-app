from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class AnonymousUser(Base):
    __tablename__ = "anonymous_users"

    id = Column(Integer, primary_key=True, index=True)
    anonymous_id = Column(String(64), unique=True, index=True, nullable=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(String(128), nullable=True)
    user_agent = Column(String(512), nullable=True)

    sessions = relationship("SessionRecord", back_populates="anonymous_user")


class SessionRecord(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), index=True, nullable=False)
    anonymous_user_id = Column(Integer, ForeignKey("anonymous_users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)

    anonymous_user = relationship("AnonymousUser", back_populates="sessions")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    anonymous_user_id = Column(Integer, ForeignKey("anonymous_users.id"), nullable=True)
    session_id = Column(String(64), index=True, nullable=False)
    event_name = Column(String(128), index=True, nullable=False)
    target_role = Column(String(128), nullable=True)
    mode = Column(String(64), nullable=True)
    packaging_level = Column(String(64), nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ExperienceInput(Base):
    __tablename__ = "experience_inputs"

    id = Column(Integer, primary_key=True, index=True)
    anonymous_user_id = Column(Integer, ForeignKey("anonymous_users.id"), nullable=True)
    session_id = Column(String(64), index=True, nullable=False)
    target_role = Column(String(128), nullable=False)
    mode = Column(String(64), nullable=False)
    packaging_level = Column(String(64), nullable=False)
    experience_type = Column(String(64), nullable=False)
    raw_input = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GenerationResult(Base):
    __tablename__ = "generation_results"

    id = Column(Integer, primary_key=True, index=True)
    experience_input_id = Column(Integer, ForeignKey("experience_inputs.id"), nullable=False)
    completeness_score = Column(Integer, nullable=False)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    generation_result_id = Column(Integer, ForeignKey("generation_results.id"), nullable=False)
    claim = Column(Text, nullable=False)
    risk_level = Column(String(16), nullable=False)
    evidence = Column(Text, nullable=True)
    risk_reason = Column(Text, nullable=True)
    interview_questions_json = Column(Text, nullable=True)
    knowledge_json = Column(Text, nullable=True)
    downgrade_wording = Column(Text, nullable=True)


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id = Column(Integer, primary_key=True, index=True)
    generation_result_id = Column(Integer, ForeignKey("generation_results.id"), nullable=True)
    model = Column(String(128), nullable=True)
    mode = Column(String(32), nullable=False)
    latency_ms = Column(Integer, nullable=True)
    success = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id = Column(Integer, primary_key=True, index=True)
    generation_result_id = Column(Integer, ForeignKey("generation_results.id"), nullable=False)
    version_type = Column(String(32), nullable=False)
    content_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GeneratedFile(Base):
    __tablename__ = "generated_files"

    id = Column(Integer, primary_key=True, index=True)
    resume_version_id = Column(Integer, ForeignKey("resume_versions.id"), nullable=True)
    generation_result_id = Column(Integer, ForeignKey("generation_results.id"), nullable=False)
    file_type = Column(String(16), nullable=False)
    file_path = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    anonymous_user_id = Column(Integer, ForeignKey("anonymous_users.id"), nullable=True)
    session_id = Column(String(64), index=True, nullable=False)
    generation_result_id = Column(Integer, ForeignKey("generation_results.id"), nullable=True)
    model_comparison = Column(String(64), nullable=False)
    value_choice = Column(String(32), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
