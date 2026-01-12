"""
학습 데이터 관련 Pydantic 스키마
"""
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

# ============ FilterLearningData ============
class FilterLearningBase(BaseModel):
    title: str = Field(..., max_length=500)
    filter_type: Optional[str] = Field(None, pattern="^(sensitive|spam|ad|low_quality|custom)$")
    filter_reason: Optional[str] = Field(None, max_length=200)
    keywords_detected: List[str] = []

class FilterLearningCreate(FilterLearningBase):
    user_action: str = Field(..., pattern="^(filtered|approved|auto_filtered)$")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

class FilterLearningResponse(FilterLearningBase):
    id: int
    title_hash: str
    user_action: str
    confidence: float
    is_trained: bool
    created_at: datetime
    class Config:
        from_attributes = True

class FilterLearningStats(BaseModel):
    """필터링 학습 통계"""
    total_count: int
    filtered_count: int
    approved_count: int
    auto_filtered_count: int
    by_filter_type: Dict[str, int]
    trained_count: int

# ============ SimilarityLearningData ============
class SimilarityLearningBase(BaseModel):
    title_a: str = Field(..., max_length=500)
    title_b: str = Field(..., max_length=500)
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    similarity_algorithm: str = Field(default="combined", pattern="^(cosine|jaccard|combined)$")

class SimilarityLearningCreate(SimilarityLearningBase):
    is_similar: bool
    user_action: str = Field(..., pattern="^(matched|rejected|grouped|separated)$")
    common_keywords: List[str] = []
    common_patterns: List[str] = []

class SimilarityLearningResponse(SimilarityLearningBase):
    id: int
    pair_hash: str
    common_keywords: Optional[List[str]]
    common_patterns: Optional[List[str]]
    is_similar: bool
    user_action: str
    is_trained: bool
    created_at: datetime
    class Config:
        from_attributes = True

class SimilarityLearningStats(BaseModel):
    """유사도 학습 통계"""
    total_count: int
    similar_count: int
    different_count: int
    by_action: Dict[str, int]
    avg_similarity_for_similar: float
    avg_similarity_for_different: float
    trained_count: int

class SimilarityThreshold(BaseModel):
    """학습된 유사도 임계값"""
    recommended_threshold: float
    confidence: float
    sample_count: int
